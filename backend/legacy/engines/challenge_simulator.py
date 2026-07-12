"""
Prop Firm Challenge Simulator — Core Engine (Phase 1, Upgraded).

Simulates whether a strategy's trade history can pass a prop firm challenge
under real-world conditions. Processes trades sequentially, day-by-day,
tracking balance (closed PnL) and equity (balance + floating PnL).

Drawdown Rules:
  - Max Daily Drawdown: based on peak equity during the day (intraday HWM).
    Checked at TWO points per trade: (1) floating_min_pnl worst-case,
    (2) post-close equity.
  - Max Total Drawdown (Phase 2 — enforced via TrailingDrawdownTracker):
    - static           → measured from initial_balance.
    - trailing_balance → measured from peak CLOSED balance.
    - trailing_equity  → measured from peak FLOATING equity.
    Legacy alias "trailing" is normalized to "trailing_equity".
  Both checked continuously (at floating worst + post-close), not just end-of-day.

Consistency Rules (from rule_engine Phase 2):
  - max_daily_profit_pct: no single day's profit > X% of total profit.
    Checked after each day completes.

Intraday Equity Field Priority:
  floating_min_pnl > floating_pnl > (no check, log warning)

Output:
  status, days_taken, final_balance, final_equity, max_drawdown,
  max_daily_drawdown, failure_reason, equity_curve, daily_summary.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

from engines.rule_enforcement import (
    TrailingDrawdownTracker,
    normalize_dd_type,
    validate_position_size,
    pre_simulation_exposure_check,
)
from engines.execution_engine import (
    apply_execution_to_trades,
    summarize_config as summarize_execution_config,
)

logger = logging.getLogger(__name__)


# P6 audit fix #4 — prop firm "broker day" boundary.
# FTMO / FundedNext / MFF / E8 / TopStep all reset the daily drawdown
# window at 17:00 America/New_York. Our market data is UTC, so without
# tz-aware bucketing a loss that straddles the NY 17:00 rollover can
# silently split across two UTC days and hide a daily-DD breach.
_BROKER_TZ = ZoneInfo("America/New_York")
_BROKER_DAY_START_HOUR = 17


# ═══════════════════════════════════════════════════════
# Firm Rule Presets (legacy fallback — Phase 2 uses DB via rule_engine)
# ═══════════════════════════════════════════════════════

FIRM_PRESETS = {
    "ftmo": {
        "name": "FTMO",
        "phase": "Challenge",
        "initial_balance": 100000,
        "profit_target_pct": 10.0,
        "max_daily_dd_pct": 5.0,
        "max_total_dd_pct": 10.0,
        "min_trading_days": 4,
        "time_limit_days": 30,
        "drawdown_type": "static",
    },
    "fundednext": {
        "name": "FundedNext",
        "phase": "Challenge Phase 1",
        "initial_balance": 100000,
        "profit_target_pct": 10.0,
        "max_daily_dd_pct": 5.0,
        "max_total_dd_pct": 10.0,
        "min_trading_days": 5,
        "time_limit_days": 0,
        "drawdown_type": "static",
    },
    "pipfarm": {
        "name": "PipFarm",
        "phase": "Evaluation",
        "initial_balance": 100000,
        "profit_target_pct": 12.0,
        "max_daily_dd_pct": 4.0,
        "max_total_dd_pct": 8.0,
        "min_trading_days": 3,
        "time_limit_days": 0,
        "drawdown_type": "trailing",
    },
}


def get_firm_presets():
    """Return all available firm presets."""
    return {k: {**v} for k, v in FIRM_PRESETS.items()}


def get_firm_rules(firm_name: str) -> dict:
    """Get rules for a specific firm. Returns None if not found."""
    return FIRM_PRESETS.get(firm_name.lower())


# ═══════════════════════════════════════════════════════
# Helper: parse trade timestamps into date keys
# ═══════════════════════════════════════════════════════

def _parse_date(ts) -> str:
    """Return the prop-firm "broker day" key for a trade timestamp.

    P6 audit fix #4 — convert the timestamp to America/New_York and
    subtract 17 hours before slicing. This groups trades by broker day
    (17:00 NY → 16:59 NY next day) instead of UTC day, which is what
    FTMO / FundedNext / MFF / E8 / TopStep use to enforce daily DD.

    Timezone-naive timestamps are assumed to be UTC (matches our
    Dukascopy feed).
    """
    if not ts:
        return None
    try:
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif isinstance(ts, datetime):
            dt = ts
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        local = dt.astimezone(_BROKER_TZ)
        return (local - timedelta(hours=_BROKER_DAY_START_HOUR)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        # Degrade gracefully to the raw slice so malformed timestamps
        # don't crash the simulator.
        if isinstance(ts, str):
            return ts[:10]
        return None


def _assign_trade_days(trades: list) -> list:
    """
    Assign each trade a 'day' key. Uses trade timestamp if present,
    otherwise distributes trades across synthetic sequential days.
    """
    enriched = []
    for i, t in enumerate(trades):
        trade = {**t}
        ts = t.get("timestamp") or t.get("close_time") or t.get("exit_time")
        day = _parse_date(ts)
        if not day:
            day = None
        trade["_day"] = day
        trade["_index"] = i
        enriched.append(trade)

    # If no timestamps, assign synthetic days: ~3-5 trades per day
    if all(tr["_day"] is None for tr in enriched):
        trades_per_day = max(1, min(5, len(enriched) // 4))
        base_date = datetime(2024, 1, 1)
        for i, tr in enumerate(enriched):
            day_offset = i // trades_per_day
            tr["_day"] = (base_date + timedelta(days=day_offset)).strftime("%Y-%m-%d")

    # For trades with partial timestamps, fill gaps forward
    last_day = None
    for tr in enriched:
        if tr["_day"] is None:
            tr["_day"] = last_day or "2024-01-01"
        last_day = tr["_day"]

    return enriched


# ═══════════════════════════════════════════════════════
# Core Simulation
# ═══════════════════════════════════════════════════════

def simulate_challenge(trades: list, rules_config: dict) -> dict:
    """
    Simulate a prop firm challenge against a list of trades.

    Args:
        trades: list of trade dicts. Each must have 'net_pnl' (closed P&L in $).
                Optional (priority order for intraday worst-case):
                  'floating_min_pnl' (worst unrealized PnL during trade — preferred),
                  'floating_pnl' (fallback for intraday check),
                  'timestamp'/'close_time' for day assignment.
        rules_config: dict with keys:
            initial_balance, profit_target_pct, max_daily_dd_pct,
            max_total_dd_pct, min_trading_days, time_limit_days,
            drawdown_type ('static' | 'trailing'),
            consistency: {enabled, max_daily_profit_pct} (optional).

    Returns:
        Structured result dict.
    """
    # ── Validate inputs ──
    initial_balance = rules_config.get("initial_balance", 100000)
    profit_target_pct = rules_config.get("profit_target_pct", 10.0)
    max_daily_dd_pct = rules_config.get("max_daily_dd_pct", 5.0)
    max_total_dd_pct = rules_config.get("max_total_dd_pct", 10.0)
    min_trading_days = rules_config.get("min_trading_days", 4)
    time_limit_days = rules_config.get("time_limit_days", 0)
    drawdown_type = rules_config.get("drawdown_type", "static")

    # Consistency rules (from rule_engine Phase 2)
    consistency_cfg = rules_config.get("consistency", {})
    consistency_enabled = consistency_cfg.get("enabled", False) if isinstance(consistency_cfg, dict) else False
    max_daily_profit_pct = consistency_cfg.get("max_daily_profit_pct") if consistency_enabled else None

    # Position sizing rules (Phase 2 upgrade)
    pos_cfg = rules_config.get("position_sizing", {})
    pos_sizing_enabled = pos_cfg.get("enabled", False) if isinstance(pos_cfg, dict) else False
    max_lot_per_trade = pos_cfg.get("max_lot_per_trade") if pos_sizing_enabled else None
    max_total_exposure = pos_cfg.get("max_total_exposure") if pos_sizing_enabled else None

    # Scaling rule (OPTIONAL — toggle-based risk reduction).
    # When enabled AND cumulative DD% >= threshold_dd_pct, every subsequent
    # trade's net_pnl and floating_min_pnl are multiplied by risk_multiplier
    # to approximate a smaller position. When disabled, ignored completely.
    scaling_cfg = rules_config.get("scaling_rule", {})
    scaling_enabled = bool(scaling_cfg.get("enabled")) if isinstance(scaling_cfg, dict) else False
    scaling_threshold_pct = (
        float(scaling_cfg.get("threshold_dd_pct") or 0.0) if scaling_enabled else 0.0
    )
    scaling_multiplier = (
        float(scaling_cfg.get("risk_multiplier") or 1.0) if scaling_enabled else 1.0
    )
    scaling_triggered_at_trade = None  # trade index when scaling first engaged
    scaled_trades_count = 0

    # Normalize trailing DD type (Phase 2): static | trailing_balance | trailing_equity.
    # Legacy alias "trailing" maps to "trailing_equity" (matches historical behavior).
    drawdown_type = normalize_dd_type(drawdown_type)

    profit_target_usd = initial_balance * (profit_target_pct / 100.0)
    max_daily_dd_usd = initial_balance * (max_daily_dd_pct / 100.0)
    max_total_dd_usd = initial_balance * (max_total_dd_pct / 100.0)

    # ── Handle edge cases ──
    if not trades or len(trades) == 0:
        return {
            "status": "fail",
            "failure_reason": "no_trades",
            "days_taken": 0,
            "trading_days": 0,
            "final_balance": initial_balance,
            "final_equity": initial_balance,
            "max_drawdown_pct": 0.0,
            "max_daily_drawdown_pct": 0.0,
            "peak_equity": initial_balance,
            "profit_pct": 0.0,
            "equity_curve": [initial_balance],
            "daily_summary": [],
            "consistency_violated": False,
            "rules_used": _rules_summary(rules_config),
        }

    # ── Assign trades to days ──
    enriched_trades = _assign_trade_days(trades)

    # ── Execution realism layer (Phase: Execution Engine) ──
    # No-op when rules_config['execution']['enabled'] is False (default).
    # When ON: applies spread, slippage, and intrabar worst-case SL-before-TP
    # flipping. Mutates net_pnl / floating_min_pnl on the enriched trade copies
    # BEFORE the DD logic runs — so drawdowns reflect realistic execution costs.
    enriched_trades = apply_execution_to_trades(enriched_trades, rules_config)

    # ── Pre-simulation: Phase 2 — position sizing + aggregate exposure ──
    position_sizing_violation = None
    exposure_violation = None
    if pos_sizing_enabled:
        if max_lot_per_trade is not None:
            for i, t in enumerate(enriched_trades):
                v = validate_position_size(t, max_lot_per_trade)
                if v is not None:
                    v["trade_index"] = i
                    position_sizing_violation = v
                    break

        if position_sizing_violation is None and max_total_exposure is not None:
            exposure_violation = pre_simulation_exposure_check(
                enriched_trades, max_total_exposure
            )

    if position_sizing_violation:
        return {
            "status": "fail",
            "failure_reason": "position_sizing",
            "position_sizing_violation": position_sizing_violation,
            "days_taken": 0,
            "trading_days": 0,
            "final_balance": initial_balance,
            "final_equity": initial_balance,
            "max_drawdown_pct": 0.0,
            "max_daily_drawdown_pct": 0.0,
            "peak_equity": initial_balance,
            "profit_pct": 0.0,
            "equity_curve": [initial_balance],
            "daily_summary": [],
            "consistency_violated": False,
            "rules_used": _rules_summary(rules_config),
        }

    if exposure_violation:
        return {
            "status": "fail",
            "failure_reason": "exposure",
            "exposure_violation": exposure_violation,
            "days_taken": 0,
            "trading_days": 0,
            "final_balance": initial_balance,
            "final_equity": initial_balance,
            "max_drawdown_pct": 0.0,
            "max_daily_drawdown_pct": 0.0,
            "peak_equity": initial_balance,
            "profit_pct": 0.0,
            "equity_curve": [initial_balance],
            "daily_summary": [],
            "consistency_violated": False,
            "rules_used": _rules_summary(rules_config),
        }

    # Group by day, preserving order
    day_order = []
    days_map = defaultdict(list)
    for tr in enriched_trades:
        day = tr["_day"]
        if day not in days_map:
            day_order.append(day)
        days_map[day].append(tr)

    # ── Simulation state ──
    balance = initial_balance
    equity = initial_balance
    # Phase 2: single tracker handles static / trailing_balance / trailing_equity.
    dd_tracker = TrailingDrawdownTracker(drawdown_type, initial_balance, max_total_dd_usd)
    max_dd_pct_seen = 0.0
    max_daily_dd_pct_seen = 0.0

    equity_curve = [round(initial_balance, 2)]
    daily_summary = []
    failure_reason = None
    failed = False
    passed = False
    trading_day_count = 0
    total_trades_processed = 0
    consistency_violated = False
    floating_estimated_count = 0

    # Daily profit tracking for consistency rule
    daily_profits = {}  # day_key → profit_usd

    # ── Day-by-day processing ──
    for day_idx, day_key in enumerate(day_order):
        if failed:
            break

        day_trades = days_map[day_key]

        # Time limit check
        if time_limit_days > 0 and day_idx >= time_limit_days:
            failed = True
            failure_reason = "time_limit"
            break

        day_peak_equity = equity
        day_low_equity = equity
        day_pnl = 0.0
        day_trade_count = 0
        day_worst_daily_dd = 0.0

        # ── Process each trade in the day ──
        for trade in day_trades:
            # Scaling rule — risk reduction after cumulative DD threshold.
            # Uses a shallow trade copy so the original list isn't mutated
            # across repeat simulations.
            if scaling_enabled and max_dd_pct_seen >= scaling_threshold_pct:
                scaled_trade = dict(trade)
                scaled_trade["net_pnl"] = float(trade.get("net_pnl", 0) or 0) * scaling_multiplier
                if trade.get("floating_min_pnl") is not None:
                    scaled_trade["floating_min_pnl"] = (
                        float(trade["floating_min_pnl"]) * scaling_multiplier
                    )
                if trade.get("floating_pnl") is not None:
                    scaled_trade["floating_pnl"] = (
                        float(trade["floating_pnl"]) * scaling_multiplier
                    )
                trade = scaled_trade
                scaled_trades_count += 1
                if scaling_triggered_at_trade is None:
                    scaling_triggered_at_trade = total_trades_processed

            net_pnl = trade.get("net_pnl", 0)

            # ── Resolve floating worst-case (priority: floating_min_pnl > floating_pnl > estimate) ──
            floating_worst = trade.get("floating_min_pnl")
            if floating_worst is None:
                floating_worst = trade.get("floating_pnl")
            if floating_worst is None:
                # Conservative estimation: no trade bypasses intraday DD logic
                if net_pnl < 0:
                    # Losing trade: assume it went 2x deeper before partial recovery
                    floating_worst = net_pnl * 2.0
                elif net_pnl > 0:
                    # Winning trade: assume adverse excursion of 50% of final profit
                    floating_worst = -abs(net_pnl) * 0.5
                else:
                    floating_worst = 0
                floating_estimated = True
            else:
                floating_estimated = False

            if floating_estimated:
                floating_estimated_count += 1

            # ── CHECKPOINT 1: Intraday worst-case (before close) ──
            if floating_worst < 0:
                intraday_equity_low = balance + floating_worst
                if intraday_equity_low < day_low_equity:
                    day_low_equity = intraday_equity_low

                # Check daily DD at floating worst
                daily_dd_at_float = day_peak_equity - intraday_equity_low
                if daily_dd_at_float > max_daily_dd_usd:
                    failed = True
                    failure_reason = "daily_dd"
                    equity = intraday_equity_low
                    equity_curve.append(round(equity, 2))
                    day_worst_daily_dd = max(day_worst_daily_dd, daily_dd_at_float)
                    breach_daily_pct = (daily_dd_at_float / initial_balance) * 100
                    if breach_daily_pct > max_daily_dd_pct_seen:
                        max_daily_dd_pct_seen = breach_daily_pct
                    breach_total = dd_tracker.observe(intraday_equity_low)
                    breach_total_pct = (breach_total / initial_balance) * 100
                    if breach_total_pct > max_dd_pct_seen:
                        max_dd_pct_seen = breach_total_pct
                    break

                # Check total DD at floating worst
                total_dd_at_float = dd_tracker.observe(intraday_equity_low)
                if total_dd_at_float > max_total_dd_usd:
                    failed = True
                    failure_reason = "total_dd"
                    equity = intraday_equity_low
                    equity_curve.append(round(equity, 2))
                    breach_total_pct = (total_dd_at_float / initial_balance) * 100
                    if breach_total_pct > max_dd_pct_seen:
                        max_dd_pct_seen = breach_total_pct
                    breach_daily = day_peak_equity - intraday_equity_low
                    breach_daily_pct = (breach_daily / initial_balance) * 100
                    if breach_daily_pct > max_daily_dd_pct_seen:
                        max_daily_dd_pct_seen = breach_daily_pct
                    break

            # ── CHECKPOINT 2: Post-close ──
            balance += net_pnl
            equity = balance
            day_pnl += net_pnl
            day_trade_count += 1
            total_trades_processed += 1

            if equity > day_peak_equity:
                day_peak_equity = equity
            if equity < day_low_equity:
                day_low_equity = equity
            # Phase 2: tracker picks up new peaks for balance/equity trailing variants.
            dd_tracker.update_balance(balance)
            dd_tracker.update_equity(equity)

            # Post-close daily DD
            daily_dd_now = day_peak_equity - equity
            day_worst_daily_dd = max(day_worst_daily_dd, daily_dd_now)

            if daily_dd_now > max_daily_dd_usd:
                failed = True
                failure_reason = "daily_dd"
                daily_dd_pct_now = (daily_dd_now / initial_balance) * 100
                if daily_dd_pct_now > max_daily_dd_pct_seen:
                    max_daily_dd_pct_seen = daily_dd_pct_now
                total_dd_here = dd_tracker.observe(equity)
                total_dd_pct_here = (total_dd_here / initial_balance) * 100
                if total_dd_pct_here > max_dd_pct_seen:
                    max_dd_pct_seen = total_dd_pct_here
                equity_curve.append(round(equity, 2))
                break

            # Post-close total DD
            total_dd_now = dd_tracker.observe(equity)
            if total_dd_now > max_total_dd_usd:
                failed = True
                failure_reason = "total_dd"
                total_dd_pct_now = (total_dd_now / initial_balance) * 100
                if total_dd_pct_now > max_dd_pct_seen:
                    max_dd_pct_seen = total_dd_pct_now
                daily_dd_pct_now = (daily_dd_now / initial_balance) * 100
                if daily_dd_pct_now > max_daily_dd_pct_seen:
                    max_daily_dd_pct_seen = daily_dd_pct_now
                equity_curve.append(round(equity, 2))
                break

            # Track worst DDs
            total_dd_pct = (total_dd_now / initial_balance) * 100
            if total_dd_pct > max_dd_pct_seen:
                max_dd_pct_seen = total_dd_pct
            daily_dd_pct = (daily_dd_now / initial_balance) * 100
            if daily_dd_pct > max_daily_dd_pct_seen:
                max_daily_dd_pct_seen = daily_dd_pct

            equity_curve.append(round(equity, 2))

        # ── End of day ──
        if day_trade_count > 0:
            trading_day_count += 1

        # Record daily profit
        daily_profits[day_key] = day_pnl

        worst_daily_dd_pct_today = (day_worst_daily_dd / initial_balance) * 100

        daily_summary.append({
            "day": day_key,
            "day_number": day_idx + 1,
            "trades": day_trade_count,
            "pnl": round(day_pnl, 2),
            "balance": round(balance, 2),
            "equity": round(equity, 2),
            "day_peak_equity": round(day_peak_equity, 2),
            "day_low_equity": round(day_low_equity, 2),
            "daily_dd_pct": round(worst_daily_dd_pct_today, 2),
            "total_dd_pct": round(max_dd_pct_seen, 2),
            "cumulative_pnl": round(balance - initial_balance, 2),
            "breached": failed and day_idx == len(daily_summary) - 1,
        })

        if failed:
            break

        # ── Consistency rule check (after each day, once enough trading days) ──
        # Only check when there are enough days for the threshold to be achievable:
        # With T% max, need at least ceil(100/T) trading days.
        if consistency_enabled and max_daily_profit_pct is not None and not failed:
            import math
            min_days_for_check = max(2, math.ceil(100.0 / max_daily_profit_pct))
            total_profit_so_far = balance - initial_balance
            if total_profit_so_far > 0 and trading_day_count >= min_days_for_check:
                for dk, dp in daily_profits.items():
                    if dp > 0:
                        day_share = (dp / total_profit_so_far) * 100
                        if day_share > max_daily_profit_pct:
                            failed = True
                            failure_reason = "consistency"
                            consistency_violated = True
                            break

        if failed:
            break

        # ── Check profit target ──
        profit_made = balance - initial_balance
        if profit_made >= profit_target_usd:
            if trading_day_count >= min_trading_days:
                passed = True
                break

    # ── Final status ──
    profit_made = balance - initial_balance
    profit_pct = (profit_made / initial_balance) * 100

    if passed:
        status = "pass"
    elif failed:
        status = "fail"
    else:
        if profit_made >= profit_target_usd and trading_day_count >= min_trading_days:
            status = "pass"
        elif profit_made < profit_target_usd:
            status = "fail"
            failure_reason = "profit_target_not_reached"
        elif trading_day_count < min_trading_days:
            status = "fail"
            failure_reason = "min_days_not_met"
        else:
            status = "fail"
            failure_reason = "unknown"

    result = {
        "status": status,
        "failure_reason": failure_reason,
        "days_taken": len(daily_summary),
        "trading_days": trading_day_count,
        "calendar_days": len(day_order),
        "total_trades": total_trades_processed,
        "final_balance": round(balance, 2),
        "final_equity": round(equity, 2),
        "peak_equity": round(dd_tracker.peak_equity, 2),
        "profit_usd": round(profit_made, 2),
        "profit_pct": round(profit_pct, 2),
        "profit_target_pct": profit_target_pct,
        "profit_target_usd": round(profit_target_usd, 2),
        "max_drawdown_pct": round(max_dd_pct_seen, 2),
        "max_daily_drawdown_pct": round(max_daily_dd_pct_seen, 2),
        "max_daily_dd_limit_pct": max_daily_dd_pct,
        "max_total_dd_limit_pct": max_total_dd_pct,
        "drawdown_type": drawdown_type,
        "min_trading_days_required": min_trading_days,
        "consistency_violated": consistency_violated,
        "scaling_rule": {
            "enabled": scaling_enabled,
            "triggered": scaled_trades_count > 0,
            "triggered_at_trade": scaling_triggered_at_trade,
            "scaled_trades": scaled_trades_count,
            "threshold_dd_pct": scaling_threshold_pct if scaling_enabled else None,
            "risk_multiplier": scaling_multiplier if scaling_enabled else None,
        },
        "equity_curve": equity_curve,
        "daily_summary": daily_summary,
        "rules_used": _rules_summary(rules_config),
    }

    # Execution cost summary (non-breaking, additive). Sums the execution-engine
    # per-trade markers on the enriched trade list. Zeros when execution is off.
    exec_enabled = bool((rules_config or {}).get("execution", {}).get("enabled"))
    total_spread_cost = sum(t.get("_exec_spread_cost", 0.0) for t in enriched_trades)
    total_slippage_cost = sum(t.get("_exec_slippage_cost", 0.0) for t in enriched_trades)
    total_commission = sum(t.get("_exec_commission_cost", 0.0) for t in enriched_trades)
    result["execution_summary"] = {
        "enabled": exec_enabled,
        "total_spread_cost": round(total_spread_cost, 2),
        "total_slippage_cost": round(total_slippage_cost, 2),
        "total_commission": round(total_commission, 2),
        "total_execution_cost": round(total_spread_cost + total_slippage_cost + total_commission, 2),
    }

    if floating_estimated_count > 0:
        result["warnings"] = [
            f"{floating_estimated_count} trade(s) had no floating_min_pnl or floating_pnl — "
            "intraday worst-case was estimated conservatively (losers: 2x net_pnl, winners: -0.5x net_pnl)"
        ]
        result["floating_estimated_count"] = floating_estimated_count

    return result


def _rules_summary(rules_config: dict) -> dict:
    """Build a clean summary of the rules used.

    Exposes CORE rules always, plus the enabled/disabled state of each
    OPTIONAL rule so downstream consumers (UI, ranker, paper-exec
    telemetry) can show "which toggles are on" without re-reading the
    raw config.
    """
    consistency = rules_config.get("consistency", {}) or {}
    position_sizing = rules_config.get("position_sizing", {}) or {}
    scaling = rules_config.get("scaling_rule", {}) or {}
    news = rules_config.get("news_restriction", {}) or {}
    return {
        # Core
        "firm_name": rules_config.get("name", "Custom"),
        "initial_balance": rules_config.get("initial_balance", 100000),
        "profit_target_pct": rules_config.get("profit_target_pct", 10.0),
        "max_daily_dd_pct": rules_config.get("max_daily_dd_pct", 5.0),
        "max_total_dd_pct": rules_config.get("max_total_dd_pct", 10.0),
        "drawdown_type": rules_config.get("drawdown_type", "static"),
        "reset_time": rules_config.get(
            "reset_time", {"timezone": "America/New_York", "hour": 17}
        ),
        "execution": summarize_execution_config(rules_config),
        # Optional — enabled + param snapshot
        "min_trading_days": rules_config.get("min_trading_days", 0),
        "min_trading_days_enabled": bool(rules_config.get("min_trading_days", 0)),
        "time_limit_days": rules_config.get("time_limit_days", 0),
        "consistency_enabled": bool(consistency.get("enabled")) if isinstance(consistency, dict) else False,
        "max_daily_profit_pct": consistency.get("max_daily_profit_pct") if isinstance(consistency, dict) else None,
        "position_sizing_enabled": bool(position_sizing.get("enabled")) if isinstance(position_sizing, dict) else False,
        "max_lot_per_trade": position_sizing.get("max_lot_per_trade") if isinstance(position_sizing, dict) else None,
        "max_total_exposure": position_sizing.get("max_total_exposure") if isinstance(position_sizing, dict) else None,
        "scaling_rule_enabled": bool(scaling.get("enabled")) if isinstance(scaling, dict) else False,
        "scaling_threshold_dd_pct": scaling.get("threshold_dd_pct") if isinstance(scaling, dict) else None,
        "scaling_risk_multiplier": scaling.get("risk_multiplier") if isinstance(scaling, dict) else None,
        "news_restriction_enabled": bool(news.get("enabled")) if isinstance(news, dict) else False,
        "news_restriction_enforced": bool(news.get("enforced")) if isinstance(news, dict) else False,
        "news_blackout_minutes": news.get("blackout_minutes") if isinstance(news, dict) else None,
    }

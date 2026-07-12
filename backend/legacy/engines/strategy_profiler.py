"""
Strategy Profiler — DNA Layer (Phase 3).

Builds a comprehensive behavioral profile for any strategy based on its trade history.
Used downstream by the matching engine to pair strategies with compatible prop firm rules.

Sections:
  risk      — drawdown metrics, daily DD distribution
  behavior  — trades/day, win rate, avg win/loss, risk-reward
  consistency — profit spread, largest day, consecutive streaks
  time      — holding periods, intraday/swing classification
  stability — Sharpe, profit factor, equity curve smoothness
  classification — DNA tags (type, risk, consistency, speed)
"""

import math
import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════

def _safe_div(a, b, default=0.0):
    return round(a / b, 4) if b else default


def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0.0
    idx = (pct / 100) * (len(sorted_vals) - 1)
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (idx - lo)


def _parse_ts(ts):
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(ts[:19], fmt)
            except ValueError:
                continue
    return None


def _extract_day(trade):
    for key in ("timestamp", "close_time", "exit_time", "entry_time"):
        ts = _parse_ts(trade.get(key))
        if ts:
            return ts.strftime("%Y-%m-%d"), ts
    return None, None


# ═══════════════════════════════════════════════════════
# Risk Metrics
# ═══════════════════════════════════════════════════════

def _calc_risk(trades, initial_balance):
    balance = initial_balance
    peak = initial_balance
    drawdowns = []
    current_dd = 0.0
    daily_pnls = defaultdict(float)

    for t in trades:
        pnl = t.get("net_pnl", 0)
        balance += pnl
        if balance > peak:
            if current_dd > 0:
                drawdowns.append(current_dd)
            peak = balance
            current_dd = 0.0
        dd = peak - balance
        if dd > current_dd:
            current_dd = dd

        day, _ = _extract_day(t)
        if day:
            daily_pnls[day] += pnl

    if current_dd > 0:
        drawdowns.append(current_dd)

    max_dd_usd = max(drawdowns) if drawdowns else 0
    max_dd_pct = _safe_div(max_dd_usd, initial_balance) * 100
    avg_dd_usd = _safe_div(sum(drawdowns), len(drawdowns)) if drawdowns else 0
    avg_dd_pct = _safe_div(avg_dd_usd, initial_balance) * 100

    # Daily drawdown distribution
    daily_dd_pcts = []
    day_keys = sorted(daily_pnls.keys())
    running = initial_balance
    day_peak = initial_balance
    for dk in day_keys:
        day_start_eq = running
        running += daily_pnls[dk]
        if running > day_peak:
            day_peak = running
        day_dd = max(0, day_start_eq - running)
        daily_dd_pcts.append(round(_safe_div(day_dd, initial_balance) * 100, 2))

    sorted_dd = sorted(daily_dd_pcts)

    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "avg_drawdown_pct": round(avg_dd_pct, 2),
        "avg_drawdown_usd": round(avg_dd_usd, 2),
        "drawdown_count": len(drawdowns),
        "daily_dd_distribution": {
            "p50": round(_percentile(sorted_dd, 50), 2),
            "p75": round(_percentile(sorted_dd, 75), 2),
            "p90": round(_percentile(sorted_dd, 90), 2),
            "p95": round(_percentile(sorted_dd, 95), 2),
            "max": round(max(sorted_dd) if sorted_dd else 0, 2),
        },
    }


# ═══════════════════════════════════════════════════════
# Trade Behavior
# ═══════════════════════════════════════════════════════

def _calc_behavior(trades):
    total = len(trades)
    if total == 0:
        return {
            "total_trades": 0, "trades_per_day": 0, "win_rate": 0,
            "avg_win": 0, "avg_loss": 0, "risk_reward_ratio": 0,
            "largest_win": 0, "largest_loss": 0,
        }

    wins = [t for t in trades if t.get("net_pnl", 0) > 0]
    losses = [t for t in trades if t.get("net_pnl", 0) < 0]
    flat = [t for t in trades if t.get("net_pnl", 0) == 0]

    days = set()
    for t in trades:
        d, _ = _extract_day(t)
        if d:
            days.add(d)
    num_days = max(len(days), 1)

    avg_win = _safe_div(sum(t["net_pnl"] for t in wins), len(wins)) if wins else 0
    avg_loss = abs(_safe_div(sum(t["net_pnl"] for t in losses), len(losses))) if losses else 0
    rr = _safe_div(avg_win, avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0)

    all_pnls = [t.get("net_pnl", 0) for t in trades]

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "flat_trades": len(flat),
        "trades_per_day": round(total / num_days, 2),
        "trading_days": num_days,
        "win_rate": round(len(wins) / total * 100, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "risk_reward_ratio": round(rr, 2),
        "largest_win": round(max(all_pnls), 2),
        "largest_loss": round(min(all_pnls), 2),
    }


# ═══════════════════════════════════════════════════════
# Consistency
# ═══════════════════════════════════════════════════════

def _calc_consistency(trades, initial_balance):
    if not trades:
        return {
            "profit_distribution": {}, "largest_winning_day_pct": 0,
            "largest_losing_day_pct": 0, "max_consecutive_wins": 0,
            "max_consecutive_losses": 0, "avg_consecutive_wins": 0,
            "avg_consecutive_losses": 0,
        }

    daily_pnl = defaultdict(float)
    for t in trades:
        d, _ = _extract_day(t)
        if d:
            daily_pnl[d] += t.get("net_pnl", 0)

    day_pnls = list(daily_pnl.values())
    total_profit = sum(p for p in day_pnls if p > 0) or 1.0

    # Profit distribution: % of total profit from each day
    day_profit_pcts = sorted(
        [round(p / total_profit * 100, 2) for p in day_pnls if p > 0],
        reverse=True,
    )

    largest_win_day = max(day_pnls) if day_pnls else 0
    largest_loss_day = min(day_pnls) if day_pnls else 0

    # Consecutive streaks
    streaks_w = []
    streaks_l = []
    cur_w = 0
    cur_l = 0
    for t in trades:
        pnl = t.get("net_pnl", 0)
        if pnl > 0:
            cur_w += 1
            if cur_l > 0:
                streaks_l.append(cur_l)
            cur_l = 0
        elif pnl < 0:
            cur_l += 1
            if cur_w > 0:
                streaks_w.append(cur_w)
            cur_w = 0
    if cur_w > 0:
        streaks_w.append(cur_w)
    if cur_l > 0:
        streaks_l.append(cur_l)

    return {
        "profit_distribution": {
            "top_day_pct": day_profit_pcts[0] if day_profit_pcts else 0,
            "top_3_days_pct": round(sum(day_profit_pcts[:3]), 2) if day_profit_pcts else 0,
            "total_profitable_days": len([p for p in day_pnls if p > 0]),
            "total_losing_days": len([p for p in day_pnls if p < 0]),
        },
        "largest_winning_day_usd": round(largest_win_day, 2),
        "largest_winning_day_pct": round(_safe_div(largest_win_day, initial_balance) * 100, 2),
        "largest_losing_day_usd": round(largest_loss_day, 2),
        "largest_losing_day_pct": round(_safe_div(abs(largest_loss_day), initial_balance) * 100, 2),
        "max_consecutive_wins": max(streaks_w) if streaks_w else 0,
        "max_consecutive_losses": max(streaks_l) if streaks_l else 0,
        "avg_consecutive_wins": round(_safe_div(sum(streaks_w), len(streaks_w)), 1) if streaks_w else 0,
        "avg_consecutive_losses": round(_safe_div(sum(streaks_l), len(streaks_l)), 1) if streaks_l else 0,
    }


# ═══════════════════════════════════════════════════════
# Time Metrics
# ═══════════════════════════════════════════════════════

def _calc_time(trades):
    holding_minutes = []
    for t in trades:
        entry_ts = _parse_ts(t.get("entry_time") or t.get("timestamp"))
        exit_ts = _parse_ts(t.get("close_time") or t.get("exit_time"))
        if entry_ts and exit_ts and exit_ts > entry_ts:
            delta = (exit_ts - entry_ts).total_seconds() / 60.0
            holding_minutes.append(delta)

    if not holding_minutes:
        # Estimate from trade density
        days = set()
        for t in trades:
            d, _ = _extract_day(t)
            if d:
                days.add(d)
        tpd = len(trades) / max(len(days), 1) if trades else 0
        # heuristic: >5 trades/day = likely scalping, 1-5 = intraday, <1 = swing
        if tpd > 5:
            est_class = "scalping"
            est_avg = 15.0
        elif tpd >= 1:
            est_class = "intraday"
            est_avg = 120.0
        else:
            est_class = "swing"
            est_avg = 1440.0
        return {
            "avg_holding_minutes": round(est_avg, 1),
            "min_holding_minutes": 0,
            "max_holding_minutes": 0,
            "holding_data_available": False,
            "intraday_pct": 0,
            "swing_pct": 0,
            "estimated_type": est_class,
        }

    sorted_h = sorted(holding_minutes)
    avg_h = sum(holding_minutes) / len(holding_minutes)
    intraday_count = sum(1 for h in holding_minutes if h < 1440)
    swing_count = len(holding_minutes) - intraday_count

    return {
        "avg_holding_minutes": round(avg_h, 1),
        "median_holding_minutes": round(_percentile(sorted_h, 50), 1),
        "min_holding_minutes": round(min(holding_minutes), 1),
        "max_holding_minutes": round(max(holding_minutes), 1),
        "holding_data_available": True,
        "intraday_pct": round(intraday_count / len(holding_minutes) * 100, 1),
        "swing_pct": round(swing_count / len(holding_minutes) * 100, 1),
        "estimated_type": "scalping" if avg_h < 30 else ("intraday" if avg_h < 1440 else "swing"),
    }


# ═══════════════════════════════════════════════════════
# Performance Stability
# ═══════════════════════════════════════════════════════

def _calc_stability(trades, initial_balance):
    if not trades:
        return {
            "sharpe_ratio": 0, "profit_factor": 0,
            "equity_curve_smoothness": 0, "net_profit": 0,
            "total_return_pct": 0,
        }

    pnls = [t.get("net_pnl", 0) for t in trades]
    gross_profit = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    net_profit = sum(pnls)

    profit_factor = _safe_div(gross_profit, gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)

    # Sharpe from trade returns
    returns = [p / initial_balance for p in pnls]
    if len(returns) >= 2:
        mean_r = sum(returns) / len(returns)
        var = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
        std_r = math.sqrt(var)
        sharpe = (mean_r / std_r) * math.sqrt(min(len(returns), 252)) if std_r > 1e-10 else 0
    else:
        sharpe = 0

    # Equity curve smoothness: R² of equity curve vs straight line
    equity = [initial_balance]
    for p in pnls:
        equity.append(equity[-1] + p)

    n = len(equity)
    if n >= 3:
        # Linear regression of equity curve
        x_mean = (n - 1) / 2
        y_mean = sum(equity) / n
        ss_xy = sum((i - x_mean) * (equity[i] - y_mean) for i in range(n))
        ss_xx = sum((i - x_mean) ** 2 for i in range(n))
        slope = ss_xy / ss_xx if ss_xx > 0 else 0
        intercept = y_mean - slope * x_mean
        predicted = [intercept + slope * i for i in range(n)]
        ss_res = sum((equity[i] - predicted[i]) ** 2 for i in range(n))
        ss_tot = sum((equity[i] - y_mean) ** 2 for i in range(n))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        smoothness = round(max(0, r_squared) * 100, 2)
    else:
        smoothness = 0

    return {
        "sharpe_ratio": round(sharpe, 3),
        "profit_factor": round(profit_factor, 2),
        "equity_curve_smoothness": smoothness,
        "net_profit": round(net_profit, 2),
        "total_return_pct": round(net_profit / initial_balance * 100, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
    }


# ═══════════════════════════════════════════════════════
# DNA Classification
# ═══════════════════════════════════════════════════════

def _classify(risk, behavior, consistency, time_metrics, stability):
    # Type classification
    est_type = time_metrics.get("estimated_type", "intraday")
    tpd = behavior.get("trades_per_day", 0)
    if est_type == "scalping" or tpd > 8:
        strategy_type = "scalping"
    elif est_type == "swing" or tpd < 0.8:
        strategy_type = "swing"
    else:
        strategy_type = "intraday"

    # Risk level
    max_dd = risk.get("max_drawdown_pct", 0)
    dd_p90 = risk.get("daily_dd_distribution", {}).get("p90", 0)
    if max_dd > 15 or dd_p90 > 3:
        risk_level = "high"
    elif max_dd > 8 or dd_p90 > 1.5:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Consistency level
    top_day = consistency.get("profit_distribution", {}).get("top_day_pct", 0)
    smoothness = stability.get("equity_curve_smoothness", 0)
    if top_day < 25 and smoothness > 60:
        consistency_level = "high"
    elif top_day < 50 and smoothness > 30:
        consistency_level = "medium"
    else:
        consistency_level = "low"

    # Speed
    avg_hold = time_metrics.get("avg_holding_minutes", 120)
    if avg_hold < 30:
        speed = "fast"
    elif avg_hold < 480:
        speed = "moderate"
    else:
        speed = "slow"

    # Summary tags
    tags = [strategy_type, risk_level + "_risk"]
    if stability.get("sharpe_ratio", 0) > 1.0:
        tags.append("strong_sharpe")
    if behavior.get("win_rate", 0) > 60:
        tags.append("high_winrate")
    if behavior.get("risk_reward_ratio", 0) > 2.0:
        tags.append("high_rr")
    if consistency_level == "high":
        tags.append("consistent")
    if max_dd < 5:
        tags.append("tight_dd")

    return {
        "type": strategy_type,
        "risk_level": risk_level,
        "consistency_level": consistency_level,
        "speed": speed,
        "tags": tags,
    }


# ═══════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════

def profile_strategy(trades: list, initial_balance: float = 10000) -> dict:
    """
    Build a complete behavioral profile (DNA) for a strategy.

    Args:
        trades: list of trade dicts with at minimum 'net_pnl'.
                Optional fields enhance the profile:
                  timestamp, entry_time, close_time/exit_time,
                  floating_pnl, gross_pnl, commission.
        initial_balance: starting capital for ratio calculations.

    Returns:
        Structured profile dict with sections:
          risk, behavior, consistency, time, stability, classification.
    """
    if not trades:
        return {
            "risk": {"max_drawdown_pct": 0, "avg_drawdown_pct": 0, "drawdown_count": 0,
                     "max_drawdown_usd": 0, "avg_drawdown_usd": 0,
                     "daily_dd_distribution": {"p50": 0, "p75": 0, "p90": 0, "p95": 0, "max": 0}},
            "behavior": {"total_trades": 0, "trades_per_day": 0, "win_rate": 0,
                         "avg_win": 0, "avg_loss": 0, "risk_reward_ratio": 0,
                         "largest_win": 0, "largest_loss": 0, "winning_trades": 0,
                         "losing_trades": 0, "flat_trades": 0, "trading_days": 0},
            "consistency": {"profit_distribution": {"top_day_pct": 0, "top_3_days_pct": 0,
                            "total_profitable_days": 0, "total_losing_days": 0},
                           "largest_winning_day_pct": 0, "largest_winning_day_usd": 0,
                           "largest_losing_day_pct": 0, "largest_losing_day_usd": 0,
                           "max_consecutive_wins": 0, "max_consecutive_losses": 0,
                           "avg_consecutive_wins": 0, "avg_consecutive_losses": 0},
            "time": {"avg_holding_minutes": 0, "holding_data_available": False,
                     "estimated_type": "unknown", "intraday_pct": 0, "swing_pct": 0},
            "stability": {"sharpe_ratio": 0, "profit_factor": 0,
                          "equity_curve_smoothness": 0, "net_profit": 0,
                          "total_return_pct": 0, "gross_profit": 0, "gross_loss": 0},
            "classification": {"type": "unknown", "risk_level": "unknown",
                               "consistency_level": "unknown", "speed": "unknown", "tags": []},
            "meta": {"trade_count": 0, "initial_balance": initial_balance,
                     "profile_version": "1.0"},
        }

    risk = _calc_risk(trades, initial_balance)
    behavior = _calc_behavior(trades)
    consistency = _calc_consistency(trades, initial_balance)
    time_metrics = _calc_time(trades)
    stability = _calc_stability(trades, initial_balance)
    classification = _classify(risk, behavior, consistency, time_metrics, stability)

    return {
        "risk": risk,
        "behavior": behavior,
        "consistency": consistency,
        "time": time_metrics,
        "stability": stability,
        "classification": classification,
        "meta": {
            "trade_count": len(trades),
            "initial_balance": initial_balance,
            "profile_version": "1.0",
        },
    }

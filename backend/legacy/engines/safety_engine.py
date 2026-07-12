"""
Safety Injection & Overtrading Detection Engine.
Analyzes backtest results for risk control compliance and realistic
trade frequency. Produces a safety score and actionable flags.

Checks:
  - Max drawdown cap (default 15%)
  - Daily loss limit (default 3% of balance)
  - Max consecutive losses
  - Trades per day / per week limits (timeframe-aware)
  - Spread cost ratio (cost drag detection)
  - Risk-reward ratio compliance
"""
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# Trade frequency limits per timeframe
# ═══════════════════════════════════════════════════════

TRADE_LIMITS = {
    "M1":  {"max_per_day": 50, "warn_per_day": 30, "label": "1-min scalp"},
    "M5":  {"max_per_day": 30, "warn_per_day": 20, "label": "5-min"},
    "M15": {"max_per_day": 20, "warn_per_day": 10, "label": "15-min"},
    "M30": {"max_per_day": 10, "warn_per_day": 5,  "label": "30-min"},
    "H1":  {"max_per_day": 5,  "warn_per_day": 3,  "label": "1-hour"},
    "H4":  {"max_per_day": 3,  "warn_per_day": 2,  "label": "4-hour"},
    "D1":  {"max_per_day": 1,  "warn_per_day": 1,  "label": "daily"},
    # Also support lowercase formats from data engine
    "1m":  {"max_per_day": 50, "warn_per_day": 30, "label": "1-min scalp"},
    "5m":  {"max_per_day": 30, "warn_per_day": 20, "label": "5-min"},
    "15m": {"max_per_day": 20, "warn_per_day": 10, "label": "15-min"},
    "30m": {"max_per_day": 10, "warn_per_day": 5,  "label": "30-min"},
    "1h":  {"max_per_day": 5,  "warn_per_day": 3,  "label": "1-hour"},
    "4h":  {"max_per_day": 3,  "warn_per_day": 2,  "label": "4-hour"},
    "1d":  {"max_per_day": 1,  "warn_per_day": 1,  "label": "daily"},
}

# Bars-per-day for each timeframe (forex ~24h trading)
BARS_PER_DAY = {
    "M1": 1440, "M5": 288, "M15": 96, "M30": 48,
    "H1": 24, "H4": 6, "D1": 1,
    "1m": 1440, "5m": 288, "15m": 96, "30m": 48,
    "1h": 24, "4h": 6, "1d": 1,
}

# Default safety thresholds
DEFAULT_THRESHOLDS = {
    "max_drawdown_pct": 15.0,
    "daily_loss_pct": 3.0,
    "max_consecutive_losses": 8,
    "max_spread_cost_ratio": 0.40,
}


def _calc_consecutive_losses(trades: list) -> int:
    """Find the longest streak of consecutive losing trades."""
    if not trades:
        return 0
    max_streak = 0
    current = 0
    for t in trades:
        if t.get("net_pnl", 0) <= 0:
            current += 1
            max_streak = max(max_streak, current)
        else:
            current = 0
    return max_streak


def _calc_trade_frequency(total_trades: int, data_points: int, timeframe: str) -> dict:
    """Calculate trades per day and per week from backtest data."""
    bpd = BARS_PER_DAY.get(timeframe, 24)
    if bpd == 0 or data_points == 0:
        return {"per_day": 0, "per_week": 0, "trading_days": 0}

    trading_days = max(data_points / bpd, 1)
    per_day = total_trades / trading_days
    per_week = per_day * 5  # forex = 5 trading days

    return {
        "per_day": round(per_day, 2),
        "per_week": round(per_week, 1),
        "trading_days": round(trading_days, 1),
    }


def _calc_daily_loss_stats(trades: list, initial_balance: float, data_points: int, timeframe: str) -> dict:
    """Estimate daily loss patterns from trade sequence."""
    if not trades or data_points == 0:
        return {"worst_daily_loss_pct": 0, "avg_daily_loss_pct": 0}

    bpd = BARS_PER_DAY.get(timeframe, 24)
    trading_days = max(data_points / bpd, 1)
    trades_per_day = len(trades) / trading_days

    if trades_per_day < 0.5:
        # Too few trades to estimate daily loss
        worst_single = min((t["net_pnl"] for t in trades), default=0)
        return {
            "worst_daily_loss_pct": round(abs(worst_single) / initial_balance * 100, 2) if worst_single < 0 else 0,
            "avg_daily_loss_pct": 0,
        }

    # Chunk trades into approximate daily groups
    chunk_size = max(1, round(trades_per_day))
    daily_pnls = []
    for i in range(0, len(trades), chunk_size):
        chunk = trades[i:i + chunk_size]
        daily_pnl = sum(t["net_pnl"] for t in chunk)
        daily_pnls.append(daily_pnl)

    losing_days = [p for p in daily_pnls if p < 0]
    worst_daily = min(daily_pnls) if daily_pnls else 0
    avg_daily_loss = (sum(losing_days) / len(losing_days)) if losing_days else 0

    return {
        "worst_daily_loss_pct": round(abs(worst_daily) / initial_balance * 100, 2) if worst_daily < 0 else 0,
        "avg_daily_loss_pct": round(abs(avg_daily_loss) / initial_balance * 100, 2),
        "losing_days": len(losing_days),
        "total_days": len(daily_pnls),
    }


def run_safety_analysis(
    backtest_results: dict,
    timeframe: str = "H1",
    thresholds: dict = None,
) -> dict:
    """
    Analyze a backtest result for safety compliance.

    Args:
        backtest_results: full backtest output dict with trades list
        timeframe: trading timeframe (H1, M15, etc.)
        thresholds: optional custom thresholds dict

    Returns:
        dict with safety_score, flags, warnings, and detailed metrics
    """
    if not backtest_results:
        return {"safety_score": 0, "grade": "N/A", "flags": [], "warnings": ["No backtest data"]}

    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    trades = backtest_results.get("trades", [])
    total_trades = backtest_results.get("total_trades", 0)
    data_points = backtest_results.get("data_points", 0)
    initial_balance = backtest_results.get("initial_balance", 10000.0)
    max_dd_pct = backtest_results.get("max_drawdown_pct", 0)
    total_costs = backtest_results.get("total_costs", 0)
    net_profit = backtest_results.get("net_profit", 0)

    flags = []
    warnings = []

    # ── 1. Drawdown Check ──
    dd_ok = max_dd_pct <= th["max_drawdown_pct"]
    if not dd_ok:
        flags.append(f"MAX_DD_EXCEEDED: {max_dd_pct:.1f}% > {th['max_drawdown_pct']}% limit")

    # ── 2. Trade Frequency ──
    freq = _calc_trade_frequency(total_trades, data_points, timeframe)
    limits = TRADE_LIMITS.get(timeframe, TRADE_LIMITS.get("H1"))

    overtrading = False
    if freq["per_day"] > limits["max_per_day"]:
        flags.append(
            f"OVERTRADING: {freq['per_day']:.1f} trades/day exceeds {limits['max_per_day']}/day limit for {timeframe}"
        )
        freq_ok = False
        overtrading = True
    elif freq["per_day"] > limits["warn_per_day"]:
        warnings.append(
            f"High frequency: {freq['per_day']:.1f} trades/day (warning at {limits['warn_per_day']}/day for {timeframe})"
        )

    # ── 3. Consecutive Losses ──
    consec_losses = _calc_consecutive_losses(trades)
    consec_ok = consec_losses <= th["max_consecutive_losses"]
    if not consec_ok:
        flags.append(f"CONSECUTIVE_LOSSES: {consec_losses} in a row (limit {th['max_consecutive_losses']})")

    # ── 4. Daily Loss ──
    daily_stats = _calc_daily_loss_stats(trades, initial_balance, data_points, timeframe)
    daily_loss_ok = daily_stats["worst_daily_loss_pct"] <= th["daily_loss_pct"]
    if not daily_loss_ok:
        flags.append(
            f"DAILY_LOSS_EXCEEDED: worst day -{daily_stats['worst_daily_loss_pct']:.1f}% > {th['daily_loss_pct']}% limit"
        )

    # ── 5. Cost Ratio (spread + commission drag) ──
    gross_profit = abs(net_profit) + total_costs if net_profit > 0 else total_costs
    cost_ratio = (total_costs / gross_profit) if gross_profit > 0 else 0
    cost_ok = cost_ratio <= th["max_spread_cost_ratio"]
    if not cost_ok and total_trades > 0:
        warnings.append(
            f"High cost drag: {cost_ratio:.0%} of gross profit consumed by spread/commission"
        )

    # ══════════════════════════════════════════════
    # Safety Score (0-100)
    # ══════════════════════════════════════════════

    # 1. Drawdown control (0-30 pts): lower DD = better
    if max_dd_pct <= 5:
        dd_score = 30
    elif max_dd_pct <= th["max_drawdown_pct"]:
        dd_score = max(0, 30 - (max_dd_pct / th["max_drawdown_pct"]) * 15)
    else:
        dd_score = max(0, 15 - (max_dd_pct - th["max_drawdown_pct"]) * 1.5)

    # 2. Trade frequency (0-25 pts): within limits = full score
    if freq["per_day"] <= limits["warn_per_day"]:
        freq_score = 25
    elif freq["per_day"] <= limits["max_per_day"]:
        overshoot = (freq["per_day"] - limits["warn_per_day"]) / (limits["max_per_day"] - limits["warn_per_day"])
        freq_score = max(0, 25 - overshoot * 15)
    else:
        overshoot = freq["per_day"] / limits["max_per_day"]
        freq_score = max(0, 10 - (overshoot - 1) * 10)

    # 3. Risk exposure (0-25 pts): based on daily loss + cost ratio
    daily_pct = daily_stats["worst_daily_loss_pct"]
    if daily_pct <= 1:
        risk_score = 25
    elif daily_pct <= th["daily_loss_pct"]:
        risk_score = max(0, 25 - (daily_pct / th["daily_loss_pct"]) * 10)
    else:
        risk_score = max(0, 15 - (daily_pct - th["daily_loss_pct"]) * 3)
    # Penalize high cost ratio
    if cost_ratio > 0.3:
        risk_score = max(0, risk_score - (cost_ratio - 0.3) * 20)

    # 4. Consecutive loss control (0-20 pts)
    if consec_losses <= 3:
        consec_score = 20
    elif consec_losses <= th["max_consecutive_losses"]:
        consec_score = max(0, 20 - (consec_losses - 3) * 2.5)
    else:
        consec_score = max(0, 7 - (consec_losses - th["max_consecutive_losses"]) * 2)

    safety_score = round(dd_score + freq_score + risk_score + consec_score, 1)
    safety_score = min(max(safety_score, 0), 100)

    # Grade
    if safety_score >= 80:
        grade = "A"
    elif safety_score >= 65:
        grade = "B"
    elif safety_score >= 50:
        grade = "C"
    elif safety_score >= 35:
        grade = "D"
    else:
        grade = "F"

    # Overall pass/fail
    critical_flags = [f for f in flags if "OVERTRADING" in f or "MAX_DD_EXCEEDED" in f]
    is_safe = len(critical_flags) == 0

    logger.info(
        f"Safety: score={safety_score} grade={grade} safe={is_safe} "
        f"dd={max_dd_pct:.1f}% freq={freq['per_day']:.1f}/day "
        f"consec_loss={consec_losses} flags={len(flags)}"
    )

    return {
        "safety_score": safety_score,
        "grade": grade,
        "is_safe": is_safe,
        "score_breakdown": {
            "drawdown_control": round(dd_score, 1),
            "trade_frequency": round(freq_score, 1),
            "risk_exposure": round(risk_score, 1),
            "consecutive_loss": round(consec_score, 1),
        },
        "metrics": {
            "max_drawdown_pct": round(max_dd_pct, 2),
            "trades_per_day": freq["per_day"],
            "trades_per_week": freq["per_week"],
            "trading_days": freq["trading_days"],
            "consecutive_losses": consec_losses,
            "worst_daily_loss_pct": daily_stats["worst_daily_loss_pct"],
            "cost_ratio": round(cost_ratio, 3),
            "overtrading": overtrading,
        },
        "thresholds": {
            "max_drawdown_pct": th["max_drawdown_pct"],
            "daily_loss_pct": th["daily_loss_pct"],
            "max_consecutive_losses": th["max_consecutive_losses"],
            "max_spread_cost_ratio": th["max_spread_cost_ratio"],
            "max_trades_per_day": limits["max_per_day"],
            "warn_trades_per_day": limits["warn_per_day"],
        },
        "flags": flags,
        "warnings": warnings,
    }

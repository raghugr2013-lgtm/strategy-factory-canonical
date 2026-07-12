"""
Monte Carlo Trade Resampling Engine.
Shuffles the real trade sequence from backtest N times,
replays each shuffled order on the initial balance, and
computes statistical robustness metrics.

No fake price data — only real trade P&L values are resampled.
"""
import math
import random
import logging

logger = logging.getLogger(__name__)

DEFAULT_SIMULATIONS = 100
INITIAL_BALANCE = 10000.0


def _replay_trades(trades: list, initial_balance: float) -> dict:
    """
    Replay a sequence of trades on a starting balance.
    Returns net_profit, max_drawdown_pct, profit_factor.
    """
    balance = initial_balance
    peak = initial_balance
    max_dd_usd = 0.0
    gross_wins = 0.0
    gross_losses = 0.0

    for t in trades:
        pnl = t["net_pnl"]
        balance += pnl
        if pnl > 0:
            gross_wins += abs(t.get("gross_pnl", pnl))
        else:
            gross_losses += abs(t.get("gross_pnl", pnl))
        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd_usd:
            max_dd_usd = dd

    net_profit = balance - initial_balance
    return_pct = (net_profit / initial_balance) * 100
    max_dd_pct = (max_dd_usd / peak * 100) if peak > 0 else 0
    pf = (gross_wins / gross_losses) if gross_losses > 0 else (
        float("inf") if gross_wins > 0 else 0
    )

    return {
        "net_profit": round(net_profit, 2),
        "return_pct": round(return_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "final_balance": round(balance, 2),
        "profit_factor": round(min(pf, 99.0), 2),
    }


def _percentile(sorted_vals: list, p: float) -> float:
    """Compute the p-th percentile from a sorted list."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def run_monte_carlo(
    trades: list,
    num_simulations: int = DEFAULT_SIMULATIONS,
    initial_balance: float = INITIAL_BALANCE,
) -> dict:
    """
    Run Monte Carlo trade-order resampling.

    Args:
        trades: list of trade dicts from backtest, each with 'net_pnl' and 'gross_pnl'
        num_simulations: number of shuffled replays (default 100)
        initial_balance: starting account balance

    Returns:
        dict with simulation results, statistics, confidence intervals, and score
    """
    if not trades or len(trades) < 3:
        return {
            "success": False,
            "error": f"Not enough trades for Monte Carlo ({len(trades) if trades else 0}). Need at least 3.",
            "num_trades": len(trades) if trades else 0,
        }

    num_simulations = max(20, min(num_simulations, 500))

    # ── Run original (unshuffled) order first ──
    original = _replay_trades(trades, initial_balance)

    # ── Run N shuffled simulations ──
    sim_results = []
    for _ in range(num_simulations):
        shuffled = trades[:]
        random.shuffle(shuffled)
        sim_results.append(_replay_trades(shuffled, initial_balance))

    # ── Aggregate statistics ──
    returns = sorted([s["return_pct"] for s in sim_results])
    drawdowns = sorted([s["max_drawdown_pct"] for s in sim_results])
    pf_vals = [s["profit_factor"] for s in sim_results]

    mean_return = sum(returns) / len(returns)
    median_return = _percentile(returns, 50)
    std_return = math.sqrt(sum((r - mean_return) ** 2 for r in returns) / len(returns))

    mean_dd = sum(drawdowns) / len(drawdowns)
    worst_dd = max(drawdowns)
    best_dd = min(drawdowns)

    mean_pf = sum(pf_vals) / len(pf_vals)

    # Confidence intervals (2.5th and 97.5th percentile)
    ci_lower = _percentile(returns, 2.5)
    ci_upper = _percentile(returns, 97.5)

    dd_ci_lower = _percentile(drawdowns, 2.5)
    dd_ci_upper = _percentile(drawdowns, 97.5)

    # Probability of loss
    losing_sims = sum(1 for r in returns if r < 0)
    prob_loss = round((losing_sims / len(returns)) * 100, 1)
    prob_profit = round(100 - prob_loss, 1)

    # ── Monte Carlo Stability Score (0-100) ──
    # 1. Consistency: % of profitable sims (0-30 pts)
    consistency_raw = prob_profit / 100
    consistency_score = min(30, consistency_raw * 30)

    # 2. Return stability: low std_dev relative to mean (0-25 pts)
    if abs(mean_return) > 0.01:
        cv = abs(std_return / mean_return)
        return_stability = max(0, min(25, 25 - cv * 8))
    else:
        return_stability = max(0, min(25, 25 - std_return * 2))

    # 3. Drawdown control: low worst-case DD (0-25 pts)
    # 0% DD = 25 pts, 50%+ DD = 0 pts
    dd_score = max(0, min(25, 25 - worst_dd * 0.5))

    # 4. Confidence: lower bound of 95% CI above 0 (0-20 pts)
    if ci_lower > 0:
        conf_score = min(20, 10 + ci_lower * 0.5)
    elif ci_lower > -5:
        conf_score = max(0, 10 + ci_lower * 2)
    else:
        conf_score = 0

    mc_score = round(consistency_score + return_stability + dd_score + conf_score, 1)
    mc_score = min(max(mc_score, 0), 100)

    # Grade
    if mc_score >= 75:
        grade = "A"
    elif mc_score >= 60:
        grade = "B"
    elif mc_score >= 45:
        grade = "C"
    elif mc_score >= 30:
        grade = "D"
    else:
        grade = "F"

    logger.info(
        f"Monte Carlo: {num_simulations} sims, {len(trades)} trades → "
        f"score={mc_score}, mean_ret={mean_return:.2f}%, "
        f"CI=[{ci_lower:.2f}%, {ci_upper:.2f}%], prob_loss={prob_loss}%"
    )

    return {
        "success": True,
        "num_trades": len(trades),
        "num_simulations": num_simulations,
        "initial_balance": initial_balance,
        "original": original,
        "statistics": {
            "mean_return": round(mean_return, 2),
            "median_return": round(median_return, 2),
            "std_return": round(std_return, 2),
            "mean_drawdown": round(mean_dd, 2),
            "worst_drawdown": round(worst_dd, 2),
            "best_drawdown": round(best_dd, 2),
            "mean_profit_factor": round(mean_pf, 2),
            "prob_profit": prob_profit,
            "prob_loss": prob_loss,
        },
        "confidence_95": {
            "return_lower": round(ci_lower, 2),
            "return_upper": round(ci_upper, 2),
            "drawdown_lower": round(dd_ci_lower, 2),
            "drawdown_upper": round(dd_ci_upper, 2),
        },
        "score": mc_score,
        "grade": grade,
        "score_breakdown": {
            "consistency": round(consistency_score, 1),
            "return_stability": round(return_stability, 1),
            "drawdown_control": round(dd_score, 1),
            "confidence": round(conf_score, 1),
        },
        "distribution": {
            "p5": round(_percentile(returns, 5), 2),
            "p25": round(_percentile(returns, 25), 2),
            "p50": round(_percentile(returns, 50), 2),
            "p75": round(_percentile(returns, 75), 2),
            "p95": round(_percentile(returns, 95), 2),
        },
    }

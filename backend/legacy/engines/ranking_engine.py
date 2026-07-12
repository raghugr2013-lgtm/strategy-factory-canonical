"""
Ranking engine: Scores strategies 0-100 based on backtest metrics.
Components (weights shift based on available data):
  Base:        Profit 35%, WR 25%, DD 25%, PF 15%
  +MC:         Profit 30%, WR 20%, DD 20%, PF 15%, MC 15%
  +Safety:     Profit 28%, WR 18%, DD 18%, PF 13%, Safety 10%, MC 13%
  +MC+Safety:  Profit 25%, WR 17%, DD 17%, PF 13%, MC 13%, Safety 15%
"""


def calculate_score(backtest_results: dict, monte_carlo: dict = None, safety: dict = None) -> dict:
    """Calculate a composite score (0-100) for a strategy based on backtest metrics."""
    if not backtest_results:
        return {"score": 0, "breakdown": {}, "grade": "N/A"}

    total_pnl = backtest_results.get("total_pnl_pips", 0)
    win_rate = backtest_results.get("win_rate", 0)
    max_dd = backtest_results.get("max_drawdown_pips", 0)
    pf = backtest_results.get("profit_factor", 0)
    total_trades = backtest_results.get("total_trades", 0)

    if total_trades == 0:
        return {"score": 0, "breakdown": {
            "profit": 0, "win_rate": 0, "drawdown": 0, "profit_factor": 0
        }, "grade": "N/A"}

    has_mc = monte_carlo and monte_carlo.get("success") and monte_carlo.get("score") is not None
    has_safety = safety and safety.get("safety_score") is not None

    # Dynamic weights
    if has_mc and has_safety:
        pw, ww, dw, pfw, mcw, sw = 25, 17, 17, 13, 13, 15
    elif has_mc:
        pw, ww, dw, pfw, mcw, sw = 30, 20, 20, 15, 15, 0
    elif has_safety:
        pw, ww, dw, pfw, mcw, sw = 28, 18, 18, 13, 0, 23
    else:
        pw, ww, dw, pfw, mcw, sw = 35, 25, 25, 15, 0, 0

    profit_score = max(min(((total_pnl + 50) / 150) * pw, pw), 0)
    winrate_score = (win_rate / 100) * ww
    drawdown_score = max(dw - (max_dd / 50) * dw, 0)
    pf_score = min((pf / 2.0) * pfw, pfw)
    mc_score = (monte_carlo["score"] / 100) * mcw if has_mc else 0
    safety_score = (safety["safety_score"] / 100) * sw if has_safety else 0

    total_score = round(profit_score + winrate_score + drawdown_score + pf_score + mc_score + safety_score, 1)
    total_score = min(max(total_score, 0), 100)

    if total_score >= 80:
        grade = "A"
    elif total_score >= 65:
        grade = "B"
    elif total_score >= 50:
        grade = "C"
    elif total_score >= 35:
        grade = "D"
    else:
        grade = "F"

    breakdown = {
        "profit": round(profit_score, 1),
        "win_rate": round(winrate_score, 1),
        "drawdown": round(drawdown_score, 1),
        "profit_factor": round(pf_score, 1),
    }
    if has_mc:
        breakdown["monte_carlo"] = round(mc_score, 1)
    if has_safety:
        breakdown["safety"] = round(safety_score, 1)

    return {"score": total_score, "breakdown": breakdown, "grade": grade}


def rank_strategies(strategies: list) -> list:
    """
    Take a list of strategy dicts (each with backtest_results),
    score them, and return sorted by score descending.
    """
    scored = []
    for s in strategies:
        bt = s.get("backtest_results") or {}
        mc = s.get("monte_carlo")
        safety = s.get("safety")
        scoring = calculate_score(bt, mc, safety)
        scored.append({
            **s,
            "ranking": {**scoring, "rank": 0, "is_best": False},
        })

    scored.sort(key=lambda x: x["ranking"]["score"], reverse=True)
    for i, s in enumerate(scored):
        s["ranking"]["rank"] = i + 1
        s["ranking"]["is_best"] = (i == 0)

    return scored

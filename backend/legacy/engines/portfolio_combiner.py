"""
Phase 3 — Portfolio Combiner.

Lightweight wrapper around `engines.portfolio_engine.analyze_portfolio` so
the dashboard pipeline can produce a portfolio block from the top-N
strategies it just ranked. The combiner pulls the equity curve from each
candidate's `_raw_bt`, falls back to synthesising one from net_profit
when needed, and returns a compact, UI-friendly payload.

Public API
----------
    combine_top_strategies(top_with_raw_bt, top_n=5, allocations=None)

Strict contract:
    * Never raises. On any error, returns
      ``{"success": False, "error": "..."}`` so the dashboard can skip
      it without breaking the response.
    * Additive only — does not mutate the inputs.
"""
from __future__ import annotations

import logging
from typing import Optional

from engines.portfolio_engine import analyze_portfolio

logger = logging.getLogger(__name__)

MIN_FOR_PORTFOLIO = 2
DEFAULT_TOP_N = 5


def _equity_from_card(card: dict, initial_balance: float = 10_000.0) -> list:
    """Return an equity-curve list from a dashboard top-strategy card.

    Priority order:
      1. ``card["_raw_bt"]["equity_curve"]`` (real backtest output)
      2. ``card["equity_curve"]`` — compact downsampled curve attached
         by `_shrink_for_dashboard` for the multi-asset combiner path.
      3. Synthesised straight-line curve from
         ``card["backtest"]["net_profit"]``  (only used when no real
         curve is available — keeps shape compatible with the analyser).
    """
    raw = card.get("_raw_bt") or {}
    eq = raw.get("equity_curve") or []
    if isinstance(eq, list) and len(eq) >= 2:
        return list(eq)
    shrunk = card.get("equity_curve") or []
    if isinstance(shrunk, list) and len(shrunk) >= 2:
        return list(shrunk)
    bt = card.get("backtest") or {}
    net = float(bt.get("net_profit", 0) or 0)
    return [initial_balance, initial_balance + net]


def _to_portfolio_input(card: dict) -> dict:
    """Adapt a dashboard top-strategy card to the shape
    `analyze_portfolio` expects."""
    raw = card.get("_raw_bt") or {}
    bt_summary = card.get("backtest") or {}
    return {
        "id": card.get("strategy_id"),
        "pair": card.get("pair"),
        "timeframe": card.get("timeframe"),
        "strategy_type": raw.get("strategy_type") or bt_summary.get("strategy_type"),
        "score": card.get("score", 0),
        "safety": card.get("safety") or {},
        "backtest_results": {
            "net_profit": bt_summary.get("net_profit", 0),
            "total_return_pct": bt_summary.get("total_return_pct", 0),
            "max_drawdown_pct": bt_summary.get("max_drawdown_pct", 0),
            "profit_factor": bt_summary.get("profit_factor", 0),
            "win_rate": bt_summary.get("win_rate", 0),
            "total_trades": bt_summary.get("total_trades", 0),
            "initial_balance": raw.get("initial_balance", 10_000.0),
            "equity_curve": _equity_from_card(card),
            "trades": raw.get("trades") or [],
        },
    }


def combine_top_strategies(
    top_with_raw_bt: list,
    *,
    top_n: int = DEFAULT_TOP_N,
    allocations: Optional[list] = None,
) -> dict:
    """Combine the top dashboard strategies into a single portfolio view.

    Returns
    -------
    dict
        ``{"success": True, "portfolio": {...analyze_portfolio output...},
        "num_combined": int, "strategy_ids": [...]}`` on success.

        ``{"success": False, "reason": str}`` when there are <2
        usable candidates (the dashboard should simply omit the
        portfolio block in that case).
    """
    if not top_with_raw_bt:
        return {"success": False, "reason": "no_candidates"}

    # Cap to top_n, drop entries with neither equity nor non-zero net_profit
    pool = []
    for c in top_with_raw_bt[:max(MIN_FOR_PORTFOLIO, int(top_n))]:
        adapted = _to_portfolio_input(c)
        ec = adapted["backtest_results"].get("equity_curve") or []
        bt = adapted["backtest_results"]
        if (len(ec) >= 2) or bt.get("net_profit") or bt.get("total_trades"):
            pool.append(adapted)

    if len(pool) < MIN_FOR_PORTFOLIO:
        return {"success": False, "reason": "insufficient_candidates", "have": len(pool)}

    try:
        analysis = analyze_portfolio(pool, allocations=allocations)
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("combine_top_strategies analyze_portfolio failed: %s", e)
        return {"success": False, "reason": f"analyse_failed: {e}"}

    return {
        "success": True,
        "num_combined": len(pool),
        "strategy_ids": [p.get("id") for p in pool],
        "portfolio": analysis,
    }

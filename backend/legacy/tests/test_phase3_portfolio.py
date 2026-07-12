"""
Phase-3 — Portfolio Combiner tests.

Verifies the dashboard-side combiner shape and behaviour:
  * combines 2+ strategies with valid equity curves
  * returns a `combined_metrics` block with combined DD / return
  * gracefully refuses single-candidate input
  * never raises on malformed input
"""
from __future__ import annotations

from engines.portfolio_combiner import combine_top_strategies


def _card(strategy_id: str, equity: list, *, pair: str = "EURUSD",
          tf: str = "H1") -> dict:
    """Build a minimal dashboard-shape card with a real equity curve."""
    return {
        "strategy_id": strategy_id,
        "pair": pair,
        "timeframe": tf,
        "score": 70,
        "backtest": {
            "net_profit": equity[-1] - equity[0],
            "total_return_pct": round((equity[-1] / equity[0] - 1) * 100, 2),
            "max_drawdown_pct": 5.0,
            "profit_factor": 1.4,
            "win_rate": 55.0,
            "total_trades": 30,
        },
        "_raw_bt": {
            "equity_curve": list(equity),
            "trades": [],
            "initial_balance": 10_000.0,
        },
    }


def test_combine_returns_success_for_two_uncorrelated_curves():
    eq_a = [10_000 + i * 5 for i in range(50)]
    eq_b = [10_000 + (49 - i) * 4 for i in range(50)]  # opposite direction
    cards = [_card("a", eq_a), _card("b", eq_b)]
    out = combine_top_strategies(cards, top_n=5)
    assert out["success"] is True
    assert out["num_combined"] == 2
    p = out["portfolio"]
    assert "combined_metrics" in p
    assert "diversification_grade" in p
    assert "correlation_matrix" in p
    cm = p["combined_metrics"]
    for f in ("total_profit", "total_return_pct", "max_drawdown_pct"):
        assert f in cm


def test_combine_refuses_single_candidate():
    eq = [10_000 + i * 5 for i in range(50)]
    out = combine_top_strategies([_card("solo", eq)])
    assert out["success"] is False
    assert out.get("reason") == "insufficient_candidates"


def test_combine_refuses_empty_list():
    out = combine_top_strategies([])
    assert out["success"] is False


def test_combine_handles_degenerate_curves_without_raising():
    """Cards with only the synthesised flat fallback curve (no real
    equity / trades / non-zero net_profit) still feed through without
    raising — the analyser handles them as zero-volatility series."""
    bad = {
        "strategy_id": "bad",
        "pair": "EURUSD", "timeframe": "H1", "score": 0,
        "backtest": {"net_profit": 0, "total_trades": 0},
        "_raw_bt": {},
    }
    out = combine_top_strategies([bad, bad])
    # success or False — both are acceptable; the contract is that
    # nothing raises and a stable shape is returned.
    assert out["success"] in (True, False)
    if out["success"]:
        assert "portfolio" in out
    else:
        assert "reason" in out


def test_combine_preserves_strategy_ids():
    eq_a = [10_000 + i * 6 for i in range(40)]
    eq_b = [10_000 + i * 3 for i in range(40)]
    out = combine_top_strategies([_card("alpha", eq_a), _card("beta", eq_b)])
    assert out["success"] is True
    assert set(out["strategy_ids"]) == {"alpha", "beta"}

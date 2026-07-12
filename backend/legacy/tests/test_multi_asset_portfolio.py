"""P4 — Multi-Asset Portfolio rollout tests.

Covers:
  * `run_asset_gate` — pass / fail / insufficient data / error handling
  * `combine_per_pair_cards` — pooling, contribution computation,
     `<2 survivors` early-exit
  * Request model defaults + validation (unique-pair deduplication,
    `need_at_least_two_pairs` 400)
"""
from __future__ import annotations

import math
import pytest

from engines.multi_asset_portfolio import (
    run_asset_gate, combine_per_pair_cards,
    GATE_TEMPLATES, DEFAULT_GATE_THRESHOLD, DEFAULT_GATE_MAX_DD,
)
from api.dashboard import MultiAssetGenerateRequest


# ─────────────────────────────────────────────────────────────────────
# run_asset_gate
# ─────────────────────────────────────────────────────────────────────

def _synthetic_prices(n: int = 1_000, *, drift: float = 0.001) -> list:
    """Generate a mildly-trending sine series so the GA produces non-null metrics."""
    return [
        100.0 + drift * i + 0.5 * math.sin(i / 9.0) + 0.25 * math.sin(i / 23.0)
        for i in range(n)
    ]


def test_gate_rejects_insufficient_data():
    res = run_asset_gate("EURUSD", "H1", prices=[1.0] * 50)
    assert res["passed"] is False
    assert res["reason"] == "insufficient_data"
    assert res["have"] == 50
    assert res["required"] == 200


def test_gate_rejects_empty_prices():
    res = run_asset_gate("EURUSD", "H1", prices=[])
    assert res["passed"] is False
    assert res["reason"] == "insufficient_data"


def test_gate_returns_runs_per_seed():
    prices = _synthetic_prices(1_200)
    res = run_asset_gate(
        "EURUSD", "H1", prices,
        seeds=[7, 42],
        population=6, generations=2,
    )
    assert res["success"] is True
    assert len(res["runs"]) == 2
    seeds = {r["seed"] for r in res["runs"]}
    assert seeds == {7, 42}


def test_gate_verdict_shape():
    prices = _synthetic_prices(1_200)
    res = run_asset_gate(
        "EURUSD", "H1", prices,
        seeds=[7, 42, 101],
        population=6, generations=2,
    )
    assert "passed" in res and isinstance(res["passed"], bool)
    assert "median_oos_pf" in res
    assert "max_oos_dd" in res
    assert res["threshold"] == DEFAULT_GATE_THRESHOLD
    assert res["max_dd_pct"] == DEFAULT_GATE_MAX_DD
    assert res["template"] == GATE_TEMPLATES["trend-following"]


def test_gate_template_per_style():
    prices = _synthetic_prices(800)
    r1 = run_asset_gate("EURUSD", "H1", prices, style="momentum",
                        seeds=[7], population=4, generations=1)
    assert r1["template"] == GATE_TEMPLATES["momentum"]


def test_gate_unknown_style_falls_back_to_default():
    prices = _synthetic_prices(800)
    r = run_asset_gate("EURUSD", "H1", prices, style="something-unknown",
                       seeds=[7], population=4, generations=1)
    assert r["template"] == GATE_TEMPLATES["trend-following"]


# ─────────────────────────────────────────────────────────────────────
# combine_per_pair_cards
# ─────────────────────────────────────────────────────────────────────

def _mock_card(sid: str, pair: str, *, net_profit: float = 100.0,
               pf: float = 1.2, dd: float = 5.0) -> dict:
    """Dashboard-shaped card with enough structure for the combiner."""
    return {
        "strategy_id": sid,
        "pair": pair,
        "timeframe": "H1",
        "score": 70.0,
        "backtest": {
            "net_profit": net_profit,
            "total_return_pct": 1.0,
            "profit_factor": pf,
            "max_drawdown_pct": dd,
            "win_rate": 55.0,
            "total_trades": 40,
        },
        "_raw_bt": {
            "initial_balance": 10_000.0,
            # Short but valid equity curve — combiner's fallback path.
            "equity_curve": [10_000.0, 10_000.0 + net_profit * 0.5,
                             10_000.0 + net_profit],
            "trades": [],
        },
    }


def test_combine_requires_at_least_two_cards():
    result = combine_per_pair_cards([
        {"pair": "EURUSD", "passed": True, "cards": [_mock_card("s1", "EURUSD")]},
    ])
    assert result["success"] is False
    assert result["reason"] == "need_at_least_two_cards_from_passing_assets"


def test_combine_skips_failed_assets():
    result = combine_per_pair_cards([
        {"pair": "EURUSD", "passed": False, "cards": [_mock_card("s1", "EURUSD")]},
        {"pair": "XAUUSD", "passed": False, "cards": [_mock_card("s2", "XAUUSD")]},
    ])
    assert result["success"] is False
    assert result["pooled"] == 0


def test_combine_pools_across_pairs_and_emits_contributions():
    pair_results = [
        {"pair": "EURUSD", "passed": True, "cards": [
            _mock_card("e1", "EURUSD", net_profit=500, pf=1.5, dd=6.0),
            _mock_card("e2", "EURUSD", net_profit=400, pf=1.3, dd=7.0),
        ]},
        {"pair": "GBPUSD", "passed": True, "cards": [
            _mock_card("g1", "GBPUSD", net_profit=350, pf=1.2, dd=8.0),
        ]},
    ]
    res = combine_per_pair_cards(pair_results, top_n_per_pair=2)
    assert res["success"] is True, res
    assert res["num_strategies"] == 3

    contribs = res["asset_contributions_pct"]
    # Both assets must be represented and the pct's must sum to ~100.
    assert set(contribs.keys()) == {"EURUSD", "GBPUSD"}
    assert abs(sum(contribs.values()) - 100.0) < 0.5

    assert res["per_pair_pick"] == {"EURUSD": 2, "GBPUSD": 1}


def test_combine_respects_top_n_per_pair_cap():
    pair_results = [
        {"pair": "EURUSD", "passed": True, "cards": [
            _mock_card(f"e{i}", "EURUSD", net_profit=100 + i) for i in range(5)
        ]},
        {"pair": "GBPUSD", "passed": True, "cards": [
            _mock_card(f"g{i}", "GBPUSD", net_profit=100 + i) for i in range(5)
        ]},
    ]
    res = combine_per_pair_cards(pair_results, top_n_per_pair=2)
    assert res["success"] is True
    # 2 per pair × 2 pairs = 4 pooled
    assert res["num_strategies"] == 4
    assert res["per_pair_pick"] == {"EURUSD": 2, "GBPUSD": 2}


# ─────────────────────────────────────────────────────────────────────
# MultiAssetGenerateRequest
# ─────────────────────────────────────────────────────────────────────

def test_request_defaults():
    req = MultiAssetGenerateRequest(pairs=["EURUSD", "GBPUSD"])
    assert req.timeframe == "H1"
    assert req.style == "trend-following"
    assert req.count == 3
    assert req.top_n_per_pair == 3
    assert req.gate_enabled is True
    assert req.gate_threshold == 1.10
    assert req.gate_max_dd_pct == 30.0
    assert req.gate_seeds == [7, 42, 101, 314, 2718]


def test_request_accepts_custom_gate_seeds():
    req = MultiAssetGenerateRequest(
        pairs=["EURUSD", "GBPUSD"], gate_seeds=[1, 2, 3],
    )
    assert req.gate_seeds == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────
# Endpoint validation (no live backtest — only the 400 guard)
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_endpoint_rejects_single_pair():
    from fastapi import HTTPException
    from api.dashboard import dashboard_generate_portfolio
    req = MultiAssetGenerateRequest(pairs=["EURUSD"])
    with pytest.raises(HTTPException) as excinfo:
        await dashboard_generate_portfolio(req)
    assert excinfo.value.status_code == 400
    assert excinfo.value.detail["error"] == "need_at_least_two_pairs"


@pytest.mark.asyncio
async def test_endpoint_deduplicates_pairs_case_insensitive():
    """Case-insensitive dedup: 'eurusd' + 'EURUSD' + 'GBPUSD' → 2 unique pairs."""
    from fastapi import HTTPException
    from api.dashboard import dashboard_generate_portfolio
    # Only one unique pair after dedup → must 400.
    req = MultiAssetGenerateRequest(pairs=["eurusd", "EURUSD", "  eurusd  "])
    with pytest.raises(HTTPException) as excinfo:
        await dashboard_generate_portfolio(req)
    assert excinfo.value.detail["pairs_requested"] == ["EURUSD"]

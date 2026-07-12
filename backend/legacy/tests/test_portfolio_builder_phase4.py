"""Phase 4 — Portfolio Builder tests.

Coverage:
    • Integration (HTTP) against the live backend — config, empty-build,
      save, recent, _id-leak check, coexistence with Phase-3/Phase-7.
    • Unit tests on the engine (with run_auto_selection monkey-patched)
      to exercise filter / diversification / selection / allocation
      / blend-metrics logic deterministically.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any, Dict, List

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fall back to loading from the frontend .env so tests can run locally.
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except OSError:
        BASE_URL = "http://localhost:8001"

PB = f"{BASE_URL}/api/portfolio-builder"

# Make the backend package importable for the unit tests.
sys.path.insert(0, "/app/backend")


# ────────────────────────────────────────────────────────────────────
# Integration (HTTP) tests
# ────────────────────────────────────────────────────────────────────
class TestPortfolioBuilderAPI:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=10)
        assert r.status_code == 200

    def test_config_defaults(self):
        r = requests.get(f"{PB}/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "defaults" in data
        d = data["defaults"]
        # Spec defaults
        assert d["target_min"] == 3
        assert d["target_max"] == 5
        assert d["min_pass_probability"] == 60.0
        assert d["min_env_confidence"] == 0.7
        assert d["min_match_score"] == 0.8
        assert d["total_risk_cap"] == 3.0
        assert d["max_same_type"] == 2
        assert d["allow_risky"] is False

    def test_build_empty_db_returns_insufficient(self):
        """With no realistic pool in the live DB, build must not crash and
        must surface status != 'ok' (typically insufficient_candidates)."""
        r = requests.post(f"{PB}/build", json={}, timeout=90)
        assert r.status_code == 200, r.text
        data = r.json()
        # Required payload shape
        for k in (
            "status", "strategies", "allocation", "total_risk",
            "expected_pf", "expected_dd", "pass_probability",
            "stability_score", "diversification_score",
            "filters", "built_at",
        ):
            assert k in data, f"missing key {k}"
        if not data["strategies"]:
            assert data["status"] == "insufficient_candidates"
            assert data["total_risk"] == 0 or data["total_risk"] == 0.0
            assert data["allocation"] == {}
            assert data["expected_pf"] in (None, 0, 0.0)
            assert data["expected_dd"] in (None, 0, 0.0)
            assert data["pass_probability"] in (None, 0, 0.0)
            assert data["diversification_score"] in (0, 0.0)

    def test_save_requires_strategies(self):
        r = requests.post(f"{PB}/save", json={}, timeout=30)
        assert r.status_code == 400

    def test_save_and_recent_no_id_leak(self):
        tag = f"TEST_{uuid.uuid4().hex[:8]}"
        payload = {
            "status": "ok",
            "strategies": [{"strategy_hash": tag, "pair": "EURUSD"}],
            "allocation": {tag: {"risk_pct": 3.0, "weight": 1.0}},
            "total_risk": 3.0,
            "_marker": tag,
        }
        r = requests.post(f"{PB}/save", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["status"] == "saved"
        assert "portfolio_id" in saved
        assert "saved_at" in saved
        assert "_id" not in saved  # no Mongo id leak

        # Recent listing — should include what we just saved and not leak _id
        r = requests.get(f"{PB}/recent?limit=10", timeout=30)
        assert r.status_code == 200
        listing = r.json()
        assert "portfolios" in listing
        assert listing["count"] == len(listing["portfolios"])
        for doc in listing["portfolios"]:
            assert "_id" not in doc, "Mongo _id leaked in /recent"
        # Our new doc should be near the top
        hashes = [
            (p.get("meta") or {}).get("_marker") for p in listing["portfolios"]
        ]
        assert tag in hashes, "newly saved portfolio not in /recent"

    def test_phase3_auto_select_endpoint_untouched(self):
        r = requests.get(f"{BASE_URL}/api/auto-select/config", timeout=10)
        assert r.status_code in (200, 404)  # endpoint exists pre-phase-4

    def test_phase7_portfolio_endpoint_untouched(self):
        # existing /api/portfolio/* must still respond
        r = requests.get(f"{BASE_URL}/api/portfolio/list", timeout=10)
        # 200 or 404/405 acceptable — the point is the route layer didn't
        # get clobbered by phase-4.
        assert r.status_code < 500, r.text

    def test_build_validates_request_bounds(self):
        bad = {"pool_size": 99999}
        r = requests.post(f"{PB}/build", json=bad, timeout=30)
        assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────
# Unit tests — drive the engine directly, monkey-patch Auto Selection
# ────────────────────────────────────────────────────────────────────
def _mk(
    h: str, *, pair: str, tf: str, status: str = "PASS",
    pp: float = 75.0, env: float = 0.85, score: float = 0.9,
    safe_risk: float = 1.5, pf: float = 1.5, stab: float = 0.7,
    strat_type: str = "trend_ema", deploy: float = 0.8,
) -> Dict[str, Any]:
    return {
        "strategy_hash": h,
        "strategy_name": h,
        "type": strat_type,
        "pair": pair,
        "timeframe": tf,
        "env_confidence": env,
        "env_flag": "ON",
        "firm_slug": "ftmo",
        "firm_name": "FTMO",
        "challenge": "100k",
        "status": status,
        "pass_probability": pp,
        "expected_days": 12,
        "match_score": score,
        "safe_risk": safe_risk,
        "strategy_best_pf": pf,
        "strategy_stability": stab,
        "deploy_score": deploy,
    }


@pytest.fixture
def seeded_pool() -> List[Dict[str, Any]]:
    # 1 FAIL (must be filtered), 1 RISKY (filtered by default), 1 low pp,
    # 1 low env_conf, 1 low match, plus a handful of good ones with
    # overlapping pair+tf and same-type clones to exercise diversification.
    return [
        _mk("h_good1", pair="EURUSD", tf="H1", deploy=0.95),
        _mk("h_good2", pair="USDJPY", tf="H4", strat_type="rsi_reversion",
            deploy=0.9),
        # Same `type` as h_good1 — 2nd trend_ema clone (allowed up to max=2)
        _mk("h_good3", pair="GBPUSD", tf="M15", strat_type="trend_ema",
            deploy=0.85),
        _mk("h_good4", pair="AUDUSD", tf="H1", strat_type="macd_trend",
            deploy=0.82),
        # dup pair+tf of good1 — should be dropped by diversification
        _mk("h_dup", pair="EURUSD", tf="H1", deploy=0.5),
        # 3rd trend_ema clone — should be capped by max_same_type=2
        _mk("h_trend3", pair="NZDUSD", tf="H1", strat_type="trend_ema",
            deploy=0.4),
        _mk("h_fail", pair="USDCAD", tf="H1", status="FAIL", deploy=0.3),
        _mk("h_risky", pair="XAUUSD", tf="H4", status="RISKY", deploy=0.3),
        _mk("h_lowpp", pair="EURJPY", tf="H1", pp=10.0, deploy=0.3),
        _mk("h_lowenv", pair="GBPJPY", tf="H1", env=0.1, deploy=0.3),
        _mk("h_lowmatch", pair="AUDJPY", tf="H1", score=0.1, deploy=0.3),
    ]


@pytest.fixture
def patch_auto_select(monkeypatch, seeded_pool):
    from engines import portfolio_builder_engine as pbe

    async def _fake_run(**kwargs):
        top_n = kwargs.get("top_n", 20)
        return {"top": seeded_pool[:top_n], "considered": len(seeded_pool),
                "eligible": len(seeded_pool)}

    monkeypatch.setattr(pbe.ase, "run_auto_selection", _fake_run)
    return pbe


class TestEngineLogic:
    def test_filter_drops_fail_and_risky_and_sub_threshold(self, patch_auto_select, seeded_pool):
        pbe = patch_auto_select
        out = pbe._filter_candidates(
            seeded_pool,
            allow_risky=False,
            min_pp=60.0, min_env_conf=0.7, min_match=0.8,
        )
        hashes = {c["strategy_hash"] for c in out}
        assert "h_fail" not in hashes
        assert "h_risky" not in hashes
        assert "h_lowpp" not in hashes
        assert "h_lowenv" not in hashes
        assert "h_lowmatch" not in hashes

    def test_allow_risky_includes_risky(self, patch_auto_select, seeded_pool):
        pbe = patch_auto_select
        out = pbe._filter_candidates(
            seeded_pool, allow_risky=True,
            min_pp=60.0, min_env_conf=0.7, min_match=0.8,
        )
        assert any(c["strategy_hash"] == "h_risky" for c in out)

    def test_diversification_drops_pair_tf_dups_and_caps_type(self, patch_auto_select, seeded_pool):
        pbe = patch_auto_select
        filtered = pbe._filter_candidates(
            seeded_pool, allow_risky=False,
            min_pp=60.0, min_env_conf=0.7, min_match=0.8,
        )
        div = pbe._apply_diversification(filtered, max_same_type=2)
        hashes = {c["strategy_hash"] for c in div}
        # h_dup shares EURUSD+H1 with h_good1 — drop the weaker one.
        assert ("h_good1" in hashes) != ("h_dup" in hashes)
        # Trend_ema clones capped at 2 → at most 2 of type=trend_ema
        trend_ema_hashes = {
            c["strategy_hash"] for c in div if (c["type"] or "").lower() == "trend_ema"
        }
        assert len(trend_ema_hashes) <= 2

    def test_selection_prefers_unique_pairs(self, patch_auto_select, seeded_pool):
        pbe = patch_auto_select
        filtered = pbe._filter_candidates(
            seeded_pool, allow_risky=False,
            min_pp=60.0, min_env_conf=0.7, min_match=0.8,
        )
        div = pbe._apply_diversification(filtered, max_same_type=2)
        sel = pbe._select_portfolio(div, target_min=3, target_max=5)
        pairs = [c["pair"] for c in sel]
        assert len(set(pairs)) == len(pairs)

    def test_risk_allocation_normalizes_to_cap(self, patch_auto_select):
        pbe = patch_auto_select
        strategies = [
            _mk("a", pair="EURUSD", tf="H1", safe_risk=1.0),
            _mk("b", pair="USDJPY", tf="H1", safe_risk=2.0),
            _mk("c", pair="GBPUSD", tf="H1", safe_risk=1.0),
        ]
        alloc = pbe._allocate_risk(strategies, total_cap=3.0)
        total = round(sum(v["risk_pct"] for v in alloc.values()), 3)
        assert 2.99 <= total <= 3.01
        # Weights sum to 1
        w = round(sum(v["weight"] for v in alloc.values()), 3)
        assert 0.99 <= w <= 1.01
        # Strategy "b" has the largest raw → gets the largest slice
        assert alloc["b"]["risk_pct"] > alloc["a"]["risk_pct"]

    def test_blend_metrics_fields(self, patch_auto_select):
        pbe = patch_auto_select
        strategies = [
            _mk("a", pair="EURUSD", tf="H1", pf=1.5, stab=0.8, pp=80),
            _mk("b", pair="USDJPY", tf="H4", pf=1.3, stab=0.6, pp=70,
                strat_type="rsi_reversion"),
            _mk("c", pair="GBPUSD", tf="M15", pf=1.8, stab=0.9, pp=75,
                strat_type="breakout"),
        ]
        alloc = pbe._allocate_risk(strategies, total_cap=3.0)
        m = pbe._blend_metrics(strategies, alloc)
        for k in ("expected_pf", "expected_dd", "pass_probability",
                  "stability_score", "diversification_score"):
            assert k in m
        assert 0.0 <= m["diversification_score"] <= 1.0
        assert 0.0 < m["expected_pf"] < 5.0
        assert 60 <= m["pass_probability"] <= 85

    def test_build_portfolio_end_to_end(self, patch_auto_select):
        pbe = patch_auto_select
        res = asyncio.get_event_loop().run_until_complete(
            pbe.build_portfolio(persist=False)
        )
        assert res["status"] == "ok"
        assert 3 <= res["selected_count"] <= 5
        assert 2.99 <= res["total_risk"] <= 3.01
        # Strategy hashes are unique
        hashes = [s["strategy_hash"] for s in res["strategies"]]
        assert len(set(hashes)) == len(hashes)
        # Pairs unique (pass 1 of _select_portfolio succeeded)
        pairs = [s["pair"] for s in res["strategies"]]
        assert len(set(pairs)) == len(pairs)
        # Allocation keys match strategies
        assert set(res["allocation"].keys()) == set(hashes)

    def test_build_empty_pool_returns_insufficient(self, monkeypatch):
        from engines import portfolio_builder_engine as pbe

        async def _empty(**kw):
            return {"top": [], "considered": 0, "eligible": 0}

        monkeypatch.setattr(pbe.ase, "run_auto_selection", _empty)
        res = asyncio.get_event_loop().run_until_complete(
            pbe.build_portfolio(persist=False)
        )
        assert res["status"] == "insufficient_candidates"
        assert res["strategies"] == []
        assert res["allocation"] == {}
        assert res["total_risk"] == 0 or res["total_risk"] == 0.0
        assert res["diversification_score"] in (0, 0.0)

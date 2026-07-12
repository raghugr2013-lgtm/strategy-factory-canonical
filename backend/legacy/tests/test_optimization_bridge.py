"""
Phase 8.5 — Auto-Approve → Portfolio Rebuild bridge tests.

Two surfaces exercised:
  1. HTTP — GET /api/optimization/portfolio-actions, POST /api/optimization/run
     with auto_rebuild_portfolio true/false, and legacy routes still alive.
  2. In-process engine — direct calls to optimization_portfolio_bridge.
     We hand-craft `results` dicts to deterministically reach every
     branch (approved, dedup, cooldown, all 5 gate failures, empty batch,
     persistence, batch_id determinism).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from typing import Any, Dict, List

import pytest
import requests

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from engines import optimization_portfolio_bridge as bridge  # noqa: E402
from engines.db import get_db  # noqa: E402

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hello-connect-768.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# ── helpers ──────────────────────────────────────────────────────────
def _good_item(sid: str | None = None, **over) -> Dict[str, Any]:
    item = {
        "verdict": "OPTIMIZED",
        "optimized_strategy": {"strategy_id": sid or f"TEST_{uuid.uuid4().hex[:8]}"},
        "original_metrics": {
            "pf": 1.8, "max_drawdown_pct": 6.5,
            "stability": 72, "pass_probability": 78, "env_confidence": 0.82,
        },
        "optimized_metrics": {
            "pf": 1.9, "max_drawdown_pct": 6.0,
            "stability": 88, "pass_probability": 78, "env_confidence": 0.82,
        },
    }
    item.update(over)
    return item


def _results(items: List[Dict[str, Any]], run_id: str | None = None) -> Dict[str, Any]:
    return {
        "run_id": run_id or f"TEST_RUN_{uuid.uuid4().hex[:10]}",
        "source": "auto_factory",
        "candidates": len(items),
        "accepted": sum(1 for i in items if i.get("verdict") == "OPTIMIZED"),
        "rejected": 0,
        "results": items,
        "built_at": "2026-01-01T00:00:00+00:00",
    }


@pytest.fixture(autouse=True)
def _reset_collection():
    """Drop bridge collection before EACH test → no cooldown/dedup leak."""
    async def _drop():
        db = get_db()
        await db[bridge.COLL_ACTIONS].delete_many({})
    asyncio.get_event_loop().run_until_complete(_drop())
    yield
    asyncio.get_event_loop().run_until_complete(_drop())


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ════════════════════════════════════════════════════════════════════
# 1.  HTTP surface
# ════════════════════════════════════════════════════════════════════
class TestHTTPSurface:
    def test_get_portfolio_actions_default(self):
        r = requests.get(f"{API}/optimization/portfolio-actions", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "count" in data and "actions" in data and "bridge_defaults" in data
        defs = data["bridge_defaults"]
        assert defs["cooldown_seconds"] == 600
        assert defs["min_optimized_pf_ratio"] == 0.95
        assert defs["min_stability"] == 0.70
        assert defs["min_pass_probability"] == 0.60
        assert isinstance(data["actions"], list)

    def test_get_portfolio_actions_limit_param(self):
        r = requests.get(f"{API}/optimization/portfolio-actions?limit=3", timeout=30)
        assert r.status_code == 200
        assert len(r.json()["actions"]) <= 3

    def test_post_run_includes_portfolio_action_when_true(self):
        body = {"source": "auto_factory", "pool_size": 2, "runs": 5,
                "auto_rebuild_portfolio": True}
        r = requests.post(f"{API}/optimization/run", json=body, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "portfolio_action" in data, "portfolio_action missing on response"
        pa = data["portfolio_action"]
        for k in ("batch_id", "ts", "triggered", "reason"):
            assert k in pa, f"missing {k}"

    def test_post_run_excludes_portfolio_action_when_false(self):
        body = {"source": "auto_factory", "pool_size": 2, "runs": 5,
                "auto_rebuild_portfolio": False}
        r = requests.post(f"{API}/optimization/run", json=body, timeout=120)
        assert r.status_code == 200, r.text
        assert "portfolio_action" not in r.json()

    def test_legacy_routes_alive(self):
        # /api/optimize-strategy expects strategy body — POST {} should NOT 404.
        for path in ("/optimize-strategy", "/portfolio/build",
                     "/portfolio-intelligence/build"):
            r = requests.post(f"{API}{path}", json={}, timeout=60)
            assert r.status_code != 404, f"{path} → 404 (route lost)"


# ════════════════════════════════════════════════════════════════════
# 2.  Engine — approved path (synthetic batch)
# ════════════════════════════════════════════════════════════════════
class TestApprovedPath:
    def test_synthetic_batch_triggers_rebuild(self):
        res = _run(bridge.handle_post_optimization(_results([_good_item()])))
        assert res["triggered"] is True, f"expected triggered, got {res}"
        assert res["reason"] == "approved"
        assert "rebuild" in res and res["rebuild"] is not None
        # rebuild should have expected_pf field present (may be None if no pool, but key exists)
        assert "expected_pf" in res["rebuild"]


# ════════════════════════════════════════════════════════════════════
# 3.  Dedup
# ════════════════════════════════════════════════════════════════════
class TestDedup:
    def test_same_run_id_returns_deduped(self):
        payload = _results([_good_item()], run_id="TEST_DEDUP_1")
        first = _run(bridge.handle_post_optimization(payload))
        assert first.get("triggered") is True
        second = _run(bridge.handle_post_optimization(payload))
        assert second.get("deduped") is True
        assert second["batch_id"] == first["batch_id"]


# ════════════════════════════════════════════════════════════════════
# 4.  Cooldown
# ════════════════════════════════════════════════════════════════════
class TestCooldown:
    def test_second_batch_within_cooldown_skipped(self):
        first = _run(bridge.handle_post_optimization(_results([_good_item()])))
        assert first["triggered"] is True
        # different run_id ⇒ new batch_id
        second = _run(bridge.handle_post_optimization(_results([_good_item()])))
        assert second["triggered"] is False
        assert second["reason"] == "cooldown"
        assert second["cooldown_remaining_seconds"] > 0


# ════════════════════════════════════════════════════════════════════
# 5.  Each safety gate
# ════════════════════════════════════════════════════════════════════
class TestGates:
    def _expect_failure(self, item, expected_reason):
        res = _run(bridge.handle_post_optimization(_results([item])))
        assert res["triggered"] is False
        assert res["reason"] == "conditions_failed", res
        reasons = [f.get("reason") for f in res.get("failures", [])]
        assert any(expected_reason in str(r) for r in reasons), \
            f"expected '{expected_reason}' in {reasons}"

    def test_gate1_verdict_rejected(self):
        item = _good_item()
        item["verdict"] = "REJECTED"
        self._expect_failure(item, "verdict=REJECTED")

    def test_gate2_pf_degraded(self):
        item = _good_item()
        item["original_metrics"]["pf"] = 2.0
        item["optimized_metrics"]["pf"] = 1.0  # < 2.0*0.95
        self._expect_failure(item, "pf_degraded")

    def test_gate3_dd_worse(self):
        item = _good_item()
        item["original_metrics"]["max_drawdown_pct"] = 5.0
        item["optimized_metrics"]["max_drawdown_pct"] = 7.0
        self._expect_failure(item, "dd_worse")

    def test_gate4_stability_low(self):
        item = _good_item()
        item["optimized_metrics"]["stability"] = 50  # 0.5 on 0..1
        self._expect_failure(item, "stability_low")

    def test_gate5_pass_prob_low(self):
        item = _good_item()
        item["optimized_metrics"]["pass_probability"] = 50  # 0.5 < 0.6
        self._expect_failure(item, "pass_prob_low")

    def test_empty_batch(self):
        res = _run(bridge.handle_post_optimization(_results([])))
        assert res["triggered"] is False
        assert res["reason"] == "conditions_failed"
        reasons = [f.get("reason") for f in res.get("failures", [])]
        assert "no_results" in reasons


# ════════════════════════════════════════════════════════════════════
# 6.  Mongo persistence
# ════════════════════════════════════════════════════════════════════
class TestPersistence:
    def test_decision_persisted_with_required_fields(self):
        res = _run(bridge.handle_post_optimization(_results([_good_item()])))
        assert res["triggered"] is True

        async def _fetch():
            db = get_db()
            return await db[bridge.COLL_ACTIONS].find_one(
                {"batch_id": res["batch_id"]}, {"_id": 0}
            )
        doc = _run(_fetch())
        assert doc is not None
        for k in ("batch_id", "ts", "triggered", "reason",
                  "items_count", "source", "config"):
            assert k in doc, f"persisted doc missing {k}"


# ════════════════════════════════════════════════════════════════════
# 7.  Determinism — same input → same batch_id
# ════════════════════════════════════════════════════════════════════
class TestBatchIdDeterminism:
    def test_run_id_passthrough(self):
        rid = "TEST_FIXED_RUN_ID_42"
        payload = _results([_good_item("S1")], run_id=rid)
        bid = bridge._batch_id_of(payload)
        assert bid == rid

    def test_sha1_fallback_stable(self):
        item = _good_item("S1")
        p1 = {"source": "auto_factory", "built_at": "2026-01-01T00:00:00+00:00",
              "results": [item]}
        p2 = {"source": "auto_factory", "built_at": "2026-01-01T00:00:00+00:00",
              "results": [item]}
        assert bridge._batch_id_of(p1) == bridge._batch_id_of(p2)
        # different source → different id
        p3 = {"source": "portfolio", "built_at": "2026-01-01T00:00:00+00:00",
              "results": [item]}
        assert bridge._batch_id_of(p1) != bridge._batch_id_of(p3)

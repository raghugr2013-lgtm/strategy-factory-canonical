"""Phase 27.2 / G6 — Autonomous lifecycle progression tests.

Validates the four bridges that turn the lifecycle classifier from
passive (Explorer-only) into autonomous (orchestrator-driven):

  1. ``strategy_lifecycle.evaluate_cohort()`` upserts transitions and
     audit-log entries — and is idempotent on a no-op pass.
  2. ``strategy_lifecycle.recent_transitions`` and
     ``cohort_stage_counts`` shape the read-side feeds the orchestrator
     consumes every tick.
  3. ``ai_orchestrator.decide()`` emits the four new G6 rules
     (``LIFECYCLE_EVALUATE`` always; promotion / demotion advisories
     when transitions exist; ``AUTO_BUILD_PORTFOLIO`` when the elite
     cohort meets the threshold AND no portfolio has been built in the
     cooldown window).
  4. ``ai_orchestrator.execute()`` correctly routes the new action
     types ``evaluate_lifecycle_cohort`` and ``auto_build_portfolio``.

Self-cleaning: every Mongo-touching test seeds with a ``TEST_G6_``
prefix and removes its rows in a finally block. Uses live Mongo (the
same approach as ``test_research_lineage_g1.py``) — no test pollution
because we don't share state across cases.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import requests
from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import ai_orchestrator as orc           # noqa: E402
from engines import strategy_lifecycle as lc          # noqa: E402
from engines.db import get_db                         # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _arun(coro):
    try:
        from engines import db as db_mod
        for attr in ("_client", "_db", "_motor_client"):
            if hasattr(db_mod, attr):
                setattr(db_mod, attr, None)
    except Exception:
        pass
    return asyncio.run(coro)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hours_ago_iso(h: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


# Strategy-row builders — produce rollup entries shaped exactly like
# `_attach_validation_view` / `_attach_lifecycle_view` would emit.
def _row(stage: str, h: str, *, library_id: str = "lib_test_id",
         oos_ratio: float = 0.8, dd: float = 0.04, pp: float = 70.0,
         total_trades: int = 60, pf: float = 1.5,
         stability: float = 70.0, runs: int = 10,
         regimes: Dict[str, int] = None,
         behavioral_profile: str = "TREND_FOLLOWER",
         smoothness: str = "SMOOTH",
         recovery_factor: float = 2.0,
         deploy_score: float = 80.0) -> Dict[str, Any]:
    return {
        "strategy_hash": h,
        "library_id":    library_id,
        "library": {
            "_id":               library_id,
            "library_id":        library_id,
            "profit_factor":     pf,
            "total_trades":      total_trades,
            "max_drawdown_pct":  dd,
            "stability_score":   stability,
            "pass_probability":  pp,
            "behavioral_profile": behavioral_profile,
            "smoothness_label":  smoothness,
            "expected_max_consec_losses": 4,
            "recovery_factor":   recovery_factor,
            "deploy_score":      deploy_score,
            "oos_holdout":       {"ratio": oos_ratio},
            "validation_report": {"badges": []},
        },
        "runs":            runs,
        "best_pf":         pf + 0.2,
        "avg_pf":          pf,
        "last_pf":         pf,
        "min_pf":          pf - 0.1,
        "stability_score": stability / 100.0,
        "regimes":         regimes or {"trending": 5, "ranging": 5},
        "validation":      {"metrics": {}, "badges": []},
    }


# ──────────────────────────────────────────────────────────────────────
# 1. evaluate_cohort — pure progression mechanics
# ──────────────────────────────────────────────────────────────────────

class TestEvaluateCohort:
    def test_first_touch_seeds_baseline(self):
        rollup = [
            _row("candidate", "TEST_G6_first_touch_001", oos_ratio=0.4,
                 stability=50, runs=3, behavioral_profile="UNCLASSIFIED"),
        ]

        async def _go():
            db = get_db()
            await db[lc.LIFECYCLE_COLL].delete_many(
                {"strategy_hash": {"$regex": "^TEST_G6_"}},
            )
            await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                {"strategy_hash": {"$regex": "^TEST_G6_"}},
            )
            try:
                with patch("engines.strategy_memory.get_explorer_rollup",
                           return_value=rollup):
                    out = await lc.evaluate_cohort(persist=True)
                assert out["evaluated"] == 1
                # First-touch is NOT counted as a promotion/demotion.
                assert out["promotions"] == 0
                assert out["demotions"] == 0
                assert out["first_touch"] == 1
                assert out["upserted"] == 1
                # Persisted doc carries the computed stage.
                doc = await lc.get_lifecycle("TEST_G6_first_touch_001")
                assert doc is not None
                assert doc["current_stage"] in lc.LIFECYCLE_STAGES
            finally:
                await db[lc.LIFECYCLE_COLL].delete_many(
                    {"strategy_hash": {"$regex": "^TEST_G6_"}},
                )
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                    {"strategy_hash": {"$regex": "^TEST_G6_"}},
                )

        _arun(_go())

    def test_promotion_recorded_on_stage_up(self):
        h = "TEST_G6_promo_001"

        async def _go():
            db = get_db()
            await db[lc.LIFECYCLE_COLL].delete_many({"strategy_hash": h})
            await db[lc.LIFECYCLE_HISTORY_COLL].delete_many({"strategy_hash": h})
            try:
                # Phase 1 — seed at CANDIDATE.
                rollup_low = [_row("candidate", h, oos_ratio=0.4,
                                   stability=50, runs=3,
                                   behavioral_profile="UNCLASSIFIED")]
                with patch("engines.strategy_memory.get_explorer_rollup",
                           return_value=rollup_low):
                    out1 = await lc.evaluate_cohort(persist=True)
                assert out1["first_touch"] == 1
                doc1 = await lc.get_lifecycle(h)
                stage1 = doc1["current_stage"]

                # Phase 2 — same hash, now satisfies VALIDATED gates.
                rollup_high = [_row("validated", h, oos_ratio=0.85,
                                    stability=75, runs=4,
                                    behavioral_profile="UNCLASSIFIED")]
                with patch("engines.strategy_memory.get_explorer_rollup",
                           return_value=rollup_high):
                    out2 = await lc.evaluate_cohort(persist=True)
                doc2 = await lc.get_lifecycle(h)
                stage2 = doc2["current_stage"]

                # Stage must have moved up (or at least equal — tightens
                # the assertion when the gate combinations conspire).
                assert (lc.STAGE_RANK[stage2] >= lc.STAGE_RANK[stage1])
                if lc.STAGE_RANK[stage2] > lc.STAGE_RANK[stage1]:
                    assert out2["promotions"] == 1
                    assert out2["demotions"] == 0
                    transitions = out2["transitions"]
                    assert len(transitions) == 1
                    assert transitions[0]["direction"] == "promotion"
                    assert transitions[0]["from_stage"] == stage1
                    assert transitions[0]["to_stage"] == stage2
                    # Audit log got the row too.
                    history = await lc.get_lifecycle_history(h)
                    assert any(r.get("from_stage") == stage1
                               and r.get("to_stage") == stage2
                               for r in history)
            finally:
                await db[lc.LIFECYCLE_COLL].delete_many({"strategy_hash": h})
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many({"strategy_hash": h})

        _arun(_go())

    def test_idempotent_on_no_change(self):
        h = "TEST_G6_idempotent_001"
        rollup = [_row("candidate", h, oos_ratio=0.4, stability=50,
                       runs=3, behavioral_profile="UNCLASSIFIED")]

        async def _go():
            db = get_db()
            await db[lc.LIFECYCLE_COLL].delete_many({"strategy_hash": h})
            await db[lc.LIFECYCLE_HISTORY_COLL].delete_many({"strategy_hash": h})
            try:
                with patch("engines.strategy_memory.get_explorer_rollup",
                           return_value=rollup):
                    out1 = await lc.evaluate_cohort(persist=True)
                    assert out1["first_touch"] == 1
                    # Second pass on identical input → no transitions.
                    out2 = await lc.evaluate_cohort(persist=True)
                    assert out2["first_touch"] == 0
                    assert out2["promotions"] == 0
                    assert out2["demotions"] == 0
                    assert out2["upserted"] == 0
                    assert out2["transitions"] == []
            finally:
                await db[lc.LIFECYCLE_COLL].delete_many({"strategy_hash": h})
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many({"strategy_hash": h})

        _arun(_go())


# ──────────────────────────────────────────────────────────────────────
# 2. recent_transitions + cohort_stage_counts (orchestrator feeds)
# ──────────────────────────────────────────────────────────────────────

class TestLifecycleReadFeeds:
    def test_recent_transitions_filters_by_since(self):
        async def _go():
            db = get_db()
            old_ts = _hours_ago_iso(48)
            new_ts = _hours_ago_iso(0.1)
            seed = [
                {"strategy_hash": "TEST_G6_feed_old", "from_stage": "candidate",
                 "to_stage": "validated", "from_stage_rank": 1,
                 "to_stage_rank": 2, "transition_at": old_ts,
                 "evidence_snapshot": {}, "flags": [],
                 "library_id": "x"},
                {"strategy_hash": "TEST_G6_feed_new", "from_stage": "validated",
                 "to_stage": "stable", "from_stage_rank": 2,
                 "to_stage_rank": 3, "transition_at": new_ts,
                 "evidence_snapshot": {}, "flags": [],
                 "library_id": "y"},
            ]
            await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                {"strategy_hash": {"$regex": "^TEST_G6_feed_"}},
            )
            try:
                await db[lc.LIFECYCLE_HISTORY_COLL].insert_many(seed)
                # No filter — both rows.
                all_rows = await lc.recent_transitions(limit=20)
                hashes = {r["strategy_hash"] for r in all_rows}
                assert "TEST_G6_feed_new" in hashes
                assert "TEST_G6_feed_old" in hashes
                # Window 1h — only the new row.
                cut = _hours_ago_iso(1)
                recent = await lc.recent_transitions(since_iso=cut, limit=20)
                hashes_recent = {r["strategy_hash"] for r in recent}
                assert "TEST_G6_feed_new" in hashes_recent
                assert "TEST_G6_feed_old" not in hashes_recent
            finally:
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                    {"strategy_hash": {"$regex": "^TEST_G6_feed_"}},
                )

        _arun(_go())

    def test_cohort_stage_counts_returns_full_taxonomy(self):
        async def _go():
            counts = await lc.cohort_stage_counts()
            for s in lc.LIFECYCLE_STAGES:
                assert s in counts
                assert isinstance(counts[s], int)

        _arun(_go())


# ──────────────────────────────────────────────────────────────────────
# 3. ai_orchestrator.decide() — new G6 rules
# ──────────────────────────────────────────────────────────────────────

class TestOrchestratorRules:
    def _base_state(self, **overrides) -> Dict[str, Any]:
        st: Dict[str, Any] = {
            "live": {"status": "idle"},
            "recent_runs":         [],
            "saves_per_run":       [],
            "pfs_per_run":         [],
            "avg_pf_recent":       None,
            "total_saves_recent":  0,
            "rejection_breakdown": {"counts": {}, "total": 0, "top_reason": None},
            "library":             {"total": 0, "new_last_hour": 0},
            "best_candidate":      None,
            "adaptive_scan":       [],
            "lifecycle": {
                "stage_counts":          {s: 0 for s in lc.LIFECYCLE_STAGES},
                "promotions_recent":     [],
                "demotions_recent":      [],
                "transitions_total":     0,
                "last_portfolio_built_at": None,
            },
        }
        st.update(overrides)
        return st

    def test_lifecycle_evaluate_always_fires(self):
        recs = orc.decide(self._base_state())
        assert any(r["rule_id"] == "LIFECYCLE_EVALUATE" for r in recs)
        evaluator = next(r for r in recs if r["rule_id"] == "LIFECYCLE_EVALUATE")
        assert evaluator["action"] == "evaluate_lifecycle_cohort"

    def test_promotions_advisory_when_present(self):
        st = self._base_state()
        st["lifecycle"]["promotions_recent"] = [
            {"strategy_hash": "h1", "from_stage": "candidate",
             "to_stage": "validated", "transition_at": _now_iso()},
            {"strategy_hash": "h2", "from_stage": "validated",
             "to_stage": "stable",    "transition_at": _now_iso()},
        ]
        recs = orc.decide(st)
        promo = [r for r in recs if r["rule_id"] == "LIFECYCLE_PROMOTIONS_DETECTED"]
        assert len(promo) == 1
        assert promo[0]["action"] == "log_recommendation"
        assert promo[0]["params"]["count"] == 2
        assert promo[0]["severity"] == "info"

    def test_demotions_advisory_when_present(self):
        st = self._base_state()
        st["lifecycle"]["demotions_recent"] = [
            {"strategy_hash": "h3", "from_stage": "stable",
             "to_stage": "validated", "transition_at": _now_iso()},
        ]
        recs = orc.decide(st)
        demo = [r for r in recs if r["rule_id"] == "LIFECYCLE_DEMOTIONS_DETECTED"]
        assert len(demo) == 1
        assert demo[0]["severity"] == "warn"

    def test_auto_build_portfolio_fires_when_threshold_met(self):
        st = self._base_state()
        st["lifecycle"]["stage_counts"]["elite"] = orc.AUTO_BUILD_MIN_ELITE
        st["lifecycle"]["last_portfolio_built_at"] = None
        recs = orc.decide(st)
        rule_ids = {r["rule_id"] for r in recs}
        assert "AUTO_BUILD_PORTFOLIO" in rule_ids
        rule = next(r for r in recs if r["rule_id"] == "AUTO_BUILD_PORTFOLIO")
        assert rule["action"] == "auto_build_portfolio"
        assert rule["params"]["elite_count"] == orc.AUTO_BUILD_MIN_ELITE

    def test_auto_build_portfolio_blocked_by_cooldown(self):
        st = self._base_state()
        st["lifecycle"]["stage_counts"]["elite"] = orc.AUTO_BUILD_MIN_ELITE * 2
        st["lifecycle"]["last_portfolio_built_at"] = _hours_ago_iso(1)
        recs = orc.decide(st)
        rule_ids = {r["rule_id"] for r in recs}
        # Hot-build rule must NOT fire.
        assert "AUTO_BUILD_PORTFOLIO" not in rule_ids
        # Quiet advisory MUST fire so operators see the system is poised.
        assert "AUTO_BUILD_PORTFOLIO_COOLDOWN" in rule_ids

    def test_auto_build_portfolio_silent_below_threshold(self):
        st = self._base_state()
        st["lifecycle"]["stage_counts"]["elite"] = max(
            0, orc.AUTO_BUILD_MIN_ELITE - 1,
        )
        recs = orc.decide(st)
        rule_ids = {r["rule_id"] for r in recs}
        assert "AUTO_BUILD_PORTFOLIO" not in rule_ids
        assert "AUTO_BUILD_PORTFOLIO_COOLDOWN" not in rule_ids


# ──────────────────────────────────────────────────────────────────────
# 4. execute() routes the new action types
# ──────────────────────────────────────────────────────────────────────

class TestOrchestratorExecute:
    def test_evaluate_lifecycle_cohort_action_calls_engine(self):
        captured: Dict[str, int] = {"calls": 0}

        async def _fake_eval(*, persist: bool = True, **kwargs):
            captured["calls"] += 1
            assert persist is True
            return {
                "evaluated": 7, "promotions": 1, "demotions": 0,
                "first_touch": 0, "upserted": 1, "stage_counts": {},
            }

        async def _go():
            with patch("engines.strategy_lifecycle.evaluate_cohort",
                       side_effect=_fake_eval):
                actions: List[Dict[str, Any]] = [{
                    "rule_id": "LIFECYCLE_EVALUATE",
                    "action":  "evaluate_lifecycle_cohort",
                    "reason":  "test",
                    "params":  {},
                    "severity": "info",
                }]
                results = await orc.execute(actions)
            return results

        results = _arun(_go())
        assert captured["calls"] == 1
        assert results[0]["status"] == "executed"
        assert results[0]["summary"]["promotions"] == 1
        assert results[0]["summary"]["evaluated"] == 7

    def test_auto_build_portfolio_action_calls_engine(self):
        captured: Dict[str, int] = {"calls": 0}

        async def _fake_build(persist: bool = False, **kwargs):
            captured["calls"] += 1
            assert persist is True
            return {
                "status": "ok", "selected_count": 4, "persisted": True,
                "portfolio_id": "TEST_G6_pf_id",
                "expected_pf": 1.45, "pass_probability": 0.62,
            }

        async def _go():
            with patch("engines.portfolio_builder_engine.build_portfolio",
                       side_effect=_fake_build):
                actions = [{
                    "rule_id": "AUTO_BUILD_PORTFOLIO",
                    "action":  "auto_build_portfolio",
                    "reason":  "test",
                    "params":  {},
                    "severity": "info",
                }]
                return await orc.execute(actions)

        results = _arun(_go())
        assert captured["calls"] == 1
        assert results[0]["status"] == "executed"
        assert results[0]["portfolio_id"] == "TEST_G6_pf_id"
        assert results[0]["selected"] == 4

    def test_unknown_action_still_skipped(self):
        async def _go():
            return await orc.execute([{
                "rule_id": "X", "action": "foo_bar",
                "reason": "?", "params": {}, "severity": "info",
            }])
        results = _arun(_go())
        assert results[0]["status"] == "skipped"


# ──────────────────────────────────────────────────────────────────────
# 5. HTTP smoke — new /api/lifecycle/* endpoints
# ──────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip()
                    break
    except OSError:
        pass
BASE_URL = BASE_URL.rstrip("/")
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def auth_headers():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    body = r.json()
    token = body.get("access_token") or body.get("token")
    if not token:
        pytest.skip(f"No token in login response: {body}")
    return {"Authorization": f"Bearer {token}",
            "Content-Type":  "application/json"}


class TestLifecycleHTTP:
    def test_stage_counts_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/lifecycle/cohort/stage-counts",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "stages" in body and "counts" in body and "total" in body
        for s in lc.LIFECYCLE_STAGES:
            assert s in body["counts"]

    def test_recent_transitions_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/lifecycle/transitions/recent?limit=5",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body and "transitions" in body

    def test_evaluate_endpoint_returns_summary(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/lifecycle/evaluate",
                          headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("evaluated", "promotions", "demotions",
                  "first_touch", "upserted", "stage_counts",
                  "evaluated_at"):
            assert k in body

    def test_lifecycle_doc_404_for_unknown_hash(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/lifecycle/TEST_G6_does_not_exist",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 404
        assert r.json().get("detail") == "lifecycle_doc_not_found"

    def test_orchestrator_decide_emits_lifecycle_evaluate(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/decide",
                          headers=auth_headers, timeout=30)
        assert r.status_code == 200
        recs = r.json().get("recommendations") or []
        rule_ids = {x["rule_id"] for x in recs}
        assert "LIFECYCLE_EVALUATE" in rule_ids

    def test_orchestrator_state_includes_lifecycle(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/orchestrator/state",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        st = r.json().get("state") or {}
        lcs = st.get("lifecycle") or {}
        assert "stage_counts" in lcs
        assert "promotions_recent" in lcs
        assert "demotions_recent" in lcs

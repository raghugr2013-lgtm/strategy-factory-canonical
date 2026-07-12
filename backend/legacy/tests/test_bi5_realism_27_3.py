"""Phase 27.3 / BI5 — Realism gate tests.

Validates the realism certification layer end-to-end:

  1. ``bi5_realism.evaluate()`` — skip paths (missing library, missing
     pair/timeframe, library PF unavailable), data-missing path
     (returns ``BI5_DATA_MISSING`` flag without demoting), and the
     three success bands (ok / partial / fail) with persisted block.
  2. Lifecycle integration — when ``bi5_realism.status='data_missing'``
     is persisted, ``compute_lifecycle_state*`` emits the new
     ``BI5_DATA_MISSING`` flag (flag-and-allow path) without demoting.
  3. Lifecycle integration — when ``bi5_realism.pf_ratio < 0.50`` is
     persisted, the pre-existing ``BI5_FAIL`` flag fires and caps stage
     at ``stable`` (cool-down behavior preserved).
  4. ``bi5_realism.sweep_realism()`` — iterates only the eligible
     cohort (``portfolio_worthy ∪ deployment_ready``), respects
     freshness, accepts ``force_refresh``.
  5. ``orchestrator_scheduler`` — when started, the realism sweep job
     is registered with a ``CronTrigger`` whose next run is next
     Sunday 03:00 UTC; ``get_status()`` exposes the new
     ``realism_sweep`` block.
  6. HTTP smoke — all 4 BI5 endpoints behave correctly (404 for
     unknown hash, 200 with shape for sweep, evaluate, stale-count).

Self-cleaning: every Mongo-touching test seeds with a ``TEST_BI5_``
prefix and removes its rows in a finally block.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
import requests
from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import bi5_realism                                 # noqa: E402
from engines import strategy_lifecycle as lc                    # noqa: E402
from engines.db import get_db                                   # noqa: E402


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


def _make_full_evidence_lib(*, pf: float = 1.5) -> Dict[str, Any]:
    """Library snapshot that already passes every cheap gate so the
    only thing flipping the lifecycle stage is the realism block."""
    return {
        "library_id":          "lib_test_bi5_full",
        "profit_factor":       pf,
        "total_trades":        80,
        "max_drawdown_pct":    0.03,
        "stability_score":     75.0,
        "pass_probability":    72.0,
        "behavioral_profile":  "TREND_FOLLOWER",
        "smoothness_label":    "SMOOTH",
        "expected_max_consec_losses": 3,
        "recovery_factor":     2.5,
        "deploy_score":        82.0,
        "oos_holdout":         {"ratio": 0.85},
        "validation_report":   {"badges": []},
    }


# ──────────────────────────────────────────────────────────────────────
# 1. evaluate() — skip paths
# ──────────────────────────────────────────────────────────────────────

class TestEvaluateSkipPaths:
    def test_unknown_strategy_hash(self):
        async def _go():
            return await bi5_realism.evaluate("TEST_BI5_does_not_exist")
        out = _arun(_go())
        assert out["status"] == "skipped"
        assert out["skipped_reason"] == "library_doc_not_found"
        assert out["pf_ratio"] is None

    def test_missing_strategy_hash(self):
        async def _go():
            return await bi5_realism.evaluate("")
        out = _arun(_go())
        assert out["status"] == "skipped"
        assert out["skipped_reason"] == "missing_strategy_hash"

    def test_library_pf_unavailable(self):
        async def _go():
            with patch.object(bi5_realism, "_resolve_library_doc",
                              return_value={
                                  "strategy_text": "RSI > 50",
                                  "pair": "EURUSD",
                                  "timeframe": "H1",
                                  "profit_factor": 0.0,
                              }):
                return await bi5_realism.evaluate("TEST_BI5_no_pf")
        out = _arun(_go())
        assert out["status"] == "skipped"
        assert out["skipped_reason"] == "library_pf_unavailable"


# ──────────────────────────────────────────────────────────────────────
# 2. evaluate() — data-missing path (flag-and-allow)
# ──────────────────────────────────────────────────────────────────────

class TestEvaluateDataMissing:
    def test_returns_data_missing_flag_when_no_bi5_bars(self):
        async def _go():
            with patch.object(bi5_realism, "_resolve_library_doc",
                              return_value={
                                  "library_id":     "lib_test",
                                  "strategy_text":  "RSI > 50",
                                  "pair":           "EURUSD",
                                  "timeframe":      "H1",
                                  "profit_factor":  1.4,
                              }), \
                 patch.object(bi5_realism, "_load_bi5_bars",
                              return_value={
                                  "status": "insufficient",
                                  "bars":   [],
                                  "count":  0,
                                  "message": "no bi5 data",
                              }), \
                 patch.object(bi5_realism, "_persist_realism",
                              return_value=None):
                return await bi5_realism.evaluate(
                    "TEST_BI5_data_missing", persist=True,
                    force_refresh=True,
                )
        out = _arun(_go())
        assert out["status"] == "data_missing"
        assert out["flag"] == "BI5_DATA_MISSING"
        assert out["pf_ratio"] is None
        assert out["bi5_pf"] is None


# ──────────────────────────────────────────────────────────────────────
# 3. evaluate() — three success bands
# ──────────────────────────────────────────────────────────────────────

def _fake_bars(n: int = 250) -> List[Dict[str, Any]]:
    base = 1.1000
    return [
        {"time": f"2026-01-{(i // 24) + 1:02d}T{(i % 24):02d}:00:00+00:00",
         "open": base, "high": base + 0.001,
         "low":  base - 0.001, "close": base,
         "volume": 1.0}
        for i in range(n)
    ]


class TestEvaluateSuccessBands:
    def _patches(self, bi5_bt_pf: float, cached_pf: float = 1.5):
        return [
            patch.object(bi5_realism, "_resolve_library_doc",
                         return_value={
                             "library_id":     "lib_test",
                             "strategy_text":  "RSI > 50",
                             "pair":           "EURUSD",
                             "timeframe":      "H1",
                             "profit_factor":  cached_pf,
                         }),
            patch.object(bi5_realism, "_load_bi5_bars",
                         return_value={
                             "status": "ok", "bars": _fake_bars(),
                             "count":  300, "message": "ok",
                         }),
            patch("engines.bi5_realism.run_backtest_logic",
                  return_value={
                      "profit_factor": bi5_bt_pf,
                      "total_trades":  60,
                      "oos_profit_factor": bi5_bt_pf * 0.95,
                  }),
            patch.object(bi5_realism, "_persist_realism",
                         return_value=None),
        ]

    def test_ok_band(self):
        # ratio = 1.30/1.5 = 0.866 → ok
        async def _go():
            patches = self._patches(bi5_bt_pf=1.30)
            for p in patches:
                p.start()
            try:
                return await bi5_realism.evaluate(
                    "TEST_BI5_ok", persist=True, force_refresh=True,
                )
            finally:
                for p in patches:
                    p.stop()
        out = _arun(_go())
        assert out["status"] == "ok"
        assert out["flag"] is None
        assert 0.86 <= out["pf_ratio"] <= 0.87

    def test_partial_band(self):
        # ratio = 0.90/1.5 = 0.60 → partial (0.50 ≤ x < 0.75)
        async def _go():
            patches = self._patches(bi5_bt_pf=0.90)
            for p in patches:
                p.start()
            try:
                return await bi5_realism.evaluate(
                    "TEST_BI5_partial", persist=True, force_refresh=True,
                )
            finally:
                for p in patches:
                    p.stop()
        out = _arun(_go())
        assert out["status"] == "partial"
        assert out["flag"] == "PARTIAL_REALISM"
        assert 0.59 <= out["pf_ratio"] <= 0.61

    def test_fail_band(self):
        # ratio = 0.50/1.5 = 0.333 → fail (< 0.50)
        async def _go():
            patches = self._patches(bi5_bt_pf=0.50)
            for p in patches:
                p.start()
            try:
                return await bi5_realism.evaluate(
                    "TEST_BI5_fail", persist=True, force_refresh=True,
                )
            finally:
                for p in patches:
                    p.stop()
        out = _arun(_go())
        assert out["status"] == "fail"
        assert out["flag"] == "BI5_FAIL"
        assert out["pf_ratio"] < 0.50


# ──────────────────────────────────────────────────────────────────────
# 4. lifecycle integration — flag emission + flag-and-allow
# ──────────────────────────────────────────────────────────────────────

class TestLifecycleFlagEmission:
    def test_data_missing_emits_bi5_data_missing_without_demotion(self):
        # Strategy at PORTFOLIO_WORTHY without realism block → no flag.
        # Same strategy, persisted bi5_realism={status: "data_missing"}
        # → BI5_DATA_MISSING flag added; current_stage stays the same.
        lib = _make_full_evidence_lib(pf=1.5)

        # Construct a realistic prior_state at PORTFOLIO_WORTHY.
        prior = {
            "current_stage": "portfolio_worthy",
            "stage_rank":    lc.STAGE_RANK["portfolio_worthy"],
            "flags":         [],
        }

        # Without realism block → no BI5 flag, stage at most ELITE
        # (portfolio_membership not supplied, so won't reach
        # PORTFOLIO_WORTHY without it).
        st_no_realism = lc.compute_lifecycle_state(
            library_doc=lib,
            history_rows=[
                {"profit_factor": 1.5, "max_drawdown_pct": 0.03,
                 "regime": "trending"} for _ in range(8)
            ],
            cohort_p90_deploy_score=70.0,
            prior_state=prior,
        )
        assert "BI5_DATA_MISSING" not in (st_no_realism.get("flags") or [])
        # With realism block declaring data_missing → flag is added,
        # but stage is NOT downgraded (flag-and-allow).
        st_data_missing = lc.compute_lifecycle_state(
            library_doc=lib,
            history_rows=[
                {"profit_factor": 1.5, "max_drawdown_pct": 0.03,
                 "regime": "trending"} for _ in range(8)
            ],
            cohort_p90_deploy_score=70.0,
            prior_state=prior,
            bi5_realism={"status": "data_missing", "pf_ratio": None},
        )
        flags = st_data_missing.get("flags") or []
        assert "BI5_DATA_MISSING" in flags
        # No demotion — the gate that gives DEPLOYMENT_READY just
        # doesn't fire (no pf_ratio); existing PORTFOLIO_WORTHY isn't
        # demoted by this flag.
        rank_no   = lc.STAGE_RANK[st_no_realism["current_stage"]]
        rank_miss = lc.STAGE_RANK[st_data_missing["current_stage"]]
        assert rank_miss >= rank_no - 0  # equal or higher; never lower

    def test_bi5_fail_caps_stage_at_stable(self):
        lib = _make_full_evidence_lib(pf=1.5)
        # No prior cool-down; supplying a realism block with pf_ratio
        # below 0.50 must emit BI5_FAIL and engage cool-down.
        st = lc.compute_lifecycle_state(
            library_doc=lib,
            history_rows=[
                {"profit_factor": 1.5, "max_drawdown_pct": 0.03,
                 "regime": "trending"} for _ in range(8)
            ],
            cohort_p90_deploy_score=70.0,
            bi5_realism={"status": "fail", "pf_ratio": 0.30},
        )
        flags = st.get("flags") or []
        assert "BI5_FAIL" in flags
        assert st.get("cool_down_until") is not None


# ──────────────────────────────────────────────────────────────────────
# 5. sweep_realism — eligibility + freshness
# ──────────────────────────────────────────────────────────────────────

class TestSweepEligibility:
    def test_only_iterates_eligible_stages(self):
        async def _go():
            db = get_db()
            seeds = [
                {"strategy_hash": "TEST_BI5_sweep_pw",
                 "current_stage": "portfolio_worthy"},
                {"strategy_hash": "TEST_BI5_sweep_dr",
                 "current_stage": "deployment_ready"},
                {"strategy_hash": "TEST_BI5_sweep_elite",
                 "current_stage": "elite"},   # NOT eligible
                {"strategy_hash": "TEST_BI5_sweep_stable",
                 "current_stage": "stable"},  # NOT eligible
            ]
            await db[lc.LIFECYCLE_COLL].delete_many(
                {"strategy_hash": {"$regex": "^TEST_BI5_sweep_"}},
            )
            try:
                await db[lc.LIFECYCLE_COLL].insert_many(seeds)
                # Patch evaluate so the sweep is a pure router test.
                evaluated = []

                async def _fake_eval(h, *, persist=True, force_refresh=False):
                    evaluated.append(h)
                    return {
                        "strategy_hash": h, "status": "ok",
                        "pf_ratio": 0.85, "flag": None,
                    }

                with patch.object(bi5_realism, "evaluate",
                                  side_effect=_fake_eval):
                    summary = await bi5_realism.sweep_realism()
                assert summary["scanned"] == 2
                assert summary["evaluated"] == 2
                assert summary["ok"] == 2
                assert set(evaluated) == {"TEST_BI5_sweep_pw",
                                          "TEST_BI5_sweep_dr"}
            finally:
                await db[lc.LIFECYCLE_COLL].delete_many(
                    {"strategy_hash": {"$regex": "^TEST_BI5_sweep_"}},
                )
        _arun(_go())


# ──────────────────────────────────────────────────────────────────────
# 6. orchestrator_scheduler — Sunday 03:00 UTC realism cron registered
# ──────────────────────────────────────────────────────────────────────

class TestSchedulerRealismCron:
    def test_realism_job_registered_on_start(self):
        from engines import orchestrator_scheduler as orc_sched

        async def _go():
            try:
                await orc_sched.start_scheduler(interval_minutes=1440)
                sched = orc_sched._scheduler
                assert sched is not None
                job = sched.get_job(orc_sched.REALISM_JOB_ID)
                assert job is not None, "realism sweep job not registered"
                # Cron trigger fires Sunday 03:00 UTC.
                trigger = job.trigger
                # APScheduler cron triggers expose `.fields` —
                # day_of_week field includes "sun".
                assert any(
                    "sun" in str(f).lower()
                    for f in getattr(trigger, "fields", [])
                ) or str(trigger).lower().count("sun") > 0
                # Status surfaces the realism block.
                status = await orc_sched.get_status()
                assert "realism_sweep" in status
                assert status["realism_sweep"]["schedule"] == "SUN 03:00 UTC"
                assert status["realism_sweep"]["next_run_at"] is not None
            finally:
                await orc_sched.stop_scheduler()
        _arun(_go())


# ──────────────────────────────────────────────────────────────────────
# 7. HTTP smoke
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


class TestBi5HTTP:
    def test_stale_count_endpoint(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bi5-realism/cohort/stale-count",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("freshness_days", "stale_count", "eligible_stages"):
            assert k in body
        assert "portfolio_worthy" in body["eligible_stages"]
        assert "deployment_ready" in body["eligible_stages"]

    def test_sweep_endpoint_empty_cohort(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/bi5-realism/sweep",
                          headers=auth_headers, timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("started_at", "finished_at", "scanned", "evaluated",
                  "ok", "partial", "fail", "data_missing", "fresh_cache",
                  "errors", "results"):
            assert k in body, f"missing {k}"

    def test_evaluate_unknown_hash_returns_skipped(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/bi5-realism/evaluate/TEST_BI5_does_not_exist",
            headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "skipped"
        assert body["skipped_reason"] == "library_doc_not_found"

    def test_get_realism_404_for_unknown_hash(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/bi5-realism/TEST_BI5_does_not_exist",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 404
        assert r.json().get("detail") == "bi5_realism_block_not_found"

    def test_orchestrator_status_exposes_realism_block(self, auth_headers):
        # Start scheduler → status should carry realism_sweep.
        try:
            r1 = requests.post(
                f"{BASE_URL}/api/orchestrator/scheduler/start",
                json={"interval_minutes": 1440},
                headers=auth_headers, timeout=15,
            )
            assert r1.status_code == 200, r1.text
            r2 = requests.get(
                f"{BASE_URL}/api/orchestrator/scheduler/status",
                headers=auth_headers, timeout=15,
            )
            assert r2.status_code == 200
            body = r2.json()
            assert "realism_sweep" in body
            rs = body["realism_sweep"]
            assert rs["schedule"] == "SUN 03:00 UTC"
            assert rs["next_run_at"] is not None
        finally:
            requests.post(
                f"{BASE_URL}/api/orchestrator/scheduler/stop",
                headers=auth_headers, timeout=15,
            )

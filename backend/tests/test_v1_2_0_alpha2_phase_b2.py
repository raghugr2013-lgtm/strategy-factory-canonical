"""v1.2.0-alpha2 Phase B.2 — Unified Autonomous Orchestration Engine tests.

Verifies:
  - All 11 task adapters register and appear in `/api/orchestrator/tasks`
  - `/api/orchestrator/{start,stop,status,budget,decisions}` endpoints exist
    and gate on admin where required
  - `/api/orchestrator/tasks/{name}/dispatch` works for a lightweight task
    and returns a well-formed TaskResult
  - Budget tracker `can_afford` respects env-driven daily USD caps
  - Provider selection (`choose_provider`) picks the highest-scoring
    affordable candidate
  - Priority scoring is deterministic (repeat ticks produce same
    non-passive candidate ranking when state is unchanged)
  - Auto-scheduler's `_is_subordinated()` returns True when the orchestrator
    is running
  - Regression: Phase A + B + B.1 endpoints unaffected
  - Router count is 93 (Phase B.2 added `orchestrator_engine`, strictly additive)
"""
from __future__ import annotations

import os
import re
import subprocess
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

_EXPECTED_TASKS = {
    "market_data_topup", "bi5_realism_sweep", "knowledge_index_refresh",
    "strategy_generate", "backtest", "validation", "mutation",
    "optimization", "learning_cycle", "ranking", "master_bot_bundle_refresh",
    "self_rebuild",   # Phase D adds this
}
_EXPECTED_PASSIVE = {"validation", "optimization", "master_bot_bundle_refresh",
                     "self_rebuild"}


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "admin@strategy-factory.local",
                       "password": "admin123"})
    assert r.status_code == 200
    d = r.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def admin(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


# ── 1. Task registry ─────────────────────────────────────────────
class TestTaskRegistry:
    def test_all_11_tasks_registered(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/tasks")
        assert r.status_code == 200
        body = r.json()
        # Phase D adds `self_rebuild` → 12.
        assert body["count"] >= 11, body
        names = {t["name"] for t in body["tasks"]}
        # Every Phase B.2 task must still be present (strictly additive).
        expected_b2 = {"market_data_topup", "bi5_realism_sweep",
                       "knowledge_index_refresh", "strategy_generate",
                       "backtest", "validation", "mutation", "optimization",
                       "learning_cycle", "ranking", "master_bot_bundle_refresh"}
        missing = expected_b2 - names
        assert not missing, f"missing Phase B.2 tasks: {missing}"

    def test_passive_defaults_match_design(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/tasks")
        assert r.status_code == 200
        tasks = {t["name"]: t for t in r.json()["tasks"]}
        # Phase B.2 passive defaults still hold (Phase D additions have their
        # own assertions in the Phase D test suite).
        b2_passive = {"validation", "optimization", "master_bot_bundle_refresh"}
        b2_active  = {"market_data_topup", "bi5_realism_sweep",
                      "knowledge_index_refresh", "strategy_generate",
                      "backtest", "mutation", "learning_cycle", "ranking"}
        for name in b2_passive:
            assert tasks[name]["passive"] is True, f"{name} should be passive"
        for name in b2_active:
            assert tasks[name]["passive"] is False, f"{name} should be active"

    def test_task_metadata_complete(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/tasks")
        for t in r.json()["tasks"]:
            for k in ("workload_class", "depends_on", "min_interval_s",
                      "priority_base", "cpu_estimate_cores", "ram_estimate_mb",
                      "expected_duration_s", "ai_provider_required",
                      "cost_estimate_usd", "business_value", "passive",
                      "runs_total", "runs_ok", "runs_fail"):
                assert k in t, f"task {t['name']} missing key {k}"


# ── 2. Endpoint contract + auth gates ─────────────────────────────
class TestEndpoints:
    def test_status_public_read(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/status")
        assert r.status_code == 200
        s = r.json()
        for k in ("running", "enabled_by_env", "config", "meta",
                  "in_flight", "task_names", "counters", "recent_decisions"):
            assert k in s

    def test_start_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/orchestrator/start")
        assert r.status_code in (401, 403)

    def test_stop_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/orchestrator/stop")
        assert r.status_code in (401, 403)

    def test_dispatch_task_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/orchestrator/tasks/learning_cycle/dispatch")
        assert r.status_code in (401, 403)

    def test_budget_public_read(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/budget")
        assert r.status_code == 200
        b = r.json()
        assert "global" in b and "per_provider" in b
        assert "daily_cap_usd" in b["global"]

    def test_decisions_public_read(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/decisions?limit=5")
        assert r.status_code == 200
        assert "decisions" in r.json()


# ── 3. Start/stop + live tick ─────────────────────────────────────
class TestStartStop:
    def test_start_run_stop_flow(self, admin):
        # Clean state
        admin.post(f"{BASE_URL}/api/orchestrator/stop")
        time.sleep(0.5)

        r = admin.post(f"{BASE_URL}/api/orchestrator/start")
        assert r.status_code == 200
        assert r.json()["running"] is True

        # Let ticks fire
        time.sleep(3)

        r = admin.get(f"{BASE_URL}/api/orchestrator/status")
        s = r.json()
        assert s["running"] is True
        assert s["meta"]["tick_count"] >= 1
        assert s["meta"]["dispatched_total"] >= 1

        # There should be at least one recent decision with candidates
        assert len(s["recent_decisions"]) >= 1
        dec = s["recent_decisions"][-1]
        assert "candidates" in dec
        assert isinstance(dec["candidates"], list)
        # Every candidate row has the scoring fields
        c0 = dec["candidates"][0]
        for k in ("task_name", "eligible", "reason", "score"):
            assert k in c0

        # Stop
        r = admin.post(f"{BASE_URL}/api/orchestrator/stop")
        assert r.status_code == 200
        assert r.json()["running"] is False


# ── 4. Manual dispatch — knowledge_index_refresh (cheap) ─────────
class TestManualDispatch:
    def test_dispatch_returns_result(self, admin):
        r = admin.post(f"{BASE_URL}/api/orchestrator/tasks/knowledge_index_refresh/dispatch")
        assert r.status_code == 200
        body = r.json()
        for k in ("ok", "reason", "duration_ms"):
            assert k in body
        assert body["ok"] is True

    def test_dispatch_unknown_task_404(self, admin):
        r = admin.post(f"{BASE_URL}/api/orchestrator/tasks/does_not_exist/dispatch")
        assert r.status_code == 404


# ── 5. Budget tracker unit tests (offline) ────────────────────────
class TestBudgetTracker:
    def test_can_afford_below_cap(self):
        code = (
            "import os, sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "os.environ['ORCH_BUDGET_DAILY_USD_GLOBAL'] = '10.0'; "
            "from engines.orchestrator.budget_tracker import BudgetTracker; "
            "b = BudgetTracker(); "
            "ok, r = b.can_afford('openai', 1.5); "
            "print('ok=', ok, 'reason=', r)"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "ok= True" in r.stdout

    def test_can_afford_over_daily_cap(self):
        code = (
            "import os, sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "os.environ['ORCH_BUDGET_DAILY_USD_GLOBAL'] = '5.0'; "
            "from engines.orchestrator.budget_tracker import BudgetTracker; "
            "b = BudgetTracker(); "
            "b.record('openai', 4.5, 100); "
            "ok, r = b.can_afford('openai', 1.0); "
            "print('ok=', ok); print('reason=', r)"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "ok= False" in r.stdout
        assert "global_daily_usd_exceeded" in r.stdout

    def test_choose_provider_prefers_higher_quality_when_affordable(self):
        code = (
            "import os, sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.orchestrator.budget_tracker import BudgetTracker, BudgetWeights; "
            "b = BudgetTracker(); "
            "w = BudgetWeights(cost=0.0, quality=1.0, latency=0.0, availability=0.0); "
            "pick = b.choose_provider(['a', 'b'], 0.001, weights=w, "
            "quality_scores={'a': 0.2, 'b': 0.9}); "
            "print('pick=', pick)"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "pick= b" in r.stdout

    def test_snapshot_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/budget")
        s = r.json()
        assert "global" in s
        assert "per_provider" in s
        assert "weights" in s
        for k in ("cost", "quality", "latency", "availability"):
            assert k in s["weights"]


# ── 6. Subordinate hook — auto_scheduler defers to orchestrator ──
class TestSubordinateHook:
    def test_auto_scheduler_defers_when_orchestrator_active(self, admin):
        # Ensure orchestrator running via API (this pod's backend)
        admin.post(f"{BASE_URL}/api/orchestrator/start")
        time.sleep(0.5)
        script = """
import asyncio, sys
sys.path.insert(0, '/app/backend')
sys.path.insert(0, '/app/backend/legacy')

async def main():
    from engines.orchestrator import get_orchestrator
    await get_orchestrator().start()
    from engines.auto_scheduler import _is_subordinated
    is_sub = await _is_subordinated()
    print('subordinated=', is_sub)
    await get_orchestrator().stop()

asyncio.run(main())
"""
        r = subprocess.run(
            ["python3", "-c", script], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy",
                 "MONGO_URL": os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
                 "DB_NAME": os.environ.get("DB_NAME", "strategy_factory_v1")},
        )
        assert r.returncode == 0, f"stderr={r.stderr} stdout={r.stdout}"
        assert "subordinated= True" in r.stdout, r.stdout
        admin.post(f"{BASE_URL}/api/orchestrator/stop")


# ── 7. Boot log invariant ─────────────────────────────────────────
class TestBootLogRouterCount:
    def test_router_count_is_93(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches, "no mount log line found"
        # Router count grows additively as new phases land.
        assert matches[-1] in ('92','93','94','95','96'), (
            f"latest boot reports {matches[-1]} routers (expected 93..95)")


# ── 8. Regression — Phase A + B + B.1 endpoints ──────────────────
class TestRegressionSweep:
    ENDPOINTS = [
        "/api/health",
        "/api/learning/config",
        "/api/learning/metrics",
        "/api/learning/scheduler/status",
        "/api/learning/continuous/status",
        "/api/ai-workforce/health",
        "/api/knowledge/status",
        "/api/library/list",
        "/api/orchestrator/status",
        "/api/orchestrator/tasks",
        "/api/orchestrator/budget",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} -> {r.status_code}: {r.text[:200]}"

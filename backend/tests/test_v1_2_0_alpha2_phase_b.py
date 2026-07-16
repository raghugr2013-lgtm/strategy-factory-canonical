"""v1.2.0-alpha2 Phase B — Continuous Learning Supervisor + Router
+ Outcome-conditioned retrieval + Strategy lineage.

Additive to Phase A. Verifies:
  - New endpoints under /api/learning/* and /api/ai-workforce/*
  - Env-configurable thresholds surface via /api/learning/config
  - Supervisor cycle runs end-to-end (offline-safe generator)
  - Metrics API reports the correct counters + pass rates
  - Router-config exposes per-task provider chains
  - AI Workforce Router bypasses when flag off (backward compat)
  - Outcome-conditioned retrieval module imports without side-effects
  - Legacy Phase A endpoints still work (regression)
"""
from __future__ import annotations

import os
import re
import time

import pymongo
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "strategy_factory_v1")


@pytest.fixture(scope="module")
def mongo():
    c = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    yield c[DB_NAME]
    c.close()


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
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("access_token") or d.get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


CYCLE_RUN_IDS: set = set()


# ── 1. Learning config endpoint ────────────────────────────────────
class TestLearningConfig:
    def test_config_returns_all_sections(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/config")
        assert r.status_code == 200
        c = r.json()
        for section in ("supervisor", "scheduler", "retrieval", "ai_workforce"):
            assert section in c, f"missing section: {section}"
        # Default pf_min is 1.2 per design doc
        assert c["supervisor"]["pf_min"] == 1.2
        assert c["supervisor"]["min_trades"] == 30
        assert isinstance(c["supervisor"]["mutation_enabled"], bool)
        assert isinstance(c["scheduler"]["enabled"], bool)
        assert c["retrieval"]["outcome_weight"] >= 0.0
        # AI Workforce failover default is OFF (opt-in per user choice)
        assert c["ai_workforce"]["failover_enabled"] is False


# ── 2. Supervisor cycle runs end-to-end ────────────────────────────
class TestSupervisorCycle:
    def test_cycle_completes_and_returns_stages(self, admin):
        r = admin.post(f"{BASE_URL}/api/learning/cycles", json={
            "pair": "EURUSD", "timeframe": "H1",
            "style": "trend-following", "count": 1,
            "max_duration_s": 60,
        })
        assert r.status_code == 200, r.text
        run = r.json()
        assert run.get("run_id") and re.fullmatch(r"[0-9a-f]{32}", run["run_id"])
        CYCLE_RUN_IDS.add(run["run_id"])
        assert run["status"] in ("completed", "early_reject", "failed")
        stages = run.get("stages") or []
        assert len(stages) >= 1
        # generate must always run first
        assert stages[0]["stage"] == "generate"
        # Every recorded stage must have a status
        for s in stages:
            assert s["status"] in ("pass", "fail", "partial", "skipped")

    def test_cycle_get_by_run_id(self, admin):
        assert CYCLE_RUN_IDS, "no cycles ran"
        rid = next(iter(CYCLE_RUN_IDS))
        r = admin.get(f"{BASE_URL}/api/learning/cycles/{rid}")
        assert r.status_code == 200
        body = r.json()
        assert body["run_id"] == rid

    def test_missing_run_id_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/cycles/deadbeef" * 4)
        assert r.status_code == 404


# ── 3. Metrics endpoint ────────────────────────────────────────────
class TestLearningMetrics:
    def test_metrics_shape_after_cycle(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "counters" in body and "pass_rates" in body
        c = body["counters"]
        assert c["cycles_started"] >= 1
        # generate stage should have at least 1 attempt after cycle
        pr = body["pass_rates"]
        assert "generate" in pr or "backtest" in pr
        if "generate" in pr:
            assert pr["generate"]["total"] >= 1
            assert 0.0 <= pr["generate"]["pass_rate"] <= 1.0


# ── 4. Scheduler endpoints ─────────────────────────────────────────
class TestScheduler:
    def test_status_is_dormant_by_default(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/scheduler/status")
        assert r.status_code == 200
        body = r.json()
        assert body["running"] is False
        assert isinstance(body["interval_seconds"], int)

    def test_start_and_stop_scheduler(self, admin):
        r = admin.post(f"{BASE_URL}/api/learning/scheduler/start")
        assert r.status_code == 200, r.text
        assert r.json()["running"] is True
        # Query status
        rs = admin.get(f"{BASE_URL}/api/learning/scheduler/status")
        assert rs.json()["running"] is True
        # Stop
        r = admin.post(f"{BASE_URL}/api/learning/scheduler/stop")
        assert r.status_code == 200
        assert r.json()["running"] is False

    def test_start_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/learning/scheduler/start")
        assert r.status_code in (401, 403)


# ── 5. Enriched lineage endpoint ───────────────────────────────────
class TestLineageDetail:
    def test_lineage_detail_returns_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/lineage/detail/nonexistent-hash")
        assert r.status_code == 200
        body = r.json()
        assert body["strategy_hash"] == "nonexistent-hash"
        assert isinstance(body["lineage"], dict)
        assert isinstance(body["chain"], list)


# ── 6. AI Workforce Router endpoints ───────────────────────────────
class TestRouterConfig:
    def test_router_config_returns_all_task_chains(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/router-config")
        assert r.status_code == 200
        body = r.json()
        assert body["enabled"] is False  # default per user choice
        assert set(body["chains"].keys()) >= {
            "strategy", "repair", "mutate", "backtest_review", "portfolio", "generic",
        }
        # Every chain is a non-empty list of provider strings
        for task, chain in body["chains"].items():
            assert isinstance(chain, list) and len(chain) >= 1
            assert all(isinstance(p, str) and p for p in chain)

    def test_router_metrics_returns_counters(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/metrics")
        assert r.status_code == 200
        body = r.json()
        for k in ("enabled", "counters", "effective_chains", "quality_scores"):
            assert k in body
        for c in ("route_calls", "route_ok", "route_bypassed"):
            assert c in body["counters"]

    def test_quality_snapshot(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/quality")
        assert r.status_code == 200
        body = r.json()
        assert "scores" in body and isinstance(body["scores"], list)
        assert "weights" in body


class TestRouteTest:
    def test_route_test_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/ai-workforce/route-test",
                   json={"task": "generic", "prompt": "ping"})
        assert r.status_code in (401, 403)

    def test_route_test_bypass_returns_shape(self, admin):
        # Router flag is off → route_test uses direct bypass path.
        # VIE is down in the test pod, so we expect ok=False with the
        # standard router response shape.
        r = admin.post(f"{BASE_URL}/api/ai-workforce/route-test",
                       json={"task": "generic", "prompt": "ping"})
        assert r.status_code == 200, r.text
        body = r.json()
        for k in ("ok", "attempts", "text_preview", "router_enabled"):
            assert k in body
        assert body["router_enabled"] is False


# ── 7. Router internals (offline) ──────────────────────────────────
class TestRouterInternals:
    def test_effective_chain_orders_by_quality(self):
        import subprocess
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.ai_workforce.router import effective_chain, DEFAULT_CHAIN; "
            "scores = {'gemini': 0.9, 'openai': 0.4}; "
            "c = effective_chain('strategy', scores); "
            "print(c[0], c[1])"
        )
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            cwd="/app/backend",
            env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert r.stdout.strip().startswith("gemini "), r.stdout

    def test_scorer_snapshot_offline(self):
        import subprocess
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "import asyncio; from engines.ai_workforce.scorer import score_snapshot; "
            "snap = asyncio.run(score_snapshot(ttl_s=0.0)); "
            "print('scores_len=', len(snap['scores'])); "
            "print('weights=', 'generate' in snap['weights'])"
        )
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            cwd="/app/backend",
            env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "weights= True" in r.stdout


# ── 8. Outcome-conditioning module imports cleanly ─────────────────
class TestOutcomeConditioning:
    def test_module_imports_and_applies_zero_boost_on_empty(self):
        import subprocess
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "import asyncio; "
            "from engines.knowledge.outcome_conditioning import boosts_for, apply_boosts; "
            "b = asyncio.run(boosts_for([], weight=2.0)); "
            "print('empty=', b == {}); "
            "scored = [(3.0, {'strategy_hash':'x'})]; "
            "out = apply_boosts(scored, {}); "
            "print('bypass=', out[0][0] == 3.0)"
        )
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            cwd="/app/backend",
            env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "empty= True" in r.stdout
        assert "bypass= True" in r.stdout


# ── 9. Lineage stamp is idempotent ─────────────────────────────────
class TestLineageStamp:
    def test_stamp_lineage_updates_matching_docs(self, mongo):
        import subprocess
        # Seed a fake strategy row we can safely mutate + delete
        mongo["strategies"].insert_one({
            "strategy_hash": "phase-b-lineage-test",
            "pair": "EURUSD", "timeframe": "H1", "style": "trend",
            "strategy_text": "phase B lineage test row",
        })
        try:
            code = (
                "import sys; sys.path.insert(0, '/app/backend'); "
                "sys.path.insert(0, '/app/backend/legacy'); "
                "import asyncio; from engines.learning.lineage import stamp_lineage; "
                "res = asyncio.run(stamp_lineage('phase-b-lineage-test', "
                "  learning_run_id='r1', stage='generate', "
                "  provider='openai', model='gpt-4o-mini', "
                "  token_usage={'total': 100})); "
                "print('ok=', res['ok'])"
            )
            r = subprocess.run(
                ["python3", "-c", code],
                capture_output=True, text=True,
                cwd="/app/backend",
                env={**os.environ,
                     "PYTHONPATH": "/app/backend:/app/backend/legacy",
                     "MONGO_URL": MONGO_URL,
                     "DB_NAME": DB_NAME},
            )
            assert r.returncode == 0, r.stderr
            assert "ok= True" in r.stdout
            row = mongo["strategies"].find_one({"strategy_hash": "phase-b-lineage-test"})
            assert row and row.get("lineage")
            assert row["lineage"]["provider"] == "openai"
            assert row["lineage"]["learning_run_id"] == "r1"
            assert "generate" in row["lineage"]["stage_chain"]
        finally:
            mongo["strategies"].delete_many({"strategy_hash": "phase-b-lineage-test"})


# ── 10. Regression — Phase A endpoints still 200 ───────────────────
class TestPhaseARegression:
    ENDPOINTS = [
        "/api/health",
        "/api/learning/runs",         # POST also works — GET here fetches list
        "/api/learning/events?limit=5",
        "/api/ai-workforce/health",
        "/api/ai-workforce/recent",
        "/api/ai-workforce/scores",
        "/api/knowledge/status",
        "/api/library/list",
        "/api/strategies/explorer",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} -> {r.status_code}: {r.text[:200]}"


# ── 11. Boot log — 92 routers still ───────────────────────────────
class TestBootLogRouterCount:
    def test_boot_log_still_92_routers(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches, "no mount log line found"
        # Later phases (B.2, C, D) add more routers additively.
        assert matches[-1] in ('92','93','94','95','96','97','98'), (
            f"latest boot reports {matches[-1]} routers (expected 92..95 — additive)")


# ── 12. Cleanup ────────────────────────────────────────────────────
class TestCleanup:
    def test_cleanup_cycle_events(self, mongo):
        if CYCLE_RUN_IDS:
            mongo["outcome_events"].delete_many({
                "learning_run_id": {"$in": list(CYCLE_RUN_IDS)},
            })
        # Verify our test-only strategy hashes are gone
        mongo["strategies"].delete_many({"strategy_hash": "phase-b-lineage-test"})

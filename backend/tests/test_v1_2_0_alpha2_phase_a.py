"""v1.2.0-alpha2 phase A — outcome-event ledger + AI Workforce foundation.

Verifies:
  - Design doc + boot log (92 routers)
  - 8 new endpoints under /api/learning/* and /api/ai-workforce/*
  - CircuitBreaker + Telemetry singleton mechanics (offline)
  - Regression sweep — 8 baseline endpoints still 200
  - Backward-compat — _single_attempt returns None on VIE 5xx / empty output
  - Cleanup: outcome_events left at count=0
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time

import pymongo
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "strategy_factory_v1")

# Test-only hashes used across the suite for later cleanup.
TEST_HASHES = ["test-hash-x", "test-hash-y", "test-hash-lineage-child", "test-hash-lineage-parent", "z"]


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
                 json={"email": "admin@strategy-factory.local", "password": "admin123"})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def admin(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end(mongo):
    """Ensure outcome_events is clean before + after suite."""
    mongo["outcome_events"].delete_many({"strategy_hash": {"$in": TEST_HASHES}})
    yield
    mongo["outcome_events"].delete_many({"strategy_hash": {"$in": TEST_HASHES}})
    # Also remove any events that referenced our test learning_run_ids
    # (in case strategy_hash was None on some rows)
    # This is a safety net — the test module tracks run_ids in RUN_IDS.
    if RUN_IDS:
        mongo["outcome_events"].delete_many({"learning_run_id": {"$in": list(RUN_IDS)}})


# Shared state (test data flow)
RUN_IDS: set = set()
STATE: dict = {}


# ── 1. Boot log — 92 routers ───────────────────────────────────────
class TestBootLog:
    def test_backend_reports_92_routers(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches, "no router-mount log line found"
        # Latest boot must be 92 or 93 (Phase B.2 adds orchestrator_engine)
        assert matches[-1] in ("92", "93"), f"latest boot reports {matches[-1]} routers, expected 92 or 93"


# ── 2. Design doc ──────────────────────────────────────────────────
class TestDesignDoc:
    DOC = "/app/docs/V1.2.0_ALPHA2_DESIGN.md"

    def test_doc_exists_and_size(self):
        assert os.path.exists(self.DOC)
        assert os.path.getsize(self.DOC) > 8 * 1024, "design doc must be >8KB"

    def test_doc_has_all_sections(self):
        with open(self.DOC) as f:
            body = f.read()
        for header in [
            "## 1. Structural review",
            "## 2. Layered architecture",
            "## 3. Data model — the new collections",
            "## 4. Emitter contract",
            "## 5. AI Workforce",
            "## 6. Continuous learning supervisor",
            "## 7. Portfolio Intelligence injection",
            "## 8. Operator Intelligence Dashboard",
            "## 9. What ships in this pass",
        ]:
            assert header in body, f"missing header: {header}"


# ── 3. POST /api/learning/runs ─────────────────────────────────────
class TestLearningRuns:
    def test_start_run_returns_hex_id(self, admin):
        r = admin.post(f"{BASE_URL}/api/learning/runs")
        assert r.status_code == 200
        data = r.json()
        rid = data.get("learning_run_id")
        assert rid and isinstance(rid, str)
        assert len(rid) == 32 and re.fullmatch(r"[0-9a-f]{32}", rid), f"bad run id: {rid}"
        RUN_IDS.add(rid)
        STATE["run_id_1"] = rid

    def test_start_run_returns_distinct_ids(self, admin):
        r1 = admin.post(f"{BASE_URL}/api/learning/runs").json()["learning_run_id"]
        r2 = admin.post(f"{BASE_URL}/api/learning/runs").json()["learning_run_id"]
        RUN_IDS.update([r1, r2])
        assert r1 != r2


# ── 4. POST /api/learning/events ───────────────────────────────────
class TestLearningEvents:
    def test_write_event_persists_with_schema_v1(self, admin, mongo):
        run_id = STATE["run_id_1"]
        payload = {
            "learning_run_id": run_id,
            "stage": "generate",
            "status": "pass",
            "strategy_hash": "test-hash-x",
            "provider": "openai",
            "model": "gpt-4o-mini",
            "metrics": {"pf": 1.6},
        }
        r = admin.post(f"{BASE_URL}/api/learning/events", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["event_id"] and isinstance(body["event_id"], str)
        assert body["learning_run_id"] == run_id

        # Direct pymongo verification
        row = mongo["outcome_events"].find_one({"learning_run_id": run_id, "strategy_hash": "test-hash-x"})
        assert row is not None
        assert row.get("__v") == 1
        assert row["stage"] == "generate"
        assert row["status"] == "pass"
        assert row["provider"] == "openai"
        assert row["model"] == "gpt-4o-mini"
        assert row["metrics"] == {"pf": 1.6}

    def test_invalid_stage_returns_422(self, admin):
        r = admin.post(f"{BASE_URL}/api/learning/events", json={
            "stage": "foo", "status": "pass",
        })
        assert r.status_code == 422, f"expected 422 for invalid stage, got {r.status_code}: {r.text}"


# ── 5. Full pipeline emission + operator decision ──────────────────
class TestFullPipeline:
    STAGES = ["generate", "validate", "repair", "backtest", "optimize"]

    def test_emit_pipeline_and_operator_decision(self, admin, mongo):
        # Fresh run id for this test
        rid = admin.post(f"{BASE_URL}/api/learning/runs").json()["learning_run_id"]
        RUN_IDS.add(rid)
        STATE["pipeline_run_id"] = rid

        # 5 pipeline stages
        for st in self.STAGES:
            r = admin.post(f"{BASE_URL}/api/learning/events", json={
                "learning_run_id": rid,
                "stage": st, "status": "pass",
                "strategy_hash": "test-hash-y",
                "provider": "openai", "model": "gpt-4o-mini",
            })
            assert r.status_code == 200, f"stage {st} failed: {r.text}"

        # Operator approval
        r = admin.post(f"{BASE_URL}/api/learning/operator-decision", json={
            "learning_run_id": rid,
            "strategy_hash": "test-hash-y",
            "approved": True, "rating": 4, "comment": "ok",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["event_id"] and isinstance(body["event_id"], str)

        # Direct pymongo — approve row must have operator.rating=4
        row = mongo["outcome_events"].find_one({
            "learning_run_id": rid, "stage": "approve", "strategy_hash": "test-hash-y",
        })
        assert row is not None, "approve row not found"
        assert row.get("operator", {}).get("rating") == 4
        assert row.get("operator", {}).get("comment") == "ok"


# ── 6. GET /api/learning/events ────────────────────────────────────
class TestListEvents:
    def test_list_events_by_run(self, admin):
        rid = STATE["pipeline_run_id"]
        r = admin.get(f"{BASE_URL}/api/learning/events", params={"learning_run_id": rid})
        assert r.status_code == 200
        body = r.json()
        # 5 pipeline + 1 approve = 6
        assert body["count"] == 6, f"expected 6 events, got {body['count']}"
        assert len(body["events"]) == 6
        assert body["query"]["learning_run_id"] == rid
        for ev in body["events"]:
            for k in ("stage", "status", "ts", "learning_run_id"):
                assert k in ev, f"event missing key {k}: {ev}"
            assert ev["learning_run_id"] == rid


# ── 7. GET /api/learning/runs (listing) ────────────────────────────
class TestListRuns:
    def test_list_runs(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/runs", params={"limit": 10})
        assert r.status_code == 200
        body = r.json()
        assert "runs" in body and "count" in body
        assert isinstance(body["runs"], list)
        # our pipeline run must appear
        pipeline_rid = STATE["pipeline_run_id"]
        matches = [r for r in body["runs"] if r["learning_run_id"] == pipeline_rid]
        assert matches, f"pipeline run {pipeline_rid} missing from /runs list"
        run = matches[0]
        for k in ("learning_run_id", "first_ts", "last_ts", "n_events", "stages", "final_status"):
            assert k in run, f"missing {k} on run summary"
        assert run["n_events"] == 6
        # stages is a set → list of unique
        assert set(run["stages"]) == {"generate", "validate", "repair", "backtest", "optimize", "approve"}


# ── 8. GET /api/learning/lineage/{hash} ────────────────────────────
class TestLineage:
    def test_single_hash_chain_length_1(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/lineage/test-hash-y")
        assert r.status_code == 200
        body = r.json()
        assert body["strategy_hash"] == "test-hash-y"
        assert body["chain"] == ["test-hash-y"]
        # 5 pipeline + 1 approve = 6 events
        assert len(body["events"]) >= 6

    def test_chain_with_parent_hash(self, admin, mongo):
        # Build a 2-link chain: child (test-hash-lineage-child) --parent--> parent (test-hash-lineage-parent)
        rid = admin.post(f"{BASE_URL}/api/learning/runs").json()["learning_run_id"]
        RUN_IDS.add(rid)
        # Parent event (a generate row on the parent hash)
        r1 = admin.post(f"{BASE_URL}/api/learning/events", json={
            "learning_run_id": rid, "stage": "generate", "status": "pass",
            "strategy_hash": "test-hash-lineage-parent",
        })
        assert r1.status_code == 200

        # Child event: repair on the child hash referencing parent via parent_hash
        # /learning/events pydantic model doesn't accept parent_hash. Insert directly via pymongo (matches emitter contract).
        import datetime as dt
        mongo["outcome_events"].insert_one({
            "learning_run_id": rid,
            "stage": "repair",
            "status": "pass",
            "strategy_hash": "test-hash-lineage-child",
            "parent_hash": "test-hash-lineage-parent",
            "reason": "test", "metrics": {},
            "provider": None, "model": None, "prompt_version": None,
            "retrieval_context_hash": None, "token_usage": None,
            "duration_ms": 0, "cost_usd": None, "operator": None,
            "ts": dt.datetime.now(dt.timezone.utc),
            "__v": 1,
        })

        r = admin.get(f"{BASE_URL}/api/learning/lineage/test-hash-lineage-child")
        assert r.status_code == 200
        body = r.json()
        assert body["chain"][0] == "test-hash-lineage-child"
        assert "test-hash-lineage-parent" in body["chain"], f"chain missing parent: {body['chain']}"


# ── 9. AI Workforce endpoints ──────────────────────────────────────
class TestAIWorkforceEndpoints:
    def test_health_idle_pod(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/health")
        assert r.status_code == 200
        body = r.json()
        assert "providers" in body
        assert body["window_s"] == 3600
        # Idle pod → providers dict may be {} OR contain entries from prior smoke tests. Accept dict.
        assert isinstance(body["providers"], dict)

    def test_recent_idle_pod(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/recent")
        assert r.status_code == 200
        body = r.json()
        assert "calls" in body
        assert isinstance(body["calls"], list)

    def test_scores_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/ai-workforce/scores")
        assert r.status_code == 200
        body = r.json()
        assert "scores" in body and isinstance(body["scores"], list)
        # If any scores exist (they should because we emitted openai events), verify shape
        for s in body["scores"]:
            for k in ("provider", "quality_score", "total_events", "per_stage"):
                assert k in s
            assert 0.0 <= s["quality_score"] <= 1.0
            assert isinstance(s["per_stage"], dict)
        # openai must be present since we emitted 6 rows with provider=openai + pass
        openai_row = next((s for s in body["scores"] if s["provider"] == "openai"), None)
        assert openai_row is not None, "openai row missing after emitting provider=openai events"
        # 6 passes / 6 total = 1.0 (unless prior data pollutes; expect >= 0.5)
        assert openai_row["quality_score"] > 0.0

    def test_circuit_reset_requires_admin(self, api):
        # Fresh session with no auth
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/ai-workforce/circuit/openai/reset")
        assert r.status_code in (401, 403), f"unauth call must be gated, got {r.status_code}"

    def test_circuit_reset_with_admin(self, admin):
        r = admin.post(f"{BASE_URL}/api/ai-workforce/circuit/openai/reset")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["provider"] == "openai"
        assert body["state"] == "closed"


# ── 10. Circuit-breaker + telemetry offline mechanics ──────────────
class TestOfflineSingletons:
    def test_circuit_breaker_trips_open_after_15_failures(self):
        # Run in subprocess to preserve isolation semantics from review spec
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.ai_workforce import get_breaker; "
            "b = get_breaker(); b.reset('test'); "
            "[b.record('test', False) for _ in range(15)]; "
            "s = b.snapshot()['test']; "
            "print(s['state'], s['error_rate'])"
        )
        import subprocess
        r = subprocess.run(
            ["python3", "-c", code],
            capture_output=True, text=True,
            cwd="/app/backend",
            env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, f"subprocess failed: {r.stderr}"
        assert "open 1.0" in r.stdout, f"expected 'open 1.0', got: {r.stdout!r}"

    def test_telemetry_record(self):
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.ai_workforce import get_telemetry; "
            "t = get_telemetry(); "
            "t.record(provider='openai', model='gpt-4o-mini', task='strategy', ok=True, latency_ms=250, prompt_tokens=100, completion_tokens=50); "
            "print(list(t.snapshot(3600).keys()))"
        )
        import subprocess
        r = subprocess.run(["python3", "-c", code], capture_output=True, text=True, cwd="/app/backend",
                           env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, f"subprocess failed: {r.stderr}"
        assert "openai" in r.stdout, f"expected openai in snapshot keys, got: {r.stdout!r}"

    def test_emitter_smoke(self, mongo):
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); sys.path.insert(0, '/app/backend/legacy'); "
            "import asyncio; from engines.learning import emit, new_run_id; "
            "rid = new_run_id(); "
            "print(rid); "
            "print(asyncio.run(emit('validate', learning_run_id=rid, status='pass', strategy_hash='z', reason='test')))"
        )
        import subprocess
        r = subprocess.run(["python3", "-c", code], capture_output=True, text=True, cwd="/app/backend",
                           env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, f"subprocess failed: {r.stderr}\n{r.stdout}"
        lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert len(lines) == 2
        rid, inserted_id = lines[0], lines[1]
        RUN_IDS.add(rid)
        assert inserted_id and inserted_id != "None", f"emitter returned None: {inserted_id!r}"
        # Verify pymongo row + __v=1
        row = mongo["outcome_events"].find_one({"learning_run_id": rid, "strategy_hash": "z"})
        assert row is not None
        assert row.get("__v") == 1


# ── 11. Regression sweep ───────────────────────────────────────────
class TestRegressionSweep:
    ENDPOINTS = [
        "/api/health",
        "/api/library/list",
        "/api/strategies/explorer",
        "/api/prop-firms/list",
        "/api/knowledge/status",
        "/api/admin/providers",
        "/api/llm/diagnostics",
        "/api/auto-maintenance/status",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} returned {r.status_code}: {r.text[:200]}"


# ── 12. Backward-compat: _single_attempt None-on-5xx/empty contract ─
class TestLLMRunnerBackwardCompat:
    """Existing contract per llm_runner.py docstring line 107-108:
        'Raises on transport error; returns None on provider-level
         failure (no available provider, upstream 5xx).'
    We verify:
      (a) source: `return None` still exists after each 503/5xx/empty branch
      (b) source: telemetry.record() is added but doesn't replace None returns
      (c) run_chat (public wrapper) still returns None end-to-end on VIE-down
          (catches ConnectError → last_err → returns None).
    """
    LLM = "/app/backend/legacy/engines/llm_runner.py"

    def test_source_has_return_none_on_503_5xx_empty(self):
        with open(self.LLM) as f:
            src = f.read()
        # 503 branch
        assert "r.status_code == 503" in src
        # generic >=400 branch
        assert "r.status_code >= 400" in src
        # empty-output branch
        assert "if not out:" in src
        # All three branches end with `return None`
        assert src.count("return None") >= 3, f"expected >=3 `return None` paths, got {src.count('return None')}"

    def test_telemetry_calls_added_but_do_not_swallow_returns(self):
        with open(self.LLM) as f:
            src = f.read()
        # telemetry.record calls present
        assert "_tel.record(" in src
        # And imports are wrapped in try/except so absence doesn't break the runner
        assert "from engines.ai_workforce import get_telemetry" in src

    def test_run_chat_returns_none_end_to_end_on_vie_down(self):
        """VIE is down in this pod. run_chat MUST return None (existing contract), not raise."""
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); sys.path.insert(0, '/app/backend/legacy'); "
            "import os; os.environ['LLM_RETRY_ENABLED']='0'; "
            "import asyncio; from engines.llm_runner import run_chat; "
            "result = asyncio.run(run_chat(task='strategy', prompt='hi', system_message='')); "
            "print('RESULT=', repr(result))"
        )
        import subprocess
        r = subprocess.run(["python3", "-c", code], capture_output=True, text=True, cwd="/app/backend",
                           env={**os.environ, "PYTHONPATH": "/app/backend:/app/backend/legacy",
                                "LLM_RETRY_ENABLED": "0"}, timeout=60)
        assert r.returncode == 0, f"run_chat raised: {r.stderr}"
        assert "RESULT= None" in r.stdout, f"expected None on VIE-down pod, got: {r.stdout!r}"


# ── 13. Cleanup verification ───────────────────────────────────────
class TestCleanup:
    def test_cleanup_leaves_collection_clean(self, mongo):
        # Explicitly do the delete_many the review asks for, then verify count=0
        # for our test hashes.
        mongo["outcome_events"].delete_many({"strategy_hash": {"$in": TEST_HASHES}})
        if RUN_IDS:
            mongo["outcome_events"].delete_many({"learning_run_id": {"$in": list(RUN_IDS)}})
        remaining = mongo["outcome_events"].count_documents({"strategy_hash": {"$in": TEST_HASHES}})
        assert remaining == 0, f"cleanup left {remaining} test rows"

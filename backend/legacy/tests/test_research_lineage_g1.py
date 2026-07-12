"""Phase 26 / G1 — Research lineage backend integration tests."""
import os
import sys
import asyncio
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

sys.path.insert(0, "/app/backend")


def _reset_motor_cache():
    """Motor binds to the first event loop; reset between _arun() calls."""
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None


def _arun(coro):
    _reset_motor_cache()
    return asyncio.run(coro)


# ── Auth helper ──
@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": "admin@local.test", "password": "admin123"},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    token = r.json().get("access_token") or r.json().get("token")
    return {"Authorization": f"Bearer {token}"}


# ────────────────────────────────────────────────
# 1. HTTP API surface
# ────────────────────────────────────────────────
class TestResearchRunsAPI:
    def test_list_runs_empty_or_populated(self, auth_headers):
        r = requests.get(f"{API}/research-runs?limit=50", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "count" in body and "runs" in body
        assert isinstance(body["runs"], list)
        assert body["count"] == len(body["runs"])
        # If there are runs, ensure sorted desc by started_at
        ts = [r.get("started_at") for r in body["runs"] if r.get("started_at")]
        assert ts == sorted(ts, reverse=True)

    def test_get_nonexistent_rrid_returns_404(self, auth_headers):
        rrid = f"rr_does_not_exist_{uuid.uuid4().hex[:8]}"
        r = requests.get(f"{API}/research-runs/{rrid}", headers=auth_headers, timeout=15)
        assert r.status_code == 404
        body = r.json()
        assert body.get("detail") == "research_run_not_found"

    def test_filter_trigger_type(self, auth_headers):
        r = requests.get(
            f"{API}/research-runs?trigger_type=manual_api&limit=20",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        for run in r.json()["runs"]:
            assert run.get("trigger", {}).get("type") == "manual_api"

    def test_filter_status(self, auth_headers):
        r = requests.get(
            f"{API}/research-runs?status=completed&limit=20",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        for run in r.json()["runs"]:
            assert run.get("status") == "completed"

    def test_by_strategy_unknown_hash(self, auth_headers):
        r = requests.get(
            f"{API}/research-runs/by-strategy/{'a' * 40}",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["strategy_hash"] == "a" * 40
        assert body["count"] == 0
        assert body["runs"] == []

    def test_by_library_unknown_id(self, auth_headers):
        r = requests.get(
            f"{API}/research-runs/by-library/nonexistent_lib_id_xyz",
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["library_id"] == "nonexistent_lib_id_xyz"
        assert body["count"] == 0


# ────────────────────────────────────────────────
# 2. Engine-level smoke test for research_lineage public surface
# ────────────────────────────────────────────────
class TestResearchLineageEngine:
    def test_engine_full_lifecycle(self):
        from engines import research_lineage
        from engines.db import get_db

        async def run():
            # Create
            rrid = await research_lineage.new_research_run(
                trigger_type="manual_api",
                trigger_reason="pytest_g1",
                config={"test": True},
            )
            assert rrid.startswith("rr_")

            # Attach children
            await research_lineage.attach_child(rrid, "multi_cycle_run", "mcr_test_1")
            await research_lineage.attach_child(rrid, "auto_run_cycle", "arc_test_1")
            await research_lineage.attach_child(rrid, "mutation_run", "mr_test_1",
                                                extra={"strategy_hash": "h1", "pf": 1.5})
            await research_lineage.attach_child(rrid, "library_save", "lib_test_1",
                                                extra={"strategy_hash": "h1"})
            await research_lineage.attach_child(rrid, "history_row", "h1")
            await research_lineage.attach_child(rrid, "history_row", "h1")

            # Append summary
            await research_lineage.append_summary(
                rrid, strategies_generated=5, strategies_saved=2,
                library_ids=["lib_test_1"], best_pf=1.8, avg_pf=1.4,
            )

            # Fetch
            doc = await research_lineage.get_run(rrid)
            assert doc is not None
            assert doc["research_run_id"] == rrid
            assert doc["status"] == "running"
            assert len(doc["children"]["multi_cycle_run"]) == 1
            assert len(doc["children"]["auto_run_cycle"]) == 1
            assert len(doc["children"]["mutation_run"]) == 1
            assert len(doc["children"]["library_save"]) == 1
            assert doc["children"]["history_row"] == 2
            assert doc["summary"]["strategies_generated"] == 5
            assert doc["summary"]["strategies_saved"] == 2
            assert "lib_test_1" in doc["summary"]["library_ids"]
            assert doc["summary"]["best_pf"] == 1.8

            # list_runs
            runs = await research_lineage.list_runs(limit=10, trigger_type="manual_api")
            assert any(r["research_run_id"] == rrid for r in runs)

            # get_runs_for_library_id
            lib_runs = await research_lineage.get_runs_for_library_id("lib_test_1")
            assert any(r["research_run_id"] == rrid for r in lib_runs)

            # mark_finished
            await research_lineage.mark_finished(rrid, status="completed")
            doc2 = await research_lineage.get_run(rrid)
            assert doc2["status"] == "completed"
            assert doc2["finished_at"] is not None

            # cleanup
            db = get_db()
            await db["research_runs"].delete_one({"research_run_id": rrid})

        _arun(run())

    def test_attach_child_with_none_rrid_is_noop(self):
        from engines import research_lineage

        async def run():
            # Should not raise
            await research_lineage.attach_child(None, "history_row", "x")
            await research_lineage.append_summary(None, strategies_generated=1)
            await research_lineage.mark_finished(None, status="completed")
            assert (await research_lineage.get_run("")) is None
            assert (await research_lineage.get_runs_for_strategy("")) == []
            assert (await research_lineage.get_runs_for_library_id("")) == []

        _arun(run())


# ────────────────────────────────────────────────
# 3. record_performance writes rrid + attaches lineage children
# ────────────────────────────────────────────────
class TestRecordPerformanceLineage:
    def test_record_performance_with_rrid(self):
        from engines import research_lineage, strategy_memory
        from engines.db import get_db

        async def run():
            rrid = await research_lineage.new_research_run(
                trigger_type="manual_api", trigger_reason="test_record_perf",
            )
            h = await strategy_memory.record_performance(
                strategy_text="TEST_strategy if rsi<30 buy else sell",
                pair="EURUSD",
                timeframe="H1",
                name="TEST_lineage_rec_perf",
                source="manual_rerun",
                mutation_run_id="mr_xyz",
                pf=1.6,
                dd_pct=4.0,
                trades=120,
                library_id="lib_lineage_test_999",
                research_run_id=rrid,
            )
            assert isinstance(h, str) and len(h) == 40

            db = get_db()
            # 1) history row carries the rrid
            row = await db["strategy_performance_history"].find_one(
                {"strategy_hash": h, "research_run_id": rrid}, {"_id": 0},
            )
            assert row is not None
            assert row["research_run_id"] == rrid
            assert row["library_id"] == "lib_lineage_test_999"

            # 2) lineage doc has history_row counter, mutation_run + library_save children
            doc = await research_lineage.get_run(rrid)
            assert doc["children"]["history_row"] >= 1
            assert any(
                c["id"] == "mr_xyz"
                for c in doc["children"]["mutation_run"]
            )
            assert any(
                c["id"] == "lib_lineage_test_999"
                for c in doc["children"]["library_save"]
            )
            # summary library_ids updated
            assert "lib_lineage_test_999" in doc["summary"]["library_ids"]

            # 3) by-strategy lookup returns this rrid
            by_strat = await research_lineage.get_runs_for_strategy(h)
            assert any(r["research_run_id"] == rrid for r in by_strat)

            # cleanup
            await db["strategy_performance_history"].delete_many({"strategy_hash": h})
            await db["research_runs"].delete_one({"research_run_id": rrid})

        _arun(run())


# ────────────────────────────────────────────────
# 4. by-strategy endpoint returns runs after seeding via API
# ────────────────────────────────────────────────
class TestBytStrategyHTTP:
    def test_by_strategy_after_seed(self, auth_headers):
        from engines import research_lineage, strategy_memory
        from engines.db import get_db

        async def seed():
            rrid = await research_lineage.new_research_run(
                trigger_type="orchestrator_tick", trigger_reason="api_seed",
            )
            h = await strategy_memory.record_performance(
                strategy_text="TEST_seed_for_api ema cross",
                pair="GBPUSD", timeframe="H4",
                name="TEST_api_seed", source="manual_rerun",
                mutation_run_id="mr_api_seed", pf=2.1,
                research_run_id=rrid,
            )
            await research_lineage.mark_finished(rrid, status="completed")
            return rrid, h

        rrid, h = _arun(seed())
        try:
            r = requests.get(
                f"{API}/research-runs/by-strategy/{h}",
                headers=auth_headers, timeout=15,
            )
            assert r.status_code == 200
            body = r.json()
            assert body["count"] >= 1
            assert any(run["research_run_id"] == rrid for run in body["runs"])

            # Get specific rrid
            r2 = requests.get(f"{API}/research-runs/{rrid}", headers=auth_headers, timeout=15)
            assert r2.status_code == 200
            assert r2.json()["research_run_id"] == rrid
            assert r2.json()["status"] == "completed"
        finally:
            async def cleanup():
                db = get_db()
                await db["strategy_performance_history"].delete_many({"strategy_hash": h})
                await db["research_runs"].delete_one({"research_run_id": rrid})
            _arun(cleanup())


# ────────────────────────────────────────────────
# 5. auto_mutation_runner / multi_cycle_runner auto-create rrid
#    (smoke test signatures only — we verify the kw param exists)
# ────────────────────────────────────────────────
class TestEngineSignatures:
    def test_run_single_cycle_accepts_research_run_id(self):
        import inspect
        from engines.auto_mutation_runner import run_single_cycle, run_auto_mutation
        assert "research_run_id" in inspect.signature(run_single_cycle).parameters
        assert "research_run_id" in inspect.signature(run_auto_mutation).parameters

    def test_start_multi_cycle_accepts_research_run_id(self):
        import inspect
        from engines.multi_cycle_runner import start_multi_cycle
        assert "research_run_id" in inspect.signature(start_multi_cycle).parameters

    def test_record_performance_accepts_research_run_id(self):
        import inspect
        from engines.strategy_memory import record_performance, record_from_mutation_result
        assert "research_run_id" in inspect.signature(record_performance).parameters
        assert "research_run_id" in inspect.signature(record_from_mutation_result).parameters

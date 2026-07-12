"""Regression tests for the every-15-min auto-discovery scheduler.

Covers:
  • start_scheduler is idempotent (replaces existing job).
  • Status reflects enabled flag + interval + persisted config.
  • Stop turns it off and persists the disabled flag.
  • Restore-on-startup re-enables when persistent config says enabled.
  • Restore is a no-op when persistent config says disabled.
  • Tick handler calls run_single_cycle exactly once with the
    spec-defined defaults (batch_size=5, quality_filter=True,
    quality_threshold=55, timeout_seconds=420).
  • Tick handler counts skipped / errored runs into runtime metrics.
  • get_status surfaces last-N history from `auto_run_cycles`.

These tests stub out APScheduler entirely (we don't want a real
background thread firing during tests) and stub the run_single_cycle
helper so we never touch the real mutation pipeline.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, "/app/backend")

from engines import auto_scheduler as sched  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# In-memory DB stub
# ─────────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rows): self._rows = list(rows)
    def sort(self, *_a, **_k): return self
    def limit(self, n): self._rows = self._rows[:int(n)]; return self
    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class _Coll:
    def __init__(self):
        self._rows: List[Dict[str, Any]] = []
        self._kv: Dict[str, Dict[str, Any]] = {}

    async def find_one(self, query, projection=None):
        if "_id" in query:
            return self._kv.get(query["_id"])
        return self._rows[0] if self._rows else None

    async def update_one(self, query, update, upsert=False):
        if "_id" in query and upsert:
            doc = self._kv.setdefault(query["_id"], {})
            doc.update(update.get("$set", {}))
            return {"matched_count": 1, "modified_count": 1}
        return {"matched_count": 0}

    async def insert_one(self, doc):
        self._rows.append(dict(doc)); return {"inserted_id": len(self._rows)}

    async def count_documents(self, query):
        return len(self._rows)

    def find(self, query=None, projection=None):
        return _Cursor(self._rows)


class _DB:
    def __init__(self):
        self._colls: Dict[str, _Coll] = {}

    def __getitem__(self, name):
        self._colls.setdefault(name, _Coll())
        return self._colls[name]


@pytest.fixture
def fake_db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(sched, "get_db", lambda: db)
    return db


# ─────────────────────────────────────────────────────────────────────
# APScheduler stub — captures jobs without actually starting threads
# ─────────────────────────────────────────────────────────────────────

class _FakeJob:
    def __init__(self, fn): self.fn = fn; self.next_run_time = None


class _FakeScheduler:
    def __init__(self, *_a, **_k):
        self._jobs: Dict[str, _FakeJob] = {}
        self.running = False

    def add_job(self, fn, *, trigger=None, id=None, **_k):
        self._jobs[id] = _FakeJob(fn)

    def remove_job(self, jid): self._jobs.pop(jid, None)
    def get_job(self, jid): return self._jobs.get(jid)
    def start(self): self.running = True
    def shutdown(self, wait=False): self.running = False


@pytest.fixture(autouse=True)
def _scheduler_stub(monkeypatch):
    """Replace APScheduler so tests can run synchronously."""
    monkeypatch.setattr(sched, "AsyncIOScheduler", _FakeScheduler)
    # Reset module-level state between tests
    sched._scheduler = None
    sched._runtime.update({
        "enabled": False, "started_at": None, "last_tick_at": None,
        "last_status": None, "last_reason": None,
        "tick_count": 0, "skip_count": 0, "error_count": 0,
    })


@pytest.fixture
def fake_run_cycle(monkeypatch):
    """Stub run_single_cycle and capture every invocation."""
    captured: List[Dict[str, Any]] = []

    async def _fake(**kwargs):
        captured.append(dict(kwargs))
        return {
            "status": "completed", "reason": None, "pair": kwargs.get("pair") or "EURUSD",
            "strategies_generated": kwargs.get("batch_size"),
            "strategies_saved": 1, "avg_pf": 1.7, "avg_dd": 6.0,
        }

    monkeypatch.setattr(sched, "run_single_cycle", _fake)
    return captured


# ─────────────────────────────────────────────────────────────────────
# start / stop / status
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestStartStop:
    async def test_start_sets_default_config(self, fake_db, fake_run_cycle):
        res = await sched.start_scheduler()
        assert res["enabled"] is True
        assert res["interval_minutes"] == 15
        assert res["payload"]["batch_size"] == 5
        assert res["payload"]["quality_filter"] is True
        assert res["payload"]["quality_threshold"] == 55.0
        assert res["payload"]["timeout_seconds"] == 420.0

    async def test_start_idempotent_replaces_job(self, fake_db, fake_run_cycle):
        await sched.start_scheduler(interval_minutes=5)
        await sched.start_scheduler(interval_minutes=10)  # replace
        s = sched._ensure_scheduler()
        assert "auto_discovery" in s._jobs

    async def test_start_clamps_interval(self, fake_db, fake_run_cycle):
        await sched.start_scheduler(interval_minutes=99999)
        cfg = await sched._load_config()
        assert cfg["interval_minutes"] == 1440

    async def test_stop_disables_and_persists(self, fake_db, fake_run_cycle):
        await sched.start_scheduler()
        await sched.stop_scheduler()
        cfg = await sched._load_config()
        assert cfg["enabled"] is False
        assert sched._scheduler is None

    async def test_status_reflects_running_state(self, fake_db, fake_run_cycle, monkeypatch):
        async def _empty_history(limit):
            return []
        monkeypatch.setattr(sched, "list_cycle_runs", _empty_history)

        st_off = await sched.get_status()
        assert st_off["enabled"] is False
        assert st_off["history"] == []

        await sched.start_scheduler(interval_minutes=15)
        st_on = await sched.get_status()
        assert st_on["enabled"] is True
        assert st_on["config"]["interval_minutes"] == 15
        assert st_on["config"]["payload"]["batch_size"] == 5


# ─────────────────────────────────────────────────────────────────────
# Tick handler — every 15 min ⇒ exactly one cycle
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTickHandler:
    async def test_tick_calls_run_single_cycle_with_spec_defaults(
        self, fake_db, fake_run_cycle,
    ):
        await sched.start_scheduler()
        # Fish out the registered tick coroutine and execute it directly.
        s = sched._ensure_scheduler()
        tick = s._jobs["auto_discovery"].fn
        await tick()
        assert len(fake_run_cycle) == 1
        kw = fake_run_cycle[0]
        assert kw["batch_size"] == 5
        assert kw["quality_filter"] is True
        assert kw["quality_threshold"] == 55.0
        assert kw["timeout_seconds"] == 420.0

    async def test_tick_counts_skipped(self, fake_db, monkeypatch):
        async def _skipped(**_kw):
            return {"status": "skipped", "reason": "run_already_active"}
        monkeypatch.setattr(sched, "run_single_cycle", _skipped)
        await sched.start_scheduler()
        tick = sched._ensure_scheduler()._jobs["auto_discovery"].fn
        await tick()
        await tick()
        assert sched._runtime["tick_count"] == 2
        assert sched._runtime["skip_count"] == 2
        assert sched._runtime["last_status"] == "skipped"

    async def test_tick_counts_errors(self, fake_db, monkeypatch):
        async def _error(**_kw):
            return {"status": "error", "reason": "boom"}
        monkeypatch.setattr(sched, "run_single_cycle", _error)
        await sched.start_scheduler()
        tick = sched._ensure_scheduler()._jobs["auto_discovery"].fn
        await tick()
        assert sched._runtime["error_count"] == 1
        assert sched._runtime["last_status"] == "error"

    async def test_tick_swallows_unhandled_exceptions(self, fake_db, monkeypatch):
        """Tick must NEVER bubble exceptions — would kill the schedule."""
        async def _crash(**_kw):
            raise RuntimeError("kapow")
        monkeypatch.setattr(sched, "run_single_cycle", _crash)
        await sched.start_scheduler()
        tick = sched._ensure_scheduler()._jobs["auto_discovery"].fn
        await tick()  # must not raise
        assert sched._runtime["error_count"] == 1
        assert sched._runtime["last_status"] == "error"
        assert "kapow" in (sched._runtime["last_reason"] or "")


# ─────────────────────────────────────────────────────────────────────
# restore_if_enabled
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRestore:
    async def test_no_op_when_disabled(self, fake_db, fake_run_cycle):
        # Default config: enabled=False
        await sched.restore_if_enabled()
        assert sched._scheduler is None  # not started

    async def test_restarts_when_enabled(self, fake_db, fake_run_cycle):
        # Pre-seed config as enabled
        await sched._save_config(
            enabled=True, interval_minutes=10,
            payload={**sched.DEFAULT_PAYLOAD, "batch_size": 3},
        )
        await sched.restore_if_enabled()
        s = sched._ensure_scheduler()
        assert s.running is True
        assert "auto_discovery" in s._jobs


# ─────────────────────────────────────────────────────────────────────
# History plumb-through
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_status_includes_last_runs_history(fake_db, monkeypatch, fake_run_cycle):
    """`get_status()` should surface the last 20 cycle rows from
    `auto_run_cycles` so the UI doesn't need a second roundtrip."""

    async def _fake_history(limit):
        return [
            {"run_id": f"r{i}", "status": "completed", "pair": "EURUSD",
             "avg_pf": 1.5, "strategies_saved": 1}
            for i in range(min(int(limit), 7))
        ]
    monkeypatch.setattr(sched, "list_cycle_runs", _fake_history)

    await sched.start_scheduler()
    st = await sched.get_status()
    assert len(st["history"]) == 7
    assert st["history"][0]["run_id"] == "r0"

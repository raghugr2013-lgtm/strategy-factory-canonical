"""Phase 27.1 / G2 — Scheduler subordination tests.

Covers the additive subordination layer that lets ``auto_scheduler``
defer to ``orchestrator_scheduler`` when both are enabled.

Test surface:
  • Engine-level unit tests using monkeypatching (no real cycles, no
    external HTTP) — fast, deterministic, no shared global state leak
    because we restore ``_runtime`` + scheduler globals in teardown.
  • HTTP-level smoke covering the new ``subordinate_to_orchestrator``
    field in ``POST /api/auto/scheduler/start`` and the
    ``runtime.is_subordinated_now`` field in
    ``GET /api/auto/scheduler/status``. Mirrors the
    ``test_orchestrator_scheduler.py`` pattern.

Self-cleaning: every Mongo-touching test seeds with a clearly-scoped
config doc (``CONFIG_COLL = auto_scheduler_config`` is the single
source of truth) and resets it back to ``enabled=False`` in a
finally/teardown block.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict
from unittest.mock import patch

import pytest
import requests
from dotenv import load_dotenv

# Ensure backend is on the import path when run via plain pytest.
_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

load_dotenv("/app/backend/.env")

from engines import auto_scheduler as auto_sched          # noqa: E402
from engines import orchestrator_scheduler as orc_sched   # noqa: E402


# ──────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────

def _arun(coro):
    """Run an async coroutine synchronously, resetting motor's cached
    client between invocations so each call is bound to a fresh event
    loop. Mirrors the helper used in ``test_research_lineage_g1.py``."""
    try:
        from engines import db as db_mod
        for attr in ("_client", "_db", "_motor_client"):
            if hasattr(db_mod, attr):
                setattr(db_mod, attr, None)
    except Exception:
        pass
    return asyncio.run(coro)


def _reset_auto_runtime() -> None:
    """Restore the in-memory runtime dict to its module defaults so a
    test never sees state from a previous test."""
    auto_sched._runtime.update({
        "enabled":                False,
        "started_at":             None,
        "last_tick_at":           None,
        "last_status":            None,
        "last_reason":            None,
        "tick_count":             0,
        "skip_count":             0,
        "error_count":            0,
        "subordinate_skip_count": 0,
    })
    auto_sched._scheduler = None


def _reset_orc_runtime() -> None:
    orc_sched._runtime.update({
        "enabled":              False,
        "started_at":           None,
        "last_tick_at":         None,
        "tick_count":           0,
        "executed_count":       0,
        "advisory_count":       0,
        "last_recommendations": [],
        "last_executions":      [],
        "last_error":           None,
    })
    orc_sched._scheduler = None


@pytest.fixture(autouse=True)
def _isolate_module_state():
    """Snapshot + restore all module-level state every test."""
    _reset_auto_runtime()
    _reset_orc_runtime()
    yield
    _reset_auto_runtime()
    _reset_orc_runtime()


# ──────────────────────────────────────────────────────────────────────
# 1. orchestrator_scheduler.is_active() probe
# ──────────────────────────────────────────────────────────────────────

class TestOrchestratorIsActive:
    def test_returns_false_when_no_scheduler(self):
        # Cold-start: nothing wired up.
        assert orc_sched.is_active() is False

    def test_returns_false_when_scheduler_stopped(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        sched = AsyncIOScheduler(timezone="UTC")
        orc_sched._scheduler = sched
        orc_sched._runtime["enabled"] = True
        # Not started — running should be False.
        assert orc_sched.is_active() is False

    def test_returns_false_when_runtime_disabled(self):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        sched = AsyncIOScheduler(timezone="UTC")
        sched.add_job(lambda: None, trigger=IntervalTrigger(minutes=15),
                      id=orc_sched.JOB_ID, coalesce=True, max_instances=1)
        # Don't actually start to avoid leaking a running loop.
        orc_sched._scheduler = sched
        orc_sched._runtime["enabled"] = False
        assert orc_sched.is_active() is False


# ──────────────────────────────────────────────────────────────────────
# 2. auto_scheduler._is_subordinated()
# ──────────────────────────────────────────────────────────────────────

class TestIsSubordinated:
    def test_default_true_with_orchestrator_active(self):
        async def _go():
            with patch.object(auto_sched, "_load_config") as load_cfg, \
                 patch.object(orc_sched, "is_active", return_value=True):
                load_cfg.return_value = {
                    "enabled": True,
                    "interval_minutes": 15,
                    "subordinate_to_orchestrator": True,
                    "payload": dict(auto_sched.DEFAULT_PAYLOAD),
                }
                return await auto_sched._is_subordinated()
        assert _arun(_go()) is True

    def test_false_when_orchestrator_inactive(self):
        async def _go():
            with patch.object(auto_sched, "_load_config") as load_cfg, \
                 patch.object(orc_sched, "is_active", return_value=False):
                load_cfg.return_value = {
                    "enabled": True,
                    "interval_minutes": 15,
                    "subordinate_to_orchestrator": True,
                    "payload": dict(auto_sched.DEFAULT_PAYLOAD),
                }
                return await auto_sched._is_subordinated()
        assert _arun(_go()) is False

    def test_escape_hatch_when_subordinate_flag_off(self):
        # Orchestrator running, but operator opted into independent mode.
        async def _go():
            with patch.object(auto_sched, "_load_config") as load_cfg, \
                 patch.object(orc_sched, "is_active", return_value=True):
                load_cfg.return_value = {
                    "enabled": True,
                    "interval_minutes": 15,
                    "subordinate_to_orchestrator": False,   # escape hatch
                    "payload": dict(auto_sched.DEFAULT_PAYLOAD),
                }
                return await auto_sched._is_subordinated()
        assert _arun(_go()) is False

    def test_load_config_failure_falls_open(self):
        # Failures must not silently disable the scheduler.
        async def _go():
            with patch.object(auto_sched, "_load_config",
                              side_effect=RuntimeError("db down")):
                return await auto_sched._is_subordinated()
        assert _arun(_go()) is False


# ──────────────────────────────────────────────────────────────────────
# 3. _build_job tick semantics — subordinate skip vs run
# ──────────────────────────────────────────────────────────────────────

class TestTickSubordination:
    def test_tick_skips_when_subordinated(self):
        """Tick must not call run_single_cycle and must not open a
        research_run when the subordination probe returns True."""
        called: Dict[str, Any] = {"run_single_cycle": 0, "new_research_run": 0}

        async def _fake_run_single_cycle(*args, **kwargs):
            called["run_single_cycle"] += 1
            return {"status": "completed", "strategies_saved": 1, "pair": "EURUSD"}

        async def _fake_new_research_run(**kwargs):
            called["new_research_run"] += 1
            return "rr_fake_xxxxxxxx"

        async def _go():
            with patch.object(auto_sched, "_is_subordinated",
                              return_value=True), \
                 patch.object(auto_sched, "run_single_cycle",
                              side_effect=_fake_run_single_cycle), \
                 patch("engines.research_lineage.new_research_run",
                       side_effect=_fake_new_research_run):
                tick = auto_sched._build_job(
                    interval_minutes=15,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                )
                await tick()

        # Need to make _is_subordinated awaitable since it's async.
        async def _async_true():
            return True

        async def _go2():
            with patch.object(auto_sched, "_is_subordinated",
                              side_effect=_async_true), \
                 patch.object(auto_sched, "run_single_cycle",
                              side_effect=_fake_run_single_cycle), \
                 patch("engines.research_lineage.new_research_run",
                       side_effect=_fake_new_research_run):
                tick = auto_sched._build_job(
                    interval_minutes=15,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                )
                await tick()

        _arun(_go2())

        assert called["run_single_cycle"] == 0, \
            "subordinate tick must not run a discovery cycle"
        assert called["new_research_run"] == 0, \
            "subordinate tick must not pollute lineage"
        assert auto_sched._runtime["tick_count"] == 1
        assert auto_sched._runtime["subordinate_skip_count"] == 1
        assert auto_sched._runtime["last_status"] == "skipped_subordinate"
        assert auto_sched._runtime["last_reason"] == "orchestrator_scheduler_active"

    def test_tick_runs_when_not_subordinated(self):
        """Tick must invoke run_single_cycle as before when the
        orchestrator scheduler is not active."""
        called: Dict[str, Any] = {"run_single_cycle": 0}

        async def _async_false():
            return False

        async def _fake_run_single_cycle(*args, **kwargs):
            called["run_single_cycle"] += 1
            return {"status": "completed", "strategies_saved": 0,
                    "pair": "EURUSD", "reason": None}

        async def _fake_new_rr(**kwargs):
            return "rr_unit_test"

        async def _fake_mark_finished(rrid, **kwargs):
            return None

        async def _go():
            with patch.object(auto_sched, "_is_subordinated",
                              side_effect=_async_false), \
                 patch.object(auto_sched, "run_single_cycle",
                              side_effect=_fake_run_single_cycle), \
                 patch("engines.research_lineage.new_research_run",
                       side_effect=_fake_new_rr), \
                 patch("engines.research_lineage.mark_finished",
                       side_effect=_fake_mark_finished):
                tick = auto_sched._build_job(
                    interval_minutes=15,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                )
                await tick()

        _arun(_go())

        assert called["run_single_cycle"] == 1
        assert auto_sched._runtime["subordinate_skip_count"] == 0
        assert auto_sched._runtime["last_status"] == "completed"


# ──────────────────────────────────────────────────────────────────────
# 4. Config persistence — round-trip through Mongo
# ──────────────────────────────────────────────────────────────────────

class TestConfigPersistence:
    """Hits the real Mongo collection for the config doc. Self-cleaning."""

    def test_save_and_load_subordinate_flag(self):
        from engines.db import get_db

        async def _go():
            db = get_db()
            # Purge any pre-existing doc to guarantee a clean baseline.
            await db[auto_sched.CONFIG_COLL].delete_one({"_id": "discovery"})
            try:
                # Default load — fresh DB → SUBORDINATE_DEFAULT (True).
                cfg0 = await auto_sched._load_config()
                assert cfg0["subordinate_to_orchestrator"] is True
                # Persist explicit False (escape hatch).
                await auto_sched._save_config(
                    enabled=False,
                    interval_minutes=15,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                    subordinate_to_orchestrator=False,
                )
                cfg1 = await auto_sched._load_config()
                assert cfg1["subordinate_to_orchestrator"] is False
                # Subsequent save with subordinate_to_orchestrator=None
                # must NOT overwrite the persisted value.
                await auto_sched._save_config(
                    enabled=True,
                    interval_minutes=20,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                    subordinate_to_orchestrator=None,
                )
                cfg2 = await auto_sched._load_config()
                assert cfg2["subordinate_to_orchestrator"] is False, \
                    "None must not overwrite the persisted flag"
                assert cfg2["interval_minutes"] == 20
                # Flip back to True with explicit value.
                await auto_sched._save_config(
                    enabled=True,
                    interval_minutes=20,
                    payload=dict(auto_sched.DEFAULT_PAYLOAD),
                    subordinate_to_orchestrator=True,
                )
                cfg3 = await auto_sched._load_config()
                assert cfg3["subordinate_to_orchestrator"] is True
            finally:
                # Clean up our test doc so we don't pollute the install.
                await db[auto_sched.CONFIG_COLL].delete_one({"_id": "discovery"})

        _arun(_go())


# ──────────────────────────────────────────────────────────────────────
# 5. HTTP smoke through external ingress
# ──────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip()
                    break
    except OSError:
        pass
BASE_URL = (BASE_URL or "").rstrip("/")
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "admin123"


def _login_headers():
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


@pytest.fixture(scope="module")
def auth_headers():
    return _login_headers()


def _http_isolate(headers):
    """Helper used by the HTTP class autouse fixture — stops both
    schedulers around the suite."""
    requests.post(f"{BASE_URL}/api/auto/scheduler/stop",
                  headers=headers, timeout=15)
    requests.post(f"{BASE_URL}/api/orchestrator/scheduler/stop",
                  headers=headers, timeout=15)


class TestSubordinationHTTP:
    @pytest.fixture(autouse=True)
    def _isolate(self, auth_headers):
        _http_isolate(auth_headers)
        yield
        _http_isolate(auth_headers)

    def test_status_shape_includes_subordinate_fields(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auto/scheduler/status",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "config" in d and "runtime" in d
        # New keys land under config + runtime.
        assert "subordinate_to_orchestrator" in d["config"], \
            f"missing config.subordinate_to_orchestrator: {d['config']}"
        assert "is_subordinated_now" in d["runtime"]
        assert "subordinate_skip_count" in d["runtime"]

    def test_start_with_independent_mode(self, auth_headers):
        # Start with explicit subordinate=False (independent mode).
        r = requests.post(
            f"{BASE_URL}/api/auto/scheduler/start",
            json={"interval_minutes": 15,
                  "subordinate_to_orchestrator": False},
            headers=auth_headers, timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("subordinate_to_orchestrator") is False, body

        # Status reflects it.
        s = requests.get(f"{BASE_URL}/api/auto/scheduler/status",
                         headers=auth_headers, timeout=15).json()
        assert s["config"]["subordinate_to_orchestrator"] is False

        # Stop and re-start with subordinate=None — flag must persist.
        requests.post(f"{BASE_URL}/api/auto/scheduler/stop",
                      headers=auth_headers, timeout=15)
        r2 = requests.post(
            f"{BASE_URL}/api/auto/scheduler/start",
            json={"interval_minutes": 15},   # no subordinate field
            headers=auth_headers, timeout=15,
        )
        assert r2.status_code == 200
        # Inherit persisted value.
        assert r2.json().get("subordinate_to_orchestrator") is False

        # Flip back to subordinate (default behaviour).
        r3 = requests.post(
            f"{BASE_URL}/api/auto/scheduler/start",
            json={"interval_minutes": 15,
                  "subordinate_to_orchestrator": True},
            headers=auth_headers, timeout=15,
        )
        assert r3.status_code == 200
        assert r3.json().get("subordinate_to_orchestrator") is True

        # Cleanup
        requests.post(f"{BASE_URL}/api/auto/scheduler/stop",
                      headers=auth_headers, timeout=15)

    def test_subordinated_now_reflects_orchestrator_state(self, auth_headers):
        # Start auto-scheduler in default subordinate mode.
        r1 = requests.post(
            f"{BASE_URL}/api/auto/scheduler/start",
            json={"interval_minutes": 1440,   # large interval — no real ticks
                  "subordinate_to_orchestrator": True},
            headers=auth_headers, timeout=15,
        )
        assert r1.status_code == 200, r1.text

        # With orchestrator OFF, is_subordinated_now must be False.
        s = requests.get(f"{BASE_URL}/api/auto/scheduler/status",
                         headers=auth_headers, timeout=15).json()
        assert s["runtime"]["is_subordinated_now"] is False

        # Bring up the orchestrator scheduler.
        r2 = requests.post(
            f"{BASE_URL}/api/orchestrator/scheduler/start",
            json={"interval_minutes": 1440},
            headers=auth_headers, timeout=15,
        )
        assert r2.status_code == 200, r2.text

        # Now is_subordinated_now must flip to True.
        s2 = requests.get(f"{BASE_URL}/api/auto/scheduler/status",
                          headers=auth_headers, timeout=15).json()
        assert s2["runtime"]["is_subordinated_now"] is True, \
            f"expected subordination active when orchestrator is on; got {s2['runtime']}"

        # Cleanup
        requests.post(f"{BASE_URL}/api/orchestrator/scheduler/stop",
                      headers=auth_headers, timeout=15)
        requests.post(f"{BASE_URL}/api/auto/scheduler/stop",
                      headers=auth_headers, timeout=15)

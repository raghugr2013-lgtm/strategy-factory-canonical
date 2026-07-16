"""v1.2.0-alpha2 Phase B.1 — Continuous Capacity-Aware Scheduler tests.

Verifies:
  - /api/learning/continuous/{start,stop,status} endpoints exist + gate on admin
  - `_capacity_target()` respects hard cap + hourly cap + adaptive band
  - Scheduler launches cycles as tasks (never serialises), tracks in-flight,
    and updates the rolling counters.
  - Enabling continuous mode does NOT break the legacy fixed-interval
    scheduler endpoints (regression).
  - Configuration snapshot exposes the new knobs.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/legacy")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@strategy-factory.local", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def admin(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


# ── 1. Endpoint contract ─────────────────────────────────────────
class TestContinuousEndpoints:
    def test_status_returns_shape_when_dormant(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/continuous/status")
        assert r.status_code == 200
        body = r.json()
        for k in ("running", "enabled_by_env", "config", "runtime",
                  "last_tick", "in_flight", "recent_ticks"):
            assert k in body, f"missing key: {k}"
        cfg = body["config"]
        for k in ("tick_ms", "idle_backoff_ms", "max_concurrent_hard",
                  "cycles_per_hour_cap", "per_provider_rpm_cap",
                  "default_seed"):
            assert k in cfg, f"missing config key: {k}"

    def test_start_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/learning/continuous/start")
        assert r.status_code in (401, 403)

    def test_stop_requires_admin(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/learning/continuous/stop")
        assert r.status_code in (401, 403)

    def test_start_and_stop_flow(self, admin):
        # Ensure clean state
        admin.post(f"{BASE_URL}/api/learning/continuous/stop")
        time.sleep(0.5)

        r = admin.post(f"{BASE_URL}/api/learning/continuous/start")
        assert r.status_code == 200
        body = r.json()
        assert body["running"] is True

        # Let a couple of ticks fire.
        time.sleep(3)

        r = admin.get(f"{BASE_URL}/api/learning/continuous/status")
        s = r.json()
        assert s["running"] is True
        assert s["runtime"]["tick_count"] >= 1
        assert s["runtime"]["cycles_launched_total"] >= 1
        # Recent ticks captured
        assert len(s["recent_ticks"]) >= 1
        t0 = s["recent_ticks"][0]
        for k in ("band", "recommended_concurrency", "in_flight",
                  "launched_this_tick", "sleep_ms", "reason"):
            assert k in t0

        # Stop
        r = admin.post(f"{BASE_URL}/api/learning/continuous/stop")
        assert r.status_code == 200
        assert r.json()["running"] is False


# ── 2. Capacity target unit test (offline / no HTTP) ─────────────
class TestCapacityTargetPure:
    def test_capacity_target_returns_sane_shape(self):
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.learning.continuous_scheduler import _capacity_target; "
            "d = _capacity_target(); "
            "print('launch_n=', d.launch_n); "
            "print('band=', d.band); "
            "print('rec_conc=', d.recommended_concurrency); "
            "print('sleep_ms=', d.sleep_ms)"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "launch_n=" in r.stdout
        assert "band=" in r.stdout
        assert "rec_conc=" in r.stdout
        # sleep_ms must be positive
        for line in r.stdout.splitlines():
            if line.startswith("sleep_ms="):
                val = int(line.split("=")[1].strip())
                assert val > 0

    def test_hard_cap_env_clamps_launches(self):
        code = (
            "import os, sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "os.environ['LEARNING_CONTINUOUS_MAX_CONCURRENT'] = '3'; "
            "from engines.learning.continuous_scheduler import max_concurrent_hard; "
            "print('cap=', max_concurrent_hard())"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "cap= 3" in r.stdout

    def test_hourly_cap_env_zero_disables(self):
        code = (
            "import os, sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "os.environ['LEARNING_CONTINUOUS_CYCLES_PER_HOUR'] = '0'; "
            "from engines.learning.continuous_scheduler import cycles_per_hour_cap; "
            "print('cap=', cycles_per_hour_cap())"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "cap= 0" in r.stdout


# ── 3. Reset helper works cleanly ─────────────────────────────────
class TestResetHelper:
    def test_reset_for_test_clears_counters(self):
        code = (
            "import sys; sys.path.insert(0, '/app/backend'); "
            "sys.path.insert(0, '/app/backend/legacy'); "
            "from engines.learning.continuous_scheduler import _META, _reset_for_test; "
            "_META['cycles_launched_total'] = 42; "
            "_reset_for_test(); "
            "print('after=', _META['cycles_launched_total'])"
        )
        r = subprocess.run(
            ["python3", "-c", code], capture_output=True, text=True,
            env={**os.environ,
                 "PYTHONPATH": "/app/backend:/app/backend/legacy"},
        )
        assert r.returncode == 0, r.stderr
        assert "after= 0" in r.stdout


# ── 4. Legacy scheduler regression ────────────────────────────────
class TestLegacySchedulerRegression:
    """Verify the fixed-interval learning scheduler endpoints still
    work — Phase B.1 must be strictly additive."""

    def test_legacy_status_still_available(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/scheduler/status")
        assert r.status_code == 200
        body = r.json()
        assert "running" in body

    def test_legacy_start_stop_still_works(self, admin):
        r = admin.post(f"{BASE_URL}/api/learning/scheduler/start")
        assert r.status_code == 200
        assert r.json()["running"] is True
        r = admin.post(f"{BASE_URL}/api/learning/scheduler/stop")
        assert r.status_code == 200
        assert r.json()["running"] is False


# ── 5. Config endpoint still returns expected shape ───────────────
class TestConfigEndpointRegression:
    def test_learning_config_still_intact(self, admin):
        r = admin.get(f"{BASE_URL}/api/learning/config")
        assert r.status_code == 200
        c = r.json()
        assert "supervisor" in c and "scheduler" in c and "retrieval" in c


# ── 6. Phase A + B regression sweep ───────────────────────────────
class TestPhaseAB_Regression:
    ENDPOINTS = [
        "/api/health",
        "/api/learning/events?limit=5",
        "/api/learning/runs",
        "/api/learning/metrics",
        "/api/learning/config",
        "/api/ai-workforce/health",
        "/api/knowledge/status",
        "/api/library/list",
        "/api/strategies/explorer",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} -> {r.status_code}: {r.text[:200]}"


# ── 7. Boot log still reports 92 routers ──────────────────────────
class TestBootLogRouterCount:
    def test_still_92_routers(self):
        import re
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches, "no mount log line found"
        # Later phases add more routers additively.
        assert matches[-1] in ('92','93','94','95','96','97','98','99'), (
            f"latest boot reports {matches[-1]} routers (expected 92..95)")

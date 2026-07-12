"""
Phase 22 — Orchestrator scheduler + tick endpoint tests.

Covers:
  - GET  /api/orchestrator/scheduler/status
  - POST /api/orchestrator/scheduler/start (15, 30, invalid)
  - POST /api/orchestrator/scheduler/stop
  - POST /api/orchestrator/tick (preview, execute, cooldown_skip, advisory not rate-limited)
  - Regression: /api/orchestrator/state, /api/orchestrator/decide, /api/auto/scheduler/status
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fallback to frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def auth_headers():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    token = r.json().get("access_token") or r.json().get("token")
    if not token:
        pytest.skip(f"No token in login response: {r.json()}")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def reset_scheduler(auth_headers):
    """Stop scheduler before tests so we start from a clean slate."""
    requests.post(f"{BASE_URL}/api/orchestrator/scheduler/stop", headers=auth_headers, timeout=15)
    yield
    requests.post(f"{BASE_URL}/api/orchestrator/scheduler/stop", headers=auth_headers, timeout=15)


# ── /scheduler/status ───────────────────────────────────────────────

class TestSchedulerStatus:
    def test_status_shape(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/orchestrator/scheduler/status",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("enabled", "interval_minutes", "tick_count",
                  "executed_count", "advisory_count", "cooldown"):
            assert k in d, f"missing key {k}: {d}"
        assert isinstance(d["cooldown"], dict)
        assert "seconds" in d["cooldown"] and "remaining" in d["cooldown"]
        assert d["cooldown"]["seconds"] == 120


# ── /scheduler/start, /stop ──────────────────────────────────────────

class TestSchedulerLifecycle:
    def test_start_default_15(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/scheduler/start",
                          json={"interval_minutes": 15},
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("enabled") is True
        assert body.get("interval_minutes") == 15

        # GET status reflects the change
        s = requests.get(f"{BASE_URL}/api/orchestrator/scheduler/status",
                         headers=auth_headers, timeout=15).json()
        assert s["enabled"] is True
        assert s["interval_minutes"] == 15
        assert s.get("next_run_at"), "next_run_at should be populated when enabled"

    def test_start_idempotent_replace_30(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/scheduler/start",
                          json={"interval_minutes": 30},
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["interval_minutes"] == 30

        s = requests.get(f"{BASE_URL}/api/orchestrator/scheduler/status",
                         headers=auth_headers, timeout=15).json()
        assert s["interval_minutes"] == 30
        assert s["enabled"] is True

    def test_start_invalid_zero(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/scheduler/start",
                          json={"interval_minutes": 0},
                          headers=auth_headers, timeout=15)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_start_invalid_too_big(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/scheduler/start",
                          json={"interval_minutes": 9999},
                          headers=auth_headers, timeout=15)
        assert r.status_code == 422

    def test_stop_disables(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/scheduler/stop",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["enabled"] is False

        s = requests.get(f"{BASE_URL}/api/orchestrator/scheduler/status",
                         headers=auth_headers, timeout=15).json()
        assert s["enabled"] is False


# ── /tick (preview / execute / cooldown) ─────────────────────────────

class TestOrchestratorTick:
    def test_tick_preview(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/tick",
                          json={"execute": False},
                          headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("status") == "preview"
        assert d.get("executed") is False
        assert "recommendations" in d and isinstance(d["recommendations"], list)

    def test_advisory_not_rate_limited(self, auth_headers):
        # multiple advisory back-to-back should all succeed (no cooldown)
        for _ in range(3):
            r = requests.post(f"{BASE_URL}/api/orchestrator/tick",
                              json={"execute": False},
                              headers=auth_headers, timeout=60)
            assert r.status_code == 200
            assert r.json().get("status") == "preview"

    def test_tick_execute_then_cooldown(self, auth_headers):
        # 1st execute should run (status=executed, executed=true)
        r1 = requests.post(f"{BASE_URL}/api/orchestrator/tick",
                           json={"execute": True},
                           headers=auth_headers, timeout=120)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        # Either fresh (executed) or already-cooled-down from a prior test run.
        assert d1.get("status") in ("executed", "cooldown_skip")

        # 2nd execute within 120s should be cooldown_skip
        r2 = requests.post(f"{BASE_URL}/api/orchestrator/tick",
                           json={"execute": True},
                           headers=auth_headers, timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("status") == "cooldown_skip"
        assert d2.get("executed") is False
        assert d2.get("cooldown_seconds") == 120
        assert d2.get("seconds_remaining", 0) > 0


# ── Regression: existing endpoints still work ────────────────────────

class TestRegression:
    def test_orchestrator_state(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/orchestrator/state",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "state" in d

    def test_orchestrator_decide(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/orchestrator/decide",
                          headers=auth_headers, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert "recommendations" in d
        assert d.get("executed") is False

    def test_auto_scheduler_status_unaffected(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auto/scheduler/status",
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Module exists and returns shape
        assert isinstance(d, dict)

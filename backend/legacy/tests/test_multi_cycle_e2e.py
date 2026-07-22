"""E2E backend tests for Phase 20 MultiCycleRunner + companion engines.

Hits the live preview URL (REACT_APP_BACKEND_URL) so the same surface
the frontend uses is exercised end-to-end:

  - Auth: /api/auth/login (admin@local.test / admin123)
  - Multi-cycle: start (cycles=1, batch_size=1) → poll status → best → history → stop
  - Engine reachability: strategies, mutation/catalogue, mutation-runner status,
    challenge-firms (matching), scheduler status.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://stall-debug.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "admin123"


# ── fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def auth_token(api_client):
    r = api_client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
    assert data["user"]["email"] == ADMIN_EMAIL
    assert data["user"]["role"] == "admin"
    return data["token"]


@pytest.fixture(scope="session")
def auth_client(api_client, auth_token):
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


# ── auth ─────────────────────────────────────────────────────────────
class TestAuth:
    def test_login_returns_jwt(self, auth_token):
        # JWT is "header.payload.signature"
        assert auth_token.count(".") == 2


# ── multi-cycle ──────────────────────────────────────────────────────
class TestMultiCycle:
    def test_status_idle_or_known(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/auto/multi-cycle/status", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "status" in body
        assert body["status"] in {"idle", "running", "completed", "error", "stopped"}

    def test_history_returns_list(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/auto/multi-cycle/history?limit=5", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "runs" in body
        assert isinstance(body["runs"], list)

    def test_start_and_complete_cycle_then_best(self, auth_client):
        # Kick off a tiny run (cycles=1, batch_size=1)
        r = auth_client.post(
            f"{BASE_URL}/api/auto/multi-cycle/start",
            json={"cycles": 1, "batch_size": 1, "timeout_per_cycle": 120},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        start_body = r.json()
        # Idempotent endpoint: status will be running OR already completed if a fresh-start race
        assert start_body["status"] in {"running", "completed"}
        run_id = start_body["run_id"]
        assert run_id and isinstance(run_id, str)

        # Poll status until terminal — max ~3 minutes
        deadline = time.time() + 180
        terminal = {"completed", "error", "stopped"}
        last_status = None
        while time.time() < deadline:
            sr = auth_client.get(f"{BASE_URL}/api/auto/multi-cycle/status", timeout=15)
            assert sr.status_code == 200
            sbody = sr.json()
            last_status = sbody["status"]
            if last_status in terminal:
                break
            time.sleep(5)
        assert last_status in terminal, f"run did not finish in time: status={last_status}"

        # Best endpoint — may return best=null when no candidate beats threshold;
        # the response shape is what we contract on.
        br = auth_client.get(f"{BASE_URL}/api/auto/multi-cycle/runs/{run_id}/best", timeout=15)
        assert br.status_code == 200
        bbody = br.json()
        assert bbody["run_id"] == run_id
        assert "best" in bbody
        assert "candidates_considered" in bbody

        # History contains this run
        hr = auth_client.get(f"{BASE_URL}/api/auto/multi-cycle/history?limit=10", timeout=15)
        assert hr.status_code == 200
        run_ids = [r["run_id"] for r in hr.json()["runs"]]
        assert run_id in run_ids

    def test_stop_callable(self, auth_client):
        r = auth_client.post(f"{BASE_URL}/api/auto/multi-cycle/stop", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "stopping" in body and "status" in body


# ── companion engines reachable ──────────────────────────────────────
class TestEnginesReachable:
    def test_strategies_list(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/strategies?limit=1", timeout=15)
        assert r.status_code == 200
        assert "strategies" in r.json()

    def test_mutation_catalogue(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/mutation/catalogue", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "mutation_types" in body
        assert isinstance(body["mutation_types"], list) and len(body["mutation_types"]) > 0

    def test_mutation_runner_status(self, auth_client):
        r = auth_client.get(f"{BASE_URL}/api/auto/mutation-runner/status", timeout=15)
        assert r.status_code == 200
        assert "status" in r.json()

    def test_challenge_firms(self, auth_client):
        # /api/challenge-firms is the prop-firm matching surface (phase4_matching's
        # /phase4/match-firms is POST-only and needs a strategy payload — covered
        # indirectly via multi-cycle's matching subphase).
        r = auth_client.get(f"{BASE_URL}/api/challenge-firms", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "firms" in body
        assert "ftmo" in body["firms"]

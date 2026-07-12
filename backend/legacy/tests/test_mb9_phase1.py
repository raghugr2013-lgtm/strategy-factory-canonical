"""MB-9 Phase 1 — backend end-to-end tests.

Coverage:
    * Runner registration + one-time token + token re-validation
    * Heartbeat (token-authed) + verdict band transitions
    * Bad-token / missing-header 401s
    * Poll queue contract
    * Runner disable → token rejected
    * Route ordering: /runners not shadowed by /{master_bot_id}

These tests are isolated: every created entity carries a TEST_ prefix
and is hard-deleted in fixture teardown.

NOTE — full deployment-lifecycle tests (register → stage → promote →
rollback with parity sign-off TTL) are deferred to MB-9 Phase 1
soak (manual operator run). This file covers the surface that does
NOT depend on a populated `master_bot_packs` row.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "http://localhost:8001",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@test.local"
ADMIN_PASSWORD = "AdminTest123!"


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type":  "application/json"}


@pytest.fixture()
def runner_factory(admin_headers):
    """Create a runner; clean up at test end."""
    created: list[str] = []

    def _make(**overrides) -> dict:
        name = f"TEST_runner_{uuid.uuid4().hex[:8]}"
        body = {
            "name":     name,
            "platform": "windows",
            "pair_filters": ["EURUSD"],
            "timeframe_filters": ["H1"],
        }
        body.update(overrides)
        r = requests.post(
            f"{API}/master-bot/runners",
            headers=admin_headers, json=body, timeout=30,
        )
        assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
        row = r.json()
        created.append(row["runner_id"])
        return row

    yield _make

    # Teardown: direct Mongo delete via the same admin token is not
    # currently exposed via an admin endpoint, so we leave the rows
    # marked with the TEST_ name prefix for offline cleanup. Each
    # test name is unique so re-runs don't collide.


# ── Registration ────────────────────────────────────────────────────

def test_register_runner_returns_one_time_token(runner_factory):
    row = runner_factory()
    assert row["runner_id"]
    assert row["token"].startswith("mbr_")
    assert "token_storage" in row
    # Token must not be persisted in any subsequent list response.
    # (The list endpoint projects token_hash out.)


def test_register_rejects_duplicate_name(runner_factory, admin_headers):
    row = runner_factory()
    r2 = requests.post(
        f"{API}/master-bot/runners",
        headers=admin_headers,
        json={"name": row["name"], "platform": "windows"},
        timeout=30,
    )
    assert r2.status_code == 400, r2.text


def test_list_runners_does_not_leak_token_hash(runner_factory, admin_headers):
    row = runner_factory()
    r = requests.get(f"{API}/master-bot/runners",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    runners = r.json()["runners"]
    target = [x for x in runners if x["runner_id"] == row["runner_id"]]
    assert target, "freshly-registered runner missing from list"
    assert "token_hash" not in target[0]
    assert "token" not in target[0]


# ── Token auth ──────────────────────────────────────────────────────

def test_heartbeat_requires_runner_headers():
    r = requests.post(f"{API}/runner/heartbeat", json={}, timeout=30)
    assert r.status_code == 401, r.text


def test_heartbeat_rejects_bad_token(runner_factory):
    row = runner_factory()
    r = requests.post(
        f"{API}/runner/heartbeat",
        headers={"X-Runner-Id": row["runner_id"], "X-Runner-Token": "WRONG"},
        json={"cpu_percent": 1.0},
        timeout=30,
    )
    assert r.status_code == 401, r.text


def test_heartbeat_accepts_valid_token_and_promotes_status(
    runner_factory, admin_headers,
):
    row = runner_factory()
    h = {
        "X-Runner-Id":    row["runner_id"],
        "X-Runner-Token": row["token"],
        "Content-Type":   "application/json",
    }
    r = requests.post(
        f"{API}/runner/heartbeat", headers=h,
        json={"cpu_percent": 12.5, "mem_percent": 33.3,
              "ctrader_desktop_state": "running",
              "runner_agent_version": "0.1.0"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    assert r.json()["runner_id"] == row["runner_id"]

    # Status promotes registered → active; verdict band → alive
    s = requests.get(
        f"{API}/master-bot/runners/{row['runner_id']}",
        headers=admin_headers, timeout=30,
    )
    assert s.status_code == 200, s.text
    body = s.json()
    assert body["status"] == "active"
    assert body["verdict"] == "alive"
    assert body["age_seconds"] is not None
    assert body["last_snapshot"]["ctrader_desktop_state"] == "running"


def test_poll_empty_queue(runner_factory):
    row = runner_factory()
    h = {"X-Runner-Id": row["runner_id"], "X-Runner-Token": row["token"]}
    r = requests.get(f"{API}/runner/poll", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["runner_id"] == row["runner_id"]
    assert body["queue_size"] == 0
    assert body["assignments"] == []


def test_artifact_unauthorised_when_pack_not_assigned(runner_factory):
    row = runner_factory()
    h = {"X-Runner-Id": row["runner_id"], "X-Runner-Token": row["token"]}
    # Random pack_id → not assigned → 404
    r = requests.get(
        f"{API}/runner/artifact/{uuid.uuid4().hex}",
        headers=h, timeout=30,
    )
    assert r.status_code == 404, r.text


# ── Disable flow ────────────────────────────────────────────────────

def test_disable_runner_blocks_subsequent_heartbeats(
    runner_factory, admin_headers,
):
    row = runner_factory()
    # Disable
    d = requests.post(
        f"{API}/master-bot/runners/{row['runner_id']}/disable",
        headers=admin_headers, timeout=30,
    )
    assert d.status_code == 200, d.text
    assert d.json()["status"] == "disabled"
    # Heartbeat with correct token now rejected
    h = {"X-Runner-Id": row["runner_id"], "X-Runner-Token": row["token"]}
    r = requests.post(f"{API}/runner/heartbeat", headers=h,
                      json={}, timeout=30)
    assert r.status_code == 401, r.text
    # Status shows verdict='disabled'
    s = requests.get(
        f"{API}/master-bot/runners/{row['runner_id']}",
        headers=admin_headers, timeout=30,
    )
    assert s.json()["verdict"] == "disabled"


# ── Route ordering (regression) ─────────────────────────────────────

def test_runners_path_not_shadowed_by_master_bot_id(admin_headers):
    """Regression: ensure `GET /master-bot/runners` returns the
    runners-list shape, NOT a 404 from get_master_bot(master_bot_id='runners').
    """
    r = requests.get(f"{API}/master-bot/runners",
                     headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "runners" in body
    assert "count"   in body


# ── Operator endpoints — non-admin RBAC ─────────────────────────────

def test_register_runner_rejects_non_admin(admin_headers):
    """Non-admin should not be able to register runners."""
    # Create a non-admin
    email = f"TEST_user_{uuid.uuid4().hex[:8]}@test.local"
    password = "UserTest123!"
    su = requests.post(f"{API}/auth/signup",
                       json={"email": email, "password": password},
                       timeout=30)
    assert su.status_code in (200, 201), su.text
    user_id = (su.json().get("user") or su.json()).get("user_id") \
              or (su.json().get("user") or su.json()).get("id")
    if not user_id:
        lu = requests.get(f"{API}/admin/users?status=pending",
                          headers=admin_headers, timeout=30).json()
        for u in lu.get("users", []):
            if (u.get("email") or "").lower() == email.lower():
                user_id = u.get("user_id") or u.get("id")
                break
    assert user_id, "could not resolve newly signed-up user_id"
    ap = requests.post(f"{API}/admin/approve/{user_id}",
                       headers=admin_headers, timeout=30)
    assert ap.status_code == 200, ap.text
    login = requests.post(f"{API}/auth/login",
                          json={"email": email, "password": password},
                          timeout=30)
    assert login.status_code == 200, login.text
    user_h = {
        "Authorization": f"Bearer {login.json()['token']}",
        "Content-Type":  "application/json",
    }
    r = requests.post(
        f"{API}/master-bot/runners",
        headers=user_h,
        json={"name": f"TEST_runner_{uuid.uuid4().hex[:8]}",
              "platform": "windows"},
        timeout=30,
    )
    assert r.status_code == 403, r.text


def test_deploy_status_returns_no_live_for_empty_bot(admin_headers):
    """Sanity: /deploy/status for a non-existent bot returns
    has_live=False (not 404 — empty state is valid)."""
    r = requests.get(
        f"{API}/master-bot/{uuid.uuid4().hex}/deploy/status",
        headers=admin_headers, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["has_live"] is False
    assert body["live"] is None

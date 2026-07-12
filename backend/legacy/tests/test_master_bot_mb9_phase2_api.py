"""MB-9 Phase 2.B — admin API integration smoke.

End-to-end coverage of the 11 new admin-gated routes wired in
``api/master_bot.py``. Uses HTTP against the running supervisor
backend (REACT_APP_BACKEND_URL or localhost:8001) with the admin
credentials seeded from ``.env`` (ADMIN_EMAIL / ADMIN_PASSWORD).

Conventions
-----------
  * Every entity created carries a TEST_ prefix and is hard-deleted
    in a fixture teardown — no orphans.
  * Skips with a clear message when the backend is unreachable so
    the suite degrades gracefully in offline CI.
  * No environment flags are flipped — defaults only. Phase 2.B
    behaviour must be exercisable without flipping any Phase 2 flag.
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

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@strategyfactory.dev")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


# ── Health gate ──────────────────────────────────────────────────────

def _backend_reachable() -> bool:
    try:
        r = requests.get(f"{API}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_reachable(),
    reason="backend not reachable on localhost:8001",
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(
            f"admin login failed ({r.status_code}); admin not seeded with "
            f".env credentials {ADMIN_EMAIL!r}: {r.text[:200]}"
        )
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(admin_token) -> dict:
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type":  "application/json"}


@pytest.fixture()
def runner_row(H):
    name = f"TEST_p2b_{uuid.uuid4().hex[:8]}"
    r = requests.post(
        f"{API}/master-bot/runners",
        headers=H,
        json={"name": name, "platform": "windows",
              "pair_filters": ["EURUSD"], "timeframe_filters": ["H1"]},
        timeout=15,
    )
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    row = r.json()
    yield row
    # Disable + sweep accounts.
    try:
        requests.post(
            f"{API}/master-bot/runners/{row['runner_id']}/disable",
            headers=H, timeout=15,
        )
    except Exception:
        pass
    from engines.db import get_db
    from engines import multi_account_envelope as mae
    from engines import runner_registry as runners
    import asyncio
    async def _cleanup():
        db = get_db()
        await db[mae.ACCOUNTS_COLL].delete_many({"runner_id": row["runner_id"]})
        await db[runners.RUNNERS_COLL].delete_one({"runner_id": row["runner_id"]})
    asyncio.get_event_loop().run_until_complete(_cleanup())


# ── 1. /runners/route-preview ────────────────────────────────────────

def test_route_preview_returns_decision(H, runner_row):
    r = requests.get(
        f"{API}/master-bot/runners/route-preview",
        headers=H, params={"pair": "EURUSD", "timeframe": "H1"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pair"] == "EURUSD"
    assert body["timeframe"] == "H1"
    assert "decision" in body
    assert "runner_id" in body["decision"] or "reason" in body["decision"]


def test_route_preview_rejects_non_admin():
    # No Authorization header.
    r = requests.get(
        f"{API}/master-bot/runners/route-preview",
        params={"pair": "EURUSD", "timeframe": "H1"},
        timeout=15,
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


def test_route_preview_accepts_policy_override(H, runner_row):
    r = requests.get(
        f"{API}/master-bot/runners/route-preview",
        headers=H,
        params={"pair": "EURUSD", "timeframe": "H1", "policy": "least_busy"},
        timeout=15,
    )
    assert r.status_code == 200
    assert r.json()["policy_override"] == "least_busy"


# ── 2. /runners/fleet ────────────────────────────────────────────────

def test_runners_fleet_snapshot(H, runner_row):
    r = requests.get(f"{API}/master-bot/runners/fleet",
                     headers=H, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "active_policy" in body
    assert body["active_policy"] in (
        "sticky_pair_tf", "least_busy", "round_robin", "local_only",
    )
    assert "multi_account_enabled" in body
    # By default multi-account is OFF; flag-OFF byte-identical preserved.
    assert body["multi_account_enabled"] is False
    assert any(r["runner_id"] == runner_row["runner_id"] for r in body["runners"])


# ── 3. /runners/{id}/rotate-token (+ expire-old + state inspect) ─────

def test_rotate_token_starts_grace_window(H, runner_row):
    rid = runner_row["runner_id"]
    r = requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token",
        headers=H, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "new_token" in body
    assert body["new_token"] and len(body["new_token"]) >= 16
    assert body["token_rotation_state"] == "rotating"
    # State inspector now reports grace window active.
    g = requests.get(f"{API}/master-bot/runners/{rid}/rotate-token",
                     headers=H, timeout=15)
    assert g.status_code == 200
    assert g.json()["grace_window_active"] is True
    # Double-start should 409.
    r2 = requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token",
        headers=H, timeout=15,
    )
    assert r2.status_code == 409, r2.text


def test_rotate_token_expire_old_completes_rotation(H, runner_row):
    rid = runner_row["runner_id"]
    requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token",
        headers=H, timeout=15,
    )
    r = requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token/expire-old",
        headers=H, timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_rotation_state"] == "active"
    # Expire-old with no active rotation → 409.
    r2 = requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token/expire-old",
        headers=H, timeout=15,
    )
    assert r2.status_code == 409


def test_rotate_token_rejects_unknown_runner(H):
    r = requests.post(
        f"{API}/master-bot/runners/runner_does_not_exist/rotate-token",
        headers=H, timeout=15,
    )
    assert r.status_code == 409


# ── 4. /runners/{id}/accounts (GET, POST, DELETE) ────────────────────

def test_account_list_returns_synthetic_legacy_row_when_flag_off(H, runner_row):
    """With RUNNER_MULTI_ACCOUNT_ENABLED=false the engine synthesises
    a single legacy row even though the collection is empty."""
    rid = runner_row["runner_id"]
    r = requests.get(
        f"{API}/master-bot/runners/{rid}/accounts",
        headers=H, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["multi_account_enabled"] is False
    assert body["count"] >= 1
    accs = body["accounts"]
    # Legacy account_id constant.
    from engines import multi_account_envelope as mae
    assert any(a.get("account_id") == mae.LEGACY_ACCOUNT_ID for a in accs)


def test_account_list_raw_bypasses_synthetic_row(H, runner_row):
    rid = runner_row["runner_id"]
    r = requests.get(
        f"{API}/master-bot/runners/{rid}/accounts",
        headers=H, params={"raw": "true"}, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["raw"] is True
    # Fresh runner has no rows in collection yet → count 0.
    assert body["count"] == 0


def test_account_add_then_delete_roundtrip(H, runner_row):
    rid = runner_row["runner_id"]
    acc_id = f"ACC_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{API}/master-bot/runners/{rid}/accounts",
        headers=H,
        json={"account_id": acc_id, "broker": "ctrader",
              "credentials_envelope": "envelope-bytes-XYZ"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == acc_id
    assert body["credentials_envelope_hash"].startswith("sha256:")
    # Duplicate → 409.
    r2 = requests.post(
        f"{API}/master-bot/runners/{rid}/accounts",
        headers=H,
        json={"account_id": acc_id, "broker": "ctrader"},
        timeout=15,
    )
    assert r2.status_code == 409
    # Delete.
    rd = requests.delete(
        f"{API}/master-bot/runners/{rid}/accounts/{acc_id}",
        headers=H, timeout=15,
    )
    assert rd.status_code == 200
    # Re-delete → 404.
    rd2 = requests.delete(
        f"{API}/master-bot/runners/{rid}/accounts/{acc_id}",
        headers=H, timeout=15,
    )
    assert rd2.status_code == 404


def test_account_add_rejects_unknown_runner(H):
    r = requests.post(
        f"{API}/master-bot/runners/unknown_runner_xyz/accounts",
        headers=H, json={"account_id": "ACC_X"}, timeout=15,
    )
    assert r.status_code in (400, 404, 409)


# ── 5. /deployments/parity-drift (all + per-deployment) ──────────────

def test_parity_drift_all_returns_envelope(H):
    r = requests.get(f"{API}/master-bot/deployments/parity-drift",
                     headers=H, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Engine returns a stable envelope shape regardless of population.
    assert "deployments" in body or "count" in body or "window_days" in body


def test_parity_drift_unknown_deployment_returns_insufficient_data(H):
    r = requests.get(
        f"{API}/master-bot/deployments/parity-drift/dep_does_not_exist",
        headers=H, timeout=15,
    )
    # Honest refusal — never blocks, always 200 with decision verdict.
    assert r.status_code == 200, r.text
    body = r.json()
    assert "decision" in body
    assert body["decision"] in (
        "insufficient_data", "not_found", "no_signoffs",
        "deployment_not_found",
    ), f"unexpected verdict {body['decision']!r}"


# ── 6. /runners/accounts/migrate-legacy + /migration-status ──────────

def test_migrate_legacy_idempotent(H, runner_row):
    r1 = requests.post(
        f"{API}/master-bot/runners/accounts/migrate-legacy",
        headers=H, timeout=30,
    )
    assert r1.status_code == 200
    r2 = requests.post(
        f"{API}/master-bot/runners/accounts/migrate-legacy",
        headers=H, timeout=30,
    )
    assert r2.status_code == 200
    rid = runner_row["runner_id"]
    # First call inserted the legacy row for the test runner;
    # second call must report it under 'already'.
    body2 = r2.json()
    assert rid not in body2["inserted"]
    assert rid in body2["already"]


def test_migration_status_endpoint(H):
    r = requests.get(
        f"{API}/master-bot/runners/accounts/migration-status",
        headers=H, timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    for k in ("total_runners", "active_runners", "legacy_account_rows"):
        assert k in body


# ── 7. Admin-gate regression on mutators ─────────────────────────────

def test_all_mutators_require_admin():
    """No bearer header → 401/403 on every Phase 2.B mutator."""
    targets = [
        ("POST",   "/master-bot/runners/x/rotate-token"),
        ("POST",   "/master-bot/runners/x/rotate-token/expire-old"),
        ("POST",   "/master-bot/runners/x/accounts"),
        ("DELETE", "/master-bot/runners/x/accounts/y"),
        ("POST",   "/master-bot/runners/accounts/migrate-legacy"),
        ("GET",    "/master-bot/runners/accounts/migration-status"),
        ("GET",    "/master-bot/runners/fleet"),
        ("GET",    "/master-bot/runners/route-preview?pair=EURUSD&timeframe=H1"),
    ]
    for method, path in targets:
        r = requests.request(
            method, f"{API}{path}",
            json={"account_id": "x"} if method == "POST" else None,
            timeout=15,
        )
        assert r.status_code in (401, 403), (
            f"{method} {path} expected 401/403, got {r.status_code}"
        )

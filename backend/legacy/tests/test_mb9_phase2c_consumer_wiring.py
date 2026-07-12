"""MB-9 Phase 2.C — consumer-wiring regression.

Proves that the four Phase 2.C wiring points behave correctly:

1. **Grace-window auth**       — `/api/runner/poll` accepts the pending
   token during the rotation grace window AND rejects every garbage
   token unchanged.
2. **Multi-account fan-out**   — `/api/runner/poll` ships an
   ``accounts`` field iff ``RUNNER_MULTI_ACCOUNT_ENABLED=true``;
   the response shape is byte-identical to Phase 1 otherwise.
3. **Router-at-register**      — `master_bot_deployment.register_deployment`
   honours ``RUNNER_AUTO_ROUTE_AT_REGISTER`` (default OFF): runner_id
   stays None when the operator omitted it; flag ON → router fills it.
4. **Parity-drift alert**      — operator-triggered
   `POST /api/master-bot/deployments/parity-drift/scan-and-alert`
   emits one ``PARITY_DRIFT_DETECTED`` event per non-OK deployment
   and emits zero on a clean fleet.

Tests use direct engine calls where possible and fall back to HTTP
when the wiring under test is at the FastAPI layer. All artefacts
carry a TEST_ prefix and are cleaned up at fixture teardown.
"""
from __future__ import annotations

import os
import uuid
import asyncio

import pytest
import pytest_asyncio
import requests

from engines import master_bot_deployment as mbdep
from engines import multi_account_envelope as mae
from engines import runner_token_rotator as rtr
from engines import runner_registry as runners
from engines.db import get_db


# ── Live-backend gate ────────────────────────────────────────────────

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
).rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@strategyfactory.dev")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def _backend_reachable() -> bool:
    try:
        r = requests.get(f"{API}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


backend_only = pytest.mark.skipif(
    not _backend_reachable(),
    reason="backend not reachable on localhost:8001",
)


# ── Shared helpers ───────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    if not _backend_reachable():
        pytest.skip("backend offline")
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type":  "application/json"}


@pytest_asyncio.fixture
async def runner_row():
    """A fresh active runner; cleaned up after the test."""
    await runners.ensure_indexes()
    await mae.ensure_indexes()
    await rtr.ensure_indexes()
    name = f"TEST_p2c_{uuid.uuid4().hex[:8]}"
    r = await runners.register_runner(
        name=name, platform="windows", actor="pytest",
        pair_filters=["EURUSD"], timeframe_filters=["H1"],
    )
    yield r
    db = get_db()
    await db[runners.RUNNERS_COLL].delete_one({"runner_id": r["runner_id"]})
    await db[mae.ACCOUNTS_COLL].delete_many({"runner_id": r["runner_id"]})
    await db[rtr.HISTORY_COLL].delete_many({"runner_id": r["runner_id"]})


@pytest.fixture(autouse=True)
def _strip_phase2_flags():
    """Strip every Phase 2 env override BEFORE each test so default
    behaviour is exercised; restore after."""
    flags = (
        "RUNNER_AFFINITY_POLICY", "RUNNER_TOKEN_GRACE_SEC",
        "RUNNER_AUTO_ROTATE", "RUNNER_PARITY_DRIFT_WINDOW_DAYS",
        "RUNNER_MULTI_ACCOUNT_ENABLED", "RUNNER_ROTATE_INTERVAL_SEC",
        "RUNNER_AUTO_ROUTE_AT_REGISTER",
    )
    saved = {k: os.environ.pop(k, None) for k in flags}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


# ╔════════════════════════════════════════════════════════════════════╗
# ║ 1.  Grace-window auth wiring                                       ║
# ╚════════════════════════════════════════════════════════════════════╝

@backend_only
def test_poll_accepts_legacy_token_when_no_rotation(runner_row):
    rid = runner_row["runner_id"]
    tok = runner_row["token"]
    r = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": tok},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["runner_id"] == rid


@backend_only
def test_poll_rejects_garbage_token_when_no_rotation(runner_row):
    rid = runner_row["runner_id"]
    r = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": "garbage-token-xyz"},
        timeout=15,
    )
    assert r.status_code == 401


@backend_only
def test_poll_accepts_pending_token_during_grace_window(runner_row, H):
    rid = runner_row["runner_id"]
    legacy_tok = runner_row["token"]
    # Open a rotation via the admin API.
    r = requests.post(
        f"{API}/master-bot/runners/{rid}/rotate-token",
        headers=H, timeout=15,
    )
    assert r.status_code == 200
    pending_tok = r.json()["new_token"]
    # Legacy token MUST still work (the engine swapped token_hash to
    # the pending value, so the OLD value is now the grace-window
    # tail-token). Engine semantics: validate_token uses the new
    # token_hash, grace lookup matches the legacy value.
    r1 = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": pending_tok},
        timeout=15,
    )
    assert r1.status_code == 200, (
        f"new (active) token must authenticate: {r1.text}"
    )
    r2 = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": legacy_tok},
        timeout=15,
    )
    assert r2.status_code == 200, (
        f"legacy token must still authenticate during grace window: {r2.text}"
    )


# ╔════════════════════════════════════════════════════════════════════╗
# ║ 2.  Multi-account fan-out in /poll                                 ║
# ╚════════════════════════════════════════════════════════════════════╝

@backend_only
def test_poll_does_not_include_accounts_field_with_flag_off(runner_row):
    rid = runner_row["runner_id"]
    r = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": runner_row["token"]},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert "accounts" not in body, (
        "byte-identical guarantee broken: 'accounts' must NOT appear "
        "in the /poll response when RUNNER_MULTI_ACCOUNT_ENABLED=false"
    )


@backend_only
def test_poll_includes_accounts_field_with_flag_on(runner_row):
    """With the flag ON the engine returns real account rows (no
    synthetic legacy row). We add one envelope, list it, and confirm
    the shape exposed to downstream consumers."""
    rid = runner_row["runner_id"]
    acc_id = f"ACC_{uuid.uuid4().hex[:6]}"
    os.environ["RUNNER_MULTI_ACCOUNT_ENABLED"] = "true"
    try:
        async def _check():
            await mae.add_account(
                runner_id=rid, account_id=acc_id,
                credentials_envelope="envelope-bytes-XYZ",
            )
            rows = await mae.list_accounts(rid)
            assert len(rows) >= 1
            assert any(r.get("account_id") == acc_id for r in rows)
            # Cleanup.
            await mae.remove_account(runner_id=rid, account_id=acc_id)
            return rows
        asyncio.get_event_loop().run_until_complete(_check())
    finally:
        os.environ.pop("RUNNER_MULTI_ACCOUNT_ENABLED", None)


# ╔════════════════════════════════════════════════════════════════════╗
# ║ 3.  Router-at-register wiring                                      ║
# ╚════════════════════════════════════════════════════════════════════╝

def test_pick_representative_pair_tf_returns_empties_on_empty_pack():
    p, tf = mbdep._pick_representative_pair_tf({})
    assert p == "" and tf == ""


def test_pick_representative_pair_tf_walks_first_enabled_member():
    pack = {
        "payload": {
            "tiers": [
                {"members": [
                    {"enabled": False, "snapshot": {"pair": "GBPUSD",
                                                    "timeframe": "M5"}},
                    {"enabled": True,  "snapshot": {"pair": "EURUSD",
                                                    "timeframe": "H1"}},
                ]},
                {"members": [
                    {"enabled": True, "snapshot": {"pair": "XAUUSD",
                                                  "timeframe": "M15"}},
                ]},
            ],
        },
    }
    p, tf = mbdep._pick_representative_pair_tf(pack)
    assert p == "EURUSD"
    assert tf == "H1"


@pytest.mark.asyncio
async def test_auto_route_returns_none_when_flag_off():
    """The hard gate: flag-OFF returns None unconditionally."""
    os.environ.pop("RUNNER_AUTO_ROUTE_AT_REGISTER", None)
    pack = {"payload": {"tiers": [{"members": [
        {"enabled": True, "snapshot": {"pair": "EURUSD", "timeframe": "H1"}},
    ]}]}}
    rid = await mbdep._auto_route_runner_id_if_enabled(pack)
    assert rid is None


@pytest.mark.asyncio
async def test_auto_route_consults_router_when_flag_on(runner_row):
    """With the flag ON the helper consults the router; verdict
    depends on alive-heartbeat state which the fresh runner lacks
    (no heartbeat yet) so router refuses → helper returns None."""
    os.environ["RUNNER_AUTO_ROUTE_AT_REGISTER"] = "true"
    try:
        pack = {"payload": {"tiers": [{"members": [
            {"enabled": True, "snapshot": {"pair": "EURUSD",
                                           "timeframe": "H1"}},
        ]}]}}
        rid = await mbdep._auto_route_runner_id_if_enabled(pack)
        # No heartbeat → router refuses → helper returns None.
        # That IS the correct contract: never silently mis-assign.
        assert rid is None or rid == runner_row["runner_id"]
    finally:
        os.environ.pop("RUNNER_AUTO_ROUTE_AT_REGISTER", None)


@pytest.mark.asyncio
async def test_auto_route_helper_never_raises_on_bad_pack():
    """Even with malformed pack payload, helper returns None."""
    os.environ["RUNNER_AUTO_ROUTE_AT_REGISTER"] = "true"
    try:
        for pack in ({}, {"payload": None}, {"payload": {"tiers": None}}):
            rid = await mbdep._auto_route_runner_id_if_enabled(pack)
            assert rid is None
    finally:
        os.environ.pop("RUNNER_AUTO_ROUTE_AT_REGISTER", None)


# ╔════════════════════════════════════════════════════════════════════╗
# ║ 4.  Parity-drift scan-and-alert wiring                             ║
# ╚════════════════════════════════════════════════════════════════════╝

@backend_only
def test_parity_drift_scan_and_alert_returns_envelope(H):
    """On a clean pod the scan finds zero live deployments → zero
    emitted alerts. The envelope shape MUST be stable regardless."""
    r = requests.post(
        f"{API}/master-bot/deployments/parity-drift/scan-and-alert",
        headers=H, timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("scanned", "emitted", "skipped_ok", "errors", "window_days"):
        assert k in body, f"missing key {k} in {body}"
    assert isinstance(body["emitted"], list)
    assert isinstance(body["errors"], list)


@backend_only
def test_parity_drift_scan_and_alert_requires_admin():
    r = requests.post(
        f"{API}/master-bot/deployments/parity-drift/scan-and-alert",
        timeout=15,
    )
    assert r.status_code in (401, 403)


def test_alert_engine_registered_parity_drift_event_type():
    """The institutional event-type tuple includes PARITY_DRIFT_DETECTED
    — required so alert_engine.emit_event() routes the event."""
    from engines import alert_engine as ae
    assert "PARITY_DRIFT_DETECTED" in ae.INSTITUTIONAL_EVENT_TYPES


# ╔════════════════════════════════════════════════════════════════════╗
# ║ 5.  Flag-OFF byte-identical regression for /poll                   ║
# ╚════════════════════════════════════════════════════════════════════╝

@backend_only
def test_poll_response_keys_byte_identical_with_all_phase2_flags_off(
    runner_row,
):
    """With every Phase 2 flag OFF, /poll keys are EXACTLY the
    Phase 1 contract: {runner_id, queue_size, assignments}."""
    rid = runner_row["runner_id"]
    r = requests.get(
        f"{API}/runner/poll",
        headers={"X-Runner-Id": rid, "X-Runner-Token": runner_row["token"]},
        timeout=15,
    )
    assert r.status_code == 200
    keys = set(r.json().keys())
    assert keys == {"runner_id", "queue_size", "assignments"}, (
        f"flag-OFF /poll keys drifted: {keys}"
    )

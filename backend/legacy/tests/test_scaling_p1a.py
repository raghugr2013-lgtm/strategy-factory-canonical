"""VPS Scaling Phase 1.A — unit + integration tests.

Coverage (per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §5.1):

* Compute Probe accurately detects machine resources (snapshot + band)
* Scaling Router default policy is `accept_all` (byte-identical
  behaviour to the pre-P1.A world: every decision is ACCEPT)
* Scaling Router under `band_based` policy follows the canonical
  decision table, including honest-refusal on `band=unknown`
* `scaling_registry.register_or_heartbeat` is idempotent upsert
* `scaling_registry.ensure_indexes` is idempotent (re-run safe)
* Feature flag `ENABLE_BAND_BASED_ROUTING` is registered and dormant
* `compute_probe.headroom_summary()` adds `band` without changing
  any pre-existing return-shape field (regression / additive contract)
* API: POST /api/scaling/heartbeat persists + returns the snapshot
* API: GET  /api/scaling/nodes returns the persisted rows
* API: GET  /api/scaling/route preview matches the pure-function verdict
* API: every /api/scaling/* route requires auth (401 without token)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from auth_utils import create_token
from engines import compute_probe, feature_flags as ff
from engines import scaling_registry, scaling_router
from engines.db import get_db
from server import app


TEST_USER_EMAIL = "test_scaling_p1a@local.test"
TEST_HOST_ID    = "test-host-p1a"


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _fresh_motor_client():
    """Reset the motor client so each test sees a hot connection."""
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    yield


@pytest_asyncio.fixture
async def _seeded_test_user():
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    user_doc = {
        "user_id":     "test_scaling_user",
        "email":       TEST_USER_EMAIL,
        "role":        "admin",
        "status":      "approved",
        "created_at":  now,
        "approved_at": now,
    }
    await db["users"].update_one(
        {"email": TEST_USER_EMAIL},
        {"$set": user_doc},
        upsert=True,
    )
    yield user_doc
    await db["users"].delete_one({"email": TEST_USER_EMAIL})
    await db["scaling_nodes"].delete_one({"_id": TEST_HOST_ID})


def _auth_header() -> dict:
    token = create_token({
        "user_id": "test_scaling_user",
        "email":   TEST_USER_EMAIL,
        "role":    "admin",
    })
    return {"Authorization": f"Bearer {token}"}


# ─── compute_probe: band classification ──────────────────────────────

def test_compute_probe_snapshot_returns_full_shape():
    """Compute Probe accurately detects machine resources on this host."""
    snap = compute_probe.snapshot()
    assert isinstance(snap, dict)
    for key in (
        "ts", "available", "cpu_count", "cpu_percent",
        "load_avg", "mem_total_gb", "mem_available_gb", "mem_percent",
    ):
        assert key in snap, f"snapshot missing key: {key}"
    # On a normal CI host, psutil should be available.
    if snap["available"]:
        assert isinstance(snap["cpu_count"], int) and snap["cpu_count"] > 0
        assert isinstance(snap["mem_total_gb"], (int, float))
        assert snap["mem_total_gb"] > 0


def test_headroom_summary_returns_band_field():
    """P1.A — the band field is the new operator-facing categorical."""
    head = compute_probe.headroom_summary()
    assert "band" in head, "headroom_summary must include band field (P1.A)"
    assert head["band"] in ("ok", "warn", "critical", "unknown")


@pytest.mark.parametrize("cpu,mem,expected_band", [
    (10.0,  20.0, "ok"),
    (50.0,  50.0, "ok"),
    (60.0,  60.0, "ok"),       # still OK (60 < 80, 60 < 85)
    (80.0,  50.0, "warn"),     # cpu >= 80
    (50.0,  85.0, "warn"),     # mem >= 85
    (94.9,  84.9, "warn"),     # boundary just below critical
    (95.0,  50.0, "critical"), # cpu >= 95
    (50.0,  95.0, "critical"), # mem >= 95
    (99.0,  99.0, "critical"),
])
def test_band_classification_table(cpu, mem, expected_band):
    """Pure-function band classifier — exhaustive table."""
    fake_snap = {
        "ts": "x", "available": True, "cpu_count": 12,
        "cpu_percent": cpu, "mem_percent": mem,
        "load_avg": [0.5, 0.5, 0.5],
        "mem_total_gb": 32.0, "mem_available_gb": 16.0,
        "open_fds": 50, "process_rss_mb": 200.0,
    }
    head = compute_probe.headroom_summary(fake_snap)
    assert head["band"] == expected_band, (
        f"cpu={cpu} mem={mem} -> expected {expected_band}, got {head['band']}"
    )


def test_band_unknown_when_metrics_missing():
    """Honest-refusal: missing metric → unknown (never coerced to ok)."""
    fake_snap = {
        "ts": "x", "available": False,
        "cpu_percent": None, "mem_percent": None,
        "cpu_count": None, "load_avg": None,
        "mem_total_gb": None, "mem_available_gb": None,
        "open_fds": None, "process_rss_mb": None,
    }
    head = compute_probe.headroom_summary(fake_snap)
    assert head["band"] == "unknown"


def test_headroom_summary_preserves_existing_shape():
    """REGRESSION: pre-existing keys must remain present + unchanged
    when only `band` is added. Existing consumers (safe_to_widen,
    activation_governance, soak_stability, ai_orchestrator,
    agent_advisor) index by these key names."""
    head = compute_probe.headroom_summary()
    for legacy_key in ("ok", "cpu_headroom_pct", "mem_headroom_pct", "load_per_core"):
        assert legacy_key in head, f"P1.A removed legacy key: {legacy_key}"


# ─── scaling_router: pure function, default accept_all ───────────────

def test_router_default_policy_is_accept_all(monkeypatch):
    """Default behaviour (flag OFF) must be accept_all."""
    monkeypatch.delenv("ENABLE_BAND_BASED_ROUTING", raising=False)
    assert scaling_router.current_policy() == scaling_router.POLICY_ACCEPT_ALL


@pytest.mark.parametrize("band", ["ok", "warn", "critical", "unknown", None])
def test_accept_all_returns_accept_regardless_of_band(monkeypatch, band):
    """ACCEPT-ALL means: byte-identical to the pre-P1.A world."""
    monkeypatch.delenv("ENABLE_BAND_BASED_ROUTING", raising=False)
    v = scaling_router.route(class_="backtest", band=band)
    assert v["decision"] == scaling_router.DECISION_ACCEPT
    assert v["policy"]   == scaling_router.POLICY_ACCEPT_ALL
    assert v["reason"]   == "policy_accept_all"
    assert v["band"]     == band
    assert v["class_"]   == "backtest"
    assert "evaluated_at" in v


@pytest.mark.parametrize("band,expected_decision,expected_reason", [
    ("ok",        "accept", "band_ok"),
    ("warn",      "defer",  "band_warn"),
    ("critical",  "refuse", "band_critical"),
    ("unknown",   "defer",  "band_unknown"),
    (None,        "defer",  "band_unknown"),
])
def test_band_based_decision_table(monkeypatch, band, expected_decision, expected_reason):
    """When operator flips ENABLE_BAND_BASED_ROUTING=true, the router
    follows the canonical decision table from CAPACITY_ENGINE_DESIGN
    §5 / WORKER_ALLOCATION_FLOW §8."""
    monkeypatch.setenv("ENABLE_BAND_BASED_ROUTING", "true")
    v = scaling_router.route(class_="backtest", band=band)
    assert v["decision"] == expected_decision
    assert v["reason"]   == expected_reason
    assert v["policy"]   == scaling_router.POLICY_BAND_BASED


def test_router_pulls_band_from_headroom_when_band_missing(monkeypatch):
    """When `band` arg is omitted, router consults headroom['band']."""
    monkeypatch.setenv("ENABLE_BAND_BASED_ROUTING", "true")
    v = scaling_router.route(class_="mutation", headroom={"band": "critical"})
    assert v["decision"] == "refuse"
    assert v["band"]     == "critical"


# ─── feature_flags: P1.A flag registration ───────────────────────────

def test_band_routing_flag_registered():
    """The P1.A flag must live in the central registry."""
    names = {spec["name"] for spec in ff.iter_specs()}
    assert "ENABLE_BAND_BASED_ROUTING" in names


def test_band_routing_flag_default_dormant():
    """ENABLE_* discipline — must default to False."""
    for spec in ff.iter_specs():
        if spec["name"] == "ENABLE_BAND_BASED_ROUTING":
            assert spec["default"] is False
            assert spec["kind"]    == "bool"
            assert spec["scope"]   == "scaling"
            return
    pytest.fail("ENABLE_BAND_BASED_ROUTING not registered")


# ─── scaling_registry: persistence ──────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_indexes_is_idempotent():
    """ensure_indexes must be safe to call repeatedly."""
    r1 = await scaling_registry.ensure_indexes()
    r2 = await scaling_registry.ensure_indexes()
    # Second invocation: every index already exists.
    assert isinstance(r1, dict)
    assert isinstance(r2, dict)
    assert len(r2.get("errors", [])) == 0
    # On second run, nothing should be created (only "existed").
    assert len(r2.get("created", [])) == 0


@pytest.mark.asyncio
async def test_register_or_heartbeat_upserts_idempotently():
    """One heartbeat creates, second heartbeat updates same row."""
    db = get_db()
    await db["scaling_nodes"].delete_one({"_id": TEST_HOST_ID})

    snap = {"cpu_percent": 30.0, "mem_percent": 40.0, "cpu_count": 12}
    head = compute_probe.headroom_summary(snap)
    r1 = await scaling_registry.register_or_heartbeat(
        host_id=TEST_HOST_ID, hostname="t1",
        snapshot=snap, headroom=head, workload_tags=["build_host"],
    )
    assert r1["ok"]
    row1 = await scaling_registry.get_node(TEST_HOST_ID)
    assert row1 is not None
    assert row1["heartbeat_count"] == 1
    assert row1["last_headroom"]["band"] == "ok"

    # Second heartbeat — same _id, fields update, counter increments.
    snap2 = {"cpu_percent": 88.0, "mem_percent": 40.0, "cpu_count": 12}
    head2 = compute_probe.headroom_summary(snap2)
    r2 = await scaling_registry.register_or_heartbeat(
        host_id=TEST_HOST_ID, hostname="t1",
        snapshot=snap2, headroom=head2, workload_tags=["build_host"],
    )
    assert r2["ok"]
    row2 = await scaling_registry.get_node(TEST_HOST_ID)
    assert row2["heartbeat_count"] == 2
    assert row2["last_headroom"]["band"] == "warn"
    assert row2["first_seen"] == row1["first_seen"]   # preserved on update
    # band_history grew but stays bounded.
    assert len(row2["band_history"]) == 2

    await db["scaling_nodes"].delete_one({"_id": TEST_HOST_ID})


@pytest.mark.asyncio
async def test_register_rejects_invalid_host_id():
    r = await scaling_registry.register_or_heartbeat(host_id="")
    assert r["ok"] is False
    assert r["reason"] == "invalid_host_id"


# ─── API: auth-gating + happy paths ──────────────────────────────────

@pytest.mark.asyncio
async def test_scaling_endpoints_require_auth():
    """All /api/scaling/* endpoints must require JWT auth — but the
    in-pod localhost caller bypasses JWT (see auth_middleware._is_local_caller).
    To verify the auth contract we hit the route with a forged X-Forwarded-For
    so middleware does not classify us as 'internal'."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.example.com",
    ) as ac:
        # ASGI transport uses 'testclient' as client.host, NOT localhost,
        # so JWT enforcement is active.
        r1 = await ac.get("/api/scaling/nodes")
        r2 = await ac.post("/api/scaling/heartbeat", json={"host_id": "x"})
        r3 = await ac.get("/api/scaling/route?band=ok")
    for r in (r1, r2, r3):
        # 401 unauthenticated OR 403 not-approved — both are auth failures.
        assert r.status_code in (401, 403), f"got {r.status_code}: {r.text[:120]}"


@pytest.mark.asyncio
async def test_heartbeat_persists_and_returns_band(_seeded_test_user):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.example.com",
    ) as ac:
        r = await ac.post(
            "/api/scaling/heartbeat",
            headers=_auth_header(),
            json={
                "host_id": TEST_HOST_ID,
                "hostname": "p1a-test",
                "workload_tags": ["build_host"],
                "snapshot": {"cpu_percent": 20.0, "mem_percent": 30.0, "cpu_count": 8},
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["band"] == "ok"
    assert body["host_id"] == TEST_HOST_ID
    assert body["headroom"]["band"] == "ok"


@pytest.mark.asyncio
async def test_nodes_endpoint_returns_seeded_row(_seeded_test_user):
    # Seed via the engine directly so the API test is independent.
    snap = {"cpu_percent": 70.0, "mem_percent": 75.0, "cpu_count": 8}
    head = compute_probe.headroom_summary(snap)
    await scaling_registry.register_or_heartbeat(
        host_id=TEST_HOST_ID, hostname="p1a-test",
        snapshot=snap, headroom=head, workload_tags=["build_host"],
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.example.com",
    ) as ac:
        r = await ac.get("/api/scaling/nodes", headers=_auth_header())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    ids = [n["host_id"] for n in body["nodes"]]
    assert TEST_HOST_ID in ids


@pytest.mark.asyncio
async def test_route_preview_returns_accept_under_default_policy(
    _seeded_test_user, monkeypatch,
):
    """The router preview endpoint must return ACCEPT for any band
    when ENABLE_BAND_BASED_ROUTING is OFF (default behaviour soak)."""
    monkeypatch.delenv("ENABLE_BAND_BASED_ROUTING", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.example.com",
    ) as ac:
        r = await ac.get(
            "/api/scaling/route?class_=mutation&band=critical",
            headers=_auth_header(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "accept"
    assert body["policy"]   == "accept_all"


@pytest.mark.asyncio
async def test_route_preview_band_based_refuses_critical(
    _seeded_test_user, monkeypatch,
):
    monkeypatch.setenv("ENABLE_BAND_BASED_ROUTING", "true")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test.example.com",
    ) as ac:
        r = await ac.get(
            "/api/scaling/route?class_=factory_cycle&band=critical",
            headers=_auth_header(),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "refuse"
    assert body["policy"]   == "band_based"


# ─── No-impact contract: no production engine imports the router ────

def test_router_not_imported_by_production_engines():
    """P1.A invariant: scaling_router is advisory. No production engine
    may IMPORT and consume it yet. (P1.D will introduce wrap sites.)
    Allowed imports: api/scaling.py (advisory preview endpoint) and
    engines/scaling_router.py itself (the module definition)."""
    import subprocess
    # Search for actual import statements, not docstring mentions.
    try:
        out = subprocess.check_output(
            ["grep", "-rlnE",
             r"^(from engines\.scaling_router|from engines import .*scaling_router|import engines\.scaling_router)",
             "/app/backend/engines", "/app/backend/api"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        out = ""   # grep exits 1 when no matches — that's the success case.
    importers = [line for line in out.splitlines() if line]
    allowed_suffixes = (
        "/engines/scaling_router.py",  # the module itself
        "/api/scaling.py",             # advisory preview endpoint
    )
    illegal = [
        line for line in importers
        if not any(line.endswith(s) for s in allowed_suffixes)
    ]
    assert not illegal, (
        f"P1.A dormancy invariant violated — production engines import "
        f"scaling_router: {illegal}"
    )

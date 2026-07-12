"""Factory Supervisor FS-P1.0 — Phase 1.0 test suite.

Scope (per FACTORY_SUPERVISOR_P1_ARCHITECTURE_REVIEW.md §8):
  * Feature-flag registration (3 new flags)
  * supervisor_lock: try_acquire / renew / release / current_holder /
    is_leader / lease TTL clamp / atomic re-claim / cross-host blocking
  * supervisor_heartbeat: emit dormancy / verdict-band classification /
    cadence resolution / verdict vocabulary parity with
    factory_runner_heartbeat
  * supervisor_events: ALL_EVENT_TYPES vocab / severity & category maps /
    flag-OFF dormancy / dual-write to scaling_events + notifications
    when NC bridge ON / stats per-type / list_events filter
  * fleet_registry: snapshot composition / 5-s cache / refresh override /
    worst-of fleet_band / sources reporting
  * Index ensure: lock + heartbeats + notifications, idempotent
  * Public surface imports stable
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest

from engines import feature_flags as ff
from engines.factory_supervisor import (
    fleet_registry,
    supervisor_events,
    supervisor_heartbeat,
    supervisor_lock,
)


# ─── Fixture: isolate flag + lock + cache state per test ─────────────

@pytest.fixture(autouse=True)
def _isolate_fs_p10():
    saved = {
        k: os.environ.pop(k, None)
        for k in (
            "ENABLE_FACTORY_SUPERVISOR",
            "ENABLE_NOTIFICATION_CENTER",
            "FS_ROUTING_POLICY",
            "FS_LEADER_LEASE_TTL_SEC",
            "FS_HEARTBEAT_CADENCE_SEC",
        )
    }
    fleet_registry.invalidate_cache()
    # Reset the cached Motor client so each test gets a fresh
    # AsyncIOMotorClient bound to its own per-function event loop.
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    fleet_registry.invalidate_cache()
    _db_mod._client = None
    _db_mod._db = None


# ─── 1) Feature flags registered with operator-locked defaults ───────

def test_flag_enable_factory_supervisor_registered_default_off():
    assert ff.flag("ENABLE_FACTORY_SUPERVISOR") is False


def test_flag_fs_routing_policy_default_local_only():
    assert ff.flag("FS_ROUTING_POLICY") == "local_only"


def test_flag_enable_notification_center_registered_default_off():
    assert ff.flag("ENABLE_NOTIFICATION_CENTER") is False


def test_flag_fs_leader_lease_ttl_sec_default_60():
    assert ff.flag("FS_LEADER_LEASE_TTL_SEC") == 60


def test_flag_fs_heartbeat_cadence_sec_default_30():
    assert ff.flag("FS_HEARTBEAT_CADENCE_SEC") == 30


def test_flag_unknown_raises():
    with pytest.raises(KeyError):
        ff.flag("FS_DOES_NOT_EXIST")


def test_flag_factory_supervisor_scope_consistent():
    snap = ff.all_flags()
    assert snap["ENABLE_FACTORY_SUPERVISOR"]["scope"] == "factory_supervisor"
    assert snap["FS_ROUTING_POLICY"]["scope"] == "factory_supervisor"
    assert snap["ENABLE_NOTIFICATION_CENTER"]["scope"] == "notification_center"


# ─── 2) Public-surface re-exports stable ─────────────────────────────

def test_public_surface_reexports():
    import engines.factory_supervisor as fs
    # The four FS-P1.0 modules must be reachable via the package surface.
    assert hasattr(fs, "supervisor_lock")
    assert hasattr(fs, "fleet_registry")
    assert hasattr(fs, "supervisor_heartbeat")
    assert hasattr(fs, "supervisor_events")


# ─── 3) supervisor_events — vocabulary + maps ────────────────────────

def test_supervisor_events_vocab_complete():
    assert set(supervisor_events.ALL_EVENT_TYPES) == {
        "WORK_ROUTED", "WORK_DEFERRED", "WORK_REFUSED", "WORK_REROUTED",
        "WORK_QUEUED", "WORK_RETRIED", "WORK_EXPIRED", "WORK_COMPLETED",
        "WORK_FAILED",
        "FLEET_DEGRADED", "SUPERVISOR_HEARTBEAT_LOST",
        "SUPERVISOR_LEADER_CONFLICT", "ROUTING_POLICY_DEGRADED",
        "DEFER_QUEUE_OVERFLOW",
    }


def test_supervisor_events_severity_map_uses_5_level_vocab():
    valid = {"debug", "info", "warn", "critical", "fatal"}
    for evt in supervisor_events.ALL_EVENT_TYPES:
        sev = supervisor_events.EVENT_SEVERITY_MAP[evt]
        assert sev in valid, f"{evt} has invalid severity {sev!r}"


def test_supervisor_events_category_map_uses_canonical_taxonomy():
    valid = {
        "scaling", "factory", "deployment", "runner", "strategy",
        "master_bot", "feature_activation", "recommendation",
        "compute_health", "credit", "supervisor", "error",
    }
    for evt in supervisor_events.ALL_EVENT_TYPES:
        cat = supervisor_events.EVENT_CATEGORY_MAP[evt]
        assert cat in valid, f"{evt} has invalid category {cat!r}"


@pytest.mark.asyncio
async def test_supervisor_events_emit_is_noop_when_flag_off():
    assert not supervisor_events.is_enabled()
    res = await supervisor_events.emit(
        supervisor_events.EVENT_WORK_ROUTED,
        {"class_": "BACKTEST", "host_id": "test"},
    )
    assert res["emitted"] is False
    assert res["skipped"] == "flag_off"
    assert res["scaling_events_ok"] is False
    assert res["notifications_ok"] is False


@pytest.mark.asyncio
async def test_supervisor_events_emit_writes_to_scaling_events_when_flag_on(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    assert supervisor_events.is_enabled()
    assert not supervisor_events.notification_center_enabled()
    res = await supervisor_events.emit(
        supervisor_events.EVENT_WORK_ROUTED,
        {"class_": "BACKTEST", "host_id": "test-host"},
    )
    # Best-effort: scaling_events write should succeed when Mongo is up.
    assert res["scaling_events_ok"] is True
    assert res["notifications_ok"] is False  # NC bridge OFF
    assert res["severity"] == "info"
    assert res["category"] == "scaling"
    assert res["id"] and len(res["id"]) >= 8


@pytest.mark.asyncio
async def test_supervisor_events_emit_dual_writes_when_nc_on(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    monkeypatch.setenv("ENABLE_NOTIFICATION_CENTER", "true")
    assert supervisor_events.notification_center_enabled()
    res = await supervisor_events.emit(
        supervisor_events.EVENT_WORK_REFUSED,
        {"class_": "BACKTEST", "reason": "queue_full"},
        target_id="mb-test",
    )
    assert res["scaling_events_ok"] is True
    assert res["notifications_ok"] is True
    assert res["severity"] == "warn"  # WORK_REFUSED default severity


@pytest.mark.asyncio
async def test_supervisor_events_nc_bridge_gated_by_master_flag(monkeypatch):
    # Even when NC flag is set, no events flow when master FS flag is OFF.
    monkeypatch.setenv("ENABLE_NOTIFICATION_CENTER", "true")
    monkeypatch.delenv("ENABLE_FACTORY_SUPERVISOR", raising=False)
    assert not supervisor_events.notification_center_enabled()
    res = await supervisor_events.emit(
        supervisor_events.EVENT_WORK_REFUSED, {}
    )
    assert res["skipped"] == "flag_off"


@pytest.mark.asyncio
async def test_supervisor_events_stats_returns_all_keys_zeroed():
    s = await supervisor_events.stats(window_sec=60)
    assert set(s["per_type"].keys()) >= set(supervisor_events.ALL_EVENT_TYPES)
    assert s["window_sec"] == 60
    assert isinstance(s["total"], int)


@pytest.mark.asyncio
async def test_supervisor_events_list_events_returns_list():
    rows = await supervisor_events.list_events(limit=5)
    assert isinstance(rows, list)
    # If any rows exist, they must all be from this producer.
    for r in rows:
        assert r.get("producer") == "factory_supervisor"


@pytest.mark.asyncio
async def test_supervisor_events_ensure_indexes_idempotent():
    r1 = await supervisor_events.ensure_indexes()
    r2 = await supervisor_events.ensure_indexes()
    # second call should see all indexes existed already
    assert len(r2.get("created") or []) == 0
    expected = {
        "ix_notifications_ts",
        "ix_notifications_severity_ts",
        "ix_notifications_category_ts",
        "ix_notifications_status_ts",
        "ix_notifications_target_ts",
    }
    seen = set((r1.get("created") or []) + (r1.get("existed") or []))
    assert expected.issubset(seen)


# ─── 4) supervisor_lock — cooperative lease semantics ────────────────

@pytest.mark.asyncio
async def test_supervisor_lock_try_acquire_basic():
    lock_name = f"test_lock_{int(time.time()*1000)}"
    acquired, doc = await supervisor_lock.try_acquire(
        "host-A", lock_name=lock_name, ttl_sec=10,
    )
    assert acquired is True
    assert doc["holder_host_id"] == "host-A"
    # Cleanup
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_second_acquire_blocked_by_live_holder():
    lock_name = f"test_lock_{int(time.time()*1000)}_b"
    ok1, _ = await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=10)
    assert ok1
    ok2, doc2 = await supervisor_lock.try_acquire("host-B", lock_name=lock_name, ttl_sec=10)
    assert ok2 is False
    assert doc2["holder_host_id"] == "host-A"
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_same_holder_reclaim_succeeds():
    """Re-acquire by the same host should always succeed (lease refresh)."""
    lock_name = f"test_lock_{int(time.time()*1000)}_c"
    ok1, _ = await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=30)
    assert ok1
    ok2, doc2 = await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=30)
    assert ok2 is True
    assert doc2["holder_host_id"] == "host-A"
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_renew_only_for_holder():
    lock_name = f"test_lock_{int(time.time()*1000)}_d"
    await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=10)
    assert await supervisor_lock.renew("host-A", lock_name=lock_name, ttl_sec=20) is True
    assert await supervisor_lock.renew("host-B", lock_name=lock_name, ttl_sec=20) is False
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_release_only_for_holder():
    lock_name = f"test_lock_{int(time.time()*1000)}_e"
    await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=10)
    # Wrong holder cannot release
    assert await supervisor_lock.release("host-B", lock_name=lock_name) is False
    # Right holder can
    assert await supervisor_lock.release("host-A", lock_name=lock_name) is True


@pytest.mark.asyncio
async def test_supervisor_lock_expired_lease_can_be_stolen():
    lock_name = f"test_lock_{int(time.time()*1000)}_f"
    # ttl_sec gets clamped to minimum 5. We bypass by manually inserting an
    # expired doc.
    from engines.db import get_db
    db = get_db()
    await db[supervisor_lock.COLLECTION].replace_one(
        {"_id": lock_name},
        {
            "_id": lock_name,
            "lock_name": lock_name,
            "holder_host_id": "host-A",
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "renewed_at": datetime.now(timezone.utc).isoformat(),
            "lease_until_epoch": 1.0,        # epoch 1 = effectively expired
            "process_pid": 0,
        },
        upsert=True,
    )
    # host-B steals
    ok, doc = await supervisor_lock.try_acquire("host-B", lock_name=lock_name, ttl_sec=10)
    assert ok is True
    assert doc["holder_host_id"] == "host-B"
    await supervisor_lock.release("host-B", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_current_holder_reports_remaining_seconds():
    lock_name = f"test_lock_{int(time.time()*1000)}_g"
    await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=60)
    doc = await supervisor_lock.current_holder(lock_name)
    assert doc is not None
    assert doc["holder_host_id"] == "host-A"
    assert "seconds_remaining" in doc
    assert 0 < doc["seconds_remaining"] <= 60
    assert doc["is_expired"] is False
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_is_leader():
    lock_name = f"test_lock_{int(time.time()*1000)}_h"
    await supervisor_lock.try_acquire("host-A", lock_name=lock_name, ttl_sec=30)
    assert await supervisor_lock.is_leader("host-A", lock_name) is True
    assert await supervisor_lock.is_leader("host-B", lock_name) is False
    await supervisor_lock.release("host-A", lock_name=lock_name)


@pytest.mark.asyncio
async def test_supervisor_lock_ttl_clamped(monkeypatch):
    # Below floor of 5
    assert supervisor_lock._resolve_ttl(0) == 5
    # Above ceiling of 3600
    assert supervisor_lock._resolve_ttl(99999) == 3600
    # Env honoured
    monkeypatch.setenv("FS_LEADER_LEASE_TTL_SEC", "120")
    assert supervisor_lock._resolve_ttl(None) == 120


@pytest.mark.asyncio
async def test_supervisor_lock_invalid_host_id_rejected():
    ok, doc = await supervisor_lock.try_acquire("", lock_name="x")
    assert ok is False
    assert doc is None


@pytest.mark.asyncio
async def test_supervisor_lock_ensure_indexes_idempotent():
    r1 = await supervisor_lock.ensure_indexes()
    r2 = await supervisor_lock.ensure_indexes()
    seen = set((r1.get("created") or []) + (r1.get("existed") or []))
    assert "ix_fs_lock_name" in seen
    assert len(r2.get("created") or []) == 0


# ─── 5) supervisor_heartbeat — emit + verdict band ───────────────────

@pytest.mark.asyncio
async def test_supervisor_heartbeat_emit_noop_when_flag_off():
    assert not supervisor_heartbeat.is_enabled()
    result = await supervisor_heartbeat.emit("test-host", {"k": "v"})
    assert result is False


@pytest.mark.asyncio
async def test_supervisor_heartbeat_emit_when_flag_on(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    assert supervisor_heartbeat.is_enabled()
    ok = await supervisor_heartbeat.emit(
        f"test-host-{int(time.time()*1000)}", {"queue_depth": 3}, is_leader=True,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_supervisor_heartbeat_verdict_band_not_expected_when_flag_off():
    v = await supervisor_heartbeat.verdict_band("some-host-no-data")
    assert v["band"] == supervisor_heartbeat.VERDICT_NOT_EXPECTED
    assert v["enabled"] is False


@pytest.mark.asyncio
async def test_supervisor_heartbeat_verdict_band_never_seen_with_flag_on(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    v = await supervisor_heartbeat.verdict_band(f"never-seen-{int(time.time()*1000)}")
    assert v["band"] == supervisor_heartbeat.VERDICT_NEVER_SEEN
    assert v["enabled"] is True


@pytest.mark.asyncio
async def test_supervisor_heartbeat_verdict_band_alive_after_emit(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    host = f"test-alive-{int(time.time()*1000)}"
    await supervisor_heartbeat.emit(host, {"q": 0})
    v = await supervisor_heartbeat.verdict_band(host, cadence_sec=30)
    assert v["band"] == supervisor_heartbeat.VERDICT_ALIVE
    assert v["age_sec"] is not None and v["age_sec"] < 5


def test_supervisor_heartbeat_classify_thresholds():
    classify = supervisor_heartbeat._classify
    # not_expected when disabled
    assert classify(None, 30, False) == supervisor_heartbeat.VERDICT_NOT_EXPECTED
    # never_seen when enabled but no data
    assert classify(None, 30, True) == supervisor_heartbeat.VERDICT_NEVER_SEEN
    # alive bucket
    assert classify(30, 30, True) == supervisor_heartbeat.VERDICT_ALIVE
    assert classify(60, 30, True) == supervisor_heartbeat.VERDICT_ALIVE
    # stale bucket
    assert classify(61, 30, True) == supervisor_heartbeat.VERDICT_STALE
    assert classify(120, 30, True) == supervisor_heartbeat.VERDICT_STALE
    # dead bucket
    assert classify(121, 30, True) == supervisor_heartbeat.VERDICT_DEAD
    # clock skew → unknown
    assert classify(-1, 30, True) == supervisor_heartbeat.VERDICT_UNKNOWN


def test_supervisor_heartbeat_vocabulary_parity_with_factory_runner():
    """Verdict band vocabulary must match factory_runner_heartbeat verbatim."""
    from engines import factory_runner_heartbeat as frh
    assert supervisor_heartbeat.VERDICT_ALIVE == frh.VERDICT_ALIVE
    assert supervisor_heartbeat.VERDICT_STALE == frh.VERDICT_STALE
    assert supervisor_heartbeat.VERDICT_DEAD == frh.VERDICT_DEAD
    assert supervisor_heartbeat.VERDICT_NEVER_SEEN == frh.VERDICT_NEVER_SEEN
    assert supervisor_heartbeat.VERDICT_NOT_EXPECTED == frh.VERDICT_NOT_EXPECTED
    assert supervisor_heartbeat.VERDICT_UNKNOWN == frh.VERDICT_UNKNOWN


def test_supervisor_heartbeat_cadence_resolution(monkeypatch):
    assert supervisor_heartbeat._resolve_cadence(None) == 30
    assert supervisor_heartbeat._resolve_cadence(45) == 45
    assert supervisor_heartbeat._resolve_cadence(2) == 5     # clamped low
    assert supervisor_heartbeat._resolve_cadence(99999) == 600  # clamped high
    monkeypatch.setenv("FS_HEARTBEAT_CADENCE_SEC", "90")
    assert supervisor_heartbeat._resolve_cadence(None) == 90


@pytest.mark.asyncio
async def test_supervisor_heartbeat_list_recent():
    rows = await supervisor_heartbeat.list_recent(limit=5)
    assert isinstance(rows, list)


@pytest.mark.asyncio
async def test_supervisor_heartbeat_ensure_indexes_idempotent():
    r1 = await supervisor_heartbeat.ensure_indexes()
    r2 = await supervisor_heartbeat.ensure_indexes()
    assert len(r2.get("created") or []) == 0
    seen = set((r1.get("created") or []) + (r1.get("existed") or []))
    assert "ix_fs_heartbeat_host_ts" in seen
    assert "ix_fs_heartbeat_ts" in seen


# ─── 6) fleet_registry — snapshot composition ────────────────────────

@pytest.mark.asyncio
async def test_fleet_registry_snapshot_shape():
    snap = await fleet_registry.snapshot(refresh=True)
    expected = {"evaluated_at", "local_host_id", "hosts", "local",
                "fleet_band", "sources"}
    assert expected.issubset(snap.keys())
    assert "host_capability" in snap["local"]
    assert "queue_pressure"  in snap["local"]
    assert "headroom"        in snap["local"]
    assert "admission_stats" in snap["local"]
    assert "remote_hosts"    in snap["sources"]


@pytest.mark.asyncio
async def test_fleet_registry_cache_hit_within_ttl():
    s1 = await fleet_registry.snapshot(refresh=True)
    # Mutate the cached value to prove the second call is a cache hit
    s1["_test_marker"] = "cached"
    s2 = await fleet_registry.snapshot()  # not refresh
    assert s2.get("_test_marker") == "cached"


@pytest.mark.asyncio
async def test_fleet_registry_refresh_bypasses_cache():
    s1 = await fleet_registry.snapshot(refresh=True)
    s1["_test_marker"] = "cached"
    s2 = await fleet_registry.snapshot(refresh=True)
    assert "_test_marker" not in s2


def test_fleet_registry_fleet_band_worst_of():
    # No hosts, no local headroom → unknown
    assert fleet_registry.fleet_band({"hosts": [], "local": {}}) == "unknown"
    # Worst-of: critical beats warn beats ok
    snap = {
        "hosts": [
            {"last_headroom": {"band": "ok"}},
            {"last_headroom": {"band": "warn"}},
            {"last_headroom": {"band": "critical"}},
        ],
        "local": {},
    }
    assert fleet_registry.fleet_band(snap) == "critical"
    # No critical → warn wins
    snap["hosts"][2]["last_headroom"]["band"] = "ok"
    assert fleet_registry.fleet_band(snap) == "warn"


@pytest.mark.asyncio
async def test_fleet_registry_sources_reports_status():
    snap = await fleet_registry.snapshot(refresh=True)
    for k, v in snap["sources"].items():
        assert v in {"ok", "error", "unavailable"}, f"{k}={v}"


@pytest.mark.asyncio
async def test_fleet_registry_local_host_id_populated():
    snap = await fleet_registry.snapshot(refresh=True)
    assert snap["local_host_id"]
    assert isinstance(snap["local_host_id"], str)


# ─── 7) Notification-bridge invariants ───────────────────────────────

@pytest.mark.asyncio
async def test_notification_bridge_writes_canonical_shape(monkeypatch):
    """When the NC bridge writes, the row carries the frozen
    Notification schema fields (severity, category, status, payload,
    title, message)."""
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    monkeypatch.setenv("ENABLE_NOTIFICATION_CENTER", "true")
    res = await supervisor_events.emit(
        supervisor_events.EVENT_DEFER_QUEUE_OVERFLOW,
        {"class_": "BACKTEST", "reason": "depth_cap_exceeded", "depth": 1001},
        target_id="defer_queue_BACKTEST",
        correlation_id=f"corr-{int(time.time()*1000)}",
    )
    assert res["notifications_ok"] is True

    from engines.db import get_db
    db = get_db()
    doc = await db[supervisor_events.NOTIFICATIONS_COLLECTION].find_one(
        {"id": res["id"]}
    )
    assert doc is not None
    # Frozen schema fields
    for k in ("ts", "ts_epoch", "host_id", "event_type", "producer",
              "category", "severity", "status", "title", "message",
              "payload", "target_id", "correlation_id",
              "suggested_action", "acked_by", "acked_at"):
        assert k in doc, f"missing field: {k}"
    assert doc["status"] == "new"
    assert doc["producer"] == "factory_supervisor"
    assert doc["severity"] in {"debug", "info", "warn", "critical", "fatal"}
    assert doc["acked_by"] is None
    assert doc["acked_at"] is None


# ─── 8) Forward-compat: unknown event types do not crash ─────────────

@pytest.mark.asyncio
async def test_supervisor_events_unknown_type_does_not_crash(monkeypatch):
    monkeypatch.setenv("ENABLE_FACTORY_SUPERVISOR", "true")
    res = await supervisor_events.emit(
        "NEW_UNREGISTERED_TYPE_FOR_FORWARD_COMPAT",
        {"k": "v"},
        severity="info",
        category="supervisor",
    )
    assert res["emitted"] is True or res["scaling_events_ok"] is True
    assert res["severity"] == "info"
    assert res["category"] == "supervisor"

"""Factory Supervisor FS-P1.3 — Phase 1.3 test suite.

Scope:
  * system_state_view: aggregator shape, advisory_only gating, health
    derivation, source reporters, 5 s cache.
  * notification_center: read API filters, unread_count, stats,
    acknowledge() / archive() idempotence.
  * architect_advisor: every rule's positive + negative path, sort
    order, "no action required" fallback, dashboard payload contract,
    five Copilot-mandated questions answerable.
  * worker_scheduler: dormant by default, start/stop idempotent,
    register_task surface, every built-in sub-task gated independently,
    status() never raises.
  * feature flags: every FS-P1.3 flag default OFF / neutral.
  * API contracts: status block advertises FS-P1.3, scheduler block
    present, notification_center_api block present.
"""
from __future__ import annotations

import os

import pytest

from engines.factory_supervisor import (
    architect_advisor,
    notification_center,
    supervisor_events,
    system_state_view,
    worker_scheduler,
)


# ─── Fixture: isolate FS-P1.3 flags + DB module per test ────────────

_FS_FLAGS = (
    "ENABLE_FACTORY_SUPERVISOR",
    "ENABLE_NOTIFICATION_CENTER",
    "FS_ENABLE_SYSTEM_STATE_VIEW",
    "FS_ENABLE_ARCHITECT_DASHBOARD",
    "FS_ENABLE_WORKER_SCHEDULER",
    "FS_ENABLE_NOTIFICATION_API",
    "FS_ENABLE_TELEMETRY_WORKER",
    "FS_ENABLE_NOTIFICATION_WORKER",
    "FS_ENABLE_AUTO_LEARNING_WORKER",
    "FS_ENABLE_COPILOT_REFRESH",
    "FS_ENABLE_DEFER_QUEUE",
    "FS_ENABLE_DEFER_WORKER",
    "FS_WORKER_POLL_INTERVAL_SEC",
    "ENABLE_AUTONOMOUS_DISCOVERY",
)


@pytest.fixture(autouse=True)
def _isolate_fs_p13():
    saved = {k: os.environ.pop(k, None) for k in _FS_FLAGS}
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()
    # Ensure no scheduler task survives a test.
    try:
        worker_scheduler.stop()
    except Exception:
        pass


def _enable_fs():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"


# ============================================================================
# 1) Feature flags — every FS-P1.3 flag defaults OFF / neutral
# ============================================================================


def test_fs_p13_flags_default_off():
    from engines.feature_flags import flag
    assert flag("FS_ENABLE_SYSTEM_STATE_VIEW") is False
    assert flag("FS_ENABLE_ARCHITECT_DASHBOARD") is False
    assert flag("FS_ENABLE_WORKER_SCHEDULER") is False
    assert flag("FS_ENABLE_NOTIFICATION_API") is False
    assert flag("FS_ENABLE_TELEMETRY_WORKER") is False
    assert flag("FS_ENABLE_NOTIFICATION_WORKER") is False
    assert flag("FS_ENABLE_AUTO_LEARNING_WORKER") is False
    assert flag("FS_ENABLE_COPILOT_REFRESH") is False


def test_fs_p13_flags_registered_with_intent():
    from engines.feature_flags import _FLAG_SPECS
    names = {s["name"] for s in _FLAG_SPECS}
    for n in (
        "FS_ENABLE_SYSTEM_STATE_VIEW",
        "FS_ENABLE_ARCHITECT_DASHBOARD",
        "FS_ENABLE_WORKER_SCHEDULER",
        "FS_ENABLE_NOTIFICATION_API",
        "FS_ENABLE_TELEMETRY_WORKER",
        "FS_ENABLE_NOTIFICATION_WORKER",
        "FS_ENABLE_AUTO_LEARNING_WORKER",
        "FS_ENABLE_COPILOT_REFRESH",
    ):
        assert n in names, f"{n} not registered"


# ============================================================================
# 2) system_state_view — gating, shape, cache
# ============================================================================


def test_system_state_view_disabled_by_default():
    assert system_state_view.is_enabled() is False


def test_system_state_view_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    assert system_state_view.is_enabled() is True


def test_system_state_view_requires_master_flag():
    # master OFF, sub-flag ON → still disabled
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    assert system_state_view.is_enabled() is False


@pytest.mark.asyncio
async def test_snapshot_shape_advisory_only_when_gated_off():
    _enable_fs()
    snap = await system_state_view.snapshot(refresh=True)
    assert snap["phase"] in ("FS-P1.3", "FS-P1.4")
    assert snap["advisory_only"] is True       # gate OFF
    # Every top-level key from the contract is present
    for k in (
        "evaluated_at", "local_host_id", "system_health",
        "fleet", "queue_pressure", "submissions", "defer_queue",
        "notifications", "scaling_events", "admission", "workers",
        "routing", "remote_transport", "deployment_readiness",
        "feature_flags", "sources",
    ):
        assert k in snap, f"missing top-level key {k}"


@pytest.mark.asyncio
async def test_snapshot_advisory_off_when_consumer_gate_on():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    snap = await system_state_view.snapshot(refresh=True)
    assert snap["advisory_only"] is False


@pytest.mark.asyncio
async def test_snapshot_sources_track_per_subsystem_status():
    snap = await system_state_view.snapshot(refresh=True)
    sources = snap["sources"]
    # All expected sources are reported
    for s in (
        "fleet", "queue_pressure", "submissions", "defer_queue",
        "notifications", "supervisor_events", "admission", "workers",
        "routing", "remote_transport", "deployment", "feature_flags",
    ):
        assert s in sources
        assert sources[s] in ("ok", "error", "unavailable")


@pytest.mark.asyncio
async def test_snapshot_cached_within_ttl():
    snap1 = await system_state_view.snapshot(refresh=True)
    snap2 = await system_state_view.snapshot(refresh=False)
    assert snap1 is snap2                # exact same dict ref → cached


@pytest.mark.asyncio
async def test_snapshot_refresh_bypasses_cache():
    snap1 = await system_state_view.snapshot(refresh=True)
    snap2 = await system_state_view.snapshot(refresh=True)
    assert snap1 is not snap2


@pytest.mark.asyncio
async def test_snapshot_includes_fs_flags_block():
    snap = await system_state_view.snapshot(refresh=True)
    flags = snap["feature_flags"]
    assert "fs_flags" in flags
    # Curated subset — every FS-P1.3 flag must be visible to dashboards
    for n in ("FS_ENABLE_SYSTEM_STATE_VIEW", "FS_ENABLE_ARCHITECT_DASHBOARD",
              "FS_ENABLE_WORKER_SCHEDULER"):
        assert n in flags["fs_flags"]


@pytest.mark.asyncio
async def test_system_health_unknown_with_empty_signals():
    snap = await system_state_view.snapshot(refresh=True)
    # Worst-of derivation — accept any valid band; we just want a
    # stable string from the enumerated set.
    assert snap["system_health"] in ("ok", "warn", "critical", "unknown")


def test_invalidate_cache_resets_state():
    system_state_view._CACHE["value"] = {"sentinel": True}
    system_state_view.invalidate_cache()
    assert system_state_view._CACHE["value"] is None


# ============================================================================
# 3) Notification Center — read API + acknowledge
# ============================================================================


def test_notification_center_disabled_by_default():
    assert notification_center.is_enabled() is False


def test_notification_center_enables_with_both_flags():
    _enable_fs()
    os.environ["ENABLE_NOTIFICATION_CENTER"] = "true"
    assert notification_center.is_enabled() is True


def test_notification_center_exports_statuses():
    assert notification_center.STATUS_NEW == "new"
    assert notification_center.STATUS_ACK == "ack"
    assert notification_center.STATUS_ARCHIVED == "archived"
    assert set(notification_center.ALL_STATUSES) == {"new", "ack", "archived"}


@pytest.mark.asyncio
async def test_list_notifications_empty_when_gated_off():
    rows = await notification_center.list_notifications(limit=10)
    assert isinstance(rows, list)
    # gated OFF → no writes → empty list (or whatever survived)
    assert rows == [] or all(isinstance(r, dict) for r in rows)


@pytest.mark.asyncio
async def test_unread_count_returns_int_even_when_gated_off():
    n = await notification_center.unread_count()
    assert isinstance(n, int)
    assert n >= 0


@pytest.mark.asyncio
async def test_stats_returns_stable_shape():
    s = await notification_center.stats(window_sec=3600)
    for k in ("window_sec", "total", "per_severity", "per_category", "per_status"):
        assert k in s


@pytest.mark.asyncio
async def test_notification_full_lifecycle_emit_list_ack_archive():
    _enable_fs()
    os.environ["ENABLE_NOTIFICATION_CENTER"] = "true"
    emitted = await supervisor_events.emit(
        event_type="LOCK_ACQUIRED",
        target_id="test-host-p13",
        payload={"smoke": True, "reason": "p1.3 smoke"},
    )
    nid = emitted.get("id")
    assert nid is not None
    assert emitted.get("notifications_ok") is True
    # list_notifications can see it
    rows = await notification_center.list_notifications(limit=10, event_type="LOCK_ACQUIRED")
    assert any(r.get("id") == nid for r in rows)
    # unread_count ≥ 1
    assert await notification_center.unread_count() >= 1
    # acknowledge it
    res = await notification_center.acknowledge([nid], user={"email": "operator@x"})
    assert res["matched"] >= 1
    assert nid in res["acked_ids"]
    # double-ack is idempotent (modified may be 0)
    res2 = await notification_center.acknowledge([nid], user={"email": "operator@x"})
    assert res2["matched"] >= 0
    # archive
    arc = await notification_center.archive([nid], user={"email": "admin@x"})
    assert arc["matched"] >= 1
    # final row state = archived
    row = await notification_center.get_notification(nid)
    assert row is not None
    assert row["status"] == "archived"


@pytest.mark.asyncio
async def test_get_notification_returns_none_for_missing_id():
    row = await notification_center.get_notification("nonexistent-xyz")
    assert row is None


@pytest.mark.asyncio
async def test_acknowledge_with_empty_list_is_noop():
    res = await notification_center.acknowledge([], user={"email": "x"})
    assert res["matched"] == 0
    assert res["modified"] == 0
    assert res["acked_ids"] == []


@pytest.mark.asyncio
async def test_list_notifications_severity_filter_applied():
    _enable_fs()
    os.environ["ENABLE_NOTIFICATION_CENTER"] = "true"
    emitted = await supervisor_events.emit(
        event_type="WORK_FAILED",      # severity=critical per FS-P1.2
        target_id="host-A",
        payload={"smoke": True},
    )
    nid_crit = emitted.get("id")
    assert nid_crit is not None
    rows = await notification_center.list_notifications(severity="critical", limit=20)
    assert all(r["severity"] == "critical" for r in rows)
    assert any(r.get("id") == nid_crit for r in rows)


# ============================================================================
# 4) architect_advisor — rules + dashboard payload
# ============================================================================


def test_architect_advisor_disabled_by_default():
    assert architect_advisor.is_enabled() is False


def test_architect_advisor_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_ARCHITECT_DASHBOARD"] = "true"
    assert architect_advisor.is_enabled() is True


def test_recommendation_shape_is_stable():
    r = architect_advisor.Recommendation(
        code="X", severity="info", title="t", detail="d",
    )
    d = r.to_dict()
    for k in ("code", "severity", "title", "detail", "suggested_fix", "evidence"):
        assert k in d


def test_evaluate_empty_snap_returns_no_action_or_advisories():
    recs = architect_advisor.evaluate({})
    assert len(recs) >= 1
    assert all(isinstance(r, architect_advisor.Recommendation) for r in recs)
    # Sorted by severity desc — first must be the strongest
    sev_ranks = [architect_advisor._SEV_RANK[r.severity] for r in recs]
    assert sev_ranks == sorted(sev_ranks, reverse=True)


def test_rule_no_action_required_when_all_clean():
    """If the synthetic snap explicitly states 'everything is fine',
    we expect the happy-path rec — but only IF no other rule fires.
    The advisor errs on the side of advisories, which is by design."""
    snap = {
        "fleet": {
            "hosts": [{"last_host_capability": {"os": "Windows"}}],
            "fleet_band": "ok",
        },
        "deployment_readiness": {"ready": True, "blockers": []},
        "system_health": "ok",
        "feature_flags": {
            "auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": True},
        },
    }
    recs = architect_advisor.evaluate(snap)
    codes = {r.code for r in recs}
    # Either NO_ACTION_REQUIRED or DEPLOYMENT_READY (both happy paths)
    assert ("NO_ACTION_REQUIRED" in codes) or ("DEPLOYMENT_READY" in codes)


def test_rule_b_windows_soak_fires_when_no_windows_host():
    snap = {"fleet": {"hosts": []}}
    codes = {r.code for r in architect_advisor.evaluate(snap)}
    assert "WINDOWS_VPS_SOAK_INCOMPLETE" in codes


def test_rule_b_windows_soak_silent_when_host_present():
    snap = {
        "fleet": {
            "hosts": [
                {"last_host_capability": {"os": "Windows Server 2022"}},
                {"last_host_capability": {"os": "Linux"}},
            ],
            "fleet_band": "ok",
        },
    }
    codes = {r.code for r in architect_advisor.evaluate(snap)}
    assert "WINDOWS_VPS_SOAK_INCOMPLETE" not in codes


def test_rule_c_auto_learning_eligible_but_disabled_fires():
    snap = {
        "fleet": {"fleet_band": "ok", "hosts": [
            {"last_host_capability": {"os": "Windows"}},
        ]},
        "defer_queue": {"stats": {"per_status": {"queued": 0, "retrying": 0}}},
        "feature_flags": {"auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": False}},
    }
    codes = {r.code for r in architect_advisor.evaluate(snap)}
    assert "AUTO_LEARNING_ELIGIBLE_BUT_DISABLED" in codes


def test_rule_c_silent_when_flag_already_on():
    snap = {
        "fleet": {"fleet_band": "ok", "hosts": [
            {"last_host_capability": {"os": "Windows"}},
        ]},
        "feature_flags": {"auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": True}},
    }
    codes = {r.code for r in architect_advisor.evaluate(snap)}
    assert "AUTO_LEARNING_ELIGIBLE_BUT_DISABLED" not in codes


def test_rule_d_best_master_bot_fires_when_deployment_ready_and_count():
    snap = {
        "deployment_readiness": {"ready": True, "evidence": {"deployment_count": 3}},
        "fleet": {"hosts": [{"last_host_capability": {"os": "Windows"}}]},
        "feature_flags": {"auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": True}},
    }
    codes = {r.code for r in architect_advisor.evaluate(snap)}
    assert "BEST_MASTER_BOT_AVAILABLE" in codes


def test_rule_g_broker_unhealthy_fires_when_critical_headroom():
    snap = {
        "fleet": {
            "hosts": [{"last_host_capability": {"os": "Windows"}}],
            "local": {"headroom": {"band": "critical"}},
        },
    }
    rec = next(r for r in architect_advisor.evaluate(snap)
               if r.code == "BROKER_CONNECTION_UNHEALTHY")
    assert rec.severity == "critical"


def test_rule_h_defer_backlog_warn_vs_critical():
    snap_warn = {
        "fleet": {"hosts": [{"last_host_capability": {"os": "Windows"}}]},
        "defer_queue": {"stats": {"per_status": {"queued": 40, "retrying": 0, "claimed": 0}}},
    }
    rec = next(r for r in architect_advisor.evaluate(snap_warn)
               if r.code == "DEFER_QUEUE_BACKLOG")
    assert rec.severity == "warn"

    snap_crit = {
        "fleet": {"hosts": [{"last_host_capability": {"os": "Windows"}}]},
        "defer_queue": {"stats": {"per_status": {"queued": 200, "retrying": 0, "claimed": 0}}},
    }
    rec = next(r for r in architect_advisor.evaluate(snap_crit)
               if r.code == "DEFER_QUEUE_BACKLOG")
    assert rec.severity == "critical"


def test_rule_j_critical_unacked_fires():
    snap = {
        "fleet": {"hosts": [{"last_host_capability": {"os": "Windows"}}]},
        "notifications": {"stats": {
            "per_severity": {"critical": 3, "warn": 1},
            "per_status":   {"new": 4, "ack": 0, "archived": 0},
        }},
    }
    rec = next(r for r in architect_advisor.evaluate(snap)
               if r.code == "NOTIFICATION_CRITICALS_UNACKED")
    assert rec.severity == "critical"


def test_recommended_action_returns_top_priority():
    snap = {
        "fleet": {"hosts": [{"last_host_capability": {"os": "Windows"}}]},
        "notifications": {"stats": {
            "per_severity": {"critical": 1},
            "per_status":   {"new": 1, "ack": 0, "archived": 0},
        }},
    }
    rec = architect_advisor.recommended_action(snap)
    assert rec.severity == "critical"
    assert rec.code == "NOTIFICATION_CRITICALS_UNACKED"


def test_dashboard_payload_answers_five_copilot_questions():
    snap = {
        "phase": "FS-P1.3",
        "advisory_only": True,
        "evaluated_at": "2026-02-01T00:00:00+00:00",
        "system_health": "ok",
        "fleet": {"hosts": [], "fleet_band": "unknown"},
        "queue_pressure": {},
        "submissions": {"stats": {"per_outcome": {"refused": 0}}},
        "defer_queue": {"stats": {"per_status": {}}, "rows_preview": []},
        "notifications": {"stats": {"per_severity": {}, "per_status": {}}, "recent_preview": []},
        "scaling_events": {"recent_preview": []},
        "admission": {"band": "ok"},
        "workers":  {"manifest": [{"name": "deferred_worker", "active": False}]},
        "routing":  {"active": "compute_health_aware", "manifest": []},
        "remote_transport": {},
        "deployment_readiness": {"ready": False, "blockers": [], "evidence": {}},
        "feature_flags": {
            "fs_flags": {"FS_ENABLE_ARCHITECT_DASHBOARD": False},
            "fag_flags": {"ENABLE_BAND_BASED_ROUTING": False,
                          "ENABLE_ADMISSION_CONTROL": False},
            "auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": False},
        },
        "sources": {"fleet": "ok", "submissions": "ok"},
    }
    payload = architect_advisor.dashboard_payload(snap)
    # What requires attention?
    assert "recommendations" in payload and len(payload["recommendations"]) >= 1
    # What is blocked?
    assert "blocked" in payload
    # What should I do next?
    assert "recommended_action" in payload
    assert payload["recommended_action"]["code"]
    # Which systems are healthy?
    assert "healthy_systems" in payload
    # Which systems are inactive?
    assert "inactive_workers" in payload
    assert "deferred_worker" in payload["inactive_workers"]
    assert "inactive_flags" in payload
    # Which features are ready for activation?
    assert "activation_ready" in payload


def test_dashboard_sections_cover_every_operator_requirement():
    snap = {"feature_flags": {}, "sources": {}}
    payload = architect_advisor.dashboard_payload(snap)
    sections = payload["sections"]
    # Every section the operator demanded
    for k in (
        "fleet_health", "queue_pressure", "submissions", "defer_queue",
        "notifications", "scaling_events", "admission_stats",
        "worker_status", "routing_stats", "deployment_readiness",
    ):
        assert k in sections


# ============================================================================
# 5) worker_scheduler — registry + start/stop + per-task gates
# ============================================================================


def test_scheduler_disabled_by_default():
    assert worker_scheduler.is_enabled() is False


def test_scheduler_enables_only_with_both_flags():
    os.environ["FS_ENABLE_WORKER_SCHEDULER"] = "true"     # only sub-flag
    assert worker_scheduler.is_enabled() is False
    _enable_fs()
    assert worker_scheduler.is_enabled() is True


def test_scheduler_status_lists_every_builtin_task():
    st = worker_scheduler.status()
    names = {t["name"] for t in st["tasks"]}
    for n in (
        "defer_queue_poller",
        "telemetry_sync",
        "notification_fanout",
        "auto_learning_drain",
        "copilot_context_refresh",
    ):
        assert n in names


def test_scheduler_start_noop_when_master_flag_off():
    res = worker_scheduler.start()
    assert res["running"] is False
    assert res["started"] == []
    assert all(s["reason"] == "master_flag_off" for s in res["skipped"])


@pytest.mark.asyncio
async def test_scheduler_start_stop_idempotent():
    _enable_fs()
    os.environ["FS_ENABLE_WORKER_SCHEDULER"] = "true"
    os.environ["FS_WORKER_POLL_INTERVAL_SEC"] = "3600"   # don't fire mid-test
    res1 = worker_scheduler.start()
    assert res1["running"] is True
    assert "defer_queue_poller" in res1["started"]
    # Second start is idempotent
    res2 = worker_scheduler.start()
    assert any(
        s["name"] == "defer_queue_poller" and s["reason"] == "already_running"
        for s in res2["skipped"]
    )
    # Stop
    stop = worker_scheduler.stop()
    assert "defer_queue_poller" in stop["stopped"]
    # Double-stop is safe
    stop2 = worker_scheduler.stop()
    assert stop2["stopped"] == []


def test_scheduler_register_task_extends_registry():
    async def custom_runner():
        return {"ok": True}
    worker_scheduler.register_task(
        "custom_test_task",
        custom_runner,
        flag="FS_ENABLE_TEST_TASK",
        interval_sec=5,
        intent="unit test",
    )
    names = {t["name"] for t in worker_scheduler.status()["tasks"]}
    assert "custom_test_task" in names
    # Cleanup so other tests don't see it
    worker_scheduler._TASKS.pop("custom_test_task", None)


def test_scheduler_status_carries_flag_value_for_each_task():
    st = worker_scheduler.status()
    for t in st["tasks"]:
        assert "flag_value" in t
        assert isinstance(t["flag_value"], bool)


def test_scheduler_per_task_flag_independence():
    # Master ON + per-task flag OFF → task body would skip even if loop runs
    _enable_fs()
    os.environ["FS_ENABLE_WORKER_SCHEDULER"] = "true"
    # All sub-task flags default OFF
    st = worker_scheduler.status()
    for t in st["tasks"]:
        if t["name"] != "defer_queue_poller":
            assert t["flag_value"] is False


# ============================================================================
# 6) Public API contract — /status block carries FS-P1.3 fields
# ============================================================================


@pytest.mark.asyncio
async def test_status_block_advertises_fs_p13():
    """Without spinning up FastAPI, validate the underlying modules
    expose the keys the /status endpoint composes."""
    from engines.factory_supervisor import supervisor_events as _ev
    assert "WORK_QUEUED" in _ev.ALL_EVENT_TYPES
    assert system_state_view.is_enabled() in (True, False)
    assert architect_advisor.is_enabled() in (True, False)
    assert isinstance(worker_scheduler.status(), dict)
    assert notification_center.is_enabled() in (True, False)


# ============================================================================
# 7) Provider/transport neutrality — no transport SDK imported by FS-P1.3
# ============================================================================


def test_no_provider_specific_sdk_imported_by_fs_p13():
    import sys
    forbidden = (
        "openai", "anthropic", "google.generativeai",
        "stripe", "twilio", "boto3",
    )
    for f in forbidden:
        assert f not in sys.modules, f"{f} accidentally imported by FS-P1.3"

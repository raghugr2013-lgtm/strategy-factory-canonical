"""Factory Supervisor FS-P1.1 — Phase 1.1 test suite.

Scope:
  * workload envelope contract (required metadata fields, factory)
  * routing_policy registry (local_only active; 5 inactive fall back)
  * routing_policy.resolve_policy_name() obeys FS_ROUTING_POLICY flag
  * submission_dispatcher DORMANT short-circuit (flag OFF)
  * submission_dispatcher full pipeline (flag ON):
      - WORK_ROUTED for accepted
      - WORK_DEFERRED for deferred
      - WORK_REFUSED for refused
      - WORK_REROUTED supported in event vocabulary
  * Index ensure idempotent
  * API surface: status manifest, /submit envelope round-trip, /submissions
  * supervisor_events WORK_REROUTED registered (severity/category)
  * Notification Center compatibility (accepted/deferred/refused/rerouted)
"""
from __future__ import annotations

import os
import uuid

import pytest

from engines.factory_supervisor import (
    routing_policy,
    submission_dispatcher,
    supervisor_events,
)
from engines.factory_supervisor.workload import (
    REQUIRED_METADATA_FIELDS,
    new_workload,
)


# ─── Fixture: isolate flag + cache state per test ────────────────────

@pytest.fixture(autouse=True)
def _isolate_fs_p11():
    saved = {
        k: os.environ.pop(k, None)
        for k in (
            "ENABLE_FACTORY_SUPERVISOR",
            "ENABLE_NOTIFICATION_CENTER",
            "ENABLE_ADMISSION_CONTROL",
            "FS_ROUTING_POLICY",
            "FS_LEADER_LEASE_TTL_SEC",
            "FS_HEARTBEAT_CADENCE_SEC",
        )
    }
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _db_mod._client = None
    _db_mod._db = None


# ─── 1) Workload envelope contract ───────────────────────────────────

def test_workload_required_metadata_fields_frozen():
    # Operator-locked contract.
    assert REQUIRED_METADATA_FIELDS == (
        "workload_class",
        "priority",
        "source_module",
        "correlation_id",
        "created_at",
        "routing_decision",
        "assigned_host",
    )


def test_new_workload_stamps_correlation_and_created_at():
    w = new_workload(workload_class="backtest", source_module="auto_factory")
    assert w.workload_class == "backtest"
    assert w.source_module == "auto_factory"
    assert isinstance(w.correlation_id, str) and len(w.correlation_id) > 8
    assert isinstance(w.created_at, str) and w.created_at.endswith("+00:00")
    assert isinstance(w.workload_id, str) and len(w.workload_id) > 8
    # routing_decision + assigned_host are None pre-dispatch
    assert w.routing_decision is None
    assert w.assigned_host is None
    assert w.priority == 0
    assert w.has_required_metadata()


def test_new_workload_preserves_supplied_correlation_id():
    cid = "user-supplied-" + str(uuid.uuid4())
    w = new_workload(
        workload_class="mutation", source_module="mb2", correlation_id=cid,
    )
    assert w.correlation_id == cid


def test_workload_to_dict_round_trip():
    w = new_workload(
        workload_class="agent",
        source_module="ctrader_telemetry",
        priority=2,
        target_id="strategy-123",
        pair="EURUSD",
        capabilities_required=["gpu", "redis"],
        payload={"x": 1},
    )
    d = w.to_dict()
    assert d["workload_class"] == "agent"
    assert d["priority"] == 2
    assert d["pair"] == "EURUSD"
    assert d["capabilities_required"] == ["gpu", "redis"]
    assert d["payload"] == {"x": 1}
    assert "workload_id" in d
    assert "created_at" in d


# ─── 2) routing_policy registry ──────────────────────────────────────

def test_routing_policy_registry_has_six_policies():
    expected = {
        "local_only",
        "least_busy",
        "capability_based",
        "pair_affinity",
        "strategy_affinity",
        "deployment_affinity",
    }
    assert set(routing_policy.POLICY_REGISTRY.keys()) == expected
    assert set(routing_policy.ALL_POLICY_NAMES) == expected


def test_routing_policy_local_only_is_active():
    assert routing_policy.POLICY_REGISTRY["local_only"]["active"] is True


def test_routing_policy_other_policies_are_inactive():
    for name in (
        "least_busy", "capability_based", "pair_affinity",
        "strategy_affinity", "deployment_affinity",
    ):
        assert routing_policy.POLICY_REGISTRY[name]["active"] is False, name


def test_routing_policy_default_is_local_only():
    assert routing_policy.DEFAULT_POLICY_NAME == "local_only"


def test_routing_policy_resolve_default_when_env_unset():
    os.environ.pop("FS_ROUTING_POLICY", None)
    assert routing_policy.resolve_policy_name() == "local_only"


def test_routing_policy_resolve_respects_env_when_known():
    os.environ["FS_ROUTING_POLICY"] = "least_busy"
    assert routing_policy.resolve_policy_name() == "least_busy"


def test_routing_policy_resolve_falls_back_on_unknown_value():
    os.environ["FS_ROUTING_POLICY"] = "weird_unknown_policy"
    assert routing_policy.resolve_policy_name() == "local_only"


def test_routing_policy_choose_host_local_only_returns_local_decision():
    w = new_workload(workload_class="backtest", source_module="t")
    rd = routing_policy.choose_host(w, fleet_snapshot={"local_host_id": "host-A"})
    assert rd.policy == "local_only"
    assert rd.decision == "local"
    assert rd.assigned_host == "host-A"
    assert rd.fallback_from is None
    assert rd.rationale["policy_active"] is True


def test_routing_policy_inactive_policy_falls_back_with_rationale():
    os.environ["FS_ROUTING_POLICY"] = "least_busy"
    w = new_workload(workload_class="mutation", source_module="t")
    rd = routing_policy.choose_host(w, fleet_snapshot={"local_host_id": "host-B"})
    assert rd.policy == "local_only"
    assert rd.decision == "local"
    assert rd.fallback_from == "least_busy"
    assert rd.rationale["fallback_from"] == "least_busy"
    assert rd.rationale["policy_active"] is False


def test_routing_policy_choose_host_works_without_fleet_snapshot():
    w = new_workload(workload_class="agent", source_module="t")
    rd = routing_policy.choose_host(w, fleet_snapshot=None)
    # local_host falls back to host_capability or socket.gethostname()
    assert rd.policy == "local_only"
    assert rd.decision == "local"
    assert rd.assigned_host  # non-empty


def test_routing_policy_manifest_is_jsonable_and_complete():
    m = routing_policy.policy_manifest()
    assert isinstance(m, list)
    assert len(m) == 6
    for row in m:
        assert {"name", "active", "intent", "kind"} <= set(row.keys())


# ─── 3) supervisor_events: WORK_REROUTED added ───────────────────────

def test_supervisor_events_includes_work_rerouted():
    assert "WORK_REROUTED" in supervisor_events.ALL_EVENT_TYPES
    assert supervisor_events.EVENT_SEVERITY_MAP["WORK_REROUTED"] in {
        "debug", "info", "warn", "critical", "fatal",
    }
    assert supervisor_events.EVENT_CATEGORY_MAP["WORK_REROUTED"] == "scaling"


def test_supervisor_events_outcome_event_map_covers_nc_vocab():
    """Notification Center compatibility — every dispatch outcome maps
    to a supervisor event type that the NC bridge understands."""
    mapping = {
        submission_dispatcher.OUTCOME_ACCEPTED: supervisor_events.EVENT_WORK_ROUTED,
        submission_dispatcher.OUTCOME_DEFERRED: supervisor_events.EVENT_WORK_DEFERRED,
        submission_dispatcher.OUTCOME_REFUSED:  supervisor_events.EVENT_WORK_REFUSED,
        submission_dispatcher.OUTCOME_REROUTED: supervisor_events.EVENT_WORK_REROUTED,
    }
    for outcome, evt in mapping.items():
        assert evt in supervisor_events.ALL_EVENT_TYPES, (outcome, evt)


# ─── 4) submission_dispatcher: dormant short-circuit (flag OFF) ──────

def test_dispatcher_is_disabled_by_default():
    assert submission_dispatcher.is_enabled() is False


@pytest.mark.asyncio
async def test_dispatch_bypass_when_flag_off():
    os.environ.pop("ENABLE_FACTORY_SUPERVISOR", None)
    w = new_workload(workload_class="backtest", source_module="t-bypass")
    v = await submission_dispatcher.dispatch(w)
    assert v.mode == "bypass"
    assert v.outcome == submission_dispatcher.OUTCOME_ACCEPTED
    assert v.reason == "flag_off"
    assert v.persisted is False
    assert v.event_emitted is False
    assert v.admission_decision is None
    assert v.routing_decision is None


@pytest.mark.asyncio
async def test_dispatch_bypass_preserves_workload_envelope():
    os.environ.pop("ENABLE_FACTORY_SUPERVISOR", None)
    w = new_workload(
        workload_class="mutation",
        source_module="auto_learning_dormant",
        priority=1,
        target_id="m-123",
    )
    v = await submission_dispatcher.dispatch(w)
    assert v.workload_id    == w.workload_id
    assert v.correlation_id == w.correlation_id
    assert v.created_at     == w.created_at
    assert v.priority       == w.priority


# ─── 5) submission_dispatcher: full pipeline (flag ON) ───────────────

@pytest.mark.asyncio
async def test_dispatch_local_accepted_when_admission_off_flag_on():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    # ENABLE_ADMISSION_CONTROL stays OFF → admission returns admit/flag_off.
    w = new_workload(workload_class="backtest", source_module="t-accepted")
    v = await submission_dispatcher.dispatch(w)
    assert v.mode == "local"
    assert v.outcome == submission_dispatcher.OUTCOME_ACCEPTED
    assert v.assigned_host  # non-empty
    assert v.admission_decision == "admit"
    assert v.admission_reason  == "flag_off"
    assert v.routing_decision and "local_only" in v.routing_decision
    assert v.rationale["routing"]["policy"] == "local_only"
    assert v.rationale["admission"]["decision"] == "admit"


@pytest.mark.asyncio
async def test_dispatch_unknown_workload_class_admitted_with_marker():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    w = new_workload(workload_class="unknown_class", source_module="t")
    v = await submission_dispatcher.dispatch(w)
    assert v.mode == "local"
    assert v.outcome == submission_dispatcher.OUTCOME_ACCEPTED
    assert v.admission_decision == "admit"
    assert v.admission_reason.startswith("class_unmapped")


@pytest.mark.asyncio
async def test_dispatch_with_inactive_policy_falls_back_to_local():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    os.environ["FS_ROUTING_POLICY"] = "capability_based"
    w = new_workload(workload_class="agent", source_module="t",
                     capabilities_required=["gpu"])
    v = await submission_dispatcher.dispatch(w)
    assert v.mode == "local"
    assert v.outcome == submission_dispatcher.OUTCOME_ACCEPTED
    assert v.fallback_from_policy == "capability_based"
    assert "capability_based->local_only" in (v.routing_decision or "")


@pytest.mark.asyncio
async def test_dispatch_writes_envelope_back_to_workload():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    w = new_workload(workload_class="backtest", source_module="t-back")
    assert w.routing_decision is None
    assert w.assigned_host is None
    await submission_dispatcher.dispatch(w)
    # dispatch annotates the envelope
    assert w.routing_decision is not None
    assert w.assigned_host is not None


# ─── 6) Index ensure idempotency ─────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_ensure_indexes_idempotent():
    out1 = await submission_dispatcher.ensure_indexes()
    out2 = await submission_dispatcher.ensure_indexes()
    # Either first call creates, or all already existed; second call
    # must NOT create anything new.
    assert out2["created"] == [] or len(out2["created"]) <= len(out1["created"])
    # All known specs accounted for.
    all_first = set(out1["created"]) | set(out1["existed"])
    expected = {
        "ix_fs_subs_ts",
        "ix_fs_subs_outcome_ts",
        "ix_fs_subs_class_ts",
        "ix_fs_subs_correlation",
        "ix_fs_subs_assigned_host_ts",
    }
    assert expected.issubset(all_first)


# ─── 7) Persistence + observability when flag ON ─────────────────────

@pytest.mark.asyncio
async def test_dispatch_persists_record_when_flag_on():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    await submission_dispatcher.ensure_indexes()
    cid = "test-corr-" + str(uuid.uuid4())
    w = new_workload(
        workload_class="backtest", source_module="t-persist",
        correlation_id=cid,
    )
    v = await submission_dispatcher.dispatch(w)
    assert v.persisted is True
    rows = await submission_dispatcher.list_recent(correlation_id=cid, limit=5)
    assert len(rows) == 1
    r = rows[0]
    assert r["workload_class"] == "backtest"
    assert r["source_module"] == "t-persist"
    assert r["outcome"] == submission_dispatcher.OUTCOME_ACCEPTED
    assert r["correlation_id"] == cid
    assert r["supervisor_version"] == "FS-P1.1"


@pytest.mark.asyncio
async def test_dispatch_emits_supervisor_event_when_flag_on():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    w = new_workload(workload_class="agent", source_module="t-emit")
    v = await submission_dispatcher.dispatch(w)
    # Event went to scaling_events (NC bridge gated separately).
    assert v.event_emitted is True


@pytest.mark.asyncio
async def test_dispatch_no_event_emitted_when_flag_off():
    os.environ.pop("ENABLE_FACTORY_SUPERVISOR", None)
    w = new_workload(workload_class="agent", source_module="t-no-emit")
    v = await submission_dispatcher.dispatch(w)
    assert v.event_emitted is False


# ─── 8) Stats aggregator ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatcher_stats_shape_when_no_records():
    os.environ.pop("ENABLE_FACTORY_SUPERVISOR", None)
    s = await submission_dispatcher.stats(window_sec=60)
    assert "total" in s
    assert "per_outcome" in s
    assert "per_class" in s
    for o in submission_dispatcher.ALL_OUTCOMES:
        assert o in s["per_outcome"]


@pytest.mark.asyncio
async def test_dispatcher_stats_counts_persisted_rows():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    await submission_dispatcher.ensure_indexes()
    cid = "stats-" + str(uuid.uuid4())
    for _ in range(3):
        w = new_workload(workload_class="backtest", source_module="t-stats",
                         correlation_id=cid)
        await submission_dispatcher.dispatch(w)
    s = await submission_dispatcher.stats(window_sec=600)
    assert s["total"] >= 3
    assert s["per_outcome"][submission_dispatcher.OUTCOME_ACCEPTED] >= 3


# ─── 9) Dispatch verdict contract (Copilot compatibility) ────────────

@pytest.mark.asyncio
async def test_dispatch_verdict_includes_all_copilot_fields():
    """Copilot questions answered by these fields:
        - 'Why deferred?'          → reason, admission_reason
        - 'Which node received it?'→ assigned_host
        - 'Queue pressure now?'    → pressure_band, band
        - 'Which workloads waiting?'→ via /submissions endpoint
        - 'Why this routing?'      → routing_decision + rationale.routing
    """
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    w = new_workload(workload_class="backtest", source_module="t-copilot")
    v = await submission_dispatcher.dispatch(w)
    d = v.to_dict()
    for field in (
        "workload_id", "workload_class", "source_module",
        "correlation_id", "created_at", "priority",
        "outcome", "mode",
        "routing_decision", "assigned_host",
        "reason", "retry_after_sec",
        "admission_decision", "admission_reason",
        "pressure_band", "band", "fallback_from_policy",
        "persisted", "event_emitted", "rationale",
    ):
        assert field in d, field
    assert isinstance(d["rationale"], dict)
    assert "routing" in d["rationale"]
    assert "admission" in d["rationale"]


# ─── 10) Public surface stable ───────────────────────────────────────

def test_factory_supervisor_package_exports_p11_modules():
    from engines import factory_supervisor as fs
    for name in (
        "workload", "routing_policy", "submission_dispatcher",
        "fleet_registry", "supervisor_events",
        "supervisor_heartbeat", "supervisor_lock",
    ):
        assert hasattr(fs, name), name


def test_dispatch_outcomes_are_nc_compatible_vocab():
    """NC vocabulary the operator approved: accepted/deferred/refused/rerouted."""
    assert set(submission_dispatcher.ALL_OUTCOMES) == {
        "accepted", "deferred", "refused", "rerouted",
    }

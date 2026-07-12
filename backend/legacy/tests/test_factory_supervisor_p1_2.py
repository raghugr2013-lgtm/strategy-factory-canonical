"""Factory Supervisor FS-P1.2 — Phase 1.2 test suite.

Scope:
  * defer_queue: enqueue / claim / retry / completed / failed / expired
  * defer_queue: exponential backoff schedule
  * defer_queue: required metadata preserved verbatim per operator directive
  * worker_runtime: registry shape; pluggable workers
  * worker_runtime: dormant by default; full pipeline when 3 flags ON
  * remote_transport: provider/transport-neutral interface; HTTP stub
  * supervisor_events: WORK_QUEUED/RETRIED/EXPIRED/COMPLETED first-class
  * dispatcher → defer_queue integration on outcome=deferred
  * indexes idempotent
  * Copilot 5-question read paths
"""
from __future__ import annotations

import os
import uuid

import pytest

from engines.factory_supervisor import (
    defer_queue,
    remote_transport,
    submission_dispatcher,
    supervisor_events,
    worker_runtime,
)
from engines.factory_supervisor.workload import new_workload


# ─── Fixture: isolate state per test ─────────────────────────────────

_FS_FLAGS = (
    "ENABLE_FACTORY_SUPERVISOR",
    "ENABLE_NOTIFICATION_CENTER",
    "ENABLE_ADMISSION_CONTROL",
    "FS_ROUTING_POLICY",
    "FS_ENABLE_DEFER_QUEUE",
    "FS_ENABLE_DEFER_WORKER",
    "FS_DEFER_RETRY_BASE_SEC",
    "FS_DEFER_RETRY_MAX_SEC",
    "FS_DEFER_MAX_RETRIES",
    "FS_DEFER_TTL_SEC",
    "FS_WORKER_POLL_INTERVAL_SEC",
    "FS_REMOTE_TRANSPORT",
    "FS_LEADER_LEASE_TTL_SEC",
    "FS_HEARTBEAT_CADENCE_SEC",
)


@pytest.fixture(autouse=True)
def _isolate_fs_p12():
    saved = {k: os.environ.pop(k, None) for k in _FS_FLAGS}
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


def _enable_fs_and_queue():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"
    os.environ["FS_ENABLE_DEFER_QUEUE"] = "true"


def _enable_full():
    _enable_fs_and_queue()
    os.environ["FS_ENABLE_DEFER_WORKER"] = "true"


# ─── 1) supervisor_events: 4 new types first-class ──────────────────

def test_event_vocab_includes_p12_types():
    for t in ("WORK_QUEUED", "WORK_RETRIED", "WORK_EXPIRED", "WORK_COMPLETED"):
        assert t in supervisor_events.ALL_EVENT_TYPES
        assert t in supervisor_events.EVENT_SEVERITY_MAP
        assert supervisor_events.EVENT_CATEGORY_MAP[t] == "scaling"


def test_event_severity_assignments_match_directive():
    sv = supervisor_events.EVENT_SEVERITY_MAP
    assert sv["WORK_QUEUED"]    == "info"
    assert sv["WORK_RETRIED"]   == "info"
    assert sv["WORK_EXPIRED"]   == "warn"
    assert sv["WORK_COMPLETED"] == "info"
    assert sv["WORK_FAILED"]    == "critical"


# ─── 2) defer_queue dormant by default ──────────────────────────────

def test_defer_queue_disabled_by_default():
    assert defer_queue.is_enabled() is False


@pytest.mark.asyncio
async def test_enqueue_skipped_when_flag_off():
    wl = new_workload(workload_class="backtest", source_module="t")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "test"})
    assert out["enqueued"] is False
    assert out["skipped"] == "flag_off"


# ─── 3) defer_queue: enqueue preserves the FROZEN metadata contract ─

@pytest.mark.asyncio
async def test_enqueue_preserves_required_metadata():
    """Operator directive: every deferred workload should preserve:
    original submission, defer reason, defer timestamp, retry count,
    next eligible retry time, workload class, routing rationale,
    admission rationale."""
    _enable_fs_and_queue()
    await defer_queue.ensure_indexes()
    wl = new_workload(
        workload_class="mutation", source_module="t-meta",
        priority=2, correlation_id="meta-" + uuid.uuid4().hex,
    )
    verdict = {
        "outcome": "deferred",
        "reason":  "band:caution",
        "admission_reason": "band:caution",
        "rationale": {
            "routing":   {"policy": "local_only", "decision": "local"},
            "admission": {"decision": "defer", "reason": "band:caution"},
        },
    }
    out = await defer_queue.enqueue(wl.to_dict(), verdict)
    assert out["enqueued"] is True
    row = out["row"]
    # Required fields per operator directive
    assert row["original_envelope"]["workload_class"] == "mutation"
    assert row["original_envelope"]["correlation_id"] == wl.correlation_id
    assert row["defer_reason"] == "band:caution"
    assert "defer_ts" in row and row["defer_ts"].endswith("+00:00")
    assert row["retry_count"] == 0
    assert row["next_eligible_retry_epoch"] > row["defer_ts_epoch"]
    assert row["workload_class"] == "mutation"
    assert row["routing_rationale"]["policy"] == "local_only"
    assert row["admission_rationale"]["decision"] == "defer"
    assert row["status"] == defer_queue.STATUS_QUEUED
    assert row["supervisor_version"] == "FS-P1.2"


# ─── 4) defer_queue exponential backoff ─────────────────────────────

def test_compute_next_retry_exponential():
    base_ts = 1_000_000.0
    base = defer_queue._retry_base_sec()
    cap  = defer_queue._retry_max_sec()
    e0 = defer_queue.compute_next_retry_epoch(0, base_ts)
    e1 = defer_queue.compute_next_retry_epoch(1, base_ts)
    e2 = defer_queue.compute_next_retry_epoch(2, base_ts)
    e_huge = defer_queue.compute_next_retry_epoch(30, base_ts)
    assert e0 - base_ts == base
    assert e1 - base_ts == base * 2
    assert e2 - base_ts == base * 4
    assert e_huge - base_ts == cap, "backoff must clamp at max"


# ─── 5) defer_queue: claim_due is atomic across workers ─────────────

@pytest.mark.asyncio
async def test_claim_due_marks_status_claimed():
    _enable_fs_and_queue()
    os.environ["FS_DEFER_RETRY_BASE_SEC"] = "1"   # tighten so row is due now
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="backtest", source_module="t-claim")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "test", "rationale": {}})
    row_id = out["row_id"]
    # Force next_eligible_retry_epoch into the past so it's due immediately.
    from engines.db import get_db
    db = get_db()
    await db[defer_queue.DEFER_COLLECTION].update_one(
        {"row_id": row_id},
        {"$set": {"next_eligible_retry_epoch": 0.0}},
    )
    claimed = await defer_queue.claim_due("worker-A", batch=4)
    assert any(r["row_id"] == row_id for r in claimed)
    refetched = await defer_queue.get_row(row_id)
    assert refetched["status"] == defer_queue.STATUS_CLAIMED
    assert refetched["claimed_by_worker_id"] == "worker-A"


@pytest.mark.asyncio
async def test_claim_due_skips_not_yet_due_rows():
    _enable_fs_and_queue()
    os.environ["FS_DEFER_RETRY_BASE_SEC"] = "3600"  # 1h delay
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="agent", source_module="t-not-due")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "test", "rationale": {}})
    claimed = await defer_queue.claim_due("worker-B", batch=4)
    row_ids = {r["row_id"] for r in claimed}
    assert out["row_id"] not in row_ids


# ─── 6) defer_queue: retry → backoff → max → failed ─────────────────

@pytest.mark.asyncio
async def test_mark_retry_increments_count_and_reschedules():
    _enable_fs_and_queue()
    os.environ["FS_DEFER_RETRY_BASE_SEC"] = "5"
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="backtest", source_module="t-retry")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "test", "rationale": {}})
    row_id = out["row_id"]
    ok = await defer_queue.mark_retry(row_id,
        {"outcome": "deferred", "reason": "still_deferred"})
    assert ok is True
    r = await defer_queue.get_row(row_id)
    assert r["retry_count"] == 1
    assert r["status"] == defer_queue.STATUS_QUEUED
    assert r["claimed_by_worker_id"] is None
    assert r["last_block_reason"] == "still_deferred"
    assert len(r["history"]) == 1
    assert r["history"][0]["attempt"] == 1


@pytest.mark.asyncio
async def test_mark_retry_fails_after_max_retries():
    _enable_fs_and_queue()
    os.environ["FS_DEFER_MAX_RETRIES"] = "2"
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="backtest", source_module="t-maxretry")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "test", "rationale": {}})
    row_id = out["row_id"]
    await defer_queue.mark_retry(row_id, {"outcome": "deferred", "reason": "x"})
    await defer_queue.mark_retry(row_id, {"outcome": "deferred", "reason": "x"})
    await defer_queue.mark_retry(row_id, {"outcome": "deferred", "reason": "x"})
    r = await defer_queue.get_row(row_id)
    assert r["status"] == defer_queue.STATUS_FAILED
    assert r["last_block_reason"] in ("x", "max_retries_exceeded")
    assert r["retry_count"] >= 3


# ─── 7) defer_queue terminal marks ───────────────────────────────────

@pytest.mark.asyncio
async def test_mark_completed_terminal():
    _enable_fs_and_queue()
    wl = new_workload(workload_class="backtest", source_module="t-comp")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "x", "rationale": {}})
    ok = await defer_queue.mark_completed(out["row_id"], detail={"x": 1})
    assert ok is True
    r = await defer_queue.get_row(out["row_id"])
    assert r["status"] == defer_queue.STATUS_COMPLETED


@pytest.mark.asyncio
async def test_mark_failed_records_reason():
    _enable_fs_and_queue()
    wl = new_workload(workload_class="backtest", source_module="t-fail")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "x", "rationale": {}})
    ok = await defer_queue.mark_failed(out["row_id"], reason="boom")
    assert ok is True
    r = await defer_queue.get_row(out["row_id"])
    assert r["status"] == defer_queue.STATUS_FAILED
    assert r["last_block_reason"] == "boom"


@pytest.mark.asyncio
async def test_cancel_marks_failed_cancelled():
    _enable_fs_and_queue()
    wl = new_workload(workload_class="backtest", source_module="t-cancel")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "x", "rationale": {}})
    ok = await defer_queue.cancel(out["row_id"])
    assert ok is True
    r = await defer_queue.get_row(out["row_id"])
    assert r["status"] == defer_queue.STATUS_FAILED
    assert r["last_block_reason"] == "cancelled"


@pytest.mark.asyncio
async def test_expire_overdue_marks_old_rows():
    _enable_fs_and_queue()
    os.environ["FS_DEFER_TTL_SEC"] = "60"
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="backtest", source_module="t-expire")
    out = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "x", "rationale": {}})
    # Backdate the row past the TTL window.
    from engines.db import get_db
    db = get_db()
    await db[defer_queue.DEFER_COLLECTION].update_one(
        {"row_id": out["row_id"]},
        {"$set": {"defer_ts_epoch": 0.0}},
    )
    n = await defer_queue.expire_overdue()
    assert n >= 1
    r = await defer_queue.get_row(out["row_id"])
    assert r["status"] == defer_queue.STATUS_EXPIRED


# ─── 8) Index idempotency ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_defer_queue_ensure_indexes_idempotent():
    o1 = await defer_queue.ensure_indexes()
    o2 = await defer_queue.ensure_indexes()
    assert o2["created"] == [] or len(o2["created"]) <= len(o1["created"])
    expected = {
        "ix_fs_defer_status_next",
        "ix_fs_defer_ts",
        "ix_fs_defer_workload_id",
        "ix_fs_defer_correlation",
        "ix_fs_defer_class_status",
        "ix_fs_defer_worker_status",
    }
    assert expected.issubset(set(o1["created"]) | set(o1["existed"]))


# ─── 9) Stats shape + counts ────────────────────────────────────────

@pytest.mark.asyncio
async def test_defer_queue_stats_shape():
    s = await defer_queue.stats(window_sec=60)
    for k in ("window_sec", "total", "per_status", "limits"):
        assert k in s
    for st in defer_queue.ALL_STATUSES:
        assert st in s["per_status"]
    for k in ("retry_base_sec", "retry_max_sec", "max_retries", "ttl_sec"):
        assert k in s["limits"]


@pytest.mark.asyncio
async def test_defer_queue_stats_counts():
    _enable_fs_and_queue()
    await defer_queue.ensure_indexes()
    for i in range(3):
        wl = new_workload(workload_class="backtest", source_module="t-stats")
        await defer_queue.enqueue(wl.to_dict(),
            {"outcome": "deferred", "reason": "x", "rationale": {}})
    s = await defer_queue.stats(window_sec=600)
    assert s["total"] >= 3
    assert s["per_status"][defer_queue.STATUS_QUEUED] >= 3


# ─── 10) Dispatcher → defer_queue integration ───────────────────────

@pytest.mark.asyncio
async def test_dispatcher_enqueues_on_deferred_outcome_when_flag_on(monkeypatch):
    _enable_fs_and_queue()
    await defer_queue.ensure_indexes()

    # Force dispatcher to see admission.decision="defer".
    async def fake_admission(workload_class, force=False):
        return {
            "decision": "defer", "reason": "band:caution",
            "pressure_band": "caution",
            "retry_after_sec": 30,
        }
    monkeypatch.setattr(submission_dispatcher,
        "_run_admission", fake_admission)

    wl = new_workload(workload_class="backtest", source_module="t-dispenq")
    v = await submission_dispatcher.dispatch(wl)
    assert v.outcome == submission_dispatcher.OUTCOME_DEFERRED
    assert v.rationale.get("defer_queue", {}).get("enqueued") is True
    row_id = v.rationale["defer_queue"]["row_id"]
    r = await defer_queue.get_row(row_id)
    assert r["original_envelope"]["correlation_id"] == wl.correlation_id
    assert r["routing_rationale"]["policy"] == "local_only"
    assert r["admission_rationale"]["decision"] == "defer"


@pytest.mark.asyncio
async def test_dispatcher_does_not_enqueue_when_queue_flag_off(monkeypatch):
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"   # queue flag stays OFF

    async def fake_admission(workload_class, force=False):
        return {"decision": "defer", "reason": "test"}
    monkeypatch.setattr(submission_dispatcher,
        "_run_admission", fake_admission)

    wl = new_workload(workload_class="backtest", source_module="t-noenq")
    v = await submission_dispatcher.dispatch(wl)
    assert v.outcome == submission_dispatcher.OUTCOME_DEFERRED
    dq = v.rationale.get("defer_queue", {})
    assert dq.get("enqueued") is False
    assert dq.get("skipped") == "flag_off"


# ─── 11) worker_runtime: registry + manifest ─────────────────────────

def test_worker_registry_completeness():
    expected = {
        "local_executor",
        "multi_node_executor",
        "ctrader_telemetry_worker",
        "auto_learning_worker",
        "notification_center_worker",
        "copilot_context_refresh",
    }
    assert set(worker_runtime.WORKER_REGISTRY.keys()) == expected
    assert set(worker_runtime.ALL_WORKER_NAMES) == expected


def test_worker_local_executor_is_active():
    assert worker_runtime.WORKER_REGISTRY["local_executor"]["active"] is True


def test_workers_inactive_by_default():
    for n in ("multi_node_executor", "ctrader_telemetry_worker",
              "auto_learning_worker", "notification_center_worker",
              "copilot_context_refresh"):
        assert worker_runtime.WORKER_REGISTRY[n]["active"] is False, n


def test_worker_manifest_is_jsonable():
    m = worker_runtime.worker_manifest()
    assert isinstance(m, list) and len(m) == 6
    for entry in m:
        assert {"name", "active", "handles", "intent"} <= set(entry.keys())


def test_worker_id_is_stable_per_process():
    assert worker_runtime.worker_id() == worker_runtime.worker_id()


# ─── 12) worker_runtime: dormant + active pipeline ──────────────────

def test_worker_runtime_disabled_by_default():
    assert worker_runtime.is_enabled() is False


@pytest.mark.asyncio
async def test_worker_runtime_noop_when_disabled():
    out = await worker_runtime.claim_and_run_once(batch=4)
    assert out == []


@pytest.mark.asyncio
async def test_worker_runtime_drains_due_row_when_all_flags_on():
    _enable_full()
    os.environ["FS_DEFER_RETRY_BASE_SEC"] = "1"
    await defer_queue.ensure_indexes()
    wl = new_workload(workload_class="backtest", source_module="t-drain")
    enq = await defer_queue.enqueue(wl.to_dict(),
        {"outcome": "deferred", "reason": "x", "rationale": {}})
    # Make the row immediately due.
    from engines.db import get_db
    db = get_db()
    await db[defer_queue.DEFER_COLLECTION].update_one(
        {"row_id": enq["row_id"]},
        {"$set": {"next_eligible_retry_epoch": 0.0}},
    )
    results = await worker_runtime.claim_and_run_once(batch=4)
    assert any(r["row_id"] == enq["row_id"] for r in results)
    r = await defer_queue.get_row(enq["row_id"])
    assert r["status"] == defer_queue.STATUS_COMPLETED


# ─── 13) remote_transport: provider/transport-neutral interface ─────

def test_remote_transport_registry_contains_http_and_none():
    assert "none" in remote_transport.TRANSPORT_REGISTRY
    assert "http" in remote_transport.TRANSPORT_REGISTRY


def test_remote_transport_default_is_none():
    t = remote_transport.resolve_transport()
    assert t.name == "none"


def test_remote_transport_resolves_to_http_when_flagged():
    os.environ["FS_REMOTE_TRANSPORT"] = "http"
    t = remote_transport.resolve_transport()
    assert t.name == "http"


def test_remote_transport_unknown_falls_back_to_none():
    os.environ["FS_REMOTE_TRANSPORT"] = "weird"
    t = remote_transport.resolve_transport()
    assert t.name == "none"


@pytest.mark.asyncio
async def test_remote_transport_http_stub_returns_not_connected():
    os.environ["FS_REMOTE_TRANSPORT"] = "http"
    t = remote_transport.resolve_transport()
    res = await t.submit({"workload_class": "x"}, target_host="some-host")
    d = res.to_dict()
    assert d["transport"] == "http"
    assert d["accepted"] is False
    assert d["soft_defer"] is True
    assert d["error"] == "http_transport_stub_FS_P1_2"


@pytest.mark.asyncio
async def test_remote_transport_healthcheck_shape():
    os.environ["FS_REMOTE_TRANSPORT"] = "http"
    t = remote_transport.resolve_transport()
    h = await t.healthcheck()
    assert h["transport"] == "http"
    assert h["status"] == "stub_only"


# ─── 14) Copilot 5-question contract ─────────────────────────────────

@pytest.mark.asyncio
async def test_copilot_can_answer_what_is_waiting(monkeypatch):
    """List rows by status='queued'."""
    _enable_fs_and_queue()
    await defer_queue.ensure_indexes()
    cid = "copilot-" + uuid.uuid4().hex
    async def fake_admission(workload_class, force=False):
        return {"decision": "defer", "reason": "band:caution"}
    monkeypatch.setattr(submission_dispatcher, "_run_admission", fake_admission)
    wl = new_workload(workload_class="backtest", source_module="t-copilot",
                      correlation_id=cid)
    await submission_dispatcher.dispatch(wl)
    rows = await defer_queue.list_rows(
        status=defer_queue.STATUS_QUEUED, correlation_id=cid, limit=5,
    )
    assert len(rows) == 1
    r = rows[0]
    # Q1: What is waiting? → row exists with status=queued
    assert r["status"] == defer_queue.STATUS_QUEUED
    # Q2: Why is it waiting?
    assert r["defer_reason"] == "band:caution"
    assert r["admission_rationale"]["decision"] == "defer"
    # Q3: When will it retry?
    assert r["next_eligible_retry_epoch"] > r["defer_ts_epoch"]
    # Q4: Which worker owns it? (None pre-claim — claim populates it)
    assert "claimed_by_worker_id" in r
    # Q5: What is blocking execution?
    assert r["last_block_reason"] == "band:caution"


# ─── 15) Package surface stability ───────────────────────────────────

def test_package_exports_p12_modules():
    from engines import factory_supervisor as fs
    for name in ("defer_queue", "remote_transport", "worker_runtime"):
        assert hasattr(fs, name), name


def test_outcome_to_event_map_covers_p12_nc_vocab():
    """Notification Center vocab per operator directive:
    queued/retried/expired/completed/failed must all be first-class."""
    for evt in ("WORK_QUEUED", "WORK_RETRIED", "WORK_EXPIRED",
                "WORK_COMPLETED", "WORK_FAILED"):
        assert evt in supervisor_events.ALL_EVENT_TYPES

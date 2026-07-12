"""
Factory Supervisor FS-P1.0 — Operator API surface.

Phase 1.0 ships read-only observability + lock-management endpoints:

  GET  /api/factory-supervisor/fleet            — multi-host snapshot
  GET  /api/factory-supervisor/lock             — current lease holder
  POST /api/factory-supervisor/lock/release     — force-release (admin)
  GET  /api/factory-supervisor/heartbeat-status — verdict band per host
  GET  /api/factory-supervisor/events           — recent supervisor events
  GET  /api/factory-supervisor/events/stats     — per-type counts
  GET  /api/factory-supervisor/status           — service self-report

Routing/submission/queue endpoints land in FS-P1.1+. All endpoints are
auth-gated. Writes (lock release) require admin.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import get_current_user
from engines.factory_supervisor import (
    architect_advisor,
    auto_learning,
    copilot_advanced,
    copilot_context,
    copilot_operational,
    defer_queue,
    eligibility_signals,
    fag_proposals,
    fleet_registry,
    llm_adapter_base,
    notification_center,
    recommendation_engine,
    remote_transport,
    routing_policy,
    submission_dispatcher,
    supervisor_events,
    supervisor_heartbeat,
    supervisor_lock,
    system_state_view,
    worker_runtime,
    worker_scheduler,
)
from engines.factory_supervisor.workload import new_workload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/factory-supervisor", tags=["factory-supervisor"])


def _is_admin(user: Dict[str, Any]) -> bool:
    role = (user or {}).get("role") or ""
    return str(role).lower() in {"admin", "owner", "superadmin"}


def _require_admin(user: Dict[str, Any]) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="admin role required")


# ─── Read endpoints ──────────────────────────────────────────────────


@router.get("/status")
async def status_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lightweight self-report. Always 200; carries the supervisor's
    enablement state."""
    return {
        "service":                "factory_supervisor",
        "phase":                  "FS-P1.4",
        "enabled":                supervisor_events.is_enabled(),
        "notification_center":    supervisor_events.notification_center_enabled(),
        "event_types":            list(supervisor_events.ALL_EVENT_TYPES),
        "routing_policy":         {
            "active":   routing_policy.resolve_policy_name(),
            "default":  routing_policy.DEFAULT_POLICY_NAME,
            "manifest": routing_policy.policy_manifest(),
        },
        "dispatch_outcomes":      list(submission_dispatcher.ALL_OUTCOMES),
        "defer_queue": {
            "enabled":       defer_queue.is_enabled(),
            "statuses":      list(defer_queue.ALL_STATUSES),
            "collection":    defer_queue.DEFER_COLLECTION,
        },
        "worker_runtime": {
            "enabled":  worker_runtime.is_enabled(),
            "worker_id": worker_runtime.worker_id(),
            "workers":  worker_runtime.worker_manifest(),
        },
        "remote_transport": remote_transport.transport_manifest(),
        "system_state_view": {
            "enabled":   system_state_view.is_enabled(),
        },
        "architect_dashboard": {
            "enabled":   architect_advisor.is_enabled(),
        },
        "worker_scheduler": worker_scheduler.status(),
        "notification_center_api": {
            "enabled":   notification_center.is_enabled(),
            "statuses":  list(notification_center.ALL_STATUSES),
        },
        # ── FS-P1.4 surface ─────────────────────────────────────────
        "recommendation_engine": {
            "enabled":   recommendation_engine.is_enabled(),
        },
        "eligibility_engine": {
            "enabled":   eligibility_signals.is_enabled(),
            "features":  eligibility_signals.list_features(),
        },
        "fag_engine": {
            "enabled":     fag_proposals.is_enabled(),
            "states":      list(fag_proposals.ALL_STATES),
            "collection":  fag_proposals.PROPOSAL_COLLECTION,
        },
        "copilot_operational": {
            "enabled":     copilot_operational.is_enabled(),
            "canonical_questions": list(copilot_operational.CANONICAL_QUESTIONS),
        },
        "copilot_advanced":    copilot_advanced.provider_manifest(),
        "auto_learning": {
            "enabled":         auto_learning.is_enabled(),
            "loop_enabled":    auto_learning.is_loop_enabled(),
            "operator_directive": "off",
            "components": [
                "risk_of_ruin",
                "lifecycle_decay",
                "calibration_framework",
                "execution_realism_defaults",
            ],
            "flags":           auto_learning.flag_manifest(),
        },
    }


@router.get("/fleet")
async def fleet_endpoint(
    refresh: bool = Query(False, description="Bypass 5-s cache."),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Multi-host fleet snapshot. Read-only; no side effects."""
    return await fleet_registry.snapshot(refresh=refresh, window_sec=window_sec)


@router.get("/lock")
async def lock_endpoint(
    lock_name: str = Query(supervisor_lock.LOCK_NAME_LEADER, min_length=1, max_length=64),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Current lease holder for the named lock. None if no holder."""
    doc = await supervisor_lock.current_holder(lock_name)
    return {
        "lock_name": lock_name,
        "holder":    doc,
    }


@router.get("/heartbeat-status")
async def heartbeat_status_endpoint(
    host_id: Optional[str] = Query(None, description="Default = local host_id."),
    cadence_sec: Optional[int] = Query(None, ge=5, le=600),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Classify the Supervisor's liveness for the given host."""
    return await supervisor_heartbeat.verdict_band(host_id=host_id, cadence_sec=cadence_sec)


@router.get("/heartbeats")
async def heartbeats_endpoint(
    limit: int = Query(50, ge=1, le=500),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Recent supervisor heartbeats. Diagnostic; not sensitive."""
    rows = await supervisor_heartbeat.list_recent(limit=limit)
    return {"count": len(rows), "rows": rows}


@router.get("/events")
async def events_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    event_type: Optional[str] = Query(None),
    since_epoch: Optional[float] = Query(None, ge=0),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List recent supervisor events from the scaling_events stream."""
    rows = await supervisor_events.list_events(
        limit=limit,
        event_type=event_type,
        since_epoch=since_epoch,
    )
    return {"count": len(rows), "rows": rows}


@router.get("/events/stats")
async def events_stats_endpoint(
    window_sec: int = Query(3600, ge=60, le=2592000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-event-type counts in the window."""
    return await supervisor_events.stats(window_sec=window_sec)


# ─── Admin endpoints (write) ─────────────────────────────────────────


class LockReleasePayload(BaseModel):
    lock_name: str = Field(
        default=supervisor_lock.LOCK_NAME_LEADER,
        min_length=1,
        max_length=64,
    )
    force: bool = Field(
        default=False,
        description=(
            "If true, bypass the holder-host-id check and delete the row "
            "outright (use for split-brain recovery)."
        ),
    )
    actor_host_id: Optional[str] = Field(
        default=None,
        description="The host_id that claims to hold the lease; required when force=false.",
    )


@router.post("/lock/release")
async def lock_release_endpoint(
    payload: LockReleasePayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Release the named lock. Two modes:

      * Cooperative (default): caller must specify `actor_host_id` and the
        lock must currently be held by that host. Returns 409 otherwise.
      * Forced: `force=true` deletes the row regardless of holder; audit-
        logged with `force_override=true`.

    Either way the operation is admin-gated and a `SUPERVISOR_LEADER_CONFLICT`
    notification is emitted when force=true so the operator audit trail is
    complete.
    """
    _require_admin(user)

    if payload.force:
        try:
            from engines.db import get_db
            db = get_db()
            result = await db[supervisor_lock.COLLECTION].delete_one(
                {"_id": payload.lock_name}
            )
            deleted = result.deleted_count > 0
        except Exception as e:                                 # pragma: no cover
            raise HTTPException(status_code=500, detail=f"db_error: {str(e)[:200]}")
        # Best-effort audit event (only emits when supervisor flag is on).
        await supervisor_events.emit(
            supervisor_events.EVENT_SUPERVISOR_LEADER_CONFLICT,
            payload={
                "reason":         "force_release",
                "lock_name":      payload.lock_name,
                "actor_user":     (user or {}).get("email") or (user or {}).get("user_id"),
                "force_override": True,
            },
        )
        return {"released": deleted, "mode": "force", "lock_name": payload.lock_name}

    # Cooperative path
    if not payload.actor_host_id:
        raise HTTPException(
            status_code=400,
            detail="actor_host_id required when force=false",
        )
    released = await supervisor_lock.release(
        host_id=payload.actor_host_id,
        lock_name=payload.lock_name,
    )
    if not released:
        # Either Mongo blip or caller is not the holder.
        holder = await supervisor_lock.current_holder(payload.lock_name)
        raise HTTPException(
            status_code=409,
            detail={
                "released":  False,
                "reason":    "not_holder_or_no_row",
                "holder":    holder,
            },
        )
    return {"released": True, "mode": "cooperative", "lock_name": payload.lock_name}



# ─── FS-P1.1: Submission dispatcher endpoints ────────────────────────


class SubmitPayload(BaseModel):
    workload_class: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="One of the engines.workload_classes.WorkloadClass values.",
    )
    source_module: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Caller identifier (e.g. 'auto_factory', 'mb2', 'auto_learning_dormant').",
    )
    priority: int = Field(default=0, ge=-10, le=10)
    correlation_id: Optional[str] = Field(default=None, max_length=128)
    target_id: Optional[str] = Field(default=None, max_length=128)
    pair: Optional[str] = Field(default=None, max_length=64)
    strategy_id: Optional[str] = Field(default=None, max_length=128)
    deployment_id: Optional[str] = Field(default=None, max_length=128)
    deadline_epoch: Optional[float] = Field(default=None, ge=0)
    capabilities_required: Optional[list] = Field(default=None)
    payload: Optional[Dict[str, Any]] = Field(default=None)
    force: bool = Field(
        default=False,
        description="Admin-only: bypass admission band/cap gates.",
    )


@router.post("/submit")
async def submit_endpoint(
    payload: SubmitPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Submit one workload through the Supervisor dispatch pipeline.

    The dispatcher composes:
      routing_policy.choose_host → admission_controller.gate →
      supervisor_events.emit (WORK_ROUTED / WORK_DEFERRED / WORK_REFUSED /
      WORK_REROUTED) → persistence to factory_supervisor_submissions.

    Behaviour:
      * ENABLE_FACTORY_SUPERVISOR=false (default) ⇒ the dispatcher
        returns mode='bypass' / outcome='accepted'. No persistence,
        no event, no admission consultation. Caller must continue to
        use the legacy P1.D admission_wrapper.
      * ENABLE_FACTORY_SUPERVISOR=true ⇒ full pipeline; verdict mirrors
        admission decision (admit→accepted / defer→deferred /
        refuse→refused). Multi-node assignments yield mode='remote_stub'
        and outcome='rerouted' (the HTTP-RPC submit itself is FS-P1.2).
    """
    if payload.force:
        _require_admin(user)
    wl = new_workload(
        workload_class        = payload.workload_class,
        source_module         = payload.source_module,
        priority              = payload.priority,
        correlation_id        = payload.correlation_id,
        target_id             = payload.target_id,
        pair                  = payload.pair,
        strategy_id           = payload.strategy_id,
        deployment_id         = payload.deployment_id,
        deadline_epoch        = payload.deadline_epoch,
        capabilities_required = payload.capabilities_required,
        payload               = payload.payload,
    )
    verdict = await submission_dispatcher.dispatch(wl, force=payload.force)
    return {
        "workload": wl.to_dict(),
        "verdict":  verdict.to_dict(),
    }


@router.get("/submissions")
async def submissions_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    outcome: Optional[str] = Query(None),
    workload_class: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    since_epoch: Optional[float] = Query(None, ge=0),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List recent submission records persisted by the dispatcher."""
    rows = await submission_dispatcher.list_recent(
        limit=limit,
        outcome=outcome,
        workload_class=workload_class,
        correlation_id=correlation_id,
        since_epoch=since_epoch,
    )
    return {"count": len(rows), "rows": rows}


@router.get("/submissions/stats")
async def submissions_stats_endpoint(
    window_sec: int = Query(3600, ge=60, le=2592000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-outcome + per-class counts within the rolling window."""
    return await submission_dispatcher.stats(window_sec=window_sec)


@router.get("/routing-policy")
async def routing_policy_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Routing policy manifest + active selection (Copilot input)."""
    return {
        "active":   routing_policy.resolve_policy_name(),
        "default":  routing_policy.DEFAULT_POLICY_NAME,
        "manifest": routing_policy.policy_manifest(),
    }



# ─── FS-P1.2: Defer queue + worker runtime endpoints ─────────────────


@router.get("/defer-queue")
async def defer_queue_list_endpoint(
    limit:          int           = Query(100, ge=1, le=1000),
    status:         Optional[str] = Query(None),
    workload_class: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    since_epoch:    Optional[float] = Query(None, ge=0),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List defer-queue rows (Copilot: "What is waiting?")."""
    if status is not None and status not in defer_queue.ALL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {defer_queue.ALL_STATUSES}",
        )
    rows = await defer_queue.list_rows(
        limit=limit,
        status=status,
        workload_class=workload_class,
        correlation_id=correlation_id,
        since_epoch=since_epoch,
    )
    return {"count": len(rows), "rows": rows}


@router.get("/defer-queue/stats")
async def defer_queue_stats_endpoint(
    window_sec: int = Query(3600, ge=60, le=2592000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-status counts + retry limits (Copilot: "How big is the backlog?")."""
    return await defer_queue.stats(window_sec=window_sec)


@router.get("/defer-queue/{row_id}")
async def defer_queue_get_endpoint(
    row_id: str,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fetch one row, including rationale + history (Copilot: "Why
    is it waiting? When will it retry? Which worker owns it?")."""
    row = await defer_queue.get_row(row_id)
    if not row:
        raise HTTPException(status_code=404, detail="row_not_found")
    return row


class DeferCancelPayload(BaseModel):
    row_id: str = Field(..., min_length=1, max_length=128)


@router.post("/defer-queue/cancel")
async def defer_queue_cancel_endpoint(
    payload: DeferCancelPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin: cancel a queued/claimed row (marks status=failed,
    reason=cancelled, emits WORK_FAILED)."""
    _require_admin(user)
    ok = await defer_queue.cancel(payload.row_id)
    return {"row_id": payload.row_id, "cancelled": bool(ok)}


@router.post("/defer-queue/expire-overdue")
async def defer_queue_expire_endpoint(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin: mark all TTL-overdue rows expired (emits WORK_EXPIRED)."""
    _require_admin(user)
    n = await defer_queue.expire_overdue()
    return {"expired": n}


@router.get("/workers")
async def workers_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Worker registry manifest + active selection (Copilot input)."""
    return {
        "enabled":  worker_runtime.is_enabled(),
        "worker_id": worker_runtime.worker_id(),
        "workers":  worker_runtime.worker_manifest(),
    }


@router.post("/workers/tick")
async def workers_tick_endpoint(
    batch: int = Query(8, ge=1, le=64),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin: run a single worker poll iteration.

    Useful for operator-driven smoke checks BEFORE the worker is
    activated via FS_ENABLE_DEFER_WORKER. Returns the list of rows
    processed in this tick."""
    _require_admin(user)
    results = await worker_runtime.claim_and_run_once(batch=batch)
    return {"processed": len(results), "results": results}


@router.get("/remote-transport")
async def remote_transport_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Remote-submit transport manifest + healthcheck."""
    transport = remote_transport.resolve_transport()
    health = await transport.healthcheck()
    return {
        "manifest":    remote_transport.transport_manifest(),
        "healthcheck": health,
    }


# ─── FS-P1.3 — system_state_view + Architect dashboard ────────────────


@router.get("/system-state-view")
async def system_state_view_endpoint(
    refresh: bool = Query(False, description="Bypass 5 s in-process cache."),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — authoritative read model.

    Composes a JSON-serialisable snapshot from every supervisor
    subsystem: fleet, queue pressure, submissions, defer queue,
    notifications, scaling events, admission, workers, routing,
    remote_transport, deployment readiness, and a curated feature_flags
    slice. Read-only / safe.

    The snapshot carries `advisory_only=true` when
    `FS_ENABLE_SYSTEM_STATE_VIEW` is OFF — downstream consumers
    (Copilot, FAG, Auto-Learning readiness) MUST honour that field.
    """
    return await system_state_view.snapshot(refresh=refresh, window_sec=window_sec)


@router.get("/architect/dashboard")
async def architect_dashboard_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — Architect Dashboard payload.

    READ-ONLY. The Architect has zero execution authority. Returns the
    full dashboard contract: recommended action, recommendations list,
    sections (fleet/queue/submissions/defer/notifications/scaling/
    admission/workers/routing/deployment), blockers, healthy systems,
    inactive workers/flags, activation-ready features.
    """
    snap = await system_state_view.snapshot(refresh=refresh, window_sec=window_sec)
    return architect_advisor.dashboard_payload(snap)


@router.get("/architect/recommended-action")
async def architect_recommended_action_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — single top-priority Next Recommended Action."""
    snap = await system_state_view.snapshot(refresh=refresh, window_sec=window_sec)
    rec = architect_advisor.recommended_action(snap)
    return {
        "evaluated_at":        snap.get("evaluated_at"),
        "advisory_only":       bool(snap.get("advisory_only", True)),
        "system_health":       snap.get("system_health"),
        "recommended_action":  rec.to_dict(),
    }


# ─── FS-P1.3 — Notification Center read API ───────────────────────────


@router.get("/notifications")
async def notifications_list_endpoint(
    limit: int = Query(100, ge=1, le=1000),
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    since_epoch: Optional[float] = Query(None),
    target_id: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — list notifications with operator-mandated filters
    (severity / category / status / event_type / since / target /
    correlation). Time-sorted desc."""
    rows = await notification_center.list_notifications(
        limit=limit,
        severity=severity,
        category=category,
        status=status,
        event_type=event_type,
        since_epoch=since_epoch,
        target_id=target_id,
        correlation_id=correlation_id,
    )
    return {
        "enabled": notification_center.is_enabled(),
        "count":   len(rows),
        "rows":    rows,
    }


@router.get("/notifications/unread-count")
async def notifications_unread_count_endpoint(
    severity: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — unread (status='new') notification count, optionally
    filtered by severity / category for priority badges."""
    n = await notification_center.unread_count(severity=severity, category=category)
    return {
        "enabled":      notification_center.is_enabled(),
        "unread_count": n,
        "severity":     severity,
        "category":     category,
    }


@router.get("/notifications/stats")
async def notifications_stats_endpoint(
    window_sec: int = Query(3600, ge=60, le=86400 * 30),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — per-severity / per-category / per-status counts."""
    return await notification_center.stats(window_sec=window_sec)


class _AcknowledgeBody(BaseModel):
    notification_ids: list = Field(default_factory=list)


@router.post("/notifications/acknowledge")
async def notifications_acknowledge_endpoint(
    body: _AcknowledgeBody,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — acknowledge one or more notifications. Idempotent.
    Auth-required (any authenticated user); admin not required."""
    return await notification_center.acknowledge(
        notification_ids=list(body.notification_ids or []),
        user=user,
    )


@router.post("/notifications/archive")
async def notifications_archive_endpoint(
    body: _AcknowledgeBody,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — archive (hide) one or more notifications. Admin only."""
    _require_admin(user)
    return await notification_center.archive(
        notification_ids=list(body.notification_ids or []),
        user=user,
    )


@router.get("/notifications/{notification_id}")
async def notifications_get_endpoint(
    notification_id: str,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — single notification by id."""
    row = await notification_center.get_notification(notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return row


# ─── FS-P1.3 — Worker scheduler ───────────────────────────────────────


@router.get("/scheduler/status")
async def scheduler_status_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — persistent scheduler status (per-task running state,
    last-tick outcomes, error counts). Read-only."""
    return worker_scheduler.status()


@router.post("/scheduler/start")
async def scheduler_start_endpoint(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — admin start the background scheduler. Idempotent;
    no-op if the master flag is OFF."""
    _require_admin(user)
    return worker_scheduler.start()


@router.post("/scheduler/stop")
async def scheduler_stop_endpoint(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.3 — admin stop the background scheduler. Idempotent."""
    _require_admin(user)
    return worker_scheduler.stop()


# ─── FS-P1.4 — Recommendation engine ─────────────────────────────────


@router.get("/recommendations")
async def recommendations_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — full recommendation list (architect + cross-collection).

    Read-only. The engine consumes only the `CopilotContext`; downstream
    consumers must honour `advisory_only` when consumption is gated OFF.
    """
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    recs = await recommendation_engine.evaluate(ctx)
    return {
        "advisory_only":  ctx.advisory_only or not recommendation_engine.is_enabled(),
        "evaluated_at":   ctx.evaluated_at,
        "system_health":  ctx.system_health,
        "count":          len(recs),
        "recommendations": [r.to_dict() for r in recs],
    }


@router.get("/recommendations/top")
async def recommendations_top_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — top single recommendation across all rule families."""
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    rec = await recommendation_engine.top_recommendation(ctx)
    return {
        "advisory_only":  ctx.advisory_only or not recommendation_engine.is_enabled(),
        "evaluated_at":   ctx.evaluated_at,
        "system_health":  ctx.system_health,
        "top":            rec.to_dict(),
    }


# ─── FS-P1.4 — Eligibility signals ───────────────────────────────────


@router.get("/eligibility")
async def eligibility_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — eligibility verdict for every registered feature."""
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    verdicts = eligibility_signals.evaluate_all(ctx)
    return {
        "advisory_only":  ctx.advisory_only or not eligibility_signals.is_enabled(),
        "evaluated_at":   ctx.evaluated_at,
        "features":       eligibility_signals.list_features(),
        "verdicts":       [v.to_dict() for v in verdicts],
    }


@router.get("/eligibility/{feature_name}")
async def eligibility_one_endpoint(
    feature_name: str,
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — eligibility verdict for one feature."""
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    verdict = eligibility_signals.evaluate(feature_name, ctx)
    return {
        "advisory_only":  ctx.advisory_only or not eligibility_signals.is_enabled(),
        "evaluated_at":   ctx.evaluated_at,
        "verdict":        verdict.to_dict(),
    }


# ─── FS-P1.4 — Feature Activation Governance (FAG) ───────────────────


class _FagObservePayload(BaseModel):
    feature_name: str = Field(..., min_length=1, max_length=128)


class _FagIdPayload(BaseModel):
    proposal_id: str = Field(..., min_length=1, max_length=128)


class _FagRejectPayload(BaseModel):
    proposal_id: str = Field(..., min_length=1, max_length=128)
    reason:      str = Field(default="", max_length=500)


@router.get("/fag/proposals")
async def fag_proposals_list_endpoint(
    state:   Optional[str] = Query(None),
    feature: Optional[str] = Query(None),
    limit:   int = Query(50, ge=1, le=1000),
    _user:   Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — list FAG proposals (Copilot-facing)."""
    if state and state not in fag_proposals.ALL_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"state must be one of {fag_proposals.ALL_STATES}",
        )
    rows = await fag_proposals.list_proposals(state=state, feature=feature, limit=limit)
    return {
        "enabled": fag_proposals.is_enabled(),
        "count":   len(rows),
        "rows":    rows,
    }


@router.get("/fag/proposals/stats")
async def fag_proposals_stats_endpoint(
    window_sec: int = Query(86400, ge=60, le=86400 * 30),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — per-state / per-feature counts."""
    return await fag_proposals.stats(window_sec=window_sec)


@router.get("/fag/proposals/{proposal_id}")
async def fag_proposal_get_endpoint(
    proposal_id: str,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — one proposal by id."""
    row = await fag_proposals.get_proposal(proposal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    return row


@router.post("/fag/observe")
async def fag_observe_endpoint(
    body: _FagObservePayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Step 1: observe a feature. Creates a `pending`
    proposal if the eligibility verdict is satisfied. Idempotent —
    re-observing reuses any open proposal."""
    if not fag_proposals.is_enabled():
        return {"ok": False, "reason": "engine_off",
                "advisory_note": "FS_ENABLE_FAG_ENGINE is OFF; proposals are not landed."}
    ctx = await copilot_context.build_from_snapshot()
    return await fag_proposals.observe(body.feature_name, ctx, user=user)


@router.post("/fag/recommend")
async def fag_recommend_endpoint(
    body: _FagIdPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Steps 2+3: promote pending→recommended AND notify."""
    _require_admin(user)
    return await fag_proposals.recommend_and_notify(body.proposal_id, user=user)


@router.post("/fag/approve")
async def fag_approve_endpoint(
    body: _FagIdPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Step 4a: approve (still NOT activated)."""
    _require_admin(user)
    return await fag_proposals.approve(body.proposal_id, user=user)


@router.post("/fag/reject")
async def fag_reject_endpoint(
    body: _FagRejectPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Step 4b: reject."""
    _require_admin(user)
    return await fag_proposals.reject(body.proposal_id, user=user, reason=body.reason)


@router.post("/fag/activate")
async def fag_activate_endpoint(
    body: _FagIdPayload,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Step 5: activate. Admin-only. Honours operator
    directive vetoes (e.g. Auto-Learning) regardless of state."""
    _require_admin(user)
    return await fag_proposals.activate(body.proposal_id, user=user)


@router.post("/fag/expire-overdue")
async def fag_expire_endpoint(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — admin: expire stale proposals (default TTL 24 h)."""
    _require_admin(user)
    try:
        from engines.feature_flags import flag as _flag
        ttl = int(_flag("FS_FAG_PROPOSAL_TTL_SEC") or 86400)
    except Exception:                                            # pragma: no cover
        ttl = 86400
    return await fag_proposals.expire_overdue(ttl_sec=ttl)


# ─── FS-P1.4 — Copilot context + Operational Copilot ────────────────


@router.get("/copilot/context")
async def copilot_context_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — frozen CopilotContext built from system_state_view.

    Read-only / safe. Carries `advisory_only=true` when the context's
    consumption gate (`FS_ENABLE_SYSTEM_STATE_VIEW`) is OFF.
    """
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    return ctx.to_dict()


@router.get("/copilot/answers")
async def copilot_answers_endpoint(
    refresh: bool = Query(False),
    window_sec: int = Query(3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — answer every canonical operator question deterministically.

    NEVER calls an LLM. The Advanced layer endpoint
    `/copilot/advanced/invoke` is the LLM-bridge.
    """
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    return copilot_operational.answer_all(ctx)


class _CopilotQuestion(BaseModel):
    question_id: str = Field(..., min_length=1, max_length=64)
    refresh:     bool = Field(default=False)
    window_sec:  int = Field(default=3600, ge=60, le=86400)


@router.post("/copilot/answer")
async def copilot_answer_one_endpoint(
    body: _CopilotQuestion,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — answer a single canonical question."""
    ctx = await copilot_context.build_from_snapshot(
        refresh=body.refresh, window_sec=body.window_sec,
    )
    return copilot_operational.answer(ctx, body.question_id)


# ─── FS-P1.4 — Advanced Intelligence Copilot (provider-agnostic) ────


@router.get("/copilot/advanced/manifest")
async def copilot_advanced_manifest_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Advanced Copilot manifest (active provider, registered
    providers, advisory flag). NEVER calls a provider."""
    return copilot_advanced.provider_manifest()


@router.get("/copilot/advanced/providers")
async def copilot_advanced_providers_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — list registered LLM providers + the active one."""
    name, _adapter = llm_adapter_base.resolve_active_adapter()
    return {
        "enabled":         copilot_advanced.is_enabled(),
        "active_provider": name,
        "registered":      llm_adapter_base.list_providers(),
    }


class _CopilotInvokeBody(BaseModel):
    intent:     str = Field(..., min_length=1, max_length=64)
    user_input: Optional[str] = Field(default=None, max_length=4000)
    refresh:    bool = Field(default=False)
    window_sec: int = Field(default=3600, ge=60, le=86400)


@router.post("/copilot/advanced/invoke")
async def copilot_advanced_invoke_endpoint(
    body: _CopilotInvokeBody,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """FS-P1.4 — Advanced Copilot invocation. Admin-only.

    When `FS_ENABLE_COPILOT_ADVANCED=false` (default) the request is
    short-circuited — no provider is contacted, the response carries
    `advisory_only=true` and `provider='none'`. When enabled, the
    LLMRequest is routed through the registered provider adapter
    (NullLLMAdapter is the safe default).

    No execution authority — the layer is advisory-only by design.
    """
    _require_admin(user)
    ctx = await copilot_context.build_from_snapshot(
        refresh=body.refresh, window_sec=body.window_sec,
    )
    return await copilot_advanced.invoke(
        ctx, intent=body.intent, user_input=body.user_input,
    )


# ─── FS-P1.4 Auto-Learning Infrastructure ──────────────────────────


@router.get("/auto-learning/status")
async def auto_learning_status_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only status of the Auto-Learning Infrastructure aggregator.

    Returns the consumption gate, loop gate, the four connected
    learning components, and the flag manifest. The aggregator is
    advisory-only by design — this endpoint NEVER triggers execution.
    """
    return {
        "service":            "auto_learning",
        "phase":              "FS-P1.4",
        "enabled":            auto_learning.is_enabled(),
        "loop_enabled":       auto_learning.is_loop_enabled(),
        "operator_directive": "off",
        "components": {
            "risk_of_ruin":               True,
            "lifecycle_decay":            True,
            "calibration_framework":      True,
            "execution_realism_defaults": True,
        },
        "integrations": {
            "recommendation_engine":   True,
            "eligibility_signals":     True,
            "notification_center":     "manual_only",
            "architect_dashboard":     True,
            "copilot_context":         True,
        },
        "flags": auto_learning.flag_manifest(),
    }


@router.get("/auto-learning/aggregate")
async def auto_learning_aggregate_endpoint(
    ror_limit: int = Query(default=50, ge=1, le=500),
    realism_limit: int = Query(default=50, ge=1, le=500),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only aggregate snapshot from the four dormant learning
    components plus the derived insight list. NEVER mutates state.
    """
    report = await auto_learning.build_report(
        ror_limit=ror_limit, realism_limit=realism_limit,
    )
    return report.to_dict()


@router.get("/auto-learning/insights")
async def auto_learning_insights_endpoint(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only insight list (no component bulk). Each insight is
    purely advisory; severities are capped at WARN."""
    report = await auto_learning.build_report()
    insights_obj = auto_learning.generate_insights(report)
    return {
        "advisory_only":   not auto_learning.is_enabled(),
        "is_loop_enabled": report.is_loop_enabled,
        "evaluated_at":    report.evaluated_at,
        "insights":        [i.to_dict() for i in insights_obj],
        "recommendations": auto_learning.to_recommendations(insights_obj),
    }


@router.get("/auto-learning/eligibility")
async def auto_learning_eligibility_endpoint(
    refresh: bool = Query(default=False),
    window_sec: int = Query(default=3600, ge=60, le=86400),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Explicit eligibility verdict for the Auto-Learning loop gate.

    The verdict honestly evaluates technical readiness, but
    `evidence.operator_directive='off'` is a HARD veto that FAG must
    refuse to override.
    """
    ctx = await copilot_context.build_from_snapshot(
        refresh=refresh, window_sec=window_sec,
    )
    verdict = eligibility_signals.evaluate("FS_ENABLE_AUTO_LEARNING_LOOP", ctx)
    return {
        "feature":            "FS_ENABLE_AUTO_LEARNING_LOOP",
        "verdict":            verdict.to_dict(),
        "operator_directive": "off",
        "advisory_only":      not auto_learning.is_enabled(),
    }


class _AutoLearningNotifyBody(BaseModel):
    severity_floor: str = Field(default="suggestion")


@router.post("/auto-learning/notify")
async def auto_learning_notify_endpoint(
    body: _AutoLearningNotifyBody,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ADMIN-ONLY MANUAL fan-out of current insights to the
    Notification Center.

    Strictly operator-triggered — there is NO scheduler, NO auto loop,
    NO automatic emission. Even when invoked, the fan-out only emits
    advisory events; nothing in the trading pipeline mutates.
    """
    _require_admin(user)
    report = await auto_learning.build_report()
    insights = auto_learning.generate_insights(report)
    result = await auto_learning.fan_out_to_notifications(
        insights,
        user=user,
        severity_floor=body.severity_floor,
    )
    return {
        "ok":             True,
        "advisory_only":  not auto_learning.is_enabled(),
        "result":         result,
        "insight_count":  len(insights),
        "triggered_by":   (user or {}).get("email") or "operator",
    }

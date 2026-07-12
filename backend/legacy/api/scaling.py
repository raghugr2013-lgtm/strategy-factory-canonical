"""
VPS Scaling P1.A — admin-gated API surface (READ-MOSTLY).

Three endpoints:
  * POST /api/scaling/heartbeat  — node ingest (admin)
  * GET  /api/scaling/nodes      — diagnostic list (admin)
  * GET  /api/scaling/route      — pure-function router preview (admin)

All routes are auth-gated via `get_current_user`. No public exposure.
No control-plane side-effects — this surface only persists observations
and previews the (currently `accept_all`) router verdict.
"""
from __future__ import annotations

import logging
import socket
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_utils import get_current_user
from engines import (
    adaptive_concurrency,
    admission_controller,
    architect_scaling_view,
    compute_probe,
    host_capability,
    queue_pressure,
    scaling_events,
    scaling_registry,
    scaling_router,
)
from engines.workload_classes import WorkloadClass

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scaling", tags=["scaling"])


class HeartbeatPayload(BaseModel):
    host_id:       Optional[str] = Field(default=None, description="Stable host id. Defaults to socket.gethostname().")
    hostname:      Optional[str] = Field(default=None, description="Display name; defaults to host_id.")
    workload_tags: Optional[List[str]] = Field(default=None, description="e.g. ['build_host', 'ctrader_runner']")
    snapshot:      Optional[Dict[str, Any]] = Field(default=None, description="Pre-captured snapshot; if omitted, server reads locally via compute_probe.")


@router.post("/heartbeat")
async def heartbeat(
    payload: HeartbeatPayload,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Receive one host's compute snapshot.

    If `snapshot` is omitted, the server reads its own local snapshot
    via `compute_probe.snapshot()` — useful for a cron on the build
    host to self-report.

    The endpoint is intentionally tolerant: a missing host_id falls
    back to socket.gethostname(), missing snapshot falls back to local
    psutil. Failure modes return structured JSON, never 5xx.
    """
    host_id = (payload.host_id or socket.gethostname() or "unknown").strip()
    if not host_id:
        raise HTTPException(status_code=400, detail="host_id required")

    snap = payload.snapshot or compute_probe.snapshot()
    head = compute_probe.headroom_summary(snap)

    result = await scaling_registry.register_or_heartbeat(
        host_id=host_id,
        hostname=payload.hostname or host_id,
        snapshot=snap,
        headroom=head,
        workload_tags=payload.workload_tags or [],
    )
    return {
        "ok":        bool(result.get("ok")),
        "host_id":   host_id,
        "band":      head.get("band"),
        "snapshot":  snap,
        "headroom":  head,
        "persist":   {k: v for k, v in result.items() if k not in ("row",)},
    }


@router.get("/nodes")
async def nodes(
    limit: int = 100,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only diagnostic table of all registered nodes."""
    rows = await scaling_registry.list_nodes(limit=limit)
    return {
        "count": len(rows),
        "nodes": rows,
    }


@router.get("/route")
async def route_preview(
    class_: Optional[str] = None,
    band:   Optional[str] = None,
    _user:  Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Preview the router verdict for a given (class_, band) tuple.

    When `band` is omitted, the server reads a fresh local
    `compute_probe.headroom_summary()` so the operator can see what
    the router *would* decide given the host's current state.
    """
    if band is None:
        head = compute_probe.headroom_summary()
        verdict = scaling_router.route(class_=class_, headroom=head)
        verdict["headroom"] = head
        return verdict
    return scaling_router.route(class_=class_, band=band)


# ─── VPS Scaling P1.C — adaptive concurrency + admission preview ─────

@router.get("/concurrency")
async def concurrency_preview(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Preview the per-class concurrency targets for THIS host RIGHT NOW.

    Pure, read-only. Combines the persisted HostCapability (P1.B) with
    a fresh compute_probe snapshot and the live queue_pressure snapshot
    to produce a `ConcurrencyTargets` recommendation.

    Returns the targets struct PLUS the inputs that produced it, so the
    operator can audit how a decision was made.
    """
    caps    = host_capability.current()
    probe   = compute_probe.snapshot()
    head    = compute_probe.headroom_summary(probe)
    press   = queue_pressure.snapshot()
    targets = adaptive_concurrency.recommend(caps, probe, press)
    return {
        "host_id":  caps.host_id if caps else None,
        "profile":  caps.profile if caps else None,
        "probe":    probe,
        "headroom": head,
        "pressure": press,
        "targets":  targets.to_dict(),
    }


@router.get("/admission")
async def admission_preview(
    class_: str,
    force:  bool = False,
    _user:  Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Preview the admission verdict for one WorkloadClass.

    Read-only — does NOT write to the admission_journal. Useful for
    operators to see what `gate()` would return without consuming a
    record slot.

    Returns 400 if `class_` is not a known WorkloadClass.
    """
    try:
        wc = WorkloadClass(class_)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"unknown class_={class_!r}; "
                   f"valid: {[c.value for c in WorkloadClass]}",
        )
    verdict = admission_controller.gate(wc, force=force)
    return {
        "enabled":  admission_controller.is_enabled(),
        "verdict":  verdict.to_dict(),
    }


@router.get("/pressure")
async def pressure_preview(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Live queue-pressure snapshot. Read-only; no I/O beyond the local
    counters + cpu_pool worker count.
    """
    return queue_pressure.snapshot()



# ─── VPS Scaling P1.D — events + journal stats + architect view ──────

@router.get("/events")
async def list_scaling_events(
    limit:       int            = 100,
    event_type:  Optional[str]  = None,
    since_epoch: Optional[float] = None,
    _user:       Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read scaling_events. Storage-only — no UI consumes this yet.

    Filter by `event_type` (one of `scaling_events.ALL_EVENT_TYPES`)
    and/or `since_epoch` (UNIX epoch seconds). Default returns last 100.
    """
    if event_type and event_type not in scaling_events.ALL_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unknown event_type={event_type!r}; "
                   f"valid: {list(scaling_events.ALL_EVENT_TYPES)}",
        )
    events = await scaling_events.list_events(
        limit=limit, event_type=event_type, since_epoch=since_epoch,
    )
    return {
        "enabled":     scaling_events.is_enabled(),
        "count":       len(events),
        "events":      events,
    }


@router.get("/events/stats")
async def scaling_events_stats(
    window_sec: int = 3600,
    _user:      Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-type event counters across the last `window_sec` seconds."""
    return await scaling_events.stats(window_sec=window_sec)


@router.get("/admission/journal-stats")
async def admission_journal_stats(
    window_sec: int = 3600,
    _user:      Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-class admit/defer/refuse counters from the admission_journal."""
    return await architect_scaling_view.get_admission_journal_stats(window_sec)


@router.get("/architect/snapshot")
async def architect_snapshot(
    window_sec: int = 3600,
    _user:      Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Single-shot consolidated read for the future Architect.

    Dormant in P1.D — no Architect actually consumes this yet. Wires
    `host_capability` + `queue_pressure` + `adaptive_concurrency` +
    `admission_journal` stats into one structured response.
    """
    return await architect_scaling_view.get_full_architect_snapshot(window_sec)

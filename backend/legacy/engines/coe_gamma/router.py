"""Phase 2 Stage 4 P4B — COE γ router.

Endpoints (each gates on its component flag; HTTP 503 when off):

  GET  /api/coe/dead-letter                   — list rows
  GET  /api/coe/dead-letter/{row_id}          — one row
  POST /api/coe/dead-letter/{row_id}/requeue  — mark requeued
  POST /api/coe/dead-letter/{row_id}/discard  — soft-delete
  GET  /api/coe/dead-letter/depth             — count of open rows

  POST /api/coe/circuit-breaker/{provider}/reset
  POST /api/coe/queue/pause
  POST /api/coe/queue/resume

All are admin-only surfaces (authorisation is applied by the platform
layer; this router only enforces the feature flags).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .dead_letter import (
    DeadLetterRepository,
    get_dead_letter_repository,
    is_dead_letter_enabled,
)
from .operator_controls import (
    OperatorControls,
    get_operator_controls,
    is_operator_controls_enabled,
)

router = APIRouter(prefix="/api/coe", tags=["coe"])


# ── Dead-letter endpoints ────────────────────────────────────────────

@router.get("/dead-letter")
async def get_dead_letter_list(
    class_: Optional[str] = Query(None, alias="class"),
    limit:  int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
) -> Dict[str, Any]:
    if not is_dead_letter_enabled():
        raise HTTPException(status_code=503, detail="COE_DEAD_LETTER_ENABLED is off")
    repo: DeadLetterRepository = get_dead_letter_repository()
    rows = await repo.list_rows(
        workload_class=class_, limit=limit, offset=offset,
        include_discarded=include_discarded,
    )
    return {"count": len(rows), "rows": rows}


@router.get("/dead-letter/depth")
async def get_dead_letter_depth(
    class_: Optional[str] = Query(None, alias="class"),
) -> Dict[str, Any]:
    if not is_dead_letter_enabled():
        raise HTTPException(status_code=503, detail="COE_DEAD_LETTER_ENABLED is off")
    repo: DeadLetterRepository = get_dead_letter_repository()
    n = await repo.depth(workload_class=class_)
    return {"depth": n, "workload_class": class_}


@router.get("/dead-letter/{row_id}")
async def get_dead_letter_row(row_id: str) -> Dict[str, Any]:
    if not is_dead_letter_enabled():
        raise HTTPException(status_code=503, detail="COE_DEAD_LETTER_ENABLED is off")
    repo: DeadLetterRepository = get_dead_letter_repository()
    row = await repo.get(row_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown dead-letter row: {row_id}")
    return row


class RequeueRequest(BaseModel):
    requested_by: str = Field(..., min_length=1, max_length=200)


class DiscardRequest(BaseModel):
    requested_by: str = Field(..., min_length=1, max_length=200)
    reason:       str = Field(..., min_length=1, max_length=500)


@router.post("/dead-letter/{row_id}/requeue")
async def post_dead_letter_requeue(row_id: str, body: RequeueRequest = Body(...)) -> Dict[str, Any]:
    if not is_dead_letter_enabled():
        raise HTTPException(status_code=503, detail="COE_DEAD_LETTER_ENABLED is off")
    repo: DeadLetterRepository = get_dead_letter_repository()
    result = await repo.requeue(row_id, requested_by=body.requested_by)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"unknown dead-letter row: {row_id}")
    return result


@router.post("/dead-letter/{row_id}/discard")
async def post_dead_letter_discard(row_id: str, body: DiscardRequest = Body(...)) -> Dict[str, Any]:
    if not is_dead_letter_enabled():
        raise HTTPException(status_code=503, detail="COE_DEAD_LETTER_ENABLED is off")
    repo: DeadLetterRepository = get_dead_letter_repository()
    result = await repo.discard(row_id, requested_by=body.requested_by, reason=body.reason)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail=f"unknown dead-letter row: {row_id}")
    return result


# ── Operator-control endpoints ───────────────────────────────────────

class OperatorActionRequest(BaseModel):
    requested_by: str = Field(..., min_length=1, max_length=200)
    reason:       str = Field(..., min_length=1, max_length=500)


@router.post("/circuit-breaker/{provider}/reset")
async def post_circuit_reset(provider: str, body: OperatorActionRequest = Body(...)) -> Dict[str, Any]:
    if not is_operator_controls_enabled():
        raise HTTPException(status_code=503, detail="COE_OPERATOR_CONTROLS_ENABLED is off")
    if not (provider or "").strip():
        raise HTTPException(status_code=400, detail="provider must be non-empty")
    ctl: OperatorControls = get_operator_controls()
    return await ctl.circuit_reset(
        provider=provider, requested_by=body.requested_by, reason=body.reason,
    )


class QueueControlRequest(BaseModel):
    workload_class: str = Field(..., min_length=1, max_length=100)
    requested_by:   str = Field(..., min_length=1, max_length=200)
    reason:         str = Field(..., min_length=1, max_length=500)


@router.post("/queue/pause")
async def post_queue_pause(body: QueueControlRequest = Body(...)) -> Dict[str, Any]:
    if not is_operator_controls_enabled():
        raise HTTPException(status_code=503, detail="COE_OPERATOR_CONTROLS_ENABLED is off")
    ctl: OperatorControls = get_operator_controls()
    return await ctl.queue_pause(
        workload_class=body.workload_class,
        requested_by=body.requested_by,
        reason=body.reason,
    )


@router.post("/queue/resume")
async def post_queue_resume(body: QueueControlRequest = Body(...)) -> Dict[str, Any]:
    if not is_operator_controls_enabled():
        raise HTTPException(status_code=503, detail="COE_OPERATOR_CONTROLS_ENABLED is off")
    ctl: OperatorControls = get_operator_controls()
    return await ctl.queue_resume(
        workload_class=body.workload_class,
        requested_by=body.requested_by,
        reason=body.reason,
    )

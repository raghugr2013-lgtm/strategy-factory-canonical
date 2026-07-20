"""Phase 2 Stage 3.γ — Promote Bridge router (P2C.9).

Two admin-gated endpoints, both refuse with HTTP 503 when
`UKIE_PROMOTE_BRIDGE_ENABLED` is off:

  POST /api/knowledge/promote/{item_id}
       Body: { "reason": str, "requested_by": str,
               "override_dedup": bool (optional, default false) }
       Query: ?dry_run=1 (optional; overrides UKIE_PROMOTE_DRY_RUN)

  POST /api/knowledge/promote/{item_id}/rollback
       Body: { "reason": str, "requested_by": str }

Both endpoints are audit-first — every attempt (success OR refusal)
lands in `strategy_knowledge_base.promote_events` regardless of the
HTTP status the caller sees.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .promote import PromoteOptions, is_promote_bridge_enabled
from .promote_bridge import DemoteResult, PromoteResult, get_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Schemas ──────────────────────────────────────────────────────────

class PromoteRequest(BaseModel):
    reason:         str  = Field(..., min_length=1, max_length=1000,
                                 description="Operator-provided free-text.")
    requested_by:   str  = Field(..., min_length=1, max_length=200,
                                 description="Operator identifier.")
    override_dedup: bool = Field(False, description="Physical opt-in to duplicate promote; audited.")


class RollbackRequest(BaseModel):
    reason:       str = Field(..., min_length=1, max_length=1000)
    requested_by: str = Field(..., min_length=1, max_length=200)


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/promote/{item_id}")
async def post_promote(
    item_id: str,
    body: PromoteRequest = Body(...),
    dry_run: Optional[int] = Query(None, description="1 = force dry-run; 0 = force commit."),
) -> Dict[str, Any]:
    """Promote one UKIE-KB strategy item to production `strategies`.

    Flag-gated by `UKIE_PROMOTE_BRIDGE_ENABLED` (default OFF → 503).
    Dry-run default follows `UKIE_PROMOTE_DRY_RUN` (default TRUE) —
    override per-request via `?dry_run=0` (commit) or `?dry_run=1`
    (force dry-run).
    """
    if not is_promote_bridge_enabled():
        raise HTTPException(status_code=503, detail="UKIE_PROMOTE_BRIDGE_ENABLED is off")
    if not (item_id or "").strip():
        raise HTTPException(status_code=400, detail="item_id must be non-empty")

    dry: Optional[bool] = None if dry_run is None else bool(int(dry_run))
    opts = PromoteOptions(
        reason=body.reason,
        requested_by=body.requested_by,
        override_dedup=body.override_dedup,
    )
    result: PromoteResult = await get_bridge().promote_item(item_id, opts, dry_run=dry)
    return result.to_dict()


@router.post("/promote/{item_id}/rollback")
async def post_promote_rollback(
    item_id: str,
    body: RollbackRequest = Body(...),
) -> Dict[str, Any]:
    """Delete every production `strategies` row promoted from `item_id`.

    Idempotent. Never touches the source UKIE-KB row.
    """
    if not is_promote_bridge_enabled():
        raise HTTPException(status_code=503, detail="UKIE_PROMOTE_BRIDGE_ENABLED is off")
    if not (item_id or "").strip():
        raise HTTPException(status_code=400, detail="item_id must be non-empty")
    result: DemoteResult = await get_bridge().demote_item(
        item_id,
        requested_by=body.requested_by,
        reason=body.reason,
    )
    return result.to_dict()

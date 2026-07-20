"""Phase 2 Stage 3.γ — Retro-scoring router (P2C.11).

Two admin-gated endpoints, both refuse with HTTP 503 when
`UKIE_RETRO_SCORE_ENABLED` is off:

  POST /api/knowledge/retro-score
       Body: {
         "dry_run":       true,        # default true
         "batch_size":    100,
         "confirm_write": "yes_write_the_kb",   # required when dry_run=false
         "requested_by":  "operator"
       }

  POST /api/knowledge/retro-score/rollback/{run_id}
       Body: { "reason": str, "requested_by": str }

Live-write path is DOUBLY gated:
  1. `UKIE_RETRO_SCORE_ENABLED=true`  (this router)
  2. `UKIE_GOVERNANCE_CUTOVER=true`   (repository layer)

If (2) is off, a `dry_run=false` request still runs the full pipeline
but the repository returns `status="dormant"` for every row — nothing
lands in Mongo. Rationale: retro-scoring is a special case of the
normal pipeline write; it must not bypass the governance cutover.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from .retro_score import (
    CONFIRM_WRITE_TOKEN,
    RetroScoreSummary,
    get_runner,
    is_retro_score_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Schemas ──────────────────────────────────────────────────────────

class RetroScoreRequest(BaseModel):
    dry_run:       bool           = Field(True, description="Default true — caller must opt in.")
    batch_size:    int            = Field(100, ge=1, le=5000)
    confirm_write: Optional[str]  = Field(None,
                                          description="Physical safety catch — required when dry_run=false.")
    requested_by:  str            = Field("operator", min_length=1, max_length=200)


class RetroScoreRollbackRequest(BaseModel):
    reason:       str = Field(..., min_length=1, max_length=1000)
    requested_by: str = Field(..., min_length=1, max_length=200)


# ── Endpoints ────────────────────────────────────────────────────────

@router.post("/retro-score")
async def post_retro_score(body: RetroScoreRequest = Body(...)) -> Dict[str, Any]:
    """Run one retro-scoring pass over `ingested_strategies` → UKIE-KB.

    Dry-run is the default. A real run requires:
      * `dry_run=false` in the body
      * `confirm_write="yes_write_the_kb"` in the body
      * `UKIE_RETRO_SCORE_ENABLED=true`  (this router)
      * `UKIE_GOVERNANCE_CUTOVER=true`   (repository layer — enforced
        automatically; the caller does NOT need to pass anything for it)
    """
    if not is_retro_score_enabled():
        raise HTTPException(status_code=503, detail="UKIE_RETRO_SCORE_ENABLED is off")

    if not body.dry_run:
        if (body.confirm_write or "").strip() != CONFIRM_WRITE_TOKEN:
            raise HTTPException(
                status_code=400,
                detail=(
                    "confirm_write must equal 'yes_write_the_kb' when dry_run=false"
                ),
            )

    summary: RetroScoreSummary = await get_runner().run(
        dry_run=body.dry_run,
        batch_size=body.batch_size,
        requested_by=body.requested_by,
    )
    return summary.to_dict()


@router.post("/retro-score/rollback/{run_id}")
async def post_retro_score_rollback(
    run_id: str,
    body: RetroScoreRollbackRequest = Body(...),
) -> Dict[str, Any]:
    """Delete every UKIE-KB row carrying the specified `run_id`.

    Idempotent. Stamps a `rollbacks[]` entry on the corresponding
    `retro_score_runs` row for audit.
    """
    if not is_retro_score_enabled():
        raise HTTPException(status_code=503, detail="UKIE_RETRO_SCORE_ENABLED is off")
    if not (run_id or "").strip():
        raise HTTPException(status_code=400, detail="run_id must be non-empty")
    return await get_runner().rollback(
        run_id,
        requested_by=body.requested_by,
        reason=body.reason,
    )

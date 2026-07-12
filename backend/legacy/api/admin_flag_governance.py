"""POST /api/admin/flag — governed flag-flip endpoint (RECORD-OF-INTENT).

Admin-authenticated. Records the operator's flag-flip intent into:
  * `flag_overrides` (current state, idempotent upsert)
  * `flag_override_history` (immutable append)
  * `activation_journal` (with live safe_to_widen snapshot captured at
                          write-time)

Critical: this endpoint does NOT mutate `os.environ` — the engines
continue to read the deployed environment. The override is recorded
for forensic auditability and as a declarative source-of-truth that a
future adoption pass may begin honouring at runtime.

Safety:
  * `safe_to_widen.evaluate()` runs BEFORE the write.
  * When `verdict="BLOCKED"`, the write is refused unless the caller
    explicitly passes `acknowledge_blocks=true`.
  * Every write produces an `activation_journal` row carrying the live
    verdict at write-time, so the forensic trail records "what the
    advisor said the moment before the operator flipped X".

Endpoints
---------
POST   /api/admin/flag                   — set/update an override
DELETE /api/admin/flag/{flag_name}       — remove an override
GET    /api/admin/flag                   — list current overrides
GET    /api/admin/flag/history           — append-only history
GET    /api/admin/widening-proposals     — list proposals
POST   /api/admin/widening-proposals     — submit a proposal
POST   /api/admin/widening-proposals/{id}/approve
POST   /api/admin/widening-proposals/{id}/reject
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines import (
    activation_journal,
    flag_overrides,
    safe_to_widen,
    widening_proposal,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────────

class FlagSetRequest(BaseModel):
    flag_name: str = Field(..., min_length=1, max_length=80)
    value: Any
    rationale: str = Field(default="", max_length=1000)
    acknowledge_blocks: bool = Field(
        default=False,
        description=(
            "Required to be true if safe_to_widen.verdict=='BLOCKED'. "
            "Set deliberately by the operator to override an institutional block."
        ),
    )


class ProposalSubmitRequest(BaseModel):
    proposed_flag: str = Field(..., min_length=1, max_length=80)
    proposed_value: Any
    rationale: str = Field(default="", max_length=2000)
    target_stage: Optional[str] = Field(default=None, max_length=8)
    success_criteria: List[str] = Field(default_factory=list, max_length=20)


class ProposalDecisionRequest(BaseModel):
    rationale: str = Field(default="", max_length=2000)


# ─────────────────────────────────────────────────────────────────────
# Flag-flip endpoints
# ─────────────────────────────────────────────────────────────────────

@router.post("/admin/flag")
async def post_flag(
    body: FlagSetRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Record an operator-declared flag-flip intent."""
    # ── 1. Live safe_to_widen pre-check ──────────────────────────
    sw = await safe_to_widen.evaluate()
    verdict = sw.get("verdict")
    if verdict == "BLOCKED" and not body.acknowledge_blocks:
        raise HTTPException(
            status_code=409,
            detail={
                "reason":  "safe_to_widen_blocked",
                "verdict": verdict,
                "blocking_reasons": sw.get("blocking_reasons"),
                "hint": (
                    "Resolve the blocking reasons above, or re-submit "
                    "with `acknowledge_blocks=true` to deliberately "
                    "override the institutional block."
                ),
            },
        )

    actor = str(user.get("email") or user.get("sub") or "admin")

    # ── 2. Persist to flag_overrides ─────────────────────────────
    res = await flag_overrides.set_override(
        body.flag_name,
        body.value,
        set_by=actor,
        rationale=body.rationale,
        safe_to_widen_snapshot=sw,
    )

    # ── 3. Journal the event ─────────────────────────────────────
    try:
        await activation_journal.journal_event(
            "flag_override",
            actor=actor,
            summary=(
                f"Set {body.flag_name} = {body.value!r} "
                f"(verdict_at_set={verdict}; "
                f"acknowledge_blocks={body.acknowledge_blocks})"
            ),
            payload={
                "flag_name":         body.flag_name,
                "value":             body.value,
                "rationale":         body.rationale,
                "acknowledge_blocks": body.acknowledge_blocks,
                "override_result":   res,
            },
            include_safe_to_widen=False,   # already embedded via flag_overrides
            include_governance=False,
        )
    except Exception:                                       # pragma: no cover
        logger.debug("[admin/flag] journal write failed", exc_info=True)

    return {
        "ok":              True,
        "override":        res,
        "verdict_at_set":  verdict,
        "acknowledge_blocks_used": body.acknowledge_blocks,
        "note": (
            "This endpoint records the operator's flag-flip INTENT. "
            "It does NOT mutate os.environ — engines still read the "
            "deployed environment. To make the change runtime-effective "
            "across reboots, also update backend/.env and restart."
        ),
    }


@router.delete("/admin/flag/{flag_name}")
async def delete_flag(
    flag_name: str,
    rationale: str = Query(default="", max_length=1000),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    actor = str(user.get("email") or user.get("sub") or "admin")
    res = await flag_overrides.remove_override(
        flag_name, removed_by=actor, rationale=rationale,
    )
    try:
        await activation_journal.journal_event(
            "flag_override_remove",
            actor=actor,
            summary=f"Removed override for {flag_name}",
            payload={"flag_name": flag_name, "rationale": rationale,
                     "remove_result": res},
            include_safe_to_widen=False,
            include_governance=False,
        )
    except Exception:                                       # pragma: no cover
        pass
    return {"ok": res.get("ok", False), "result": res}


@router.get("/admin/flag")
async def list_flags(
    _user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    rows = await flag_overrides.list_overrides()
    return {
        "ok":     True,
        "count":  len(rows),
        "overrides": rows,
        "note": (
            "This is the operator-declared override map. Engines do "
            "NOT consult it yet — runtime behaviour still reads os.environ."
        ),
    }


@router.get("/admin/flag/history")
async def flag_history(
    _user: Dict[str, Any] = Depends(require_admin),
    flag_name: Optional[str] = Query(default=None, max_length=80),
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    rows = await flag_overrides.history(flag_name=flag_name, limit=limit)
    return {"ok": True, "count": len(rows), "history": rows}


# ─────────────────────────────────────────────────────────────────────
# Widening-proposal endpoints
# ─────────────────────────────────────────────────────────────────────

@router.post("/admin/widening-proposals")
async def submit_widening_proposal(
    body: ProposalSubmitRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    actor = str(user.get("email") or user.get("sub") or "admin")
    return await widening_proposal.submit_proposal(
        proposed_flag=body.proposed_flag,
        proposed_value=body.proposed_value,
        submitted_by=actor,
        rationale=body.rationale,
        target_stage=body.target_stage,
        success_criteria=body.success_criteria,
    )


@router.post("/admin/widening-proposals/{proposal_id}/approve")
async def approve_widening_proposal(
    proposal_id: str,
    body: ProposalDecisionRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    actor = str(user.get("email") or user.get("sub") or "admin")
    return await widening_proposal.approve_proposal(
        proposal_id, decided_by=actor, rationale=body.rationale,
    )


@router.post("/admin/widening-proposals/{proposal_id}/reject")
async def reject_widening_proposal(
    proposal_id: str,
    body: ProposalDecisionRequest,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    actor = str(user.get("email") or user.get("sub") or "admin")
    return await widening_proposal.reject_proposal(
        proposal_id, decided_by=actor, rationale=body.rationale,
    )


@router.get("/admin/widening-proposals")
async def list_widening_proposals(
    _user: Dict[str, Any] = Depends(require_admin),
    status: Optional[str] = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=500),
) -> Dict[str, Any]:
    return await widening_proposal.list_proposals(status=status, limit=limit)

"""API layer for Phase 2 — Challenge Type Matching Engine.

All additive. Reuses prop_firm_rule_engine and challenge_matching_engine
only — does not touch mutation / scoring / ingestion.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import challenge_matching_engine as cm

logger = logging.getLogger(__name__)

strategies_scope_router = APIRouter(prefix="/strategies", tags=["challenge-matching"])
matching_router = APIRouter(prefix="/challenge-matching", tags=["challenge-matching"])


class MatchRequest(BaseModel):
    force: bool = False


class BatchRequest(BaseModel):
    limit: int = Field(cm.MAX_PER_CYCLE, ge=1, le=20)
    force: bool = False


# ── Challenge-type catalog ───────────────────────────────────────────

@matching_router.get("/challenge-types")
async def challenge_types_flat():
    rows = await cm.list_challenge_types()
    return {"count": len(rows), "challenge_types": rows}


@matching_router.get("/challenge-types/by-firm")
async def challenge_types_by_firm():
    return await cm.list_by_firm()


# ── Per-strategy matching ────────────────────────────────────────────

@strategies_scope_router.post("/{strategy_hash}/match-challenges")
async def match_challenges(strategy_hash: str, req: MatchRequest):
    try:
        return await cm.match_strategy_to_challenges(strategy_hash, force=req.force)
    except PermissionError:
        raise HTTPException(status_code=409, detail="rules_not_verified")
    except ValueError as e:
        msg = str(e)
        # eligibility failure → 422 (unprocessable), missing history → 404
        if "not eligible" in msg:
            raise HTTPException(status_code=422, detail=msg)
        raise HTTPException(status_code=404, detail=msg)


@strategies_scope_router.get("/{strategy_hash}/challenge-match")
async def get_challenge_match(strategy_hash: str):
    doc = await cm.get_match(strategy_hash)
    if not doc:
        raise HTTPException(status_code=404, detail="no match for this strategy_hash")
    return doc


# ── Batch eligible ──────────────────────────────────────────────────

@matching_router.post("/run-eligible")
async def run_eligible(req: BatchRequest):
    return await cm.match_eligible(limit=req.limit, force=req.force)

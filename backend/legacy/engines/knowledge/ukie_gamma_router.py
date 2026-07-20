"""Phase 2 Stage 4 P4C — UKIE γ router.

Endpoints (each gates on its component flag; HTTP 503 when off):

  POST /api/knowledge/query
       — retrieval

  POST /api/knowledge/lifecycle-sweep
       — retention + decay sweep (dry-run default)

  POST /api/knowledge/endorsement
       — record a manual endorsement (operator)

  POST /api/knowledge/contradiction
       — record a contradiction pair; both items get contested=true

  POST /api/knowledge/governance/evaluate/{kb_id}
       — dry-run policy evaluation over one KB row (no write)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from .confidence import (
    get_confidence_store,
    is_confidence_evolution_enabled,
)
from .governance_policy import (
    get_governance_policy_engine,
    is_governance_policy_enabled,
)
from .lifecycle import (
    get_lifecycle_sweeper,
    is_lifecycle_sweep_enabled,
)
from .retrieval import (
    QueryRequest,
    get_retrieval_engine,
    is_query_api_enabled,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Retrieval ────────────────────────────────────────────────────────

class QueryBody(BaseModel):
    domain:            Optional[str]       = None
    query:             str                 = Field("", min_length=0, max_length=8000)
    top_k:             int                 = Field(10, ge=1, le=200)
    pair:              Optional[str]       = None
    timeframe:         Optional[str]       = None
    min_trust_tier:    Optional[int]       = Field(None, ge=1, le=5)
    license_outcomes:  Optional[List[str]] = None


@router.post("/query")
async def post_query(body: QueryBody = Body(...)) -> Dict[str, Any]:
    if not is_query_api_enabled():
        raise HTTPException(status_code=503, detail="UKIE_QUERY_API_ENABLED is off")
    return await get_retrieval_engine().query(QueryRequest(
        domain=body.domain, query=body.query, top_k=body.top_k,
        pair=body.pair, timeframe=body.timeframe,
        min_trust_tier=body.min_trust_tier,
        license_outcomes=body.license_outcomes,
    ))


# ── Lifecycle ────────────────────────────────────────────────────────

class LifecycleSweepBody(BaseModel):
    dry_run:              bool = True
    annotate_decay_only:  bool = False


@router.post("/lifecycle-sweep")
async def post_lifecycle_sweep(body: LifecycleSweepBody = Body(...)) -> Dict[str, Any]:
    if not is_lifecycle_sweep_enabled():
        raise HTTPException(status_code=503, detail="UKIE_LIFECYCLE_SWEEP_ENABLED is off")
    summary = await get_lifecycle_sweeper().sweep(
        dry_run=body.dry_run,
        annotate_decay_only=body.annotate_decay_only,
    )
    return summary.to_dict()


# ── Confidence evolution ────────────────────────────────────────────

class EndorsementBody(BaseModel):
    kb_id:   str            = Field(..., min_length=1, max_length=200)
    domain:  str            = Field(..., min_length=1, max_length=100)
    source:  str            = Field("operator", max_length=100)
    context: Optional[Dict[str, Any]] = None


@router.post("/endorsement")
async def post_endorsement(body: EndorsementBody = Body(...)) -> Dict[str, Any]:
    if not is_confidence_evolution_enabled():
        raise HTTPException(status_code=503, detail="UKIE_CONFIDENCE_EVOLUTION_ENABLED is off")
    return await get_confidence_store().record_endorsement(
        kb_id=body.kb_id, domain=body.domain,
        source=body.source, context=body.context,
    )


class ContradictionBody(BaseModel):
    domain:      str = Field(..., min_length=1, max_length=100)
    kb_id_a:     str = Field(..., min_length=1, max_length=200)
    kb_id_b:     str = Field(..., min_length=1, max_length=200)
    reason:      str = Field(..., min_length=1, max_length=500)
    reported_by: str = Field("operator", max_length=100)


@router.post("/contradiction")
async def post_contradiction(body: ContradictionBody = Body(...)) -> Dict[str, Any]:
    if not is_confidence_evolution_enabled():
        raise HTTPException(status_code=503, detail="UKIE_CONFIDENCE_EVOLUTION_ENABLED is off")
    return await get_confidence_store().record_contradiction(
        domain=body.domain,
        kb_id_a=body.kb_id_a, kb_id_b=body.kb_id_b,
        reason=body.reason, reported_by=body.reported_by,
    )


# ── Governance policy (advisory) ─────────────────────────────────────

class GovernanceEvaluateBody(BaseModel):
    domain: str = Field(..., min_length=1, max_length=100)
    write:  bool = False   # when true, stamp advisory tags on the KB row


@router.post("/governance/evaluate/{kb_id}")
async def post_governance_evaluate(
    kb_id: str,
    body: GovernanceEvaluateBody = Body(...),
) -> Dict[str, Any]:
    if not is_governance_policy_enabled():
        raise HTTPException(status_code=503, detail="UKIE_GOVERNANCE_POLICY_ENABLED is off")
    engine = get_governance_policy_engine()
    # Load the row via the injected DB — we ask the engine for the KB
    # DB handle so tests can inject a fake.
    db = engine._kb_db()  # pragma: no cover — protected accessor is intentional
    if db is None:
        raise HTTPException(status_code=503, detail="kb_db_unavailable")
    try:
        from .domains import KnowledgeDomain, storage_collection_for
        coll = storage_collection_for(KnowledgeDomain(body.domain.strip().lower()))
    except Exception:
        raise HTTPException(status_code=400, detail="unknown_domain")
    try:
        row = await db[coll].find_one({"_id": kb_id})
    except Exception as e:                                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)[:120])
    if row is None:
        raise HTTPException(status_code=404, detail=f"kb row not found: {kb_id}")
    verdict = await engine.evaluate(row)
    result = verdict.to_dict()
    if body.write:
        wr = await engine.write_verdict(verdict, domain=body.domain)
        result["write"] = wr
    return result

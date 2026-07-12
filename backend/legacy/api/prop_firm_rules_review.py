"""Prop Firm Rules — human-in-the-loop Review & Approval layer.

Endpoints (all additive, mounted at /api/prop-firm-rules):
    GET  /                        list every firm with parse/approval state
    GET  /{firm_slug}             single firm detail
    POST /ingest-parsed           persist a parser output as status='parsed'
    POST /{firm_slug}/approve     persist user-edited approved_rules
    POST /{firm_slug}/reject      mark rejected
    POST /{firm_slug}/reset       back to status='parsed'
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import prop_firm_rule_engine as pe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prop-firm-rules", tags=["prop-firm-rules-review"])


# ── Schemas ──────────────────────────────────────────────────────────

class IngestParsedRequest(BaseModel):
    firm_slug: str = Field(..., min_length=1)
    firm_name: Optional[str] = None
    parsed_rules: Dict[str, Any]
    parser_confidence: Optional[float] = None
    source_type: Optional[str] = None   # "url" | "pdf"
    source_url: Optional[str] = None


class ApproveRequest(BaseModel):
    approved_rules: Dict[str, Any]


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def list_all() -> Dict[str, Any]:
    rows = await pe.list_normalized_rules()
    return {"count": len(rows), "rules": rows}


@router.get("/{firm_slug}")
async def get_one(firm_slug: str) -> Dict[str, Any]:
    doc = await pe.get_normalized_rules(firm_slug, require_approved=False)
    if not doc:
        raise HTTPException(status_code=404, detail=f"no rules for firm_slug: {firm_slug}")
    return doc


@router.post("/ingest-parsed")
async def ingest_parsed(req: IngestParsedRequest) -> Dict[str, Any]:
    return await pe.ingest_parsed_rules(
        firm_slug=req.firm_slug.lower(),
        firm_name=req.firm_name,
        parsed_rules=req.parsed_rules,
        parser_confidence=req.parser_confidence,
        source_type=req.source_type,
        source_url=req.source_url,
    )


@router.post("/{firm_slug}/approve")
async def approve(firm_slug: str, req: ApproveRequest) -> Dict[str, Any]:
    try:
        return await pe.approve_rules(firm_slug, req.approved_rules)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{firm_slug}/reject")
async def reject(firm_slug: str) -> Dict[str, Any]:
    try:
        return await pe.reject_rules(firm_slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{firm_slug}/reset")
async def reset(firm_slug: str) -> Dict[str, Any]:
    try:
        return await pe.reset_rules(firm_slug)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

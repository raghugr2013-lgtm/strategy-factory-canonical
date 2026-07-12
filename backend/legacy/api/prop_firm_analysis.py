"""API layer for Prop Firm Rule Engine + Challenge Simulator (Phase 1).

All endpoints additive. They do NOT duplicate or replace the existing
`prop_firms` / `challenge` routes — they sit on top of the normalised
snapshot collection and expose strategy-level analysis.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import prop_firm_rule_engine as pe

logger = logging.getLogger(__name__)

strategies_scope_router = APIRouter(prefix="/strategies", tags=["prop-firm-analysis"])
firms_router = APIRouter(prefix="/prop-firm-analysis", tags=["prop-firm-analysis"])


class AnalyzeRequest(BaseModel):
    firm_slug: str = Field(pe.DEFAULT_FIRM, min_length=2, max_length=60)


class BatchAnalyzeRequest(BaseModel):
    firm_slug: str = Field(pe.DEFAULT_FIRM, min_length=2, max_length=60)
    limit: int = Field(50, ge=1, le=500)
    min_runs: int = Field(1, ge=0, le=100)
    force: bool = False


# ── Rule snapshot endpoints ──────────────────────────────────────────

@firms_router.get("/rules")
async def list_rules():
    rows = await pe.list_normalized_rules()
    return {"count": len(rows), "rules": rows}


@firms_router.get("/rules/{firm_slug}")
async def get_rule(firm_slug: str):
    doc = await pe.get_normalized_rules(firm_slug)
    if not doc:
        raise HTTPException(status_code=404, detail=f"unknown firm_slug: {firm_slug}")
    return doc


# ── Per-strategy analysis ────────────────────────────────────────────

@strategies_scope_router.post("/{strategy_hash}/prop-analysis")
async def analyze(strategy_hash: str, req: AnalyzeRequest):
    try:
        return await pe.analyze_strategy(strategy_hash, firm_slug=req.firm_slug)
    except PermissionError:
        raise HTTPException(status_code=409, detail="rules_not_verified")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@strategies_scope_router.get("/{strategy_hash}/prop-analysis")
async def get_analysis(
    strategy_hash: str,
    firm_slug: str = Query(pe.DEFAULT_FIRM),
    include_rules: bool = Query(True),
):
    saved = await pe.get_saved_analysis(strategy_hash, firm_slug=firm_slug)
    if not saved or not saved.get("analysis"):
        raise HTTPException(status_code=404, detail="no analysis for this strategy_hash + firm")
    out = {"analysis": saved["analysis"], "risk_profile": saved.get("risk_profile")}
    if include_rules:
        out["rules"] = await pe.get_normalized_rules(firm_slug)
    return out


# ── Batch analysis ───────────────────────────────────────────────────

@firms_router.post("/batch-analyze")
async def batch_analyze(req: BatchAnalyzeRequest):
    return await pe.batch_analyze(
        firm_slug=req.firm_slug,
        limit=req.limit,
        min_runs=req.min_runs,
        force=req.force,
    )

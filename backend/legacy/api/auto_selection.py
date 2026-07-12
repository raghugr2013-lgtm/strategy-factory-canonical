"""Phase 3 — Auto Selection Engine API.

Endpoints mounted at /api/auto-select:
  POST /run      run the selector with optional filters
  GET  /recent   list recent run snapshots
  GET  /config   return default thresholds
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from engines import auto_selection_engine as ase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auto-select", tags=["auto-selection"])


class RunRequest(BaseModel):
    top_n: int = Field(10, ge=1, le=50)
    min_pf: float = ase.DEFAULT_MIN_PF
    min_runs: int = Field(ase.DEFAULT_MIN_RUNS, ge=1, le=100)
    min_stability: float = ase.DEFAULT_MIN_STABILITY
    min_pass_probability: float = ase.DEFAULT_MIN_PASS_PROB
    min_match_score: float = ase.DEFAULT_MIN_MATCH_SCORE
    min_env_confidence: float = ase.DEFAULT_MIN_ENV_CONFIDENCE
    firm_slug: Optional[str] = None
    pass_only: bool = False
    run_missing_matches: bool = True
    persist: bool = True


@router.post("/run")
async def run_selection(req: RunRequest):
    return await ase.run_auto_selection(
        top_n=req.top_n,
        min_pf=req.min_pf,
        min_runs=req.min_runs,
        min_stability=req.min_stability,
        min_pass_probability=req.min_pass_probability,
        min_match_score=req.min_match_score,
        min_env_confidence=req.min_env_confidence,
        firm_slug=req.firm_slug,
        pass_only=req.pass_only,
        run_missing_matches=req.run_missing_matches,
        persist=req.persist,
    )


@router.get("/recent")
async def recent_runs(limit: int = Query(10, ge=1, le=50)):
    rows = await ase.get_recent_runs(limit=limit)
    return {"count": len(rows), "runs": rows}


@router.get("/config")
async def config():
    return {
        "min_pf": ase.DEFAULT_MIN_PF,
        "min_runs": ase.DEFAULT_MIN_RUNS,
        "min_stability": ase.DEFAULT_MIN_STABILITY,
        "min_pass_probability": ase.DEFAULT_MIN_PASS_PROB,
        "min_match_score": ase.DEFAULT_MIN_MATCH_SCORE,
        "min_env_confidence": ase.DEFAULT_MIN_ENV_CONFIDENCE,
    }

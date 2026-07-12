"""
Phase 7 — Portfolio Intelligence API.

Thin FastAPI surface over `engines.portfolio_intelligence_engine`.

Endpoints (mounted at `/api/portfolio-intelligence`):
    POST /build     — optimise a portfolio from the requested source
                      (auto_factory | explorer).
    GET  /current   — latest built portfolio snapshot.
    GET  /history   — last N builds (lightweight; correlation matrix stripped).

NOTE: The task spec calls for `/api/portfolio/build|current|history`, but
`/api/portfolio/build` is already owned by the existing Phase-7
library-sourced builder (`api/portfolio.py`). Per the safety rule ("do
not override existing Portfolio Builder"), this upgrade layer is
namespaced under `/api/portfolio-intelligence` and coexists additively.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import portfolio_intelligence_engine as pie

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio-intelligence", tags=["portfolio-intelligence"])


class BuildRequest(BaseModel):
    source: str = Field("auto_factory", description="auto_factory | explorer")
    pool_size: int = Field(pie.DEFAULT_CONFIG["pool_size"], ge=2, le=200)
    target_min: int = Field(pie.DEFAULT_CONFIG["target_min"], ge=2, le=10)
    target_max: int = Field(pie.DEFAULT_CONFIG["target_max"], ge=2, le=10)
    min_weight: float = Field(pie.DEFAULT_CONFIG["min_weight"], ge=0.0, le=0.5)
    max_weight: float = Field(pie.DEFAULT_CONFIG["max_weight"], ge=0.1, le=1.0)
    max_portfolio_dd: float = Field(pie.DEFAULT_CONFIG["max_portfolio_dd"], ge=1.0, le=50.0)
    min_pf: float = Field(pie.DEFAULT_CONFIG["min_pf"], ge=0.0, le=10.0)
    min_pass_probability: float = Field(
        pie.DEFAULT_CONFIG["min_pass_probability"], ge=0.0, le=100.0,
    )
    min_env_confidence: float = Field(
        pie.DEFAULT_CONFIG["min_env_confidence"], ge=0.0, le=1.0,
    )
    high_corr_threshold: float = Field(
        pie.DEFAULT_CONFIG["high_corr_threshold"], ge=0.5, le=1.0,
    )
    strategies: Optional[list] = Field(
        None,
        description=(
            "Optional explicit strategies list. When provided, overrides `source`. "
            "Each item is normalised internally (accepts auto-factory / library shape)."
        ),
    )


@router.post("/build")
async def build(req: BuildRequest) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "source": req.source,
        "pool_size": req.pool_size,
        "target_min": min(req.target_min, req.target_max),
        "target_max": req.target_max,
        "min_weight": req.min_weight,
        "max_weight": req.max_weight,
        "max_portfolio_dd": req.max_portfolio_dd,
        "min_pf": req.min_pf,
        "min_pass_probability": req.min_pass_probability,
        "min_env_confidence": req.min_env_confidence,
        "high_corr_threshold": req.high_corr_threshold,
    }

    try:
        if req.strategies is not None:
            # Explicit list — run the core builder directly and persist.
            result = pie.build_optimized_portfolio(req.strategies, cfg)
            result["source"] = "explicit"
            result["pool_raw_count"] = len(req.strategies)
            await pie._persist(result)
        else:
            result = await pie.run_build_from_source(cfg)
    except Exception as e:
        logger.exception("portfolio-intelligence: build failed")
        raise HTTPException(status_code=500, detail=str(e))
    return result


@router.get("/current")
async def current() -> Dict[str, Any]:
    doc = await pie.get_current()
    if not doc:
        return {"status": "empty", "portfolio": None}
    return {"status": "ok", "portfolio": doc}


@router.get("/history")
async def history(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    rows = await pie.get_history(limit=limit)
    return {"count": len(rows), "history": rows}


@router.get("/config")
async def get_defaults() -> Dict[str, Any]:
    return {"defaults": pie.DEFAULT_CONFIG}

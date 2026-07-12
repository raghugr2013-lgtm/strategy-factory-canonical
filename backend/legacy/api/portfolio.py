"""
Phase 7 — Portfolio API (library-sourced).

Thin FastAPI surface over `engines.portfolio_engine.build_portfolio_from_library`.
Stateless at the HTTP layer; built portfolios are persisted to the
`portfolios` Mongo collection so `/status` can return the most recent
one + a short history.

Endpoints:
  POST /api/portfolio/build    — build a diversified multi-strategy portfolio
  GET  /api/portfolio/status   — most recent + history (default: 10)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines.db import get_db
from engines.portfolio_engine import build_portfolio_from_library

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

COLLECTION = "portfolios"


class PortfolioBuildRequest(BaseModel):
    top_n_pool: int = Field(25, ge=2, le=200)
    target_size: int = Field(4, ge=2, le=7)
    max_pair_corr: float = Field(0.6, ge=0.0, le=1.0)
    max_same_pair: int = Field(2, ge=1, le=7)
    max_same_style: int = Field(2, ge=1, le=7)
    min_score: float = Field(0.0, ge=0.0, le=100.0)
    source_filter: Optional[str] = None   # e.g. "auto_factory"


@router.post("/build")
async def portfolio_build(req: PortfolioBuildRequest):
    """Build a diversified portfolio from the top strategies in
    `strategy_library`. Honors correlation + per-bucket (pair/style) caps."""
    try:
        result = await build_portfolio_from_library(
            top_n_pool=req.top_n_pool,
            target_size=req.target_size,
            max_pair_corr=req.max_pair_corr,
            max_same_pair=req.max_same_pair,
            max_same_style=req.max_same_style,
            min_score=req.min_score,
            source_filter=req.source_filter,
        )
    except Exception as e:
        logger.exception("Portfolio build failed")
        raise HTTPException(status_code=500, detail=str(e))

    if not result.get("success"):
        # 400 for user-visible errors (not enough strategies, bad caps, ...)
        raise HTTPException(status_code=400, detail=result)
    return result


@router.get("/status")
async def portfolio_status(limit: int = 10):
    """Most recent portfolio + last `limit` history entries (summarized)."""
    db = get_db()
    limit = max(1, min(limit, 50))
    cursor = db[COLLECTION].find(
        {},
        # Drop heavy fields from the list response; keep only summary.
        {"_id": 0, "correlation_matrix": 0, "selection_log": 0},
    ).sort("created_at", -1).limit(limit)

    history: List[Dict[str, Any]] = []
    async for doc in cursor:
        history.append(doc)

    latest = history[0] if history else None
    # Trim history entries down to a lightweight shape.
    light_history = [
        {
            "run_id": h.get("run_id"),
            "created_at": h.get("created_at"),
            "portfolio_score": h.get("portfolio_score"),
            "diversification_grade": h.get("diversification_grade"),
            "num_strategies": len(h.get("strategies") or []),
            "combined_metrics": h.get("combined_metrics"),
            "config": h.get("config"),
        }
        for h in history
    ]
    return {
        "total_portfolios": await db[COLLECTION].count_documents({}),
        "latest": latest,
        "history": light_history,
    }

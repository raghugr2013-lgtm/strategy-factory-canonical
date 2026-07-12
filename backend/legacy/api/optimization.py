"""
Phase 8 — Optimization API.

Thin FastAPI surface over `engines.strategy_refinement_engine`.

Endpoints (mounted at `/api/optimization`):
    POST /run      — optimise strategies sourced from auto_factory or
                     the latest Portfolio Intelligence snapshot; or a
                     single strategy passed explicitly in the body.
    GET  /history  — recent optimisation run summaries.
    GET  /best     — top optimised strategies by fitness (OPTIMIZED only).
    GET  /config   — default thresholds / knobs.

Additive only. Does not collide with the legacy grid-search endpoints
`/api/optimize-strategy` and `/api/optimize-random`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import strategy_refinement_engine as sre
from engines import optimization_portfolio_bridge as bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/optimization", tags=["optimization"])


class OptimizeRequest(BaseModel):
    source: str = Field("auto_factory", description="auto_factory | portfolio")
    pool_size: int = Field(10, ge=1, le=100)
    runs: int = Field(sre.DEFAULT_CONFIG["runs"], ge=1, le=50)
    perturbation_pct: float = Field(
        sre.DEFAULT_CONFIG["perturbation_pct"], ge=0.05, le=0.25,
    )
    min_pf: float = Field(sre.DEFAULT_CONFIG["min_pf"], ge=0.0, le=10.0)
    max_dd_pct: float = Field(sre.DEFAULT_CONFIG["max_dd_pct"], ge=0.5, le=100.0)
    min_stability: float = Field(
        sre.DEFAULT_CONFIG["min_stability"], ge=0.0, le=1.0,
    )
    preserve_original: bool = sre.DEFAULT_CONFIG["preserve_original"]
    strategy: Optional[Dict[str, Any]] = Field(
        None, description="Optional single strategy — when set, source is ignored."
    )
    auto_rebuild_portfolio: bool = Field(
        True,
        description=(
            "When true (default), after a successful batch the optimization→portfolio "
            "bridge evaluates safety gates and may auto-trigger a Portfolio Intelligence "
            "rebuild. Set false to skip the bridge entirely."
        ),
    )


@router.post("/run")
async def run(req: OptimizeRequest) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "source": req.source,
        "pool_size": req.pool_size,
        "runs": req.runs,
        "perturbation_pct": req.perturbation_pct,
        "min_pf": req.min_pf,
        "max_dd_pct": req.max_dd_pct,
        "min_stability": req.min_stability,
        "preserve_original": req.preserve_original,
    }
    try:
        if req.strategy is not None:
            res = sre.optimize_strategy(req.strategy, cfg)
            res["source"] = "explicit"
            await sre._persist_single(res)
            batch_result = {
                "source": "explicit",
                "candidates": 1,
                "accepted": 1 if res["verdict"] == "OPTIMIZED" else 0,
                "rejected": 0 if res["verdict"] == "OPTIMIZED" else 1,
                "results": [res],
                "built_at": res["built_at"],
                "config": cfg,
            }
        else:
            batch_result = await sre.run_optimization_batch(cfg)
    except Exception as e:
        logger.exception("optimization: run failed")
        raise HTTPException(status_code=500, detail=str(e))

    # Optional post-hook: safe Auto-Approve → Portfolio Rebuild bridge.
    if req.auto_rebuild_portfolio:
        try:
            action = await bridge.handle_post_optimization(batch_result)
        except Exception:
            # Bridge must never break the primary optimisation response.
            logger.exception("optimization: bridge hook raised unexpectedly")
            action = {"triggered": False, "reason": "bridge_error"}
        batch_result["portfolio_action"] = action
    return batch_result


@router.get("/history")
async def history(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    rows = await sre.get_history(limit=limit)
    return {"count": len(rows), "history": rows}


@router.get("/best")
async def best(limit: int = Query(10, ge=1, le=50)) -> Dict[str, Any]:
    rows = await sre.get_best(limit=limit)
    return {"count": len(rows), "strategies": rows}


@router.get("/strategy/{strategy_id}")
async def one(strategy_id: str) -> Dict[str, Any]:
    doc = await sre.get_one(strategy_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"No optimisation record for {strategy_id}")
    return doc


@router.get("/config")
async def defaults() -> Dict[str, Any]:
    return {"defaults": sre.DEFAULT_CONFIG}


@router.get("/portfolio-actions")
async def portfolio_actions(limit: int = Query(20, ge=1, le=100)) -> Dict[str, Any]:
    """Recent Auto-Approve bridge decisions (approved / skipped / cooldown)."""
    rows = await bridge.get_recent_actions(limit=limit)
    return {"count": len(rows), "actions": rows, "bridge_defaults": bridge.DEFAULT_CONFIG}

"""
Phase 11 — Gem Factory API.

Thin surface over `engines.gem_factory_engine`.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import gem_factory_engine as gf

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gem-factory", tags=["gem-factory"])


class GemFactoryRunRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    styles: Optional[List[str]] = None
    per_combo: int = Field(30, ge=20, le=50)
    m1_mode: str = Field("off", pattern="^(off|strict)$")
    auto_replace_retired: bool = True


@router.post("/run")
async def gem_factory_run(req: GemFactoryRunRequest):
    """Run one Gem Factory cycle.
    Returns per-slot counts (candidates / strict-kept / library-eligible /
    winners / saved), the degradation sweep, and any replacement slots
    queued. Use /status afterwards for cumulative library state."""
    try:
        return await gf.run_gem_factory(
            pairs=req.pairs, timeframes=req.timeframes, styles=req.styles,
            per_combo=req.per_combo, m1_mode=req.m1_mode,
            auto_replace_retired=req.auto_replace_retired,
            triggered_by="api",
        )
    except RuntimeError as e:
        if str(e) == "already_running":
            raise HTTPException(status_code=409, detail="gem factory already running")
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("gem_factory run failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def gem_factory_status(limit: int = 10):
    """Library lifecycle counts + recent runs + configured rules."""
    try:
        return await gf.get_status(limit=limit)
    except Exception as e:
        logger.exception("gem_factory status failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sweep-degradation")
async def gem_factory_sweep():
    """Trigger just the degradation sweep (no generation)."""
    try:
        return {"success": True, **await gf.sweep_degradation()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

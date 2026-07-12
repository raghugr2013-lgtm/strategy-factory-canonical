"""
Phase 10 — Challenge Management API.

Thin FastAPI surface over `engines.challenge_manager`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import challenge_manager as cm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/challenge", tags=["challenge"])


class DecisionRequest(BaseModel):
    dry_run: bool = True
    safety_rules: Optional[Dict[str, Any]] = None
    auto_rebuild: bool = False


class ControlRequest(BaseModel):
    enabled: bool
    interval_minutes: float = Field(10.0, gt=0, le=60)


@router.get("/status")
async def challenge_status(history_limit: int = 20):
    """Current classification + scheduler state + recent decision history."""
    try:
        return await cm.get_status(history_limit=history_limit)
    except Exception as e:
        logger.exception("challenge status failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decision")
async def challenge_decision(req: DecisionRequest):
    """Run one adaptive-loop tick. `dry_run=True` classifies + decides
    but does NOT apply the action. Default True to prevent accidental halts."""
    try:
        return await cm.tick_and_act(
            dry_run=req.dry_run, safety_rules=req.safety_rules,
            auto_rebuild=req.auto_rebuild,
        )
    except Exception as e:
        logger.exception("challenge decision failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-cooldown")
async def challenge_clear_cooldown():
    """Clear the active cooldown — operator override."""
    try:
        await cm.clear_cooldown()
        return {"success": True, "cooldown": {"active": False, "until": None}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/control")
async def challenge_control(req: ControlRequest):
    """Toggle the adaptive control loop."""
    try:
        if req.enabled:
            return cm.start_control_loop(interval_minutes=req.interval_minutes)
        return cm.stop_control_loop()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("challenge control failed")
        raise HTTPException(status_code=500, detail=str(e))

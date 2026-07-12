"""Strategies — Stage 2 module interface (preserved boundary).

Phase 0: CRUD endpoints only. `generate`, `backtest`, `safety` endpoints are
gated by ENABLE_LEGACY_ROUTERS and use lazy imports so a Phase-0 boot without
legacy code loaded still succeeds.

Stage 2 implementations live under `backend/legacy/engines/strategy_*.py`.
They are preserved verbatim and NOT extended here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.deps import get_current_user, require_roles
from app.core.config import get_settings
from app.db.models import UserPublic
from app.db.mongo import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyGenerateRequest(BaseModel):
    pair: str
    timeframe: str
    style: str = ""


class StrategyGenerateResponse(BaseModel):
    strategy: str


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    ir: Optional[dict] = None
    tags: List[str] = Field(default_factory=list)


class StrategyOut(BaseModel):
    strategy_id: str
    name: str
    description: Optional[str] = None
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    status: str = "draft"
    created_by: str
    created_at: datetime
    updated_at: datetime


def _require_legacy() -> None:
    if not get_settings().enable_legacy_routers:
        raise HTTPException(
            status_code=503,
            detail="feature disabled: enable ENABLE_LEGACY_ROUTERS and recover the Strategy Generation module (Phase 1)",
        )


@router.get("", response_model=List[StrategyOut])
async def list_strategies(user: UserPublic = Depends(get_current_user)):
    db = get_db()
    cur = db.strategies.find({}, {"ir": 0}).sort("created_at", -1).limit(200)
    out: list[StrategyOut] = []
    async for d in cur:
        out.append(_to_out(d))
    return out


@router.post("/generate", response_model=StrategyGenerateResponse)
async def generate_strategy(
    req: StrategyGenerateRequest,
    user: UserPublic = Depends(get_current_user),
):
    _require_legacy()
    # Lazy import — legacy engines only touched once the module is recovered.
    from legacy.engines.strategy_engine import generate_strategy_text  # noqa: WPS433

    text = await generate_strategy_text(req.pair, req.timeframe, req.style)
    return StrategyGenerateResponse(strategy=text)


@router.post("", response_model=StrategyOut, status_code=201)
async def create_strategy(
    req: StrategyCreate,
    user: UserPublic = Depends(require_roles("admin", "developer", "researcher")),
):
    db = get_db()
    now = datetime.now(timezone.utc)
    doc: dict[str, Any] = {
        "strategy_id": uuid.uuid4().hex[:16],
        "name": req.name,
        "description": req.description,
        "symbol": req.symbol,
        "timeframe": req.timeframe,
        "ir": req.ir,
        "tags": req.tags,
        "status": "draft",
        "created_by": user.user_id,
        "created_at": now,
        "updated_at": now,
    }
    await db.strategies.insert_one(doc)
    return _to_out(doc)


@router.get("/{strategy_id}", response_model=StrategyOut)
async def get_strategy(strategy_id: str, user: UserPublic = Depends(get_current_user)):
    db = get_db()
    d = await db.strategies.find_one({"strategy_id": strategy_id})
    if not d:
        raise HTTPException(status_code=404, detail="strategy not found")
    return _to_out(d)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: str,
    user: UserPublic = Depends(require_roles("admin", "developer")),
):
    db = get_db()
    res = await db.strategies.delete_one({"strategy_id": strategy_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="strategy not found")


def _to_out(d: dict) -> StrategyOut:
    return StrategyOut(
        strategy_id=d["strategy_id"],
        name=d["name"],
        description=d.get("description"),
        symbol=d.get("symbol"),
        timeframe=d.get("timeframe"),
        tags=d.get("tags", []),
        status=d.get("status", "draft"),
        created_by=d.get("created_by", ""),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
    )

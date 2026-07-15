"""Public knowledge API — v1.1.1 AI Learning Layer.

Endpoints (mounted at `/api/knowledge/*`):

    GET  /api/knowledge/status         index size + last rebuild + coverage
    POST /api/knowledge/rebuild        force rebuild (admin)
    GET  /api/knowledge/lookup         top-K neighbours + winners/losers cohort
    POST /api/knowledge/preview-prompt render exactly what would be injected

Retrieval is protected by the standard admin/user auth applied at
mount time — see `app/main.py::_mount_legacy_routers`. Rebuild is
admin-only via the extra `require_admin` dep.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines.knowledge import (
    build_block,
    format_lookup_summary,
    get_index_status,
    rebuild,
    retrieve,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class RebuildRequest(BaseModel):
    scope: str = Field("incremental", pattern="^(incremental|full)$")
    limit: Optional[int] = None


class PreviewRequest(BaseModel):
    pair: str
    timeframe: str
    style: Optional[str] = ""
    strategy_type: Optional[str] = ""
    indicators: Optional[List[str]] = None
    top_k: int = 8
    include_failures: bool = True


@router.get("/status")
async def status():
    return await get_index_status()


@router.post("/rebuild")
async def force_rebuild(req: RebuildRequest, _user=Depends(require_admin)):
    if req.scope not in ("incremental", "full"):
        raise HTTPException(status_code=422, detail="scope must be incremental|full")
    return await rebuild(scope=req.scope, limit=req.limit)


@router.get("/lookup")
async def lookup(
    pair: str = Query(..., min_length=1, max_length=32),
    timeframe: str = Query(..., min_length=1, max_length=8),
    style: Optional[str] = Query(""),
    strategy_type: Optional[str] = Query(""),
    top_k: int = Query(8, ge=1, le=32),
    include_failures: bool = Query(True),
):
    ctx = await retrieve(
        pair=pair, timeframe=timeframe,
        style=style, strategy_type=strategy_type,
        top_k=top_k, include_failures=include_failures,
    )
    return format_lookup_summary(ctx)


@router.post("/preview-prompt")
async def preview_prompt(req: PreviewRequest):
    ctx = await retrieve(
        pair=req.pair, timeframe=req.timeframe,
        style=req.style, strategy_type=req.strategy_type,
        indicators=req.indicators or [],
        top_k=req.top_k, include_failures=req.include_failures,
    )
    return {
        "prompt_block": build_block(ctx),
        "context_summary": {
            "winners_count": len(ctx.winners),
            "losers_count":  len(ctx.losers),
            "neutral_count": len(ctx.neutral),
            "total_scanned": ctx.total_scanned,
            "mutation_paths": [{"family": f, "count": n} for f, n in ctx.mutation_paths],
        },
    }

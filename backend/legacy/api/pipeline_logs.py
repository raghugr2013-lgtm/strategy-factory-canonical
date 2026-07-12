"""Phase 14.4 — Pipeline Logs API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from engines import pipeline_logs as _pl

router = APIRouter(prefix="/logs", tags=["pipeline_logs"])


@router.get("")
async def get_logs(
    limit: int = Query(100, ge=1, le=500),
    run_id: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
):
    """Return newest-first pipeline log entries.

    Filters are optional — all combinable:
      * `run_id`  — all rows for a single pipeline invocation
      * `stage`   — generation | backtest | validation | mutation | save | auto_save
      * `level`   — info | success | warn | error
      * `limit`   — 1..500 (default 100)
    """
    try:
        logs = await _pl.list_logs(
            limit=limit, run_id=run_id, stage=stage, level=level,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"count": len(logs), "logs": logs}


@router.get("/stages")
async def get_stages():
    """Return the canonical stage + level vocabularies the logger uses."""
    return {"stages": list(_pl.STAGES), "levels": list(_pl.LEVELS)}

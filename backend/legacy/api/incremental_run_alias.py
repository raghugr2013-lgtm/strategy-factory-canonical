"""Thin alias: POST /api/incremental/run

Adds the endpoint name users/playbooks expect, without changing any
business logic. Internally this delegates to the existing data-
maintenance handler (which itself calls the Dukascopy BID downloader +
BI5 incremental pipeline).

Keeps response shape identical to /api/data/maintenance/run so the UI
and external consumers can treat the two interchangeably.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.data_maintenance import run_now as data_maintenance_run_now
from api.data_maintenance import RunRequest as _DataMaintRunRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incremental", tags=["incremental-run-alias"])


class IncrementalRunRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    enforce: bool = True


@router.post("/run")
async def incremental_run(req: Optional[IncrementalRunRequest] = None):
    """Alias of /api/data/maintenance/run.

    Accepts the same {pairs, timeframes, enforce} contract and returns
    the same summary payload. Preserves error semantics.
    """
    r = req or IncrementalRunRequest()
    try:
        inner = _DataMaintRunRequest(
            pairs=r.pairs, timeframes=r.timeframes, enforce=r.enforce,
        )
        summary = await data_maintenance_run_now(inner)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("incremental/run alias failed")
        raise HTTPException(status_code=500, detail=str(e))

    # data_maintenance_run_now already returns {success: True, ...}
    return {"alias_of": "/api/data/maintenance/run", **summary}

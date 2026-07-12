"""Phase 27.3 / BI5 — Realism API.

Three minimal endpoints — no UI dashboard, no aggregations:
  • GET  /api/bi5-realism/{strategy_hash}      — read persisted block.
  • POST /api/bi5-realism/evaluate/{hash}      — manually trigger one
                                                  strategy's realism check.
  • POST /api/bi5-realism/sweep                — manually trigger the
                                                  full sweep that the
                                                  Sunday cron would run.
  • GET  /api/bi5-realism/cohort/stale-count   — ops health check
                                                  (how many eligible
                                                  strategies have a
                                                  stale or missing
                                                  realism reading).

The Sunday 03:00 UTC sweep is automatic (mounted on the orchestrator
scheduler); these endpoints exist so an operator can run an ad-hoc
check after uploading new BI5 chunks rather than waiting for the
weekly slot.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from engines import bi5_realism

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bi5-realism", tags=["bi5-realism"])


@router.get("/cohort/stale-count")
async def get_stale_count(
    freshness_days: int = Query(
        bi5_realism.REALISM_FRESHNESS_DAYS, ge=1, le=365,
    ),
) -> Dict[str, Any]:
    """How many eligible strategies (PORTFOLIO_WORTHY ∪ DEPLOYMENT_READY)
    are due for a realism re-check (no reading or older than
    ``freshness_days``)."""
    n = await bi5_realism.stale_realism_count(freshness_days=int(freshness_days))
    return {
        "freshness_days":   int(freshness_days),
        "stale_count":      n,
        "eligible_stages":  list(bi5_realism.ELIGIBLE_STAGES),
    }


@router.post("/sweep")
async def post_sweep(
    force_refresh: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    """Manually trigger a sweep across the eligible cohort.

    ``force_refresh=True`` ignores the freshness window and re-runs
    realism for every eligible strategy.
    """
    return await bi5_realism.sweep_realism(
        force_refresh=bool(force_refresh),
        limit=int(limit),
    )


@router.post("/evaluate/{strategy_hash}")
async def post_evaluate(
    strategy_hash: str,
    force_refresh: bool = Query(True),
    persist: bool = Query(True),
) -> Dict[str, Any]:
    """Run a realism check for one strategy hash. Default behaviour is
    ``force_refresh=True`` so an operator triggering the endpoint gets
    a fresh reading rather than the cached one."""
    if not strategy_hash:
        raise HTTPException(status_code=400, detail="strategy_hash required")
    result = await bi5_realism.evaluate(
        strategy_hash,
        persist=bool(persist),
        force_refresh=bool(force_refresh),
    )
    return result


@router.get("/{strategy_hash}")
async def get_realism(strategy_hash: str) -> Dict[str, Any]:
    """Read the persisted ``bi5_realism`` block from the lifecycle doc.

    Returns 404 when the strategy doesn't have a lifecycle row OR has
    not yet been realism-checked.
    """
    if not strategy_hash:
        raise HTTPException(status_code=400, detail="strategy_hash required")
    block = await bi5_realism.get_realism(strategy_hash)
    if not block:
        raise HTTPException(
            status_code=404, detail="bi5_realism_block_not_found",
        )
    return {"strategy_hash": strategy_hash, "bi5_realism": block}

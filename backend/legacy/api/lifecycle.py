"""Phase 27.2 / G6 — Lifecycle progression API.

Read-only endpoints + a single manual evaluation trigger. The
orchestrator drives evaluation autonomously every tick; these
endpoints exist so operators can:
  • inspect a strategy's lifecycle history,
  • view recent transitions across the cohort,
  • manually re-run a cohort evaluation pass (useful after
    bulk-importing strategies or clearing the persisted state),
  • view current cohort-stage distribution (for ops health checks
    without needing a separate dashboard).

Intentionally minimal — no UI, no aggregations beyond what
``strategy_lifecycle`` already exposes. New surface is one router with
five GET routes and one POST.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from engines import strategy_lifecycle as lc

logger = logging.getLogger(__name__)

# Mounted under /api/lifecycle by server.py
router = APIRouter(prefix="/lifecycle", tags=["lifecycle"])


@router.get("/cohort/stage-counts")
async def get_stage_counts():
    """Distribution of strategies across the 8 lifecycle stages.

    Cheap aggregation — used by the orchestrator and ops health checks.
    Returns a stable shape: every stage key is present (zero when no
    strategies have reached that stage yet).
    """
    counts = await lc.cohort_stage_counts()
    return {
        "stages": list(lc.LIFECYCLE_STAGES),
        "counts": counts,
        "total":  sum(counts.values()),
    }


@router.get("/transitions/recent")
async def get_recent_transitions(
    since: Optional[str] = Query(
        None,
        description="ISO timestamp lower bound (transition_at >= since).",
    ),
    limit: int = Query(50, ge=1, le=500),
):
    """Read recent transitions from ``strategy_lifecycle_history``.

    Sorted descending by ``transition_at``. Used by the orchestrator
    every tick (with a 1h since-window) and by ops to monitor
    autonomous progression.
    """
    rows = await lc.recent_transitions(since_iso=since, limit=limit)
    return {"count": len(rows), "transitions": rows}


@router.post("/evaluate")
async def post_evaluate_cohort(
    persist: bool = Query(True),
    limit: int = Query(500, ge=1, le=2000),
):
    """Manually trigger a cohort lifecycle evaluation pass.

    Same code path the orchestrator runs every tick. Returns the full
    summary so an operator can confirm transitions immediately rather
    than waiting for the next tick.
    """
    summary = await lc.evaluate_cohort(persist=bool(persist), limit=int(limit))
    return summary


@router.get("/{strategy_hash}")
async def get_lifecycle_doc(strategy_hash: str):
    """Return the persisted lifecycle doc for a single strategy hash.

    404 when the strategy has never been evaluated (i.e. no row in the
    ``strategy_lifecycle`` collection). The Explorer's `validation`
    block already carries the latest computed view; this endpoint is
    the persistence-side equivalent so callers can verify what was
    actually written for the strategy.
    """
    if not strategy_hash:
        raise HTTPException(status_code=400, detail="strategy_hash required")
    doc = await lc.get_lifecycle(strategy_hash)
    if not doc:
        raise HTTPException(
            status_code=404, detail="lifecycle_doc_not_found",
        )
    return doc


@router.get("/{strategy_hash}/history")
async def get_lifecycle_history(
    strategy_hash: str,
    limit: int = Query(50, ge=1, le=500),
):
    """Return the audit-log history for a single strategy hash."""
    if not strategy_hash:
        raise HTTPException(status_code=400, detail="strategy_hash required")
    rows = await lc.get_lifecycle_history(strategy_hash, limit=int(limit))
    return {
        "strategy_hash": strategy_hash,
        "count":         len(rows),
        "history":       rows,
    }

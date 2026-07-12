"""Semi-automatic Mutation Runner API.

Wires the `auto_mutation_runner` engine to HTTP. Runs the loop as a
background task so the HTTP POST returns immediately with a job_id;
progress is polled via GET /status.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines import auto_mutation_runner as amr

logger = logging.getLogger(__name__)

# Note: `/api` prefix is applied by server.py — this router uses `/auto`.
router = APIRouter(prefix="/auto", tags=["auto-mutation-runner"])


class AutoMutationRequest(BaseModel):
    iterations: int = Field(20, ge=1, le=200)
    strategies_per_cycle: int = Field(5, ge=1, le=20)
    pair: str = Field("EURUSD", min_length=3)
    timeframe: str = Field("H1", min_length=2)
    style: str = ""                     # free-form hint; the generator randomises
    delay_between_cycles: float = Field(0.0, ge=0.0, le=300.0)
    firm: str = "ftmo"
    auto_save: bool = True


# Keep a reference to the background task so the runtime doesn't GC it.
_BG_TASK: Optional[asyncio.Task] = None


@router.post("/mutation-runner")
async def start_auto_mutation_runner(req: AutoMutationRequest):
    """Kick off an async run. Returns immediately with the job snapshot
    (initial state). Poll `/status` for progress."""
    global _BG_TASK

    # Reject if something is already running.
    if amr.JOB_STATE["status"] == "running":
        raise HTTPException(status_code=409, detail="auto_mutation run already in progress")

    async def _runner():
        try:
            await amr.run_auto_mutation(
                iterations=req.iterations,
                strategies_per_cycle=req.strategies_per_cycle,
                pair=req.pair,
                timeframe=req.timeframe,
                style=req.style,
                delay_between_cycles=req.delay_between_cycles,
                firm=req.firm,
                auto_save=req.auto_save,
            )
        except Exception as e:
            logger.exception("auto_mutation background task crashed: %s", e)

    _BG_TASK = asyncio.create_task(_runner())

    # Give the task a tick to populate JOB_STATE before responding.
    await asyncio.sleep(0.05)
    return amr.get_live_status()


@router.get("/mutation-runner/status")
async def auto_mutation_status():
    """Live in-memory snapshot of the current (or last) run."""
    return amr.get_live_status()


@router.post("/mutation-runner/stop")
async def auto_mutation_stop():
    """Flag the currently-running loop for a graceful stop at the next
    cycle boundary. Returns {"stopping": bool}."""
    ok = amr.request_stop()
    return {"stopping": ok, "status": amr.JOB_STATE["status"]}


@router.get("/mutation-runner/cycles")
async def auto_mutation_cycles(
    job_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Persisted cycle history (latest first). Filter by job_id."""
    rows = await amr.list_cycles(job_id=job_id, limit=limit)
    return {"count": len(rows), "cycles": rows}



# ═════════════════════════════════════════════════════════════════════
# Phase 3 — scheduler-friendly single-cycle endpoint
# ═════════════════════════════════════════════════════════════════════

class RunCycleRequest(BaseModel):
    """Request body for `POST /api/auto/run-cycle`.

    Every field optional — sensible defaults let a dumb scheduler call
    `POST /api/auto/run-cycle` with an empty body and get a full cycle.
    """
    batch_size: int = Field(5, ge=1, le=20)
    pair: Optional[str] = None                  # None → auto-rotate EURUSD ↔ XAUUSD
    timeframe: str = Field("H1", min_length=2)
    style: str = ""
    firm: str = "ftmo"
    quality_filter: bool = True
    quality_threshold: float = Field(55.0, ge=0.0, le=100.0)
    optimizer: str = Field("random", pattern="^(random|ga)$")
    auto_save: bool = True
    timeout_seconds: float = Field(420.0, ge=30.0, le=900.0)


@router.post("/run-cycle")
async def auto_run_cycle(req: RunCycleRequest = RunCycleRequest()):
    """Execute ONE discovery cycle and return its summary.

    Safe for cron / external schedulers — no background task, no
    infinite loop, hard `timeout_seconds` cap. Returns 200 with
    `{"status": "skipped"}` when another run is already active so the
    scheduler can try again next tick (no 409).
    """
    result = await amr.run_single_cycle(
        batch_size=req.batch_size,
        pair=req.pair,
        timeframe=req.timeframe,
        style=req.style,
        firm=req.firm,
        quality_filter=req.quality_filter,
        quality_threshold=req.quality_threshold,
        optimizer=req.optimizer,
        auto_save=req.auto_save,
        timeout_seconds=req.timeout_seconds,
    )
    return result


@router.get("/run-cycle/history")
async def auto_run_cycle_history(limit: int = Query(50, ge=1, le=200)):
    """Return the most recent single-cycle run logs (latest first)."""
    rows = await amr.list_cycle_runs(limit=limit)
    return {"count": len(rows), "cycles": rows}


# Alias — the dashboard "Run Now" button calls this. Same handler as
# /run-cycle, just under the friendlier path the UI spec asked for.
# No new logic — pure delegation.
@router.post("/run-once")
async def auto_run_once(req: RunCycleRequest = RunCycleRequest()):
    """Manual single-cycle trigger (alias of POST /api/auto/run-cycle)."""
    return await auto_run_cycle(req)



# ═════════════════════════════════════════════════════════════════════
# Phase 3 — periodic scheduler control (every-15-min auto-discovery)
# ═════════════════════════════════════════════════════════════════════

class SchedulerStartRequest(BaseModel):
    """Body for `POST /api/auto/scheduler/start`. Every field optional —
    posting an empty body starts the scheduler at the spec defaults."""
    interval_minutes: int = Field(15, ge=1, le=1440)
    batch_size: int = Field(5, ge=1, le=20)
    quality_filter: bool = True
    quality_threshold: float = Field(55.0, ge=0.0, le=100.0)
    timeout_seconds: float = Field(420.0, ge=30.0, le=900.0)
    optimizer: str = Field("random", pattern="^(random|ga)$")
    auto_save: bool = True
    pair: Optional[str] = None
    timeframe: str = "H1"
    style: str = ""
    firm: str = "ftmo"
    # Phase 27.1 / G2 — when True (default), this scheduler defers to
    # `orchestrator_scheduler` whenever the orchestrator owns a live job.
    # ``None`` keeps the previously persisted setting (or the default
    # True on the first start). Operators wanting both schedulers to run
    # independently should pass ``false`` here.
    subordinate_to_orchestrator: Optional[bool] = None


@router.post("/scheduler/start")
async def auto_scheduler_start(req: SchedulerStartRequest = SchedulerStartRequest()):
    """Start the in-process discovery scheduler.

    Idempotent — if a job already exists it's replaced with the new
    schedule. Persists the config so the scheduler survives a backend
    restart.
    """
    from engines.auto_scheduler import start_scheduler
    payload = req.model_dump(
        exclude={"interval_minutes", "subordinate_to_orchestrator"},
        exclude_none=False,
    )
    return await start_scheduler(
        interval_minutes=req.interval_minutes,
        payload=payload,
        subordinate_to_orchestrator=req.subordinate_to_orchestrator,
    )


@router.post("/scheduler/stop")
async def auto_scheduler_stop():
    """Stop the discovery scheduler. Persists `enabled=False` so it
    stays off across restarts."""
    from engines.auto_scheduler import stop_scheduler
    return await stop_scheduler()


@router.get("/scheduler/status")
async def auto_scheduler_status():
    """Full status snapshot: enabled, runtime counters, next-run-at,
    plus the last 20 cycle rows from `auto_run_cycles`."""
    from engines.auto_scheduler import get_status
    return await get_status()



# ═════════════════════════════════════════════════════════════════════
# Evolution telemetry endpoint (read-only)
# ═════════════════════════════════════════════════════════════════════

@router.get("/evolution/weights")
async def evolution_weights(regime_type: Optional[str] = None):
    """Return the current mutation-type weights the evolution engine
    would apply RIGHT NOW. Read-only, cheap — safe for an ops dashboard
    or health check.

    Response:
        {
          "active": true|false,        # False → fallback to uniform random
          "reason": null|"insufficient_logs"|"regime_insufficient"|...,
          "regime_type": "trending"|...,    # echo of the query param
          "weights": {mutation_type: weight, ...} | null,
          "stats": {
            "total_logs": 135,
            "per_type": { type: {success_rate, avg_pf, ...}, ... },
            "min_logs_for_weights": 50,
            "min_logs_per_regime": 20,
          }
        }
    """
    from engines.evolution_engine import (
        compute_mutation_weights, get_evolution_stats,
        MIN_LOGS_FOR_WEIGHTS, MIN_LOGS_PER_REGIME,
    )
    weights = await compute_mutation_weights(regime_type=regime_type)
    stats = await get_evolution_stats(regime_type=regime_type)
    reason = None
    if weights is None:
        total = int((stats or {}).get("total_logs") or 0)
        if regime_type and total < MIN_LOGS_PER_REGIME:
            reason = "regime_insufficient"
        elif total < MIN_LOGS_FOR_WEIGHTS:
            reason = "insufficient_logs"
        else:
            reason = "unknown"
    return {
        "active": weights is not None,
        "reason": reason,
        "regime_type": regime_type,
        "weights": weights,
        "stats": {
            **(stats or {}),
            "min_logs_for_weights": MIN_LOGS_FOR_WEIGHTS,
            "min_logs_per_regime": MIN_LOGS_PER_REGIME,
        },
    }

"""
Phase 22 — AI Orchestrator API.

Thin FastAPI surface around `engines.ai_orchestrator` plus a scheduler
control layer that wraps `engines.orchestrator_scheduler`.

Endpoints:
    GET  /api/orchestrator/state               — current snapshot (no side effect)
    POST /api/orchestrator/decide              — snapshot + recommendations
    POST /api/orchestrator/tick                — full observe → decide → execute
    POST /api/orchestrator/scheduler/start     — start 15-min (configurable) scheduler
    POST /api/orchestrator/scheduler/stop      — stop scheduler
    GET  /api/orchestrator/scheduler/status    — scheduler status + last decision

Concurrency / safety:
    * Scheduler-level overlap guard is enforced inside
      `engines.orchestrator_scheduler` (APScheduler `max_instances=1` +
      `coalesce=True`).
    * `/tick` (execute=True) and the scheduler share a small in-process
      cooldown guard (default 120s) so a human spamming "Run Now" cannot
      stack executions on top of a scheduled tick.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engines import ai_orchestrator as orc
from engines import orchestrator_scheduler as orc_sched
from engines import env_priority

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])

# ── Cooldown guard ──────────────────────────────────────────────────
# Wall-clock seconds between two real `execute=True` runs. Advisory
# (execute=False) calls are NOT rate-limited. The scheduler runs at
# 15+ min intervals so this never blocks a scheduled tick — it only
# stops a human / external caller from stacking manual "Run Now"
# clicks on top of an in-flight execution.
COOLDOWN_SECONDS = 120
_last_execute_at: float = 0.0  # monotonic timestamp


def _cooldown_remaining() -> float:
    """Seconds left until the next real execute is allowed (0 if ready)."""
    if _last_execute_at <= 0:
        return 0.0
    elapsed = time.monotonic() - _last_execute_at
    return max(0.0, COOLDOWN_SECONDS - elapsed)


# ── Pydantic models ─────────────────────────────────────────────────

class TickRequest(BaseModel):
    execute: bool = Field(
        False,
        description=(
            "When true, the orchestrator executes the planned actions. "
            "When false (default), only advisory recommendations are "
            "returned — safe preview."
        ),
    )


class SchedulerStartRequest(BaseModel):
    interval_minutes: int = Field(
        15, ge=1, le=1440,
        description="Tick interval in minutes (default 15, max 1440).",
    )


# ── Orchestrator endpoints ──────────────────────────────────────────

@router.get("/state")
async def orchestrator_state() -> Dict[str, Any]:
    state = await orc.observe_state()
    return {"observed_at": state.get("observed_at"), "state": state}


@router.post("/decide")
async def orchestrator_decide() -> Dict[str, Any]:
    state = await orc.observe_state()
    recs = orc.decide(state)
    return {
        "observed_at": state.get("observed_at"),
        "state": state,
        "recommendations": recs,
        "executions": None,
        "executed": False,
    }


@router.post("/tick")
async def orchestrator_tick(req: TickRequest = TickRequest()) -> Dict[str, Any]:
    """One full orchestration tick.

    When `execute=true`, an in-process cooldown guard prevents two real
    executions inside `COOLDOWN_SECONDS`. A blocked call returns a
    `cooldown_skip` payload (HTTP 200) with `seconds_remaining` so
    the UI can render a friendly notice without retrying.
    """
    global _last_execute_at

    if req.execute:
        remaining = _cooldown_remaining()
        if remaining > 0:
            state = await orc.observe_state()
            recs = orc.decide(state)
            logger.info(
                "[orchestrator/tick] cooldown_skip — %.1fs remaining",
                remaining,
            )
            return {
                "observed_at": state.get("observed_at"),
                "state": state,
                "recommendations": recs,
                "executions": None,
                "executed": False,
                "status": "cooldown_skip",
                "cooldown_seconds": COOLDOWN_SECONDS,
                "seconds_remaining": round(remaining, 1),
            }

    result = await orc.run_tick(execute_actions=bool(req.execute))
    if req.execute:
        _last_execute_at = time.monotonic()
    result["status"] = result.get("status") or (
        "executed" if req.execute else "preview"
    )
    return result


# ── Scheduler control endpoints ─────────────────────────────────────

@router.post("/scheduler/start")
async def orchestrator_scheduler_start(
    req: SchedulerStartRequest = SchedulerStartRequest(),
) -> Dict[str, Any]:
    """Start (or replace) the periodic orchestrator scheduler."""
    return await orc_sched.start_scheduler(interval_minutes=req.interval_minutes)


@router.post("/scheduler/stop")
async def orchestrator_scheduler_stop() -> Dict[str, Any]:
    """Stop the periodic orchestrator scheduler (idempotent)."""
    return await orc_sched.stop_scheduler()


@router.get("/scheduler/status")
async def orchestrator_scheduler_status() -> Dict[str, Any]:
    """Return scheduler runtime + last decision snapshot.

    Augments the engine's status payload with the cooldown window so
    the UI can disable "Run Now" while a cooldown is active.
    """
    status = await orc_sched.get_status()
    status["cooldown"] = {
        "seconds": COOLDOWN_SECONDS,
        "remaining": round(_cooldown_remaining(), 1),
    }
    return status


# ════════════════════════════════════════════════════════════════════
# Phase 23 — Adaptive Environment Priority
# ════════════════════════════════════════════════════════════════════

class EnvPriorityTierPatch(BaseModel):
    pairs: Optional[list] = None
    timeframes: Optional[list] = None
    weight: Optional[float] = None


class EnvPriorityKnobsPatch(BaseModel):
    ema_alpha: Optional[float] = None
    decay_rate: Optional[float] = None
    exploratory_floor: Optional[float] = None
    max_env_share: Optional[float] = None
    allow_noisy_scans: Optional[bool] = None
    adaptation_enabled: Optional[bool] = None
    score_weights: Optional[Dict[str, float]] = None


class EnvPriorityConfigPatch(BaseModel):
    tiers: Optional[Dict[str, EnvPriorityTierPatch]] = None
    knobs: Optional[EnvPriorityKnobsPatch] = None


class EnvPrioritySampleRequest(BaseModel):
    n: int = Field(8, ge=1, le=64)
    allow_noisy: Optional[bool] = None
    seed: Optional[int] = None


@router.get("/env-priority/config")
async def env_priority_get_config() -> Dict[str, Any]:
    return await env_priority.get_config()


@router.post("/env-priority/config")
async def env_priority_save_config(patch: EnvPriorityConfigPatch) -> Dict[str, Any]:
    payload = patch.model_dump(exclude_none=True)
    if not payload:
        return await env_priority.get_config()
    try:
        cfg = await env_priority.save_config(payload)
    except ValueError as e:
        raise __import__("fastapi").HTTPException(status_code=400, detail=str(e))
    return cfg


@router.get("/env-priority/stats")
async def env_priority_stats() -> Dict[str, Any]:
    rows = await env_priority.get_stats()
    cfg = await env_priority.get_config()
    allocation = await env_priority.preview_allocation(
        allow_noisy=bool(cfg["knobs"].get("allow_noisy_scans")),
    )
    alloc_map = {
        f"{r['pair']}|{r['timeframe']}": r["weight"] for r in allocation
    }
    for row in rows:
        row["allocation"] = alloc_map.get(row["key"], 0.0)
    return {"config": cfg, "envs": rows}


@router.post("/env-priority/sample")
async def env_priority_sample(req: EnvPrioritySampleRequest) -> Dict[str, Any]:
    picks = await env_priority.pick_environments(
        req.n, allow_noisy=req.allow_noisy, seed=req.seed,
    )
    return {
        "n": req.n,
        "allow_noisy": bool(req.allow_noisy)
            if req.allow_noisy is not None else None,
        "picks": [{"pair": p, "timeframe": tf} for p, tf in picks],
    }


@router.post("/env-priority/reset")
async def env_priority_reset() -> Dict[str, Any]:
    return await env_priority.reset_multipliers()


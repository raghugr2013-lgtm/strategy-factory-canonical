"""
Phase 22 — Orchestrator scheduler.

Wires `engines.ai_orchestrator.run_tick(execute_actions=True)` into a
periodic APScheduler job. Mirrors the pattern of
`engines/auto_scheduler.py` but for the orchestrator (decision engine)
rather than the discovery cycle.

Single-tenant, in-process, idempotent. The scheduler is enabled via
`POST /api/orchestrator/scheduler/start` and survives backend restart
through a Mongo-persisted config row.

Public surface:
    • start_scheduler(interval_minutes=15) -> dict
    • stop_scheduler()                     -> dict
    • get_status()                         -> dict
    • restore_if_enabled()                 -> called at FastAPI startup

Safety:
    • `max_instances=1` + `coalesce=True` — the scheduler will NEVER
      run two ticks in parallel, even if a tick overruns its window.
    • The orchestrator itself ALSO guards against stacking runs (its
      `RUN_ACTIVE` rule short-circuits any trigger_multi_cycle action
      when a multi-cycle run is already in flight).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from engines import ai_orchestrator as orc
from engines.db import get_db

logger = logging.getLogger(__name__)

CONFIG_COLL = "orchestrator_scheduler_config"
DEFAULT_INTERVAL_MIN = 15
JOB_ID = "ai_orchestrator_tick"

# Phase 27.3 — weekly BI5 realism sweep job. Mounted on the same
# AsyncIOScheduler instance as the orchestrator tick (the user-approved
# G2 "single authority" design); the orchestrator becomes the home of
# every recurring background job that should fire only when the
# orchestration authority is active.
REALISM_JOB_ID = "bi5_realism_sweep"
REALISM_DAY_OF_WEEK = "sun"   # Sunday
REALISM_HOUR = 3              # 03:00 UTC

_scheduler: Optional[AsyncIOScheduler] = None
_runtime: Dict[str, Any] = {
    "enabled": False,
    "started_at": None,
    "last_tick_at": None,
    "tick_count": 0,
    "executed_count": 0,
    "advisory_count": 0,
    "last_recommendations": [],
    "last_executions": [],
    "last_error": None,
    # Phase 27.3 — weekly BI5 realism sweep observability.
    "last_realism_sweep_at":      None,
    "last_realism_sweep_summary": None,
    "realism_sweep_count":        0,
}


# ── Persistence (so the scheduler survives restart) ────────────────

async def _load_config() -> Dict[str, Any]:
    db = get_db()
    doc = await db[CONFIG_COLL].find_one({"_id": "default"}, {"_id": 0})
    return doc or {}


async def _save_config(*, enabled: bool, interval_minutes: int) -> None:
    db = get_db()
    await db[CONFIG_COLL].update_one(
        {"_id": "default"},
        {"$set": {
            "enabled": enabled,
            "interval_minutes": interval_minutes,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )


# ── Scheduler internals ───────────────────────────────────────────

def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def _build_job():
    async def _tick() -> None:
        _runtime["last_tick_at"] = datetime.now(timezone.utc).isoformat()
        _runtime["tick_count"] += 1
        try:
            result = await orc.run_tick(execute_actions=True)
            recs = result.get("recommendations") or []
            execs = result.get("executions") or []
            _runtime["last_recommendations"] = recs
            _runtime["last_executions"] = execs
            executed_real = [
                e for e in execs if e.get("status") == "executed"
            ]
            advisory = [
                e for e in execs if e.get("status") == "advisory"
            ]
            _runtime["executed_count"] += len(executed_real)
            _runtime["advisory_count"] += len(advisory)
            _runtime["last_error"] = None
            logger.info(
                "[orchestrator/scheduler] tick #%d → %d recs, %d executed, %d advisory",
                _runtime["tick_count"], len(recs),
                len(executed_real), len(advisory),
            )
        except Exception as e:
            _runtime["last_error"] = str(e)[:240]
            logger.exception("[orchestrator/scheduler] tick crashed")
    return _tick


# Phase 27.3 — Sunday 03:00 UTC BI5 realism sweep job.
# Lives on the orchestrator's scheduler so it only fires while the
# orchestration authority is active (consistent with the G2 design:
# the orchestrator is the single home of recurring background work).
def _build_realism_sweep_job():
    async def _sweep() -> None:
        from engines import bi5_realism
        ts = datetime.now(timezone.utc).isoformat()
        try:
            summary = await bi5_realism.sweep_realism(
                force_refresh=False,
            )
            _runtime["realism_sweep_count"] += 1
            _runtime["last_realism_sweep_at"] = ts
            # Keep only counters in runtime — full result dict is too
            # large for an in-memory snapshot. The sweep's per-strategy
            # results are persisted on the lifecycle docs anyway.
            _runtime["last_realism_sweep_summary"] = {
                "started_at":   summary.get("started_at"),
                "finished_at":  summary.get("finished_at"),
                "scanned":      summary.get("scanned"),
                "evaluated":    summary.get("evaluated"),
                "ok":           summary.get("ok"),
                "partial":      summary.get("partial"),
                "fail":         summary.get("fail"),
                "data_missing": summary.get("data_missing"),
                "fresh_cache":  summary.get("fresh_cache"),
                "errors":       summary.get("errors"),
            }
            logger.info(
                "[orchestrator/scheduler] realism sweep #%d → "
                "scanned=%d evaluated=%d ok=%d partial=%d fail=%d "
                "data_missing=%d fresh_cache=%d errors=%d",
                _runtime["realism_sweep_count"],
                summary.get("scanned"), summary.get("evaluated"),
                summary.get("ok"), summary.get("partial"),
                summary.get("fail"), summary.get("data_missing"),
                summary.get("fresh_cache"), summary.get("errors"),
            )
        except Exception:
            logger.exception("[orchestrator/scheduler] realism sweep crashed")
    return _sweep


# ── Public API ────────────────────────────────────────────────────

async def start_scheduler(
    *, interval_minutes: int = DEFAULT_INTERVAL_MIN,
) -> Dict[str, Any]:
    """Idempotent — replaces any existing job with the new schedule."""
    interval_minutes = max(1, min(int(interval_minutes), 1440))

    sched = _ensure_scheduler()
    if sched.get_job(JOB_ID):
        sched.remove_job(JOB_ID)
    sched.add_job(
        _build_job(),
        trigger=IntervalTrigger(minutes=interval_minutes),
        id=JOB_ID,
        coalesce=True,
        max_instances=1,
    )
    # Phase 27.3 — also (re-)mount the weekly BI5 realism sweep on the
    # same scheduler instance. Idempotent — replace if it exists.
    if sched.get_job(REALISM_JOB_ID):
        sched.remove_job(REALISM_JOB_ID)
    sched.add_job(
        _build_realism_sweep_job(),
        trigger=CronTrigger(
            day_of_week=REALISM_DAY_OF_WEEK,
            hour=REALISM_HOUR,
            minute=0,
            timezone="UTC",
        ),
        id=REALISM_JOB_ID,
        coalesce=True,
        max_instances=1,
    )
    if not sched.running:
        sched.start()

    _runtime.update({
        "enabled": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    await _save_config(enabled=True, interval_minutes=interval_minutes)
    logger.info(
        "[orchestrator/scheduler] STARTED — interval=%dm",
        interval_minutes,
    )
    return {"enabled": True, "interval_minutes": interval_minutes}


async def stop_scheduler() -> Dict[str, Any]:
    sched = _ensure_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
    global _scheduler
    _scheduler = None
    _runtime["enabled"] = False
    cfg = await _load_config()
    await _save_config(
        enabled=False,
        interval_minutes=int(cfg.get("interval_minutes") or DEFAULT_INTERVAL_MIN),
    )
    logger.info("[orchestrator/scheduler] STOPPED")
    return {"enabled": False}


async def get_status() -> Dict[str, Any]:
    sched = _scheduler
    cfg = await _load_config()
    next_run = None
    next_realism_sweep = None
    if sched is not None and sched.running:
        job = sched.get_job(JOB_ID)
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
        # Phase 27.3 — also expose the next realism-sweep slot.
        rjob = sched.get_job(REALISM_JOB_ID)
        if rjob and rjob.next_run_time:
            next_realism_sweep = rjob.next_run_time.isoformat()
    return {
        "enabled": bool(_runtime["enabled"]),
        "interval_minutes": int(cfg.get("interval_minutes") or DEFAULT_INTERVAL_MIN),
        "started_at": _runtime["started_at"],
        "last_tick_at": _runtime["last_tick_at"],
        "tick_count": _runtime["tick_count"],
        "executed_count": _runtime["executed_count"],
        "advisory_count": _runtime["advisory_count"],
        "next_run_at": next_run,
        "last_error": _runtime["last_error"],
        "last_recommendations": _runtime["last_recommendations"],
        "last_executions": _runtime["last_executions"],
        # Phase 27.3 — BI5 realism sweep observability.
        "realism_sweep": {
            "schedule":    f"{REALISM_DAY_OF_WEEK.upper()} {REALISM_HOUR:02d}:00 UTC",
            "next_run_at": next_realism_sweep,
            "last_run_at": _runtime["last_realism_sweep_at"],
            "run_count":   _runtime["realism_sweep_count"],
            "last_summary": _runtime["last_realism_sweep_summary"],
        },
    }


async def restore_if_enabled() -> Optional[Dict[str, Any]]:
    """Called at FastAPI startup. Re-arms the scheduler when its
    persisted config has `enabled=True`. Idempotent — safe to call
    multiple times."""
    cfg = await _load_config()
    if not cfg.get("enabled"):
        return None
    interval = int(cfg.get("interval_minutes") or DEFAULT_INTERVAL_MIN)
    return await start_scheduler(interval_minutes=interval)


# ── Phase 27.1 / G2 — subordination probe ──────────────────────────
# Cheap, in-memory check (no DB I/O) used by `auto_scheduler` to decide
# whether to defer its tick. Returns True iff this scheduler currently
# owns a live APScheduler job and the runtime flag confirms enablement.
def is_active() -> bool:
    """True iff the orchestrator scheduler has a live job right now.

    Read-only, no I/O — safe to call from any other engine's hot path.
    Returns False on any inconsistency (no scheduler, not running, no
    job registered, runtime flag flipped).
    """
    sched = _scheduler
    if sched is None or not sched.running:
        return False
    if not _runtime.get("enabled"):
        return False
    try:
        return sched.get_job(JOB_ID) is not None
    except Exception:                                       # pragma: no cover
        return False

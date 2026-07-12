"""Auto-discovery scheduler — every-15-min trigger for `/api/auto/run-cycle`.

In-process scheduler built on the same APScheduler that powers the
existing `auto_data_maintainer`. One job, one tick per interval, no
overlap, no infinite while-True. Each tick simply calls
`auto_mutation_runner.run_single_cycle(...)` — the cycle helper itself
already enforces the lock, hard timeout, and persistence to
`auto_run_cycles`. The scheduler adds no new logic — only periodic
triggering, monitoring, and restart-after-reboot.

Public surface (consumed by `api/auto_scheduler.py`):
    • start_scheduler(payload)  — idempotent
    • stop_scheduler()
    • get_status()              — runtime state + next run + last 20 runs
    • restore_if_enabled()      — called at FastAPI startup
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.auto_mutation_runner import (
    list_cycle_runs,
    run_single_cycle,
)
from engines.db import get_db

logger = logging.getLogger(__name__)

CONFIG_COLL = "auto_scheduler_config"
DEFAULT_INTERVAL_MIN = 15
DEFAULT_PAYLOAD: Dict[str, Any] = {
    "batch_size": 5,
    "quality_filter": True,
    "quality_threshold": 35.0,
    "timeout_seconds": 420.0,
    "optimizer": "random",
    "auto_save": True,
}
HISTORY_LIMIT = 20

# Phase 27.1 / G2 — when True (default), this scheduler defers to
# `orchestrator_scheduler` whenever the orchestrator owns a live job.
# Operators can flip to False to keep both schedulers running in
# parallel (escape hatch / feature flag). Persisted alongside the rest
# of the config so the choice survives backend restart.
SUBORDINATE_DEFAULT = True

_scheduler: Optional[AsyncIOScheduler] = None
_runtime: Dict[str, Any] = {
    "enabled": False,
    "started_at": None,
    "last_tick_at": None,
    "last_status": None,
    "last_reason": None,
    "tick_count": 0,
    "skip_count": 0,
    "error_count": 0,
    # G2: counts ticks that were no-ops because the orchestrator was active.
    "subordinate_skip_count": 0,
}


# ─────────────────────────────────────────────────────────────────────
# Persistent config (so the scheduler survives backend restart)
# ─────────────────────────────────────────────────────────────────────

async def _load_config() -> Dict[str, Any]:
    db = get_db()
    doc = await db[CONFIG_COLL].find_one({"_id": "discovery"}, {"_id": 0})
    if not doc:
        return {
            "enabled": False,
            "interval_minutes": DEFAULT_INTERVAL_MIN,
            "subordinate_to_orchestrator": SUBORDINATE_DEFAULT,
            "payload": dict(DEFAULT_PAYLOAD),
        }
    # Backfill any missing keys from defaults.
    return {
        "enabled": bool(doc.get("enabled")),
        "interval_minutes": int(doc.get("interval_minutes") or DEFAULT_INTERVAL_MIN),
        # G2: legacy configs (pre-Phase-27.1) lack this key; default to True
        # so existing scheduler installs become subordinate on first restart.
        "subordinate_to_orchestrator": bool(
            doc.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT)
        ),
        "payload": {**DEFAULT_PAYLOAD, **(doc.get("payload") or {})},
    }


async def _save_config(
    *,
    enabled: bool,
    interval_minutes: int,
    payload: Dict[str, Any],
    subordinate_to_orchestrator: Optional[bool] = None,
) -> None:
    db = get_db()
    update: Dict[str, Any] = {
        "enabled": bool(enabled),
        "interval_minutes": int(interval_minutes),
        "payload": dict(payload),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    # G2: preserve subordinate flag across saves; only overwrite when
    # an explicit value is supplied by the caller.
    if subordinate_to_orchestrator is not None:
        update["subordinate_to_orchestrator"] = bool(subordinate_to_orchestrator)
    await db[CONFIG_COLL].update_one(
        {"_id": "discovery"},
        {"$set": update},
        upsert=True,
    )


# ─────────────────────────────────────────────────────────────────────
# Scheduler internals
# ─────────────────────────────────────────────────────────────────────

def _ensure_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


# Phase 27.1 / G2 — defer to orchestrator scheduler when active.
async def _is_subordinated() -> bool:
    """Return True iff this scheduler should skip its tick because
    the orchestrator scheduler currently owns the discovery loop AND
    we are configured to defer to it. Cheap, exception-safe.

    Resolution order:
      1. Read persisted `subordinate_to_orchestrator` flag (default True).
      2. Probe `orchestrator_scheduler.is_active()` (in-memory, no I/O).
    Any failure returns False — the tick proceeds normally rather than
    silently disabling the scheduler.
    """
    try:
        cfg = await _load_config()
    except Exception:
        return False
    if not cfg.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT):
        return False
    try:
        from engines import orchestrator_scheduler as orc_sched
        return bool(orc_sched.is_active())
    except Exception:                                       # pragma: no cover
        return False


def _build_job(interval_minutes: int, payload: Dict[str, Any]):
    async def _tick() -> None:
        """One scheduler tick → one discovery cycle."""
        _runtime["last_tick_at"] = datetime.now(timezone.utc).isoformat()
        _runtime["tick_count"] += 1
        # Phase 27.1 / G2 — subordinate skip path. The orchestrator
        # scheduler is the canonical discovery driver when both are
        # enabled; this scheduler then becomes a passive standby that
        # records the skip but neither runs a cycle nor opens a
        # research_run lineage doc (subordinate ticks must not pollute
        # lineage). Counter is surfaced through `get_status()` so the
        # UI can show that ticks are deliberately deferred.
        if await _is_subordinated():
            _runtime["subordinate_skip_count"] += 1
            _runtime["last_status"] = "skipped_subordinate"
            _runtime["last_reason"] = "orchestrator_scheduler_active"
            logger.info(
                "[auto/scheduler] tick #%d → skipped_subordinate "
                "(orchestrator_scheduler is active)",
                _runtime["tick_count"],
            )
            return
        # G1 — every auto-scheduler tick opens its own research_run.
        # That makes manual + scheduler + orchestrator paths uniform.
        rrid: Optional[str] = None
        try:
            from engines import research_lineage
            rrid = await research_lineage.new_research_run(
                trigger_type="auto_scheduler_tick",
                trigger_reason=f"tick_{_runtime['tick_count']}",
                config={
                    "interval_minutes": interval_minutes,
                    "payload": dict(payload or {}),
                },
            )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] auto_scheduler new_research_run failed: %s", e)
        status_for_lineage = "completed"
        last_error: Optional[str] = None
        try:
            res = await run_single_cycle(
                batch_size=int(payload.get("batch_size") or 5),
                pair=payload.get("pair") or None,
                timeframe=payload.get("timeframe") or "H1",
                style=payload.get("style") or "",
                firm=payload.get("firm") or "ftmo",
                quality_filter=bool(payload.get("quality_filter", True)),
                quality_threshold=float(payload.get("quality_threshold", 35.0)),
                optimizer=str(payload.get("optimizer", "random")),
                auto_save=bool(payload.get("auto_save", True)),
                timeout_seconds=float(payload.get("timeout_seconds", 420.0)),
                research_run_id=rrid,
            )
            _runtime["last_status"] = res.get("status")
            _runtime["last_reason"] = res.get("reason")
            if res.get("status") == "skipped":
                _runtime["skip_count"] += 1
                status_for_lineage = "skipped"
            elif res.get("status") in ("error", "timeout"):
                _runtime["error_count"] += 1
                status_for_lineage = res["status"]
                last_error = res.get("reason")
            logger.info(
                "[auto/scheduler] tick #%d → status=%s pair=%s saved=%s rrid=%s",
                _runtime["tick_count"], res.get("status"),
                res.get("pair"), res.get("strategies_saved"), rrid,
            )
        except Exception as e:
            _runtime["last_status"] = "error"
            _runtime["last_reason"] = str(e)[:240]
            _runtime["error_count"] += 1
            status_for_lineage = "error"
            last_error = str(e)[:240]
            logger.exception("[auto/scheduler] tick crashed")
        finally:
            if rrid:
                try:
                    from engines import research_lineage
                    await research_lineage.mark_finished(
                        rrid, status=status_for_lineage, error=last_error,
                    )
                except Exception:                           # pragma: no cover
                    pass
    return _tick


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

async def start_scheduler(
    *,
    interval_minutes: int = DEFAULT_INTERVAL_MIN,
    payload: Optional[Dict[str, Any]] = None,
    subordinate_to_orchestrator: Optional[bool] = None,
) -> Dict[str, Any]:
    """Idempotent — replaces any existing job with the new schedule.

    The first run is delayed by `interval_minutes` so an admin who just
    flipped the toggle in the UI doesn't unexpectedly burn a cycle on
    a half-initialised system. Use `POST /api/auto/run-cycle` for a
    one-shot manual kick.

    Phase 27.1 / G2: ``subordinate_to_orchestrator`` controls whether
    this scheduler defers to ``orchestrator_scheduler`` when both are
    enabled. ``None`` keeps the previously persisted setting (or the
    package default ``SUBORDINATE_DEFAULT=True`` on first start).
    """
    interval_minutes = max(1, min(int(interval_minutes), 1440))
    pay = {**DEFAULT_PAYLOAD, **(payload or {})}

    sched = _ensure_scheduler()
    if sched.get_job("auto_discovery"):
        sched.remove_job("auto_discovery")
    sched.add_job(
        _build_job(interval_minutes, pay),
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="auto_discovery",
        coalesce=True,
        max_instances=1,   # belt-and-braces: scheduler-level overlap guard
    )
    if not sched.running:
        sched.start()

    _runtime.update({
        "enabled": True,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    await _save_config(
        enabled=True,
        interval_minutes=interval_minutes,
        payload=pay,
        subordinate_to_orchestrator=subordinate_to_orchestrator,
    )
    # Re-read so the response advertises the resolved subordinate flag
    # (caller may have left it as None to inherit the persisted value).
    cfg_after = await _load_config()
    logger.info(
        "[auto/scheduler] STARTED — interval=%dm subordinate=%s payload=%s",
        interval_minutes,
        cfg_after.get("subordinate_to_orchestrator"),
        pay,
    )
    return {
        "enabled": True,
        "interval_minutes": interval_minutes,
        "subordinate_to_orchestrator": bool(
            cfg_after.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT)
        ),
        "payload": pay,
    }


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
        payload=dict(cfg.get("payload") or DEFAULT_PAYLOAD),
        # Preserve the persisted subordinate flag through stop/start cycles.
        subordinate_to_orchestrator=bool(
            cfg.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT)
        ),
    )
    logger.info("[auto/scheduler] STOPPED")
    return {"enabled": False}


async def get_status() -> Dict[str, Any]:
    """Snapshot for monitoring UI / cron health checks.

    Combines:
      • persistent config (enabled, interval, payload, subordinate flag),
      • in-memory runtime (tick counts, last status, subordinate skips),
      • scheduler-level next_run_time,
      • last `HISTORY_LIMIT` cycle rows from `auto_run_cycles`.

    Phase 27.1 / G2: surfaces ``runtime.is_subordinated_now`` so the UI
    can show a "deferring to orchestrator" pill without a separate API call.
    """
    cfg = await _load_config()
    next_run = None
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("auto_discovery")
        if job and job.next_run_time:
            next_run = job.next_run_time.astimezone(timezone.utc).isoformat()
    history = await list_cycle_runs(limit=HISTORY_LIMIT)
    is_subordinated_now = False
    if cfg.get("enabled") and (_scheduler and _scheduler.running):
        try:
            is_subordinated_now = await _is_subordinated()
        except Exception:                                   # pragma: no cover
            is_subordinated_now = False
    return {
        "enabled": bool(cfg.get("enabled") and (_scheduler and _scheduler.running)),
        "config": {
            "interval_minutes": int(cfg.get("interval_minutes") or DEFAULT_INTERVAL_MIN),
            "subordinate_to_orchestrator": bool(
                cfg.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT)
            ),
            "payload": cfg.get("payload") or dict(DEFAULT_PAYLOAD),
        },
        "runtime": {
            "started_at": _runtime["started_at"],
            "last_tick_at": _runtime["last_tick_at"],
            "last_status": _runtime["last_status"],
            "last_reason": _runtime["last_reason"],
            "tick_count": _runtime["tick_count"],
            "skip_count": _runtime["skip_count"],
            "error_count": _runtime["error_count"],
            "subordinate_skip_count": _runtime["subordinate_skip_count"],
            "is_subordinated_now": bool(is_subordinated_now),
            "next_run_at": next_run,
        },
        "history": history,
    }


async def restore_if_enabled() -> None:
    """Called on FastAPI startup. Re-enables the scheduler when it was
    ON before the last restart so deployment / supervisor restarts
    don't silently kill the discovery loop."""
    try:
        cfg = await _load_config()
    except Exception:
        logger.exception("[auto/scheduler] could not load config; not restoring")
        return
    if not cfg.get("enabled"):
        return
    try:
        await start_scheduler(
            interval_minutes=int(cfg.get("interval_minutes") or DEFAULT_INTERVAL_MIN),
            payload=cfg.get("payload") or dict(DEFAULT_PAYLOAD),
            # Preserve persisted subordinate flag across restarts.
            subordinate_to_orchestrator=bool(
                cfg.get("subordinate_to_orchestrator", SUBORDINATE_DEFAULT)
            ),
        )
    except Exception:
        logger.exception("[auto/scheduler] failed to restore on startup")

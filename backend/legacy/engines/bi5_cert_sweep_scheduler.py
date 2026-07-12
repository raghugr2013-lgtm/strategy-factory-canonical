"""BI5 R2 / B-4 — weekly auto-sweep scheduler.

Registers a single APScheduler `CronTrigger` job that fires every
Sunday at 03:00 UTC and runs `engines.bi5_cert_sweep.run_sweep` with
`trigger="auto_weekly"`. Idempotent on import (the scheduler is a
module-level singleton).

The scheduler is started by `server.py` at app boot inside the
existing FastAPI startup hook. It is a pure cadence layer — it owns no
sweep logic of its own — so the sweep can also be triggered manually
via `POST /api/admin/bi5/sweep`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_ID = "bi5_cert_sweep_weekly"
TIMEZONE = "UTC"
CRON_KWARGS = dict(day_of_week="sun", hour=3, minute=0, second=0)

_scheduler: Optional[AsyncIOScheduler] = None
_runtime: Dict[str, Any] = {
    "started_at":    None,
    "tick_count":    0,
    "last_tick_at":  None,
    "last_status":   None,
    "last_run_id":   None,
    "last_error":    None,
}


async def _tick() -> None:
    """One Sunday 03:00 UTC tick → one auto-sweep."""
    from engines.bi5_cert_sweep import run_sweep

    _runtime["tick_count"] += 1
    _runtime["last_tick_at"] = datetime.now(timezone.utc).isoformat()
    try:
        res = await run_sweep(trigger="auto_weekly")
        _runtime["last_run_id"] = res.run_id
        _runtime["last_status"] = "ok"
        _runtime["last_error"] = None
        logger.info(
            "[bi5_cert_sweep] auto_weekly tick #%d → run_id=%s "
            "discovered=%d processed=%d pass=%d warn=%d fail=%d "
            "skipped=%d errors=%d duration=%.2fs",
            _runtime["tick_count"], res.run_id,
            res.discovered, res.processed,
            res.pass_count, res.warn_count, res.fail_count,
            res.skipped, res.errors, res.duration_seconds,
        )
    except Exception as e:                                # pragma: no cover
        _runtime["last_status"] = "error"
        _runtime["last_error"] = str(e)[:240]
        logger.exception(
            "[bi5_cert_sweep] auto_weekly tick crashed: %s", e,
        )


def start_scheduler() -> Dict[str, Any]:
    """Idempotent start of the weekly cadence."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return get_status()
    sch = _scheduler or AsyncIOScheduler(timezone=TIMEZONE)
    if sch.get_job(JOB_ID) is None:
        sch.add_job(
            _tick,
            trigger=CronTrigger(timezone=TIMEZONE, **CRON_KWARGS),
            id=JOB_ID,
            replace_existing=True,
            misfire_grace_time=600,
            coalesce=True,
            max_instances=1,
        )
    if not sch.running:
        sch.start()
    _scheduler = sch
    _runtime["started_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(
        "[bi5_cert_sweep] scheduler armed · cron=Sun 03:00 UTC · job=%s",
        JOB_ID,
    )
    return get_status()


def stop_scheduler() -> Dict[str, Any]:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as e:                            # pragma: no cover
            logger.warning("[bi5_cert_sweep] scheduler shutdown failed: %s", e)
    return get_status()


def get_status() -> Dict[str, Any]:
    sch = _scheduler
    job_info: Optional[Dict[str, Any]] = None
    next_run: Optional[str] = None
    if sch is not None:
        job = sch.get_job(JOB_ID)
        if job is not None:
            next_run = (
                job.next_run_time.astimezone(timezone.utc).isoformat()
                if job.next_run_time else None
            )
            job_info = {
                "id":            job.id,
                "next_run_utc":  next_run,
                "trigger_type":  "cron",
                "cron":          "Sun 03:00 UTC",
            }
    return {
        "running":       bool(sch and sch.running),
        "job":           job_info,
        "next_run_utc":  next_run,
        "runtime":       dict(_runtime),
        "schedule":      "Sunday 03:00 UTC",
        "version":       "bi5_cert_sweep_scheduler@R2-v1",
    }

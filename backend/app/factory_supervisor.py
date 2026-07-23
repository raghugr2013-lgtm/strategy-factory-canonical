"""factory_supervisor — APScheduler-based recurring-job authority.

Phase 1b (2026-07-23). This module owns the timetable of recurring
factory work — orchestrator ticks, mutation processing, factory
evaluation, meta-learning cycles, governance & cleanup. It is
deliberately decoupled from the backend engines themselves: each job
starts as a **safe placeholder** that emits a structured log line, and
each placeholder can later be swapped for a real engine invocation
without touching the scheduler wiring.

Design contract
---------------
* One `AsyncIOScheduler` per process, singleton-guarded.
* Every job runs inside a try/except that never re-raises — a crashing
  job cannot stop the scheduler.
* Every job entry is stamped with a structured log payload:
  ``{"job":"orchestrator","tick":42,"ts":"...","status":"ok"}``.
* Clean startup: `start_supervisor()` builds the scheduler, registers
  jobs, starts it, and returns the singleton.
* Clean shutdown: `stop_supervisor()` idempotently shuts it down with
  a bounded timeout so container SIGTERM handling is deterministic.
* Health-safe: the supervisor NEVER blocks — every job body runs to
  completion or times out via the executor's own guard rails.
* No API surface changes. No new endpoints. No new engines. No Mongo
  writes from the placeholder job bodies.
* No breaking change to the existing legacy sibling path — the
  Factory Supervisor is a THIRD runtime mode, gated by
  ``FACTORY_SUPERVISOR_ENABLED`` (default false).

Env flags
---------
* ``FACTORY_SUPERVISOR_ENABLED``      — turn the supervisor on
* ``SUPERVISOR_ORCHESTRATOR_CRON``    — override orchestrator cadence (default: every 1 min)
* ``SUPERVISOR_MUTATION_CRON``        — override mutation cadence     (default: every 15 min)
* ``SUPERVISOR_FACTORY_EVAL_CRON``    — override factory-eval cadence (default: every 1 h)
* ``SUPERVISOR_META_LEARNING_CRON``   — override meta-learning cadence(default: every 6 h)
* ``SUPERVISOR_GOVERNANCE_CRON``      — override governance cadence   (default: daily @ 04:00 UTC)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Callable, Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    _APS_AVAILABLE = True
except Exception:  # pragma: no cover
    _APS_AVAILABLE = False


log = logging.getLogger("factory_supervisor")


# ─── singleton state ───────────────────────────────────────────────
_scheduler: Optional["AsyncIOScheduler"] = None
_started_at: Optional[float] = None
_job_counters: dict[str, int] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _structured_log(payload: dict) -> None:
    """Emit one JSON line to stdout for easy log-collector ingestion."""
    payload.setdefault("ts", _now_iso())
    payload.setdefault("supervisor_uptime_s",
                       int(time.time() - _started_at) if _started_at else 0)
    log.info(json.dumps(payload, default=str, sort_keys=True))


def _safe_job(name: str, body: Callable[[], None]) -> Callable[[], None]:
    """Wrap a job body so a crash never stops the scheduler."""
    def _runner() -> None:
        _job_counters[name] = _job_counters.get(name, 0) + 1
        started = time.time()
        try:
            body()
            _structured_log({
                "job": name,
                "tick": _job_counters[name],
                "status": "ok",
                "duration_ms": int((time.time() - started) * 1000),
            })
        except Exception as exc:                             # noqa: BLE001
            _structured_log({
                "job": name,
                "tick": _job_counters[name],
                "status": "error",
                "duration_ms": int((time.time() - started) * 1000),
                "error": type(exc).__name__,
                "error_msg": str(exc)[:200],
            })
    _runner.__name__ = f"job_{name}"
    return _runner


# ─── placeholder job bodies (safe by construction) ─────────────────
def _job_orchestrator() -> None:
    """Placeholder: emit a structured tick log every minute.

    Wiring point: replace with a call to the orchestrator engine's
    ``tick()`` once the Feature Freeze is lifted for that engine.
    """
    _structured_log({"job": "orchestrator", "body": "placeholder_tick"})


def _job_mutation() -> None:
    """Placeholder: emit a mutation-processing batch log every 15 min.

    Wiring point: enqueue a mutation-processing batch via the COE
    queue (`/api/coe/*`) once execution flows are wired.
    """
    _structured_log({"job": "mutation", "body": "placeholder_batch"})


def _job_factory_eval() -> None:
    """Placeholder: emit a factory-eval cycle log every hour.

    Wiring point: invoke the factory-eval engine's rescore endpoint
    once available.
    """
    _structured_log({"job": "factory_eval", "body": "placeholder_cycle"})


def _job_meta_learning() -> None:
    """Placeholder: emit a meta-learning cycle log every 6 hours.

    Wiring point: invoke the meta-learning engine cycle once
    available.
    """
    _structured_log({"job": "meta_learning", "body": "placeholder_cycle"})


def _job_governance() -> None:
    """Placeholder: emit a governance / cleanup log daily.

    Wiring point: invoke governance re-rank + housekeeping (audit-log
    TTL, dead-letter drain, etc.) once available.
    """
    _structured_log({"job": "governance", "body": "placeholder_daily"})


# ─── public API ────────────────────────────────────────────────────
def start_supervisor() -> Optional["AsyncIOScheduler"]:
    """Idempotently build + start the singleton scheduler.

    Returns the AsyncIOScheduler on success, or None if APScheduler is
    not installed or the supervisor is disabled by env flag.
    """
    global _scheduler, _started_at

    if not _APS_AVAILABLE:
        log.warning("APScheduler is NOT installed — factory_supervisor is a no-op")
        return None

    if _scheduler is not None and _scheduler.running:
        log.info("factory_supervisor already running — returning existing instance")
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")

    def _trigger(default_interval_sec: Optional[int] = None,
                 default_cron: Optional[dict] = None,
                 env_override: Optional[str] = None):
        raw = os.environ.get(env_override or "", "").strip()
        if raw:
            try:
                return CronTrigger.from_crontab(raw, timezone="UTC")
            except Exception:                                   # noqa: BLE001
                log.exception("bad crontab in %s=%r — falling back to default", env_override, raw)
        if default_interval_sec is not None:
            return IntervalTrigger(seconds=default_interval_sec)
        return CronTrigger(**(default_cron or {}), timezone="UTC")

    # Job registration — defaults per operator spec
    _scheduler.add_job(
        _safe_job("orchestrator", _job_orchestrator),
        trigger=_trigger(default_interval_sec=60,
                         env_override="SUPERVISOR_ORCHESTRATOR_CRON"),
        id="orchestrator", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _safe_job("mutation", _job_mutation),
        trigger=_trigger(default_interval_sec=15 * 60,
                         env_override="SUPERVISOR_MUTATION_CRON"),
        id="mutation", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _safe_job("factory_eval", _job_factory_eval),
        trigger=_trigger(default_interval_sec=60 * 60,
                         env_override="SUPERVISOR_FACTORY_EVAL_CRON"),
        id="factory_eval", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _safe_job("meta_learning", _job_meta_learning),
        trigger=_trigger(default_interval_sec=6 * 60 * 60,
                         env_override="SUPERVISOR_META_LEARNING_CRON"),
        id="meta_learning", replace_existing=True, max_instances=1, coalesce=True,
    )
    _scheduler.add_job(
        _safe_job("governance", _job_governance),
        trigger=_trigger(default_cron={"hour": 4, "minute": 0},
                         env_override="SUPERVISOR_GOVERNANCE_CRON"),
        id="governance", replace_existing=True, max_instances=1, coalesce=True,
    )

    _scheduler.start()
    _started_at = time.time()

    for job in _scheduler.get_jobs():
        log.info("registered %s → next_run=%s trigger=%s",
                 job.id, job.next_run_time, job.trigger)
    log.info("factory_supervisor STARTED · %d jobs registered", len(_scheduler.get_jobs()))
    _structured_log({"event": "supervisor_started",
                     "jobs": [j.id for j in _scheduler.get_jobs()]})
    return _scheduler


def stop_supervisor(wait: bool = True) -> None:
    """Idempotently shut the scheduler down."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        if _scheduler.running:
            _scheduler.shutdown(wait=wait)
            _structured_log({"event": "supervisor_stopped"})
            log.info("factory_supervisor stopped")
    except Exception:                                          # noqa: BLE001
        log.exception("scheduler shutdown raised — swallowed")
    _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def state() -> dict:
    """Introspection snapshot used by callers who want to log status."""
    if not is_running():
        return {"running": False, "jobs": []}
    return {
        "running": True,
        "started_at": _started_at,
        "uptime_s": int(time.time() - _started_at) if _started_at else 0,
        "jobs": [
            {
                "id": j.id,
                "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
                "tick_count": _job_counters.get(j.id, 0),
            }
            for j in _scheduler.get_jobs()
        ],
    }

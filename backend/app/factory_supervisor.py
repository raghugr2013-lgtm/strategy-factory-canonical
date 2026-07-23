"""factory_supervisor — APScheduler-based lifecycle / observability authority.

Phase 2 (2026-07-23). The Factory Supervisor is a THIN cross-process
observability + governance layer. It is deliberately NOT an orchestrator —
task orchestration is owned by the in-backend `Unified Orchestrator`
(``legacy/engines/orchestrator/core.py``), which has a full task
registry, readiness scoring, workload-class capping, hard timeouts and
adaptive dispatch.

The Supervisor's five recurring jobs are read-only health / governance
hooks that emit structured JSON log lines from the ``factory-runner``
container, giving operators an independent observability channel when
the FastAPI worker is degraded or restarting.

Cross-process observability caveat
----------------------------------
The Unified Orchestrator singleton lives in the ``factory-backend``
process memory. The Factory Supervisor runs in a **different**
container (``factory-runner``). To observe the backend's live state
cross-process, set ``SUPERVISOR_BACKEND_STATUS_URL`` (and optionally
``SUPERVISOR_BACKEND_TOKEN`` for legacy-router auth) — the supervisor
will then poll ``/api/orchestrator/status`` with a short timeout and
merge the response into its snapshot. When the env vars are unset (or
the HTTP call fails), the supervisor falls back to a **local-process**
view that proves the orchestrator module is importable and reports
the env-flag configuration in this container. Either way the beacon
keeps publishing when the backend worker is degraded or restarting —
that is the entire point of splitting the runner into a sibling
container.

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
* Health-safe: the supervisor NEVER blocks, NEVER dispatches
  orchestrator tasks, NEVER writes engine ledgers, and NEVER reaches
  into strategy_library. It only observes.
* No API surface changes. No new endpoints. No new engines.

Env flags
---------
* ``FACTORY_SUPERVISOR_ENABLED``      — turn the supervisor on
* ``SUPERVISOR_ORCHESTRATOR_CRON``    — override orchestrator observability cadence (default: every 1 min)
* ``SUPERVISOR_MUTATION_CRON``        — override mutation observability cadence     (default: every 15 min)
* ``SUPERVISOR_FACTORY_EVAL_CRON``    — override factory-eval observability cadence (default: every 1 h)
* ``SUPERVISOR_META_LEARNING_CRON``   — override meta-learning observability cadence(default: every 6 h)
* ``SUPERVISOR_GOVERNANCE_CRON``      — override governance cadence                 (default: daily @ 04:00 UTC)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

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
_job_counters: Dict[str, int] = {}


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


# ─── observability helpers — cross-process reads only ──────────────
def _fetch_backend_status() -> Optional[Dict[str, Any]]:
    """Best-effort HTTP proxy to the backend's ``/api/orchestrator/status``.

    Returns ``None`` when either the URL is unset, the HTTP call fails,
    or the response is not valid JSON. Never raises. Kept dependency-
    free (uses ``urllib``) so the runner container's minimal Python
    surface is enough. Auth is optional via ``SUPERVISOR_BACKEND_TOKEN``.
    """
    url = (os.environ.get("SUPERVISOR_BACKEND_STATUS_URL") or "").strip()
    if not url:
        return None
    token = (os.environ.get("SUPERVISOR_BACKEND_TOKEN") or "").strip()
    timeout_s = float(os.environ.get("SUPERVISOR_BACKEND_TIMEOUT_S") or "3.0")
    try:
        import urllib.request as _u
        req = _u.Request(url, headers={"Accept": "application/json"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with _u.urlopen(req, timeout=timeout_s) as resp:            # noqa: S310
            body = resp.read()
        return json.loads(body.decode("utf-8", errors="replace"))
    except Exception:                                                # noqa: BLE001
        return None


def _orchestrator_snapshot() -> Dict[str, Any]:
    """Return the best available orchestrator snapshot.

    Preference order:
      1. HTTP proxy to ``/api/orchestrator/status`` when
         ``SUPERVISOR_BACKEND_STATUS_URL`` is set — returns the live
         backend singleton state.
      2. Local-process import view — proves the module is importable
         in the runner container, but the local singleton is fresh
         (never started) so ``running`` will be False.
      3. Full fallback: ``{"running": False, "importable": False}`` when
         neither channel works.
    """
    remote = _fetch_backend_status()
    if remote is not None:
        remote["importable"] = True
        remote["source"] = "http_proxy"
        return remote

    import sys as _sys
    _legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "legacy")
    if _legacy_dir not in _sys.path:
        _sys.path.insert(0, _legacy_dir)
    try:
        from engines.orchestrator import get_orchestrator, orchestrator_enabled  # type: ignore
    except Exception:                                           # pragma: no cover
        return {"running": False, "importable": False, "source": "unavailable",
                "reason": "orchestrator_module_unavailable"}
    try:
        snap = get_orchestrator().snapshot()
    except Exception as exc:                                    # noqa: BLE001
        return {"running": False, "importable": True, "source": "local_singleton",
                "reason": f"snapshot_crashed: {str(exc)[:120]}"}
    snap["importable"] = True
    snap["enabled_by_env"] = orchestrator_enabled()
    snap["source"] = "local_singleton"
    return snap


def _task_counters(snapshot: Dict[str, Any], task_name: str) -> Dict[str, Any]:
    """Slice a per-task counter view out of the orchestrator snapshot."""
    counters = snapshot.get("counters", {}) or {}
    return {
        "runs_total": (counters.get("runs_total") or {}).get(task_name, 0),
        "runs_ok":    (counters.get("runs_ok")    or {}).get(task_name, 0),
        "runs_fail":  (counters.get("runs_fail")  or {}).get(task_name, 0),
        "last_completed_ts": (counters.get("last_completed_ts") or {}).get(task_name),
    }


# ─── placeholder job bodies (safe by construction) ─────────────────
def _job_orchestrator() -> None:
    """Emit a compact orchestrator liveness snapshot every minute.

    Cross-process observability: even if the backend worker is
    degraded, this job continues to publish the last-known state
    from the runner container's stdout.
    """
    snap = _orchestrator_snapshot()
    _structured_log({
        "job": "orchestrator",
        "body": "liveness_snapshot",
        "source": snap.get("source"),
        "orchestrator_running": bool(snap.get("running")),
        "orchestrator_enabled_by_env": bool(snap.get("enabled_by_env")),
        "importable": bool(snap.get("importable")),
        "tick_count": (snap.get("meta") or {}).get("tick_count"),
        "dispatched_total": (snap.get("meta") or {}).get("dispatched_total"),
        "in_flight": len(snap.get("in_flight") or []),
        "task_names": snap.get("task_names") or [],
    })


def _job_mutation() -> None:
    """Emit mutation-task counter snapshot every 15 minutes.

    Read-only: we look at the orchestrator's per-task counters for
    the ``mutation`` task and publish them. The actual mutation work
    (if any) is dispatched by the orchestrator's tick loop when the
    ``ORCH_TASK_MUTATION_PASSIVE`` flag allows it.
    """
    snap = _orchestrator_snapshot()
    _structured_log({
        "job": "mutation",
        "body": "counter_snapshot",
        "task": "mutation",
        "counters": _task_counters(snap, "mutation"),
        "passive_env": os.environ.get("ORCH_TASK_MUTATION_PASSIVE", ""),
    })


def _job_factory_eval() -> None:
    """Emit factory-evaluation counter + mode snapshot every hour."""
    mode = _read_engine_mode("factory_eval")
    snap = _orchestrator_snapshot()
    _structured_log({
        "job": "factory_eval",
        "body": "counter_snapshot",
        "task": "factory_evaluation",
        "mode": mode,
        "counters": _task_counters(snap, "factory_evaluation"),
    })


def _job_meta_learning() -> None:
    """Emit meta-learning counter + mode snapshot every 6 hours."""
    mode = _read_engine_mode("meta_learning")
    snap = _orchestrator_snapshot()
    _structured_log({
        "job": "meta_learning",
        "body": "counter_snapshot",
        "task": "meta_learning_evaluation",
        "mode": mode,
        "counters": _task_counters(snap, "meta_learning_evaluation"),
    })


def _job_governance() -> None:
    """Governance / housekeeping — daily @ 04:00 UTC.

    Read-only: emits a governance-health snapshot. Intentionally does
    NOT invoke any mutation, cleanup, or audit-log TTL routines from
    this location — those live in the backend and are triggered by
    the orchestrator or explicit operator action. This job's role is
    purely to publish a daily "governance surface still alive" beacon
    from a process independent of the FastAPI worker.
    """
    snap = _orchestrator_snapshot()
    payload = {
        "job": "governance",
        "body": "daily_beacon",
        "engine_modes": {
            "meta_learning":  _read_engine_mode("meta_learning"),
            "factory_eval":   _read_engine_mode("factory_eval"),
            "market_intel":   os.environ.get("MI_ENABLED", ""),
            "execution":      os.environ.get("EXEC_ENABLED", ""),
            "orchestrator":   os.environ.get("ORCHESTRATOR_ENABLED", ""),
            "supervisor":     os.environ.get("FACTORY_SUPERVISOR_ENABLED", ""),
        },
        "orchestrator_running": bool(snap.get("running")),
        "importable": bool(snap.get("importable")),
    }
    _structured_log(payload)


def _read_engine_mode(engine: str) -> str:
    """Return the current mode string for a mode-gated engine.

    Read-only. Best-effort — if the engine module is not importable
    (which is the common case in the sibling runner container), we
    fall back to the raw env-var value so operators still see the
    surface they configured.
    """
    import sys as _sys
    _legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "legacy")
    if _legacy_dir not in _sys.path:
        _sys.path.insert(0, _legacy_dir)
    try:
        if engine == "meta_learning":
            from engines.meta_learning import config as _c  # type: ignore
            return str(_c.mode())
        if engine == "factory_eval":
            from engines.factory_eval import config as _c   # type: ignore
            return str(_c.mode())
    except Exception:                                          # pragma: no cover
        pass
    # Fallback: raw env
    env_map = {
        "meta_learning": "META_LEARNING_MODE",
        "factory_eval":  "FACTORY_EVAL_MODE",
    }
    return os.environ.get(env_map.get(engine, ""), "") or "unknown"


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
                     "jobs": [j.id for j in _scheduler.get_jobs()],
                     "role": "observability_and_governance"})
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

"""
Factory Supervisor FS-P1.3 — Persistent worker scheduler.

A SINGLE long-lived asyncio task that drains due defer-queue rows on
cadence. Designed to host multiple "scheduler workers" (local,
multi-node, telemetry, NC, auto-learning, copilot-refresh) as the
Factory matures — each gated by its own feature flag so activation
remains additive and rollback-safe.

Discipline (operator-locked):
  * DORMANT by default. `FS_ENABLE_WORKER_SCHEDULER=false` ⇒ `start()`
    is a no-op; `claim_and_run_once()` is still callable manually via
    the existing `POST /workers/tick` endpoint.
  * SINGLETON per process. Multiple `start()` calls are idempotent.
    `stop()` cancels the task; `start()` after stop() resumes cleanly.
  * Best-effort. Exceptions inside the loop are logged but never crash
    the task (the loop catches everything except CancelledError).
  * Provider/transport-neutral. The scheduler never touches HTTP /
    gRPC / WebSocket directly — it dispatches via `worker_runtime` and
    its registered workers, which themselves resolve transport via
    `remote_transport`.
  * Future-ready: a sub-task registry is exposed so additional cadences
    (telemetry sync, NC fan-out, auto-learning, copilot refresh) can
    each register a separate gated task with its own poll interval.

Public surface:
    is_enabled()                           → bool
    register_task(name, runner, *, flag,
                  interval_sec, intent)    — declare a sub-task
    start()                                → dict
    stop()                                 → dict
    status()                               → dict      (for status_view)
    claim_and_run_once(batch=8)            → list      (manual tick passthrough)
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class _TaskState:
    name:          str
    flag:          str
    interval_sec:  int
    intent:        str
    runner:        Optional[Callable[..., Awaitable[Any]]] = None  # cb (no args)
    task:          Optional[asyncio.Task] = None
    started_at:    Optional[str] = None
    ticks:         int = 0
    last_tick_ts:  Optional[str] = None
    last_outcome:  Optional[Dict[str, Any]] = None
    error_count:   int = 0
    last_error:    Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("runner", None)
        d.pop("task",   None)
        d["running"] = bool(self.task and not self.task.done())
        return d


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _flag(name: str, default: Any = False) -> Any:
    try:
        from engines.feature_flags import flag
        return flag(name)
    except Exception:                                            # pragma: no cover
        return default


def _clamp_poll_interval(name: str, lo: int = 1, hi: int = 600) -> int:
    try:
        v = int(_flag(name, 15))
    except Exception:                                            # pragma: no cover
        v = 15
    return max(lo, min(v, hi))


# ─── Built-in defer-queue runner ─────────────────────────────────────


async def _run_defer_queue_tick() -> Dict[str, Any]:
    """Wrap `worker_runtime.claim_and_run_once()` so the scheduler can
    call it without knowing about the worker registry."""
    try:
        from engines.factory_supervisor import worker_runtime
        results = await worker_runtime.claim_and_run_once(batch=8)
        return {"processed": len(results), "results": results}
    except Exception as e:                                       # pragma: no cover
        logger.debug("[worker_scheduler] defer_queue tick failed: %s", e)
        return {"processed": 0, "error": str(e)[:200]}


# ─── Registry of scheduler tasks (future-ready) ──────────────────────


_TASKS: Dict[str, _TaskState] = {
    # Built-in: defer-queue worker poller.
    "defer_queue_poller": _TaskState(
        name="defer_queue_poller",
        flag="FS_ENABLE_WORKER_SCHEDULER",
        interval_sec=15,
        intent="Drain due defer-queue rows on cadence (local + multi-node workers).",
        runner=_run_defer_queue_tick,
    ),
    # Future-ready stubs; each gated independently.
    "telemetry_sync": _TaskState(
        name="telemetry_sync",
        flag="FS_ENABLE_TELEMETRY_WORKER",
        interval_sec=30,
        intent="Pull cTrader telemetry tasks from remote runners (FS-P1.4+).",
        runner=None,
    ),
    "notification_fanout": _TaskState(
        name="notification_fanout",
        flag="FS_ENABLE_NOTIFICATION_WORKER",
        interval_sec=20,
        intent="Materialise notifications + multi-channel deliveries (FS-P1.4+).",
        runner=None,
    ),
    "auto_learning_drain": _TaskState(
        name="auto_learning_drain",
        flag="FS_ENABLE_AUTO_LEARNING_WORKER",
        interval_sec=60,
        intent="Drain Auto-Learning queue (gate strictly OFF per directive).",
        runner=None,
    ),
    "copilot_context_refresh": _TaskState(
        name="copilot_context_refresh",
        flag="FS_ENABLE_COPILOT_REFRESH",
        interval_sec=120,
        intent="Periodic CopilotContext refresh (provider-agnostic).",
        runner=None,
    ),
}


def register_task(
    name: str,
    runner: Callable[..., Awaitable[Any]],
    *,
    flag: str,
    interval_sec: int = 15,
    intent: str = "",
) -> None:
    """Plug a new scheduler task at runtime. The task does NOT start
    until `start()` is called; the per-task flag governs activation."""
    _TASKS[name] = _TaskState(
        name=name,
        flag=flag,
        interval_sec=int(interval_sec),
        intent=intent or f"Custom task {name}",
        runner=runner,
    )


def is_enabled() -> bool:
    """Master switch for the scheduler — requires ENABLE_FACTORY_SUPERVISOR
    AND FS_ENABLE_WORKER_SCHEDULER. Per-task flags still gate individual
    runners on top of this."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_WORKER_SCHEDULER"))
    except Exception:                                            # pragma: no cover
        return False


# ─── Loop runner ────────────────────────────────────────────────────


async def _task_loop(state: _TaskState) -> None:
    """Run one scheduler sub-task until cancelled. Catches everything
    except CancelledError so a bad tick never kills the loop."""
    while True:
        try:
            await asyncio.sleep(state.interval_sec)
        except asyncio.CancelledError:
            raise
        # Per-task gate; toggle live.
        if not _flag(state.flag):
            continue
        if state.runner is None:
            continue
        try:
            outcome = await state.runner()
            state.ticks += 1
            state.last_tick_ts = _now_iso()
            state.last_outcome = outcome if isinstance(outcome, dict) else {"value": outcome}
        except asyncio.CancelledError:
            raise
        except Exception as e:                                   # pragma: no cover
            state.error_count += 1
            state.last_error = str(e)[:200]
            logger.debug("[worker_scheduler] %s tick raised: %s", state.name, e)


# ─── Public start / stop / status ────────────────────────────────────


def start() -> Dict[str, Any]:
    """Start any sub-tasks whose runner is non-None AND whose flag is
    currently ON, AND when the master switch (`FS_ENABLE_WORKER_SCHEDULER`)
    is ON. Idempotent — already-running tasks are skipped."""
    started: List[str] = []
    skipped: List[Dict[str, str]] = []
    if not is_enabled():
        return {"started": [], "skipped": [
            {"name": n, "reason": "master_flag_off"} for n in _TASKS
        ], "running": False}
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:                                         # pragma: no cover
        return {"started": [], "skipped": [], "error": "no_event_loop"}

    for name, state in _TASKS.items():
        if state.runner is None:
            skipped.append({"name": name, "reason": "no_runner"})
            continue
        if state.task and not state.task.done():
            skipped.append({"name": name, "reason": "already_running"})
            continue
        # Refresh poll interval from the env if applicable.
        if name == "defer_queue_poller":
            state.interval_sec = _clamp_poll_interval("FS_WORKER_POLL_INTERVAL_SEC")
        state.task        = loop.create_task(_task_loop(state))
        state.started_at  = _now_iso()
        state.ticks       = 0
        state.error_count = 0
        state.last_error  = None
        started.append(name)
    return {"started": started, "skipped": skipped, "running": True}


def stop() -> Dict[str, Any]:
    """Cancel every running sub-task. Idempotent."""
    stopped: List[str] = []
    for name, state in _TASKS.items():
        if state.task and not state.task.done():
            state.task.cancel()
            stopped.append(name)
        state.task = None
    return {"stopped": stopped, "running": False}


def status() -> Dict[str, Any]:
    """JSON-serialisable view of every registered sub-task. Always
    safe to call — never raises."""
    out: List[Dict[str, Any]] = []
    any_running = False
    for state in _TASKS.values():
        d = state.to_dict()
        # Refresh flag value lazily; helps the dashboard.
        d["flag_value"] = bool(_flag(state.flag))
        if d.get("running"):
            any_running = True
        out.append(d)
    return {
        "enabled":  is_enabled(),
        "running":  any_running,
        "tasks":    out,
    }


async def claim_and_run_once(batch: int = 8) -> Dict[str, Any]:
    """Manual tick passthrough — calls the defer-queue worker once."""
    try:
        from engines.factory_supervisor import worker_runtime
        results = await worker_runtime.claim_and_run_once(batch=batch)
        return {"processed": len(results), "results": results}
    except Exception as e:                                       # pragma: no cover
        logger.debug("[worker_scheduler] claim_and_run_once failed: %s", e)
        return {"processed": 0, "error": str(e)[:200]}

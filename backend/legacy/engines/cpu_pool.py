"""
Phase D.2 — CPU process pool (ADDITIVE, feature-gated).

A singleton ProcessPoolExecutor that mutation/backtest hot paths can
opt into via the `USE_PROCESS_POOL` env flag. Defaults to OFF so the
existing `asyncio.to_thread` path is preserved byte-for-byte.

Discipline:
  * Feature-gated: `USE_PROCESS_POOL=true` activates the pool.
  * Reversible: flip the env back to false and the pool sleeps.
    Workers are spawned lazily on first submission.
  * Observable: `get_pool_state()` snapshots active workers.
  * Safe: when the pool is disabled, `submit_cpu(...)` transparently
    falls through to `asyncio.to_thread` so callers can use one API.

The pool is sized via `CPU_POOL_SIZE` (default 4 on machines with
12 vCPU, leaving 8 cores for the API workers, scheduler, MongoDB,
and OS overhead).

Caveats (callers MUST be aware):
  * Functions submitted MUST be importable at module level (no
    closures, no lambdas). Subprocesses re-import the module.
  * Arguments + return values MUST be picklable (no Mongo cursors,
    no DB handles, no FastAPI Request objects).
  * Mongo handles cannot cross the boundary — pass plain dicts in,
    plain dicts out.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    raw = (os.environ.get("USE_PROCESS_POOL") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def pool_size() -> int:
    """Resolve the cpu_pool worker count.

    Priority (per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §1.2):
      1. `CPU_POOL_SIZE` env var if set — operator pin wins absolutely.
      2. `ENABLE_ADAPTIVE_POOL_SIZING=true` AND host capability detected
         → consult `adaptive_pool_sizer.recommend_pool_size()`.
      3. Otherwise legacy default = 4.

    All paths are clamped to `[1, 32]`. Behaviour with the new flag OFF
    AND no env override is byte-identical to the pre-P1.B world.
    """
    raw = os.environ.get("CPU_POOL_SIZE")
    if raw is not None and str(raw).strip() != "":
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = 4
        return max(1, min(n, 32))

    # No explicit env pin — try adaptive sizer when the flag is ON.
    try:
        from engines.feature_flags import flag
        if bool(flag("ENABLE_ADAPTIVE_POOL_SIZING")):
            from engines.adaptive_pool_sizer import recommend_pool_size
            from engines.host_capability import current as _current_caps
            caps = _current_caps()
            if caps is not None:
                n = recommend_pool_size(caps)
                return max(1, min(int(n), 32))
    except Exception:                                        # pragma: no cover
        # Defensive: any failure in adaptive path falls through to legacy.
        pass

    return 4  # legacy default — preserved verbatim from pre-P1.B world


_executor: Optional[ProcessPoolExecutor] = None
_executor_lock = asyncio.Lock()

# ── Stage 1 (Phase 2, 2026-02-19) — crash budget + auto-recycle ────
# Feature-gated via `COE_CRASH_BUDGET_ENABLED`. When enabled, if the
# pool sees `POOL_CRASH_THRESHOLD` `BrokenProcessPool` exceptions
# within `POOL_CRASH_WINDOW_S` seconds, it shuts down the pool. The
# next `submit_cpu` re-creates a fresh pool. Never raises.
_crash_events: list = []                     # list[float] — event timestamps
_crash_count_total: int = 0                  # since boot


def _crash_budget_enabled() -> bool:
    raw = (os.environ.get("COE_CRASH_BUDGET_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def _crash_threshold() -> int:
    try:
        return max(1, int(os.environ.get("POOL_CRASH_THRESHOLD") or "5"))
    except (TypeError, ValueError):
        return 5


def _crash_window_s() -> float:
    try:
        v = float(os.environ.get("POOL_CRASH_WINDOW_S") or "60.0")
        return max(1.0, v)
    except (TypeError, ValueError):
        return 60.0


def _record_crash() -> int:
    """Append a crash event; prune out-of-window; return current in-window count."""
    global _crash_count_total
    import time as _time
    now = _time.time()
    _crash_events.append(now)
    _crash_count_total += 1
    cutoff = now - _crash_window_s()
    while _crash_events and _crash_events[0] < cutoff:
        _crash_events.pop(0)
    return len(_crash_events)


def _should_recycle() -> bool:
    return _crash_budget_enabled() and len(_crash_events) >= _crash_threshold()


async def _ensure_pool() -> ProcessPoolExecutor:
    global _executor
    if _executor is not None:
        return _executor
    async with _executor_lock:
        if _executor is None:
            size = pool_size()
            _executor = ProcessPoolExecutor(max_workers=size)
            logger.info("[cpu_pool] initialized ProcessPoolExecutor(max_workers=%d)", size)
        return _executor


async def submit_cpu(fn: Callable, /, *args, workload_class: Any = None, **kwargs) -> Any:
    """Submit a CPU-bound function.

    Routing:
      * `USE_PROCESS_POOL=true` → ProcessPoolExecutor (parallel across cores)
      * `USE_PROCESS_POOL=false` (default) → asyncio.to_thread (GIL-bound)

    The two paths are observationally equivalent for pure-Python work;
    the process pool path unlocks true multi-core for numpy-heavy
    inner loops (backtest_engine).

    VPS Scaling P1.D — wrapped in `admission_gate(workload_class)`. With
    `ENABLE_ADMISSION_CONTROL=false` (default) the gate is a no-op and
    behaviour is byte-identical to pre-P1.D. With the flag ON, the gate
    counts each submission against the per-class cap.

    Args
    ----
    workload_class : optional `WorkloadClass` enum value. Defaults to
                     `WorkloadClass.BACKTEST` when None — virtually all
                     existing callers (mutation_engine, backtest_pool)
                     submit backtest work.
    """
    # Defer the import — the workload_classes enum + admission_wrapper
    # both import this module's siblings, so a top-level import would
    # create a cycle.
    from engines.workload_classes import WorkloadClass
    from engines.admission_wrapper import admission_gate

    if workload_class is None:
        workload_class = WorkloadClass.BACKTEST

    async with admission_gate(
        workload_class,
        metadata={"site": "cpu_pool.submit_cpu",
                  "fn": getattr(fn, "__qualname__", str(fn))},
    ):
        return await _submit_cpu_inner(fn, *args, **kwargs)


async def _submit_cpu_inner(fn: Callable, /, *args, **kwargs) -> Any:
    """Inner submission body — pre-P1.D verbatim, plus Stage 1 crash budget."""
    if not is_enabled():
        return await asyncio.to_thread(fn, *args, **kwargs)
    pool = await _ensure_pool()
    loop = asyncio.get_running_loop()
    # ProcessPoolExecutor doesn't accept kwargs in run_in_executor.
    # Wrap via functools.partial if any kwargs are supplied.
    try:
        if kwargs:
            from functools import partial
            return await loop.run_in_executor(pool, partial(fn, *args, **kwargs))
        return await loop.run_in_executor(pool, fn, *args)
    except Exception as e:                                       # noqa: BLE001
        # Detect BrokenProcessPool without importing directly (it lives
        # in concurrent.futures.process which is private). Match on class
        # name to stay stdlib-version-safe.
        etype_name = type(e).__name__
        if etype_name in ("BrokenProcessPool", "BrokenExecutor"):
            in_window = _record_crash()
            logger.warning(
                "[cpu_pool] BrokenProcessPool detected (in_window=%d, total=%d)",
                in_window, _crash_count_total,
            )
            if _should_recycle():
                logger.error(
                    "[cpu_pool] crash budget exceeded (%d in %.0fs) — recycling pool",
                    in_window, _crash_window_s(),
                )
                try:
                    await shutdown_pool()
                except Exception:                                # pragma: no cover
                    pass
                # Best-effort: clear the in-window events so the fresh
                # pool starts with a clean budget.
                _crash_events.clear()
        raise


def get_pool_state() -> Dict[str, Any]:
    """Read-only diagnostic snapshot."""
    return {
        "enabled": is_enabled(),
        "pool_size_configured": pool_size(),
        "pool_initialized": _executor is not None,
        "worker_count": (_executor._max_workers if _executor is not None else 0),  # noqa: SLF001
        # Stage 1 additions
        "crash_budget_enabled": _crash_budget_enabled(),
        "crash_threshold": _crash_threshold(),
        "crash_window_s": _crash_window_s(),
        "crash_count_in_window": len(_crash_events),
        "crash_count": _crash_count_total,
    }


async def shutdown_pool() -> None:
    """Best-effort shutdown for clean restarts / tests. Never raises."""
    global _executor
    if _executor is None:
        return
    try:
        _executor.shutdown(wait=False, cancel_futures=True)
    except Exception as e:                                  # pragma: no cover
        logger.warning("[cpu_pool] shutdown failed: %s", e)
    _executor = None

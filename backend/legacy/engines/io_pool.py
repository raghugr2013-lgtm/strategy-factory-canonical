"""Phase 2, Stage 2 — dedicated I/O ThreadPoolExecutor.

Mirrors `cpu_pool.py` but bounded to I/O-bound work: MARKET_DATA
ingestion, KNOWLEDGE fetches, MONITORING pollers. Isolates I/O from
the ProcessPoolExecutor so a burst of BI5 downloads cannot starve
BACKTEST / MUTATION.

Feature-gated by `USE_IO_POOL=true`. When off: callers fall through
to `asyncio.to_thread` (default asyncio thread pool), preserving
pre-Stage-2 behaviour byte-identically.

Distribution-ready: the pool is a local resource. In γ+, MARKET_DATA
work will be dispatched to remote worker nodes via the distributed
queue driver — this local pool becomes one worker in a cluster.
"""
from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = asyncio.Lock()

_submit_count_total: int = 0
_submit_count_by_class: Dict[str, int] = {}


def is_enabled() -> bool:
    raw = (os.environ.get("USE_IO_POOL") or "").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def pool_size() -> int:
    """Default sizing: min(32, 4 × cpu_count)."""
    raw = os.environ.get("IO_POOL_SIZE")
    if raw:
        try:
            v = int(raw)
            if v > 0:
                return v
        except ValueError:
            pass
    try:
        cpu = os.cpu_count() or 4
    except Exception:                                    # pragma: no cover
        cpu = 4
    return min(32, cpu * 4)


async def _ensure_pool() -> ThreadPoolExecutor:
    global _executor
    if _executor is not None:
        return _executor
    async with _executor_lock:
        if _executor is None:
            n = pool_size()
            _executor = ThreadPoolExecutor(max_workers=n, thread_name_prefix="io-pool")
            logger.info("[io_pool] created ThreadPoolExecutor size=%d", n)
    return _executor


async def submit_io(fn: Callable, /, *args, workload_class: str = "io", **kwargs) -> Any:
    """Run a blocking I/O call on the dedicated pool.

    When `USE_IO_POOL=false`, falls through to `asyncio.to_thread` — no
    isolation, byte-identical to pre-Stage-2 behaviour.
    """
    global _submit_count_total
    _submit_count_total += 1
    _submit_count_by_class[workload_class] = _submit_count_by_class.get(workload_class, 0) + 1

    if not is_enabled():
        return await asyncio.to_thread(fn, *args, **kwargs)
    pool = await _ensure_pool()
    loop = asyncio.get_running_loop()
    if kwargs:
        from functools import partial
        return await loop.run_in_executor(pool, partial(fn, *args, **kwargs))
    return await loop.run_in_executor(pool, fn, *args)


async def shutdown_pool() -> None:
    global _executor
    async with _executor_lock:
        if _executor is not None:
            try:
                _executor.shutdown(wait=False, cancel_futures=True)
            except Exception:                            # pragma: no cover
                pass
            _executor = None


def get_pool_state() -> Dict[str, Any]:
    """Diagnostic snapshot."""
    return {
        "enabled": is_enabled(),
        "pool_size_configured": pool_size(),
        "pool_initialized": _executor is not None,
        "worker_count": (_executor._max_workers if _executor is not None else 0),  # noqa: SLF001
        "submit_count_total": _submit_count_total,
        "submit_count_by_class": dict(_submit_count_by_class),
    }


def _reset_for_tests() -> None:
    """Test-only — force fresh pool + counters on next `submit_io`."""
    global _executor, _submit_count_total, _submit_count_by_class
    if _executor is not None:
        try:
            _executor.shutdown(wait=False, cancel_futures=True)
        except Exception:                                # pragma: no cover
            pass
    _executor = None
    _submit_count_total = 0
    _submit_count_by_class = {}

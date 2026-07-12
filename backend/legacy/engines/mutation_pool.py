"""
Phase 1+2 scaffolding — Mutation process-pool adoption wrapper (DORMANT).

A narrow helper for routing CPU-heavy mutation work through the process
pool when both gates are active:

  USE_PROCESS_POOL=true  AND  ENABLE_PROCESS_POOL_MUTATION=true
      → ProcessPoolExecutor
  otherwise (default)
      → asyncio.to_thread

Adoption is OPT-IN at the call-site. Current mutation hot paths in
`engines.mutation_engine` and `engines.auto_mutation_runner` are
untouched; future migration imports `submit_mutation_cpu(...)` to gain
pool routing without changing semantics.

Discipline matches `engines.backtest_pool`:
  * Functions submitted MUST be top-level (picklable).
  * Arguments + returns MUST be picklable.
  * No DB handles, no Mongo cursors, no closures.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Dict

from engines import cpu_pool

logger = logging.getLogger(__name__)


def _mutation_pool_enabled() -> bool:
    if not cpu_pool.is_enabled():
        return False
    raw = (os.environ.get("ENABLE_PROCESS_POOL_MUTATION") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def submit_mutation_cpu(fn: Callable, /, *args, **kwargs) -> Any:
    """Route a CPU-bound mutation function via the process pool when
    both gates are active; otherwise fall through to `asyncio.to_thread`.

    The function MUST be top-level (importable by module path) and its
    arguments + return value MUST be picklable.
    """
    if _mutation_pool_enabled():
        return await cpu_pool.submit_cpu(fn, *args, **kwargs)
    if kwargs:
        from functools import partial
        return await asyncio.to_thread(partial(fn, *args, **kwargs))
    return await asyncio.to_thread(fn, *args)


def adoption_state() -> Dict[str, Any]:
    """Read-only diagnostic surface."""
    return {
        "use_process_pool":             cpu_pool.is_enabled(),
        "enable_process_pool_mutation": _mutation_pool_enabled() or False,
        "pooled_path_active":           _mutation_pool_enabled(),
        "pool_state":                   cpu_pool.get_pool_state(),
    }

"""Shared helpers for task adapters — freshness/staleness math + graceful
engine import guards. No business logic here.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

from ..core import get_orchestrator
from ..types import Readiness


def _last_completed(task_name: str) -> Optional[float]:
    return get_orchestrator()._last_completed_ts.get(task_name)  # noqa: SLF001


def freshness_pressure(task_name: str, min_interval_s: int) -> float:
    """0..N staleness multiplier. Returns 1.0 for fresh, grows linearly
    beyond MIN_INTERVAL_S. Never negative. Event-driven tasks
    (min_interval_s == 0) always return 1.0 — freshness is handled by
    dependency readiness instead."""
    if min_interval_s <= 0:
        return 1.0
    last = _last_completed(task_name)
    if last is None:
        return 2.0                        # never run → high pressure
    age = time.time() - last
    if age < min_interval_s:
        return max(0.05, age / max(1, min_interval_s))
    # Overdue: grow linearly, cap at 4.
    return min(4.0, 1.0 + (age - min_interval_s) / max(1, min_interval_s))


def dependencies_ready(dep_names: tuple, min_recent: int = 1,
                       within_s: Optional[int] = None) -> tuple:
    """Return (readiness_score, stale_deps_tuple).

    A dependency is considered satisfied if it has completed at least
    `min_recent` times, OR within `within_s` seconds when supplied.
    Missing dependencies contribute 0.

    Result is `sum(satisfied) / max(1, len(deps))`.
    """
    if not dep_names:
        return (1.0, ())
    orc = get_orchestrator()
    now = time.time()
    ok = 0
    stale = []
    for d in dep_names:
        last = orc._last_completed_ts.get(d)  # noqa: SLF001
        runs = orc._runs_ok.get(d, 0)          # noqa: SLF001
        if within_s is not None:
            if last is not None and (now - last) <= within_s:
                ok += 1
            else:
                stale.append(d)
        else:
            if runs >= min_recent:
                ok += 1
            else:
                stale.append(d)
    return (ok / len(dep_names), tuple(stale))


def eligible_from_env(env_key: str, default_eligible: bool = True) -> tuple:
    """Env-driven eligibility hook. When `ORCH_TASK_<NAME>_DISABLED=true`,
    return (False, "disabled_via_env"). Otherwise (default_eligible, "")."""
    import os
    raw = (os.environ.get(env_key) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return (False, "disabled_via_env")
    return (default_eligible, "")

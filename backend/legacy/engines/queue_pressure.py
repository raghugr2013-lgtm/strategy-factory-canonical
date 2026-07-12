"""
VPS Scaling P1.C — Queue pressure counters + rolling-window snapshot.

Tracks per-WorkloadClass in-flight depth, exposes a rolling-window
summary, and reports cpu_pool worker utilisation. Pure in-memory
state — no DB writes, no env mutation. Counters are incremented at
the top of every wrap site (`with_admission` in P1.D) and decremented
in the `finally:` block, making the counter robust to exceptions.

Discipline (per CAPACITY_ENGINE_DESIGN.md §4):
  * Pure in-memory; thread-safe via `threading.Lock`.
  * No I/O; never raises.
  * `incr` / `decr` are O(1).
  * `snapshot()` is O(n_classes × window_samples). Window samples are
    capped at `QUEUE_PRESSURE_WINDOW_SEC * 2 / sample_period` so memory
    is bounded irrespective of uptime.
  * In P1.C nothing CALLS `incr`/`decr` — the counters stay at 0. The
    `snapshot()` API is still callable so the admission controller and
    diagnostic API can consult it. P1.D wires the wrap sites.

Public API:
    incr(cls)             — atomic per-class increment
    decr(cls)             — atomic per-class decrement (floors at 0)
    current_depth(cls)    — instantaneous read
    sample()              — append a (ts, depth_per_class) row to the window
    snapshot()            — structured rolling-window summary + utilization
    worker_utilization()  — active_workers / pool_size
    reset()               — test-only: clear all state
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple

from engines.workload_classes import WorkloadClass

# ─── Internal state ──────────────────────────────────────────────────

_lock = threading.Lock()

# Instantaneous depth per class. Floored at 0 even on bad caller flow.
_depth: Dict[WorkloadClass, int] = {c: 0 for c in WorkloadClass}

# Rolling window of (ts, depth_snapshot_per_class) tuples. Cap at
# WINDOW_MAX_SAMPLES so the deque cannot grow unbounded if `sample()`
# is called from a misbehaving caller.
_WINDOW_MAX_SAMPLES = 1024
_window: Deque[Tuple[float, Dict[WorkloadClass, int]]] = deque(maxlen=_WINDOW_MAX_SAMPLES)

# Default window seconds. Operator may override via env (consulted on
# every snapshot — no caching, so live-reload works).
_DEFAULT_WINDOW_SEC = 30.0


def _window_sec() -> float:
    """Return current rolling-window length in seconds. Min 1, Max 600."""
    raw = os.environ.get("QUEUE_PRESSURE_WINDOW_SEC")
    if raw is None or str(raw).strip() == "":
        return _DEFAULT_WINDOW_SEC
    try:
        v = float(raw)
        if v <= 0:
            return _DEFAULT_WINDOW_SEC
        return max(1.0, min(v, 600.0))
    except (TypeError, ValueError):
        return _DEFAULT_WINDOW_SEC


# ─── Counter API ─────────────────────────────────────────────────────

def incr(cls: WorkloadClass) -> int:
    """Increment the per-class counter. Returns the new depth."""
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"queue_pressure.incr expects WorkloadClass, got {type(cls).__name__}")
    with _lock:
        _depth[cls] += 1
        return _depth[cls]


def decr(cls: WorkloadClass) -> int:
    """Decrement the per-class counter. Floors at 0. Returns the new depth."""
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"queue_pressure.decr expects WorkloadClass, got {type(cls).__name__}")
    with _lock:
        if _depth[cls] > 0:
            _depth[cls] -= 1
        return _depth[cls]


def current_depth(cls: WorkloadClass) -> int:
    """Instantaneous depth for one class."""
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"queue_pressure.current_depth expects WorkloadClass, got {type(cls).__name__}")
    with _lock:
        return _depth[cls]


def all_depths() -> Dict[str, int]:
    """Instantaneous depth for every class (str-keyed for JSON)."""
    with _lock:
        return {c.value: _depth[c] for c in WorkloadClass}


# ─── Rolling-window API ──────────────────────────────────────────────

def sample(ts: Optional[float] = None) -> None:
    """Append one (ts, depth) row to the window. O(1)."""
    if ts is None:
        ts = time.time()
    with _lock:
        snap = {c: _depth[c] for c in WorkloadClass}
        _window.append((ts, snap))


def worker_utilization() -> float:
    """Compute active_workers / pool_size as a float in [0, 1].

    Reads `cpu_pool.get_pool_state()` for `worker_count` and
    `pool_size_configured`. When the pool is uninitialised (worker_count=0)
    OR cpu_pool isn't enabled, we report utilisation as the sum of
    BACKTEST+MUTATION depth / pool_size (best-effort proxy for the
    "is the pool saturated?" signal).
    """
    try:
        from engines import cpu_pool
        state = cpu_pool.get_pool_state()
        pool_n = max(1, int(state.get("pool_size_configured") or 1))
        # When the pool is initialised, prefer the actual worker count.
        # When uninitialised, fall back to in-flight cpu-bound depth.
        if state.get("pool_initialized"):
            # Approximate active workers by in-flight backtest+mutation
            # depth (clamped to pool_n). This is the value the admission
            # controller cares about — "how saturated is the pool".
            inflight = current_depth(WorkloadClass.BACKTEST) + current_depth(WorkloadClass.MUTATION)
            return round(min(1.0, inflight / pool_n), 3)
        # Pool not initialised → proxy via depth.
        inflight = current_depth(WorkloadClass.BACKTEST) + current_depth(WorkloadClass.MUTATION)
        return round(min(1.0, inflight / pool_n), 3)
    except Exception:                                          # pragma: no cover
        return 0.0


def snapshot() -> Dict[str, Any]:
    """Structured rolling-window summary.

    Shape:
        {
          "ts":                  iso-string,
          "window_sec":          float,
          "sample_count":        int,
          "worker_utilization":  float (0..1),
          "pressure_band":       "idle" | "normal" | "high" | "critical",
          "per_class": {
            "backtest":  {"depth_now": int, "depth_avg": float, "depth_max": int, "samples": int},
            "mutation":  ...,
            "factory_cycle": ...,
            "api_hot":   ...,
            "agent":     ...,
          },
        }

    The `pressure_band` is a categorical summary the admission
    controller consumes. Thresholds (per CAPACITY_ENGINE_DESIGN.md §4
    + operator decisions in P1.C):
        idle     : worker_utilization < 0.25 AND total_depth < 2
        normal   : worker_utilization < 0.70
        high     : worker_utilization < 0.90
        critical : worker_utilization >= 0.90  OR  total_depth > 2 * pool_size

    `worker_utilization` is bounded [0, 1]. `total_depth` is the sum
    over BACKTEST + MUTATION (the two pool-gated classes).
    """
    from datetime import datetime, timezone
    win = _window_sec()
    now = time.time()
    with _lock:
        # Snapshot the window under lock — copies (ts, dict) tuples but
        # the inner dicts are tiny.
        samples_in_window = [(ts, dict(d)) for ts, d in _window if (now - ts) <= win]
        depth_now = {c: _depth[c] for c in WorkloadClass}

    per_class: Dict[str, Dict[str, Any]] = {}
    for c in WorkloadClass:
        depths = [d.get(c, 0) for _ts, d in samples_in_window]
        per_class[c.value] = {
            "depth_now":  depth_now[c],
            "depth_avg":  round(sum(depths) / len(depths), 3) if depths else 0.0,
            "depth_max":  max(depths) if depths else depth_now[c],
            "samples":    len(depths),
        }

    util = worker_utilization()
    total_pool_depth = depth_now[WorkloadClass.BACKTEST] + depth_now[WorkloadClass.MUTATION]

    # Pool-size for the critical threshold.
    try:
        from engines import cpu_pool
        pool_n = max(1, int(cpu_pool.get_pool_state().get("pool_size_configured") or 1))
    except Exception:                                          # pragma: no cover
        pool_n = 1

    if util >= 0.90 or total_pool_depth > 2 * pool_n:
        band = "critical"
    elif util >= 0.70:
        band = "high"
    elif util >= 0.25 or total_pool_depth >= 2:
        band = "normal"
    else:
        band = "idle"

    return {
        "ts":                 datetime.now(timezone.utc).isoformat(),
        "window_sec":         win,
        "sample_count":       len(samples_in_window),
        "worker_utilization": util,
        "pressure_band":      band,
        "per_class":          per_class,
    }


# ─── Test-only helpers ───────────────────────────────────────────────

def reset() -> None:
    """Test-only: clear all counters + window. Never call in production."""
    with _lock:
        for c in WorkloadClass:
            _depth[c] = 0
        _window.clear()


def _set_depth_for_test(cls: WorkloadClass, n: int) -> None:
    """Test-only — directly set a per-class depth. Never call in prod."""
    with _lock:
        _depth[cls] = max(0, int(n))

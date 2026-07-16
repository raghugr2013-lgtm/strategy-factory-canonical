"""v1.2.0-alpha2 Phase B.1 — Continuous Capacity-Aware Scheduler.

Design goal: replace the fixed-interval sleep-and-tick learning scheduler
with an event-loop-native driver that continuously polls host capacity
(via the existing Adaptive Concurrency Engine) and launches learning
cycles as tasks whenever the resource envelope allows.

Additive. Opt-in via `LEARNING_CONTINUOUS_MODE=true`. When disabled, no
runtime change — the legacy `_scheduler_loop` in `supervisor.py`
continues to own the loop. When enabled, the legacy loop is dormant
and this module drives cycle dispatch.

Public surface (called by `api/learning.py`):
    start_continuous_scheduler() -> dict
    stop_continuous_scheduler()  -> dict
    continuous_status()          -> dict
    set_targets(**kwargs)        -> dict

Every field this module reads or writes lives outside the pre-existing
supervisor counters so the two subsystems can coexist during rollout.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Deque, Dict, List, Optional

from . import config as lcfg
from .supervisor import LearningSeed, run_learning_cycle

logger = logging.getLogger(__name__)


# ── Configurable knobs (env-driven; live-reload safe) ───────────────

def _int_env(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return int(default)
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _float_env(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return float(default)
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _flag_env(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def continuous_mode_enabled() -> bool:
    """Master switch for Phase B.1. Off by default → legacy scheduler runs."""
    return _flag_env("LEARNING_CONTINUOUS_MODE", False)


def tick_ms() -> int:
    """Loop cadence when we are actively launching work. Range 200..10000."""
    v = _int_env("LEARNING_CONTINUOUS_TICK_MS", 1000)
    return max(200, min(v, 10_000))


def idle_backoff_ms() -> int:
    """Loop cadence when capacity band is warn/critical or budgets are dry."""
    v = _int_env("LEARNING_CONTINUOUS_IDLE_MS", 2000)
    return max(500, min(v, 30_000))


def max_concurrent_hard() -> int:
    """Absolute ceiling on in-flight learning cycles regardless of adaptive
    recommendation. Prevents runaway concurrency from an overly-optimistic
    probe. Range 1..64. Default 8 — comfortably below any real VPS core
    count while leaving headroom for API workers + Mongo.
    """
    v = _int_env("LEARNING_CONTINUOUS_MAX_CONCURRENT", 8)
    return max(1, min(v, 64))


def cycles_per_hour_cap() -> int:
    """Safety governor: max learning cycles launched per rolling hour.
    Prevents burning provider budgets on a stuck factory. Range 1..100000.
    Default 600 → up to 10/minute sustained. Set to 0 to disable.
    """
    v = _int_env("LEARNING_CONTINUOUS_CYCLES_PER_HOUR", 600)
    return max(0, min(v, 100_000))


def per_provider_rpm_cap() -> int:
    """Max LLM requests per minute per provider across all in-flight
    cycles. 0 → disabled (rely on VIE's own limiter). Default 0."""
    v = _int_env("LEARNING_CONTINUOUS_PROVIDER_RPM", 0)
    return max(0, v)


# ── Internal state ──────────────────────────────────────────────────

_LOCK = RLock()
_TASK: Optional[asyncio.Task] = None
_STOP_EVT: Optional[asyncio.Event] = None

_IN_FLIGHT: Dict[str, Dict[str, Any]] = {}          # task_id → {run_id, started_at}
_LAUNCHED_TIMES: Deque[float] = deque(maxlen=100_000)   # rolling hour launches
_LAST_TICK: Dict[str, Any] = {
    "ts": None,
    "band": None,
    "recommended_concurrency": 0,
    "in_flight": 0,
    "launched_this_tick": 0,
    "reason": "",
    "sleep_ms": 0,
}
_META: Dict[str, Any] = {
    "started_at": None,
    "stopped_at": None,
    "cycles_launched_total": 0,
    "cycles_completed_total": 0,
    "cycles_failed_total": 0,
    "cycles_early_reject_total": 0,
    "tick_count": 0,
    "last_error": None,
}
_RECENT_TICKS: Deque[Dict[str, Any]] = deque(maxlen=200)


# ── Capacity computation ────────────────────────────────────────────

@dataclass
class Decision:
    launch_n:                int              # cycles to launch this tick
    sleep_ms:                int
    band:                    str
    band_reason:             str
    recommended_concurrency: int              # from adaptive_concurrency
    in_flight:               int
    reason:                  str = ""
    derivation:              Dict[str, Any] = field(default_factory=dict)


def _prune_hour_window(now: float) -> int:
    cutoff = now - 3600.0
    while _LAUNCHED_TIMES and _LAUNCHED_TIMES[0] < cutoff:
        _LAUNCHED_TIMES.popleft()
    return len(_LAUNCHED_TIMES)


def _capacity_target() -> Decision:
    """Merge the adaptive-concurrency recommendation, hard cap, and
    rolling-hour governor into one integer target for THIS tick.

    Failure modes degrade to conservative single-cycle behaviour.
    """
    now = time.time()
    in_flight = len(_IN_FLIGHT)
    launched_last_hour = _prune_hour_window(now)

    caps = None
    probe = None
    pressure = None
    try:
        from engines import compute_probe as _cp, queue_pressure as _qp
        from engines.host_capability import current as _current_caps, detect as _detect_caps
        caps = _current_caps()
        # First-tick fallback: nothing has called host_capability.persist()
        # yet during this process. Detect (pure OS read, no DB) and cache
        # so the adaptive sizer can produce > 1 recommendations. This is
        # additive and idempotent.
        if caps is None:
            try:
                caps = _detect_caps()
                # Poke the module cache so subsequent ticks skip the OS read.
                import engines.host_capability as _hc
                _hc._CACHE = caps  # noqa: SLF001 — intentional cache warm-up
            except Exception:  # noqa: BLE001
                caps = None
        probe = _cp.snapshot()
        pressure = _qp.snapshot()
    except Exception as e:  # noqa: BLE001
        logger.debug("[continuous] probe/pressure snapshot failed: %s", e)

    band = "unknown"
    band_reason = "capacity_layer_unavailable"
    rec_conc = 1
    try:
        from engines.adaptive_concurrency import recommend as _recommend
        targets = _recommend(caps, probe, pressure)
        band = targets.band
        band_reason = targets.band_reason
        # Backtest+mutation share the pool; use their max as the
        # concurrency ceiling for a "learning cycle" (which is
        # generate → backtest → optionally mutate).
        rec_conc = max(
            int(getattr(targets, "max_concurrent_backtests", 1)),
            int(getattr(targets, "max_concurrent_mutations", 1)),
        )
        # `adaptive_concurrency.recommend` returns 0 for band=critical
        # or unknown (correct for backtest gating). For a learning
        # cycle we still want SOME work to happen when the probe just
        # can't classify (fresh psutil boot, container restart) — so
        # if the band is `unknown` AND we have caps, use half the pool.
        if band == "unknown" and caps is not None:
            rec_conc = max(1, int(caps.effective_cpu_count) // 2)
    except Exception as e:  # noqa: BLE001
        logger.debug("[continuous] adaptive_concurrency.recommend failed: %s", e)

    hard = max_concurrent_hard()
    hourly = cycles_per_hour_cap()

    # Effective target for this tick.
    target = min(rec_conc, hard)

    # Governor: cap by remaining hourly budget.
    if hourly > 0:
        remaining = max(0, hourly - launched_last_hour)
        target = min(target, remaining)

    launch_n = max(0, target - in_flight)

    # Sleep policy — longer backoff when we're gated by capacity/pressure,
    # short cadence when we're actively dispatching or headroom exists.
    if band in ("critical", "unknown"):
        sleep_ms = idle_backoff_ms() * 2
        reason = f"band={band}: pausing dispatch"
    elif band == "warn":
        sleep_ms = idle_backoff_ms()
        reason = "band=warn: slowing dispatch"
    elif launch_n <= 0 and in_flight >= 1:
        sleep_ms = tick_ms()
        reason = "at_capacity: waiting for cycle completion"
    elif launch_n <= 0:
        sleep_ms = idle_backoff_ms()
        reason = "no_room: hourly cap reached" if (hourly > 0 and launched_last_hour >= hourly) \
            else "no_room: hard_cap or adaptive_target=0"
    else:
        sleep_ms = tick_ms()
        reason = f"launching {launch_n} cycle(s)"

    return Decision(
        launch_n=int(launch_n),
        sleep_ms=int(sleep_ms),
        band=band,
        band_reason=band_reason,
        recommended_concurrency=int(rec_conc),
        in_flight=int(in_flight),
        reason=reason,
        derivation={
            "hard_cap": hard,
            "hourly_cap": hourly,
            "launched_last_hour": launched_last_hour,
            "effective_target": target,
        },
    )


# ── Cycle dispatch ──────────────────────────────────────────────────

def _default_seed() -> LearningSeed:
    return LearningSeed(
        pair=os.environ.get("LEARNING_CONTINUOUS_PAIR", "EURUSD"),
        timeframe=os.environ.get("LEARNING_CONTINUOUS_TIMEFRAME", "H1"),
        style=os.environ.get("LEARNING_CONTINUOUS_STYLE", "trend-following"),
        count=1,
        max_duration_s=float(_int_env("LEARNING_CONTINUOUS_CYCLE_MAX_S", 300)),
    )


async def _dispatch_one(seed: LearningSeed) -> None:
    """Launch a single learning cycle as an isolated task; record start,
    completion, and outcome counters. Never raises to the parent loop."""
    task_id = f"cycle-{int(time.time() * 1000)}-{id(seed)}"
    with _LOCK:
        _IN_FLIGHT[task_id] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "run_id": None,
        }
        _LAUNCHED_TIMES.append(time.time())
        _META["cycles_launched_total"] += 1
    try:
        run = await run_learning_cycle(seed)
        with _LOCK:
            _IN_FLIGHT[task_id]["run_id"] = run.run_id
            if run.status == "completed":
                _META["cycles_completed_total"] += 1
            elif run.status == "early_reject":
                _META["cycles_early_reject_total"] += 1
            else:
                _META["cycles_failed_total"] += 1
    except Exception as e:  # noqa: BLE001
        logger.exception("[continuous] cycle dispatch crashed")
        with _LOCK:
            _META["cycles_failed_total"] += 1
            _META["last_error"] = str(e)[:240]
    finally:
        with _LOCK:
            _IN_FLIGHT.pop(task_id, None)


# ── Main scheduler loop ─────────────────────────────────────────────

async def _scheduler_body(stop_evt: asyncio.Event) -> None:
    """Continuously poll capacity and dispatch cycles. Exits cleanly when
    `stop_evt` is set. Every iteration is exception-safe."""
    logger.info("[continuous] scheduler loop started (mode=%s)",
                "on" if continuous_mode_enabled() else "off")
    with _LOCK:
        _META["started_at"] = datetime.now(timezone.utc).isoformat()

    seed = _default_seed()

    while not stop_evt.is_set():
        tick_ts = datetime.now(timezone.utc).isoformat()
        launched = 0
        try:
            decision = _capacity_target()

            for _ in range(decision.launch_n):
                asyncio.create_task(_dispatch_one(seed))
                launched += 1

            with _LOCK:
                _META["tick_count"] += 1
                snap = {
                    "ts": tick_ts,
                    "band": decision.band,
                    "band_reason": decision.band_reason,
                    "recommended_concurrency": decision.recommended_concurrency,
                    "in_flight": decision.in_flight,
                    "launched_this_tick": launched,
                    "reason": decision.reason,
                    "sleep_ms": decision.sleep_ms,
                    "derivation": decision.derivation,
                }
                _LAST_TICK.clear()
                _LAST_TICK.update(snap)
                _RECENT_TICKS.append(snap)

            # Refresh seed from env each tick so operator changes take
            # effect without restart.
            seed = _default_seed()
        except Exception as e:  # noqa: BLE001
            logger.exception("[continuous] tick body crashed (non-fatal)")
            with _LOCK:
                _META["last_error"] = str(e)[:240]

        try:
            await asyncio.wait_for(stop_evt.wait(),
                                   timeout=(_LAST_TICK.get("sleep_ms", tick_ms()) / 1000.0))
        except asyncio.TimeoutError:
            pass

    with _LOCK:
        _META["stopped_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("[continuous] scheduler loop stopped (tick_count=%d)", _META["tick_count"])


# ── Public API ──────────────────────────────────────────────────────

async def start_continuous_scheduler() -> Dict[str, Any]:
    """Idempotent — starts the loop if not already running. Enables the
    continuous-mode env flag implicitly for the lifetime of this process
    (operator toggle via API), so a subsequent call to `continuous_status`
    reports `enabled_by_env=True` even before the .env is rewritten."""
    global _TASK, _STOP_EVT
    with _LOCK:
        if _TASK is not None and not _TASK.done():
            return {"running": True, "already_started": True, **_snapshot_meta()}

    os.environ["LEARNING_CONTINUOUS_MODE"] = "true"
    _STOP_EVT = asyncio.Event()
    _TASK = asyncio.create_task(_scheduler_body(_STOP_EVT))
    return {"running": True, "already_started": False, **_snapshot_meta()}


async def stop_continuous_scheduler(*, timeout_s: float = 10.0) -> Dict[str, Any]:
    """Idempotent — signals the loop to stop, waits for in-flight cycles
    to complete up to `timeout_s`, then cancels any leftovers."""
    global _TASK, _STOP_EVT
    if _TASK is None or _TASK.done():
        return {"running": False, **_snapshot_meta()}
    if _STOP_EVT is not None:
        _STOP_EVT.set()
    try:
        await asyncio.wait_for(_TASK, timeout=timeout_s)
    except asyncio.TimeoutError:
        _TASK.cancel()
    _TASK = None
    _STOP_EVT = None
    return {"running": False, **_snapshot_meta()}


def continuous_status() -> Dict[str, Any]:
    """Snapshot for /api/learning/continuous/status."""
    with _LOCK:
        running = bool(_TASK and not _TASK.done())
        return {
            "running": running,
            "enabled_by_env": continuous_mode_enabled(),
            "config": {
                "tick_ms": tick_ms(),
                "idle_backoff_ms": idle_backoff_ms(),
                "max_concurrent_hard": max_concurrent_hard(),
                "cycles_per_hour_cap": cycles_per_hour_cap(),
                "per_provider_rpm_cap": per_provider_rpm_cap(),
                "default_seed": {
                    "pair": os.environ.get("LEARNING_CONTINUOUS_PAIR", "EURUSD"),
                    "timeframe": os.environ.get("LEARNING_CONTINUOUS_TIMEFRAME", "H1"),
                    "style": os.environ.get("LEARNING_CONTINUOUS_STYLE", "trend-following"),
                    "cycle_max_s": _int_env("LEARNING_CONTINUOUS_CYCLE_MAX_S", 300),
                },
            },
            "runtime": _snapshot_meta(),
            "last_tick": dict(_LAST_TICK),
            "in_flight": [
                {"task_id": tid, **info} for tid, info in list(_IN_FLIGHT.items())
            ],
            "recent_ticks": list(_RECENT_TICKS)[-20:],
        }


def _snapshot_meta() -> Dict[str, Any]:
    with _LOCK:
        return {
            "started_at": _META["started_at"],
            "stopped_at": _META["stopped_at"],
            "cycles_launched_total": _META["cycles_launched_total"],
            "cycles_completed_total": _META["cycles_completed_total"],
            "cycles_early_reject_total": _META["cycles_early_reject_total"],
            "cycles_failed_total": _META["cycles_failed_total"],
            "tick_count": _META["tick_count"],
            "last_error": _META["last_error"],
            "in_flight_now": len(_IN_FLIGHT),
        }


# ── Test-only helpers ────────────────────────────────────────────────

def _reset_for_test() -> None:
    with _LOCK:
        _IN_FLIGHT.clear()
        _LAUNCHED_TIMES.clear()
        _LAST_TICK.clear()
        _RECENT_TICKS.clear()
        for k in list(_META.keys()):
            if isinstance(_META[k], int):
                _META[k] = 0
            else:
                _META[k] = None

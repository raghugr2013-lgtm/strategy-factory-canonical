"""Phase B.2 — Central decision engine.

The `Orchestrator` runs a single asyncio coroutine that, every tick:

    ① gathers signals   — host_capability + compute_probe + queue_pressure
                          + adaptive_concurrency + budget_tracker
    ② collects candidates — every non-passive task in `registry`
    ③ calls `readiness()` on each — eligibility + freshness pressure
    ④ scores each     — (§5 of design doc) deterministic priority function
    ⑤ dispatches top-K — up to adaptive-concurrency ceilings + hard cap
    ⑥ records decision  — the last-N tick derivations kept in memory for
                          `/api/orchestrator/decisions`

Every step is exception-safe. A failing task adapter is logged and skipped;
the loop never crashes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Deque, Dict, List, Optional, Tuple

from .budget_tracker import BudgetTracker, get_budget_tracker
from .registry import registry
from .types import OrchestratorContext, Task, TaskResult

logger = logging.getLogger(__name__)


# ── Env knobs ────────────────────────────────────────────────────────

def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _flag_env(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def orchestrator_enabled() -> bool:
    return _flag_env("ORCHESTRATOR_ENABLED", False)


def tick_ms() -> int:
    v = _int_env("ORCH_TICK_MS", 1000)
    return max(200, min(v, 10_000))


def idle_ms() -> int:
    v = _int_env("ORCH_IDLE_MS", 2500)
    return max(500, min(v, 60_000))


def max_concurrent_tasks() -> int:
    v = _int_env("ORCH_MAX_CONCURRENT_TASKS", 12)
    return max(1, min(v, 128))


def decision_history_size() -> int:
    v = _int_env("ORCH_DECISION_HISTORY", 100)
    return max(10, min(v, 5000))


# ── Decision record ─────────────────────────────────────────────────

@dataclass
class Candidate:
    task_name:            str
    eligible:             bool
    reason:               str = ""
    priority_base:        float = 0.0
    business_value:       float = 0.0
    pressure:             float = 1.0
    dep_readiness:        float = 1.0
    budget_headroom:      float = 1.0
    resource_cost_factor: float = 1.0
    score:                float = 0.0
    last_completed_ts:    Optional[float] = None


# ── Core orchestrator ───────────────────────────────────────────────

class Orchestrator:
    """Singleton — one instance per process. Access via `get_orchestrator()`."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._task_task: Optional[asyncio.Task] = None
        self._stop_evt: Optional[asyncio.Event] = None
        self._in_flight: Dict[str, Dict[str, Any]] = {}    # asyncio_task_id → info
        self._last_completed_ts: Dict[str, float] = {}      # task_name → epoch
        self._runs_total: Dict[str, int] = {}
        self._runs_ok: Dict[str, int] = {}
        self._runs_fail: Dict[str, int] = {}
        self._decisions: Deque[Dict[str, Any]] = deque(maxlen=decision_history_size())
        self._meta: Dict[str, Any] = {
            "started_at": None,
            "stopped_at": None,
            "tick_count": 0,
            "dispatched_total": 0,
            "last_error": None,
            "last_tick": None,
        }

    # ── State accessors ──
    def is_running(self) -> bool:
        return self._task_task is not None and not self._task_task.done()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.is_running(),
                "enabled_by_env": orchestrator_enabled(),
                "config": {
                    "tick_ms": tick_ms(),
                    "idle_ms": idle_ms(),
                    "max_concurrent_tasks": max_concurrent_tasks(),
                    "decision_history_size": decision_history_size(),
                },
                "meta": dict(self._meta),
                "in_flight": [
                    {"task_id": tid, **info}
                    for tid, info in list(self._in_flight.items())
                ],
                "task_names": registry.names(),
                "counters": {
                    "runs_total": dict(self._runs_total),
                    "runs_ok":    dict(self._runs_ok),
                    "runs_fail":  dict(self._runs_fail),
                    "last_completed_ts": dict(self._last_completed_ts),
                },
                "recent_decisions": list(self._decisions)[-20:],
            }

    def decisions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._decisions)[-max(1, min(limit, 1000)):]

    # ── Signal gathering ──
    def _gather_signals(self) -> OrchestratorContext:
        caps = probe = pressure = adaptive = None
        try:
            from engines.host_capability import current as _current, detect as _detect
            caps = _current()
            if caps is None:
                try:
                    caps = _detect()
                    import engines.host_capability as _hc
                    _hc._CACHE = caps  # noqa: SLF001 — warm cache
                except Exception:                                # pragma: no cover
                    caps = None
        except Exception:                                        # pragma: no cover
            caps = None
        try:
            from engines import compute_probe as _cp
            probe = _cp.snapshot()
        except Exception:                                        # pragma: no cover
            probe = {}
        try:
            from engines import queue_pressure as _qp
            pressure = _qp.snapshot()
        except Exception:                                        # pragma: no cover
            pressure = {}
        try:
            from engines.adaptive_concurrency import recommend as _recommend
            adaptive = _recommend(caps, probe, pressure)
        except Exception:                                        # pragma: no cover
            adaptive = None

        return OrchestratorContext(
            tick_id=f"tick-{uuid.uuid4().hex[:12]}",
            caps=caps,
            probe=probe or {},
            pressure=pressure or {},
            adaptive=adaptive,
            budget=get_budget_tracker(),
            now_iso=datetime.now(timezone.utc).isoformat(),
            default_seed={
                "pair": os.environ.get("LEARNING_CONTINUOUS_PAIR", "EURUSD"),
                "timeframe": os.environ.get("LEARNING_CONTINUOUS_TIMEFRAME", "H1"),
                "style": os.environ.get("LEARNING_CONTINUOUS_STYLE", "trend-following"),
            },
        )

    # ── Candidate scoring ──
    async def _score_task(self, task: Task, ctx: OrchestratorContext) -> Candidate:
        name = task.NAME

        # Passive check first — respects env override.
        if registry.is_passive_via_env(name, bool(getattr(task, "PASSIVE", False))):
            return Candidate(task_name=name, eligible=False, reason="passive")

        # Task readiness
        try:
            r = await task.readiness(ctx)
        except Exception as e:                                   # noqa: BLE001
            logger.exception("[orchestrator] readiness(%s) crashed", name)
            return Candidate(task_name=name, eligible=False,
                             reason=f"readiness_crashed: {str(e)[:120]}")
        if not r.eligible:
            return Candidate(task_name=name, eligible=False, reason=r.reason,
                             dep_readiness=r.dependency_readiness)

        # Budget check (if AI required)
        budget_headroom = 1.0
        if getattr(task, "AI_PROVIDER_REQUIRED", False):
            est = float(getattr(task, "COST_ESTIMATE_USD", 0.0))
            ok, breason = ctx.budget.can_afford_global(est)
            if not ok:
                return Candidate(task_name=name, eligible=False,
                                 reason=f"budget:{breason}")
            budget_headroom = 1.0  # affordable → full weight

        # Resource cost factor (higher = worse)
        cpu_est = max(0.1, float(getattr(task, "CPU_ESTIMATE_CORES", 0.5)))
        ram_est_mb = int(getattr(task, "RAM_ESTIMATE_MB", 128))
        cpu_pct_available = 100.0 - float(ctx.probe.get("cpu_percent") or 0.0)
        mem_avail_gb = float(ctx.probe.get("mem_available_gb") or 0.0)
        # Normalise: if the task is expected to use most of headroom → factor grows
        cpu_pressure = (cpu_est * 100.0) / max(1.0, cpu_pct_available)
        mem_pressure = (ram_est_mb / 1024.0) / max(0.25, mem_avail_gb)
        resource_cost_factor = max(1.0, cpu_pressure + mem_pressure)

        priority_base = registry.priority_base_via_env(name, float(task.PRIORITY_BASE))
        business = float(getattr(task, "BUSINESS_VALUE", 0.5))
        score = (
            priority_base
            * business
            * max(0.01, r.pressure)
            * max(0.05, r.dependency_readiness)
            * budget_headroom
            / resource_cost_factor
        )

        return Candidate(
            task_name=name,
            eligible=True,
            reason=r.reason or "eligible",
            priority_base=priority_base,
            business_value=business,
            pressure=r.pressure,
            dep_readiness=r.dependency_readiness,
            budget_headroom=budget_headroom,
            resource_cost_factor=resource_cost_factor,
            score=score,
            last_completed_ts=self._last_completed_ts.get(name),
        )

    # ── Workload-class dispatch cap ──
    def _workload_capacity(self, ctx: OrchestratorContext) -> Dict[str, int]:
        """Map workload class → remaining dispatch slots this tick."""
        adaptive = ctx.adaptive
        # In-flight counts by workload class
        inflight_by_class: Dict[str, int] = {}
        for _tid, info in self._in_flight.items():
            wc = info.get("workload_class", "unknown")
            inflight_by_class[wc] = inflight_by_class.get(wc, 0) + 1

        def _cap(attr: str) -> int:
            if adaptive is None:
                return 1
            v = getattr(adaptive, attr, 0)
            if isinstance(v, str):
                return max_concurrent_tasks()  # "unlimited"
            return int(v)

        caps_map = {
            "backtest":       _cap("max_concurrent_backtests"),
            "mutation":       _cap("max_concurrent_mutations"),
            "factory_cycle":  _cap("max_concurrent_factory_cycles"),
            "api_hot":        max_concurrent_tasks(),
            "agent":          max_concurrent_tasks(),
            "io":             max_concurrent_tasks(),
        }
        remaining = {
            k: max(0, caps_map[k] - inflight_by_class.get(k, 0)) for k in caps_map
        }
        return remaining

    # ── Dispatch a chosen task ──
    async def _dispatch(self, task: Task, ctx: OrchestratorContext, score: float) -> None:
        task_id = f"orch-{task.NAME}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        wc = str(getattr(task, "WORKLOAD_CLASS", "unknown"))
        # Enum unwrapping if present
        wc = getattr(wc, "value", wc) if hasattr(wc, "value") else wc
        # For enums exposed as `WorkloadClass.BACKTEST`, .value is more useful
        try:
            from engines.workload_classes import WorkloadClass as _WC
            if isinstance(task.WORKLOAD_CLASS, _WC):
                wc = task.WORKLOAD_CLASS.value
        except Exception:                                        # pragma: no cover
            pass

        with self._lock:
            self._in_flight[task_id] = {
                "task_name": task.NAME,
                "workload_class": wc,
                "started_at": ctx.now_iso,
                "score": round(score, 3),
            }
            self._meta["dispatched_total"] = self._meta.get("dispatched_total", 0) + 1
            self._runs_total[task.NAME] = self._runs_total.get(task.NAME, 0) + 1
        t0 = time.time()
        result: Optional[TaskResult] = None
        error: Optional[str] = None
        try:
            result = await task.run(ctx)
        except Exception as e:                                   # noqa: BLE001
            logger.exception("[orchestrator] %s.run() crashed", task.NAME)
            error = str(e)[:240]
        finally:
            with self._lock:
                self._in_flight.pop(task_id, None)
                self._last_completed_ts[task.NAME] = time.time()
                if result and result.ok:
                    self._runs_ok[task.NAME] = self._runs_ok.get(task.NAME, 0) + 1
                else:
                    self._runs_fail[task.NAME] = self._runs_fail.get(task.NAME, 0) + 1
                    if error:
                        self._meta["last_error"] = f"{task.NAME}: {error}"
                    elif result and result.error:
                        self._meta["last_error"] = f"{task.NAME}: {result.error[:200]}"
            logger.info(
                "[orchestrator] %s → ok=%s dur_ms=%d reason=%s",
                task.NAME,
                bool(result and result.ok),
                int((time.time() - t0) * 1000),
                (result.reason if result else (error or "unknown")),
            )

    # ── Single tick ──
    async def _tick(self) -> Dict[str, Any]:
        ctx = self._gather_signals()
        band = getattr(ctx.adaptive, "band", "unknown") if ctx.adaptive is not None else "unknown"

        # Score every task
        candidates: List[Candidate] = []
        for task in registry.all():
            c = await self._score_task(task, ctx)
            candidates.append(c)

        # Sort eligible tasks by score DESC, then by staleness ASC.
        eligible = [c for c in candidates if c.eligible]
        eligible.sort(key=lambda c: (
            -c.score,
            (c.last_completed_ts or 0.0),
            c.task_name,
        ))

        # Enforce workload-class remaining capacity + global hard cap.
        remaining = self._workload_capacity(ctx)
        hard_cap_remaining = max(0, max_concurrent_tasks() - len(self._in_flight))

        launched: List[Dict[str, Any]] = []
        for c in eligible:
            if hard_cap_remaining <= 0:
                break
            task = registry.get(c.task_name)
            if task is None:
                continue
            wc = str(getattr(task, "WORKLOAD_CLASS", "unknown"))
            try:
                from engines.workload_classes import WorkloadClass as _WC
                if isinstance(task.WORKLOAD_CLASS, _WC):
                    wc = task.WORKLOAD_CLASS.value
            except Exception:                                    # pragma: no cover
                pass

            if remaining.get(wc, 0) <= 0:
                # Consumed all slots for this class — annotate reason and skip.
                c.reason = f"class_cap_reached ({wc})"
                c.eligible = False
                continue

            asyncio.create_task(self._dispatch(task, ctx, c.score))
            remaining[wc] -= 1
            hard_cap_remaining -= 1
            launched.append({
                "task_name": c.task_name,
                "workload_class": wc,
                "score": round(c.score, 3),
            })

        # Sleep policy — critical band forces longer backoff.
        if band == "critical":
            next_sleep = idle_ms() * 2
        elif band == "warn":
            next_sleep = idle_ms()
        elif not launched and self._in_flight:
            next_sleep = tick_ms()
        elif not launched:
            next_sleep = idle_ms()
        else:
            next_sleep = tick_ms()

        decision = {
            "tick_id": ctx.tick_id,
            "ts": ctx.now_iso,
            "band": band,
            "in_flight": len(self._in_flight),
            "launched": launched,
            "next_sleep_ms": next_sleep,
            "candidates": [c.__dict__ for c in candidates],
        }
        with self._lock:
            self._decisions.append(decision)
            self._meta["tick_count"] = self._meta.get("tick_count", 0) + 1
            self._meta["last_tick"] = {
                "tick_id": decision["tick_id"],
                "ts": decision["ts"],
                "band": band,
                "in_flight": decision["in_flight"],
                "launched": launched,
                "next_sleep_ms": next_sleep,
            }
        return decision

    # ── Public start/stop ──
    async def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._task_task is not None and not self._task_task.done():
                return {"running": True, "already_started": True, **self._meta}
        os.environ["ORCHESTRATOR_ENABLED"] = "true"
        self._stop_evt = asyncio.Event()

        async def _loop() -> None:
            with self._lock:
                self._meta["started_at"] = datetime.now(timezone.utc).isoformat()
                self._meta["stopped_at"] = None
            logger.info("[orchestrator] started")
            while not self._stop_evt.is_set():
                try:
                    decision = await self._tick()
                    sleep_s = float(decision["next_sleep_ms"]) / 1000.0
                except Exception as e:                             # noqa: BLE001
                    logger.exception("[orchestrator] tick crashed (non-fatal)")
                    with self._lock:
                        self._meta["last_error"] = str(e)[:240]
                    sleep_s = idle_ms() / 1000.0
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=sleep_s)
                except asyncio.TimeoutError:
                    pass
            with self._lock:
                self._meta["stopped_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("[orchestrator] stopped (tick_count=%d)", self._meta.get("tick_count", 0))

        self._task_task = asyncio.create_task(_loop())
        return {"running": True, "already_started": False, **self._meta}

    async def stop(self, *, timeout_s: float = 10.0) -> Dict[str, Any]:
        if self._task_task is None or self._task_task.done():
            return {"running": False, **self._meta}
        if self._stop_evt is not None:
            self._stop_evt.set()
        try:
            await asyncio.wait_for(self._task_task, timeout=timeout_s)
        except asyncio.TimeoutError:
            self._task_task.cancel()
        self._task_task = None
        self._stop_evt = None
        return {"running": False, **self._meta}

    # ── Manual dispatch (for /api/orchestrator/tasks/{name}/dispatch) ──
    async def dispatch_task(self, name: str) -> Dict[str, Any]:
        task = registry.get(name)
        if task is None:
            return {"ok": False, "reason": f"unknown_task: {name}"}
        ctx = self._gather_signals()
        # Skip readiness gating on manual dispatch — operator intent is explicit.
        t0 = time.time()
        try:
            result = await task.run(ctx)
            with self._lock:
                self._last_completed_ts[name] = time.time()
                self._runs_total[name] = self._runs_total.get(name, 0) + 1
                if result and result.ok:
                    self._runs_ok[name] = self._runs_ok.get(name, 0) + 1
                else:
                    self._runs_fail[name] = self._runs_fail.get(name, 0) + 1
            return {
                "ok": bool(result and result.ok),
                "reason": result.reason if result else "",
                "duration_ms": int((time.time() - t0) * 1000),
                "payload": result.payload if result else {},
                "error": result.error if result else None,
            }
        except Exception as e:                                    # noqa: BLE001
            logger.exception("[orchestrator] manual dispatch %s crashed", name)
            with self._lock:
                self._runs_fail[name] = self._runs_fail.get(name, 0) + 1
            return {"ok": False, "reason": str(e)[:240], "duration_ms": int((time.time() - t0) * 1000)}


# ── Singleton accessor ──────────────────────────────────────────────

_INSTANCE: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Orchestrator()
    return _INSTANCE


def is_active() -> bool:
    """Read-only helper consumed by legacy schedulers' subordinate hooks.

    Returns True iff the orchestrator is currently running. Cheap; no I/O.
    """
    if _INSTANCE is None:
        return False
    return _INSTANCE.is_running()

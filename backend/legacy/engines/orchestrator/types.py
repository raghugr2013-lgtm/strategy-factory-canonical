"""Phase B.2 — Types shared by the orchestrator, task registry, and adapters.

All types are dataclasses / Protocols for zero-cost duck typing. No runtime
dependency on anything outside the standard library.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, Tuple, runtime_checkable


# Re-export WorkloadClass without importing (avoids cycle in some contexts).
try:
    from engines.workload_classes import WorkloadClass
except Exception:  # pragma: no cover — fallback stub if legacy path missing
    class WorkloadClass(str):  # type: ignore
        BACKTEST = "backtest"
        MUTATION = "mutation"
        FACTORY_CYCLE = "factory_cycle"
        API_HOT = "api_hot"
        AGENT = "agent"
        IO = "io"


@dataclass
class Readiness:
    """Return-value of `Task.readiness()`. Consumed by the scoring engine."""
    eligible:  bool                 # False → task excluded from this tick
    reason:    str = ""             # human-readable explanation
    pressure:  float = 1.0          # 0..N — freshness multiplier
    dependency_readiness: float = 1.0  # 0..1 — fraction of dependencies satisfied
    depends_stale: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class TaskResult:
    """Return-value of `Task.run()`."""
    ok:            bool
    reason:        str = ""
    duration_ms:   int = 0
    payload:       Dict[str, Any] = field(default_factory=dict)
    error:         Optional[str] = None


@dataclass
class OrchestratorContext:
    """Read-only snapshot handed to each `Task.run()` invocation.

    Includes capacity signals, budget handle, and the current tick_id so
    downstream engines can correlate their own logs / outcome_events with
    the orchestrator decision that spawned them.
    """
    tick_id:        str
    caps:           Any                # HostCapability | None
    probe:          Dict[str, Any]     # compute_probe.snapshot()
    pressure:       Dict[str, Any]     # queue_pressure.snapshot()
    adaptive:       Any                # adaptive_concurrency.ConcurrencyTargets | None
    budget:         Any                # BudgetTracker handle
    now_iso:        str
    default_seed:   Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Task(Protocol):
    """Task protocol — every task adapter must satisfy this.

    Class-level metadata is preferred over instance state so registration
    is cheap and the registry can enumerate everything without invoking
    anything. Adapters are singletons (registered as classes; instantiated
    once by the registry).
    """

    NAME:                    str
    WORKLOAD_CLASS:          Any            # WorkloadClass enum
    DEPENDS_ON:              Tuple[str, ...]
    MIN_INTERVAL_S:          int            # 0 = event-driven only
    PRIORITY_BASE:           float          # 0..100
    CPU_ESTIMATE_CORES:      float
    RAM_ESTIMATE_MB:         int
    EXPECTED_DURATION_S:     float
    AI_PROVIDER_REQUIRED:    bool
    COST_ESTIMATE_USD:       float
    BUSINESS_VALUE:          float          # 0..1
    PASSIVE:                 bool           # if True, never dispatched

    async def readiness(self, ctx: OrchestratorContext) -> Readiness: ...
    async def run(self, ctx: OrchestratorContext) -> TaskResult: ...


# Type alias for adapter factories (used by the registry).
TaskFactory = Callable[[], Task]

"""
VPS Scaling P1.B — Workload class registry (PURE, NO I/O).

Five canonical workload classes. Every existing cpu-submission site in
this codebase maps to exactly one of these. Per-class defaults
(`cpu_share`, `mem_cap_mb`, `max_parallel_hint`) are *advisory* in
P1.B — they will be consumed by the adaptive concurrency calculator
in P1.C. P1.B uses only the enum membership.

Discipline (per CAPACITY_ENGINE_DESIGN.md §2):
  * No I/O, no DB, no env mutation.
  * Frozen vocabulary across all sub-phases — wrap sites in P1.D
    rely on this enum being stable.
  * `max_parallel_hint` semantics:
        "unlimited" — class is not gated on count (only on band).
        "pool_size" — class is bounded by current cpu_pool.pool_size().
        <int>       — fixed cap (used for FACTORY_CYCLE).
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class WorkloadClass(str, Enum):
    """The five canonical classes covering every cpu-submission site."""
    API_HOT       = "api_hot"
    BACKTEST      = "backtest"
    MUTATION      = "mutation"
    FACTORY_CYCLE = "factory_cycle"
    AGENT         = "agent"


# Per-class profile defaults. Operator-tunable in P1.C; do NOT consult
# in P1.B except via `profile_for()` (frozen contract).
_PROFILE_DEFAULTS: Dict[WorkloadClass, Dict[str, Any]] = {
    WorkloadClass.API_HOT:       {"cpu_share": 0.10, "mem_cap_mb":  200, "max_parallel_hint": "unlimited"},
    WorkloadClass.BACKTEST:      {"cpu_share": 0.50, "mem_cap_mb": 1024, "max_parallel_hint": "pool_size"},
    WorkloadClass.MUTATION:      {"cpu_share": 0.30, "mem_cap_mb":  768, "max_parallel_hint": "pool_size"},
    WorkloadClass.FACTORY_CYCLE: {"cpu_share": 0.05, "mem_cap_mb":  256, "max_parallel_hint": 1},
    WorkloadClass.AGENT:         {"cpu_share": 0.05, "mem_cap_mb":  512, "max_parallel_hint": "unlimited"},
}


def profile_for(cls: WorkloadClass) -> Dict[str, Any]:
    """Return a COPY of the per-class profile dict. Pure; idempotent."""
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"profile_for expects WorkloadClass, got {type(cls).__name__}")
    return dict(_PROFILE_DEFAULTS[cls])


def all_classes() -> list:
    """Frozen ordering: API_HOT, BACKTEST, MUTATION, FACTORY_CYCLE, AGENT."""
    return list(WorkloadClass)

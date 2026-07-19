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
    """The workload class taxonomy.

    Stage 1 (2026-02-19) extended the historical 5-class vocabulary to
    10 to cover the full Strategy Factory workload. The five originals
    keep their exact string values so every existing wrap site and
    task adapter continues to work unchanged.
    """
    # KEEP — historical (P1.B) — semantics unchanged
    API_HOT       = "api_hot"
    BACKTEST      = "backtest"
    MUTATION      = "mutation"
    FACTORY_CYCLE = "factory_cycle"
    AGENT         = "agent"
    # ADD — Phase 2 Stage 1 (2026-02-19)
    MARKET_DATA   = "market_data"     # BI5/BID ingest, tick pulls
    KNOWLEDGE     = "knowledge"       # UKIE connectors + index refresh
    EXECUTION     = "execution"       # broker calls, order lifecycle
    MONITORING    = "monitoring"      # dashboards, alert engines, MI observers
    META_LEARNING = "meta_learning"   # factory-eval / policy update


# Per-class profile defaults.
#
# Stage 1 (2026-02-19) added the `reservation` field per operator
# directive: "Live execution must never be starved. Market data
# ingestion must remain responsive. AI workloads should always yield
# to critical trading workloads. Background learning and research
# should use remaining capacity."
#
# Reservations are CONSERVATIVE for Stage 1 — calibrate later using
# production metrics. See PHASE_2D §1.2 for the target table.
_PROFILE_DEFAULTS: Dict[WorkloadClass, Dict[str, Any]] = {
    # Historical classes (values unchanged from P1.B) + reservation added.
    WorkloadClass.API_HOT:       {"cpu_share": 0.10, "mem_cap_mb":  200, "max_parallel_hint": "unlimited",  "reservation": 2},
    WorkloadClass.BACKTEST:      {"cpu_share": 0.50, "mem_cap_mb": 1024, "max_parallel_hint": "pool_size",  "reservation": 1},
    WorkloadClass.MUTATION:      {"cpu_share": 0.30, "mem_cap_mb":  768, "max_parallel_hint": "pool_size",  "reservation": 1},
    WorkloadClass.FACTORY_CYCLE: {"cpu_share": 0.05, "mem_cap_mb":  256, "max_parallel_hint": 1,            "reservation": 0},
    WorkloadClass.AGENT:         {"cpu_share": 0.05, "mem_cap_mb":  512, "max_parallel_hint": "unlimited",  "reservation": 1},
    # New classes (Stage 1).
    WorkloadClass.MARKET_DATA:   {"cpu_share": 0.03, "mem_cap_mb":  512, "max_parallel_hint": 2,            "reservation": 1},
    WorkloadClass.KNOWLEDGE:     {"cpu_share": 0.05, "mem_cap_mb":  768, "max_parallel_hint": 2,            "reservation": 0},
    WorkloadClass.EXECUTION:     {"cpu_share": 0.02, "mem_cap_mb":  256, "max_parallel_hint": "unlimited",  "reservation": 2},
    WorkloadClass.MONITORING:    {"cpu_share": 0.01, "mem_cap_mb":  128, "max_parallel_hint": "unlimited",  "reservation": 1},
    WorkloadClass.META_LEARNING: {"cpu_share": 0.05, "mem_cap_mb":  512, "max_parallel_hint": 1,            "reservation": 0},
}


def reservation_for(cls: WorkloadClass) -> int:
    """Return the reservation floor for a class.

    Operator env override: `ORCH_RESERVATION_<CLASS>=<int>` — e.g.
    `ORCH_RESERVATION_EXECUTION=3`. Non-parseable values fall back to
    the code default. Never raises.
    """
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"reservation_for expects WorkloadClass, got {type(cls).__name__}")
    import os as _os
    raw = _os.environ.get(f"ORCH_RESERVATION_{cls.value.upper()}")
    if raw is not None and str(raw).strip() != "":
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            pass
    return int(_PROFILE_DEFAULTS[cls]["reservation"])


def profile_for(cls: WorkloadClass) -> Dict[str, Any]:
    """Return a COPY of the per-class profile dict. Pure; idempotent."""
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"profile_for expects WorkloadClass, got {type(cls).__name__}")
    return dict(_PROFILE_DEFAULTS[cls])


def all_classes() -> list:
    """Frozen ordering: API_HOT, BACKTEST, MUTATION, FACTORY_CYCLE, AGENT."""
    return list(WorkloadClass)

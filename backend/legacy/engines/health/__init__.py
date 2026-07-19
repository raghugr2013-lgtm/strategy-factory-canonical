"""Universal Health Contract — Phase 2, Stage 1.

Every subsystem in the Strategy Factory (VIE, BI5, UKIE, COE,
Meta-Learning, Execution Intelligence, MI, Portfolio, Factory-Eval)
emits the same `HealthSnapshot` shape. This module is the ONLY place
that shape is defined.

Cross-cutting principle #12 (measurable health everywhere) —
PHASE_2_CONSOLIDATED_REVIEW §5.1 and PHASE_2D §1.1.8.

Public API:
    HealthSnapshot        — the canonical dataclass
    ResourceUsage         — the resource_usage sub-block
    LastSuccessfulRun     — the last_successful_run sub-block
    FailureCount          — the failure_count sub-block
    RecoveryStatus        — the recovery_status sub-block
    RecoveryState         — closed enum: ok|degraded|critical|recovering
    ActionRequired        — closed enum: none|operator_review|...
    empty_snapshot(name)  — helper that returns a "no data yet" snapshot
"""
from .contract import (
    ActionRequired,
    FailureCount,
    HealthSnapshot,
    LastSuccessfulRun,
    RecoveryState,
    RecoveryStatus,
    ResourceUsage,
    empty_snapshot,
)

__all__ = [
    "ActionRequired",
    "FailureCount",
    "HealthSnapshot",
    "LastSuccessfulRun",
    "RecoveryState",
    "RecoveryStatus",
    "ResourceUsage",
    "empty_snapshot",
]

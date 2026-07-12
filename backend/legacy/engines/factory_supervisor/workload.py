"""
Factory Supervisor FS-P1.1 — Workload envelope.

A canonical envelope every submission carries through the Supervisor.
Pure dataclass; NO I/O; NO behaviour. Routing + dispatching consume
this; persistence + observability emit from it.

Required fields (frozen for FS-P1.1, additive only after):

    workload_class    — engines.workload_classes.WorkloadClass value
                        (e.g. "backtest", "mutation", "factory_cycle")
    priority          — small int, 0=normal, +1=high, -1=low; advisory
    source_module     — free-text caller id ("mb2", "auto_factory",
                        "auto_learning_dormant", "ctrader_telemetry"…).
                        Used by Copilot to answer "where did this come
                        from?" without joining tables.
    correlation_id    — opaque uuid; ties a submission to its origin
                        event chain (mutation_id, cycle_id, …).
    created_at        — ISO8601 string (UTC). Stamped at envelope
                        creation; preserved verbatim through dispatch.
    routing_decision  — populated by routing_policy after policy run;
                        e.g. "local_only", "least_busy:vps-build-02".
                        None on a fresh envelope.
    assigned_host     — populated by routing_policy; defaults to local
                        host_id when policy returns local_only.

Forward-compat optionals (FS-P1.2+ may consume):
    payload           — arbitrary caller-supplied dict (the actual job
                        spec); never inspected by FS-P1.1.
    target_id         — optional target object id (mutation_id,
                        strategy_id, deployment_id, …).
    deadline_epoch    — optional Unix epoch by which the job must
                        complete; consumed by future SLO routing.
    capabilities_required — optional list of capability tags consulted
                        by `capability_based` routing policy.
    pair / strategy_id / deployment_id — affinity hints consumed by
                        the affinity routing policies.

Public surface:
    Workload                       — frozen dataclass
    new_workload(...)              — convenience constructor
    REQUIRED_METADATA_FIELDS       — for tests + Copilot manifest
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Frozen field set the operator approved as the FS-P1.1 metadata contract.
REQUIRED_METADATA_FIELDS: tuple = (
    "workload_class",
    "priority",
    "source_module",
    "correlation_id",
    "created_at",
    "routing_decision",
    "assigned_host",
)


@dataclass
class Workload:
    """Submission envelope. All FS-P1.1 metadata in one place."""

    # ── required metadata (frozen contract) ─────────────────────
    workload_class:    str
    source_module:     str
    correlation_id:    str
    created_at:        str
    priority:          int                = 0
    routing_decision:  Optional[str]      = None
    assigned_host:     Optional[str]      = None

    # ── forward-compat optionals ────────────────────────────────
    payload:           Dict[str, Any]     = field(default_factory=dict)
    target_id:         Optional[str]      = None
    deadline_epoch:    Optional[float]    = None
    capabilities_required: List[str]      = field(default_factory=list)
    pair:              Optional[str]      = None
    strategy_id:       Optional[str]      = None
    deployment_id:     Optional[str]      = None

    # ── derived (populated downstream; advisory) ────────────────
    workload_id:       str                = ""

    def __post_init__(self) -> None:
        if not self.workload_id:
            self.workload_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def has_required_metadata(self) -> bool:
        """All FS-P1.1 metadata fields populated (routing_decision +
        assigned_host MAY be None pre-dispatch)."""
        return all(
            getattr(self, k) is not None and getattr(self, k) != ""
            for k in ("workload_class", "source_module", "correlation_id", "created_at")
        )


def new_workload(
    *,
    workload_class:        str,
    source_module:         str,
    payload:               Optional[Dict[str, Any]] = None,
    priority:              int = 0,
    correlation_id:        Optional[str] = None,
    target_id:             Optional[str] = None,
    deadline_epoch:        Optional[float] = None,
    capabilities_required: Optional[List[str]] = None,
    pair:                  Optional[str] = None,
    strategy_id:           Optional[str] = None,
    deployment_id:         Optional[str] = None,
) -> Workload:
    """Convenience factory: stamps `created_at` + `correlation_id` if missing."""
    return Workload(
        workload_class    = str(workload_class),
        source_module     = str(source_module),
        correlation_id    = correlation_id or str(uuid.uuid4()),
        created_at        = datetime.now(timezone.utc).isoformat(),
        priority          = int(priority),
        payload           = dict(payload or {}),
        target_id         = target_id,
        deadline_epoch    = deadline_epoch,
        capabilities_required = list(capabilities_required or []),
        pair              = pair,
        strategy_id       = strategy_id,
        deployment_id     = deployment_id,
    )

"""Phase 2, Stage 1 — WorkloadRequest canonical envelope.

The unified shape every submitter uses to enqueue work. Stage 1
introduces the dataclass; Stage 2 wires the `WorkloadQueue.submit()`
consumer. Nothing in Stage 1 mandates use — existing engines keep
their direct-dispatch paths.

Distribution-ready invariant (§3 principle #11): every field is
JSON-serialisable so a `WorkloadRequest` can cross a process / node
boundary via a queue driver without transformation.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class Lane(str, Enum):
    """Priority lanes within a workload class.

    P0 — interactive (user-triggered, must not wait behind background)
    P1 — scheduled (orchestrator ticks, cron jobs)
    P2 — background (best-effort, may be starved)
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class RetryPolicy(str, Enum):
    """Retry disposition. Actual attempts + backoff come from class config."""

    NONE = "none"
    DEFAULT = "default"
    AGGRESSIVE = "aggressive"


def new_job_id() -> str:
    """Fresh short UUID for a job envelope."""
    return uuid.uuid4().hex[:16]


@dataclass
class WorkloadRequest:
    # Identity
    job_id: str = field(default_factory=new_job_id)
    class_: str = ""                 # WorkloadClass value (not enum type, for JSON safety)
    lane: str = Lane.P1.value
    task_name: str = ""              # matches orchestrator registry key

    # Origin
    submitted_by: str = "unknown"    # "api" | "scheduler" | "orchestrator" | "<user_id>"
    submitted_at: str = ""           # UTC ISO — auto-filled
    parent_job_id: Optional[str] = None
    correlation_id: Optional[str] = None   # research_run_id / learning_run_id

    # Payload — free-form dict, MUST be JSON-serialisable
    payload: Dict[str, Any] = field(default_factory=dict)

    # Execution hints (advisory)
    est_cost_usd: float = 0.0
    est_cpu_cores: float = 0.5
    est_ram_mb: int = 256
    est_duration_s: float = 30.0
    hard_timeout_s: Optional[float] = None    # overrides class default

    # Retry state
    attempt: int = 0
    max_attempts: int = 1
    last_error: Optional[str] = None
    last_failed_at: Optional[str] = None
    retry_policy: str = RetryPolicy.DEFAULT.value

    # Governance
    idempotency_key: Optional[str] = None
    provider_hint: Optional[str] = None       # for AGENT/BACKTEST-LLM
    tenant_id: Optional[str] = None           # reserved (Phase 3+)

    def __post_init__(self) -> None:
        if not self.submitted_at:
            self.submitted_at = datetime.now(timezone.utc).isoformat()
        # Normalize lane to string
        if isinstance(self.lane, Lane):
            self.lane = self.lane.value
        if isinstance(self.retry_policy, RetryPolicy):
            self.retry_policy = self.retry_policy.value

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkloadRequest":
        """Rehydrate a `WorkloadRequest` from a JSON-safe dict.

        Unknown fields are ignored; missing fields fall back to defaults.
        This is the driver-boundary hydrator (COE γ).
        """
        allowed = {
            "job_id", "class_", "lane", "task_name",
            "submitted_by", "submitted_at", "parent_job_id", "correlation_id",
            "payload",
            "est_cost_usd", "est_cpu_cores", "est_ram_mb", "est_duration_s", "hard_timeout_s",
            "attempt", "max_attempts", "last_error", "last_failed_at", "retry_policy",
            "idempotency_key", "provider_hint", "tenant_id",
        }
        clean = {k: v for k, v in (d or {}).items() if k in allowed}
        return cls(**clean)

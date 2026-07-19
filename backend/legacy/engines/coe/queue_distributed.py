"""Phase 2 — DistributedQueueDriver (stub for Phase 3+ γ driver).

Implements the WorkloadQueue Protocol so `COE_QUEUE_DRIVER=distributed`
can be selected AT INTERFACE LEVEL from day one — proving the
switch-point works. Every method raises `NotImplementedError` with a
clear message pointing to Phase 3.

This file exists to enforce the "distribution-ready from day one"
invariant (see PHASE_2_CONSOLIDATED_REVIEW §5 invariant #11):

  * The protocol is the same
  * The switch is a driver swap, not a rewrite
  * Any code path that would leak a single-node assumption fails
    LOUDLY here, at development time, not silently in production

Phase 3+ implementation choices:
  * Redis Streams (XADD / XREADGROUP)  — simplest, low-op cost
  * RabbitMQ with priority queues     — feature-rich, more ops
  * AWS SQS FIFO with priority groups — cloud-native

The chosen backend will populate this class; nothing else in the
Strategy Factory will need to change.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .workload_request import WorkloadRequest


class DistributedQueueDriver:
    """Stub — every method raises. See module docstring for rationale."""

    _WHY = (
        "Distributed queue driver is a Phase 3 deliverable. "
        "The Protocol is in place today so the switch will be a driver swap. "
        "Set COE_QUEUE_DRIVER=local to use the in-memory driver."
    )

    async def submit(self, req: WorkloadRequest) -> str:
        raise NotImplementedError(self._WHY)

    async def next(self, class_: str, cap: int) -> Optional[WorkloadRequest]:
        raise NotImplementedError(self._WHY)

    async def cancel(self, job_id: str) -> bool:
        raise NotImplementedError(self._WHY)

    async def peek(self, class_: str) -> Dict[str, int]:
        raise NotImplementedError(self._WHY)

    async def snapshot(self) -> Dict[str, Any]:
        return {
            "driver": "distributed",
            "status": "stub",
            "reason": self._WHY,
        }

    async def size(self) -> int:
        raise NotImplementedError(self._WHY)

"""Compute Orchestration Engine — Phase 2 canonical primitives.

Stage 1 ships:
  * WorkloadRequest — the unified job envelope
Stage 2 ships:
  * WorkloadQueue Protocol + LocalQueueDriver + DistributedQueueDriver stub

Everything here is JSON-serialisable and driver-agnostic so the
distributed-driver switch (COE γ) is a driver swap, not a rewrite.
"""
from .queue import (
    WorkloadQueue,
    get_queue,
    get_queue_driver_name,
    _reset_singleton_for_tests,
)
from .queue_local import LocalQueueDriver
from .queue_distributed import DistributedQueueDriver
from .workload_request import (
    Lane,
    RetryPolicy,
    WorkloadRequest,
    new_job_id,
)

__all__ = [
    "DistributedQueueDriver",
    "Lane",
    "LocalQueueDriver",
    "RetryPolicy",
    "WorkloadQueue",
    "WorkloadRequest",
    "get_queue",
    "get_queue_driver_name",
    "new_job_id",
    "_reset_singleton_for_tests",
]

"""Compute Orchestration Engine — Phase 2 canonical primitives.

Stage 1 ships:
  * WorkloadRequest — the unified job envelope
  * (Stage 2 will add WorkloadQueue)

Everything here is JSON-serialisable and driver-agnostic so the
distributed-driver switch (COE γ) is a driver swap, not a rewrite.
"""
from .workload_request import (
    Lane,
    RetryPolicy,
    WorkloadRequest,
    new_job_id,
)

__all__ = [
    "Lane",
    "RetryPolicy",
    "WorkloadRequest",
    "new_job_id",
]

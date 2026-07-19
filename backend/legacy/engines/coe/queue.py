"""Phase 2, Stage 2 — WorkloadQueue Protocol.

The unified dispatch surface: submit() enqueues a WorkloadRequest;
next() pulls the next-runnable job for a workload class, subject to
lane ordering (P0 → P1 → P2) and reservation floors.

Distribution-ready invariant (§3 principle #11): the Protocol is
identical for `LocalQueueDriver` (in-memory, Stage 2.β) and
`DistributedQueueDriver` (Redis/RabbitMQ/SQS, Phase 3+). Consumers
never learn which backend they're talking to.

Selection at boot: `COE_QUEUE_DRIVER=local` (default) | `distributed`.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .workload_request import Lane, WorkloadRequest


@runtime_checkable
class WorkloadQueue(Protocol):
    """The one interface every driver implements.

    All methods are async so the distributed driver's network I/O
    doesn't force a signature break at γ+.
    """

    async def submit(self, req: WorkloadRequest) -> str:
        """Enqueue a job. Returns the job_id (may be assigned server-side)."""
        ...

    async def next(self, class_: str, cap: int) -> Optional[WorkloadRequest]:
        """Return the next-runnable job for `class_` OR None.

        `cap` is the caller's willingness to accept work — the driver
        may return None if capacity is exhausted or no jobs match.
        Ordering: P0 → P1 → P2 within-class; FIFO within-lane.
        """
        ...

    async def cancel(self, job_id: str) -> bool:
        """Remove a queued (not-yet-running) job. Returns True on success."""
        ...

    async def peek(self, class_: str) -> Dict[str, int]:
        """Depths per lane for one class. Shape: {"P0": n, "P1": n, "P2": n, "total": n}."""
        ...

    async def snapshot(self) -> Dict[str, Any]:
        """Read-only diagnostic snapshot of the whole queue state."""
        ...

    async def size(self) -> int:
        """Total items across all classes and lanes."""
        ...


def get_queue_driver_name() -> str:
    """Return the configured driver name — used at boot for selection."""
    raw = (os.environ.get("COE_QUEUE_DRIVER") or "local").strip().lower()
    return raw if raw in ("local", "distributed") else "local"


def get_queue() -> WorkloadQueue:
    """Factory — returns the driver singleton per `COE_QUEUE_DRIVER`.

    Kept as a function (not a module-level singleton) so tests can
    force construction of a fresh instance by resetting the cache.
    """
    global _QUEUE_SINGLETON
    if _QUEUE_SINGLETON is not None:
        return _QUEUE_SINGLETON
    name = get_queue_driver_name()
    if name == "distributed":
        from .queue_distributed import DistributedQueueDriver
        _QUEUE_SINGLETON = DistributedQueueDriver()
    else:
        from .queue_local import LocalQueueDriver
        _QUEUE_SINGLETON = LocalQueueDriver()
    return _QUEUE_SINGLETON


_QUEUE_SINGLETON: Optional[WorkloadQueue] = None


def _reset_singleton_for_tests() -> None:
    """Test-only — force re-creation of the queue on next `get_queue()`."""
    global _QUEUE_SINGLETON
    _QUEUE_SINGLETON = None

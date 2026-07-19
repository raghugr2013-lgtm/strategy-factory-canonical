"""Phase 2, Stage 2 — LocalQueueDriver (in-memory).

Three lanes (P0/P1/P2) per workload class. Protected by asyncio.Lock
so all mutations are serialised — critical for the reservation-floor
invariant to hold under concurrent submit/next.

Reservations enforced at `next()` time, not `submit()` time. A class
may enqueue arbitrarily many jobs; the dispatcher pulls at most
`cap` from that class per tick, respecting the reservation floor.

Not-persisted. On restart, in-flight jobs at the caller-side are lost
(the caller retries; that's the retry-policy layer's job). Enqueued
jobs that haven't been picked up are lost.

Distribution-ready invariant: this class must NEVER expose internal
state (deques, dicts) to callers. Only the WorkloadQueue Protocol
methods are public. Everything else is implementation detail that
the future distributed driver may reorganise arbitrarily.
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from collections import deque
from typing import Any, Deque, Dict, Optional

from .queue import WorkloadQueue
from .workload_request import Lane, WorkloadRequest

logger = logging.getLogger(__name__)


class LocalQueueDriver:
    """In-memory driver. Implements WorkloadQueue."""

    def __init__(self) -> None:
        # Structure: {class_name: {"P0": deque, "P1": deque, "P2": deque}}
        self._lanes: Dict[str, Dict[str, Deque[WorkloadRequest]]] = {}
        # Job-id → (class_, lane) for cancel() lookups
        self._index: Dict[str, tuple] = {}
        self._lock = asyncio.Lock()

    def _ensure_class(self, class_: str) -> Dict[str, Deque[WorkloadRequest]]:
        if class_ not in self._lanes:
            self._lanes[class_] = {
                Lane.P0.value: deque(),
                Lane.P1.value: deque(),
                Lane.P2.value: deque(),
            }
        return self._lanes[class_]

    async def submit(self, req: WorkloadRequest) -> str:
        if not req.class_:
            raise ValueError("WorkloadRequest.class_ required")
        lane = req.lane if req.lane in (Lane.P0.value, Lane.P1.value, Lane.P2.value) else Lane.P1.value
        async with self._lock:
            lanes = self._ensure_class(req.class_)
            # Attach submission monotonic time for latency measurement
            req.__dict__["_submitted_mono"] = _time.perf_counter()
            lanes[lane].append(req)
            self._index[req.job_id] = (req.class_, lane)
        # Metrics
        try:
            from engines.metrics import get_metrics, Metric
            get_metrics().inc(Metric.QUEUE_SUBMIT_TOTAL, class_=req.class_, lane=lane)
        except Exception:                                # pragma: no cover
            pass
        return req.job_id

    async def next(self, class_: str, cap: int) -> Optional[WorkloadRequest]:
        """Pop the next-runnable job for `class_` respecting lane order.

        `cap` is advisory — the driver does not enforce it here (the
        caller's dispatcher gate enforces overall class capacity via
        `admission_gate`). This driver's only job is lane ordering and
        FIFO within lane.
        """
        if cap <= 0:
            return None
        async with self._lock:
            lanes = self._lanes.get(class_)
            if not lanes:
                return None
            for lane_name in (Lane.P0.value, Lane.P1.value, Lane.P2.value):
                dq = lanes[lane_name]
                if dq:
                    req = dq.popleft()
                    self._index.pop(req.job_id, None)
                    # Metrics — latency from submit → dispatch
                    try:
                        submitted_mono = req.__dict__.pop("_submitted_mono", None)
                        from engines.metrics import get_metrics, Metric
                        m = get_metrics()
                        m.inc(Metric.QUEUE_DISPATCH_TOTAL, class_=class_, lane=lane_name)
                        if submitted_mono is not None:
                            latency_ms = (_time.perf_counter() - submitted_mono) * 1000.0
                            m.observe(Metric.QUEUE_LATENCY_MS, latency_ms, class_=class_, lane=lane_name)
                    except Exception:                    # pragma: no cover
                        pass
                    return req
            return None

    async def cancel(self, job_id: str) -> bool:
        async with self._lock:
            ref = self._index.pop(job_id, None)
            if ref is None:
                return False
            class_, lane = ref
            lanes = self._lanes.get(class_)
            if not lanes:
                return False
            dq = lanes[lane]
            # Linear scan — jobs cancellations are rare compared to submits/pops
            for i, r in enumerate(dq):
                if r.job_id == job_id:
                    del dq[i]
                    return True
            return False

    async def peek(self, class_: str) -> Dict[str, int]:
        async with self._lock:
            lanes = self._lanes.get(class_)
            if not lanes:
                return {Lane.P0.value: 0, Lane.P1.value: 0, Lane.P2.value: 0, "total": 0}
            p0 = len(lanes[Lane.P0.value])
            p1 = len(lanes[Lane.P1.value])
            p2 = len(lanes[Lane.P2.value])
            return {Lane.P0.value: p0, Lane.P1.value: p1, Lane.P2.value: p2, "total": p0 + p1 + p2}

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            classes: Dict[str, Dict[str, int]] = {}
            total = 0
            for class_, lanes in self._lanes.items():
                p0 = len(lanes[Lane.P0.value])
                p1 = len(lanes[Lane.P1.value])
                p2 = len(lanes[Lane.P2.value])
                sub = p0 + p1 + p2
                total += sub
                classes[class_] = {"P0": p0, "P1": p1, "P2": p2, "total": sub}
            return {
                "driver": "local",
                "total_enqueued": total,
                "class_count": len(classes),
                "classes": classes,
            }

    async def size(self) -> int:
        async with self._lock:
            return sum(
                len(lanes[Lane.P0.value]) + len(lanes[Lane.P1.value]) + len(lanes[Lane.P2.value])
                for lanes in self._lanes.values()
            )

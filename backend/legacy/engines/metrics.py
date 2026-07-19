"""Phase 2, Stage 2 — lightweight metrics registry.

Stage 2 collects the measurements that will feed the Market Data
Validation Report per operator directive:

  * CTS aggregation performance
  * Cache generation time
  * Cache hit ratio
  * Queue latency
  * Workload scheduling latency
  * I/O pool utilisation
  * Historical rebuild timing

Kept intentionally small — no external dependency, no Prometheus text
format at this stage (Stage 2.ι lands the exporter). Records
in-memory counters + histogram buckets. Every metric is read via
`snapshot()` for consumption by observability endpoints and by the
validation report generator.

Thread-safety: `threading.Lock` (metrics are updated from both
asyncio tasks and sync code paths). Overhead per record: one dict
lookup + one list append — sub-microsecond.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional


class MetricsRegistry:
    """In-memory metrics registry — one instance per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Counters — monotonic
        self._counters: Dict[str, float] = {}
        # Histograms — bucketed samples
        self._histograms: Dict[str, List[float]] = {}
        # Gauges — instant values
        self._gauges: Dict[str, float] = {}
        # Labels — {metric_name: {label_key: value}} for future Prometheus
        self._labels: Dict[str, Dict[str, str]] = {}

    # ── Counters ──
    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + float(value)
            if labels:
                self._labels[key] = labels

    # ── Gauges ──
    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)
            if labels:
                self._labels[key] = labels

    # ── Histograms (bounded) ──
    def observe(self, name: str, value: float, **labels: str) -> None:
        """Record a histogram sample. Retained samples capped at 10000/metric."""
        key = self._key(name, labels)
        with self._lock:
            arr = self._histograms.setdefault(key, [])
            arr.append(float(value))
            if len(arr) > 10000:
                # Keep the most recent 10k — rolling window
                del arr[:-10000]
            if labels:
                self._labels[key] = labels

    # ── Timers ──
    def timer(self, name: str, **labels: str) -> "MetricTimer":
        """Context manager that observes duration in ms."""
        return MetricTimer(self, name, labels)

    # ── Read ──
    def snapshot(self) -> Dict[str, Any]:
        """Serialisable snapshot of the entire registry."""
        with self._lock:
            hist: Dict[str, Dict[str, float]] = {}
            for k, arr in self._histograms.items():
                if not arr:
                    continue
                sorted_arr = sorted(arr)
                n = len(sorted_arr)
                hist[k] = {
                    "count": n,
                    "sum": sum(sorted_arr),
                    "min": sorted_arr[0],
                    "max": sorted_arr[-1],
                    "p50": sorted_arr[n // 2],
                    "p95": sorted_arr[min(n - 1, int(n * 0.95))],
                    "p99": sorted_arr[min(n - 1, int(n * 0.99))],
                }
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": hist,
                "labels": dict(self._labels),
            }

    def reset(self) -> None:
        """Test-only: clear all metrics."""
        with self._lock:
            self._counters.clear()
            self._histograms.clear()
            self._gauges.clear()
            self._labels.clear()

    # ── Internals ──
    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]]) -> str:
        if not labels:
            return name
        # Deterministic key: name{k1=v1,k2=v2,...}
        pairs = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{pairs}}}"


class MetricTimer:
    """Context manager that observes elapsed ms into a histogram."""

    def __init__(self, registry: MetricsRegistry, name: str, labels: Dict[str, str]) -> None:
        self._registry = registry
        self._name = name
        self._labels = labels
        self._t0 = 0.0

    def __enter__(self) -> "MetricTimer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = (time.perf_counter() - self._t0) * 1000.0
        self._registry.observe(self._name, elapsed_ms, **self._labels)


# ── Module-level singleton ──
_REGISTRY: Optional[MetricsRegistry] = None


def get_metrics() -> MetricsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = MetricsRegistry()
    return _REGISTRY


# ── Canonical metric names (for consistency across the codebase) ──
class Metric:
    """Canonical metric name catalogue for Phase 2.

    Names follow Prometheus conventions:
      <subsystem>_<what>_<unit>[_total]

    Adding a new metric here first, then using `Metric.CTS_AGG_MS`
    at call sites, keeps the vocabulary discoverable.
    """

    # WorkloadQueue
    QUEUE_SUBMIT_TOTAL     = "coe_queue_submit_total"
    QUEUE_DISPATCH_TOTAL   = "coe_queue_dispatch_total"
    QUEUE_LATENCY_MS       = "coe_queue_latency_ms"          # submit → next
    QUEUE_DEPTH_GAUGE      = "coe_queue_depth"

    # Orchestrator
    ORCH_TICK_MS           = "coe_tick_ms"
    ORCH_DISPATCH_MS       = "coe_dispatch_ms"               # per task
    ORCH_RESERVATION_HIT   = "coe_reservation_hit_total"

    # I/O pool
    IO_POOL_SUBMIT_TOTAL   = "coe_io_pool_submit_total"
    IO_POOL_UTIL_GAUGE     = "coe_io_pool_utilization"

    # CTS (Canonical Timeframe Service — populated in Stage 2.ε/ζ)
    CTS_AGG_MS             = "cts_aggregation_ms"
    CTS_CACHE_HIT_TOTAL    = "cts_cache_hit_total"
    CTS_CACHE_MISS_TOTAL   = "cts_cache_miss_total"
    CTS_CACHE_WRITE_MS     = "cts_cache_write_ms"
    CTS_REBUILD_MS         = "cts_rebuild_ms"
    CTS_INVALIDATION_TOTAL = "cts_invalidation_total"

    # Budget
    BUDGET_RECORD_TOTAL    = "vie_budget_record_total"

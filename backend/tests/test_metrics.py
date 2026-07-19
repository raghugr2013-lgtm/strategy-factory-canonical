"""Phase 2, Stage 2 — metrics registry tests."""
from __future__ import annotations

import sys
import time
from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.metrics import Metric, MetricsRegistry, get_metrics  # noqa: E402


def test_counter_basic():
    r = MetricsRegistry()
    r.inc("foo", 1)
    r.inc("foo", 2)
    snap = r.snapshot()
    assert snap["counters"]["foo"] == 3.0


def test_counter_with_labels():
    r = MetricsRegistry()
    r.inc("bar", 1, class_="backtest", lane="P0")
    r.inc("bar", 1, class_="backtest", lane="P0")
    r.inc("bar", 1, class_="agent", lane="P1")
    snap = r.snapshot()
    keys = list(snap["counters"].keys())
    assert any("backtest" in k and "P0" in k for k in keys)
    assert any("agent" in k and "P1" in k for k in keys)


def test_gauge():
    r = MetricsRegistry()
    r.set_gauge("g", 5.0)
    r.set_gauge("g", 7.0)  # overwrites
    assert r.snapshot()["gauges"]["g"] == 7.0


def test_histogram_percentiles():
    r = MetricsRegistry()
    for v in range(100):
        r.observe("h", float(v))
    h = r.snapshot()["histograms"]["h"]
    assert h["count"] == 100
    assert h["min"] == 0.0
    assert h["max"] == 99.0
    assert 49 <= h["p50"] <= 51
    assert 94 <= h["p95"] <= 96


def test_histogram_bounded_at_10k():
    r = MetricsRegistry()
    for i in range(11000):
        r.observe("h", float(i))
    h = r.snapshot()["histograms"]["h"]
    assert h["count"] == 10000
    assert h["min"] >= 1000   # oldest 1000 evicted


def test_timer_records_ms():
    r = MetricsRegistry()
    with r.timer("t"):
        time.sleep(0.02)
    h = r.snapshot()["histograms"]["t"]
    assert h["count"] == 1
    # Should be at least 20 ms, allow generous upper bound for CI jitter
    assert 15.0 <= h["min"] <= 200.0


def test_singleton_get_metrics_is_stable():
    r1 = get_metrics()
    r2 = get_metrics()
    assert r1 is r2


def test_metric_name_catalogue_contains_stage2_names():
    """Sanity — every Stage-2 name we plan to record is declared."""
    for name in [
        Metric.QUEUE_SUBMIT_TOTAL,
        Metric.QUEUE_DISPATCH_TOTAL,
        Metric.QUEUE_LATENCY_MS,
        Metric.ORCH_TICK_MS,
        Metric.ORCH_DISPATCH_MS,
        Metric.IO_POOL_SUBMIT_TOTAL,
        Metric.CTS_AGG_MS,
        Metric.CTS_CACHE_HIT_TOTAL,
        Metric.CTS_CACHE_MISS_TOTAL,
        Metric.CTS_REBUILD_MS,
    ]:
        assert isinstance(name, str) and name


def test_reset_clears_all():
    r = MetricsRegistry()
    r.inc("x")
    r.observe("y", 1.0)
    r.set_gauge("z", 5.0)
    r.reset()
    snap = r.snapshot()
    assert snap["counters"] == {} and snap["histograms"] == {} and snap["gauges"] == {}

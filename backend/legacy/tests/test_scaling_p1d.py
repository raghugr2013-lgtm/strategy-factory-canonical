"""VPS Scaling Phase 1.D — Integration & Factory Wrapping tests.

Coverage:

* admission_wrapper.admission_gate — context-manager flag-OFF byte-identical
* admission_wrapper.admission_gate — flag-ON admit / defer / refuse paths
* admission_wrapper.admission_gate — counter incr/decr invariants
* admission_wrapper.admission_gate — exception types + verdict payload
* scaling_events — emit dormancy + ALL_EVENT_TYPES vocab + stats
* architect_scaling_view — all four read-only views + bundle
* Wrap-site signature smoke: cpu_pool / auto_factory / mutation_engine /
  master_bot_deployment all expose the same outer signature as before P1.D.
"""
from __future__ import annotations

import inspect
import os

import pytest

from engines import (
    admission_controller,
    admission_wrapper,
    architect_scaling_view,
    queue_pressure,
    scaling_events,
)
from engines.workload_classes import WorkloadClass


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_p1d():
    queue_pressure.reset()
    saved = {
        k: os.environ.pop(k, None)
        for k in (
            "ENABLE_ADMISSION_CONTROL",
            "QUEUE_PRESSURE_WINDOW_SEC",
            "CPU_POOL_SIZE",
            "ENABLE_ADAPTIVE_POOL_SIZING",
            "WORKLOAD_PROFILE",
        )
    }
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    queue_pressure.reset()


# ─── admission_wrapper.admission_gate — flag-OFF behaviour ───────────

@pytest.mark.asyncio
async def test_admission_gate_flag_off_is_noop():
    """With ENABLE_ADMISSION_CONTROL=false (default), the context manager
    enters and exits cleanly without touching counters or journal."""
    assert not admission_controller.is_enabled()
    before = queue_pressure.current_depth(WorkloadClass.BACKTEST)
    async with admission_wrapper.admission_gate(WorkloadClass.BACKTEST):
        # depth must NOT have been incremented when the gate is OFF
        assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == before
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == before


@pytest.mark.asyncio
async def test_admission_gate_type_check():
    with pytest.raises(TypeError):
        async with admission_wrapper.admission_gate("backtest"):
            pass


@pytest.mark.asyncio
async def test_admission_gate_flag_on_admit_increments_and_decrements(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    assert admission_controller.is_enabled()
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0
    async with admission_wrapper.admission_gate(WorkloadClass.BACKTEST):
        # incremented during the body
        assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 1
    # decremented after the body
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


@pytest.mark.asyncio
async def test_admission_gate_flag_on_decrements_even_on_exception(monkeypatch):
    """The `finally:` semantics MUST hold — depth returns to 0 even when
    the wrapped body raises."""
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    with pytest.raises(RuntimeError):
        async with admission_wrapper.admission_gate(WorkloadClass.BACKTEST):
            assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 1
            raise RuntimeError("boom")
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


@pytest.mark.asyncio
async def test_admission_gate_force_admits_critical(monkeypatch):
    """force=True bypasses the band gate (operator override)."""
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    # Inject critical probe via monkey-patching compute_probe.snapshot
    from engines import compute_probe
    monkeypatch.setattr(compute_probe, "snapshot",
                        lambda: {"cpu_percent": 99.0, "mem_percent": 50.0,
                                 "ts": "", "available": True, "cpu_count": 8,
                                 "load_avg": [0.5, 0.5, 0.5], "mem_total_gb": 16,
                                 "mem_available_gb": 8, "open_fds": 10,
                                 "process_rss_mb": 50.0})
    async with admission_wrapper.admission_gate(WorkloadClass.BACKTEST, force=True):
        assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 1


@pytest.mark.asyncio
async def test_admission_gate_raises_on_refuse(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    from engines import compute_probe
    monkeypatch.setattr(compute_probe, "snapshot",
                        lambda: {"cpu_percent": 99.0, "mem_percent": 50.0,
                                 "ts": "", "available": True, "cpu_count": 8,
                                 "load_avg": [0.5, 0.5, 0.5], "mem_total_gb": 16,
                                 "mem_available_gb": 8, "open_fds": 10,
                                 "process_rss_mb": 50.0})
    with pytest.raises(admission_wrapper.AdmissionRefused) as ei:
        async with admission_wrapper.admission_gate(WorkloadClass.BACKTEST):
            pytest.fail("body should not run when refused")
    assert ei.value.verdict["decision"] == "refuse"
    assert ei.value.verdict["band"] == "critical"
    # Counter must NOT have been incremented for a refused entry
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


@pytest.mark.asyncio
async def test_admission_gate_raises_on_defer(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    from engines import compute_probe
    # Unknown band: probe missing critical fields → API_HOT defers
    monkeypatch.setattr(compute_probe, "snapshot",
                        lambda: {"cpu_percent": None, "mem_percent": None,
                                 "ts": "", "available": False, "cpu_count": 0,
                                 "load_avg": [], "mem_total_gb": 0,
                                 "mem_available_gb": 0, "open_fds": 0,
                                 "process_rss_mb": 0.0})
    with pytest.raises(admission_wrapper.AdmissionDeferred) as ei:
        async with admission_wrapper.admission_gate(WorkloadClass.API_HOT):
            pytest.fail("body should not run when deferred")
    assert ei.value.verdict["decision"] == "defer"
    assert ei.value.retry_after_sec == 30


# ─── scaling_events — emitter behaviour ──────────────────────────────

def test_scaling_events_vocab_complete():
    """All five operator-required event types are present."""
    assert set(scaling_events.ALL_EVENT_TYPES) == {
        "HIGH_QUEUE_PRESSURE",
        "WORKER_SATURATION",
        "ADMISSION_DEFERRAL",
        "ADMISSION_REFUSED",
        "CAPACITY_WARNING",
    }


@pytest.mark.asyncio
async def test_scaling_events_emit_noop_when_flag_off():
    """With ENABLE_ADMISSION_CONTROL=false, emit() returns False."""
    assert not scaling_events.is_enabled()
    ok = await scaling_events.emit(scaling_events.EVENT_HIGH_QUEUE_PRESSURE, {"k": "v"})
    assert ok is False


@pytest.mark.asyncio
async def test_scaling_events_stats_returns_zero_keys_on_empty():
    """stats() with no events still returns every event type key."""
    s = await scaling_events.stats(window_sec=60)
    assert s["total"] >= 0  # may be >0 if other tests ran with flag ON
    assert set(s["per_type"].keys()) >= set(scaling_events.ALL_EVENT_TYPES)


# ─── architect_scaling_view — read-only surface ──────────────────────

@pytest.mark.asyncio
async def test_architect_view_host_capability_smoke():
    v = await architect_scaling_view.get_host_capability_view()
    assert "available" in v
    if v["available"]:
        assert "profile" in v
        assert "effective_cpu_count" in v


@pytest.mark.asyncio
async def test_architect_view_queue_pressure_smoke():
    v = await architect_scaling_view.get_queue_pressure_view()
    assert "pressure_band" in v or "available" in v
    if "pressure_band" in v:
        assert v["pressure_band"] in ("idle", "normal", "high", "critical")


@pytest.mark.asyncio
async def test_architect_view_concurrency_smoke():
    v = await architect_scaling_view.get_concurrency_recommendation()
    assert "targets" in v or "available" in v


@pytest.mark.asyncio
async def test_architect_view_journal_stats_shape():
    v = await architect_scaling_view.get_admission_journal_stats(window_sec=60)
    assert "per_decision" in v
    assert set(v["per_decision"].keys()) >= {"admit", "defer", "refuse"}


@pytest.mark.asyncio
async def test_architect_view_bundle():
    v = await architect_scaling_view.get_full_architect_snapshot(window_sec=60)
    assert set(v.keys()) >= {
        "host_capability",
        "queue_pressure",
        "concurrency_recommendation",
        "admission_journal_stats",
    }


# ─── Wrap-site outer-signature smoke ─────────────────────────────────
# Without running the real cycle, verify the public API of each
# wrap site is preserved (same name + same outer kwargs).

def test_cpu_pool_submit_cpu_signature():
    from engines import cpu_pool
    sig = inspect.signature(cpu_pool.submit_cpu)
    # `workload_class` is a NEW kwarg (defaulting to None) — additive,
    # no caller break. The first positional `fn` is preserved.
    params = list(sig.parameters)
    assert params[0] == "fn"
    assert "workload_class" in params
    # The default for the new param MUST be None so callers that don't
    # pass it get backtest semantics from the inner gate logic.
    assert sig.parameters["workload_class"].default is None


def test_auto_factory_run_auto_factory_cycle_signature():
    from engines import auto_factory
    sig = inspect.signature(auto_factory.run_auto_factory_cycle)
    expected = {"max_combos", "strategies_per_combo", "keep_top_n",
                "seed", "mc_simulations"}
    assert expected.issubset(set(sig.parameters))


def test_mutation_engine_run_mutation_pipeline_signature():
    from engines import mutation_engine
    sig = inspect.signature(mutation_engine.run_mutation_pipeline)
    expected = {"base_strategy", "max_variants", "prices",
                "triggered_by", "auto_save", "firm", "sim_config"}
    assert expected.issubset(set(sig.parameters))


def test_master_bot_deployment_promote_to_live_signature():
    from engines import master_bot_deployment
    sig = inspect.signature(master_bot_deployment.promote_to_live)
    assert "deployment_id" in sig.parameters
    assert "actor" in sig.parameters


# ─── Wrap-site flag-OFF byte-identical behaviour ─────────────────────

@pytest.mark.asyncio
async def test_cpu_pool_submit_cpu_flag_off_passthrough():
    """With ENABLE_ADMISSION_CONTROL=false, submit_cpu must work exactly
    as it did in P1.A/B — no gate, no journal, no events. We submit a
    trivial pure function and check the result."""
    from engines import cpu_pool

    def _square(x):
        return x * x

    out = await cpu_pool.submit_cpu(_square, 7)
    assert out == 49
    # No counter movement either (flag OFF semantics)
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


@pytest.mark.asyncio
async def test_cpu_pool_submit_cpu_flag_on_admit_path(monkeypatch):
    """With the flag ON and ok band, submit_cpu increments BACKTEST
    depth during the call and decrements after."""
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    from engines import cpu_pool

    captured = {}

    def _spy(x):
        captured["depth_during"] = queue_pressure.current_depth(WorkloadClass.BACKTEST)
        return x + 1

    out = await cpu_pool.submit_cpu(_spy, 41)
    assert out == 42
    assert captured["depth_during"] == 1
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


@pytest.mark.asyncio
async def test_cpu_pool_submit_cpu_accepts_explicit_workload_class(monkeypatch):
    """Caller can override the default BACKTEST class."""
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    from engines import cpu_pool

    captured = {}

    def _spy(x):
        captured["depth_during"] = queue_pressure.current_depth(WorkloadClass.MUTATION)
        return x

    out = await cpu_pool.submit_cpu(_spy, 1, workload_class=WorkloadClass.MUTATION)
    assert out == 1
    assert captured["depth_during"] == 1


# ─── P1.D dormancy invariant — Architect view is read-only ───────────

def test_architect_view_is_pure_read():
    """`architect_scaling_view` must not have any function that mutates
    state. We scan for known mutating verbs in callable names."""
    forbidden = {"set_", "incr", "decr", "reset", "delete", "drop",
                 "write", "insert", "update", "create", "emit"}
    for name, obj in vars(architect_scaling_view).items():
        if name.startswith("_") or not callable(obj):
            continue
        for verb in forbidden:
            assert verb not in name.lower(), (
                f"architect_scaling_view.{name} looks mutating ({verb}) "
                f"— P1.D requires read-only Architect surface."
            )


# ─── Final flag-OFF byte-identical regression ────────────────────────

def test_cpu_pool_pool_size_still_byte_identical_with_p1d_off():
    """With all P1.C/P1.D flags OFF and no env override, cpu_pool.pool_size()
    still returns the legacy default of 4 — UNCHANGED across all of P1.A→P1.D.
    """
    from engines import cpu_pool
    assert cpu_pool.pool_size() == 4

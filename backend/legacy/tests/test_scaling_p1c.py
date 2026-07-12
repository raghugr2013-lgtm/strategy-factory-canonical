"""VPS Scaling Phase 1.C — unit + integration tests.

Coverage (per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §5 + operator
explicit requirements for P1.C):

* queue_pressure: counter atomicity, floor at 0, rolling window
* queue_pressure: per-class snapshot keys + bands (idle/normal/high/critical)
* adaptive_concurrency.classify_band: probe-band classifier table
* adaptive_concurrency.recommend: per-band step-down table
* adaptive_concurrency.recommend: operator-required concurrency
  table for 4 vCPU / 12 vCPU / 32 vCPU / 64 vCPU
* admission_controller.gate: flag-OFF byte-identical (always admit)
* admission_controller.gate: per-band + per-class admit/defer/refuse table
* admission_controller.gate: per-class cap enforcement (defer on overflow)
* admission_controller: example admission decisions for mutation,
  backtest, validation/api_hot, and export/deployment (factory_cycle)
* Feature flag registration (ENABLE_ADMISSION_CONTROL, QUEUE_PRESSURE_WINDOW_SEC)
* Dormancy invariant: no production engine consumes the gate yet
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import pytest

from engines import (
    adaptive_concurrency,
    admission_controller,
    feature_flags as ff,
    host_capability,
    queue_pressure,
)
from engines.workload_classes import WorkloadClass


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate_p1c():
    """Reset queue_pressure + env between tests for determinism."""
    queue_pressure.reset()
    saved = {
        "ENABLE_ADMISSION_CONTROL":    os.environ.pop("ENABLE_ADMISSION_CONTROL", None),
        "QUEUE_PRESSURE_WINDOW_SEC":   os.environ.pop("QUEUE_PRESSURE_WINDOW_SEC", None),
        "CPU_POOL_SIZE":               os.environ.pop("CPU_POOL_SIZE", None),
        "ENABLE_ADAPTIVE_POOL_SIZING": os.environ.pop("ENABLE_ADAPTIVE_POOL_SIZING", None),
        "WORKLOAD_PROFILE":            os.environ.pop("WORKLOAD_PROFILE", None),
    }
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    queue_pressure.reset()


def _fake_caps(*, cpu_eff: int, mem_gb: float) -> host_capability.HostCapability:
    """Synthetic HostCapability without OS reads."""
    caps = host_capability.HostCapability(
        host_id="test-host", hostname="test-host",
        detected_at=datetime.now(timezone.utc).isoformat(),
        logical_cpu_count=cpu_eff, effective_cpu_count=cpu_eff,
        mem_total_gb=mem_gb, mem_available_gb=mem_gb * 0.5,
        swap_total_gb=0.0, disk_total_gb=None, cgroup_cpu_quota=None,
        kernel="", python="3.11", profile="",
    )
    caps.profile = host_capability.recommend_profile(caps)
    return caps


def _probe(cpu: float, mem: float) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "available": True, "cpu_count": 8,
        "cpu_percent": cpu, "mem_percent": mem,
        "load_avg": [0.5, 0.5, 0.5],
        "mem_total_gb": 16.0, "mem_available_gb": 8.0,
        "open_fds": 10, "process_rss_mb": 50.0,
    }


# ─── feature_flags registration ──────────────────────────────────────

def test_admission_flag_registered_default_off():
    snap = ff.all_flags()
    assert "ENABLE_ADMISSION_CONTROL" in snap
    assert snap["ENABLE_ADMISSION_CONTROL"]["default"] is False
    assert snap["ENABLE_ADMISSION_CONTROL"]["value"] is False
    assert snap["ENABLE_ADMISSION_CONTROL"]["scope"] == "scaling"


def test_queue_pressure_window_flag_registered():
    snap = ff.all_flags()
    assert "QUEUE_PRESSURE_WINDOW_SEC" in snap
    assert snap["QUEUE_PRESSURE_WINDOW_SEC"]["default"] == 30
    assert snap["QUEUE_PRESSURE_WINDOW_SEC"]["kind"] == "int"


# ─── queue_pressure unit tests ───────────────────────────────────────

def test_queue_pressure_counter_increment_decrement():
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0
    queue_pressure.incr(WorkloadClass.BACKTEST)
    queue_pressure.incr(WorkloadClass.BACKTEST)
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 2
    queue_pressure.decr(WorkloadClass.BACKTEST)
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 1


def test_queue_pressure_decr_floors_at_zero():
    """Caller bug → decr below 0 must clamp at 0."""
    queue_pressure.decr(WorkloadClass.BACKTEST)
    queue_pressure.decr(WorkloadClass.BACKTEST)
    queue_pressure.decr(WorkloadClass.BACKTEST)
    assert queue_pressure.current_depth(WorkloadClass.BACKTEST) == 0


def test_queue_pressure_incr_rejects_non_enum():
    with pytest.raises(TypeError):
        queue_pressure.incr("backtest")


def test_queue_pressure_all_depths_keys():
    depths = queue_pressure.all_depths()
    assert set(depths.keys()) == {"api_hot", "backtest", "mutation", "factory_cycle", "agent"}


def test_queue_pressure_snapshot_idle_band():
    """Empty counters + no pool init → band=idle, util=0."""
    snap = queue_pressure.snapshot()
    assert snap["pressure_band"] == "idle"
    assert snap["worker_utilization"] == 0.0
    assert snap["sample_count"] == 0
    assert set(snap["per_class"].keys()) == {"api_hot", "backtest", "mutation", "factory_cycle", "agent"}


def test_queue_pressure_snapshot_normal_band(monkeypatch):
    """2 in-flight (BACKTEST+MUTATION) with pool_size=4 → util=0.5 → high (>=0.25)."""
    monkeypatch.setenv("CPU_POOL_SIZE", "4")
    queue_pressure._set_depth_for_test(WorkloadClass.BACKTEST, 1)
    queue_pressure._set_depth_for_test(WorkloadClass.MUTATION, 1)
    snap = queue_pressure.snapshot()
    # util = 2/4 = 0.5 → normal band (0.25 <= util < 0.70)
    assert snap["worker_utilization"] == 0.5
    assert snap["pressure_band"] == "normal"


def test_queue_pressure_snapshot_high_band(monkeypatch):
    """3 in-flight with pool_size=4 → util=0.75 → high band."""
    monkeypatch.setenv("CPU_POOL_SIZE", "4")
    queue_pressure._set_depth_for_test(WorkloadClass.BACKTEST, 2)
    queue_pressure._set_depth_for_test(WorkloadClass.MUTATION, 1)
    snap = queue_pressure.snapshot()
    assert snap["worker_utilization"] == 0.75
    assert snap["pressure_band"] == "high"


def test_queue_pressure_snapshot_critical_band(monkeypatch):
    """9 in-flight with pool_size=4 → util clamped 1.0 → critical band."""
    monkeypatch.setenv("CPU_POOL_SIZE", "4")
    queue_pressure._set_depth_for_test(WorkloadClass.BACKTEST, 5)
    queue_pressure._set_depth_for_test(WorkloadClass.MUTATION, 4)
    snap = queue_pressure.snapshot()
    assert snap["worker_utilization"] == 1.0
    assert snap["pressure_band"] == "critical"


def test_queue_pressure_window_sample_rolloff(monkeypatch):
    """Samples older than window_sec must be excluded from the avg."""
    monkeypatch.setenv("QUEUE_PRESSURE_WINDOW_SEC", "1")
    # Stale sample (~5 s ago)
    queue_pressure.sample(ts=time.time() - 5.0)
    # Recent sample now
    queue_pressure._set_depth_for_test(WorkloadClass.BACKTEST, 3)
    queue_pressure.sample()
    snap = queue_pressure.snapshot()
    # Only the recent sample should be in the window
    assert snap["sample_count"] == 1
    assert snap["per_class"]["backtest"]["depth_avg"] == 3.0


def test_queue_pressure_window_env_clamps():
    """QUEUE_PRESSURE_WINDOW_SEC out-of-range clamps to [1, 600]."""
    os.environ["QUEUE_PRESSURE_WINDOW_SEC"] = "-5"
    assert queue_pressure._window_sec() == 30.0  # invalid → default
    os.environ["QUEUE_PRESSURE_WINDOW_SEC"] = "0"
    assert queue_pressure._window_sec() == 30.0  # zero → default
    os.environ["QUEUE_PRESSURE_WINDOW_SEC"] = "10000"
    assert queue_pressure._window_sec() == 600.0  # clamped to max
    os.environ.pop("QUEUE_PRESSURE_WINDOW_SEC", None)


# ─── adaptive_concurrency.classify_band ──────────────────────────────

@pytest.mark.parametrize("cpu,mem,expected", [
    ( 5.0,  10.0, "ok"),
    (10.0,  20.0, "ok"),
    (50.0,  50.0, "ok"),
    (60.0,  50.0, "ok_busy"),
    (50.0,  70.0, "ok_busy"),
    (75.0,  60.0, "ok_busy"),
    (80.0,  50.0, "warn"),
    (50.0,  85.0, "warn"),
    (90.0,  50.0, "warn"),
    (95.0,  50.0, "critical"),
    (50.0,  95.0, "critical"),
    (99.0,  99.0, "critical"),
])
def test_classify_band_table(cpu, mem, expected):
    band, _ = adaptive_concurrency.classify_band(_probe(cpu, mem))
    assert band == expected


def test_classify_band_unknown_when_probe_missing():
    band, reason = adaptive_concurrency.classify_band(None)
    assert band == "unknown"
    assert reason == "probe_missing"


def test_classify_band_unknown_when_fields_missing():
    band, reason = adaptive_concurrency.classify_band({"cpu_percent": None, "mem_percent": None})
    assert band == "unknown"


# ─── adaptive_concurrency.recommend — operator-required table ────────

def _recommend_table(cpu_eff: int, mem_gb: float, probe_cpu: float = 10.0,
                     probe_mem: float = 20.0):
    caps = _fake_caps(cpu_eff=cpu_eff, mem_gb=mem_gb)
    return adaptive_concurrency.recommend(caps, _probe(probe_cpu, probe_mem), None)


def test_concurrency_4_vcpu_ok():
    """4 vCPU @ ok → pool=2, bt=2, mut=2, fc=1."""
    t = _recommend_table(4, 8.0)
    assert t.pool_size == 2
    assert t.max_concurrent_backtests == 2
    assert t.max_concurrent_mutations == 2
    assert t.max_concurrent_factory_cycles == 1
    assert t.band == "ok"


def test_concurrency_12_vcpu_ok():
    """12 vCPU @ ok → pool=9, bt=9, mut=9, fc=1."""
    t = _recommend_table(12, 32.0)
    assert t.pool_size == 9
    assert t.max_concurrent_backtests == 9
    assert t.max_concurrent_mutations == 9
    assert t.max_concurrent_factory_cycles == 1
    assert t.band == "ok"


def test_concurrency_32_vcpu_ok():
    """32 vCPU @ ok → pool=28, bt=28, mut=28, fc=1."""
    t = _recommend_table(32, 64.0)
    assert t.pool_size == 28
    assert t.max_concurrent_backtests == 28
    assert t.max_concurrent_mutations == 28
    assert t.max_concurrent_factory_cycles == 1
    assert t.band == "ok"


def test_concurrency_64_vcpu_ok():
    """64 vCPU @ ok → pool=32 (ceiling), bt=32, mut=32, fc=1."""
    t = _recommend_table(64, 128.0)
    assert t.pool_size == 32   # adaptive_pool_sizer ceiling
    assert t.max_concurrent_backtests == 32
    assert t.max_concurrent_mutations == 32
    assert t.max_concurrent_factory_cycles == 1
    assert t.band == "ok"


# ─── adaptive_concurrency.recommend — band step-down ─────────────────

def test_concurrency_warn_band_halves_bt_mut_and_zeros_fc():
    """warn → bt=mut=pool//2 (min 1), fc=0."""
    t = _recommend_table(12, 32.0, probe_cpu=85.0, probe_mem=50.0)
    assert t.band == "warn"
    assert t.pool_size == 9
    assert t.max_concurrent_backtests == 4    # 9//2
    assert t.max_concurrent_mutations == 4
    assert t.max_concurrent_factory_cycles == 0


def test_concurrency_critical_band_zeros_all():
    """critical → bt=mut=fc=0."""
    t = _recommend_table(12, 32.0, probe_cpu=99.0, probe_mem=50.0)
    assert t.band == "critical"
    assert t.max_concurrent_backtests == 0
    assert t.max_concurrent_mutations == 0
    assert t.max_concurrent_factory_cycles == 0


def test_concurrency_unknown_band_zeros_all():
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    t = adaptive_concurrency.recommend(caps, None, None)
    assert t.band == "unknown"
    assert t.max_concurrent_backtests == 0
    assert t.max_concurrent_mutations == 0
    assert t.max_concurrent_factory_cycles == 0


def test_concurrency_ok_busy_does_not_step_down():
    """ok_busy is still admit-band — same caps as ok."""
    t = _recommend_table(12, 32.0, probe_cpu=65.0, probe_mem=50.0)
    assert t.band == "ok_busy"
    assert t.max_concurrent_backtests == 9
    assert t.max_concurrent_mutations == 9
    assert t.max_concurrent_factory_cycles == 1


def test_concurrency_queue_critical_pressure_steps_down():
    """Even when probe is OK, queue-pressure=critical forces step-down."""
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    pressure = {"pressure_band": "critical", "worker_utilization": 0.99}
    t = adaptive_concurrency.recommend(caps, _probe(10.0, 20.0), pressure)
    assert t.band == "critical"
    assert t.max_concurrent_backtests == 0


def test_concurrency_caps_none_safe_default():
    """No caps + no probe → pool_size=1, band=unknown."""
    t = adaptive_concurrency.recommend(None, None, None)
    assert t.pool_size == 1
    assert t.band == "unknown"


# ─── admission_controller.gate — flag-OFF byte-identical ─────────────

def test_admission_flag_off_always_admits():
    """ENABLE_ADMISSION_CONTROL=OFF → every class admits with reason=flag_off."""
    assert not admission_controller.is_enabled()
    for c in WorkloadClass:
        v = admission_controller.gate(c)
        assert v.decision == "admit"
        assert v.reason == "flag_off"
        assert v.class_ == c.value


def test_admission_force_admits_even_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")
    # Inject a critical probe → would refuse without force
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    v = admission_controller.gate(
        WorkloadClass.BACKTEST, force=True,
        caps=caps, probe=_probe(99.0, 50.0),
    )
    assert v.decision == "admit"
    assert v.reason == "force_override"


def test_admission_rejects_non_enum():
    with pytest.raises(TypeError):
        admission_controller.gate("backtest")


# ─── admission_controller.gate — per-band per-class table ────────────

@pytest.fixture
def _enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_ADMISSION_CONTROL", "true")


def _gate(cls, cpu, mem, *, caps=None):
    if caps is None:
        caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    return admission_controller.gate(
        cls, caps=caps, probe=_probe(cpu, mem), pressure={"pressure_band": "idle"},
    )


def test_admission_critical_band_refuses_everything(_enabled):
    """critical band → refuse for ALL classes."""
    for c in WorkloadClass:
        v = _gate(c, 99.0, 99.0)
        assert v.decision == "refuse", f"{c.value} expected refuse got {v.decision}"
        assert v.band == "critical"


def test_admission_warn_band_refuses_factory_cycle(_enabled):
    """warn → factory_cycle refused; bt/mut admit (under cap)."""
    v_fc = _gate(WorkloadClass.FACTORY_CYCLE, 85.0, 50.0)
    assert v_fc.decision == "refuse"
    v_bt = _gate(WorkloadClass.BACKTEST, 85.0, 50.0)
    # bt cap @ warn = 4 (9//2), depth=0 → admit
    assert v_bt.decision == "admit"
    assert v_bt.band == "warn"


def test_admission_unknown_band_defers_api_hot_refuses_rest(_enabled):
    """unknown → API_HOT defers (retry-able); others refuse."""
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    # Inject explicit unknown-band probe (cpu_percent missing) so we don't
    # accidentally read the live host probe which would classify as ok.
    bad_probe = {"cpu_percent": None, "mem_percent": None}
    v_api = admission_controller.gate(WorkloadClass.API_HOT, caps=caps,
                                       probe=bad_probe, pressure={"pressure_band": "idle"})
    assert v_api.decision == "defer"
    assert v_api.retry_after_sec == 30
    v_bt = admission_controller.gate(WorkloadClass.BACKTEST, caps=caps,
                                      probe=bad_probe, pressure={"pressure_band": "idle"})
    assert v_bt.decision == "refuse"
    v_agent = admission_controller.gate(WorkloadClass.AGENT, caps=caps,
                                         probe=bad_probe, pressure={"pressure_band": "idle"})
    assert v_agent.decision == "refuse"


def test_admission_ok_band_admits_under_cap(_enabled):
    v = _gate(WorkloadClass.BACKTEST, 10.0, 20.0)
    assert v.decision == "admit"
    assert v.band == "ok"


def test_admission_cap_overflow_defers(_enabled):
    """Depth >= cap → defer with retry_after=30. Critically NOT refuse."""
    caps = _fake_caps(cpu_eff=4, mem_gb=8.0)  # pool=2 → bt cap=2 @ ok
    queue_pressure._set_depth_for_test(WorkloadClass.BACKTEST, 2)
    v = admission_controller.gate(
        WorkloadClass.BACKTEST, caps=caps,
        probe=_probe(10.0, 20.0), pressure={"pressure_band": "idle"},
    )
    assert v.decision == "defer"
    assert "cap_reached" in v.reason
    assert v.retry_after_sec == 30


# ─── Operator-required example admission decisions ───────────────────
# These four tests are the explicit per-class examples the operator
# requested in the P1.C scope: mutation / backtest / validation / export.

def test_admission_example_mutation_task_admits_when_ok(_enabled):
    """MUTATION task on idle 12 vCPU box → admit."""
    v = _gate(WorkloadClass.MUTATION, 20.0, 30.0)
    assert v.decision == "admit"
    assert v.band == "ok"
    assert v.targets["max_concurrent_mutations"] == 9


def test_admission_example_backtest_task_admits_when_ok(_enabled):
    """BACKTEST task on idle 12 vCPU box → admit."""
    v = _gate(WorkloadClass.BACKTEST, 20.0, 30.0)
    assert v.decision == "admit"
    assert v.targets["max_concurrent_backtests"] == 9


def test_admission_example_validation_task_uses_api_hot(_enabled):
    """Validation/UI calls use API_HOT — never count-gated, only band-gated."""
    # 50% CPU is fine for API_HOT
    v = _gate(WorkloadClass.API_HOT, 50.0, 50.0)
    assert v.decision == "admit"
    assert v.targets["max_concurrent_api_hot"] == "unlimited"
    # Under critical it refuses
    v_crit = _gate(WorkloadClass.API_HOT, 99.0, 50.0)
    assert v_crit.decision == "refuse"


def test_admission_example_export_deployment_uses_factory_cycle(_enabled):
    """Exports / MB-9 deployments map to FACTORY_CYCLE — admit @ ok with cap=1,
    refuse the moment band steps to warn or critical (serial-by-design).
    """
    v_ok = _gate(WorkloadClass.FACTORY_CYCLE, 20.0, 30.0)
    assert v_ok.decision == "admit"
    assert v_ok.targets["max_concurrent_factory_cycles"] == 1
    v_warn = _gate(WorkloadClass.FACTORY_CYCLE, 85.0, 50.0)
    assert v_warn.decision == "refuse"
    v_crit = _gate(WorkloadClass.FACTORY_CYCLE, 99.0, 50.0)
    assert v_crit.decision == "refuse"


# ─── Dormancy invariant ──────────────────────────────────────────────

def test_no_engine_imports_admission_controller_yet():
    """P1.C/P1.D invariant: business engines MUST consume the admission
    gate ONLY via `admission_wrapper.admission_gate` — never via direct
    `admission_controller` import. This keeps the gate's policy in one
    place and makes the wrap-site contract auditable.

    Allowed direct importers:
        * engines/admission_controller.py — itself
        * engines/admission_wrapper.py    — the canonical wrap helper
        * engines/architect_scaling_view.py — DORMANT read-only view
        * api/scaling.py                  — diagnostic preview
        * server.py                       — startup index hook
    """
    import pathlib
    import re
    repo_root = pathlib.Path("/app/backend")
    allowed_files = {
        "scaling.py", "server.py",
        "admission_controller.py", "admission_wrapper.py",
        "architect_scaling_view.py",
    }
    pattern = re.compile(r"^\s*(from|import)\s+\S*admission_controller", re.MULTILINE)
    offenders = []
    for p in repo_root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        if p.name in allowed_files:
            continue
        try:
            txt = p.read_text()
        except Exception:
            continue
        if pattern.search(txt):
            offenders.append(str(p))
    assert offenders == [], (
        f"P1.C dormancy invariant broken — these files import "
        f"admission_controller before P1.D wiring: {offenders}"
    )


def test_no_engine_imports_queue_pressure_yet():
    """P1.C/P1.D invariant: queue_pressure is only consumed by the
    wrapper chain, the controller, the concurrency calculator, and
    the architect read-only view. Business engines must NOT touch
    the counters directly.

    Allowed importers:
        * engines/queue_pressure.py — itself
        * engines/admission_controller.py — read-only depth lookup
        * engines/admission_wrapper.py    — incr/decr around wrapped work
        * engines/adaptive_concurrency.py — read-only band classifier
        * engines/architect_scaling_view.py — DORMANT read-only view
        * api/scaling.py — diagnostic preview
    """
    import pathlib
    import re
    repo_root = pathlib.Path("/app/backend")
    allowed_files = {
        "queue_pressure.py", "admission_controller.py",
        "admission_wrapper.py",
        "adaptive_concurrency.py", "scaling.py",
        "architect_scaling_view.py",
    }
    pattern = re.compile(r"^\s*(from|import)\s+\S*queue_pressure", re.MULTILINE)
    offenders = []
    for p in repo_root.rglob("*.py"):
        if "tests" in p.parts:
            continue
        if p.name in allowed_files:
            continue
        try:
            txt = p.read_text()
        except Exception:
            continue
        if pattern.search(txt):
            offenders.append(str(p))
    assert offenders == [], (
        f"P1.C dormancy invariant broken — these files import "
        f"queue_pressure before P1.D wiring: {offenders}"
    )


def test_cpu_pool_pool_size_byte_identical_with_p1c_off():
    """Final P1.C invariant: cpu_pool.pool_size() with all P1.C flags OFF
    returns the same value as before P1.C was introduced.
    """
    from engines import cpu_pool
    # Flag OFF + no env → legacy default 4
    assert cpu_pool.pool_size() == 4

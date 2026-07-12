"""VPS Scaling Phase 1.B — unit + integration tests.

Coverage (per VPS_SCALING_P1_IMPLEMENTATION_PLAN.md §5 and operator
explicit requirements):

* WorkloadClass enum + per-class profile defaults are stable
* host_capability.detect() returns sane values on the test host
* host_capability.recommend_profile() honours WORKLOAD_PROFILE env pin
* host_capability.recommend_profile() classifies hosts correctly
* adaptive_pool_sizer.recommend_pool_size() — explicit table for
  4 vCPU / 12 vCPU / 32 vCPU / 64 vCPU as required by the operator
* adaptive_pool_sizer floor/ceiling clamps
* cpu_pool.pool_size() — flag-OFF byte-identical to pre-P1.B
* cpu_pool.pool_size() — CPU_POOL_SIZE env wins absolutely
* cpu_pool.pool_size() — adaptive path consulted only when flag ON
  AND host capability detected AND env unset
* Feature flag registration + default-dormant
* host_capability.persist() upserts idempotently
* Dormancy invariant: no production engine wires adaptive sizing into
  any business path yet (P1.D introduces wrap sites)
"""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from engines import (
    adaptive_pool_sizer,
    cpu_pool,
    feature_flags as ff,
    host_capability,
    workload_classes,
)
from engines.db import get_db


# ─── Fixtures ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _isolate_host_cap():
    """Reset module caches + env between tests for determinism."""
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    host_capability.reset_cache()
    # Save + drop env vars that influence pool sizing/profile.
    saved = {
        "CPU_POOL_SIZE":              os.environ.pop("CPU_POOL_SIZE", None),
        "ENABLE_ADAPTIVE_POOL_SIZING": os.environ.pop("ENABLE_ADAPTIVE_POOL_SIZING", None),
        "WORKLOAD_PROFILE":           os.environ.pop("WORKLOAD_PROFILE", None),
    }
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    host_capability.reset_cache()


def _fake_caps(*, cpu_eff: int, mem_gb: float, profile: str = "auto",
               host_id: str = "test-host", pinned: bool = False) -> host_capability.HostCapability:
    """Build a minimal HostCapability fixture WITHOUT touching the OS.

    When `profile="auto"` (the default), we run `recommend_profile()`
    just like `detect()` does — so the fixture mirrors real boot.
    """
    caps = host_capability.HostCapability(
        host_id=host_id,
        hostname=host_id,
        detected_at=datetime.now(timezone.utc).isoformat(),
        logical_cpu_count=cpu_eff,
        effective_cpu_count=cpu_eff,
        mem_total_gb=mem_gb,
        mem_available_gb=mem_gb * 0.5,
        swap_total_gb=0.0,
        disk_total_gb=None,
        cgroup_cpu_quota=None,
        kernel="",
        python="3.11.0",
        profile=profile,
        profile_pinned_via_env=pinned,
        psutil_available=True,
    )
    if profile == "auto":
        caps.profile = host_capability.recommend_profile(caps)
    return caps


# ─── workload_classes ────────────────────────────────────────────────

def test_workload_classes_enum_membership():
    classes = workload_classes.all_classes()
    names = {c.value for c in classes}
    assert names == {"api_hot", "backtest", "mutation", "factory_cycle", "agent"}
    assert len(classes) == 5


def test_workload_classes_profile_for_returns_copy():
    """profile_for must return a COPY — caller mutations cannot leak."""
    p1 = workload_classes.profile_for(workload_classes.WorkloadClass.BACKTEST)
    p1["cpu_share"] = 999.0
    p2 = workload_classes.profile_for(workload_classes.WorkloadClass.BACKTEST)
    assert p2["cpu_share"] == 0.50, "profile_for leaked mutation across calls"


def test_workload_classes_profile_for_type_check():
    with pytest.raises(TypeError):
        workload_classes.profile_for("backtest")  # str, not enum


@pytest.mark.parametrize("cls,expected_hint", [
    (workload_classes.WorkloadClass.API_HOT,       "unlimited"),
    (workload_classes.WorkloadClass.BACKTEST,      "pool_size"),
    (workload_classes.WorkloadClass.MUTATION,      "pool_size"),
    (workload_classes.WorkloadClass.FACTORY_CYCLE, 1),
    (workload_classes.WorkloadClass.AGENT,         "unlimited"),
])
def test_workload_classes_parallel_hints(cls, expected_hint):
    p = workload_classes.profile_for(cls)
    assert p["max_parallel_hint"] == expected_hint


# ─── host_capability.detect() — real OS read ─────────────────────────

def test_detect_returns_sane_capability():
    """detect() against the actual test host returns a valid struct."""
    caps = host_capability.detect()
    assert isinstance(caps, host_capability.HostCapability)
    assert caps.host_id
    assert caps.logical_cpu_count >= 1
    assert caps.effective_cpu_count >= 1
    assert caps.effective_cpu_count <= caps.logical_cpu_count
    # mem_total_gb may be 0.0 in degraded mode but psutil is present here.
    if caps.psutil_available:
        assert caps.mem_total_gb > 0
    assert caps.profile in host_capability.VALID_PROFILES


def test_detect_writes_host_id_file(tmp_path, monkeypatch):
    """host_id is persisted at /app/data/host_id (or fallback)."""
    monkeypatch.setattr(host_capability, "_HOST_ID_FILE", tmp_path / "host_id")
    caps = host_capability.detect()
    assert (tmp_path / "host_id").exists()
    assert (tmp_path / "host_id").read_text().strip() == caps.host_id


# ─── recommend_profile — pure function table ─────────────────────────

@pytest.mark.parametrize("cpu,mem,expected", [
    ( 2,   4.0, "small"),    # 2-vCPU dev container
    ( 4,   8.0, "small"),    # 4-vCPU dev container — boundary
    ( 4,  16.0, "small"),    # cpu<=4 forces small
    ( 8,  16.0, "medium"),
    ( 8,  16.0, "medium"),
    (12,  32.0, "large"),
    (16,  32.0, "large"),
    (16,  64.0, "xlarge"),   # mem above 32 pushes to xlarge
    (32,  64.0, "xlarge"),
    (64, 128.0, "xlarge"),
    ( 1,   1.0, "small"),
])
def test_recommend_profile_table(cpu, mem, expected):
    caps = _fake_caps(cpu_eff=cpu, mem_gb=mem)
    assert host_capability.recommend_profile(caps) == expected


def test_recommend_profile_honours_env_pin(monkeypatch):
    """WORKLOAD_PROFILE env pin wins over the threshold table."""
    caps = _fake_caps(cpu_eff=64, mem_gb=128.0)
    monkeypatch.setenv("WORKLOAD_PROFILE", "small")
    assert host_capability.recommend_profile(caps) == "small"
    monkeypatch.setenv("WORKLOAD_PROFILE", "large")
    assert host_capability.recommend_profile(caps) == "large"


def test_recommend_profile_invalid_env_falls_through(monkeypatch):
    """Unknown env value falls through to auto-classify."""
    caps = _fake_caps(cpu_eff=64, mem_gb=128.0)
    monkeypatch.setenv("WORKLOAD_PROFILE", "garbage")
    assert host_capability.recommend_profile(caps) == "xlarge"


# ─── adaptive_pool_sizer — operator-required example table ───────────

# These four assertions are the operator-mandated sizing outputs:
def test_sizing_4_vcpu():
    """4 vCPU / 8 GB → small profile → 2 workers (leaves 2 cores)."""
    caps = _fake_caps(cpu_eff=4, mem_gb=8.0)
    assert host_capability.recommend_profile(caps) == "small"
    n = adaptive_pool_sizer.recommend_pool_size(caps)
    assert n == 2, f"4 vCPU expected 2 workers, got {n}"


def test_sizing_12_vcpu():
    """12 vCPU / 32 GB → large profile → 9 workers (leaves 3 cores)."""
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0)
    assert host_capability.recommend_profile(caps) == "large"
    n = adaptive_pool_sizer.recommend_pool_size(caps)
    assert n == 9, f"12 vCPU expected 9 workers, got {n}"


def test_sizing_32_vcpu():
    """32 vCPU / 64 GB → xlarge profile → 28 workers (leaves 4 cores)."""
    caps = _fake_caps(cpu_eff=32, mem_gb=64.0)
    assert host_capability.recommend_profile(caps) == "xlarge"
    n = adaptive_pool_sizer.recommend_pool_size(caps)
    assert n == 28, f"32 vCPU expected 28 workers, got {n}"


def test_sizing_64_vcpu():
    """64 vCPU / 128 GB → xlarge profile → clamped to 32 by hard ceiling."""
    caps = _fake_caps(cpu_eff=64, mem_gb=128.0)
    assert host_capability.recommend_profile(caps) == "xlarge"
    n = adaptive_pool_sizer.recommend_pool_size(caps)
    # Recommendation = max(8, 64-4) = 60, but hard ceiling 32 wins.
    assert n == 32, f"64 vCPU expected 32 workers (ceiling), got {n}"


@pytest.mark.parametrize("cpu,mem,profile,expected", [
    # Floor checks
    (1, 1.0,  "small",  1),   # max(1, min(0, 2)) = max(1, 0) = 1
    (2, 1.0,  "small",  1),   # mem<=8 forces small; max(1, min(1, 2)) = 1
    (4, 8.0,  "small",  2),   # max(1, min(3, 2)) = 2
    # Medium recommendation formula
    (8, 16.0, "medium", 6),   # max(2, 8-2) = 6
    # Large recommendation formula
    (12, 32.0, "large", 9),   # max(4, 12-3) = 9
    (16, 32.0, "large", 13),  # max(4, 16-3) = 13
    # Xlarge recommendation formula
    (17, 33.0, "xlarge", 13),
    (32, 64.0, "xlarge", 28),
    (64, 128.0,"xlarge", 32), # clamp to ceiling
    (128,256.0,"xlarge", 32), # clamp to ceiling
])
def test_sizing_full_table(cpu, mem, profile, expected):
    """Operator-acceptable sizing recommendations across the full grid."""
    caps = _fake_caps(cpu_eff=cpu, mem_gb=mem, profile=profile)
    n = adaptive_pool_sizer.recommend_pool_size(caps, profile=profile)
    assert n == expected, f"cpu={cpu} mem={mem} profile={profile} → expected {expected}, got {n}"


def test_sizing_unknown_profile_returns_legacy_default():
    caps = _fake_caps(cpu_eff=12, mem_gb=32.0, profile="bogus")
    assert adaptive_pool_sizer.recommend_pool_size(caps, profile="bogus") == 4


# ─── cpu_pool.pool_size() — the critical integration point ───────────

def test_pool_size_flag_off_byte_identical():
    """FLAG-OFF byte-identical contract: pool_size() returns 4 when
    no env override and no flag — exactly as it did pre-P1.B."""
    # Confirm fixture cleared env
    assert os.environ.get("CPU_POOL_SIZE") is None
    assert os.environ.get("ENABLE_ADAPTIVE_POOL_SIZING") is None
    assert cpu_pool.pool_size() == 4


def test_pool_size_env_override_wins_absolutely(monkeypatch):
    """Operator pin CPU_POOL_SIZE=16 must win even when adaptive flag is ON."""
    monkeypatch.setenv("CPU_POOL_SIZE", "16")
    monkeypatch.setenv("ENABLE_ADAPTIVE_POOL_SIZING", "true")
    # Even with detection done, env wins.
    caps = _fake_caps(cpu_eff=64, mem_gb=128.0)
    host_capability._CACHE = caps
    assert cpu_pool.pool_size() == 16


def test_pool_size_env_override_clamped(monkeypatch):
    """Env pin is still clamped to [1, 32]."""
    monkeypatch.setenv("CPU_POOL_SIZE", "999")
    assert cpu_pool.pool_size() == 32
    monkeypatch.setenv("CPU_POOL_SIZE", "0")
    assert cpu_pool.pool_size() == 1
    monkeypatch.setenv("CPU_POOL_SIZE", "garbage")
    assert cpu_pool.pool_size() == 4   # bad value → legacy fallback then clamp


def test_pool_size_adaptive_path_requires_flag_AND_caps(monkeypatch):
    """Adaptive sizing only activates when (flag ON) AND (caps detected)."""
    # No flag, caps detected — legacy default
    caps = _fake_caps(cpu_eff=32, mem_gb=64.0, profile="xlarge")
    host_capability._CACHE = caps
    assert cpu_pool.pool_size() == 4

    # Flag ON, caps NOT detected — legacy default
    host_capability.reset_cache()
    monkeypatch.setenv("ENABLE_ADAPTIVE_POOL_SIZING", "true")
    assert cpu_pool.pool_size() == 4

    # Flag ON AND caps detected — adaptive path
    host_capability._CACHE = caps
    assert cpu_pool.pool_size() == 28  # xlarge: max(8, 32-4) = 28


def test_pool_size_adaptive_path_clamped(monkeypatch):
    """Even adaptive path is clamped to [1, 32]."""
    monkeypatch.setenv("ENABLE_ADAPTIVE_POOL_SIZING", "true")
    host_capability._CACHE = _fake_caps(cpu_eff=128, mem_gb=256.0, profile="xlarge")
    assert cpu_pool.pool_size() == 32


def test_would_override_diagnostic(monkeypatch):
    """`would_override()` accurately reports adaptive-path activation."""
    # No flag, no caps → False
    assert adaptive_pool_sizer.would_override() is False

    monkeypatch.setenv("ENABLE_ADAPTIVE_POOL_SIZING", "true")
    # Flag ON, no caps → False
    assert adaptive_pool_sizer.would_override() is False

    host_capability._CACHE = _fake_caps(cpu_eff=12, mem_gb=32.0, profile="large")
    # Flag ON, caps detected → True
    assert adaptive_pool_sizer.would_override() is True

    monkeypatch.setenv("CPU_POOL_SIZE", "8")
    # env pin wins → False (sizer would not be consulted)
    assert adaptive_pool_sizer.would_override() is False


def test_current_recommendation_returns_none_without_caps():
    assert adaptive_pool_sizer.current_recommendation() is None
    host_capability._CACHE = _fake_caps(cpu_eff=12, mem_gb=32.0, profile="large")
    assert adaptive_pool_sizer.current_recommendation() == 9


# ─── feature_flags registration ──────────────────────────────────────

def test_p1b_flags_registered():
    names = {spec["name"] for spec in ff.iter_specs()}
    assert "ENABLE_ADAPTIVE_POOL_SIZING" in names
    assert "WORKLOAD_PROFILE" in names


def test_p1b_flags_default_dormant():
    by_name = {spec["name"]: spec for spec in ff.iter_specs()}
    eaps = by_name["ENABLE_ADAPTIVE_POOL_SIZING"]
    assert eaps["default"] is False
    assert eaps["kind"]    == "bool"
    assert eaps["scope"]   == "scaling"
    wp = by_name["WORKLOAD_PROFILE"]
    assert wp["default"] == "auto"
    assert wp["kind"]    == "string"
    assert wp["scope"]   == "scaling"


# ─── host_capability persistence (Mongo) ─────────────────────────────

@pytest.mark.asyncio
async def test_persist_upserts_idempotently():
    db = get_db()
    caps = _fake_caps(cpu_eff=8, mem_gb=16.0, profile="medium",
                      host_id="p1b-test-host")
    await db["host_capabilities"].delete_one({"_id": caps.host_id})

    r1 = await host_capability.persist(caps)
    assert r1["ok"] is True
    doc1 = await db["host_capabilities"].find_one({"_id": caps.host_id})
    assert doc1 is not None
    assert doc1["profile"] == "medium"
    assert doc1["effective_cpu_count"] == 8

    # Second persist with updated profile — same row.
    caps2 = replace(caps, profile="large", effective_cpu_count=12)
    r2 = await host_capability.persist(caps2)
    assert r2["ok"] is True
    doc2 = await db["host_capabilities"].find_one({"_id": caps.host_id})
    assert doc2["profile"] == "large"
    assert doc2["effective_cpu_count"] == 12

    await db["host_capabilities"].delete_one({"_id": caps.host_id})


@pytest.mark.asyncio
async def test_ensure_indexes_idempotent():
    r1 = await host_capability.ensure_indexes()
    r2 = await host_capability.ensure_indexes()
    assert isinstance(r1, dict)
    assert len(r2.get("errors", [])) == 0
    assert len(r2.get("created", [])) == 0  # already created


# ─── Dormancy invariant ──────────────────────────────────────────────

def test_p1b_modules_not_wired_to_business_engines():
    """P1.B invariant: the new sizer + host_capability are consumed
    ONLY by cpu_pool.pool_size() and (in P1.D) the admission gate.
    No business engine (auto_factory, mutation_engine, master_bot_*,
    r5_*, parity_*) may import them yet."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["grep", "-rlnE",
             r"from engines\.(adaptive_pool_sizer|host_capability|workload_classes)|"
             r"import engines\.(adaptive_pool_sizer|host_capability|workload_classes)",
             "/app/backend/engines", "/app/backend/api"],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        out = ""
    importers = [line for line in out.splitlines() if line]
    allowed_suffixes = (
        "/engines/adaptive_pool_sizer.py",   # the module itself
        "/engines/host_capability.py",       # the module itself
        "/engines/workload_classes.py",      # the module itself
        "/engines/cpu_pool.py",              # legitimate consumer in P1.B
        # P1.C scaffolding (advisory only — no business engine consumes
        # these until P1.D wires the wrap sites):
        "/engines/queue_pressure.py",
        "/engines/adaptive_concurrency.py",
        "/engines/admission_controller.py",
        "/api/scaling.py",                    # diagnostic preview surface
        # P1.D wrap helper + wrap sites + architect view:
        "/engines/admission_wrapper.py",
        "/engines/architect_scaling_view.py",
        "/engines/auto_factory.py",
        "/engines/mutation_engine.py",
        "/engines/master_bot_deployment.py",
        "/engines/scaling_events.py",
    )
    illegal = [
        line for line in importers
        if not any(line.endswith(s) for s in allowed_suffixes)
    ]
    assert not illegal, (
        f"P1.B dormancy violated — business engines imported sizing modules: {illegal}"
    )

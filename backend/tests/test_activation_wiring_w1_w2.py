"""Regression coverage for Coherent UKIE Activation W1 + W2 wiring.

Freeze-permitted operational wiring landed 2026-07-20:
  * W1 — TTL specs in `engines/db_indexes.py` for the five Stage-4
    audit collections (workload_dead_letter + 4 KB collections).
  * W2 — Aggregator wiring: 5 retrofit providers auto-register with
    the sync `collect_all()`; UKIE provider composed inside async
    `system_health()` under the `ukie` top-level key when its flag is
    on.

Tests here are pure, in-memory, and side-effect-free.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any, Dict, List


# Ensure the legacy engines path is importable irrespective of test cwd.
_LEGACY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "legacy",
)
if _LEGACY_PATH not in sys.path:
    sys.path.insert(0, _LEGACY_PATH)


# ────────────────────────────────────────────────────────────────────
# W1 — TTL specs
# ────────────────────────────────────────────────────────────────────

def test_w1_workload_dead_letter_ttl_declared():
    """`workload_dead_letter` has a 90d TTL spec in the main DB list."""
    from engines.db_indexes import TTL_SPECS

    names = [name for _, _, _, name in TTL_SPECS]
    assert "ttl_workload_dead_letter" in names

    for coll, field, ttl_sec, name in TTL_SPECS:
        if name == "ttl_workload_dead_letter":
            assert coll == "workload_dead_letter"
            assert field == "first_failed_at_dt", "must target *_dt companion (BSON Date)"
            assert ttl_sec == 90 * 86400
            return


def test_w1_kb_ttl_specs_declared():
    """The four UKIE-KB audit collections have TTL specs."""
    from engines.db_indexes import KB_TTL_SPECS

    expected = {
        "lifecycle_events": (180, "at_dt", "ttl_lifecycle_events"),
        "knowledge_endorsement_events": (90, "at_dt", "ttl_knowledge_endorsement_events"),
        "knowledge_contradiction_events": (365, "at_dt", "ttl_knowledge_contradiction_events"),
        "connector_events": (180, "at_dt", "ttl_connector_events"),
    }

    seen: Dict[str, Any] = {}
    for coll, field, ttl_sec, name in KB_TTL_SPECS:
        seen[coll] = (ttl_sec // 86400, field, name)

    for coll, exp in expected.items():
        assert coll in seen, f"missing KB TTL for {coll}"
        assert seen[coll] == exp, f"{coll}: expected {exp}, got {seen[coll]}"


def test_w1_env_override_honoured(monkeypatch):
    """Env overrides for the new TTL_DAYS constants are respected on re-import."""
    monkeypatch.setenv("COE_DEAD_LETTER_TTL_DAYS", "7")
    monkeypatch.setenv("UKIE_LIFECYCLE_EVENTS_TTL_DAYS", "1")

    if "engines.db_indexes" in sys.modules:
        importlib.reload(sys.modules["engines.db_indexes"])
    import engines.db_indexes as di  # type: ignore

    assert di.COE_DEAD_LETTER_TTL_DAYS == 7
    assert di.UKIE_LIFECYCLE_EVENTS_TTL_DAYS == 1


# ────────────────────────────────────────────────────────────────────
# W2 — Aggregator wiring
# ────────────────────────────────────────────────────────────────────

RETROFIT_NAMES: List[str] = [
    "meta-learning", "mi", "execution", "portfolio", "factory-eval",
]

RETROFIT_FLAGS: List[str] = [
    "META_LEARNING_HEALTH_PROVIDER_ENABLED",
    "MI_HEALTH_PROVIDER_ENABLED",
    "EXECUTION_HEALTH_PROVIDER_ENABLED",
    "PORTFOLIO_HEALTH_PROVIDER_ENABLED",
    "FACTORY_EVAL_HEALTH_PROVIDER_ENABLED",
]


def _clear_retrofit_flags(monkeypatch):
    for f in RETROFIT_FLAGS:
        monkeypatch.delenv(f, raising=False)


def test_w2_retrofit_providers_auto_register(monkeypatch):
    """Importing `subsystem_health_router` registers 5 retrofit providers."""
    _clear_retrofit_flags(monkeypatch)

    # Import (or reload) triggers registration.
    if "engines.subsystem_health_router" in sys.modules:
        importlib.reload(sys.modules["engines.subsystem_health_router"])
    else:
        import engines.subsystem_health_router  # noqa: F401

    from engines.health.providers import all_provider_names

    registered = set(all_provider_names())
    for name in RETROFIT_NAMES:
        assert name in registered, f"retrofit {name!r} not registered"


def test_w2_dormant_snapshot_when_flag_off(monkeypatch):
    """Retrofit provider with flag OFF returns dormant HealthSnapshot."""
    _clear_retrofit_flags(monkeypatch)
    if "engines.subsystem_health_router" in sys.modules:
        importlib.reload(sys.modules["engines.subsystem_health_router"])
    else:
        import engines.subsystem_health_router  # noqa: F401

    from engines.health.providers import collect_all

    by_name = {s["subsystem"]: s for s in collect_all()}
    for name in RETROFIT_NAMES:
        s = by_name[name]
        assert s["health_score"] == 100, f"{name}: expected 100, got {s['health_score']}"
        assert s["recovery_status"]["state"] == "ok"
        assert s["recovery_status"]["reason"] == "dormant"
        assert s["recovery_status"]["action_required"] == "none"


def test_w2_opted_in_snapshot_when_flag_on(monkeypatch):
    """Retrofit provider with flag ON returns opted-in HealthSnapshot."""
    _clear_retrofit_flags(monkeypatch)
    monkeypatch.setenv("MI_HEALTH_PROVIDER_ENABLED", "true")
    if "engines.subsystem_health_router" in sys.modules:
        importlib.reload(sys.modules["engines.subsystem_health_router"])
    else:
        import engines.subsystem_health_router  # noqa: F401

    from engines.health.providers import collect_all

    by_name = {s["subsystem"]: s for s in collect_all()}
    assert by_name["mi"]["recovery_status"]["reason"] == "opted_in"
    # Non-toggled retrofits stay dormant.
    for name in ("meta-learning", "execution", "portfolio", "factory-eval"):
        assert by_name[name]["recovery_status"]["reason"] == "dormant"


def test_w2_ukie_block_omitted_when_flag_off(monkeypatch):
    """`/api/health/system` MUST NOT include a `ukie` key when flag is off.

    Preserves the "no shape change to pre-Stage-4 consumers" invariant.
    """
    _clear_retrofit_flags(monkeypatch)
    monkeypatch.delenv("UKIE_HEALTH_PROVIDER_ENABLED", raising=False)
    monkeypatch.setenv("COE_HEALTH_CONTRACT_ENABLED", "true")

    if "engines.subsystem_health_router" in sys.modules:
        importlib.reload(sys.modules["engines.subsystem_health_router"])
    else:
        import engines.subsystem_health_router  # noqa: F401

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from engines.health.router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.get("/api/health/system")
    assert r.status_code == 200
    payload = r.json()
    assert "subsystems" in payload
    assert "ukie" not in payload, "ukie key must NOT be present when flag off"


def test_w2_health_contract_off_returns_503(monkeypatch):
    """Aggregator itself still respects the master flag."""
    monkeypatch.setenv("COE_HEALTH_CONTRACT_ENABLED", "false")
    monkeypatch.setenv("UKIE_HEALTH_PROVIDER_ENABLED", "true")

    if "engines.subsystem_health_router" in sys.modules:
        importlib.reload(sys.modules["engines.subsystem_health_router"])
    else:
        import engines.subsystem_health_router  # noqa: F401

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from engines.health.router import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    r = client.get("/api/health/system")
    assert r.status_code == 503

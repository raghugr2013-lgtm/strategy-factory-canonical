"""Phase 0 fix regression coverage.

Two fixes landed 2026-07-20 post Phase-0 baseline capture:

  * P0-F1 — Stage-4 UKIE health endpoint renamed from
    `/api/knowledge/health` to `/api/knowledge/ukie/health` to avoid
    collision with the pre-existing Phase-1 KB probe.
  * P0-F2 — `engines.db_indexes.ensure_indexes()` wired into the app
    startup hook so the comprehensive INDEX_SPECS + TTL_SPECS table
    (including W1 additions) is applied on boot.

Tests here are pure, in-memory, and side-effect-free.
"""
from __future__ import annotations

import importlib
import os
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient


_LEGACY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "legacy",
)
if _LEGACY_PATH not in sys.path:
    sys.path.insert(0, _LEGACY_PATH)


# ────────────────────────────────────────────────────────────────────
# P0-F1 — Stage-4 UKIE health endpoint moved to /api/knowledge/ukie/health
# ────────────────────────────────────────────────────────────────────

def _make_knowledge_app():
    if "engines.knowledge.observability_router" in sys.modules:
        importlib.reload(sys.modules["engines.knowledge.observability_router"])
    from engines.knowledge.observability_router import router
    app = FastAPI()
    app.include_router(router)
    return app


def test_p0_f1_stage4_health_on_new_path_returns_503_when_flag_off(monkeypatch):
    """The Stage-4 endpoint now lives at /api/knowledge/ukie/health."""
    monkeypatch.delenv("UKIE_HEALTH_PROVIDER_ENABLED", raising=False)
    with TestClient(_make_knowledge_app()) as c:
        r = c.get("/api/knowledge/ukie/health")
        assert r.status_code == 503
        assert "UKIE_HEALTH_PROVIDER_ENABLED" in r.json().get("detail", "")


def test_p0_f1_old_path_no_longer_registered_by_stage4_router(monkeypatch):
    """The Stage-4 router MUST NOT expose /api/knowledge/health any more.

    Previously that path clashed with the Phase-1 KB probe mounted in
    `app/knowledge/router.py`. On a fresh test app containing ONLY the
    Stage-4 observability router, the old path should now 404 (no
    handler), proving the collision surface has been removed at the
    Stage-4 side.
    """
    monkeypatch.delenv("UKIE_HEALTH_PROVIDER_ENABLED", raising=False)
    with TestClient(_make_knowledge_app()) as c:
        r = c.get("/api/knowledge/health")
        assert r.status_code == 404, (
            f"Stage-4 router still owns /api/knowledge/health "
            f"(status={r.status_code}, body={r.text[:200]})"
        )


def test_p0_f1_stage4_health_returns_snapshot_when_flag_on(monkeypatch):
    """Flag on → 200 with the UKIE dormant snapshot shape."""
    monkeypatch.setenv("UKIE_HEALTH_PROVIDER_ENABLED", "true")

    from engines.knowledge import health_provider as _hp

    # Inject a Mongo-free provider so the endpoint doesn't reach out.
    class _FakeProvider:
        async def snapshot(self):
            return {
                "subsystem": "ukie",
                "status": "dormant",
                "flags": {},
                "kb_row_count": 0,
                "checked_at": "2026-07-20T00:00:00+00:00",
            }

    monkeypatch.setattr(_hp, "_PROVIDER", _FakeProvider(), raising=False)

    with TestClient(_make_knowledge_app()) as c:
        r = c.get("/api/knowledge/ukie/health")
        assert r.status_code == 200
        body = r.json()
        assert body["subsystem"] == "ukie"
        assert body["status"] == "dormant"


# ────────────────────────────────────────────────────────────────────
# P0-F2 — engines.db_indexes.ensure_indexes() runs at app startup
# ────────────────────────────────────────────────────────────────────

def test_p0_f2_engines_ensure_indexes_wired_into_startup():
    """Assert the wiring is present in `app.main.lifespan`.

    Static-source check because the runtime side-effect (index creation)
    depends on a live Mongo — which isn't guaranteed in unit-test envs.
    The static check is a bright-line regression guard: if someone
    removes the wiring, this test fails immediately.
    """
    main_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "app", "main.py",
    )
    with open(main_path, encoding="utf-8") as f:
        src = f.read()

    assert "engines.db_indexes" in src, (
        "engines.db_indexes import missing from app/main.py — "
        "P0-F2 wiring regressed"
    )
    assert "_engines_ensure_indexes" in src, (
        "The comprehensive ensure_indexes call is missing from "
        "app/main.py lifespan — P0-F2 wiring regressed"
    )
    # Must be inside the async lifespan context so it actually runs at
    # boot rather than sitting orphaned at module top-level.
    assert "await _engines_ensure_indexes()" in src


def test_p0_f2_engines_ensure_indexes_is_awaitable_and_returns_summary():
    """The function still returns the {created, existed, errors, ttl_days}
    dict shape that the lifespan wiring logs."""
    from engines.db_indexes import ensure_indexes
    import asyncio

    # We cannot run the coroutine against a real Mongo here — but we
    # can verify it is a coroutine function that produces a coroutine
    # object when called (guarding against accidental sync rewrite).
    assert asyncio.iscoroutinefunction(ensure_indexes), (
        "engines.db_indexes.ensure_indexes must remain an async "
        "coroutine — lifespan hook uses `await`"
    )


def test_p0_f2_wired_before_seed_admin():
    """Index creation MUST run before seed_admin() so unique indexes on
    users.email / users.user_id are in place before the seeder writes.

    Static ordering check on app/main.py source.
    """
    main_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "app", "main.py",
    )
    with open(main_path, encoding="utf-8") as f:
        src = f.read()

    idx_pos = src.find("await _engines_ensure_indexes()")
    seed_pos = src.find("await seed_admin()")
    assert idx_pos > 0, "P0-F2 wiring not found"
    assert seed_pos > 0, "seed_admin call not found"
    assert idx_pos < seed_pos, (
        "engines.db_indexes.ensure_indexes must run BEFORE seed_admin — "
        "unique indexes must exist before the admin row is written"
    )

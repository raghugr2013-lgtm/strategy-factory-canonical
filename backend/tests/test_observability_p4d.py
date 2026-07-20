"""Phase 2 Stage 4 P4D — Observability finalisation tests.

Covers:
  * UkieHealthProvider — flag off / on, snapshot shape, KB counts
  * KnowledgeMetrics — flag off / on, per-domain aggregation
  * Audit visibility endpoints — 503 when off, paged list when on
  * Subsystem HealthSnapshot retrofits — 503 when off, snapshot when on
  * Connector-event snapshot helper
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.health_provider import (  # noqa: E402
    UkieHealthProvider, _TRACKED_FLAGS,
)
from engines.knowledge.metrics import KnowledgeMetrics  # noqa: E402
from engines.knowledge.connector_health import (  # noqa: E402
    ConnectorObserver, ConnectorState,
    snapshot_observation_for_persistence,
)


# ── Fake Mongo ───────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._skip = 0
        self._limit = None
        self._sort = None
    def sort(self, field, direction=1):
        self._sort = (field, direction)
        return self
    def skip(self, n):
        self._skip = n
        return self
    def limit(self, n):
        self._limit = n
        return self
    def __aiter__(self):
        rows = list(self._rows)
        if self._sort:
            f, d = self._sort
            rows.sort(key=lambda r: r.get(f, ""), reverse=(d < 0))
        rows = rows[self._skip:]
        if self._limit is not None:
            rows = rows[:self._limit]
        self._it = iter(rows)
        return self
    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, name):
        self.name = name
        self._docs: List[Dict[str, Any]] = []
    def find(self, q=None):
        q = q or {}
        def _m(d):
            for k, v in q.items():
                if isinstance(v, dict) and "$gte" in v:
                    got = d.get(k)
                    if not (got is not None and got >= v["$gte"]): return False
                elif d.get(k) != v:
                    return False
            return True
        return _Cursor([d for d in self._docs if _m(d)])
    async def count_documents(self, q=None):
        q = q or {}
        def _get(d, k):
            if "." in k:
                parts = k.split(".")
                cur: Any = d
                for p in parts:
                    if not isinstance(cur, dict):
                        return None
                    cur = cur.get(p)
                return cur
            return d.get(k)
        def _m(d):
            for k, v in q.items():
                got = _get(d, k)
                if isinstance(v, dict) and "$gte" in v:
                    if not (got is not None and got >= v["$gte"]): return False
                elif got != v:
                    return False
            return True
        return sum(1 for d in self._docs if _m(d))


class _FakeDB:
    def __init__(self):
        self._c: Dict[str, _Coll] = {}
    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = _Coll(name)
        return self._c[name]


# ── UkieHealthProvider ───────────────────────────────────────────────

class TestUkieHealthProvider:
    @pytest.mark.asyncio
    async def test_flag_off_returns_none(self, monkeypatch):
        monkeypatch.delenv("UKIE_HEALTH_PROVIDER_ENABLED", raising=False)
        p = UkieHealthProvider(kb_db_getter=lambda: _FakeDB())
        assert await p.snapshot() is None

    @pytest.mark.asyncio
    async def test_snapshot_shape(self, monkeypatch):
        monkeypatch.setenv("UKIE_HEALTH_PROVIDER_ENABLED", "true")
        db = _FakeDB()
        # Seed a couple of KB rows
        db["strategies"]._docs.append({"_id": "s1", "domain": "strategy"})
        db["research"]._docs.append({"_id": "r1", "domain": "research"})
        p = UkieHealthProvider(kb_db_getter=lambda: db)
        snap = await p.snapshot()
        assert snap["subsystem"] == "ukie"
        assert snap["kb_row_count"] == 2
        assert snap["kb_row_count_per_domain"]["strategy"] == 1
        assert snap["kb_row_count_per_domain"]["research"] == 1
        # every tracked flag is present in the response
        for f in _TRACKED_FLAGS:
            assert f in snap["flags"]

    @pytest.mark.asyncio
    async def test_dormant_when_flags_off(self, monkeypatch):
        monkeypatch.setenv("UKIE_HEALTH_PROVIDER_ENABLED", "true")
        # Note: `UKIE_DOMAIN_REGISTRY_ENABLED` + `UKIE_GOVERNANCE_CUTOVER`
        # are the two most consequential markers; both off → dormant.
        monkeypatch.delenv("UKIE_DOMAIN_REGISTRY_ENABLED", raising=False)
        monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)
        p = UkieHealthProvider(kb_db_getter=lambda: _FakeDB())
        snap = await p.snapshot()
        assert snap["status"] == "dormant"


# ── KnowledgeMetrics ─────────────────────────────────────────────────

class TestKnowledgeMetrics:
    @pytest.mark.asyncio
    async def test_snapshot_aggregates(self, monkeypatch):
        db = _FakeDB()
        db["strategies"]._docs.append({
            "_id": "s1", "trust_tier": 5,
            "license_verdict": {"outcome": "permissive"},
        })
        db["research"]._docs.append({
            "_id": "r1", "trust_tier": 4,
            "license_verdict": {"outcome": "permissive"},
        })
        m = KnowledgeMetrics(kb_db_getter=lambda: db)
        s = await m.snapshot()
        assert s["status"] == "ok"
        assert s["rows_per_domain"]["strategy"] == 1
        assert s["rows_per_domain"]["research"] == 1
        assert s["trust_tier_distribution"]["T4"] == 1
        assert s["trust_tier_distribution"]["T5"] == 1
        assert s["license_outcome_distribution"]["permissive"] == 2

    @pytest.mark.asyncio
    async def test_db_unavailable_status(self):
        m = KnowledgeMetrics(kb_db_getter=lambda: None)
        s = await m.snapshot()
        assert s["status"] == "db_unavailable"


# ── Connector-event persistence helper ───────────────────────────────

class TestConnectorEventPersistence:
    def test_snapshot_shape(self):
        obs = ConnectorObserver()
        obs.note_success("arxiv")
        row = snapshot_observation_for_persistence("arxiv", obs.snapshot("arxiv"))
        assert row["connector"] == "arxiv"
        assert row["state"] == ConnectorState.HEALTHY.value
        assert row["last_success_at"]
        assert "at" in row


# ── Observability router ─────────────────────────────────────────────

def _make_knowledge_app():
    from engines.knowledge.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestObservabilityRouter:
    def test_health_endpoint_503_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_HEALTH_PROVIDER_ENABLED", raising=False)
        with TestClient(_make_knowledge_app()) as c:
            assert c.get("/api/knowledge/health").status_code == 503

    def test_metrics_endpoint_503_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_METRICS_ENABLED", raising=False)
        with TestClient(_make_knowledge_app()) as c:
            assert c.get("/api/knowledge/metrics").status_code == 503

    def test_audit_endpoints_503_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_AUDIT_VISIBILITY_ENABLED", raising=False)
        with TestClient(_make_knowledge_app()) as c:
            assert c.get("/api/knowledge/promote-events").status_code == 503
            assert c.get("/api/knowledge/retro-score-runs").status_code == 503
            assert c.get("/api/knowledge/connector-events").status_code == 503

    def test_metrics_endpoint_serves_when_on(self, monkeypatch):
        monkeypatch.setenv("UKIE_METRICS_ENABLED", "true")
        db = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.observability_router.get_knowledge_metrics",
            lambda: KnowledgeMetrics(kb_db_getter=lambda: db),
        )
        with TestClient(_make_knowledge_app()) as c:
            r = c.get("/api/knowledge/metrics")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            assert "rows_per_domain" in body

    def test_audit_endpoints_serve_when_on(self, monkeypatch):
        monkeypatch.setenv("UKIE_AUDIT_VISIBILITY_ENABLED", "true")
        db = _FakeDB()
        db["promote_events"]._docs.extend([
            {"attempted_at": "2025-01-01T00:00:00+00:00", "resolved": "promoted"},
            {"attempted_at": "2025-01-02T00:00:00+00:00", "resolved": "refused"},
        ])
        db["retro_score_runs"]._docs.append(
            {"started_at": "2025-01-01T00:00:00+00:00", "dry_run": True},
        )
        db["connector_events"]._docs.append(
            {"at": "2025-01-01T00:00:00+00:00", "connector": "arxiv", "state": "healthy"},
        )
        monkeypatch.setattr(
            "engines.knowledge.observability_router._get_kb_db",
            lambda: db,
        )
        with TestClient(_make_knowledge_app()) as c:
            r = c.get("/api/knowledge/promote-events")
            assert r.status_code == 200
            assert r.json()["count"] == 2
            r = c.get("/api/knowledge/promote-events?resolved=refused")
            assert r.json()["count"] == 1
            r = c.get("/api/knowledge/retro-score-runs?dry_run=true")
            assert r.json()["count"] == 1
            r = c.get("/api/knowledge/connector-events?connector=arxiv")
            assert r.json()["count"] == 1


# ── Subsystem HealthSnapshot retrofits ───────────────────────────────

def _make_subsystem_app():
    from engines.subsystem_health_router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestSubsystemHealthRetrofits:
    @pytest.mark.parametrize("path,flag", [
        ("/api/meta-learning/health", "META_LEARNING_HEALTH_PROVIDER_ENABLED"),
        ("/api/mi/health",            "MI_HEALTH_PROVIDER_ENABLED"),
        ("/api/execution/health",     "EXECUTION_HEALTH_PROVIDER_ENABLED"),
        ("/api/portfolio/health",     "PORTFOLIO_HEALTH_PROVIDER_ENABLED"),
        ("/api/factory-eval/health",  "FACTORY_EVAL_HEALTH_PROVIDER_ENABLED"),
    ])
    def test_503_when_off(self, monkeypatch, path, flag):
        monkeypatch.delenv(flag, raising=False)
        with TestClient(_make_subsystem_app()) as c:
            assert c.get(path).status_code == 503

    @pytest.mark.parametrize("path,flag", [
        ("/api/meta-learning/health", "META_LEARNING_HEALTH_PROVIDER_ENABLED"),
        ("/api/mi/health",            "MI_HEALTH_PROVIDER_ENABLED"),
        ("/api/execution/health",     "EXECUTION_HEALTH_PROVIDER_ENABLED"),
        ("/api/portfolio/health",     "PORTFOLIO_HEALTH_PROVIDER_ENABLED"),
        ("/api/factory-eval/health",  "FACTORY_EVAL_HEALTH_PROVIDER_ENABLED"),
    ])
    def test_snapshot_when_on(self, monkeypatch, path, flag):
        monkeypatch.setenv(flag, "true")
        with TestClient(_make_subsystem_app()) as c:
            r = c.get(path)
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "opted_in"
            assert body["flag_enabled"] is True
            assert body["flag_name"] == flag

"""Phase 2 Stage 4 — Connector scaffolding tests (P4A.0).

Covers:
  * `ConnectorAuth` — modes, redaction, config detection
  * `RetryPolicy` — status / exception decisions, backoff computation
  * `ConnectorObserver` — state transitions
  * `AbstractConnector` — flag gating, retry composition, health snapshot
  * `registry` — flag-aware filtering (framework off / on / per-connector)
  * connector-health router — 503 when off, snapshot when on
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import (  # noqa: E402
    ConnectorCapabilities, DiscoveryQuery, RateLimit, RawKnowledgeItem, Reference,
)
from engines.knowledge.connector_auth import (  # noqa: E402
    ApiKeyAuth, BearerAuth, NoAuth, OAuthClientCredentials,
)
from engines.knowledge.connector_health import (  # noqa: E402
    ConnectorObserver, ConnectorState, _reset_observer_for_tests,
)
from engines.knowledge.connector_retry import (  # noqa: E402
    CONNECTOR_DEFAULT, DEFAULT_RETRY_STATUSES, RetryPolicy,
)
from engines.knowledge.connectors.base import AbstractConnector  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge import registry  # noqa: E402


# ── Auth ─────────────────────────────────────────────────────────────

class TestAuth:
    def test_noauth_always_configured(self):
        a = NoAuth()
        assert a.is_configured() is True
        assert a.headers() == {}
        assert "NoAuth" in repr(a)

    def test_apikey_optional_default_configured(self, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        a = ApiKeyAuth(env_var="MY_KEY", required=False)
        assert a.is_configured() is True
        assert a.headers() == {}

    def test_apikey_required_missing(self, monkeypatch):
        monkeypatch.delenv("MY_KEY", raising=False)
        a = ApiKeyAuth(env_var="MY_KEY", required=True)
        assert a.is_configured() is False

    def test_apikey_present_adds_header(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "super-secret-123")
        a = ApiKeyAuth(env_var="MY_KEY", required=True, header_name="X-Custom")
        assert a.is_configured() is True
        assert a.headers() == {"X-Custom": "super-secret-123"}
        # Redaction — secret must not appear in repr
        assert "super-secret" not in repr(a)
        # Nor in the health dict
        h = a.to_health_dict()
        assert "super-secret" not in str(h)

    def test_bearer_configuration(self, monkeypatch):
        monkeypatch.setenv("TOK", "abc")
        a = BearerAuth(env_var="TOK")
        assert a.is_configured() is True
        assert a.headers() == {"Authorization": "Bearer abc"}
        assert "abc" not in repr(a)

    def test_oauth_configuration(self, monkeypatch):
        monkeypatch.delenv("CID", raising=False)
        monkeypatch.delenv("CSC", raising=False)
        a = OAuthClientCredentials(
            client_id_env="CID", client_secret_env="CSC",
            token_url="https://example.com/token", required=True,
        )
        assert a.is_configured() is False
        monkeypatch.setenv("CID", "x")
        monkeypatch.setenv("CSC", "y")
        assert a.is_configured() is True
        # headers() returns {} for oauth — token fetch is deferred
        assert a.headers() == {}


# ── Retry policy ─────────────────────────────────────────────────────

class TestRetry:
    def test_default_statuses(self):
        assert 429 in DEFAULT_RETRY_STATUSES
        assert 500 not in DEFAULT_RETRY_STATUSES

    def test_should_retry_on_status(self):
        p = CONNECTOR_DEFAULT
        assert p.should_retry_on_status(429) is True
        assert p.should_retry_on_status(500) is False

    def test_should_retry_on_exc(self):
        p = RetryPolicy(retry_on_exc=(TimeoutError,))
        assert p.should_retry_on_exc(TimeoutError()) is True
        assert p.should_retry_on_exc(ValueError()) is False

    def test_compute_delay_deterministic(self):
        p = RetryPolicy(base_delay_s=2.0, max_delay_s=60.0, jitter="none")
        assert p.compute_delay(0) == 2.0
        assert p.compute_delay(1) == 4.0
        assert p.compute_delay(10) == 60.0  # capped

    def test_compute_delay_honours_429_floor(self):
        p = RetryPolicy(base_delay_s=2.0, max_delay_s=60.0,
                        jitter="none", cool_off_on_429_s=45.0)
        assert p.compute_delay(0, last_status=429) == 45.0

    def test_jitter_bounds(self):
        p = RetryPolicy(base_delay_s=2.0, max_delay_s=8.0, jitter="full")
        for _ in range(20):
            d = p.compute_delay(1)
            assert 0.0 <= d <= 4.0  # exp = 4, no floor


# ── Observer ─────────────────────────────────────────────────────────

class TestObserver:
    def test_success_transitions_to_healthy(self):
        _reset_observer_for_tests()
        obs = ConnectorObserver()
        obs.note_success("x")
        assert obs.snapshot("x").state == ConnectorState.HEALTHY

    def test_failure_progression(self):
        obs = ConnectorObserver()
        obs.note_success("x")
        obs.note_failure("x", "boom")
        assert obs.snapshot("x").state == ConnectorState.DEGRADED
        obs.note_failure("x", "boom again")
        assert obs.snapshot("x").state == ConnectorState.FAILING

    def test_rate_limit_moves_to_cooling(self):
        obs = ConnectorObserver()
        obs.note_success("x")
        obs.note_rate_limit("x", "2025-01-01T00:00:00+00:00")
        assert obs.snapshot("x").state == ConnectorState.COOLING

    def test_flag_off_marks_dormant(self):
        obs = ConnectorObserver()
        obs.note_flag_state("x", False)
        assert obs.snapshot("x").state == ConnectorState.DORMANT
        obs.note_flag_state("x", True)
        assert obs.snapshot("x").state == ConnectorState.OPTED_IN


# ── AbstractConnector ────────────────────────────────────────────────

class _FakeConnector(AbstractConnector):
    name = "fake"
    source_type = "test"
    supported_domains = frozenset({KnowledgeDomain.STRATEGY})
    default_trust_tier = 3
    flag_name = "UKIE_CONNECTOR_FAKE_ENABLED"
    capabilities = ConnectorCapabilities(supports_discovery=True)


class TestAbstractConnector:
    def test_default_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_FAKE_ENABLED", raising=False)
        c = _FakeConnector()
        assert c.is_flag_enabled() is False
        assert c.is_available() is False

    def test_flag_on(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FAKE_ENABLED", "true")
        c = _FakeConnector()
        assert c.is_flag_enabled() is True

    def test_content_hash(self):
        assert AbstractConnector.content_hash(b"") == ""
        h = AbstractConnector.content_hash(b"hi")
        assert h.startswith("sha256:") and len(h) == 71

    def test_health_snapshot_shape(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FAKE_ENABLED", "true")
        c = _FakeConnector()
        snap = c.health_snapshot().to_dict()
        assert snap["name"] == "fake"
        assert snap["flag_enabled"] is True
        assert snap["auth_configured"] is True
        assert snap["auth_mode"] == "none"
        assert "strategy" in snap["supported_domains"]

    @pytest.mark.asyncio
    async def test_call_with_retry_succeeds_on_second_attempt(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FAKE_ENABLED", "true")
        c = _FakeConnector(retry=RetryPolicy(max_attempts=3, base_delay_s=0.001,
                                             max_delay_s=0.001, jitter="none"))
        calls = {"n": 0}

        async def _fn():
            calls["n"] += 1
            if calls["n"] == 1:
                return {"status": 503}
            return {"status": 200}

        out = await c._call_with_retry(_fn, on_status=lambda r: r["status"])
        assert out["status"] == 200
        assert calls["n"] == 2
        assert c.health_snapshot().state == ConnectorState.HEALTHY

    @pytest.mark.asyncio
    async def test_call_with_retry_gives_up_on_final_exc(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FAKE_ENABLED", "true")
        c = _FakeConnector(retry=RetryPolicy(max_attempts=2, base_delay_s=0.001,
                                             max_delay_s=0.001, jitter="none",
                                             retry_on_exc=(TimeoutError,)))

        async def _fn():
            raise TimeoutError("timeout")

        with pytest.raises(TimeoutError):
            await c._call_with_retry(_fn)
        assert c.health_snapshot().state == ConnectorState.DEGRADED


# ── Registry — flag-aware filtering ──────────────────────────────────

class TestRegistry:
    def test_framework_off_hides_stage4_connectors(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", raising=False)
        names = [c.name for c in registry.list_connectors()]
        # Legacy `github` remains visible; new connectors are hidden.
        assert "github" in names
        for n in ("arxiv", "pdf", "propfirm", "tradingview", "internal_mongo"):
            assert n not in names

    def test_per_connector_flag(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", "true")
        monkeypatch.setenv("UKIE_CONNECTOR_ARXIV_ENABLED", "true")
        monkeypatch.delenv("UKIE_CONNECTOR_PDF_ENABLED", raising=False)
        names = [c.name for c in registry.list_connectors()]
        assert "arxiv" in names
        assert "pdf" not in names

    def test_get_connector_respects_flag(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", raising=False)
        assert registry.get_connector("arxiv") is None
        monkeypatch.setenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", "true")
        monkeypatch.setenv("UKIE_CONNECTOR_ARXIV_ENABLED", "true")
        assert registry.get_connector("arxiv") is not None


# ── Connector-health router ──────────────────────────────────────────

def _make_app():
    from engines.knowledge.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestConnectorHealthRouter:
    def test_503_when_framework_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", raising=False)
        with TestClient(_make_app()) as c:
            r = c.get("/api/knowledge/connectors/health")
            assert r.status_code == 503
            r = c.get("/api/knowledge/connectors/arxiv/health")
            assert r.status_code == 503

    def test_snapshots_when_enabled(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", "true")
        monkeypatch.setenv("UKIE_CONNECTOR_ARXIV_ENABLED", "true")
        with TestClient(_make_app()) as c:
            r = c.get("/api/knowledge/connectors/health")
            assert r.status_code == 200
            names = [x["name"] for x in r.json()["connectors"]]
            assert "arxiv" in names

    def test_unknown_connector_404(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONNECTOR_FRAMEWORK_ENABLED", "true")
        with TestClient(_make_app()) as c:
            r = c.get("/api/knowledge/connectors/no-such-thing/health")
            assert r.status_code == 404

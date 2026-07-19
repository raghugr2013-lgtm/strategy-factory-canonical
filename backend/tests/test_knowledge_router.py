"""Phase 2, Stage 3.α — UKIE router tests.

Verifies:
  * All UKIE endpoints refuse with HTTP 503 when
    `UKIE_DOMAIN_REGISTRY_ENABLED` is off
  * `GET /api/knowledge/domains` returns all six domain specs
  * `GET /api/knowledge/domains/{domain}` returns one spec
  * `GET /api/knowledge/connectors` returns registered connectors
  * `GET /api/knowledge/connectors/{name}` returns one connector
  * `GET /api/knowledge/domains/{domain}/connectors` filters correctly
  * 404 on unknown domain / connector
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))


def _make_app():
    app = FastAPI()
    from engines.knowledge.router import router as ukie_router
    app.include_router(ukie_router)
    return app


def _set(monkeypatch, **flags):
    for k, v in flags.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


# ── Flag-gate ────────────────────────────────────────────────────────

def test_all_endpoints_503_when_flag_off(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED=None)
    with TestClient(_make_app()) as c:
        for path in (
            "/api/knowledge/domains",
            "/api/knowledge/domains/strategy",
            "/api/knowledge/connectors",
            "/api/knowledge/connectors/github",
            "/api/knowledge/domains/strategy/connectors",
        ):
            r = c.get(path)
            assert r.status_code == 503, f"{path} should be 503 when flag off, got {r.status_code}"


# ── Domain endpoints ─────────────────────────────────────────────────

def test_domains_list_returns_six(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/domains")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 6
        assert len(d["domains"]) == 6
        names = [s["domain"] for s in d["domains"]]
        assert set(names) == {
            "strategy", "research", "indicator",
            "market", "execution", "internal_history",
        }


def test_domain_spec_fields_present(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/domains/strategy")
        assert r.status_code == 200
        d = r.json()
        for f in (
            "domain", "display_name", "description",
            "storage_collection", "required_fields",
            "default_trust_floor", "ai_context_policy",
            "default_retention_policy", "searchable", "version",
        ):
            assert f in d, f"missing spec field: {f}"
        assert d["domain"] == "strategy"
        assert d["storage_collection"] == "strategies"


def test_domain_lookup_case_insensitive(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        for path in (
            "/api/knowledge/domains/STRATEGY",
            "/api/knowledge/domains/Strategy",
            "/api/knowledge/domains/strategy",
        ):
            r = c.get(path)
            assert r.status_code == 200, f"{path} should resolve"
            assert r.json()["domain"] == "strategy"


def test_domain_unknown_returns_404(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/domains/sentiment")
        assert r.status_code == 404


# ── Connector endpoints ──────────────────────────────────────────────

def test_connectors_list_includes_github(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/connectors")
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 1
        names = [c["name"] for c in d["connectors"]]
        assert "github" in names


def test_connector_metadata_shape(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/connectors/github")
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "github"
        assert d["source_type"] == "code"
        assert "strategy" in d["supported_domains"]
        # Capability metadata surface
        caps = d["capabilities"]
        for f in (
            "supports_discovery", "supports_incremental_sync",
            "supports_versioning", "supports_rate_limits",
            "supports_metadata_only",
        ):
            assert f in caps, f"missing capability flag: {f}"
        # GithubConnector's honest declaration
        assert caps["supports_discovery"] is True
        assert caps["supports_versioning"] is True
        assert caps["supports_rate_limits"] is True
        # rate_limit surface
        rl = d["rate_limit"]
        assert rl["requests_per_minute"] is not None


def test_connector_unknown_returns_404(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/connectors/nonexistent")
        assert r.status_code == 404


def test_connectors_for_domain(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        # Strategy — github registered here
        r = c.get("/api/knowledge/domains/strategy/connectors")
        assert r.status_code == 200
        d = r.json()
        assert d["domain"] == "strategy"
        assert d["count"] >= 1
        assert any(x["name"] == "github" for x in d["connectors"])
        # Research — no connector yet (Stage 3.α)
        r2 = c.get("/api/knowledge/domains/research/connectors")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["domain"] == "research"
        assert not any(x["name"] == "github" for x in d2["connectors"])


def test_connectors_for_unknown_domain_returns_404(monkeypatch):
    _set(monkeypatch, UKIE_DOMAIN_REGISTRY_ENABLED="true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/domains/no_such_domain/connectors")
        assert r.status_code == 404

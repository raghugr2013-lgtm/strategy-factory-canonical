"""Phase 2 Stage 3.β — end-to-end pipeline + dry-run tests."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import RawKnowledgeItem, now_iso  # noqa: E402
from engines.knowledge.constants import (  # noqa: E402
    PIPELINE_CONTRACT_VERSION,
    PIPELINE_VERSION,
)
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge import pipeline as pl  # noqa: E402
from engines.knowledge.repository import (  # noqa: E402
    KnowledgeRepository,
    _reset_for_tests as _reset_repo,
)


# ── Fake Mongo ───────────────────────────────────────────────────────

class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self._docs: List[Dict[str, Any]] = []
        self._counter = 0
    async def find_one(self, q, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None
    async def update_one(self, q, update, upsert=False):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))
                class _R: matched_count = 1
                return _R()
        self._counter += 1
        new = {"_id": f"{self.name}-{self._counter}"}
        new.update(update.get("$set", {}))
        new.update(update.get("$setOnInsert", {}))
        for k, v in q.items():
            new.setdefault(k, v)
        if upsert:
            self._docs.append(new)
        class _R: matched_count = 0
        return _R()


class _FakeDB:
    def __init__(self):
        self._colls = {}
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _FakeCollection(name)
        return self._colls[name]


def _mk_item(domain=KnowledgeDomain.STRATEGY, body: bytes = b"//@version=5 MIT", **overrides):
    digest = hashlib.sha256(body).hexdigest()
    kwargs = dict(
        domain=domain,
        connector_name="github",
        source_url="https://example.com/x",
        source_ref="ref",
        content_hash=f"sha256:{digest}",
        fetched_at=now_iso(),
        content_bytes=body,
        content_mime="text/plain",
        license="MIT",
    )
    kwargs.update(overrides)
    return RawKnowledgeItem(**kwargs)


# ── Pipeline composition ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_all_flags_off_returns_dormant(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_DEDUP_CHECK",
              "ENABLE_LICENSE_GATE", "ENABLE_TRUST_SCORER",
              "UKIE_GOVERNANCE_CUTOVER"):
        monkeypatch.delenv(f, raising=False)
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    outcome = await pl.run_one(_mk_item(), repository=repo)
    assert outcome.write["status"] == "dormant"
    assert outcome.write["reason"] == "UKIE_GOVERNANCE_CUTOVER is off"
    assert outcome.pipeline_version == PIPELINE_VERSION
    assert outcome.pipeline_contract_version == PIPELINE_CONTRACT_VERSION
    # No writes
    assert db["strategies"]._docs == []


@pytest.mark.asyncio
async def test_pipeline_all_flags_on_writes(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_DEDUP_CHECK",
              "ENABLE_LICENSE_GATE", "ENABLE_TRUST_SCORER",
              "UKIE_GOVERNANCE_CUTOVER"):
        monkeypatch.setenv(f, "true")
    db = _FakeDB()
    # Route dedup + repository to the same fake DB
    monkeypatch.setattr(
        "engines.knowledge.dedup_check._get_knowledge_db",
        lambda db_getter=None: db,
    )
    repo = KnowledgeRepository(db_getter=lambda: db)
    outcome = await pl.run_one(_mk_item(), repository=repo)
    assert outcome.write["status"] == "inserted"
    assert outcome.routing["routed"] is True
    assert outcome.dedup["status"] == "unique"
    assert outcome.license_verdict["outcome"] == "permissive"
    assert isinstance(outcome.trust_score["tier"], int)


@pytest.mark.asyncio
async def test_pipeline_same_domain_dedup_refuses(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_DEDUP_CHECK",
              "ENABLE_LICENSE_GATE", "ENABLE_TRUST_SCORER",
              "UKIE_GOVERNANCE_CUTOVER"):
        monkeypatch.setenv(f, "true")
    db = _FakeDB()
    monkeypatch.setattr(
        "engines.knowledge.dedup_check._get_knowledge_db",
        lambda db_getter=None: db,
    )
    repo = KnowledgeRepository(db_getter=lambda: db)
    item = _mk_item()
    # First insert
    r1 = await pl.run_one(item, repository=repo)
    assert r1.write["status"] == "inserted"
    # Second try — should be refused due to same-domain hash collision
    r2 = await pl.run_one(_mk_item(), repository=repo)  # same body/hash
    assert r2.dedup["status"] == "duplicate_same_domain"
    assert r2.write["status"] == "rejected"
    assert r2.trust_score["tier"] == 1  # quarantine


@pytest.mark.asyncio
async def test_pipeline_batch_summary_shape(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_LICENSE_GATE",
              "ENABLE_TRUST_SCORER"):
        monkeypatch.setenv(f, "true")
    # Governance cutover intentionally OFF — expect "dormant" write status
    monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)
    monkeypatch.delenv("ENABLE_DEDUP_CHECK", raising=False)
    items = [
        _mk_item(body=f"payload-{i}".encode(), source_ref=f"r-{i}")
        for i in range(5)
    ]
    summary = await pl.run_batch(items, dry_run=False)
    assert summary.total == 5
    assert summary.dormant == 5
    for k in ("pipeline_version", "pipeline_contract_version",
              "trust_tier_counts", "license_outcome_counts",
              "domain_counts"):
        d = summary.to_dict()
        assert k in d
    assert summary.domain_counts.get("strategy") == 5


def test_pipeline_status_shape():
    s = pl.pipeline_status()
    assert s["pipeline_version"] == PIPELINE_VERSION
    assert s["pipeline_contract_version"] == PIPELINE_CONTRACT_VERSION
    for k in ("domain_router", "dedup_check", "license_gate", "trust_scorer"):
        assert k in s["stages"]
    assert "governance_cutover" in s


# ── Dry-run harness ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_synthetic_fixture(monkeypatch):
    # All stage flags on, cutover OFF — dry_run bypasses writes regardless
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_LICENSE_GATE",
              "ENABLE_TRUST_SCORER"):
        monkeypatch.setenv(f, "true")
    monkeypatch.delenv("ENABLE_DEDUP_CHECK", raising=False)
    monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)
    from engines.knowledge.dry_run import run_dry
    summary = await run_dry(synthetic_fixture_name="stage_3_beta_default")
    assert summary.dry_run is True
    assert summary.total == 7
    assert summary.inserted == 0
    assert summary.updated == 0
    # 6 unique domains + 1 duplicate-hash — all six domains represented
    assert set(summary.domain_counts.keys()) == {
        "strategy", "research", "indicator",
        "market", "execution", "internal_history",
    }
    # License diversity check
    outcomes = set(summary.license_outcome_counts.keys())
    assert "permissive" in outcomes
    assert "strong_copyleft" in outcomes


@pytest.mark.asyncio
async def test_dry_run_never_writes(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_DEDUP_CHECK",
              "ENABLE_LICENSE_GATE", "ENABLE_TRUST_SCORER",
              "UKIE_GOVERNANCE_CUTOVER"):
        monkeypatch.setenv(f, "true")
    db = _FakeDB()
    monkeypatch.setattr(
        "engines.knowledge.dedup_check._get_knowledge_db",
        lambda db_getter=None: db,
    )
    _reset_repo()
    monkeypatch.setattr(
        "engines.knowledge.repository.get_repository",
        lambda: KnowledgeRepository(db_getter=lambda: db),
    )
    from engines.knowledge.dry_run import run_dry
    summary = await run_dry(synthetic_fixture_name="stage_3_beta_default")
    assert summary.dry_run is True
    # Even with cutover ON, dry-run bypasses repository writes
    for coll in ("strategies", "research", "indicators",
                 "market", "execution", "internal_history"):
        assert db._colls.get(coll) is None or db._colls[coll]._docs == [], \
            f"dry-run should not have written to {coll}"


@pytest.mark.asyncio
async def test_dry_run_explicit_items(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING", "ENABLE_LICENSE_GATE",
              "ENABLE_TRUST_SCORER"):
        monkeypatch.setenv(f, "true")
    from engines.knowledge.dry_run import run_dry
    items = [_mk_item(body=b"payload-A"), _mk_item(body=b"payload-B", domain=KnowledgeDomain.RESEARCH)]
    summary = await run_dry(items=items)
    assert summary.total == 2
    assert summary.domain_counts["strategy"] == 1
    assert summary.domain_counts["research"] == 1


@pytest.mark.asyncio
async def test_dry_run_replay_returns_empty_when_no_runs(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING",):
        monkeypatch.setenv(f, "true")
    monkeypatch.delenv("ENABLE_LICENSE_GATE", raising=False)
    from engines.knowledge.dry_run import run_dry
    # No ingestion_runs collection populated → replay yields 0 items
    summary = await run_dry(
        last_n_from_ingestion_runs=5,
        db_getter=lambda: _FakeDB(),
    )
    assert summary.total == 0


@pytest.mark.asyncio
async def test_dry_run_dict_coercion(monkeypatch):
    for f in ("ENABLE_DOMAIN_ROUTING",):
        monkeypatch.setenv(f, "true")
    from engines.knowledge.dry_run import run_dry
    payload = {
        "domain": "research",
        "connector_name": "arxiv",
        "source_url": "https://arxiv.org/abs/2101.00001",
        "source_ref": "2101.00001",
        "content_hash": "sha256:coerce",
        "fetched_at": now_iso(),
        "content_bytes": "Some paper body",
        "content_mime": "text/plain",
    }
    summary = await run_dry(items=[payload])
    assert summary.total == 1
    assert summary.domain_counts["research"] == 1


# ── Router endpoints ─────────────────────────────────────────────────

def _make_app():
    app = FastAPI()
    from engines.knowledge.router import router
    app.include_router(router)
    return app


def test_router_pipeline_status_503_when_flag_off(monkeypatch):
    monkeypatch.delenv("UKIE_DOMAIN_REGISTRY_ENABLED", raising=False)
    with TestClient(_make_app()) as c:
        assert c.get("/api/knowledge/pipeline/status").status_code == 503
        assert c.get("/api/knowledge/pipeline/last-run").status_code == 503
        assert c.post("/api/knowledge/dry-run", json={}).status_code == 503


def test_router_pipeline_status_shape(monkeypatch):
    monkeypatch.setenv("UKIE_DOMAIN_REGISTRY_ENABLED", "true")
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/pipeline/status")
        assert r.status_code == 200
        d = r.json()
        assert d["pipeline_version"] == PIPELINE_VERSION
        assert d["pipeline_contract_version"] == PIPELINE_CONTRACT_VERSION
        assert set(d["stages"].keys()) >= {"domain_router", "dedup_check", "license_gate", "trust_scorer"}


def test_router_dry_run_default_fixture(monkeypatch):
    monkeypatch.setenv("UKIE_DOMAIN_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    pl._reset_last_summary_for_tests()
    with TestClient(_make_app()) as c:
        r = c.post("/api/knowledge/dry-run", json={})
        assert r.status_code == 200
        d = r.json()
        assert d["dry_run"] is True
        assert d["total"] >= 6                                # fixture has 7 items


def test_router_last_run_reports_none_initially(monkeypatch):
    monkeypatch.setenv("UKIE_DOMAIN_REGISTRY_ENABLED", "true")
    pl._reset_last_summary_for_tests()
    with TestClient(_make_app()) as c:
        r = c.get("/api/knowledge/pipeline/last-run")
        assert r.status_code == 200
        assert r.json() == {"status": "none"}


def test_router_last_run_returns_summary_after_dry_run(monkeypatch):
    monkeypatch.setenv("UKIE_DOMAIN_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    pl._reset_last_summary_for_tests()
    with TestClient(_make_app()) as c:
        c.post("/api/knowledge/dry-run", json={"synthetic_fixture": "stage_3_beta_default"})
        r = c.get("/api/knowledge/pipeline/last-run")
        assert r.status_code == 200
        d = r.json()
        assert d["dry_run"] is True
        assert d["pipeline_version"] == PIPELINE_VERSION

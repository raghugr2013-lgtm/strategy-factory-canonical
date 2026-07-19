"""Phase 2 Stage 3.β — dedup check + repository tests."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import RawKnowledgeItem, now_iso  # noqa: E402
from engines.knowledge.dedup_check import DedupResult, check, is_enabled  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge.license_gate import LicenseOutcome, LicenseVerdict  # noqa: E402
from engines.knowledge.repository import (  # noqa: E402
    InsertResult,
    KnowledgeRepository,
    is_cutover_enabled,
)
from engines.knowledge.trust_scorer import TrustScore  # noqa: E402


# ── Fake Mongo — supports find_one / update_one / find / count ───────

class _FakeCollection:
    def __init__(self, name: str, docs: List[Dict[str, Any]] | None = None):
        self.name = name
        self._docs: List[Dict[str, Any]] = list(docs or [])
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
        # Upsert
        self._counter += 1
        new = {"_id": f"{self.name}-{self._counter}"}
        new.update(update.get("$set", {}))
        new.update(update.get("$setOnInsert", {}))
        # Seed the query fields too
        for k, v in q.items():
            new.setdefault(k, v)
        if upsert:
            self._docs.append(new)
        class _R: matched_count = 0
        return _R()


class _FakeDB:
    def __init__(self):
        self._colls: Dict[str, _FakeCollection] = {}
    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._colls:
            self._colls[name] = _FakeCollection(name)
        return self._colls[name]


def _item(*, domain=KnowledgeDomain.STRATEGY, ch="sha256:abc") -> RawKnowledgeItem:
    return RawKnowledgeItem(
        domain=domain,
        connector_name="test",
        source_url="u",
        source_ref="r",
        content_hash=ch,
        fetched_at=now_iso(),
        content_bytes=b"test payload",
    )


# ── Dedup check ──────────────────────────────────────────────────────

def test_dedup_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DEDUP_CHECK", raising=False)
    assert is_enabled() is False


@pytest.mark.asyncio
async def test_dedup_returns_unique_when_flag_off(monkeypatch):
    monkeypatch.delenv("ENABLE_DEDUP_CHECK", raising=False)
    db = _FakeDB()
    res = await check(_item(), db_getter=lambda: db)
    assert res.status == "unique"
    assert res.checked is False


@pytest.mark.asyncio
async def test_dedup_returns_no_hash_when_missing(monkeypatch):
    monkeypatch.setenv("ENABLE_DEDUP_CHECK", "true")
    db = _FakeDB()
    res = await check(_item(ch=""), db_getter=lambda: db)
    assert res.status == "no_hash"


@pytest.mark.asyncio
async def test_dedup_unique_when_empty_db(monkeypatch):
    monkeypatch.setenv("ENABLE_DEDUP_CHECK", "true")
    db = _FakeDB()
    res = await check(_item(), db_getter=lambda: db)
    assert res.status == "unique"
    assert res.checked is True


@pytest.mark.asyncio
async def test_dedup_same_domain_collision(monkeypatch):
    monkeypatch.setenv("ENABLE_DEDUP_CHECK", "true")
    db = _FakeDB()
    # Pre-seed a matching doc in the STRATEGY collection
    db["strategies"]._docs.append({"_id": "prev-1", "content_hash": "sha256:abc", "domain": "strategy"})
    res = await check(_item(), db_getter=lambda: db)
    assert res.status == "duplicate_same_domain"
    assert res.matched_id == "prev-1"


@pytest.mark.asyncio
async def test_dedup_cross_domain_allowed(monkeypatch):
    monkeypatch.setenv("ENABLE_DEDUP_CHECK", "true")
    db = _FakeDB()
    # Same hash in a DIFFERENT domain — allowed by design
    db["research"]._docs.append({"_id": "r-1", "content_hash": "sha256:abc", "domain": "research"})
    res = await check(_item(), db_getter=lambda: db)
    assert res.status == "duplicate_cross_domain"
    assert res.matched_domain == "research"


@pytest.mark.asyncio
async def test_dedup_fail_open_on_no_db(monkeypatch):
    monkeypatch.setenv("ENABLE_DEDUP_CHECK", "true")
    res = await check(_item(), db_getter=lambda: None)
    assert res.status == "unique"
    assert "fail_open" in res.reason


# ── Repository ───────────────────────────────────────────────────────

def test_repository_cutover_flag_default_off(monkeypatch):
    monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)
    assert is_cutover_enabled() is False


@pytest.mark.asyncio
async def test_repository_dormant_when_cutover_off(monkeypatch):
    monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    r = await repo.insert_ingested(_item())
    assert r.status == "dormant"
    assert r.reason == "UKIE_GOVERNANCE_CUTOVER is off"
    # No writes to Mongo
    assert db["strategies"]._docs == []


@pytest.mark.asyncio
async def test_repository_inserts_when_cutover_on(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    r = await repo.insert_ingested(_item())
    assert r.status == "inserted"
    assert r.storage_collection == "strategies"
    assert r.doc_id is not None
    assert r.pipeline_version   # non-empty
    assert r.pipeline_contract_version
    # Hard rails on stored doc
    stored = db["strategies"]._docs[0]
    assert stored["learning_only"] is True
    assert stored["eligible_for_deploy"] is False


@pytest.mark.asyncio
async def test_repository_upsert_idempotent(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    it = _item()
    r1 = await repo.insert_ingested(it)
    r2 = await repo.insert_ingested(it)
    assert r1.status == "inserted"
    assert r2.status == "updated"
    # Only one document in the collection
    assert len(db["strategies"]._docs) == 1


@pytest.mark.asyncio
async def test_repository_per_domain_routing(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    for dom, coll in (
        (KnowledgeDomain.STRATEGY, "strategies"),
        (KnowledgeDomain.RESEARCH, "research"),
        (KnowledgeDomain.EXECUTION, "execution"),
    ):
        r = await repo.insert_ingested(_item(domain=dom, ch=f"sha256:{dom.value}"))
        assert r.storage_collection == coll
        assert r.status == "inserted"


@pytest.mark.asyncio
async def test_repository_hard_rails_overridden(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    it = _item()
    # Try to sneak eligible_for_deploy=True past the repository
    it.learning_only = False
    it.eligible_for_deploy = True
    await repo.insert_ingested(it)
    stored = db["strategies"]._docs[0]
    assert stored["learning_only"] is True
    assert stored["eligible_for_deploy"] is False


@pytest.mark.asyncio
async def test_repository_rejects_empty_hash(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    r = await repo.insert_ingested(_item(ch=""))
    assert r.status == "rejected"
    assert r.reason == "empty_content_hash"


@pytest.mark.asyncio
async def test_repository_error_when_db_unavailable(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    repo = KnowledgeRepository(db_getter=lambda: None)
    r = await repo.insert_ingested(_item())
    assert r.status == "error"
    assert r.reason == "db_unavailable"


@pytest.mark.asyncio
async def test_repository_writes_version_stamps(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    await repo.insert_ingested(_item())
    stored = db["strategies"]._docs[0]
    for k in ("pipeline_version", "pipeline_contract_version",
              "processed_at", "updated_at", "inserted_at"):
        assert k in stored, f"missing version/timestamp field: {k}"


@pytest.mark.asyncio
async def test_repository_carries_license_and_trust(monkeypatch):
    monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    db = _FakeDB()
    repo = KnowledgeRepository(db_getter=lambda: db)
    lv = LicenseVerdict(outcome=LicenseOutcome.PERMISSIVE, spdx_id="MIT",
                        confidence=1.0, method="spdx", evidence="MIT")
    ts = TrustScore(tier=4, seed_tier=3, parser_confidence=0.9, adjustments=[], scored=True)
    await repo.insert_ingested(_item(), license_verdict=lv, trust_score=ts)
    stored = db["strategies"]._docs[0]
    assert stored["license_verdict"]["outcome"] == "permissive"
    assert stored["trust_score"]["tier"] == 4

"""Phase 2 Stage 3.γ — Retro-scoring (P2C.11) tests.

Coverage (plan §3.9):
  1. Empty legacy collection — clean run, all counts 0
  2. Populated legacy (stub Mongo) — dry-run produces expected summary, no writes
  3. Commit run — each written row carries retro_score_run_id + version stamps
  4. Idempotency — second run returns inserted=0, updated=N
  5. `confirm_write` guard — 400 when dry_run=false without the string
  6. Rollback — deletes cleanly; second rollback idempotent
  7. Malformed legacy rows — recorded in `errored`, not silently skipped
  8. Governance cutover off — real run returns dormant=N, writes nothing
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.retro_score import (  # noqa: E402
    CONFIRM_WRITE_TOKEN,
    LEGACY_COLLECTION,
    RETRO_SCORE_RUNS_COLLECTION,
    RetroScoreRunner,
    RetroScoreSummary,
    legacy_row_to_item,
)
from engines.knowledge import retro_score as rs  # noqa: E402
from engines.knowledge.repository import (  # noqa: E402
    KnowledgeRepository,
    _reset_for_tests as _reset_repo,
)


# ── Fake Mongo ───────────────────────────────────────────────────────

class _FakeCollection:
    def __init__(self, name: str, docs: Optional[List[Dict[str, Any]]] = None):
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
                if "$push" in update:
                    for k, v in update["$push"].items():
                        d.setdefault(k, []).append(v)
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

    async def insert_one(self, doc):
        self._counter += 1
        stored = dict(doc)
        stored.setdefault("_id", f"{self.name}-{self._counter}")
        self._docs.append(stored)
        class _R:
            def __init__(self, _id): self.inserted_id = _id
        return _R(stored["_id"])

    async def delete_many(self, q):
        before = len(self._docs)
        self._docs = [d for d in self._docs if not all(d.get(k) == v for k, v in q.items())]
        class _R:
            def __init__(self, n): self.deleted_count = n
        return _R(before - len(self._docs))

    def find(self, filter=None):
        docs = list(self._docs)
        class _Cur:
            def __init__(self, docs):
                self._i = iter(docs)
            def __aiter__(self):
                return self
            async def __anext__(self):
                try:
                    return next(self._i)
                except StopIteration:
                    raise StopAsyncIteration
        return _Cur(docs)


class _FakeDB:
    def __init__(self):
        self._colls: Dict[str, _FakeCollection] = {}
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _FakeCollection(name)
        return self._colls[name]


# ── Fixtures ─────────────────────────────────────────────────────────

def _legacy_row(strategy_text: str, **overrides) -> Dict[str, Any]:
    body = strategy_text.encode("utf-8")
    row = {
        "_id":            f"legacy-{hashlib.sha256(body).hexdigest()[:8]}",
        "strategy_text":  strategy_text,
        "pair":           "XAUUSD",
        "timeframe":      "H4",
        "source_url":     "https://example.com/legacy",
        "source_ref":     "abc",
        "created_at":     "2025-01-01T00:00:00+00:00",
        "content_hash":   f"sha256:{hashlib.sha256(body).hexdigest()}",
        "license":        "MIT",
    }
    row.update(overrides)
    return row


def _enable_flags(monkeypatch, *, cutover: bool = False):
    monkeypatch.setenv("UKIE_RETRO_SCORE_ENABLED", "true")
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    monkeypatch.setenv("ENABLE_LICENSE_GATE", "true")
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    monkeypatch.delenv("ENABLE_DEDUP_CHECK", raising=False)
    if cutover:
        monkeypatch.setenv("UKIE_GOVERNANCE_CUTOVER", "true")
    else:
        monkeypatch.delenv("UKIE_GOVERNANCE_CUTOVER", raising=False)


# ── Mapping ──────────────────────────────────────────────────────────

class TestMapping:
    def test_valid_row_produces_item(self):
        item = legacy_row_to_item(_legacy_row("// MIT strategy"))
        assert item is not None
        assert item.domain.value == "strategy"
        assert item.content_hash.startswith("sha256:")
        assert item.extras["pair"] == "XAUUSD"
        assert item.extras["timeframe"] == "H4"

    def test_missing_text_returns_none(self):
        assert legacy_row_to_item({"_id": "x"}) is None
        assert legacy_row_to_item({"_id": "x", "strategy_text": ""}) is None

    def test_missing_content_hash_recomputed(self):
        row = _legacy_row("body")
        row.pop("content_hash")
        item = legacy_row_to_item(row)
        assert item is not None
        assert item.content_hash.startswith("sha256:")


# ── Runner — dry-run / commit / idempotency ──────────────────────────

class TestRunner:
    @pytest.mark.asyncio
    async def test_empty_legacy_produces_zero_summary(self, monkeypatch):
        _enable_flags(monkeypatch)
        kb = _FakeDB()
        r = RetroScoreRunner(kb_db_getter=lambda: kb)
        s = await r.run(dry_run=True, legacy_rows=[])
        assert s.input_row_count == 0
        assert s.inserted == 0 and s.dormant == 0 and s.errored == 0
        # audit run row still landed
        assert len(kb[RETRO_SCORE_RUNS_COLLECTION]._docs) == 1

    @pytest.mark.asyncio
    async def test_populated_dry_run_no_writes(self, monkeypatch):
        _enable_flags(monkeypatch)
        kb = _FakeDB()
        # dedup can query the same kb
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [_legacy_row(f"body-{i}") for i in range(3)]
        s = await r.run(dry_run=True, legacy_rows=rows)
        assert s.dry_run is True
        assert s.input_row_count == 3
        assert s.dormant == 3
        assert s.inserted == 0
        # No writes to any domain collection
        assert kb._colls.get("strategies") is None or kb["strategies"]._docs == []
        # audit run row landed
        assert len(kb[RETRO_SCORE_RUNS_COLLECTION]._docs) == 1
        run_row = kb[RETRO_SCORE_RUNS_COLLECTION]._docs[0]
        assert run_row["pipeline_version"]
        assert run_row["pipeline_contract_version"]

    @pytest.mark.asyncio
    async def test_commit_writes_and_stamps_run_id(self, monkeypatch):
        _enable_flags(monkeypatch, cutover=True)
        kb = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [_legacy_row(f"body-{i}") for i in range(3)]
        s = await r.run(dry_run=False, legacy_rows=rows)
        assert s.dry_run is False
        assert s.inserted == 3
        assert s.updated == 0
        assert s.dormant == 0
        # Every written row carries the run_id
        stored = kb["strategies"]._docs
        assert len(stored) == 3
        assert all(d["retro_score_run_id"] == s.run_id for d in stored)
        assert all(d["pipeline_version"] for d in stored)
        assert all(d["pipeline_contract_version"] for d in stored)
        # Hard rails preserved
        assert all(d["learning_only"] is True for d in stored)
        assert all(d["eligible_for_deploy"] is False for d in stored)

    @pytest.mark.asyncio
    async def test_idempotent_second_run(self, monkeypatch):
        _enable_flags(monkeypatch, cutover=True)
        kb = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [_legacy_row(f"body-{i}") for i in range(3)]
        s1 = await r.run(dry_run=False, legacy_rows=rows)
        assert s1.inserted == 3
        # Second run — same rows — should update, not duplicate
        s2 = await r.run(dry_run=False, legacy_rows=rows)
        assert s2.inserted == 0
        assert s2.updated == 3
        # Still only 3 documents in the domain collection
        assert len(kb["strategies"]._docs) == 3

    @pytest.mark.asyncio
    async def test_governance_cutover_off_yields_dormant(self, monkeypatch):
        # Real run (dry_run=False) but cutover is OFF → all dormant, no writes
        _enable_flags(monkeypatch, cutover=False)
        kb = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [_legacy_row(f"body-{i}") for i in range(3)]
        s = await r.run(dry_run=False, legacy_rows=rows)
        assert s.dormant == 3
        assert s.inserted == 0
        # Nothing landed in any domain collection
        assert kb._colls.get("strategies") is None or kb["strategies"]._docs == []

    @pytest.mark.asyncio
    async def test_malformed_row_recorded_as_errored(self, monkeypatch):
        _enable_flags(monkeypatch, cutover=True)
        kb = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [
            _legacy_row("ok body"),
            {"_id": "bad", "pair": "XAUUSD"},  # no strategy_text
        ]
        s = await r.run(dry_run=False, legacy_rows=rows)
        assert s.errored == 1
        assert s.inserted == 1


# ── Rollback ─────────────────────────────────────────────────────────

class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_deletes_and_is_idempotent(self, monkeypatch):
        _enable_flags(monkeypatch, cutover=True)
        kb = _FakeDB()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        repo = KnowledgeRepository(db_getter=lambda: kb)
        r = RetroScoreRunner(kb_db_getter=lambda: kb, repository=repo)
        rows = [_legacy_row(f"body-{i}") for i in range(3)]
        s = await r.run(dry_run=False, legacy_rows=rows)
        assert len(kb["strategies"]._docs) == 3

        rb1 = await r.rollback(s.run_id, requested_by="op", reason="test")
        assert rb1["deleted_count"] == 3
        assert rb1["resolved"] == "rolled_back"
        assert kb["strategies"]._docs == []
        # Second rollback is idempotent
        rb2 = await r.rollback(s.run_id, requested_by="op", reason="again")
        assert rb2["deleted_count"] == 0
        assert rb2["resolved"] == "already_rolled_back"
        # Rollback audit stamped on run row
        run_row = kb[RETRO_SCORE_RUNS_COLLECTION]._docs[0]
        assert "rollbacks" in run_row
        assert len(run_row["rollbacks"]) == 2


# ── Router ───────────────────────────────────────────────────────────

def _make_app():
    from engines.knowledge.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestRouter:
    def test_endpoints_503_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_RETRO_SCORE_ENABLED", raising=False)
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/retro-score", json={})
            assert r.status_code == 503
            r = c.post("/api/knowledge/retro-score/rollback/run-x",
                       json={"reason": "x", "requested_by": "op"})
            assert r.status_code == 503

    def test_dry_run_default(self, monkeypatch):
        _enable_flags(monkeypatch)
        kb = _FakeDB()
        rs._reset_for_tests()
        monkeypatch.setattr(
            "engines.knowledge.retro_score.get_runner",
            lambda: RetroScoreRunner(
                kb_db_getter=lambda: kb,
                legacy_db_getter=lambda: _FakeDB(),  # empty legacy
            ),
        )
        monkeypatch.setattr(
            "engines.knowledge.retro_score_router.get_runner",
            lambda: RetroScoreRunner(
                kb_db_getter=lambda: kb,
                legacy_db_getter=lambda: _FakeDB(),
            ),
        )
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/retro-score", json={})
            assert r.status_code == 200
            body = r.json()
            assert body["dry_run"] is True
            assert body["input_row_count"] == 0

    def test_commit_requires_confirm_write_token(self, monkeypatch):
        _enable_flags(monkeypatch)
        with TestClient(_make_app()) as c:
            # Missing token
            r = c.post("/api/knowledge/retro-score",
                       json={"dry_run": False})
            assert r.status_code == 400
            # Wrong token
            r = c.post("/api/knowledge/retro-score",
                       json={"dry_run": False, "confirm_write": "yes_please"})
            assert r.status_code == 400

    def test_commit_accepts_correct_token(self, monkeypatch):
        _enable_flags(monkeypatch, cutover=True)
        kb = _FakeDB()
        legacy_db = _FakeDB()
        legacy_db[LEGACY_COLLECTION]._docs.append(_legacy_row("router-body"))
        rs._reset_for_tests()
        monkeypatch.setattr(
            "engines.knowledge.dedup_check._get_knowledge_db",
            lambda db_getter=None: kb,
        )
        _reset_repo()
        monkeypatch.setattr(
            "engines.knowledge.retro_score_router.get_runner",
            lambda: RetroScoreRunner(
                kb_db_getter=lambda: kb,
                legacy_db_getter=lambda: legacy_db,
                repository=KnowledgeRepository(db_getter=lambda: kb),
            ),
        )
        with TestClient(_make_app()) as c:
            r = c.post(
                "/api/knowledge/retro-score",
                json={"dry_run": False, "confirm_write": CONFIRM_WRITE_TOKEN,
                      "requested_by": "operator"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["dry_run"] is False
            assert body["inserted"] == 1

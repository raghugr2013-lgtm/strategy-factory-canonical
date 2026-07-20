"""Phase 2 Stage 3.γ — Promote Bridge (P2C.9) tests.

Coverage (plan §2.9):
  1. Precondition suite — every §2.2 condition produces a specific reason
  2. Hard-rail enforcement at the writer
  3. Idempotency (already promoted)
  4. Dedup-override audit
  5. Rollback (idempotent)
  6. Empty / malformed item_id
  7. Endpoint 503 when flag off
  8. Dry-run — no Mongo write; composed doc in response
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

from engines.knowledge import promote_bridge as pb  # noqa: E402
from engines.knowledge.promote import (  # noqa: E402
    MIN_TRUST_TIER,
    REFUSE_DEDUP_COLLISION,
    REFUSE_ITEM_MALFORMED,
    REFUSE_ITEM_NOT_FOUND,
    REFUSE_LICENSE_REFUSED,
    REFUSE_TRUST_TOO_LOW,
    REFUSE_WRONG_DOMAIN,
    PromoteOptions,
    evaluate_promote,
)
from engines.knowledge.promote_bridge import (  # noqa: E402
    ORIGIN_UKIE_PROMOTE,
    PROMOTE_EVENTS_COLLECTION,
    PromoteBridge,
    RESOLVED_DRY_RUN,
    RESOLVED_PROMOTED,
    RESOLVED_REFUSED,
    RESOLVED_DEMOTED,
    RESOLVED_ALREADY_DEMOTED,
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

    async def insert_one(self, doc):
        self._counter += 1
        stored = dict(doc)
        stored.setdefault("_id", f"{self.name}-{self._counter}")
        self._docs.append(stored)
        class _R:  # noqa: D401
            def __init__(self, _id):
                self.inserted_id = _id
        return _R(stored["_id"])

    async def delete_many(self, q):
        before = len(self._docs)
        self._docs = [d for d in self._docs if not all(d.get(k) == v for k, v in q.items())]
        class _R:
            def __init__(self, n):
                self.deleted_count = n
        return _R(before - len(self._docs))


class _FakeDB:
    def __init__(self):
        self._colls: Dict[str, _FakeCollection] = {}
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _FakeCollection(name)
        return self._colls[name]


# ── Fixtures ─────────────────────────────────────────────────────────

def _kb_item(
    *,
    _id: str = "kb-1",
    domain: str = "strategy",
    trust_tier: int = 5,
    license_outcome: str = "permissive",
    content_hash: str = "sha256:abc",
    content_bytes: bytes = b"// MIT strategy",
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "_id":                _id,
        "domain":             domain,
        "content_hash":       content_hash,
        "content_bytes":      content_bytes,
        "trust_tier":         trust_tier,
        "license":            "MIT",
        "license_verdict":    {"outcome": license_outcome, "spdx_id": "mit", "confidence": 1.0},
        "extras":             extras or {"pair": "XAUUSD", "timeframe": "H4"},
    }


def _enable_promote(monkeypatch, *, dry_run_default: bool = True):
    monkeypatch.setenv("UKIE_PROMOTE_BRIDGE_ENABLED", "true")
    monkeypatch.setenv("UKIE_PROMOTE_DRY_RUN", "true" if dry_run_default else "false")


# ── evaluate_promote — precondition suite ────────────────────────────

class TestPreconditions:
    def test_item_not_found(self):
        v = evaluate_promote(None, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_ITEM_NOT_FOUND

    def test_malformed_item(self):
        v = evaluate_promote({}, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_ITEM_MALFORMED

    def test_wrong_domain(self):
        item = _kb_item(domain="research")
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_WRONG_DOMAIN

    def test_trust_too_low(self):
        item = _kb_item(trust_tier=MIN_TRUST_TIER - 1)
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_TRUST_TOO_LOW

    def test_trust_missing(self):
        item = _kb_item()
        item.pop("trust_tier")
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_TRUST_TOO_LOW

    def test_license_refused_strong_copyleft(self):
        item = _kb_item(license_outcome="strong_copyleft")
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_LICENSE_REFUSED

    def test_license_refused_proprietary(self):
        item = _kb_item(license_outcome="proprietary")
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
        assert v.ok is False
        assert v.refuse_reason == REFUSE_LICENSE_REFUSED

    def test_permissive_and_weak_copyleft_accepted(self):
        for outcome in ("permissive", "weak_copyleft"):
            item = _kb_item(license_outcome=outcome)
            v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"))
            assert v.ok is True, outcome

    def test_dedup_refused_without_override(self):
        item = _kb_item()
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op"),
                             prod_dedup_id="prod-existing")
        assert v.ok is False
        assert v.refuse_reason == REFUSE_DEDUP_COLLISION
        assert v.dedup_conflict_id == "prod-existing"

    def test_dedup_accepted_with_override(self):
        item = _kb_item()
        v = evaluate_promote(item, PromoteOptions(reason="r", requested_by="op", override_dedup=True),
                             prod_dedup_id="prod-existing")
        assert v.ok is True
        assert v.override_dedup is True
        assert v.dedup_conflict_id == "prod-existing"


# ── Writer — hard rails / dry-run / commit ───────────────────────────

class TestWriter:
    @pytest.mark.asyncio
    async def test_dry_run_composes_no_write(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=True)
        kb, prod = _FakeDB(), _FakeDB()
        # Seed the KB item — even if it advertises unsafe flags
        item = _kb_item()
        item["learning_only"] = False
        item["eligible_for_deploy"] = True
        kb["strategies"]._docs.append(item)

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        result = await b.promote_item(
            "kb-1",
            PromoteOptions(reason="unit-test", requested_by="op"),
            # dry_run=None → follows default (TRUE)
        )
        assert result.resolved == RESOLVED_DRY_RUN
        assert result.composed_doc is not None
        # Hard rails re-stamped regardless of item state
        assert result.composed_doc["learning_only"] is True
        assert result.composed_doc["eligible_for_deploy"] is False
        assert result.composed_doc["origin"] == ORIGIN_UKIE_PROMOTE
        # NO write to production
        assert prod._colls.get("strategies") is None or prod["strategies"]._docs == []
        # Audit event landed
        assert len(kb[PROMOTE_EVENTS_COLLECTION]._docs) == 1
        assert kb[PROMOTE_EVENTS_COLLECTION]._docs[0]["dry_run"] is True

    @pytest.mark.asyncio
    async def test_commit_writes_production(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        result = await b.promote_item(
            "kb-1",
            PromoteOptions(reason="commit-test", requested_by="op"),
            dry_run=False,
        )
        assert result.resolved == RESOLVED_PROMOTED
        assert result.prod_strategy_id
        # Prod row present, hard rails safe
        assert len(prod["strategies"]._docs) == 1
        stored = prod["strategies"]._docs[0]
        assert stored["learning_only"] is True
        assert stored["eligible_for_deploy"] is False
        assert stored["promoted_from"] == "kb-1"
        assert stored["origin"] == ORIGIN_UKIE_PROMOTE
        assert stored["promoted_by"] == "op"
        assert stored["promote_pipeline_version"]
        # Audit event
        assert kb[PROMOTE_EVENTS_COLLECTION]._docs[0]["resolved"] == RESOLVED_PROMOTED
        assert kb[PROMOTE_EVENTS_COLLECTION]._docs[0]["dry_run"] is False

    @pytest.mark.asyncio
    async def test_refusal_audited(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item(license_outcome="strong_copyleft"))

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        r = await b.promote_item("kb-1",
                                 PromoteOptions(reason="r", requested_by="op"),
                                 dry_run=False)
        assert r.resolved == RESOLVED_REFUSED
        assert r.refuse_reason == REFUSE_LICENSE_REFUSED
        assert prod["strategies"]._docs == []
        # audit event still landed
        assert kb[PROMOTE_EVENTS_COLLECTION]._docs[0]["resolved"] == RESOLVED_REFUSED
        assert kb[PROMOTE_EVENTS_COLLECTION]._docs[0]["refuse_reason"] == REFUSE_LICENSE_REFUSED

    @pytest.mark.asyncio
    async def test_item_not_found(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        r = await b.promote_item("kb-missing",
                                 PromoteOptions(reason="r", requested_by="op"),
                                 dry_run=False)
        assert r.resolved == RESOLVED_REFUSED
        assert r.refuse_reason == REFUSE_ITEM_NOT_FOUND

    @pytest.mark.asyncio
    async def test_dedup_refusal_without_override(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())
        # Seed a colliding production row
        prod["strategies"]._docs.append({"_id": "prod-existing", "content_hash": "sha256:abc"})

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        r = await b.promote_item("kb-1",
                                 PromoteOptions(reason="r", requested_by="op"),
                                 dry_run=False)
        assert r.resolved == RESOLVED_REFUSED
        assert r.refuse_reason == REFUSE_DEDUP_COLLISION
        assert len(prod["strategies"]._docs) == 1  # unchanged

    @pytest.mark.asyncio
    async def test_dedup_override_writes_and_audits(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())
        prod["strategies"]._docs.append({"_id": "prod-existing", "content_hash": "sha256:abc"})

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        r = await b.promote_item(
            "kb-1",
            PromoteOptions(reason="dup-ok", requested_by="op", override_dedup=True),
            dry_run=False,
        )
        assert r.resolved == RESOLVED_PROMOTED
        assert r.override_dedup is True
        assert len(prod["strategies"]._docs) == 2
        # audit event stamped override_dedup=true
        events = kb[PROMOTE_EVENTS_COLLECTION]._docs
        assert events[0]["override_dedup"] is True

    @pytest.mark.asyncio
    async def test_idempotent_second_promote_rejected(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        # First promote — OK
        r1 = await b.promote_item("kb-1",
                                  PromoteOptions(reason="r", requested_by="op"),
                                  dry_run=False)
        assert r1.resolved == RESOLVED_PROMOTED
        # Second promote — now the prod row exists, so dedup fires
        r2 = await b.promote_item("kb-1",
                                  PromoteOptions(reason="r", requested_by="op"),
                                  dry_run=False)
        assert r2.resolved == RESOLVED_REFUSED
        assert r2.refuse_reason == REFUSE_DEDUP_COLLISION
        assert len(prod["strategies"]._docs) == 1
        # Two audit events regardless
        assert len(kb[PROMOTE_EVENTS_COLLECTION]._docs) == 2

    @pytest.mark.asyncio
    async def test_flag_off_returns_flag_off_result(self, monkeypatch):
        # No _enable_promote — flag is OFF by default
        monkeypatch.delenv("UKIE_PROMOTE_BRIDGE_ENABLED", raising=False)
        kb, prod = _FakeDB(), _FakeDB()
        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        r = await b.promote_item("kb-1",
                                 PromoteOptions(reason="r", requested_by="op"))
        assert r.resolved == "flag_off"


# ── Rollback / demote ────────────────────────────────────────────────

class TestRollback:
    @pytest.mark.asyncio
    async def test_rollback_deletes_and_audits(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())

        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        await b.promote_item("kb-1",
                             PromoteOptions(reason="r", requested_by="op"),
                             dry_run=False)
        assert len(prod["strategies"]._docs) == 1

        r = await b.demote_item("kb-1", requested_by="op", reason="rollback")
        assert r.resolved == RESOLVED_DEMOTED
        assert r.deleted_count == 1
        assert prod["strategies"]._docs == []
        # Repeat rollback is idempotent
        r2 = await b.demote_item("kb-1", requested_by="op", reason="rollback again")
        assert r2.resolved == RESOLVED_ALREADY_DEMOTED
        assert r2.deleted_count == 0
        # Two demote audit events regardless
        demote_events = [d for d in kb[PROMOTE_EVENTS_COLLECTION]._docs if d.get("kind") == "demote"]
        assert len(demote_events) == 2

    @pytest.mark.asyncio
    async def test_rollback_only_touches_ukie_promote_origin(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())
        # Seed a native row that shares the promoted_from tag but not origin
        prod["strategies"]._docs.append({
            "_id":            "native-row",
            "promoted_from":  "kb-1",
            "origin":         "native_ingestion",
        })
        b = PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb)
        await b.promote_item("kb-1",
                             PromoteOptions(reason="r", requested_by="op"),
                             dry_run=False)
        assert len(prod["strategies"]._docs) == 2

        r = await b.demote_item("kb-1", requested_by="op", reason="targeted")
        assert r.deleted_count == 1
        # Native row untouched
        remaining_ids = [d["_id"] for d in prod["strategies"]._docs]
        assert "native-row" in remaining_ids


# ── Router — 503 when flag off; wired-up endpoint success ────────────

def _make_app():
    from engines.knowledge.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestRouter:
    def test_all_promote_endpoints_503_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_PROMOTE_BRIDGE_ENABLED", raising=False)
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/promote/kb-1",
                       json={"reason": "x", "requested_by": "op"})
            assert r.status_code == 503
            r = c.post("/api/knowledge/promote/kb-1/rollback",
                       json={"reason": "x", "requested_by": "op"})
            assert r.status_code == 503

    def test_promote_dry_run_via_endpoint(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=True)
        # Inject fakes into the module-level bridge singleton
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())
        pb._reset_for_tests()
        monkeypatch.setattr(
            "engines.knowledge.promote_bridge.get_bridge",
            lambda: PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb),
        )
        monkeypatch.setattr(
            "engines.knowledge.promote_router.get_bridge",
            lambda: PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb),
        )
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/promote/kb-1",
                       json={"reason": "dry", "requested_by": "op"})
            assert r.status_code == 200
            body = r.json()
            assert body["resolved"] == RESOLVED_DRY_RUN
            # No write to prod
            assert prod._colls.get("strategies") is None or prod["strategies"]._docs == []

    def test_promote_commit_via_endpoint(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=False)
        kb, prod = _FakeDB(), _FakeDB()
        kb["strategies"]._docs.append(_kb_item())
        pb._reset_for_tests()
        monkeypatch.setattr(
            "engines.knowledge.promote_router.get_bridge",
            lambda: PromoteBridge(prod_db_getter=lambda: prod, kb_db_getter=lambda: kb),
        )
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/promote/kb-1?dry_run=0",
                       json={"reason": "commit", "requested_by": "op"})
            assert r.status_code == 200
            assert r.json()["resolved"] == RESOLVED_PROMOTED
            assert len(prod["strategies"]._docs) == 1

    def test_empty_item_id_returns_400(self, monkeypatch):
        _enable_promote(monkeypatch, dry_run_default=True)
        with TestClient(_make_app()) as c:
            # FastAPI routes require path — "/promote/  " would 404. Use whitespace to test guard.
            r = c.post("/api/knowledge/promote/%20",
                       json={"reason": "x", "requested_by": "op"})
            assert r.status_code == 400

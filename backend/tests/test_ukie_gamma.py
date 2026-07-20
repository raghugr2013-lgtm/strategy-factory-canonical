"""Phase 2 Stage 4 P4C — UKIE γ tests.

Covers:
  * Ranking v2 — flag off = identity, per-multiplier behaviour, license zeroing
  * Retrieval — query filter + rule-based similarity + ai_context_policy
  * Lifecycle — dry-run per-domain sweep + audit events
  * Confidence — endorsements + contradictions with contested flag
  * Governance policy — evaluate + write_verdict (advisory only)
  * Router — 503 when flag off; 200 on happy paths
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.confidence import (  # noqa: E402
    ConfidenceStore, ENDORSEMENT_EVENTS_COLLECTION,
    CONTRADICTION_EVENTS_COLLECTION,
)
from engines.knowledge.governance_policy import (  # noqa: E402
    GovernancePolicyEngine, PolicyVerdict, _eval_condition,
)
from engines.knowledge.lifecycle import (  # noqa: E402
    LifecycleSweeper, LIFECYCLE_EVENTS_COLLECTION,
)
from engines.knowledge.ranking import (  # noqa: E402
    compose, endorsement_multiplier, license_multiplier,
    recency_multiplier, trust_multiplier,
)
from engines.knowledge.retrieval import (  # noqa: E402
    QueryRequest, RetrievalEngine, rule_based_similarity,
)


# ── Fake Mongo (rich enough for P4C) ─────────────────────────────────

class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._limit = None
        self._sort_key = None
        self._sort_dir = 1
    def limit(self, n):
        self._limit = n
        return self
    def sort(self, key, direction=1):
        self._sort_key = key
        self._sort_dir = direction
        return self
    def __aiter__(self):
        rows = list(self._rows)
        if self._sort_key:
            rows.sort(key=lambda d: d.get(self._sort_key, 0),
                      reverse=(self._sort_dir < 0))
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
        self._i = 0
    async def insert_one(self, doc):
        self._i += 1
        stored = {**doc}
        stored.setdefault("_id", f"{self.name}-{self._i}")
        self._docs.append(stored)
        class _R:
            def __init__(self, _id): self.inserted_id = _id
        return _R(stored["_id"])
    async def update_one(self, q, update, upsert=False):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))
                class _R: matched_count = 1
                return _R()
        class _R: matched_count = 0
        return _R()
    async def find_one(self, q):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None
    async def delete_many(self, q):
        before = len(self._docs)
        def _match(d):
            for k, v in q.items():
                if isinstance(v, dict) and "$in" in v:
                    if d.get(k) not in v["$in"]:
                        return False
                elif d.get(k) != v:
                    return False
            return True
        self._docs = [d for d in self._docs if not _match(d)]
        class _R:
            def __init__(self, n): self.deleted_count = n
        return _R(before - len(self._docs))
    def find(self, q):
        def _match(d):
            for k, v in q.items():
                if isinstance(v, dict):
                    for op, val in v.items():
                        got = d.get(k)
                        if op == "$gte" and not (got is not None and got >= val): return False
                        if op == "$lt"  and not (got is not None and got  < val): return False
                elif k.startswith("extras."):
                    key = k.split(".", 1)[1]
                    if (d.get("extras") or {}).get(key) != v:
                        return False
                elif d.get(k) != v:
                    return False
            return True
        return _Cursor([d for d in self._docs if _match(d)])
    async def count_documents(self, q):
        def _match(d):
            for k, v in q.items():
                if isinstance(v, dict) and "$gte" in v:
                    got = d.get(k)
                    if not (got is not None and got >= v["$gte"]): return False
                elif d.get(k) != v:
                    return False
            return True
        return sum(1 for d in self._docs if _match(d))


class _FakeDB:
    def __init__(self):
        self._c: Dict[str, _Coll] = {}
    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = _Coll(name)
        return self._c[name]


# ── Ranking ──────────────────────────────────────────────────────────

class TestRanking:
    def test_flag_off_is_identity(self, monkeypatch):
        monkeypatch.delenv("UKIE_RANKING_V2_ENABLED", raising=False)
        b = compose(base_similarity=0.4, trust_tier=5, license_outcome="permissive")
        assert b.final_score == 0.4
        assert b.trust_multiplier == 1.0
        assert "ranking_v2_disabled" in b.reasons

    def test_trust_multipliers(self):
        assert trust_multiplier(5) > trust_multiplier(3)
        assert trust_multiplier(1) < trust_multiplier(3)
        assert trust_multiplier(None) == 1.0

    def test_license_zeroed_for_bad_outcomes(self):
        assert license_multiplier("strong_copyleft") == 0.0
        assert license_multiplier("proprietary") == 0.0
        assert license_multiplier("permissive") == 1.0

    def test_recency_boost_and_stale(self):
        now = datetime.now(timezone.utc)
        young = (now - timedelta(days=5)).isoformat()
        stale = (now - timedelta(days=400)).isoformat()
        assert recency_multiplier(young, now=now) > 1.0
        assert recency_multiplier(stale, now=now) < 1.0
        assert recency_multiplier(None, now=now) == 1.0

    def test_endorsement_boost_capped(self):
        assert endorsement_multiplier(0) == 1.0
        assert endorsement_multiplier(3) > 1.0
        # 100 endorsements → capped at +20 %
        assert endorsement_multiplier(1000) == 1.20

    def test_compose_v2_zeroes_bad_license(self, monkeypatch):
        monkeypatch.setenv("UKIE_RANKING_V2_ENABLED", "true")
        b = compose(base_similarity=0.9, trust_tier=5,
                    license_outcome="proprietary")
        assert b.final_score == 0.0
        assert any("license_zeroed" in r for r in b.reasons)

    def test_compose_v2_boosts_high_trust_permissive(self, monkeypatch):
        monkeypatch.setenv("UKIE_RANKING_V2_ENABLED", "true")
        b = compose(base_similarity=0.5, trust_tier=5,
                    license_outcome="permissive",
                    endorsements_30d=5,
                    inserted_at_iso=datetime.now(timezone.utc).isoformat())
        assert b.final_score > 0.5


# ── Retrieval — rule-based similarity ────────────────────────────────

class TestRuleBasedSimilarity:
    def test_no_overlap(self):
        assert rule_based_similarity("alpha beta", "gamma delta") == 0.0

    def test_full_overlap(self):
        # tokens must be ≥ 2 chars (see _TOKEN_RE)
        assert rule_based_similarity("alpha beta gamma", "alpha beta gamma") == 1.0

    def test_partial_overlap(self):
        s = rule_based_similarity("regime detection model", "regime shift model paper")
        assert 0.0 < s < 1.0


# ── Retrieval — engine ───────────────────────────────────────────────

def _seed_kb_row(db, coll_name, *, kb_id, domain, text, tier=4, outcome="permissive"):
    db[coll_name]._docs.append({
        "_id":          kb_id,
        "domain":       domain,
        "content_text": text,
        "trust_tier":   tier,
        "license":      "MIT",
        "license_verdict": {"outcome": outcome},
        "inserted_at":  datetime.now(timezone.utc).isoformat(),
        "learning_only": True,
        "eligible_for_deploy": False,
    })


class TestRetrieval:
    @pytest.mark.asyncio
    async def test_query_returns_matches_flag_off_ranking(self, monkeypatch):
        # Flag off — ranking v2 = identity, but retrieval itself works
        monkeypatch.delenv("UKIE_RANKING_V2_ENABLED", raising=False)
        db = _FakeDB()
        # Use `research` domain — its ai_context_policy is `summary`
        # so `content_preview` must be omitted from the response.
        db["research"]._docs.extend([
            {"_id": "r1", "domain": "research",
             "content_text": "regime detection RSI momentum",
             "trust_tier": 4, "license": "MIT",
             "license_verdict": {"outcome": "permissive"},
             "inserted_at": datetime.now(timezone.utc).isoformat(),
             "learning_only": True, "eligible_for_deploy": False},
            {"_id": "r2", "domain": "research",
             "content_text": "mean reversion bollinger",
             "trust_tier": 4, "license": "MIT",
             "license_verdict": {"outcome": "permissive"},
             "inserted_at": datetime.now(timezone.utc).isoformat(),
             "learning_only": True, "eligible_for_deploy": False},
        ])
        e = RetrievalEngine(kb_db_getter=lambda: db)
        r = await e.query(QueryRequest(domain="research",
                                         query="regime detection",
                                         top_k=5))
        assert r["status"] == "ok"
        # r1 should score higher (more overlap)
        assert r["matches"][0]["kb_id"] == "r1"
        # Content preview OMITTED — research domain policy is `summary`
        assert r["matches"][0]["content_preview"] is None
        # Hard rails carried in the response
        assert r["matches"][0]["learning_only"] is True
        assert r["matches"][0]["eligible_for_deploy"] is False

    @pytest.mark.asyncio
    async def test_quote_domain_returns_preview(self, monkeypatch):
        # STRATEGY domain — policy is `quote` — preview IS returned
        db = _FakeDB()
        _seed_kb_row(db, "strategies", kb_id="s1", domain="strategy",
                     text="regime detection RSI momentum")
        e = RetrievalEngine(kb_db_getter=lambda: db)
        r = await e.query(QueryRequest(domain="strategy",
                                         query="regime detection"))
        assert r["matches"][0]["content_preview"] is not None

    @pytest.mark.asyncio
    async def test_min_trust_tier_filters(self, monkeypatch):
        db = _FakeDB()
        _seed_kb_row(db, "strategies", kb_id="lo", domain="strategy",
                     text="regime detection", tier=2)
        _seed_kb_row(db, "strategies", kb_id="hi", domain="strategy",
                     text="regime detection", tier=5)
        e = RetrievalEngine(kb_db_getter=lambda: db)
        r = await e.query(QueryRequest(domain="strategy",
                                         query="regime detection",
                                         top_k=5, min_trust_tier=4))
        ids = [m["kb_id"] for m in r["matches"]]
        assert "hi" in ids and "lo" not in ids

    @pytest.mark.asyncio
    async def test_license_whitelist_filters(self, monkeypatch):
        db = _FakeDB()
        _seed_kb_row(db, "strategies", kb_id="perm", domain="strategy",
                     text="regime", outcome="permissive")
        _seed_kb_row(db, "strategies", kb_id="prop", domain="strategy",
                     text="regime", outcome="proprietary")
        e = RetrievalEngine(kb_db_getter=lambda: db)
        r = await e.query(QueryRequest(domain="strategy", query="regime",
                                         license_outcomes=["permissive"]))
        ids = [m["kb_id"] for m in r["matches"]]
        assert "perm" in ids and "prop" not in ids

    @pytest.mark.asyncio
    async def test_zero_similarity_omitted(self, monkeypatch):
        db = _FakeDB()
        _seed_kb_row(db, "strategies", kb_id="s", domain="strategy",
                     text="completely unrelated body")
        e = RetrievalEngine(kb_db_getter=lambda: db)
        r = await e.query(QueryRequest(domain="strategy", query="regime detection"))
        assert r["match_count"] == 0


# ── Lifecycle ────────────────────────────────────────────────────────

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_flag_off_returns_marker(self, monkeypatch):
        monkeypatch.delenv("UKIE_LIFECYCLE_SWEEP_ENABLED", raising=False)
        s = LifecycleSweeper(kb_db_getter=lambda: _FakeDB())
        out = await s.sweep()
        assert out.per_domain and out.per_domain[0]["reason"] == "flag_off"

    @pytest.mark.asyncio
    async def test_dry_run_reports_no_writes(self, monkeypatch):
        monkeypatch.setenv("UKIE_LIFECYCLE_SWEEP_ENABLED", "true")
        db = _FakeDB()
        # Strategy domain has retention="forever" → nothing expires there
        _seed_kb_row(db, "strategies", kb_id="s1", domain="strategy",
                     text="body")
        # Market domain has retention "365d" — seed a stale row
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        db["market"]._docs.append({
            "_id": "m1", "domain": "market", "content_text": "old",
            "inserted_at": stale_ts, "trust_tier": 3,
            "license_verdict": {"outcome": "permissive"},
        })
        s = LifecycleSweeper(kb_db_getter=lambda: db)
        out = await s.sweep(dry_run=True)
        # Strategy sub-collection reports `forever_no_ttl`
        strat = next(p for p in out.per_domain if p.get("domain") == "strategy")
        assert strat["reason"] == "forever_no_ttl"
        # market row seen and would be deleted in dry-run
        mkt = next(p for p in out.per_domain if p.get("domain") == "market")
        assert mkt["scanned"] == 1
        assert mkt["deleted"] == 1
        # No actual delete happened
        assert len(db["market"]._docs) == 1
        # No audit event in dry-run
        assert len(db[LIFECYCLE_EVENTS_COLLECTION]._docs) == 0

    @pytest.mark.asyncio
    async def test_commit_deletes_and_audits(self, monkeypatch):
        monkeypatch.setenv("UKIE_LIFECYCLE_SWEEP_ENABLED", "true")
        db = _FakeDB()
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        db["market"]._docs.append({
            "_id": "m1", "domain": "market",
            "inserted_at": stale_ts, "content_text": "x",
        })
        s = LifecycleSweeper(kb_db_getter=lambda: db)
        out = await s.sweep(dry_run=False)
        # Row physically removed
        assert len(db["market"]._docs) == 0
        # Audit event landed for `market`
        events = [e for e in db[LIFECYCLE_EVENTS_COLLECTION]._docs
                  if e.get("domain") == "market"]
        assert len(events) == 1
        assert events[0]["deleted_count"] == 1


# ── Confidence ───────────────────────────────────────────────────────

class TestConfidence:
    @pytest.mark.asyncio
    async def test_flag_off(self, monkeypatch):
        monkeypatch.delenv("UKIE_CONFIDENCE_EVOLUTION_ENABLED", raising=False)
        s = ConfidenceStore(kb_db_getter=lambda: _FakeDB())
        r = await s.record_endorsement(kb_id="x", domain="strategy")
        assert r["status"] == "flag_off"
        assert await s.endorsements_last_30d(kb_id="x") == 0

    @pytest.mark.asyncio
    async def test_endorsement_recorded(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONFIDENCE_EVOLUTION_ENABLED", "true")
        db = _FakeDB()
        s = ConfidenceStore(kb_db_getter=lambda: db)
        # Seed 3 endorsements in the last 30d
        for _ in range(3):
            await s.record_endorsement(kb_id="x", domain="strategy")
        assert len(db[ENDORSEMENT_EVENTS_COLLECTION]._docs) == 3
        assert await s.endorsements_last_30d(kb_id="x") == 3

    @pytest.mark.asyncio
    async def test_contradiction_sets_contested(self, monkeypatch):
        monkeypatch.setenv("UKIE_CONFIDENCE_EVOLUTION_ENABLED", "true")
        db = _FakeDB()
        # Pre-seed the KB rows so the update lands
        db["strategies"]._docs.extend([
            {"_id": "a", "domain": "strategy", "trust_tier": 5},
            {"_id": "b", "domain": "strategy", "trust_tier": 5},
        ])
        s = ConfidenceStore(kb_db_getter=lambda: db)
        r = await s.record_contradiction(
            domain="strategy", kb_id_a="a", kb_id_b="b",
            reason="opposite conclusions",
        )
        assert r["status"] == "recorded"
        assert len(db[CONTRADICTION_EVENTS_COLLECTION]._docs) == 1
        # Both rows now carry contested=true
        for d in db["strategies"]._docs:
            assert d.get("contested") is True


# ── Governance policy ────────────────────────────────────────────────

class TestGovernancePolicy:
    def test_condition_operators(self):
        r = {"trust_tier": 5, "license_verdict": {"outcome": "permissive"},
             "endorsements_30d": 4, "contested": False}
        assert _eval_condition(r, {"field": "trust_tier", "op": ">=", "value": 5})
        assert not _eval_condition(r, {"field": "trust_tier", "op": ">=", "value": 6})
        assert _eval_condition(r, {"field": "license_outcome", "op": "in",
                                    "value": ["permissive"]})
        assert not _eval_condition(r, {"field": "contested", "op": "==", "value": True})
        assert _eval_condition(r, {"field": "contested", "op": "==", "value": False})

    @pytest.mark.asyncio
    async def test_flag_off_returns_empty(self, monkeypatch):
        monkeypatch.delenv("UKIE_GOVERNANCE_POLICY_ENABLED", raising=False)
        e = GovernancePolicyEngine(
            policy_loader=lambda: {"policy_id": "v1", "policy_version": 1, "rules": []},
        )
        v = await e.evaluate({"trust_tier": 5, "_id": "x"})
        assert v.actions == []
        assert v.matched_rules == []

    @pytest.mark.asyncio
    async def test_advisory_tags_produced_when_rule_matches(self, monkeypatch):
        monkeypatch.setenv("UKIE_GOVERNANCE_POLICY_ENABLED", "true")
        policy = {
            "policy_id": "v1", "policy_version": 1,
            "rules": [
                {"name": "auto-promote",
                 "all_of": [
                     {"field": "trust_tier",      "op": ">=", "value": 5},
                     {"field": "license_outcome", "op": "in", "value": ["permissive"]},
                     {"field": "contested",       "op": "==", "value": False},
                 ],
                 "action": "flag_as_auto_promote_candidate"},
                {"name": "quarantine",
                 "all_of": [{"field": "contested", "op": "==", "value": True}],
                 "action": "flag_as_needs_review"},
            ],
        }
        e = GovernancePolicyEngine(policy_loader=lambda: policy)
        row = {"_id": "x", "trust_tier": 5,
               "license_verdict": {"outcome": "permissive"},
               "contested": False}
        v = await e.evaluate(row)
        assert v.actions == ["flag_as_auto_promote_candidate"]
        assert v.matched_rules == ["auto-promote"]

    @pytest.mark.asyncio
    async def test_write_verdict_stamps_advisory_tags(self, monkeypatch):
        monkeypatch.setenv("UKIE_GOVERNANCE_POLICY_ENABLED", "true")
        db = _FakeDB()
        # Seed a full KB row (governance never touches these fields)
        db["strategies"]._docs.append({
            "_id": "x", "domain": "strategy", "trust_tier": 5,
            "learning_only": True, "eligible_for_deploy": False,
        })
        e = GovernancePolicyEngine(
            kb_db_getter=lambda: db,
            policy_loader=lambda: {
                "policy_id": "v1", "policy_version": 1,
                "rules": [{"name": "n",
                           "all_of": [{"field": "trust_tier", "op": ">=", "value": 5}],
                           "action": "flag_as_auto_promote_candidate"}],
            },
        )
        row = {"_id": "x", "trust_tier": 5}
        v = await e.evaluate(row)
        r = await e.write_verdict(v, domain="strategy")
        assert r["status"] == "stamped"
        stored = db["strategies"]._docs[0]
        assert stored["advisory_tags"] == ["flag_as_auto_promote_candidate"]
        # Governance MUST NEVER mutate hard-rail-adjacent fields
        assert stored["trust_tier"] == 5
        assert stored["learning_only"] is True
        assert stored["eligible_for_deploy"] is False


# ── Router ───────────────────────────────────────────────────────────

def _make_app():
    from engines.knowledge.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestRouter:
    def test_all_p4c_endpoints_503_when_off(self, monkeypatch):
        for f in ("UKIE_QUERY_API_ENABLED", "UKIE_LIFECYCLE_SWEEP_ENABLED",
                  "UKIE_CONFIDENCE_EVOLUTION_ENABLED",
                  "UKIE_GOVERNANCE_POLICY_ENABLED"):
            monkeypatch.delenv(f, raising=False)
        with TestClient(_make_app()) as c:
            assert c.post("/api/knowledge/query",
                          json={"query": "x"}).status_code == 503
            assert c.post("/api/knowledge/lifecycle-sweep",
                          json={}).status_code == 503
            assert c.post("/api/knowledge/endorsement",
                          json={"kb_id": "x", "domain": "strategy"}).status_code == 503
            assert c.post("/api/knowledge/contradiction",
                          json={"domain": "strategy", "kb_id_a": "a",
                                "kb_id_b": "b", "reason": "x"}).status_code == 503
            assert c.post("/api/knowledge/governance/evaluate/x",
                          json={"domain": "strategy"}).status_code == 503

    def test_query_endpoint_when_on(self, monkeypatch):
        monkeypatch.setenv("UKIE_QUERY_API_ENABLED", "true")
        db = _FakeDB()
        _seed_kb_row(db, "strategies", kb_id="s1", domain="strategy",
                     text="regime detection momentum")
        import engines.knowledge.retrieval as ret
        ret._reset_for_tests()
        monkeypatch.setattr(
            "engines.knowledge.ukie_gamma_router.get_retrieval_engine",
            lambda: RetrievalEngine(kb_db_getter=lambda: db),
        )
        with TestClient(_make_app()) as c:
            r = c.post("/api/knowledge/query",
                       json={"query": "regime detection", "domain": "strategy"})
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "ok"
            assert body["matches"][0]["kb_id"] == "s1"

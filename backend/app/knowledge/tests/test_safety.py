"""Safety-invariant tests for the Knowledge subsystem.

These tests are the guard on the guards. They lock in three invariants
that are the whole point of Phase 1.6:

1. ``canonical_hash`` collapses constants but respects parameter shape.
2. ``StrategyRepository`` refuses to bypass ``eligible_for_deploy``.
3. ``KnowledgeRepository`` refuses every write method.

Run: ``pytest backend/app/knowledge/tests/test_safety.py``
"""

from __future__ import annotations

import pytest

from app.knowledge.canonical import canonical_hash, normalise_strategy_text
from app.knowledge.evaluation import (
    DeploymentReadiness,
    evaluate_from_legacy_metrics,
)
from app.knowledge.repository import (
    KnowledgeRepository,
    StrategyRepository,
    _ImmutableError,  # noqa: SLF001 — testing the guard
)
from app.knowledge.similarity import (
    RuleBasedSimilarity,
    StrategyQuery,
)


# ── canonical_hash ─────────────────────────────────────────────────

def test_canonical_hash_ignores_constants():
    a = canonical_hash("ATR(14) breakout with SL=1.5", {"atr_sl_mult": 1.5})
    b = canonical_hash("ATR(21) breakout with SL=2.0", {"atr_sl_mult": 2.0})
    assert a == b, "numbers must be collapsed → same family"


def test_canonical_hash_respects_parameter_shape():
    a = canonical_hash("same text", {"a": 1})
    b = canonical_hash("same text", {"a": 1, "b": 2})
    assert a != b, "adding a new parameter key must fork the family"


def test_canonical_hash_strips_provenance():
    a = canonical_hash("STRATEGY: X\nDERIVED FROM: seed_42", {})
    b = canonical_hash("STRATEGY: X\nDERIVED FROM: seed_99", {})
    assert a == b, "DERIVED FROM annotation must be scrubbed"


def test_normalise_returns_str():
    assert isinstance(normalise_strategy_text("hello 123"), str)
    assert normalise_strategy_text(None) == ""


# ── evaluation ─────────────────────────────────────────────────────

def test_evaluation_never_awards_ready():
    """The pure-metrics evaluator MUST NOT emit READY.

    Only the current-framework governance pipeline can promote a
    strategy to READY. This test locks the readiness ceiling.
    """
    perfect = evaluate_from_legacy_metrics({
        "profit_factor": 3.0,
        "total_return_pct": 500.0,
        "stability_score": 100.0,
        "max_drawdown_pct": 0.0,
        "win_rate": 90.0,
        "total_trades": 5000,
        "oos_holdout": {"passes": 12, "fails": 0},  # even with perfect OOS
    }, legacy_decision_scores={"overfit": 0.0})
    assert perfect.deployment_readiness != DeploymentReadiness.READY
    assert perfect.deployment_readiness == DeploymentReadiness.PENDING_VALIDATION


def test_evaluation_needs_oos():
    ev = evaluate_from_legacy_metrics({
        "profit_factor": 1.5, "total_return_pct": 40, "stability_score": 80,
        "max_drawdown_pct": 0.1, "win_rate": 55, "total_trades": 500,
        "oos_holdout": None,
    })
    assert ev.deployment_readiness == DeploymentReadiness.NEEDS_OOS_HOLDOUT


def test_evaluation_dimensions_independent():
    """A profitable strategy can still carry high overfit risk."""
    ev = evaluate_from_legacy_metrics(
        {"profit_factor": 2.0, "total_return_pct": 100, "stability_score": 45,
         "max_drawdown_pct": 0.05, "win_rate": 60, "total_trades": 100,
         "oos_holdout": None},
        legacy_decision_scores={"overfit": 85.0},
    )
    assert ev.profitability is not None and ev.profitability > 60
    assert ev.overfit_risk == 85.0
    # High profit + high overfit is exactly the case the old "verdict"
    # collapsed into a single label. We now expose both cleanly.


# ── StrategyRepository (production safety) ─────────────────────────

class _FakeCollection:
    """In-memory pymongo-shaped stub for repo tests."""
    def __init__(self):
        self.last_filter = None
        self.name = "fake"
    def find(self, filter, *a, **kw): self.last_filter = filter; return iter([])
    def find_one(self, filter, *a, **kw): self.last_filter = filter; return None
    def count_documents(self, filter, *a, **kw): self.last_filter = filter; return 0
    def aggregate(self, pipeline, *a, **kw): return iter(pipeline)
    def insert_one(self, *a, **kw): return "inserted"
    def update_one(self, *a, **kw): return "updated"
    def delete_one(self, *a, **kw): return "deleted"


def test_strategy_repo_injects_eligible_for_deploy():
    coll = _FakeCollection()
    repo = StrategyRepository(coll)
    list(repo.find({"pair": "XAUUSD"}))
    assert coll.last_filter == {
        "pair": "XAUUSD",
        "eligible_for_deploy": {"$ne": False},
    }


def test_strategy_repo_rejects_conflicting_override():
    coll = _FakeCollection()
    repo = StrategyRepository(coll)
    # Caller explicitly trying to reach KB rows must be refused.
    with pytest.raises(_ImmutableError):
        list(repo.find({"eligible_for_deploy": False}))


def test_strategy_repo_backward_compat_semantics():
    """The safety filter uses ``$ne: False`` — a doc without the field
    remains visible, a doc explicitly ``False`` is filtered out.

    This proves the filter is deployable *before* the strategies
    collection is backfilled with the field."""
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    tmp = client["strategy_repo_test_ephemeral"]["strategies"]
    tmp.drop()
    tmp.insert_many([
        {"strategy_id": "no_field",    "pair": "X"},                          # legacy prod
        {"strategy_id": "true_field",  "pair": "X", "eligible_for_deploy": True},
        {"strategy_id": "false_field", "pair": "X", "eligible_for_deploy": False},  # KB row
    ])
    repo = StrategyRepository(tmp)
    visible = {d["strategy_id"] for d in repo.find({})}
    assert visible == {"no_field", "true_field"}
    assert "false_field" not in visible
    tmp.database.drop_collection("strategies")


def test_strategy_repo_passes_writes_through():
    coll = _FakeCollection()
    repo = StrategyRepository(coll)
    # Writes are NOT filtered — that's a governance-side concern.
    assert repo.insert_one({}) == "inserted"
    assert repo.update_one({}, {}) == "updated"
    assert repo.delete_one({}) == "deleted"


# ── KnowledgeRepository (read-only KB) ─────────────────────────────

class _FakeDatabase:
    def __init__(self, coll): self._coll = coll
    def __getitem__(self, _n): return self._coll


def test_knowledge_repo_injects_learning_only():
    coll = _FakeCollection()
    repo = KnowledgeRepository(_FakeDatabase(coll), "any")
    list(repo.find({"pair": "XAUUSD"}))
    assert coll.last_filter == {"pair": "XAUUSD", "learning_only": True}


def test_knowledge_repo_refuses_all_writes():
    coll = _FakeCollection()
    repo = KnowledgeRepository(_FakeDatabase(coll), "any")
    for method in ("insert_one", "insert_many", "update_one", "update_many",
                   "delete_one", "delete_many", "replace_one"):
        with pytest.raises(_ImmutableError):
            getattr(repo, method)({})


def test_knowledge_repo_aggregate_prepends_guard():
    coll = _FakeCollection()
    repo = KnowledgeRepository(_FakeDatabase(coll), "any")
    result = list(repo.aggregate([{"$group": {"_id": "$pair"}}]))
    assert result[0] == {"$match": {"learning_only": True}}


# ── Similarity backend ─────────────────────────────────────────────

def test_rule_based_similarity_scores_reasonably():
    query = StrategyQuery(
        strategy_text="ATR breakout on H4 with 1.5 SL and 3.0 TP",
        parameters={"atr_period": 14, "sl_mult": 1.5, "tp_mult": 3.0},
        pair="XAUUSD",
        timeframe="H4",
    )
    corpus = [
        {"strategy_id": "identical",
         "pair": "XAUUSD", "timeframe": "H4",
         "canonical_hash": canonical_hash(
             "ATR breakout on H4 with 2.0 SL and 4.0 TP",
             {"atr_period": 14, "sl_mult": 1.5, "tp_mult": 3.0}),
         "strategy_text": "ATR breakout on H4 with 2.0 SL and 4.0 TP",
         "parameter_keys": ["atr_period", "sl_mult", "tp_mult"]},
        {"strategy_id": "unrelated",
         "pair": "XAUUSD", "timeframe": "H4",
         "canonical_hash": "0000000000000000",
         "strategy_text": "session-based EMA cross on GBPJPY",
         "parameter_keys": ["ema_fast", "ema_slow"]},
        {"strategy_id": "wrong_pair",
         "pair": "EURUSD", "timeframe": "H4",
         "strategy_text": "ATR breakout on H4",
         "parameter_keys": ["atr_period"]},
    ]
    top = RuleBasedSimilarity().rank(query, corpus, top_k=5)
    # "wrong_pair" must be filtered out entirely by the hard pair filter
    ids = [m.strategy_id for m in top]
    assert "wrong_pair" not in ids
    # "identical" must rank first
    assert top[0].strategy_id == "identical"
    assert "same_canonical_family" in top[0].similarity_reasons

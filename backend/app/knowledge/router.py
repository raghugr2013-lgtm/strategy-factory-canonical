"""FastAPI router for the Knowledge subsystem — mounted at ``/api/knowledge``.

Contract stability guarantee: the request/response shape of every
endpoint here is stable across backend swaps. When the embedding
backend replaces :class:`~.similarity.RuleBasedSimilarity`, the same
JSON shape MUST come back; only the ``backend`` field in the envelope
will change. That contract is why ``SimilarityMatch`` is a
dataclass with named fields rather than a raw row from Mongo.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .canonical import canonical_hash
from .evaluation import DeploymentReadiness, evaluate_from_legacy_metrics
from .repository import KnowledgeRepository
from .similarity import (
    RuleBasedSimilarity,
    SimilarityBackend,
    StrategyQuery,
)


# ── Router + backend selection ──────────────────────────────────────

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _default_repo() -> KnowledgeRepository:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    return KnowledgeRepository.open(
        mongo_url,
        collection_name="strategy_kb_view",
        db_name=os.environ.get("KNOWLEDGE_DB_NAME") or None,
    )


def _select_backend() -> SimilarityBackend:
    name = os.environ.get("SIMILARITY_BACKEND", "rule_based").lower()
    if name == "rule_based":
        return RuleBasedSimilarity()
    if name == "embedding":
        from .similarity import EmbeddingSimilarityStub
        return EmbeddingSimilarityStub()
    # Unknown value → default to rule_based rather than crashing at boot.
    return RuleBasedSimilarity()


# ── Request/response schemas ────────────────────────────────────────

class NearestRequest(BaseModel):
    strategy_text: str = Field(..., min_length=1, max_length=32_000)
    parameters: dict[str, Any] | None = None
    pair: str | None = Field(None, description="Optional hard filter, e.g. XAUUSD")
    timeframe: str | None = Field(None, description="Optional hard filter, e.g. H4")
    top_k: int = Field(5, ge=1, le=50)


class SimilarityMatchOut(BaseModel):
    strategy_id: str
    similarity_score: float
    similarity_reasons: list[str]
    canonical_hash: str | None
    pair: str | None
    timeframe: str | None
    strategy_type: str | None
    legacy_metrics: dict[str, Any] | None
    rescored: dict[str, Any] | None
    evaluation: dict[str, Any] | None = None
    # ── permanent guardrails ────────────────────────────────────────
    learning_only: bool = True
    eligible_for_deploy: bool = False


class NearestResponse(BaseModel):
    query_canonical_hash: str
    backend: str
    total_corpus: int
    matches: list[SimilarityMatchOut]
    guardrails: dict[str, Any] = Field(
        default_factory=lambda: {
            "learning_only": True,
            "eligible_for_deploy": False,
            "note": "Results are historical knowledge. None are approved "
                    "for deployment. Any candidate must be re-inserted "
                    "cold through the strategies API and pass the full "
                    "current-framework pipeline first.",
        }
    )


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/nearest", response_model=NearestResponse)
async def nearest(payload: NearestRequest = Body(...)) -> NearestResponse:
    """Retrieve the top-k historical strategies most similar to a query.

    Similarity is computed by the currently-configured backend (default
    ``rule_based``). Every result carries the row-level
    ``learning_only``/``eligible_for_deploy`` guardrails plus a split
    six-dimensional evaluation reconstructed from the historical
    metrics.
    """
    repo = _default_repo()
    backend = _select_backend()

    q = StrategyQuery(
        strategy_text=payload.strategy_text,
        parameters=payload.parameters,
        pair=payload.pair,
        timeframe=payload.timeframe,
    )

    # We pull the whole KB view (140 rows in the historical corpus —
    # cheap). When the KB grows, switch to a coarse pre-filter here.
    corpus = list(repo.find({}, {"_id": 0}))
    matches = backend.rank(q, corpus, payload.top_k)

    out: list[SimilarityMatchOut] = []
    for m in matches:
        ev = None
        if m.legacy_metrics:
            try:
                ev = evaluate_from_legacy_metrics(m.legacy_metrics).model_dump()
            except Exception:  # noqa: BLE001 — non-fatal enrichment
                ev = None
        out.append(SimilarityMatchOut(**{**asdict(m), "evaluation": ev}))

    return NearestResponse(
        query_canonical_hash=canonical_hash(payload.strategy_text, payload.parameters),
        backend=backend.name,
        total_corpus=len(corpus),
        matches=out,
    )


@router.get("/families/{canonical_hash_key}")
async def family_members(canonical_hash_key: str) -> dict[str, Any]:
    """Retrieve all KB strategies sharing a canonical structural family."""
    repo = _default_repo()
    rows = list(repo.find({"canonical_hash": canonical_hash_key}, {"_id": 0}))
    if not rows:
        raise HTTPException(status_code=404, detail="canonical_hash not found in KB")
    return {
        "canonical_hash": canonical_hash_key,
        "size": len(rows),
        "members": rows,
        "guardrails": {"learning_only": True, "eligible_for_deploy": False},
    }


@router.get("/champions")
async def champions() -> dict[str, Any]:
    """Return the champion strategies produced by Phase 1.5 analysis."""
    # Champions live in a sibling collection, still under the KB DB —
    # bind a new repo instance to reuse the safety guards.
    repo = KnowledgeRepository.open(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
        collection_name="strategy_kb_champions",
    )
    rows = list(repo.find({}, {"_id": 0}))
    return {
        "categories": {row["category"]: row["rows"] for row in rows},
        "guardrails": {"learning_only": True, "eligible_for_deploy": False},
    }


@router.get("/statistics")
async def statistics() -> dict[str, Any]:
    """High-level KB metrics for dashboards."""
    repo = _default_repo()
    total = repo.count_documents({})

    # Family-count via aggregation. Guardrail is auto-prepended.
    fam_pipe = [
        {"$group": {"_id": "$canonical_hash", "n": {"$sum": 1}}},
        {"$group": {"_id": None, "families": {"$sum": 1},
                    "multi": {"$sum": {"$cond": [{"$gt": ["$n", 1]}, 1, 0]}}}},
    ]
    fam_agg = list(repo.aggregate(fam_pipe))
    families = multi = 0
    if fam_agg:
        families = fam_agg[0].get("families", 0)
        multi = fam_agg[0].get("multi", 0)

    # Pair breakdown
    pair_agg = list(repo.aggregate([
        {"$group": {"_id": "$pair", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]))

    # Positive-return subset
    positive = repo.count_documents({
        "legacy_metrics.profit_factor": {"$gt": 1.0},
        "legacy_metrics.total_return_pct": {"$gt": 0},
    })

    return {
        "total_strategies": total,
        "canonical_families": families,
        "multi_member_families": multi,
        "pair_distribution": {r["_id"]: r["n"] for r in pair_agg},
        "positive_return_pf_gt_1": positive,
        "guardrails": {"learning_only": True, "eligible_for_deploy": False},
        "backend_available": {
            "rule_based": True,
            "embedding": False,  # Phase 2 — see similarity.EmbeddingSimilarityStub
        },
    }


@router.get("/strategy/{strategy_id}")
async def strategy_detail(strategy_id: str) -> dict[str, Any]:
    """Retrieve one KB entry with its full re-scored evaluation."""
    repo = _default_repo()
    row = repo.find_one({"strategy_id": strategy_id}, {"_id": 0})
    if not row:
        raise HTTPException(status_code=404, detail="strategy not found in KB")
    ev = None
    if row.get("legacy_metrics"):
        try:
            ev = evaluate_from_legacy_metrics(row["legacy_metrics"]).model_dump()
        except Exception:  # noqa: BLE001
            ev = None
    row["evaluation"] = ev
    row["guardrails"] = {"learning_only": True, "eligible_for_deploy": False}
    return row


@router.get("/health")
async def health() -> dict[str, Any]:
    """Cheap health probe — confirms KB DB is reachable and non-empty."""
    try:
        repo = _default_repo()
        n = repo.count_documents({})
        return {
            "status": "ok" if n > 0 else "empty",
            "corpus_size": n,
            "backend": _select_backend().name,
            "readiness_ceiling": DeploymentReadiness.PENDING_VALIDATION.value,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503,
                            detail=f"knowledge base unavailable: {e}") from e


def get_router() -> APIRouter:
    """Public accessor used by :mod:`app.main` to mount the router."""
    return router

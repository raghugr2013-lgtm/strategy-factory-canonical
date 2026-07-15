"""Knowledge retriever (L1).

Ranks the `strategy_knowledge_index` collection by relevance to a
(pair, timeframe, style, style_hint) request and returns top-K
neighbours + a winners/losers cohort + mutation-path histogram.

Ranking is metadata-first (deterministic, zero external deps):
    * pair exact-match       → +4.0
    * timeframe exact-match  → +2.5
    * style / strategy_type  → +1.5  (partial: +0.75)
    * indicator Jaccard      → up to +1.5
    * verdict='win'          → +1.0
    * verdict='loss'         → −0.5   (losers only surface in cohort)
    * recovered doc          → +0.25  (learning corpus preferred)

Optional TF-IDF over `knowledge_summary_text` is provided when
scikit-learn is installed — activated by KNOWLEDGE_TFIDF=true env var.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

INDEX_COLL = "strategy_knowledge_index"


@dataclass
class KnowledgeContext:
    winners: List[Dict[str, Any]] = field(default_factory=list)
    losers:  List[Dict[str, Any]] = field(default_factory=list)
    neutral: List[Dict[str, Any]] = field(default_factory=list)
    mutation_paths: List[Tuple[str, int]] = field(default_factory=list)
    lifecycle_paths: Dict[str, int] = field(default_factory=dict)
    total_scanned: int = 0
    summary_text: str = ""       # rendered by prompt_block.build_block()
    query: Dict[str, Any] = field(default_factory=dict)


def _jaccard(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def _score(row: Dict[str, Any], want: Dict[str, Any]) -> float:
    s = 0.0
    if row.get("pair") == want.get("pair"):
        s += 4.0
    if row.get("timeframe") == want.get("timeframe"):
        s += 2.5

    row_style = (row.get("style") or row.get("strategy_type") or "").lower()
    want_style = (want.get("style") or "").lower()
    if row_style == want_style and row_style:
        s += 1.5
    elif want_style and want_style in row_style:
        s += 0.75

    j = _jaccard(row.get("indicators") or [], want.get("indicators") or [])
    s += 1.5 * j

    v = row.get("verdict")
    if v == "win":
        s += 1.0
    elif v == "loss":
        s -= 0.5

    if row.get("is_recovered"):
        s += 0.25

    return s


async def _maybe_tfidf_rerank(
    ranked: List[Tuple[float, Dict[str, Any]]],
    want: Dict[str, Any],
    top_k: int,
) -> List[Tuple[float, Dict[str, Any]]]:
    """Optional sklearn TF-IDF pass. Enabled with KNOWLEDGE_TFIDF=true.
    No-op fallback if sklearn isn't installed."""
    if os.environ.get("KNOWLEDGE_TFIDF", "").lower() not in ("true", "1", "yes", "on"):
        return ranked
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception:  # noqa: BLE001
        return ranked
    query_text = (
        f"{want.get('style','')} {want.get('strategy_type','')} "
        f"{' '.join(want.get('indicators', []))} {want.get('pair','')} {want.get('timeframe','')}"
    ).strip()
    docs = [(r.get("knowledge_summary_text") or "") for _, r in ranked]
    if not query_text or not any(docs):
        return ranked
    try:
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
        m = vec.fit_transform([query_text] + docs)
        sims = cosine_similarity(m[0:1], m[1:]).flatten()
        boosted = []
        for i, (base_score, row) in enumerate(ranked):
            row = dict(row)
            row["_tfidf"] = float(sims[i])
            boosted.append((base_score + 1.5 * float(sims[i]), row))
        boosted.sort(key=lambda x: x[0], reverse=True)
        return boosted[: max(top_k, 20)]
    except Exception:  # noqa: BLE001
        return ranked


async def retrieve(
    *,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    style: Optional[str] = None,
    strategy_type: Optional[str] = None,
    indicators: Optional[List[str]] = None,
    top_k: int = 8,
    include_failures: bool = True,
    limit_candidates: int = 300,
) -> KnowledgeContext:
    """Return the top-K nearest historical strategies for (pair, tf, style).

    Deterministic scan — fetches up to `limit_candidates` docs
    from the index (filtered by pair when supplied), scores each in
    Python, then returns cohorts.
    """
    db = get_db()
    want = {
        "pair":         (pair or "").upper(),
        "timeframe":    (timeframe or "").lower(),
        "style":        (style or "").lower(),
        "strategy_type": (strategy_type or "").lower(),
        "indicators":   [str(x).lower() for x in (indicators or [])],
    }
    query: Dict[str, Any] = {}
    if want["pair"]:
        # Boost hit-rate by filtering to same-pair rows first, but keep
        # a fallback if nothing matches.
        query["pair"] = want["pair"]

    scanned: List[Dict[str, Any]] = []
    try:
        async for row in db[INDEX_COLL].find(query, {"__index_ts": 0}).limit(limit_candidates):
            scanned.append(row)
    except Exception:  # noqa: BLE001
        logger.exception("knowledge.retrieve: index scan failed")
        scanned = []

    if not scanned and query:
        # widen: no same-pair matches → scan the whole index
        try:
            async for row in db[INDEX_COLL].find({}, {"__index_ts": 0}).limit(limit_candidates):
                scanned.append(row)
        except Exception:  # noqa: BLE001
            scanned = []

    ranked: List[Tuple[float, Dict[str, Any]]] = [(_score(r, want), r) for r in scanned]
    ranked.sort(key=lambda x: x[0], reverse=True)
    ranked = ranked[: max(top_k * 3, 20)]
    ranked = await _maybe_tfidf_rerank(ranked, want, top_k)

    winners:  List[Dict[str, Any]] = []
    losers:   List[Dict[str, Any]] = []
    neutral:  List[Dict[str, Any]] = []
    mut_hist: Dict[str, int] = {}
    life_hist: Dict[str, int] = {}

    for score, row in ranked:
        row = dict(row)
        row["_score"] = round(float(score), 4)
        v = row.get("verdict") or "neutral"
        if v == "win" and len(winners) < top_k:
            winners.append(row)
        elif v == "loss" and include_failures and len(losers) < top_k:
            losers.append(row)
        elif v == "neutral" and len(neutral) < top_k:
            neutral.append(row)
        family = row.get("mutation_family")
        if family:
            mut_hist[family] = mut_hist.get(family, 0) + 1
        stage = row.get("lifecycle_terminal_stage")
        if stage:
            life_hist[stage] = life_hist.get(stage, 0) + 1

    ctx = KnowledgeContext(
        winners=winners,
        losers=losers,
        neutral=neutral,
        mutation_paths=sorted(mut_hist.items(), key=lambda x: x[1], reverse=True)[:8],
        lifecycle_paths=life_hist,
        total_scanned=len(scanned),
        query=want,
    )
    return ctx

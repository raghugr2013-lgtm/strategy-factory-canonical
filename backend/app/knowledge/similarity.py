"""Pluggable similarity backends for the Knowledge API.

Design constraint (Phase 1.6 §E): the ``/api/knowledge/nearest`` API
must be able to evolve from rule-based similarity to embedding-based
semantic search **without changing the API contract**. That means the
API-facing shape is fixed here, and the ranking logic sits behind a
:class:`Protocol` so alternative backends can be swapped in.

Two backends ship today:

* :class:`RuleBasedSimilarity` — canonical-hash exact match + Jaccard
  overlap on the parameter-key sets + token overlap on the normalised
  ``strategy_text``. Deterministic, zero-cost, no external services.

* :class:`EmbeddingSimilarityStub` — Placeholder. Raises
  :class:`NotImplementedError` if called. When the AI-provider
  integration lands, the concrete implementation replaces this class
  and the router picks it up via ``SIMILARITY_BACKEND=embedding``
  configuration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Protocol, Sequence

from .canonical import canonical_hash, normalise_strategy_text


# ── DTOs ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StrategyQuery:
    """Input to a similarity backend.

    Only ``strategy_text`` is required. The remaining fields are
    optional filters / signals that a backend MAY use to sharpen the
    match — a backend is free to ignore them.
    """
    strategy_text: str
    parameters: Mapping[str, Any] | None = None
    pair: str | None = None
    timeframe: str | None = None


@dataclass
class SimilarityMatch:
    """One ranked result. Shape is API-stable across backend swaps."""
    strategy_id: str
    similarity_score: float                    # 0..1, higher = closer
    similarity_reasons: list[str] = field(default_factory=list)
    canonical_hash: str | None = None
    pair: str | None = None
    timeframe: str | None = None
    strategy_type: str | None = None
    legacy_metrics: dict[str, Any] | None = None
    rescored: dict[str, Any] | None = None


class SimilarityBackend(Protocol):
    """The single interface any similarity backend must satisfy."""

    name: str

    def rank(
        self,
        query: StrategyQuery,
        corpus: Iterable[Mapping[str, Any]],
        top_k: int,
    ) -> list[SimilarityMatch]: ...


# ── Rule-based baseline ──────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{2,}")


def _tokenise(normalised_text: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalised_text))


def _jaccard(a: Sequence[str] | set[str], b: Sequence[str] | set[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class RuleBasedSimilarity:
    """Deterministic zero-cost baseline.

    Similarity score is a weighted mix of three signals:

    * 0.50 — canonical_hash exact match (1.0 if same family else 0.0)
    * 0.30 — Jaccard overlap of ``parameter_keys`` sets
    * 0.20 — Jaccard overlap of tokenised normalised strategy_text

    Optional hard filters: ``pair`` and ``timeframe`` are applied
    before ranking if the query supplies them. Backends are free to
    also emit *soft* pair/timeframe matches (score boost) — this one
    treats them as strict filters because operators reviewing a
    new EURUSD H4 candidate almost never want XAUUSD H1 neighbours.
    """

    name = "rule_based_v1"

    def rank(
        self,
        query: StrategyQuery,
        corpus: Iterable[Mapping[str, Any]],
        top_k: int,
    ) -> list[SimilarityMatch]:
        q_hash = canonical_hash(query.strategy_text, query.parameters)
        q_norm = normalise_strategy_text(query.strategy_text)
        q_tokens = _tokenise(q_norm)
        q_params = set((query.parameters or {}).keys())

        scored: list[SimilarityMatch] = []
        for row in corpus:
            # Hard filters
            if query.pair and row.get("pair") != query.pair:
                continue
            if query.timeframe and row.get("timeframe") != query.timeframe:
                continue

            # Signal 1: canonical hash exact match
            row_hash = row.get("canonical_hash")
            hash_signal = 1.0 if row_hash and row_hash == q_hash else 0.0

            # Signal 2: parameter-key Jaccard
            row_params = set(row.get("parameter_keys") or [])
            param_signal = _jaccard(q_params, row_params)

            # Signal 3: text-token Jaccard on normalised text
            text_signal = 0.0
            row_text = row.get("strategy_text")
            if row_text:
                r_norm = normalise_strategy_text(row_text)
                text_signal = _jaccard(q_tokens, _tokenise(r_norm))

            score = 0.50 * hash_signal + 0.30 * param_signal + 0.20 * text_signal

            reasons: list[str] = []
            if hash_signal == 1.0:
                reasons.append("same_canonical_family")
            if param_signal > 0.6:
                reasons.append(f"param_overlap={param_signal:.2f}")
            elif param_signal > 0.0:
                reasons.append(f"param_partial={param_signal:.2f}")
            if text_signal > 0.4:
                reasons.append(f"text_overlap={text_signal:.2f}")

            scored.append(SimilarityMatch(
                strategy_id=str(row.get("strategy_id") or row.get("_id")),
                similarity_score=round(score, 4),
                similarity_reasons=reasons,
                canonical_hash=row_hash,
                pair=row.get("pair"),
                timeframe=row.get("timeframe"),
                strategy_type=row.get("strategy_type"),
                legacy_metrics=row.get("legacy_metrics"),
                rescored=row.get("rescored"),
            ))

        scored.sort(key=lambda m: m.similarity_score, reverse=True)
        return scored[:top_k]


# ── Embedding backend — placeholder (Phase 2) ────────────────────────

class EmbeddingSimilarityStub:
    """Reserved for the embedding backend that will ship after
    AI-provider integration. Kept here so the router can already
    import it and select by config, and so the contract is visible."""

    name = "embedding_stub"

    def rank(
        self,
        query: StrategyQuery,
        corpus: Iterable[Mapping[str, Any]],
        top_k: int,
    ) -> list[SimilarityMatch]:
        raise NotImplementedError(
            "Embedding similarity is a Phase 2 deliverable. Configure "
            "SIMILARITY_BACKEND=rule_based (default) until then."
        )

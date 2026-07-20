"""Phase 2 Stage 4 P4C.1 — Retrieval API.

Read-only retrieval endpoint over `strategy_knowledge_base`. Zero
writes. Every request goes through the layered ranker (`ranking.compose`)
and returns matches WITHOUT raw content bytes when the domain's
`ai_context_policy` is `summary` or `off`.

Feature flag: `UKIE_QUERY_API_ENABLED` (default OFF). Endpoint returns
HTTP 503 when off.

Similarity backend:
  * `rule_based` (default) — token overlap (Jaccard-lite over
    whitespace-tokenised, lowercased content). No dependency on any
    external encoder. Deterministic.
  * Future: `embedding` — plugs behind the same `SimilarityBackend`
    Protocol from Phase-1.6 when P4C ranking-v2 gains encoder support.
    Not shipped in P4C because the encoder addition is a Stage-5
    concern.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .constants import KNOWLEDGE_DB_NAME, PIPELINE_CONTRACT_VERSION, PIPELINE_VERSION
from .domains import KnowledgeDomain, get_domain_spec, storage_collection_for
from .ranking import compose

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_query_api_enabled() -> bool:
    return _flag("UKIE_QUERY_API_ENABLED", False)


# ── Similarity ───────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")


def _tokenise(text: str) -> set:
    if not text:
        return set()
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


def rule_based_similarity(query: str, doc_text: str) -> float:
    """Jaccard-lite over lowercased token sets. Deterministic."""
    q, d = _tokenise(query), _tokenise(doc_text)
    if not q or not d:
        return 0.0
    inter = len(q & d)
    if inter == 0:
        return 0.0
    return inter / float(len(q | d))


# ── Request / result shapes ──────────────────────────────────────────

@dataclass
class QueryRequest:
    domain:            Optional[str]      = None
    query:             str                = ""
    top_k:             int                = 10
    pair:              Optional[str]      = None
    timeframe:         Optional[str]      = None
    min_trust_tier:    Optional[int]      = None
    license_outcomes:  Optional[List[str]] = None


@dataclass
class QueryMatch:
    kb_id:               str
    domain:              str
    source_url:          Optional[str]
    trust_tier:          Optional[int]
    license:             Optional[str]
    license_outcome:     Optional[str]
    similarity_score:    float
    final_score:         float
    similarity_reasons:  List[str]
    ranking_breakdown:   Dict[str, Any]
    learning_only:       bool
    eligible_for_deploy: bool
    inserted_at:         Optional[str]
    content_preview:     Optional[str]           = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Retrieval engine ─────────────────────────────────────────────────

class RetrievalEngine:
    """Read-only retrieval over `strategy_knowledge_base`.

    Injectable DB getter for tests. `similarity_fn` is also injectable
    to allow future encoder backends without changing this class.
    """

    def __init__(
        self,
        *,
        kb_db_getter: Optional[Callable] = None,
        similarity_fn: Optional[Callable[[str, str], float]] = None,
    ) -> None:
        self._kb_db_getter = kb_db_getter
        self._sim = similarity_fn or rule_based_similarity

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                  # pragma: no cover
            logger.warning("[retrieval] cannot resolve KB DB: %s", e)
            return None

    def _domains_to_scan(self, req: QueryRequest) -> List[KnowledgeDomain]:
        if req.domain:
            try:
                return [KnowledgeDomain(req.domain.strip().lower())]
            except ValueError:
                return []
        return list(KnowledgeDomain)

    def _resolve_ai_policy(self, domain: KnowledgeDomain) -> str:
        try:
            spec = get_domain_spec(domain)
            return (spec.ai_context_policy or "off").strip().lower()
        except Exception:                                       # noqa: BLE001
            return "off"

    def _extract_text(self, row: Dict[str, Any]) -> str:
        # Prefer explicit `content_text`; fall back to decoded bytes;
        # then a compact JSON-ish summary of extras.
        text = row.get("content_text")
        if isinstance(text, str) and text:
            return text
        cb = row.get("content_bytes")
        if isinstance(cb, bytes):
            try:
                return cb.decode("utf-8", errors="replace")
            except Exception:                                   # pragma: no cover
                return ""
        if isinstance(cb, str):
            return cb
        extras = row.get("extras") or {}
        parts = []
        for k in ("title", "abstract", "summary", "description"):
            v = extras.get(k)
            if isinstance(v, str) and v:
                parts.append(v)
        return " ".join(parts)

    async def query(self, req: QueryRequest) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc)
        matches: List[QueryMatch] = []
        db = self._kb_db()
        if db is None:
            return self._compose_response(req, matches, started_at, "db_unavailable")

        allowed_outcomes = frozenset(
            (o or "").strip().lower() for o in (req.license_outcomes or [
                "permissive", "weak_copyleft",
            ])
        )

        for domain in self._domains_to_scan(req):
            coll = storage_collection_for(domain)
            policy = self._resolve_ai_policy(domain)
            mongo_filter: Dict[str, Any] = {"domain": domain.value}
            if req.pair and domain in (KnowledgeDomain.STRATEGY,
                                        KnowledgeDomain.INDICATOR,
                                        KnowledgeDomain.MARKET):
                mongo_filter["extras.pair"] = req.pair
            if req.timeframe and domain in (KnowledgeDomain.STRATEGY,
                                             KnowledgeDomain.INDICATOR,
                                             KnowledgeDomain.MARKET):
                mongo_filter["extras.timeframe"] = req.timeframe

            try:
                cur = db[coll].find(mongo_filter).limit(2000)
                async for row in cur:
                    # min_trust_tier filter
                    tt = row.get("trust_tier")
                    if req.min_trust_tier is not None:
                        if not isinstance(tt, int) or tt < int(req.min_trust_tier):
                            continue
                    lv = row.get("license_verdict") or {}
                    outcome = str(lv.get("outcome") or "").strip().lower()
                    if outcome and outcome not in allowed_outcomes:
                        continue

                    doc_text = self._extract_text(row)
                    base = self._sim(req.query or "", doc_text)
                    if base <= 0.0:
                        continue

                    breakdown = compose(
                        base_similarity=base,
                        trust_tier=tt if isinstance(tt, int) else None,
                        license_outcome=outcome or None,
                        inserted_at_iso=row.get("inserted_at"),
                        contested_flag=bool(row.get("contested")),
                        endorsements_30d=int(row.get("endorsements_30d") or 0),
                        now=started_at,
                    )
                    if breakdown.final_score <= 0.0:
                        continue

                    preview: Optional[str] = None
                    if policy in ("summary", "off"):
                        # NEVER include raw content_bytes when the
                        # domain policy forbids verbatim quoting.
                        preview = None
                    else:
                        preview = (doc_text or "")[:280]

                    matches.append(QueryMatch(
                        kb_id=str(row.get("_id") or row.get("id") or ""),
                        domain=domain.value,
                        source_url=row.get("source_url"),
                        trust_tier=tt if isinstance(tt, int) else None,
                        license=row.get("license"),
                        license_outcome=outcome or None,
                        similarity_score=base,
                        final_score=breakdown.final_score,
                        similarity_reasons=breakdown.reasons,
                        ranking_breakdown=breakdown.to_dict(),
                        learning_only=bool(row.get("learning_only", True)),
                        eligible_for_deploy=bool(row.get("eligible_for_deploy", False)),
                        inserted_at=row.get("inserted_at"),
                        content_preview=preview,
                    ))
            except Exception as e:                             # noqa: BLE001
                logger.debug("[retrieval] scan of %s failed: %s", coll, e)
                continue

        matches.sort(key=lambda m: m.final_score, reverse=True)
        top = matches[: max(1, int(req.top_k or 10))]
        return self._compose_response(req, top, started_at, "ok")

    def _compose_response(
        self,
        req: QueryRequest,
        matches: List[QueryMatch],
        started_at: datetime,
        status: str,
    ) -> Dict[str, Any]:
        return {
            "status":                    status,
            "query":                     req.query,
            "domain":                    req.domain,
            "pair":                      req.pair,
            "timeframe":                 req.timeframe,
            "min_trust_tier":            req.min_trust_tier,
            "top_k":                     int(req.top_k or 10),
            "match_count":               len(matches),
            "matches":                   [m.to_dict() for m in matches],
            "pipeline_version":          PIPELINE_VERSION,
            "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
            "processed_at":              datetime.now(timezone.utc).isoformat(),
            "started_at":                started_at.isoformat(),
        }


_ENGINE: Optional[RetrievalEngine] = None


def get_retrieval_engine() -> RetrievalEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = RetrievalEngine()
    return _ENGINE


def _reset_for_tests() -> None:
    global _ENGINE
    _ENGINE = None

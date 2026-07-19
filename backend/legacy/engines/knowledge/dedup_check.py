"""Phase 2 Stage 3.β — dedup check (P2C.7).

`canonical_hash` uniqueness **within the target domain**. An identical
hash in a DIFFERENT domain is allowed by design (a paper about EMA
crossovers and a Pine indicator file about EMA crossovers coexist in
`research` and `indicator` even if their canonical text happens to
match on the hash).

Backing store: `strategy_knowledge_base.<storage_collection>` — reads
only, no writes.

Feature-gated by `ENABLE_DEDUP_CHECK`. When off: returns
`DedupResult(status="unique", checked=False)` — dedup is bypassed and
downstream stages must not treat the item as duplicate.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .connector import RawKnowledgeItem
from .constants import KNOWLEDGE_DB_NAME
from .domains import KnowledgeDomain, storage_collection_for

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_enabled() -> bool:
    return _flag("ENABLE_DEDUP_CHECK", False)


DedupStatus = str  # "unique" | "duplicate_same_domain" | "duplicate_cross_domain" | "no_hash"


@dataclass
class DedupResult:
    status:           DedupStatus
    canonical_hash:   str
    matched_id:       Optional[str]           # _id of the matched doc (same-domain only)
    matched_domain:   Optional[str]           # domain of the cross-domain match (informational)
    checked:          bool                    = True
    reason:           str                     = ""

    def to_outcome(self) -> Dict[str, Any]:
        return {
            "status":         self.status,
            "canonical_hash": self.canonical_hash,
            "matched_id":     self.matched_id,
            "matched_domain": self.matched_domain,
            "checked":        self.checked,
            "reason":         self.reason,
        }


def _get_knowledge_db(db_getter=None):
    """Return the `strategy_knowledge_base` Mongo DB handle.

    Uses the shared connection pool from `engines.db` and switches to
    the knowledge DB by name. `db_getter` is an injection point for
    tests.
    """
    if db_getter is not None:
        return db_getter()
    try:
        from engines.db import get_db
        main = get_db()
        # The AsyncIOMotorClient exposes other DBs via `[name]`
        return main.client[KNOWLEDGE_DB_NAME]
    except Exception as e:                                    # pragma: no cover
        logger.warning("[dedup_check] cannot resolve knowledge DB: %s", e)
        return None


async def check(item: RawKnowledgeItem, *, db_getter=None) -> DedupResult:
    """Return the dedup result for an item.

    Never raises to the caller. Errors degrade to a `unique` result
    with a diagnostic reason (fail-open by design — a Mongo blip must
    not block ingestion).
    """
    ch = (item.content_hash or "").strip()
    if not ch:
        return DedupResult(
            status="no_hash",
            canonical_hash="",
            matched_id=None,
            matched_domain=None,
            checked=is_enabled(),
            reason="empty_content_hash",
        )

    if not is_enabled():
        return DedupResult(
            status="unique",
            canonical_hash=ch,
            matched_id=None,
            matched_domain=None,
            checked=False,
            reason="ENABLE_DEDUP_CHECK is off",
        )

    db = _get_knowledge_db(db_getter=db_getter)
    if db is None:
        return DedupResult(
            status="unique",
            canonical_hash=ch,
            matched_id=None,
            matched_domain=None,
            checked=True,
            reason="db_unavailable_fail_open",
        )

    target_coll = storage_collection_for(item.domain)
    try:
        hit = await db[target_coll].find_one(
            {"content_hash": ch}, {"_id": 1, "domain": 1},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[dedup_check] same-domain query failed: %s", e)
        hit = None
    if hit:
        return DedupResult(
            status="duplicate_same_domain",
            canonical_hash=ch,
            matched_id=str(hit.get("_id")),
            matched_domain=str(hit.get("domain") or item.domain.value),
            checked=True,
            reason="hash_collision_same_domain",
        )

    # Advisory cross-domain lookup — informational only; does NOT block.
    cross_hit_domain: Optional[str] = None
    for other in KnowledgeDomain:
        if other is item.domain:
            continue
        other_coll = storage_collection_for(other)
        try:
            match = await db[other_coll].find_one(
                {"content_hash": ch}, {"_id": 1, "domain": 1},
            )
        except Exception:                                     # noqa: BLE001
            continue
        if match:
            cross_hit_domain = str(match.get("domain") or other.value)
            break

    if cross_hit_domain:
        return DedupResult(
            status="duplicate_cross_domain",
            canonical_hash=ch,
            matched_id=None,
            matched_domain=cross_hit_domain,
            checked=True,
            reason="hash_present_in_other_domain_allowed",
        )

    return DedupResult(
        status="unique",
        canonical_hash=ch,
        matched_id=None,
        matched_domain=None,
        checked=True,
        reason="no_collision",
    )

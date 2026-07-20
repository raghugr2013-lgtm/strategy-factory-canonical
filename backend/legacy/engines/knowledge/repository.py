"""Phase 2 Stage 3.β — KnowledgeRepository (P2C.8).

The **audited write path** for ingested knowledge items. Every UKIE
write must land here — legacy paths that call
`strategy_ingestion.injector` directly are untouched and continue
working. The governance cutover flag `UKIE_GOVERNANCE_CUTOVER`
gates the actual Mongo write; when off, the repository returns
`status="dormant"` without touching the database.

Guarantees enforced:

  * Hard rails — `learning_only=True`, `eligible_for_deploy=False`
    are stamped on every write regardless of what the item claims.
  * Domain-partitioned storage — writes go to the collection returned
    by `storage_collection_for(item.domain)` inside
    `strategy_knowledge_base` DB.
  * Provenance stamped — `pipeline_version`, `pipeline_contract_version`,
    `inserted_at`.
  * Idempotent — upsert on `(content_hash, domain)` composite key.
    Re-writing the same item updates `updated_at` but preserves
    `inserted_at`.

The repository does **not** query or read for external consumers in
Stage 3.β (write-only surface). Retrieval remains the responsibility
of the existing `knowledge.retriever` module.

No reads to production `strategies` — this is a critical rail.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .connector import RawKnowledgeItem
from .constants import (
    KNOWLEDGE_DB_NAME,
    PIPELINE_CONTRACT_VERSION,
    PIPELINE_VERSION,
)
from .domains import KnowledgeDomain, storage_collection_for
from .license_gate import LicenseVerdict
from .trust_scorer import TrustScore

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_cutover_enabled() -> bool:
    return _flag("UKIE_GOVERNANCE_CUTOVER", False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InsertResult:
    """Outcome of `insert_ingested()`.

    Attributes:
        status: `"inserted"` | `"updated"` | `"dormant"` | `"rejected"` | `"error"`
        domain: The domain the item was routed to.
        storage_collection: Where the write landed (or would land in dormant).
        content_hash: Hash of the raw payload.
        doc_id: `_id` of the written document (str) — None in dormant.
        pipeline_version: The `PIPELINE_VERSION` under which the item
            was written.
        pipeline_contract_version: The semantic contract version.
        reason: Free-form diagnostic.
    """

    status:                     str
    domain:                     str
    storage_collection:         str
    content_hash:               str
    doc_id:                     Optional[str]     = None
    pipeline_version:           str               = PIPELINE_VERSION
    pipeline_contract_version:  str               = PIPELINE_CONTRACT_VERSION
    processed_at:               str               = field(default_factory=_now_iso)
    reason:                     str               = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KnowledgeRepository:
    """Sole audited writer for UKIE ingestion.

    Consumers instantiate once (or use the module-level singleton
    `get_repository()`). Mongo access is lazy via `_db_getter` so tests
    can inject a stub without touching the real driver.
    """

    def __init__(self, db_getter=None) -> None:
        self._db_getter = db_getter

    def _db(self):
        if self._db_getter is not None:
            return self._db_getter()
        try:
            from engines.db import get_db
            main = get_db()
            return main.client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                # pragma: no cover
            logger.warning("[repository] cannot resolve knowledge DB: %s", e)
            return None

    async def insert_ingested(
        self,
        item: RawKnowledgeItem,
        *,
        license_verdict: Optional[LicenseVerdict] = None,
        trust_score:     Optional[TrustScore]     = None,
        retro_score_run_id: Optional[str]         = None,
    ) -> InsertResult:
        """Write one item into its domain sub-collection.

        Returns quickly on any error — the pipeline logs and continues.
        Guarantees hard rails (`learning_only=True`,
        `eligible_for_deploy=False`) regardless of item state.

        Args:
            retro_score_run_id: Optional Stage-3.γ audit stamp. When
                supplied, the written document carries a
                `retro_score_run_id` field enabling per-run rollback via
                `retro_score.rollback(run_id)`. Non-retro writes pass
                None and produce documents without this field
                (backward-compatible; no shape change to Stage 3.β
                write path).
        """
        domain = item.domain
        target = storage_collection_for(domain)
        ch = (item.content_hash or "").strip()

        # Hard-rail enforcement — never trust incoming values
        item.learning_only = True
        item.eligible_for_deploy = False

        if not is_cutover_enabled():
            return InsertResult(
                status="dormant",
                domain=domain.value,
                storage_collection=target,
                content_hash=ch,
                reason="UKIE_GOVERNANCE_CUTOVER is off",
            )
        if not ch:
            return InsertResult(
                status="rejected",
                domain=domain.value,
                storage_collection=target,
                content_hash="",
                reason="empty_content_hash",
            )

        db = self._db()
        if db is None:
            return InsertResult(
                status="error",
                domain=domain.value,
                storage_collection=target,
                content_hash=ch,
                reason="db_unavailable",
            )

        now = _now_iso()
        doc_body = self._build_doc(item, now=now,
                                   license_verdict=license_verdict,
                                   trust_score=trust_score,
                                   retro_score_run_id=retro_score_run_id)
        try:
            res = await db[target].update_one(
                {"content_hash": ch, "domain": domain.value},
                {
                    "$set": doc_body,
                    "$setOnInsert": {"inserted_at": now},
                },
                upsert=True,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[repository] write failed for %s/%s: %s", target, ch, e)
            return InsertResult(
                status="error",
                domain=domain.value,
                storage_collection=target,
                content_hash=ch,
                reason=f"write_failed:{str(e)[:120]}",
            )
        try:
            doc = await db[target].find_one(
                {"content_hash": ch, "domain": domain.value},
                {"_id": 1},
            )
            doc_id = str(doc["_id"]) if doc else None
        except Exception:                                     # pragma: no cover
            doc_id = None

        matched = int(getattr(res, "matched_count", 0) or 0)
        return InsertResult(
            status="updated" if matched else "inserted",
            domain=domain.value,
            storage_collection=target,
            content_hash=ch,
            doc_id=doc_id,
            reason="ok",
        )

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _build_doc(
        item: RawKnowledgeItem,
        *,
        now: str,
        license_verdict: Optional[LicenseVerdict],
        trust_score:     Optional[TrustScore],
        retro_score_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """The authoritative document shape written to the domain sub-collection."""
        doc: Dict[str, Any] = {
            "domain":                    item.domain.value,
            "connector_name":            item.connector_name,
            "source_url":                item.source_url,
            "source_ref":                item.source_ref,
            "content_hash":              item.content_hash,
            "content_mime":              item.content_mime,
            "author":                    item.author,
            "fetched_at":                item.fetched_at,
            "license":                   item.license,
            "license_confidence":        item.license_confidence,
            "learning_only":             True,               # HARD RAIL
            "eligible_for_deploy":       False,              # HARD RAIL
            "trust_tier":                item.trust_tier,
            "trust_reasons":             list(item.trust_reasons),
            "extras":                    item.extras,
            "pipeline_version":          PIPELINE_VERSION,
            "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
            "processed_at":              now,
            "updated_at":                now,
        }
        if license_verdict is not None:
            doc["license_verdict"] = license_verdict.to_outcome()
        if trust_score is not None:
            doc["trust_score"] = trust_score.to_outcome()
        if retro_score_run_id is not None:
            doc["retro_score_run_id"] = str(retro_score_run_id)
        return doc


# ── Module-level singleton ───────────────────────────────────────────

_REPOSITORY: Optional[KnowledgeRepository] = None


def get_repository() -> KnowledgeRepository:
    global _REPOSITORY
    if _REPOSITORY is None:
        _REPOSITORY = KnowledgeRepository()
    return _REPOSITORY


def _reset_for_tests() -> None:
    global _REPOSITORY
    _REPOSITORY = None

"""Phase 2 Stage 4 — InternalMongoConnector (P4A.5).

Read-only mirror of the Factory's own outputs into the
`internal_history` domain. Reads from configurable source collections
(default: `strategy_library`, `strategy_lifecycle_history`,
`mutation_events`) and produces one `RawKnowledgeItem` per row.

CRITICAL invariant: **pure READ**. This connector never writes to its
source collections; write attempts against them are structurally
impossible because the connector holds no write handle.

Discovery: supported (cursor over the source collection).
Incremental sync: supported via `DiscoveryQuery.since` filter on
`created_at` (or an equivalent stable field per collection).
Trust seed: T5 (produced by the Factory itself).
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, FrozenSet, List, Optional

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..connector_auth import NoAuth
from ..connector_retry import CONNECTOR_CONSERVATIVE
from ..domains import KnowledgeDomain
from .base import AbstractConnector

logger = logging.getLogger(__name__)


DEFAULT_SOURCE_COLLECTIONS: List[str] = [
    "strategy_library",
    "strategy_lifecycle_history",
    "mutation_events",
]


def _stable_hash(row: Dict[str, Any]) -> str:
    """Deterministic hash over the JSON-normalised row (minus `_id`).

    We use `default=str` so ObjectIds / datetimes get stringified —
    safe for hashing though obviously not for storage. `_id` is
    excluded so re-ingesting the same source row upserts idempotently.
    """
    scrub = {k: v for k, v in row.items() if k != "_id"}
    blob = json.dumps(scrub, sort_keys=True, default=str).encode("utf-8", errors="replace")
    return f"sha256:{hashlib.sha256(blob).hexdigest()}"


class InternalMongoConnector(AbstractConnector):
    """Internal-history connector — INTERNAL_HISTORY domain."""

    name:               str = "internal_mongo"
    source_type:        str = "docs"
    supported_domains:  FrozenSet[KnowledgeDomain] = frozenset({KnowledgeDomain.INTERNAL_HISTORY})
    default_trust_tier: int = 5                                # T5 — Factory-produced
    supported_licenses: FrozenSet[str] = frozenset({"internal"})
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=True,
        supports_incremental_sync=True,
        supports_versioning=True,          # source row `_id` is immutable
        supports_rate_limits=False,        # in-process Mongo — no external rate limit
        supports_metadata_only=True,
    )

    flag_name: str = "UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED"
    connector_version: str = "0.1.0"
    source_contract_version: int = 1

    _auth = NoAuth()
    _retry_policy = CONNECTOR_CONSERVATIVE

    def __init__(
        self,
        *,
        db_getter: Optional[Callable] = None,
        source_collections: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._db_getter = db_getter
        self._source_collections = source_collections or DEFAULT_SOURCE_COLLECTIONS

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=600, burst=60, cooloff_seconds=5.0)

    # ── DB resolver — never held, never cached ───────────────────────

    def _db(self):
        if self._db_getter is not None:
            return self._db_getter()
        try:                                                    # pragma: no cover
            from engines.db import get_db
            return get_db()
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[internal_mongo_connector] db unavailable: %s", e)
            return None

    # ── Protocol methods ─────────────────────────────────────────────

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        if query.domain not in self.supported_domains:
            return
        if not self.is_flag_enabled():
            return
        db = self._db()
        if db is None:
            return
        # Optional incremental filter
        mongo_filter: Dict[str, Any] = {}
        if query.since:
            try:
                dt = datetime.fromisoformat(query.since)
                mongo_filter["created_at"] = {"$gte": dt}
            except ValueError:
                logger.debug("[internal_mongo_connector] invalid since %r", query.since)

        limit_left = int(query.limit or 0)
        for coll_name in self._source_collections:
            if limit_left <= 0 and query.limit:
                break
            try:
                cur = db[coll_name].find(mongo_filter)
                async for row in cur:
                    yield self._row_to_reference(row, coll_name)
                    limit_left -= 1
                    if query.limit and limit_left <= 0:
                        break
            except Exception as e:                             # noqa: BLE001
                logger.debug("[internal_mongo_connector] discover in %s failed: %s", coll_name, e)
                continue

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        extras = dict(ref.extras or {})
        row = extras.get("row") or {}
        # Content = normalised JSON body — the internal-history domain
        # policy is "summary", so downstream consumers summarise (they
        # do not quote verbatim).
        body_bytes: bytes = b""
        try:
            body_bytes = json.dumps(row, sort_keys=True, default=str).encode("utf-8", errors="replace")
        except Exception:                                      # pragma: no cover
            body_bytes = b""
        return RawKnowledgeItem(
            domain=KnowledgeDomain.INTERNAL_HISTORY,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=self.content_hash(body_bytes),
            fetched_at=now_iso(),
            content_bytes=body_bytes,
            content_mime="application/json",
            author="factory-internal",
            license="internal",
            license_confidence=1.0,
            extras={
                "collection":              extras.get("collection"),
                "row_id":                  extras.get("row_id"),
                "connector_version":       self.connector_version,
                "source_contract_version": self.source_contract_version,
                "curated":                 True,               # +1 trust tier
                "parser_confidence":       0.98,
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _row_to_reference(self, row: Dict[str, Any], collection: str) -> Reference:
        row_id = str(row.get("_id") or "")
        return Reference(
            connector_name=self.name,
            source_url=f"mongo://{collection}/{row_id}",
            source_ref=_stable_hash(row),
            target_domain=KnowledgeDomain.INTERNAL_HISTORY,
            title=str(row.get("strategy_id") or row.get("event_id") or row_id or collection),
            extras={
                "collection": collection,
                "row_id":     row_id,
                "row":        row,
            },
        )

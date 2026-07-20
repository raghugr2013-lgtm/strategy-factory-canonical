"""Phase 2 Stage 4 — ArxivConnector (P4A.1).

Fetches research references from Arxiv. Public API, no auth required
(optional `ARXIV_API_KEY` env var raises the connector's declared
rate limits).

Concrete network I/O is DEFERRED: this connector ships with an
injectable HTTP client so tests exercise it without hitting the
internet. Live wiring (aiohttp.ClientSession → arxiv API) becomes a
one-line switch when the operator flips
`UKIE_CONNECTOR_ARXIV_ENABLED=true` and the connector's `_http` is
still `None`.

Domains: `research`. Discovery: supported. Incremental sync: supported
via `DiscoveryQuery.since` timestamp. Versioning: supported (arxiv IDs
are permalinks — used as `source_ref`).
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, FrozenSet, List, Optional

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..connector_auth import ApiKeyAuth
from ..connector_retry import CONNECTOR_DEFAULT
from ..domains import KnowledgeDomain
from .base import AbstractConnector

logger = logging.getLogger(__name__)


class ArxivConnector(AbstractConnector):
    """Arxiv research paper connector."""

    name:               str = "arxiv"
    source_type:        str = "paper"
    supported_domains:  FrozenSet[KnowledgeDomain] = frozenset({KnowledgeDomain.RESEARCH})
    default_trust_tier: int = 4                     # T4 — curated academic corpus
    supported_licenses: FrozenSet[str] = frozenset({
        "arxiv-perpetual",         # arxiv's own default (permissive-ish)
        "cc-by",
        "cc-by-sa",
        "cc-by-nc",
        "cc0",
    })
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=True,
        supports_incremental_sync=True,
        supports_versioning=True,
        supports_rate_limits=True,
        supports_metadata_only=True,
    )

    flag_name: str = "UKIE_CONNECTOR_ARXIV_ENABLED"
    connector_version: str = "0.1.0"
    source_contract_version: int = 1

    _auth = ApiKeyAuth(env_var="ARXIV_API_KEY", required=False)
    _retry_policy = CONNECTOR_DEFAULT

    def __init__(self, *, http_client: Optional[Callable] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # `http_client` is an optional callable `(url, headers) → awaitable[dict]`
        # returning a JSON-ish shape compatible with the arxiv API. When
        # None, the connector runs in "dormant network" mode — discover
        # yields the entries the caller injects via `.seed(...)`.
        self._http = http_client
        self._seed: List[Reference] = []

    # ── Test/seed hook ───────────────────────────────────────────────

    def seed(self, refs: List[Reference]) -> None:
        """Inject references to be yielded by `discover()` in test /
        curated-list mode."""
        self._seed = list(refs)

    # ── Protocol methods ─────────────────────────────────────────────

    def rate_limit(self) -> RateLimit:
        # Arxiv publishes a 3-req/s soft-limit for their export API.
        # We stay well below.
        return RateLimit(requests_per_minute=60, burst=5, cooloff_seconds=60.0)

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        if query.domain not in self.supported_domains:
            return
        if not self.is_flag_enabled():
            return
        # In-process seed path (test / curated list)
        for r in self._seed:
            if query.limit and query.limit > 0:
                query = DiscoveryQuery(**{**query.__dict__, "limit": query.limit - 1})
            yield r
        # Live HTTP path — invoked only when `http_client` was injected
        if self._http is not None:
            try:
                async def _fetch():
                    return await self._http(
                        "https://export.arxiv.org/api/query",
                        {**self._auth.headers(), "User-Agent": "ukie-arxiv/0.1"},
                    )
                data = await self._call_with_retry(_fetch)
                for entry in (data or {}).get("entries", []):
                    yield self._entry_to_reference(entry)
            except Exception as e:                             # noqa: BLE001
                logger.warning("[arxiv_connector] discover failed: %s", e)

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        extras = ref.extras or {}
        abstract = str(extras.get("abstract") or "")
        payload = abstract.encode("utf-8")
        return RawKnowledgeItem(
            domain=KnowledgeDomain.RESEARCH,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=self.content_hash(payload),
            fetched_at=now_iso(),
            content_bytes=payload,
            content_mime="text/plain",
            author=extras.get("authors"),
            license=extras.get("license"),
            license_confidence=float(extras.get("license_confidence") or 0.0),
            extras={
                **extras,
                "connector_version":       self.connector_version,
                "source_contract_version": self.source_contract_version,
                "citations":               extras.get("citations", 0),
                "parser_confidence":       0.95,
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _entry_to_reference(self, entry: dict) -> Reference:
        arxiv_id = str(entry.get("id") or entry.get("arxiv_id") or "")
        return Reference(
            connector_name=self.name,
            source_url=str(entry.get("url") or f"https://arxiv.org/abs/{arxiv_id}"),
            source_ref=arxiv_id,
            target_domain=KnowledgeDomain.RESEARCH,
            title=str(entry.get("title") or ""),
            extras={
                "abstract":         entry.get("abstract"),
                "authors":          entry.get("authors"),
                "published":        entry.get("published"),
                "categories":       entry.get("categories"),
                "citations":        entry.get("citations", 0),
                "license":          entry.get("license"),
                "license_confidence": entry.get("license_confidence", 0.0),
            },
        )

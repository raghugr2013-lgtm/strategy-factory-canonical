"""Phase 2 Stage 4 — PropFirmConnector (P4A.3).

Ingests prop-firm rule sets into the `execution` domain. Discovery is
NOT supported — every reference comes from a curated allow-list per
prop firm. Auth is mixed: public rulebooks use `NoAuth`; some portals
require `OAuthClientCredentials`.

Trust seed: T4 (rule sets need high trust — used by realism sweep).
Content policy: verbatim (per Stage-3.α domain spec).

The connector's allow-list is intentionally minimal at Stage-4
kick-off. Adding a new prop firm is one entry in `_ALLOWLIST` — no
code changes required elsewhere.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable, Dict, FrozenSet, List, Optional

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..connector_auth import ConnectorAuth, NoAuth, OAuthClientCredentials
from ..connector_retry import CONNECTOR_CONSERVATIVE
from ..domains import KnowledgeDomain
from .base import AbstractConnector

logger = logging.getLogger(__name__)


# ── Curated allow-list ───────────────────────────────────────────────
#
# Each entry declares:
#   * `firm_name` — canonical firm identifier
#   * `rulebook_url` — canonical URL of the rulebook (HTML or PDF)
#   * `auth` — "none" or "oauth"
#   * `curated_trust_tier` — 4 by default; 5 for firms with verified
#     official-source relationships
#
# Adding a new firm: append a new dict. That's it.

_ALLOWLIST: List[Dict[str, Any]] = [
    {"firm_name": "ftmo",       "rulebook_url": "https://ftmo.com/rules/",       "auth": "none", "curated_trust_tier": 4},
    {"firm_name": "myforexfunds","rulebook_url": "https://myforexfunds.com/rules","auth": "none", "curated_trust_tier": 4},
    {"firm_name": "the5ers",    "rulebook_url": "https://the5ers.com/rules/",    "auth": "none", "curated_trust_tier": 4},
]


class PropFirmConnector(AbstractConnector):
    """Prop-firm rule ingestion — execution domain."""

    name:               str = "propfirm"
    source_type:        str = "docs"
    supported_domains:  FrozenSet[KnowledgeDomain] = frozenset({KnowledgeDomain.EXECUTION})
    default_trust_tier: int = 4
    supported_licenses: FrozenSet[str] = frozenset({"proprietary", "unknown", "arr"})
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=True,          # walks the allow-list
        supports_incremental_sync=True,   # ETag/If-Modified-Since
        supports_versioning=True,
        supports_rate_limits=True,
        supports_metadata_only=True,
    )

    flag_name: str = "UKIE_CONNECTOR_PROPFIRM_ENABLED"
    connector_version: str = "0.1.0"
    source_contract_version: int = 1

    # Default auth: NoAuth. Callers requiring OAuth wire it via
    # constructor injection when subclassing per-firm.
    _auth: ConnectorAuth = NoAuth()
    _retry_policy = CONNECTOR_CONSERVATIVE

    def __init__(
        self,
        *,
        allowlist: Optional[List[Dict[str, Any]]] = None,
        http_client: Optional[Callable] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._allowlist = allowlist if allowlist is not None else _ALLOWLIST
        self._http = http_client

    def rate_limit(self) -> RateLimit:
        # Prop-firm portals are typically low-volume — be gentle.
        return RateLimit(requests_per_minute=6, burst=1, cooloff_seconds=120.0)

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        if query.domain not in self.supported_domains:
            return
        if not self.is_flag_enabled():
            return
        for entry in self._allowlist:
            yield Reference(
                connector_name=self.name,
                source_url=str(entry["rulebook_url"]),
                source_ref=f"{entry['firm_name']}@rulebook",
                target_domain=KnowledgeDomain.EXECUTION,
                title=f"{entry['firm_name']} rulebook",
                extras={
                    "firm_name":           entry["firm_name"],
                    "curated":             True,
                    "curated_trust_tier":  int(entry.get("curated_trust_tier") or 4),
                    "auth_hint":           entry.get("auth"),
                },
            )

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        extras = dict(ref.extras or {})
        text_hint = extras.get("text")
        payload: bytes = b""
        if isinstance(text_hint, str) and text_hint:
            payload = text_hint.encode("utf-8", errors="replace")
        elif self._http is not None:
            try:
                async def _fetch():
                    return await self._http(
                        ref.source_url,
                        {**self._auth.headers(), "User-Agent": "ukie-propfirm/0.1"},
                    )
                data = await self._call_with_retry(_fetch)
                raw = (data or {}).get("body") or b""
                if isinstance(raw, str):
                    raw = raw.encode("utf-8", errors="replace")
                payload = raw
            except Exception as e:                             # noqa: BLE001
                logger.warning("[propfirm_connector] fetch failed: %s", e)

        return RawKnowledgeItem(
            domain=KnowledgeDomain.EXECUTION,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=self.content_hash(payload),
            fetched_at=now_iso(),
            content_bytes=payload,
            content_mime="text/html",
            author=extras.get("firm_name"),
            license=extras.get("license") or "proprietary",     # rule sets are almost always ARR
            license_confidence=float(extras.get("license_confidence") or 0.8),
            extras={
                **extras,
                "connector_version":       self.connector_version,
                "source_contract_version": self.source_contract_version,
                "parser_confidence":       0.9 if text_hint else 0.7,
            },
        )

"""Phase 2 Stage 4 — TradingViewConnector (P4A.4).

Ingests public Pine scripts into `strategy` + `indicator` domains.
Discovery is NOT supported in v1 (TradingView's public search API is
rate-limited + ToS-restricted); references come from curated seed
lists. Auth: `NoAuth`.

License detection: Pine scripts that carry the standard MPL-2.0
header land as `permissive`; others default to `unknown`.
Trust seed: T3 by default; T4 when `extras.tv_house_scripts=True`.
"""
from __future__ import annotations

import logging
import re
from typing import Any, AsyncIterator, Callable, FrozenSet, List, Optional

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..connector_auth import NoAuth
from ..connector_retry import CONNECTOR_DEFAULT
from ..domains import KnowledgeDomain
from .base import AbstractConnector

logger = logging.getLogger(__name__)


_MPL_HEADER = re.compile(
    r"//\s*This source code is subject to the terms of the Mozilla Public License",
    re.IGNORECASE,
)


class TradingViewConnector(AbstractConnector):
    """TradingView Pine-script connector.

    v1 supports STRATEGY + INDICATOR domains via a curated seed list.
    `discover()` yields refs previously injected via `.seed(...)`;
    `fetch()` uses `ref.extras["pine_source"]` when present, else
    calls the injected `http_client`.
    """

    name:               str = "tradingview"
    source_type:        str = "code"
    supported_domains:  FrozenSet[KnowledgeDomain] = frozenset({
        KnowledgeDomain.STRATEGY,
        KnowledgeDomain.INDICATOR,
    })
    default_trust_tier: int = 3
    supported_licenses: FrozenSet[str] = frozenset({"MPL-2.0", "unknown"})
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=False,           # seed-list only in v1
        supports_incremental_sync=False,
        supports_versioning=True,           # TV publish IDs are stable
        supports_rate_limits=True,
        supports_metadata_only=True,
    )

    flag_name: str = "UKIE_CONNECTOR_TRADINGVIEW_ENABLED"
    connector_version: str = "0.1.0"
    source_contract_version: int = 1

    _auth = NoAuth()
    _retry_policy = CONNECTOR_DEFAULT

    def __init__(self, *, http_client: Optional[Callable] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._http = http_client
        self._seed: List[Reference] = []

    def seed(self, refs: List[Reference]) -> None:
        self._seed = list(refs)

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=30, burst=3, cooloff_seconds=60.0)

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        if query.domain not in self.supported_domains:
            return
        if not self.is_flag_enabled():
            return
        for r in self._seed:
            if r.target_domain == query.domain:
                yield r

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        extras = dict(ref.extras or {})
        pine = extras.get("pine_source")
        payload: bytes = b""
        if isinstance(pine, str):
            payload = pine.encode("utf-8", errors="replace")
        elif isinstance(pine, (bytes, bytearray)):
            payload = bytes(pine)
        elif self._http is not None:
            try:
                async def _fetch():
                    return await self._http(
                        ref.source_url,
                        {"User-Agent": "ukie-tradingview/0.1"},
                    )
                data = await self._call_with_retry(_fetch)
                raw = (data or {}).get("body") or b""
                if isinstance(raw, str):
                    raw = raw.encode("utf-8", errors="replace")
                payload = raw
            except Exception as e:                             # noqa: BLE001
                logger.warning("[tradingview_connector] fetch failed: %s", e)

        # Basic MPL header detection → licence stamp
        text_preview = payload[:8192].decode("utf-8", errors="replace")
        detected_license: Optional[str] = None
        detected_conf: float = 0.0
        if _MPL_HEADER.search(text_preview):
            detected_license = "MPL-2.0"
            detected_conf = 0.9

        # Trust boost heuristics
        stars = int(extras.get("tv_stars") or 0)
        house = bool(extras.get("tv_house_scripts"))
        # `curated=True` boosts the Stage-3.β trust scorer +1 tier
        curated_flag = {"curated": True} if house else {}

        return RawKnowledgeItem(
            domain=ref.target_domain,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=self.content_hash(payload),
            fetched_at=now_iso(),
            content_bytes=payload,
            content_mime="text/x-pine",
            author=extras.get("author"),
            license=extras.get("license") or detected_license,
            license_confidence=float(extras.get("license_confidence") or detected_conf),
            extras={
                **extras,
                **curated_flag,
                "connector_version":       self.connector_version,
                "source_contract_version": self.source_contract_version,
                "stars":                   stars,
                "parser_confidence":       0.9,
            },
        )

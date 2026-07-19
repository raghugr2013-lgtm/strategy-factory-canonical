"""Phase 2 Stage 3.α — GithubConnector (P2C.1 adapter).

Wraps the existing `strategy_ingestion.collector.collect_from_github`
logic behind the `KnowledgeConnector` Protocol. The legacy
`ingestion_runner` continues to call `collector` directly today — this
adapter is the forward-compatible surface that Stage 3.β pipeline
stages will consume.

Design promises:
  * Zero behaviour change to the legacy path — importing this module
    does not alter `strategy_ingestion` state or side-effects.
  * Declares `supported_domains={STRATEGY}` per PHASE_2C §7 P2C.1.
  * Declares its capability set honestly — versioning (git SHA) YES;
    incremental sync NOT YET; discovery YES; rate-limit awareness YES
    via the `GITHUB_TOKEN` env var handling in the legacy collector;
    metadata-only NOT YET.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import AsyncIterator, FrozenSet

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    KnowledgeConnector,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..domains import KnowledgeDomain

logger = logging.getLogger(__name__)


class GithubConnector:
    """`KnowledgeConnector` for GitHub source repositories.

    Delegates to the pre-existing curated + search-driven crawler in
    `engines.strategy_ingestion.collector`. Emits one
    `RawKnowledgeItem(domain=STRATEGY)` per collected file.
    """

    name:               str                              = "github"
    source_type:        str                              = "code"
    supported_domains:  FrozenSet[KnowledgeDomain]       = frozenset({KnowledgeDomain.STRATEGY})
    default_trust_tier: int                              = 3          # T3 — Standard (uncurated GitHub w/ license)
    supported_licenses: FrozenSet[str]                   = frozenset({
        "MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause",
        "MPL-2.0", "GPL-3.0", "LGPL-3.0",
    })
    capabilities:       ConnectorCapabilities            = ConnectorCapabilities(
        supports_discovery=True,
        supports_incremental_sync=False,   # implemented in Stage 4
        supports_versioning=True,          # commit SHA in url
        supports_rate_limits=True,         # GITHUB_TOKEN lifts limits
        supports_metadata_only=False,      # implemented in Stage 4
    )

    # ── Protocol methods ─────────────────────────────────────────────

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        """Yield GitHub references matching a discovery query.

        Stage 3.α: for the STRATEGY domain, we delegate to the legacy
        collector which returns both the reference and the fetched
        content in one call. We surface a `Reference` per collected
        file so callers who only want references (metadata-only) can
        stop before invoking `fetch()`. The content is NOT re-fetched
        by `fetch()` for these — see notes on Stage 4.
        """
        if query.domain not in self.supported_domains:
            return
        try:
            from engines.strategy_ingestion.collector import collect_from_github
        except Exception as e:  # pragma: no cover
            logger.warning("[github_connector] legacy collector unavailable: %s", e)
            return
        try:
            items = await collect_from_github(
                queries=[query.query] if query.query else None,
                max_total=int(query.limit or 10),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("[github_connector] discover failed: %s", e)
            return
        for it in items:
            url = str(it.get("url") or "")
            if not url:
                continue
            yield Reference(
                connector_name=self.name,
                source_url=url,
                source_ref=self._extract_ref(url),
                target_domain=KnowledgeDomain.STRATEGY,
                title=str(it.get("name") or ""),
                extras={
                    "repo":     it.get("repo"),
                    "path":     it.get("path"),
                    "ext":      it.get("ext"),
                    "raw_code": it.get("raw_code"),   # carried through so `fetch()` can return without re-network
                },
            )

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        """Return the fetched item as a canonical `RawKnowledgeItem`.

        Stage 3.α: the legacy collector already returned the content
        alongside the reference; `discover()` carries it in
        `ref.extras["raw_code"]`. Stage 4 rewires this to a direct
        blob-fetch path so `discover()` can be metadata-only.
        """
        extras = ref.extras or {}
        raw = extras.get("raw_code")
        if isinstance(raw, str):
            payload = raw.encode("utf-8", errors="replace")
        elif isinstance(raw, (bytes, bytearray)):
            payload = bytes(raw)
        else:
            payload = b""
        digest = hashlib.sha256(payload).hexdigest() if payload else ""
        return RawKnowledgeItem(
            domain=KnowledgeDomain.STRATEGY,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=f"sha256:{digest}" if digest else "sha256:",
            fetched_at=now_iso(),
            content_bytes=payload,
            content_mime=self._mime_for_ext(extras.get("ext")),
            license=None,             # populated by license_gate in Stage 3.β
            license_confidence=0.0,
            author=extras.get("repo"),
        )

    def rate_limit(self) -> RateLimit:
        # GitHub API: 60 rpm unauth; 5000 / hour authed. Conservative
        # sustained rate suits both — token-holders can raise via env
        # in Stage 4 without changing the interface.
        return RateLimit(
            requests_per_minute=30,
            burst=5,
            cooloff_seconds=60.0,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_ref(url: str) -> str:
        """Best-effort extraction of a commit SHA / branch pointer.

        Format: `https://github.com/{owner}/{repo}/blob/{ref}/{path}`.
        """
        parts = url.split("/blob/", 1)
        if len(parts) != 2:
            return url
        tail = parts[1]
        # `ref` is up to the first `/`
        cut = tail.find("/")
        return tail[:cut] if cut >= 0 else tail

    @staticmethod
    def _mime_for_ext(ext: str | None) -> str:
        m = {
            ".py":        "text/x-python",
            ".pine":      "text/x-pine",
            ".pinescript": "text/x-pine",
            ".mq4":       "text/x-mql4",
            ".mq5":       "text/x-mql5",
        }
        return m.get((ext or "").lower(), "text/plain")


# Verify the Protocol is satisfied at import time (helpful for CI)
assert isinstance(GithubConnector(), KnowledgeConnector), \
    "GithubConnector does not satisfy KnowledgeConnector Protocol"

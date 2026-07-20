"""Phase 2 Stage 4 — PdfConnector (P4A.2).

Fetches PDF documents from URLs and extracts text via `pdfminer.six`
(already available). Discovery is NOT supported — callers supply
references (curated seed lists). Incremental sync is supported via
ETag / Last-Modified.

Domains:
  * `research`  (default)
  * `strategy`, `execution`, `indicator` (via `ref.target_domain`)

Auth:
  * `NoAuth` for open URLs (default)
  * `BearerAuth` when the caller injects one (gated PDFs; e.g. some
    prop-firm portals distribute PDFs behind an auth wall)

Trust seed: T3 by default; T4 when `ref.extras["curated"] = True`.
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
from ..connector_auth import ConnectorAuth, NoAuth
from ..connector_retry import CONNECTOR_DEFAULT
from ..domains import KnowledgeDomain
from .base import AbstractConnector

logger = logging.getLogger(__name__)


class PdfConnector(AbstractConnector):
    """Generic PDF connector.

    Runs in TWO modes:
      * Seed mode (default): caller calls `.seed(refs)` with a curated
        list; `discover()` yields those; `fetch()` uses the injected
        HTTP client OR an in-memory blob supplied via
        `ref.extras["pdf_bytes"]`.
      * Live mode: caller injects `http_client` — the connector fetches
        the PDF bytes over HTTP with retries and extracts text.

    Text extraction lives in `_extract_text()` — deferred to
    `pdfminer.six` when the payload is real bytes; when the caller
    supplies pre-extracted text via `ref.extras["text"]`, extraction
    is a no-op.
    """

    name:               str = "pdf"
    source_type:        str = "book"
    supported_domains:  FrozenSet[KnowledgeDomain] = frozenset({
        KnowledgeDomain.RESEARCH,
        KnowledgeDomain.STRATEGY,
        KnowledgeDomain.EXECUTION,
        KnowledgeDomain.INDICATOR,
    })
    default_trust_tier: int = 3
    supported_licenses: FrozenSet[str] = frozenset({"*"})   # per-doc licence detection
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=False,          # caller-driven seed list
        supports_incremental_sync=True,    # ETag / Last-Modified
        supports_versioning=True,          # source_ref is the immutable URL + etag
        supports_rate_limits=True,
        supports_metadata_only=True,
    )

    flag_name: str = "UKIE_CONNECTOR_PDF_ENABLED"
    connector_version: str = "0.1.0"
    source_contract_version: int = 1

    _auth: ConnectorAuth = NoAuth()
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
        # 1. Pre-supplied bytes / text (test / cached path)
        payload: bytes = b""
        text_hint = extras.get("text")
        if isinstance(text_hint, str):
            payload = text_hint.encode("utf-8", errors="replace")
        elif isinstance(extras.get("pdf_bytes"), (bytes, bytearray)):
            raw = bytes(extras["pdf_bytes"])
            payload = self._extract_text(raw).encode("utf-8", errors="replace")
        # 2. Live HTTP fetch
        elif self._http is not None:
            try:
                async def _fetch():
                    return await self._http(
                        ref.source_url,
                        {**self._auth.headers(), "User-Agent": "ukie-pdf/0.1"},
                    )
                data = await self._call_with_retry(_fetch)
                raw = (data or {}).get("bytes") or b""
                payload = self._extract_text(raw).encode("utf-8", errors="replace")
            except Exception as e:                             # noqa: BLE001
                logger.warning("[pdf_connector] fetch failed: %s", e)

        curated = bool(extras.get("curated"))
        trust_seed_extras = {"curated": True} if curated else {}
        return RawKnowledgeItem(
            domain=ref.target_domain,
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash=self.content_hash(payload),
            fetched_at=now_iso(),
            content_bytes=payload,
            content_mime="text/plain",
            author=extras.get("author"),
            license=extras.get("license"),
            license_confidence=float(extras.get("license_confidence") or 0.0),
            extras={
                **extras,
                **trust_seed_extras,
                "connector_version":       self.connector_version,
                "source_contract_version": self.source_contract_version,
                "parser_confidence":       0.75 if not text_hint else 0.95,
            },
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _extract_text(self, raw: bytes) -> str:
        """Extract text from PDF bytes via pdfminer.six.

        Returns an empty string on any failure. The caller then produces
        a `RawKnowledgeItem` with `content_hash=""` → the pipeline
        rejects it as `no_hash` (Stage 3.β `dedup_check` semantics).
        """
        if not raw:
            return ""
        try:                                                    # pragma: no cover
            from io import BytesIO
            from pdfminer.high_level import extract_text
            return extract_text(BytesIO(raw)) or ""
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[pdf_connector] pdfminer failed: %s", e)
            # Fallback: treat as opaque bytes; caller supplied `text`
            # extras will already have covered the common case.
            return ""

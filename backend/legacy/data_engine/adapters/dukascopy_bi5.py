"""
P0A — Dukascopy concrete BI5 adapter.

Fetches one hour of raw .bi5 bytes from Dukascopy's public archive at:

    https://datafeed.dukascopy.com/datafeed/{SLUG}/{YYYY}/{MM-1:02d}/{DD:02d}/{HH:02d}h_ticks.bi5

(Note: Dukascopy month is **0-indexed** in the URL — January = 00.)

This adapter MUST NOT:
  * decompress LZMA (that's tick_aggregator's job),
  * write to disk (that's tick_archive's job),
  * touch MongoDB.

TODO(P1 — Symbol Registry Promotion):
    Today ``url_slug`` comes from ``config.bi5_symbols.get_bi5_symbol_spec``,
    which is a hardcoded dict. Once ``engines.market_universe`` is promoted
    to the single source of truth, swap the lookup to consult the registry
    (``broker_class="dukascopy"`` → ``url_slug``). The HTTP layer below
    does NOT need to change.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

from config.bi5_symbols import get_bi5_symbol_spec
from data_engine.adapters.base import BI5Adapter, BI5HourBlob, normalize_hour_utc

logger = logging.getLogger(__name__)

DUKASCOPY_BASE_URL = "https://datafeed.dukascopy.com/datafeed"

# Public archive — no auth. UA is required (default httpx UA gets rate-limited
# more aggressively than a real-looking one).
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (AIStrategyFactory BI5 ingester; +https://emergentagent.com)"
)

# Conservative network defaults. Dukascopy occasionally serves slow.
DEFAULT_CONNECT_TIMEOUT_S = 10.0
DEFAULT_READ_TIMEOUT_S = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_S = 1.5  # exponential: 1.5, 2.25, 3.375 …


class DukascopyBI5Adapter(BI5Adapter):
    """HTTP adapter for Dukascopy's public BI5 tick archive."""

    source_id = "dukascopy"

    def __init__(
        self,
        *,
        base_url: str = DUKASCOPY_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        connect_timeout_s: float = DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout_s: float = DEFAULT_READ_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_s = float(retry_backoff_s)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=connect_timeout_s,
                read=read_timeout_s,
                write=read_timeout_s,
                pool=read_timeout_s,
            ),
            headers={"User-Agent": self._user_agent, "Accept": "*/*"},
            follow_redirects=True,
        )

    # ----- BI5Adapter ----------------------------------------------------

    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        spec = get_bi5_symbol_spec(symbol)
        hour_utc = normalize_hour_utc(hour_utc)
        url = self.build_url(spec.url_slug, hour_utc)

        payload = await self._get_with_retries(url)
        return BI5HourBlob(
            symbol=spec.symbol,
            hour_utc=hour_utc,
            payload=payload,
            source=self.source_id,
        )

    async def close(self) -> None:
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    # ----- internals -----------------------------------------------------

    def build_url(self, url_slug: str, hour_utc: datetime) -> str:
        """Build a Dukascopy datafeed URL for one hour of ticks.

        Dukascopy uses **0-indexed months** in the path — be careful.
        """
        month_idx = hour_utc.month - 1  # 0-indexed
        return (
            f"{self._base_url}/{url_slug}/"
            f"{hour_utc.year:04d}/{month_idx:02d}/{hour_utc.day:02d}/"
            f"{hour_utc.hour:02d}h_ticks.bi5"
        )

    async def _get_with_retries(self, url: str) -> bytes:
        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_retries):
            try:
                resp = await self._client.get(url)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning(
                    "bi5.dukascopy.transport_error url=%s attempt=%d/%d err=%s",
                    url, attempt + 1, self._max_retries, exc,
                )
                await asyncio.sleep(self._retry_backoff_s ** (attempt + 1))
                continue

            if resp.status_code == 200:
                return resp.content
            if resp.status_code == 404:
                # No file published for this hour → treat as "no ticks".
                # We still cache b"" so we never re-hit Dukascopy for it.
                logger.debug("bi5.dukascopy.404 url=%s", url)
                return b""
            if resp.status_code in (429, 500, 502, 503, 504):
                # Transient — retry.
                last_exc = httpx.HTTPStatusError(
                    f"transient {resp.status_code}", request=resp.request, response=resp
                )
                logger.warning(
                    "bi5.dukascopy.transient url=%s status=%d attempt=%d/%d",
                    url, resp.status_code, attempt + 1, self._max_retries,
                )
                await asyncio.sleep(self._retry_backoff_s ** (attempt + 1))
                continue

            # Permanent non-200, non-404 — surface immediately.
            raise httpx.HTTPStatusError(
                f"unexpected status {resp.status_code} for {url}",
                request=resp.request,
                response=resp,
            )

        # Exhausted retries.
        assert last_exc is not None
        raise last_exc

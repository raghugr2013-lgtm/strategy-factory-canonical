"""
P0A — abstract BI5 source adapter.

Concrete adapters fetch one hour of raw BI5 bytes for one symbol. They MUST
NOT decompress or aggregate — that is the tick_archive / tick_aggregator
responsibility. Keeping adapters dumb keeps the cache layer source-agnostic
and lets us replay archived bytes without re-hitting the upstream.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BI5HourBlob:
    """One hour of raw .bi5 bytes for one symbol, as returned by an adapter.

    ``payload`` may be empty (``b""``). Dukascopy uses 0-byte files to mean
    "the market was closed / no ticks this hour" — that is a legitimate
    response and MUST be cached on disk (otherwise we re-fetch closed hours
    forever).
    """

    symbol: str
    hour_utc: datetime          # tz-aware, minute=0, second=0, microsecond=0
    payload: bytes              # LZMA-compressed BI5 bytes; may be empty
    source: str                 # short adapter id, e.g. "dukascopy"


class BI5Adapter(ABC):
    """Source of raw, undecompressed, per-hour BI5 blobs."""

    #: short adapter id used in archive paths + Mongo source tags.
    source_id: str = "abstract"

    @abstractmethod
    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        """Return one hour of raw BI5 bytes for ``symbol`` at ``hour_utc``.

        Implementations MUST:
          * normalize ``hour_utc`` to tz-aware UTC, minute=0.
          * return an empty payload (not raise) when upstream reports
            "no data" for that hour (e.g. weekend / holiday).
          * raise on transport / decode errors so the caller can retry
            or surface the failure.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Release any underlying network resources. Idempotent."""
        return None


def normalize_hour_utc(when: datetime) -> datetime:
    """Round ``when`` down to the top of the UTC hour (tz-aware).

    Centralised so every layer (adapter, archive, aggregator) agrees on
    bucket boundaries.
    """
    from datetime import timezone

    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    else:
        when = when.astimezone(timezone.utc)
    return when.replace(minute=0, second=0, microsecond=0)

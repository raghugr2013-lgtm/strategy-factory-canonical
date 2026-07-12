"""
P0A — Tier-2 derivation: decode BI5 LZMA bytes → ticks → 1-minute OHLCV bars.

Dukascopy BI5 tick record layout (big-endian, 20 bytes):
    uint32  ms_offset_from_hour_start
    uint32  ask_price_fixedpt
    uint32  bid_price_fixedpt
    float32 ask_volume   (millions)
    float32 bid_volume   (millions)

Note: the volume fields are IEEE-754 floats, not ints — that's a common
gotcha. We unpack as ``>IIIff``.

This module is purely deterministic / stateless. It does NOT touch the
network, the filesystem cache, or MongoDB.

TODO(P1 — Symbol Registry Promotion):
    ``price_multiplier`` is currently sourced via ``config.bi5_symbols``.
    When the registry takes over, swap the lookup but keep the decode
    routine — the binary format is dictated by Dukascopy, not by us.
"""
from __future__ import annotations

import logging
import lzma
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional

from config.bi5_symbols import BI5SymbolSpec, get_bi5_symbol_spec
from data_engine.adapters.base import normalize_hour_utc

logger = logging.getLogger(__name__)

# ``>`` = big-endian; ``IIIff`` = 3×uint32 + 2×float32 = 20 bytes.
_TICK_STRUCT = struct.Struct(">IIIff")
TICK_RECORD_SIZE = _TICK_STRUCT.size  # 20

assert TICK_RECORD_SIZE == 20, "BI5 tick record must be exactly 20 bytes"


@dataclass(frozen=True)
class Tick:
    ts_utc: datetime          # tz-aware UTC tick timestamp
    bid: float                # decoded floating-point bid
    ask: float                # decoded floating-point ask
    bid_volume: float         # raw float volume (millions, as Dukascopy ships it)
    ask_volume: float


@dataclass(frozen=True)
class Bar1m:
    """One 1-minute OHLCV bar derived from BI5 ticks (mid-price)."""

    symbol: str
    minute_utc: datetime      # tz-aware, second=0, microsecond=0
    open: float
    high: float
    low: float
    close: float
    volume: float             # sum of (bid_volume + ask_volume) across ticks
    tick_count: int
    source: str = "bi5"


# ---------------------------------------------------------------------------
# Tick decode
# ---------------------------------------------------------------------------

def decode_bi5_hour(
    payload: bytes,
    *,
    hour_utc: datetime,
    spec: BI5SymbolSpec,
) -> List[Tick]:
    """Decompress + decode one hour of BI5 bytes into a list of ``Tick``.

    Returns ``[]`` for ``b""`` payloads (closed market). Raises ``ValueError``
    if the decompressed stream isn't a clean multiple of 20 bytes.
    """
    if not payload:
        return []

    hour_utc = normalize_hour_utc(hour_utc)

    # Dukascopy uses the **legacy LZMA-Alone** stream format (not XZ).
    try:
        raw = lzma.decompress(payload, format=lzma.FORMAT_ALONE)
    except lzma.LZMAError as exc:
        raise ValueError(f"BI5 LZMA decode failed for {spec.symbol}: {exc}") from exc

    if len(raw) % TICK_RECORD_SIZE != 0:
        raise ValueError(
            f"BI5 decompressed stream for {spec.symbol} is {len(raw)} bytes "
            f"— not a multiple of {TICK_RECORD_SIZE}"
        )

    mult = spec.price_multiplier
    ticks: List[Tick] = []
    append = ticks.append
    iter_unpack = _TICK_STRUCT.iter_unpack

    for ms_offset, ask_fp, bid_fp, ask_vol, bid_vol in iter_unpack(raw):
        ts = hour_utc + timedelta(milliseconds=int(ms_offset))
        append(Tick(
            ts_utc=ts,
            bid=bid_fp / mult,
            ask=ask_fp / mult,
            bid_volume=float(bid_vol),
            ask_volume=float(ask_vol),
        ))

    return ticks


# ---------------------------------------------------------------------------
# Tick → 1m bar aggregation
# ---------------------------------------------------------------------------

def _floor_minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def aggregate_ticks_to_1m(
    ticks: Iterable[Tick],
    *,
    symbol: str,
    source: str = "bi5",
) -> List[Bar1m]:
    """Bucket ticks into 1-minute OHLCV bars using mid-price.

    Bars are emitted only for minutes that contain at least one tick. Gap
    minutes are NOT synthesised here — that's a downstream concern.
    """
    ticks_list = list(ticks)
    if not ticks_list:
        return []

    # Ticks within an hour are usually already sorted; sort defensively.
    ticks_list.sort(key=lambda t: t.ts_utc)

    bars: List[Bar1m] = []
    cur_minute: Optional[datetime] = None
    o = h = l = c = 0.0
    vol = 0.0
    n = 0

    for t in ticks_list:
        mid = (t.bid + t.ask) * 0.5
        minute = _floor_minute(t.ts_utc)

        if cur_minute is None:
            cur_minute = minute
            o = h = l = c = mid
            vol = t.bid_volume + t.ask_volume
            n = 1
            continue

        if minute != cur_minute:
            bars.append(Bar1m(
                symbol=symbol, minute_utc=cur_minute,
                open=o, high=h, low=l, close=c,
                volume=vol, tick_count=n, source=source,
            ))
            cur_minute = minute
            o = h = l = c = mid
            vol = t.bid_volume + t.ask_volume
            n = 1
            continue

        if mid > h:
            h = mid
        if mid < l:
            l = mid
        c = mid
        vol += t.bid_volume + t.ask_volume
        n += 1

    # Flush the last bucket.
    if cur_minute is not None:
        bars.append(Bar1m(
            symbol=symbol, minute_utc=cur_minute,
            open=o, high=h, low=l, close=c,
            volume=vol, tick_count=n, source=source,
        ))

    return bars


def decode_and_aggregate(
    payload: bytes,
    *,
    symbol: str,
    hour_utc: datetime,
) -> List[Bar1m]:
    """Convenience: BI5 bytes → 1m bars in one call (for that one hour)."""
    spec = get_bi5_symbol_spec(symbol)
    ticks = decode_bi5_hour(payload, hour_utc=hour_utc, spec=spec)
    return aggregate_ticks_to_1m(ticks, symbol=spec.symbol)

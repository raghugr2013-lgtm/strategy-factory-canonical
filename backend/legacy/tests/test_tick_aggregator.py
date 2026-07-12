"""P0A — Tick decoder + 1m aggregator unit tests.

Builds a synthetic Dukascopy-compatible BI5 payload IN-MEMORY (no network),
compresses it with LZMA-Alone (the format Dukascopy ships), and verifies:

* decode_bi5_hour returns the exact tick count and price encoding
* aggregate_ticks_to_1m emits one bar per minute that contains ticks
* OHLC is mid-price; volume is bid+ask sums; tick_count is exact
"""
from __future__ import annotations

import lzma
import struct
from datetime import datetime, timezone
from typing import List, Tuple

import pytest

from config.bi5_symbols import get_bi5_symbol_spec
from data_engine.tick_aggregator import (
    Bar1m,
    aggregate_ticks_to_1m,
    decode_bi5_hour,
    Tick,
)


_TICK_STRUCT = struct.Struct(">IIIff")


def _pack_ticks_lzma_alone(
    raw_ticks: List[Tuple[int, int, int, float, float]],
) -> bytes:
    """Build a Dukascopy-style LZMA-Alone-compressed tick stream.

    Each tuple: ``(ms_offset, ask_fp, bid_fp, ask_vol, bid_vol)``.
    """
    buf = b"".join(_TICK_STRUCT.pack(*t) for t in raw_ticks)
    # FORMAT_ALONE = legacy lzma1, exactly what Dukascopy serves.
    return lzma.compress(buf, format=lzma.FORMAT_ALONE)


def test_decode_empty_payload_returns_empty_list():
    spec = get_bi5_symbol_spec("EURUSD")
    assert decode_bi5_hour(b"", hour_utc=datetime(2024, 1, 2, 7, tzinfo=timezone.utc), spec=spec) == []


def test_decode_three_ticks_within_one_hour_decodes_prices_correctly():
    spec = get_bi5_symbol_spec("EURUSD")  # price_multiplier 100_000 for 5-digit FX
    mult = spec.price_multiplier

    # 3 ticks in the SAME minute (07:00:00.000, 07:00:00.123, 07:00:30.500).
    payload = _pack_ticks_lzma_alone([
        (0,       int(1.1005 * mult), int(1.1000 * mult), 1.0, 2.0),
        (123,     int(1.1010 * mult), int(1.1005 * mult), 0.5, 0.5),
        (30_500,  int(1.1008 * mult), int(1.1003 * mult), 1.5, 1.5),
    ])

    hour_utc = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    ticks = decode_bi5_hour(payload, hour_utc=hour_utc, spec=spec)

    assert len(ticks) == 3
    # First tick: bid 1.1000 ± float precision, ask 1.1005
    assert ticks[0].bid == pytest.approx(1.1000, abs=1e-9)
    assert ticks[0].ask == pytest.approx(1.1005, abs=1e-9)
    # Timestamp offsets honoured
    assert ticks[0].ts_utc == hour_utc
    assert ticks[1].ts_utc.microsecond == 123_000
    assert ticks[2].ts_utc.second == 30


def test_decode_malformed_raises_value_error():
    """A non-LZMA payload must raise ValueError, never silently swallow."""
    spec = get_bi5_symbol_spec("EURUSD")
    with pytest.raises(ValueError):
        decode_bi5_hour(b"not-lzma-bytes", hour_utc=datetime(2024, 1, 2, 7, tzinfo=timezone.utc), spec=spec)


def test_aggregate_one_minute_one_bar_mid_price_ohlc():
    """All ticks in one minute → one bar with correct mid OHLC."""
    base = datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc)
    ticks = [
        Tick(ts_utc=base,                         bid=1.10, ask=1.12, bid_volume=1.0, ask_volume=1.0),  # mid=1.11
        Tick(ts_utc=base.replace(second=10),      bid=1.20, ask=1.22, bid_volume=2.0, ask_volume=0.0),  # mid=1.21 (high)
        Tick(ts_utc=base.replace(second=20),      bid=1.00, ask=1.02, bid_volume=0.5, ask_volume=0.5),  # mid=1.01 (low)
        Tick(ts_utc=base.replace(second=30),      bid=1.05, ask=1.07, bid_volume=0.5, ask_volume=0.5),  # mid=1.06 (close)
    ]
    bars = aggregate_ticks_to_1m(ticks, symbol="EURUSD")

    assert len(bars) == 1
    b = bars[0]
    assert isinstance(b, Bar1m)
    assert b.symbol == "EURUSD"
    assert b.minute_utc == base
    assert b.open == pytest.approx(1.11)
    assert b.high == pytest.approx(1.21)
    assert b.low == pytest.approx(1.01)
    assert b.close == pytest.approx(1.06)
    assert b.tick_count == 4
    assert b.volume == pytest.approx(6.0)
    assert b.source == "bi5"


def test_aggregate_two_minutes_two_bars():
    """Two minutes with ticks → two bars; minutes without ticks → no bar."""
    base = datetime(2024, 1, 2, 7, 0, tzinfo=timezone.utc)
    ticks = [
        Tick(ts_utc=base.replace(minute=0, second=5),  bid=1.10, ask=1.12, bid_volume=1, ask_volume=0),
        Tick(ts_utc=base.replace(minute=2, second=15), bid=1.30, ask=1.32, bid_volume=2, ask_volume=0),  # minute 1 skipped
    ]
    bars = aggregate_ticks_to_1m(ticks, symbol="EURUSD")
    assert [b.minute_utc.minute for b in bars] == [0, 2]


def test_aggregate_empty_input_returns_empty_list():
    assert aggregate_ticks_to_1m([], symbol="EURUSD") == []

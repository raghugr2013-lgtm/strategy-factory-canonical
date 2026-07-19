"""CTS resampler — pure M1 → HTF aggregation.

Idempotent, deterministic pure function. Same input → same output.
No I/O; no DB; no framework imports.

Bar-shape convention:
  * timestamp = OPEN of the bar (not close)
  * pandas `resample(rule).ohlc()` semantics — label='left', closed='left'
  * volume aggregated as sum

Timeframe rules (pandas offset aliases):
  1m → not resampled (canonical)
  5m → "5min"
  15m → "15min"
  30m → "30min"
  1h → "1h"
  4h → "4h"
  1d → "1D"
"""
from __future__ import annotations

import logging
import time
from typing import List

import pandas as pd

from .types import Candle, ResampleReport

logger = logging.getLogger(__name__)

_PANDAS_RULE = {
    "1m":  "1min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1h",
    "4h":  "4h",
    "1d":  "1D",
}


def is_canonical_tf(timeframe: str) -> bool:
    """Return True when `timeframe` is the canonical (M1) source."""
    return _norm_tf(timeframe) == "1m"


def _norm_tf(tf: str) -> str:
    """Normalise a timeframe to canonical lower-case form.

    Accepts `M1|1m`, `H1|1h`, `D1|1d`, etc.
    """
    return {
        "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
        "H1": "1h", "H4": "4h", "D1": "1d",
    }.get(tf, tf.lower())


def resample_m1_to(candles: List[Candle], target_tf: str) -> tuple[List[Candle], ResampleReport]:
    """Aggregate M1 candles into `target_tf` OHLCV bars.

    Args:
        candles:    list of M1 Candles, sorted by timestamp ascending
        target_tf:  target timeframe (e.g. "H1", "1h", "15m")

    Returns:
        (aggregated_candles, ResampleReport)
    """
    t0 = time.perf_counter()
    target = _norm_tf(target_tf)
    if not candles:
        return [], ResampleReport(0, 0, 0.0, "1m", target)
    if target == "1m":
        return list(candles), ResampleReport(len(candles), len(candles), 0.0, "1m", "1m")
    rule = _PANDAS_RULE.get(target)
    if rule is None:
        raise ValueError(f"unsupported target timeframe: {target_tf}")

    # Build DataFrame — timestamps as UTC-aware DatetimeIndex
    df = pd.DataFrame(
        [
            {"timestamp": c.timestamp, "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()

    agg = df.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "high", "low", "close"])

    out: List[Candle] = [
        Candle(
            timestamp=ts.isoformat().replace("+00:00", "+00:00") if ts.tzinfo else ts.isoformat() + "+00:00",
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume),
        )
        for ts, row in agg.iterrows()
    ]
    dur_ms = (time.perf_counter() - t0) * 1000.0
    return out, ResampleReport(
        input_rows=len(candles),
        output_rows=len(out),
        duration_ms=dur_ms,
        from_tf="1m",
        to_tf=target,
    )


def bucket_key_for(symbol: str, timeframe: str, ts_iso: str) -> str:
    """Return the 3-axis sharding key for a given (symbol, tf, timestamp).

    Bucket granularity: monthly (yyyy-mm) per operator directive §10.2
    for M15 and below; kept monthly for H1+ too in Stage 2 for
    simplicity — recalibrate to quarterly in a later stage if bucket
    counts explode.
    """
    tf = _norm_tf(timeframe)
    # Extract yyyy-mm from ISO string without a full parse — cheaper
    yyyy_mm = ts_iso[:7]  # e.g. "2026-02"
    return f"{symbol}|{tf}|{yyyy_mm}"


def bucket_month_start(ts_iso: str) -> str:
    """First-of-month ISO for a given ISO string. `2026-02-15...` → `2026-02-01T00:00:00+00:00`."""
    yyyy_mm = ts_iso[:7]
    return f"{yyyy_mm}-01T00:00:00+00:00"

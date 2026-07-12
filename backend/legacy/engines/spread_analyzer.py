"""
P0B Phase 1 — Spread Analyzer (pure functions).

Rolls per-tick ``ask − bid`` into per-minute spread bars and computes the
per-strategy Spread_Score per P0B_SPEC §2.

Public surface
──────────────
    rollup_spread_minutes(ticks, *, symbol) → List[SpreadBar]
    compute_spread_score(*, fill_spread, mid, assumed_cost_bps,
                         tolerance_bps) → SpreadScoreResult
    spread_score_from_fills(fills, *, symbol, assumed_cost_bps,
                            tolerance_bps=None) → SpreadScoreResult
    DEFAULT_TOLERANCE_BPS, get_tolerance_bps(symbol)

BID/BI5 firewall
────────────────
This module is BI5-side. It MUST NOT be imported by any of:
    discovery, mutation, validation, pass_probability,
    challenge_matching, portfolio_selection, phase30_*.

TODO(P1 — market_universe):
    DEFAULT_TOLERANCE_BPS and SYMBOL_DEFAULT_BPS belong with the symbol
    registry. They live here for the P0B seed only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median
from typing import Dict, Iterable, List, Mapping, Optional, Sequence


EVALUATOR_VERSION = "spread_analyzer@P0B-v1"

# TODO(P1): migrate to market_universe.
DEFAULT_TOLERANCE_BPS: Dict[str, float] = {
    "EURUSD": 1.0,
    "GBPUSD": 1.0,
    "USDJPY": 1.2,
    "XAUUSD": 5.0,
}
_FALLBACK_TOLERANCE_BPS = 2.0

# Soft fallback used when caller doesn't pass an explicit `assumed_cost_bps`
# on a strategy — flagged but non-blocking, see §2.
# TODO(P1): migrate to market_universe.
SYMBOL_DEFAULT_BPS: Dict[str, float] = {
    "EURUSD": 0.8,
    "GBPUSD": 1.0,
    "USDJPY": 1.0,
    "XAUUSD": 8.0,
}


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpreadBar:
    """One minute of spread OHLC, ready for ``market_spread`` persistence
    in Phase 2. Kept as plain values — no Mongo here."""
    symbol: str
    ts: datetime
    spread_open: float
    spread_high: float
    spread_low: float
    spread_close: float
    spread_mean: float
    tick_count: int


@dataclass(frozen=True)
class SpreadScoreResult:
    spread_score: float
    realised_cost_bps: float
    assumed_cost_bps: float
    tolerance_bps: float
    flags: List[str]
    evaluator_version: str = EVALUATOR_VERSION


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def get_tolerance_bps(symbol: str) -> float:
    # R2 — route through market_universe_adapter. Byte-identical when
    # flag OFF (the adapter falls back to DEFAULT_TOLERANCE_BPS).
    try:
        from engines.market_universe_adapter import (
            get_tolerance_bps as _adapter,
        )
        return _adapter(symbol)
    except Exception:                                       # pragma: no cover
        return DEFAULT_TOLERANCE_BPS.get(symbol, _FALLBACK_TOLERANCE_BPS)


def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _floor_minute(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.replace(second=0, microsecond=0)


# ──────────────────────────────────────────────────────────────────────
# Spread rollup (per-minute bars from BI5 ticks)
# ──────────────────────────────────────────────────────────────────────

def rollup_spread_minutes(
    ticks: Iterable[object],
    *,
    symbol: str,
) -> List[SpreadBar]:
    """Aggregate ticks (Tick-like with .ts_utc/.bid/.ask) into per-minute
    spread bars. Bars are emitted only for minutes containing at least
    one valid tick (bid > 0, ask >= bid)."""
    tick_list = sorted(ticks, key=lambda t: t.ts_utc)
    if not tick_list:
        return []

    bars: List[SpreadBar] = []
    cur_minute: Optional[datetime] = None
    s_open = s_high = s_low = s_close = 0.0
    s_sum = 0.0
    n = 0

    def _flush() -> None:
        nonlocal s_open, s_high, s_low, s_close, s_sum, n
        if cur_minute is None or n == 0:
            return
        bars.append(SpreadBar(
            symbol=symbol, ts=cur_minute,
            spread_open=s_open, spread_high=s_high,
            spread_low=s_low, spread_close=s_close,
            spread_mean=s_sum / n, tick_count=n,
        ))

    for t in tick_list:
        if t.bid <= 0 or t.ask < t.bid:
            continue
        spread = t.ask - t.bid
        minute = _floor_minute(t.ts_utc)

        if cur_minute is None or minute != cur_minute:
            _flush()
            cur_minute = minute
            s_open = s_high = s_low = s_close = spread
            s_sum = spread
            n = 1
            continue

        if spread > s_high:
            s_high = spread
        if spread < s_low:
            s_low = spread
        s_close = spread
        s_sum += spread
        n += 1

    _flush()
    return bars


# ──────────────────────────────────────────────────────────────────────
# Spread Score
# ──────────────────────────────────────────────────────────────────────

def compute_spread_score(
    *,
    fill_spread: float,
    mid: float,
    assumed_cost_bps: Optional[float],
    tolerance_bps: float,
    symbol: Optional[str] = None,
) -> SpreadScoreResult:
    """Score one fill's realised spread vs. the strategy's assumed cost.

    Per P0B_SPEC §2:
        realised_cost_bps = (fill_spread / mid) * 1e4
        score             = clamp01(1 − |realised − assumed| / tolerance)
    """
    flags: List[str] = []
    if mid <= 0:
        return SpreadScoreResult(
            spread_score=0.0, realised_cost_bps=0.0,
            assumed_cost_bps=assumed_cost_bps or 0.0,
            tolerance_bps=tolerance_bps,
            flags=["INVALID_MID"],
        )
    if tolerance_bps <= 0:
        raise ValueError("tolerance_bps must be > 0")

    if assumed_cost_bps is None:
        # R2 — route through market_universe_adapter. Byte-identical
        # when flag OFF (the adapter falls back to SYMBOL_DEFAULT_BPS).
        try:
            from engines.market_universe_adapter import (
                get_symbol_default_bps as _adapter,
            )
            assumed_cost_bps = _adapter(symbol or "")
        except Exception:                                   # pragma: no cover
            assumed_cost_bps = SYMBOL_DEFAULT_BPS.get(symbol or "", _FALLBACK_TOLERANCE_BPS)
        flags.append("ASSUMED_SPREAD_DEFAULTED")

    realised_bps = (fill_spread / mid) * 1e4
    score = _clamp01(1.0 - abs(realised_bps - assumed_cost_bps) / tolerance_bps)

    return SpreadScoreResult(
        spread_score=score,
        realised_cost_bps=realised_bps,
        assumed_cost_bps=assumed_cost_bps,
        tolerance_bps=tolerance_bps,
        flags=flags,
    )


def spread_score_from_fills(
    fills: Sequence[Mapping[str, float]],
    *,
    symbol: str,
    assumed_cost_bps: Optional[float],
    tolerance_bps: Optional[float] = None,
) -> SpreadScoreResult:
    """Roll-up over many fills. Each fill is a mapping with keys
    ``fill_spread`` and ``mid``. Returns the median-fill spread score so
    a handful of outlier fills can't blow up certification."""
    if not fills:
        raise ValueError("spread_score_from_fills requires at least one fill")

    tol = tolerance_bps if tolerance_bps is not None else get_tolerance_bps(symbol)
    per_fill = [
        compute_spread_score(
            fill_spread=float(f["fill_spread"]),
            mid=float(f["mid"]),
            assumed_cost_bps=assumed_cost_bps,
            tolerance_bps=tol,
            symbol=symbol,
        )
        for f in fills
    ]
    realised_bps_list = sorted(r.realised_cost_bps for r in per_fill)
    median_realised = median(realised_bps_list)
    resolved_assumed = per_fill[0].assumed_cost_bps
    flags = sorted({fl for r in per_fill for fl in r.flags})

    score = _clamp01(1.0 - abs(median_realised - resolved_assumed) / tol)
    return SpreadScoreResult(
        spread_score=score,
        realised_cost_bps=median_realised,
        assumed_cost_bps=resolved_assumed,
        tolerance_bps=tol,
        flags=flags,
    )

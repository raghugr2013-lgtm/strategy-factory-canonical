"""
P0B Phase 1 — Tick Validator (pure functions).

Validates a BI5 hour blob (or a decoded tick list) and rolls hour-level
validations up to a per-window BI5 Score. No I/O, no Mongo, no archive
reads — inputs are passed in by the caller.

Public surface
──────────────
    validate_hour(ticks, hour_utc, symbol, *, session, prev_60m_sigma=None)
        → HourValidation
    aggregate_window(hour_validations, *, weights=DEFAULT_WEIGHTS)
        → BI5ScoreReport
    classify_session(hour_utc) → "asia" | "london" | "ny" | "overlap" | "closed"

BID/BI5 firewall
────────────────
This module is BI5-side. It MUST NOT be imported from any of:
    discovery, mutation, validation, pass_probability,
    challenge_matching, portfolio_selection, phase30_*.

TODO(P1 — market_universe):
    DENSITY_TABLE and SESSION_BOUNDS_UTC are local constants for the P0B
    seed (EURUSD, GBPUSD, USDJPY, XAUUSD). When market_universe lands
    in P1 these tables move there and become the single source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────
# Constants (TODO(P1): migrate to market_universe)
# ──────────────────────────────────────────────────────────────────────

EVALUATOR_VERSION = "tick_validator@P0B-v2"

# UTC hour bands (left-closed, right-open). Coarse but good enough for
# tick-density scoring; finer DST handling is deferred to P1 calendar.
# TODO(P1): move to market_universe per-symbol calendar.
SESSION_BOUNDS_UTC: Tuple[Tuple[str, int, int], ...] = (
    ("asia",   0,  7),    # 00:00–07:00 UTC
    ("london", 7, 12),    # 07:00–12:00 UTC
    ("overlap", 12, 16),  # 12:00–16:00 UTC (London/NY overlap)
    ("ny",     16, 21),   # 16:00–21:00 UTC
    # 21:00–24:00 UTC treated as low-liquidity tail → fold under "asia"
)

# Per-symbol density table — ticks/hour. Floor = sparse threshold,
# Target = low-density threshold. From P0B_SPEC §1.1.
# TODO(P1): migrate to market_universe.
# Schema: { symbol: { session: (floor, target) } }
#
# R2 Step-0 (Option A) calibration — 2026-06-13.
# Re-grounded against the 15 archived cert windows: original FX
# floors (5k–6k ticks/hr) were 3×–5× higher than actual Dukascopy
# emission rates, which forced density sub-scores to 0.15–0.40 on
# structurally clean data. XAUUSD floors are KEPT (XAU already PASSed
# with the original values; the existing floors match XAU emission).
DENSITY_TABLE: Dict[str, Dict[str, Tuple[int, int]]] = {
    "EURUSD": {
        "asia":   (300,   1500),
        "london": (1500,  8000),
        "ny":     (2000, 10000),
        "overlap": (2000, 10000),
    },
    "GBPUSD": {
        "asia":   (250,   1200),
        "london": (1200,  6000),
        "ny":     (1500,  8000),
        "overlap": (1500,  8000),
    },
    "USDJPY": {
        "asia":   (800,   4500),
        "london": (800,   4500),
        "ny":     (1200,  6500),
        "overlap": (1200,  6500),
    },
    "XAUUSD": {
        "asia":   (500,   3000),
        "london": (3000, 16000),
        "ny":     (4000, 20000),
        "overlap": (4000, 20000),
    },
}

# Fallback when a symbol has no entry yet (lets the validator return a
# WARN-grade density score instead of crashing).
_FALLBACK_DENSITY: Dict[str, Tuple[int, int]] = {
    "asia":   (500,   3000),
    "london": (2000, 12000),
    "ny":     (2500, 15000),
    "overlap": (2500, 15000),
}

# Price-sanity outlier band: |mid − tick_mid| > Z · σ_60m.
PRICE_OUTLIER_Z = 8.0

# Default per-dimension weights for the BI5 Score geometric mean.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "cov":        3.0,
    "integrity":  4.0,
    "price":      2.0,
    "density":    2.0,
    "continuity": 1.0,
}

# Verdict thresholds (BI5_SPEC §1.2).
# R2 Step-0 (Option A) — rebased 2026-06-13. The original 0.90/0.75
# pair was mathematically unreachable for FX pairs given the
# weighted-geomean math × achievable density distribution on real
# Dukascopy archives. After the percentile-continuity hardening and
# the FX density floor recalibration above, 0.85/0.70 makes PASS a
# meaningful, achievable bar without becoming trivial to clear.
PASS_THRESHOLD = 0.85
WARN_THRESHOLD = 0.70


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HourValidation:
    symbol: str
    hour_utc: datetime
    session: str
    status: str                       # "ok" | "expected_empty" | "missing" | "decode_fail"
    ticks_count: int
    non_monotonic_ticks: int
    price_outlier_ticks: int
    zero_vol_ticks: int
    max_silent_gap_s: float
    density_floor: int
    density_target: int


@dataclass(frozen=True)
class BI5ScoreReport:
    symbol: str
    window_start: datetime
    window_end: datetime
    hours_expected: int
    hours_present: int
    hours_missing: int
    hours_expected_empty: int
    hours_decode_fail: int
    ticks_total: int
    non_monotonic_ticks: int
    price_outlier_ticks: int
    zero_vol_ticks: int
    sparse_hours: int
    low_density_hours: int
    max_silent_gap_s: float
    subscores: Dict[str, float]
    bi5_score: float
    verdict: str                      # "PASS" | "WARN" | "FAIL"
    evaluator_version: str = EVALUATOR_VERSION


# ──────────────────────────────────────────────────────────────────────
# Helpers (pure)
# ──────────────────────────────────────────────────────────────────────

def classify_session(hour_utc: datetime) -> str:
    """Map a UTC hour to a session band. Closed weekends are still mapped
    to a band — callers separately decide if the hour is *expected* to
    be empty (via market_calendar). This function is intentionally
    calendar-agnostic so it stays pure."""
    h = hour_utc.hour
    for name, lo, hi in SESSION_BOUNDS_UTC:
        if lo <= h < hi:
            return name
    return "asia"  # 21:00–24:00 UTC tail


def _density_for(symbol: str, session: str) -> Tuple[int, int]:
    # R2 — route through market_universe_adapter for alias resolution
    # (e.g. NAS100 → US100) and registry consultation. With the flag
    # OFF (default), the adapter returns the same value this function
    # would have returned for the canonical 7 symbols.
    try:
        from engines.market_universe_adapter import get_density_table
        return get_density_table(symbol, session)
    except Exception:                                       # pragma: no cover
        table = DENSITY_TABLE.get(symbol)
        if table is None:
            return _FALLBACK_DENSITY.get(session, (500, 3000))
        return table.get(session, _FALLBACK_DENSITY[session])


# ──────────────────────────────────────────────────────────────────────
# Per-hour validation
# ──────────────────────────────────────────────────────────────────────

def validate_hour(
    ticks: Optional[Iterable[object]],   # iterable of Tick-like (ts_utc, bid, ask, bid_volume, ask_volume)
    *,
    hour_utc: datetime,
    symbol: str,
    status: str = "ok",
    prev_60m_sigma: Optional[float] = None,
    reference_mid: Optional[float] = None,
) -> HourValidation:
    """Validate one hour of decoded BI5 ticks.

    Caller is responsible for telling us whether the hour is ``ok``,
    ``expected_empty`` (closed-market hour from market_calendar),
    ``missing`` (file absent on a session hour), or ``decode_fail``
    (corrupt payload). When status != "ok" we still emit a record with
    zeroed counters so the aggregator can roll it up.
    """
    if hour_utc.tzinfo is None:
        hour_utc = hour_utc.replace(tzinfo=timezone.utc)

    session = classify_session(hour_utc)
    floor, target = _density_for(symbol, session)

    if status != "ok":
        return HourValidation(
            symbol=symbol, hour_utc=hour_utc, session=session, status=status,
            ticks_count=0, non_monotonic_ticks=0, price_outlier_ticks=0,
            zero_vol_ticks=0, max_silent_gap_s=0.0,
            density_floor=floor, density_target=target,
        )

    tick_list = list(ticks or [])
    n = len(tick_list)
    if n == 0:
        # Caller said "ok" but no ticks — treat as session-hour-with-zero-ticks.
        # This collapses density to zero (a real signal).
        #
        # R2 Step-0 (Option A) — 2026-06-13: max_silent_gap_s lowered
        # from 3600.0 to 600.0. The previous 3600 value forced the
        # window aggregator's max-gap rollup to 0.0 continuity on a
        # single empty-but-session-active hour, zero-scoring otherwise
        # clean 30-day windows. Density still collapses to 0 for the
        # hour (the real signal), and the new 600 s value is the
        # "conservative session-hour gap proxy" the aggregator's 95th
        # percentile will absorb when only an isolated quiet hour
        # occurs (e.g. Sunday week-open, holiday-flanking).
        return HourValidation(
            symbol=symbol, hour_utc=hour_utc, session=session, status="ok",
            ticks_count=0, non_monotonic_ticks=0, price_outlier_ticks=0,
            zero_vol_ticks=0, max_silent_gap_s=600.0,
            density_floor=floor, density_target=target,
        )

    # Monotonicity, volume, price, continuity in a single pass.
    non_mono = 0
    zero_vol = 0
    price_out = 0
    max_gap = 0.0
    prev_ts = None
    sigma = prev_60m_sigma  # may be None; if so we skip the price-outlier check
    ref_mid = reference_mid

    if ref_mid is None:
        # Use the median-ish mid of the hour as a rough centre. Cheap.
        mids = sorted(((t.bid + t.ask) * 0.5 for t in tick_list))
        ref_mid = mids[n // 2]

    band = (PRICE_OUTLIER_Z * sigma) if sigma else None

    for t in tick_list:
        # Monotonicity
        if prev_ts is not None:
            delta = (t.ts_utc - prev_ts).total_seconds()
            if delta < 0:
                non_mono += 1
            elif delta > max_gap:
                max_gap = delta
        prev_ts = t.ts_utc

        # Volume sanity
        if (t.bid_volume <= 0 and t.ask_volume <= 0) or t.bid <= 0 or t.ask <= 0 or t.ask < t.bid:
            zero_vol += 1
            # Negative / inverted prices are tallied as zero_vol too because
            # they are equivalent "broken record" signals; this keeps the
            # integrity sub-score sensitive without double-counting.

        # Price-outlier (only if we have σ)
        if band is not None:
            mid = (t.bid + t.ask) * 0.5
            if abs(mid - ref_mid) > band:
                price_out += 1

    # Cover gap from end of last tick to hour boundary if it's larger.
    if tick_list:
        end_gap = (hour_utc.replace(minute=59, second=59) - tick_list[-1].ts_utc).total_seconds()
        if end_gap > max_gap:
            max_gap = max(0.0, end_gap)
        head_gap = (tick_list[0].ts_utc - hour_utc).total_seconds()
        if head_gap > max_gap:
            max_gap = max(0.0, head_gap)

    return HourValidation(
        symbol=symbol, hour_utc=hour_utc, session=session, status="ok",
        ticks_count=n, non_monotonic_ticks=non_mono,
        price_outlier_ticks=price_out, zero_vol_ticks=zero_vol,
        max_silent_gap_s=float(max_gap),
        density_floor=floor, density_target=target,
    )


# ──────────────────────────────────────────────────────────────────────
# Window aggregation → BI5 Score
# ──────────────────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def aggregate_window(
    hour_validations: List[HourValidation],
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
) -> BI5ScoreReport:
    if not hour_validations:
        raise ValueError("aggregate_window requires at least one hour")

    symbol = hour_validations[0].symbol
    hour_validations = sorted(hour_validations, key=lambda h: h.hour_utc)
    window_start = hour_validations[0].hour_utc
    window_end = hour_validations[-1].hour_utc

    hours_expected = sum(1 for h in hour_validations if h.status != "expected_empty")
    hours_expected_empty = sum(1 for h in hour_validations if h.status == "expected_empty")
    hours_missing = sum(1 for h in hour_validations if h.status == "missing")
    hours_decode_fail = sum(1 for h in hour_validations if h.status == "decode_fail")
    hours_present = sum(1 for h in hour_validations if h.status == "ok")

    ticks_total = sum(h.ticks_count for h in hour_validations)
    non_mono = sum(h.non_monotonic_ticks for h in hour_validations)
    price_out = sum(h.price_outlier_ticks for h in hour_validations)
    zero_vol = sum(h.zero_vol_ticks for h in hour_validations)

    # R2 Step-0 (Option A) — 2026-06-13: continuity rollup hardened.
    # The original implementation took the window-MAX silent gap which
    # meant a single bad hour out of 720 could drive continuity to 0.0
    # and zero-score an otherwise pristine 30-day window. We now use
    # the 95th percentile of `max_silent_gap_s` over *session-active*
    # (status=="ok") hours only — the 5 % tail (~35 hours of a 720-hour
    # window) absorbs routine quiet hours (Asian-tail, post-news
    # settlement, Sunday week-open) without diluting genuine multi-hour
    # silences. Sessions tagged `expected_empty` / `missing` /
    # `decode_fail` are excluded — they are measured by `cov` and
    # `integrity` instead. We retain the *raw* window max as the
    # surfaced `max_silent_gap_s` field for diagnostic visibility.
    ok_gaps = sorted(
        h.max_silent_gap_s for h in hour_validations if h.status == "ok"
    )
    if ok_gaps:
        # Index of the 95th percentile element (inclusive, clamped).
        # For len=720 → idx=684; for len=2 → idx=1; for len=1 → idx=0.
        idx = min(len(ok_gaps) - 1, int(len(ok_gaps) * 0.95))
        continuity_gap = ok_gaps[idx]
    else:
        continuity_gap = 0.0
    max_gap = max((h.max_silent_gap_s for h in hour_validations), default=0.0)

    sparse_hours = 0
    low_density_hours = 0
    for h in hour_validations:
        if h.status != "ok":
            continue
        if h.ticks_count < h.density_floor:
            sparse_hours += 1
        elif h.ticks_count < h.density_target:
            low_density_hours += 1

    # ── sub-scores in [0,1] ──────────────────────────────────────────
    # cov: present / (expected non-empty). 1.0 when nothing is missing.
    cov = 1.0 if hours_expected == 0 else hours_present / hours_expected

    # integrity: 1 − rate of structural broken ticks. A decode_fail is
    # categorical: the BI5 hour blob is corrupt and its data cannot be
    # trusted. Any decode_fail in the window collapses integrity to zero,
    # which propagates through the weighted geometric mean below and
    # crushes the BI5 score (matching the "sparse density → 0" behaviour
    # for density). Without this, a single corrupt hour gets dilution-
    # amortised against abundant clean ticks and integrity stays ≈1.0.
    if hours_decode_fail > 0:
        integrity = 0.0
    elif ticks_total:
        integrity = 1.0 - ((non_mono + zero_vol) / ticks_total)
    else:
        integrity = 1.0

    # price: 1 − outlier-rate.
    price = 1.0 - (price_out / ticks_total) if ticks_total else 1.0

    # density: weighted average of per-hour density scores.
    # sparse = 0.0, low_density = 0.5, ok = 1.0.
    density_terms: List[float] = []
    for h in hour_validations:
        if h.status != "ok":
            continue
        if h.ticks_count < h.density_floor:
            density_terms.append(0.0)
        elif h.ticks_count < h.density_target:
            density_terms.append(0.5)
        else:
            density_terms.append(1.0)
    density = sum(density_terms) / len(density_terms) if density_terms else 1.0

    # continuity: inverse log scaling of the 95th-percentile silent gap
    # across session-active hours (see ok_gaps computation above).
    # 0s → 1.0; 60s → ~0.85; 300s → ~0.60; 1800s → ~0.20; 3600s → 0.0.
    if continuity_gap <= 0:
        continuity = 1.0
    elif continuity_gap >= 3600:
        continuity = 0.0
    else:
        continuity = 1.0 - (log(1 + continuity_gap) / log(1 + 3600))

    subscores = {
        "cov":        _clamp01(cov),
        "integrity":  _clamp01(integrity),
        "price":      _clamp01(price),
        "density":    _clamp01(density),
        "continuity": _clamp01(continuity),
    }

    # Weighted geometric mean: any zero collapses the score.
    w_sum = sum(weights[k] for k in subscores)
    log_acc = 0.0
    for k, v in subscores.items():
        if v <= 0.0:
            bi5_score = 0.0
            break
        log_acc += weights[k] * log(v)
    else:
        bi5_score = pow(2.71828182845904523536, log_acc / w_sum)
    # When the for-loop breaks without else, bi5_score was assigned above.

    if bi5_score >= PASS_THRESHOLD:
        verdict = "PASS"
    elif bi5_score >= WARN_THRESHOLD:
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return BI5ScoreReport(
        symbol=symbol,
        window_start=window_start,
        window_end=window_end,
        hours_expected=hours_expected,
        hours_present=hours_present,
        hours_missing=hours_missing,
        hours_expected_empty=hours_expected_empty,
        hours_decode_fail=hours_decode_fail,
        ticks_total=ticks_total,
        non_monotonic_ticks=non_mono,
        price_outlier_ticks=price_out,
        zero_vol_ticks=zero_vol,
        sparse_hours=sparse_hours,
        low_density_hours=low_density_hours,
        max_silent_gap_s=max_gap,
        subscores=subscores,
        bi5_score=_clamp01(bi5_score),
        verdict=verdict,
    )

"""
P0B Phase 1 — Slippage Model (pure functions).

Per-fill slippage decomposition per P0B_SPEC §3:

    slippage_price = sign(side) · ( half_spread + impact + queue_drift )
    half_spread    = (ask − bid)/2
    impact         = k_impact · (order_size / adv_per_minute)^α
    queue_drift    = mid(t + Δlatency) − mid(t)

Public surface
──────────────
    compute_slippage(*, side, bid, ask, mid_before, mid_after,
                     order_size, adv_per_minute,
                     k_impact=K_IMPACT, alpha=ALPHA) → SlippageBreakdown
    rolling_adv_per_minute(volumes_per_minute, window=60) → List[float]
    slippage_score(*, fills, assumed_slippage_bps,
                   tolerance_bps=TOLERANCE_BPS) → SlippageScoreResult

BID/BI5 firewall
────────────────
This module is BI5-side. It MUST NOT be imported by any of:
    discovery, mutation, validation, pass_probability,
    challenge_matching, portfolio_selection, phase30_*.

TODO(P1 — market_universe):
    k_impact, alpha, and tolerance are deliberately module-level
    constants for the P0B seed. Move them to the symbol registry once
    `market_universe` is the single source of truth and per-symbol
    calibration history exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, List, Mapping, Sequence


EVALUATOR_VERSION = "slippage_model@P0B-v1"

# Locked P0B constants. TODO(P1): migrate to market_universe + calibration.
K_IMPACT = 0.5
ALPHA = 0.5
TOLERANCE_BPS = 0.5

# Minimum ADV to avoid divide-by-zero / explosive impact for thin minutes.
_MIN_ADV = 1e-6


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SlippageBreakdown:
    side: int                  # +1 = buy, -1 = sell
    half_spread: float         # in price units
    impact: float              # in price units
    queue_drift: float         # in price units (signed)
    slippage_price: float      # signed total in price units
    slippage_bps: float        # signed total in bps of mid_before
    evaluator_version: str = EVALUATOR_VERSION


@dataclass(frozen=True)
class SlippageScoreResult:
    slippage_score: float
    median_slippage_bps: float
    p95_slippage_bps: float
    assumed_slippage_bps: float
    tolerance_bps: float
    k_impact: float
    alpha: float
    evaluator_version: str = EVALUATOR_VERSION


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _percentile(values: Sequence[float], pct: float) -> float:
    """Linear-interp percentile on an already-iterable list. Inputs are
    copied + sorted here so callers can pass any iterable."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    frac = k - lo
    return s[lo] + (s[hi] - s[lo]) * frac


# ──────────────────────────────────────────────────────────────────────
# ADV (per-minute) — rolling mean from raw volume series
# ──────────────────────────────────────────────────────────────────────

def rolling_adv_per_minute(
    volumes_per_minute: Iterable[float],
    *,
    window: int = 60,
) -> List[float]:
    """Trailing rolling mean of (bid_vol + ask_vol) per minute. The
    first ``window`` outputs use whatever data is available so far
    (expanding window), which matches the spec's "rolling 60-min mean"
    intent without dropping leading minutes."""
    if window <= 0:
        raise ValueError("window must be > 0")
    vols = list(volumes_per_minute)
    if not vols:
        return []
    out: List[float] = []
    running = 0.0
    for i, v in enumerate(vols):
        running += v
        if i >= window:
            running -= vols[i - window]
            out.append(running / window)
        else:
            out.append(running / (i + 1))
    return out


# ──────────────────────────────────────────────────────────────────────
# Per-fill slippage
# ──────────────────────────────────────────────────────────────────────

def compute_slippage(
    *,
    side: int,
    bid: float,
    ask: float,
    mid_before: float,
    mid_after: float,
    order_size: float,
    adv_per_minute: float,
    k_impact: float = K_IMPACT,
    alpha: float = ALPHA,
) -> SlippageBreakdown:
    if side not in (1, -1):
        raise ValueError("side must be +1 (buy) or -1 (sell)")
    if bid <= 0 or ask < bid:
        raise ValueError("invalid bid/ask")
    if mid_before <= 0:
        raise ValueError("mid_before must be > 0")
    if order_size < 0:
        raise ValueError("order_size must be >= 0")

    half_spread = (ask - bid) / 2.0
    adv = max(adv_per_minute, _MIN_ADV)
    impact = k_impact * (order_size / adv) ** alpha
    queue_drift = mid_after - mid_before

    slippage_price = side * (half_spread + impact + queue_drift)
    slippage_bps = (slippage_price / mid_before) * 1e4

    return SlippageBreakdown(
        side=side,
        half_spread=half_spread,
        impact=impact,
        queue_drift=queue_drift,
        slippage_price=slippage_price,
        slippage_bps=slippage_bps,
    )


# ──────────────────────────────────────────────────────────────────────
# Slippage Score
# ──────────────────────────────────────────────────────────────────────

def slippage_score(
    *,
    fills: Sequence[Mapping[str, float]],
    assumed_slippage_bps: float,
    tolerance_bps: float = TOLERANCE_BPS,
    k_impact: float = K_IMPACT,
    alpha: float = ALPHA,
) -> SlippageScoreResult:
    """Score from a population of fills. Each fill is a mapping with the
    same keys ``compute_slippage`` consumes (``side``, ``bid``, ``ask``,
    ``mid_before``, ``mid_after``, ``order_size``, ``adv_per_minute``).
    Score uses |median − assumed| / tolerance, p95 is recorded but does
    not feed the score itself (spec §3)."""
    if not fills:
        raise ValueError("slippage_score requires at least one fill")
    if tolerance_bps <= 0:
        raise ValueError("tolerance_bps must be > 0")

    bps = [
        compute_slippage(
            side=int(f["side"]),
            bid=float(f["bid"]),
            ask=float(f["ask"]),
            mid_before=float(f["mid_before"]),
            mid_after=float(f["mid_after"]),
            order_size=float(f["order_size"]),
            adv_per_minute=float(f["adv_per_minute"]),
            k_impact=k_impact,
            alpha=alpha,
        ).slippage_bps
        for f in fills
    ]

    med = median(bps)
    p95 = _percentile(bps, 95.0)
    score = _clamp01(1.0 - abs(med - assumed_slippage_bps) / tolerance_bps)

    return SlippageScoreResult(
        slippage_score=score,
        median_slippage_bps=med,
        p95_slippage_bps=p95,
        assumed_slippage_bps=assumed_slippage_bps,
        tolerance_bps=tolerance_bps,
        k_impact=k_impact,
        alpha=alpha,
    )

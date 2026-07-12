"""
P0B Phase 1 — Execution Simulator (pure functions).

Tick-walk fill engine per P0B_SPEC §4. Pure functions only — callers
supply the BI5 tick list, signal time, side, order size, and the venue
profile. We never touch Mongo, the network, or the filesystem.

Public surface
──────────────
    pick_decision_tick(ticks, t_signal) → Optional[Tick]
    pick_fill_tick(ticks, t_signal, delta_latency_ms,
                   *, gap_max_ms=GAP_MAX_MS) → Optional[Tick]
    sample_latency_ms(profile, *, rng=None) → float
    simulate_fill(*, ticks, t_signal, side, order_size,
                  adv_per_minute, profile,
                  assumed_cost_bps=None, rng=None) → FillResult
    simulate_fills(signals, *, ticks, profile,
                   adv_per_minute, rng=None) → ExecutionReport
    VENUE_PROFILES, get_profile(name)

BID/BI5 firewall
────────────────
This module is BI5-side. It MUST NOT be imported by any of:
    discovery, mutation, validation, pass_probability,
    challenge_matching, portfolio_selection, phase30_*.

TODO(P1 — market_universe):
    VENUE_PROFILES is a local seed table. Defaults are persisted via the
    existing `api/admin_execution_realism.py` upsert path in Phase 2;
    callers should resolve from Mongo at that point.

TODO(P0B Phase 2):
    * Wire defaults into ``api/admin_execution_realism.py`` upserts.
    * Loop ``simulate_fill`` from the orchestrator
      (`engines/bi5_certification.py`).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import List, Mapping, Optional, Sequence

from engines.slippage_model import (
    K_IMPACT, ALPHA, compute_slippage, SlippageBreakdown,
)


EVALUATOR_VERSION = "execution_simulator@P0B-v1"

# Default §4 constants.
GAP_MAX_MS = 500
_JITTER_CLIP_MS = 2000.0


# ──────────────────────────────────────────────────────────────────────
# Venue profiles (P0B seed). TODO(P1): migrate to market_universe /
# existing admin_execution_realism collection.
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VenueProfile:
    name: str
    base_latency_ms: float
    jitter_ms: float           # clip half-width for the LogNormal sample


VENUE_PROFILES: Mapping[str, VenueProfile] = {
    "retail":    VenueProfile("retail",    80.0, 50.0),
    "ECN":       VenueProfile("ECN",       15.0, 10.0),
    "prop_firm": VenueProfile("prop_firm", 25.0, 15.0),
}


def get_profile(name: str) -> VenueProfile:
    try:
        return VENUE_PROFILES[name]
    except KeyError as e:
        raise ValueError(f"unknown venue profile: {name}") from e


# ──────────────────────────────────────────────────────────────────────
# Result containers
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FillResult:
    filled: bool
    reason: str                # "FILLED" | "REJECTED_NO_LIQUIDITY" | "REJECTED_NO_DECISION_TICK"
    t_signal: datetime
    decision_ts: Optional[datetime]
    fill_ts: Optional[datetime]
    latency_ms: float
    time_to_fill_ms: float
    fill_price: float
    slippage_bps: float
    slippage: Optional[SlippageBreakdown]
    side: int
    evaluator_version: str = EVALUATOR_VERSION


@dataclass(frozen=True)
class ExecutionReport:
    fills: List[FillResult]
    fill_rate: float
    median_ms_to_fill: float
    rejections: int
    no_quote_events: int
    fill_time_score: float
    rejection_score: float
    gap_score: float
    execution_score: float
    venue_class: str
    evaluator_version: str = EVALUATOR_VERSION


# ──────────────────────────────────────────────────────────────────────
# Helpers (pure)
# ──────────────────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def pick_decision_tick(ticks: Sequence[object], t_signal: datetime):
    """First tick with ``ts_utc >= t_signal``. None if no such tick."""
    t_signal = _to_utc(t_signal)
    for t in ticks:
        if t.ts_utc >= t_signal:
            return t
    return None


def pick_fill_tick(
    ticks: Sequence[object],
    t_signal: datetime,
    delta_latency_ms: float,
    *,
    gap_max_ms: int = GAP_MAX_MS,
):
    """First tick with ``ts_utc >= t_signal + Δlatency``.

    Per §4(5): if the candidate's gap to the decision moment exceeds
    ``gap_max_ms``, we treat it as no liquidity (returns ``None``).
    """
    t_signal = _to_utc(t_signal)
    target = t_signal + timedelta(milliseconds=delta_latency_ms)
    for t in ticks:
        if t.ts_utc >= target:
            gap_ms = (t.ts_utc - target).total_seconds() * 1000.0
            if gap_ms > gap_max_ms:
                return None
            return t
    return None


def sample_latency_ms(
    profile: VenueProfile,
    *,
    rng: Optional[random.Random] = None,
) -> float:
    """LogNormal-clipped latency draw.

    The spec gives ``Δlatency = base + jitter, jitter ~ LogNormal(μ,σ)``
    clipped to [0, 2000 ms]. We pick μ,σ so the median jitter equals the
    profile's ``jitter_ms`` configured value — a deterministic enough
    interpretation that keeps unit tests cheap.
    """
    rng = rng or random.Random()
    if profile.jitter_ms <= 0:
        return float(profile.base_latency_ms)
    mu = math.log(profile.jitter_ms)
    sigma = 0.5
    jitter = math.exp(rng.normalvariate(mu, sigma))
    jitter = min(max(jitter, 0.0), _JITTER_CLIP_MS)
    return float(profile.base_latency_ms + jitter)


# ──────────────────────────────────────────────────────────────────────
# Single-fill simulation
# ──────────────────────────────────────────────────────────────────────

def simulate_fill(
    *,
    ticks: Sequence[object],
    t_signal: datetime,
    side: int,
    order_size: float,
    adv_per_minute: float,
    profile: VenueProfile,
    rng: Optional[random.Random] = None,
    k_impact: float = K_IMPACT,
    alpha: float = ALPHA,
) -> FillResult:
    if side not in (1, -1):
        raise ValueError("side must be +1 (buy) or -1 (sell)")
    if not ticks:
        return FillResult(
            filled=False, reason="REJECTED_NO_DECISION_TICK",
            t_signal=_to_utc(t_signal), decision_ts=None, fill_ts=None,
            latency_ms=0.0, time_to_fill_ms=0.0,
            fill_price=0.0, slippage_bps=0.0, slippage=None, side=side,
        )

    t_signal = _to_utc(t_signal)

    decision = pick_decision_tick(ticks, t_signal)
    if decision is None:
        return FillResult(
            filled=False, reason="REJECTED_NO_DECISION_TICK",
            t_signal=t_signal, decision_ts=None, fill_ts=None,
            latency_ms=0.0, time_to_fill_ms=0.0,
            fill_price=0.0, slippage_bps=0.0, slippage=None, side=side,
        )

    latency_ms = sample_latency_ms(profile, rng=rng)
    fill_tick = pick_fill_tick(ticks, t_signal, latency_ms)
    if fill_tick is None:
        return FillResult(
            filled=False, reason="REJECTED_NO_LIQUIDITY",
            t_signal=t_signal,
            decision_ts=decision.ts_utc, fill_ts=None,
            latency_ms=latency_ms, time_to_fill_ms=0.0,
            fill_price=0.0, slippage_bps=0.0, slippage=None, side=side,
        )

    mid_before = (decision.bid + decision.ask) * 0.5
    mid_after = (fill_tick.bid + fill_tick.ask) * 0.5

    slip = compute_slippage(
        side=side, bid=fill_tick.bid, ask=fill_tick.ask,
        mid_before=mid_before, mid_after=mid_after,
        order_size=order_size, adv_per_minute=adv_per_minute,
        k_impact=k_impact, alpha=alpha,
    )

    # Base fill price: ask on buys, bid on sells. Add the signed
    # slippage in price units.
    base = fill_tick.ask if side == 1 else fill_tick.bid
    fill_price = base + slip.slippage_price

    ttf_ms = (fill_tick.ts_utc - t_signal).total_seconds() * 1000.0

    return FillResult(
        filled=True, reason="FILLED",
        t_signal=t_signal,
        decision_ts=decision.ts_utc, fill_ts=fill_tick.ts_utc,
        latency_ms=latency_ms, time_to_fill_ms=ttf_ms,
        fill_price=fill_price, slippage_bps=slip.slippage_bps,
        slippage=slip, side=side,
    )


# ──────────────────────────────────────────────────────────────────────
# Population-level scoring
# ──────────────────────────────────────────────────────────────────────

def simulate_fills(
    signals: Sequence[Mapping[str, object]],
    *,
    ticks: Sequence[object],
    profile: VenueProfile,
    adv_per_minute: float,
    rng: Optional[random.Random] = None,
    k_impact: float = K_IMPACT,
    alpha: float = ALPHA,
) -> ExecutionReport:
    """Run ``simulate_fill`` over many signals and score per §4.

    ``Execution_Score = 0.4·fill_rate + 0.3·time_to_fill_score
                        + 0.2·rejection_score + 0.1·gap_score``
    """
    if not signals:
        raise ValueError("simulate_fills requires at least one signal")

    results: List[FillResult] = []
    for s in signals:
        results.append(simulate_fill(
            ticks=ticks,
            t_signal=s["t_signal"],          # type: ignore[index]
            side=int(s["side"]),              # type: ignore[index]
            order_size=float(s.get("order_size", 1.0)),  # type: ignore[union-attr]
            adv_per_minute=adv_per_minute,
            profile=profile,
            rng=rng,
            k_impact=k_impact,
            alpha=alpha,
        ))

    n = len(results)
    fills = [r for r in results if r.filled]
    rejections = sum(1 for r in results if r.reason == "REJECTED_NO_LIQUIDITY")
    no_quote = sum(1 for r in results if r.reason == "REJECTED_NO_DECISION_TICK")

    fill_rate = len(fills) / n
    ttf_values = [r.time_to_fill_ms for r in fills]
    median_ttf = median(ttf_values) if ttf_values else 0.0

    # Time-to-fill sub-score: <100 ms → 1.0, ≥2000 ms → 0.0, log-scaled.
    if not ttf_values:
        time_to_fill_score = 0.0
    elif median_ttf <= 100:
        time_to_fill_score = 1.0
    elif median_ttf >= 2000:
        time_to_fill_score = 0.0
    else:
        time_to_fill_score = 1.0 - (math.log(median_ttf / 100.0)
                                    / math.log(2000.0 / 100.0))

    rejection_score = 1.0 - (rejections / n)
    # Gap score: ratio of unfilled-due-to-no-quote vs population.
    gap_score = 1.0 - (no_quote / n)

    execution_score = (
        0.4 * fill_rate +
        0.3 * _clamp01(time_to_fill_score) +
        0.2 * _clamp01(rejection_score) +
        0.1 * _clamp01(gap_score)
    )

    return ExecutionReport(
        fills=results,
        fill_rate=_clamp01(fill_rate),
        median_ms_to_fill=median_ttf,
        rejections=rejections,
        no_quote_events=no_quote,
        fill_time_score=_clamp01(time_to_fill_score),
        rejection_score=_clamp01(rejection_score),
        gap_score=_clamp01(gap_score),
        execution_score=_clamp01(execution_score),
        venue_class=profile.name,
    )

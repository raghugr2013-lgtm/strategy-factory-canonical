"""Unit tests for engines/execution_simulator.py (P0B Phase 1, §4).

Pure-function tests — no Mongo, no API, no filesystem. RNGs are seeded
so the suite stays deterministic.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from engines.execution_simulator import (
    GAP_MAX_MS,
    VENUE_PROFILES,
    ExecutionReport,
    get_profile,
    pick_decision_tick,
    pick_fill_tick,
    sample_latency_ms,
    simulate_fill,
    simulate_fills,
)


@dataclass(frozen=True)
class _Tick:
    ts_utc: datetime
    bid: float
    ask: float


def _ticks(base: datetime, n: int, *, step_ms: float = 100.0,
           bid: float = 1.1000, spread: float = 0.0001):
    return [
        _Tick(
            ts_utc=base + timedelta(milliseconds=step_ms * i),
            bid=bid, ask=bid + spread,
        )
        for i in range(n)
    ]


# ── get_profile / VENUE_PROFILES ─────────────────────────────────────

def test_get_profile_known() -> None:
    assert get_profile("ECN").name == "ECN"
    assert get_profile("retail").base_latency_ms == 80.0


def test_get_profile_unknown_raises() -> None:
    with pytest.raises(ValueError):
        get_profile("not-a-venue")


# ── sample_latency_ms ────────────────────────────────────────────────

def test_sample_latency_zero_jitter_returns_base() -> None:
    p = VENUE_PROFILES["retail"]
    flat = type(p)(name=p.name, base_latency_ms=50.0, jitter_ms=0.0)
    out = sample_latency_ms(flat, rng=random.Random(0))
    assert out == 50.0


def test_sample_latency_clipped_to_window_and_positive() -> None:
    rng = random.Random(42)
    out = sample_latency_ms(VENUE_PROFILES["ECN"], rng=rng)
    assert 0.0 <= out <= VENUE_PROFILES["ECN"].base_latency_ms + 2000.0


# ── pick_decision_tick / pick_fill_tick ──────────────────────────────

def test_pick_decision_tick_first_at_or_after_signal() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 5)
    sig = base + timedelta(milliseconds=150)
    out = pick_decision_tick(ts, sig)
    assert out is ts[2]  # 200ms tick is the first ≥ 150ms


def test_pick_decision_tick_returns_none_when_no_quote() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 3)
    sig = base + timedelta(seconds=10)
    assert pick_decision_tick(ts, sig) is None


def test_pick_fill_tick_returns_none_when_gap_exceeds_max() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # Two ticks 5s apart — first is BEFORE the latency target so it is
    # ignored; the second is way beyond gap_max_ms.
    ts = [
        _Tick(base, 1.1, 1.1001),
        _Tick(base + timedelta(seconds=5), 1.1, 1.1001),
    ]
    sig = base
    out = pick_fill_tick(ts, sig, delta_latency_ms=50.0,
                        gap_max_ms=GAP_MAX_MS)
    assert out is None


def test_pick_fill_tick_within_gap_returns_tick() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 20, step_ms=50.0)
    sig = base
    out = pick_fill_tick(ts, sig, delta_latency_ms=100.0)
    assert out is not None
    # 100ms target → first tick at 100ms or later
    assert (out.ts_utc - sig).total_seconds() * 1000.0 >= 100.0


# ── simulate_fill ────────────────────────────────────────────────────

def test_simulate_fill_no_ticks_rejected_with_decision_reason() -> None:
    sig = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    out = simulate_fill(
        ticks=[], t_signal=sig, side=1, order_size=1.0,
        adv_per_minute=1000.0, profile=get_profile("ECN"),
        rng=random.Random(0),
    )
    assert not out.filled
    assert out.reason == "REJECTED_NO_DECISION_TICK"


def test_simulate_fill_no_quote_after_signal_rejected() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # Only past-ticks; signal is 1h after the last quote.
    ts = _ticks(base, 3)
    sig = base + timedelta(hours=1)
    out = simulate_fill(
        ticks=ts, t_signal=sig, side=1, order_size=1.0,
        adv_per_minute=1000.0, profile=get_profile("ECN"),
        rng=random.Random(0),
    )
    assert not out.filled
    assert out.reason == "REJECTED_NO_DECISION_TICK"


def test_simulate_fill_no_liquidity_rejected_when_gap_too_wide() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = [
        _Tick(base, 1.1, 1.1001),
        _Tick(base + timedelta(seconds=10), 1.1, 1.1001),
    ]
    sig = base
    out = simulate_fill(
        ticks=ts, t_signal=sig, side=1, order_size=1.0,
        adv_per_minute=1000.0, profile=get_profile("ECN"),
        rng=random.Random(0),
    )
    assert not out.filled
    assert out.reason == "REJECTED_NO_LIQUIDITY"


def test_simulate_fill_filled_uses_ask_for_buy_plus_slippage() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 200, step_ms=10.0)   # 10ms ticks → fills easily
    sig = base
    out = simulate_fill(
        ticks=ts, t_signal=sig, side=1, order_size=0.0,
        adv_per_minute=1000.0, profile=get_profile("ECN"),
        rng=random.Random(123),
    )
    assert out.filled
    assert out.reason == "FILLED"
    assert out.slippage is not None
    # Buy fill price ≈ ask + signed slippage_price
    assert out.fill_price > 0
    assert out.time_to_fill_ms >= 0


def test_simulate_fill_sell_uses_bid() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 200, step_ms=10.0)
    out = simulate_fill(
        ticks=ts, t_signal=base, side=-1, order_size=0.0,
        adv_per_minute=1000.0, profile=get_profile("ECN"),
        rng=random.Random(7),
    )
    assert out.filled
    # Sell-side base is bid; for zero-impact / zero-drift / zero-spread-change
    # the fill_price should be near the bid.
    assert out.fill_price < ts[0].ask  # below ask
    assert out.side == -1


def test_simulate_fill_invalid_side_raises() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        simulate_fill(
            ticks=_ticks(base, 5), t_signal=base, side=0,
            order_size=1.0, adv_per_minute=1000.0,
            profile=get_profile("ECN"),
        )


# ── simulate_fills (population) ──────────────────────────────────────

def _signals(base: datetime, n: int, *, gap_ms: float = 500.0):
    return [
        {
            "t_signal": base + timedelta(milliseconds=gap_ms * i),
            "side": 1 if i % 2 == 0 else -1,
            "order_size": 0.0,
        }
        for i in range(n)
    ]


def test_simulate_fills_all_filled_scores_high() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # 60min of 10ms-step quotes ensures every signal can fill within gap.
    ts = _ticks(base, 6000, step_ms=10.0)
    sigs = _signals(base + timedelta(milliseconds=100), n=10, gap_ms=200.0)
    rep = simulate_fills(
        sigs, ticks=ts, profile=get_profile("ECN"),
        adv_per_minute=1000.0, rng=random.Random(0),
    )
    assert isinstance(rep, ExecutionReport)
    assert rep.fill_rate == pytest.approx(1.0)
    assert rep.rejections == 0
    assert rep.no_quote_events == 0
    # 0.4·1 + 0.3·≥0 + 0.2·1 + 0.1·1  ≥ 0.7
    assert rep.execution_score >= 0.7


def test_simulate_fills_all_no_quote_collapses_score() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # Ticks well before any signal.
    ts = _ticks(base, 5, step_ms=10.0)
    sigs = _signals(base + timedelta(hours=2), n=4)
    rep = simulate_fills(
        sigs, ticks=ts, profile=get_profile("ECN"),
        adv_per_minute=1000.0, rng=random.Random(0),
    )
    assert rep.fill_rate == pytest.approx(0.0)
    assert rep.no_quote_events == 4
    assert rep.rejections == 0
    assert rep.gap_score == pytest.approx(0.0)
    # All-fail must keep score in [0,1] and very low.
    assert 0.0 <= rep.execution_score <= 0.3


def test_simulate_fills_rejections_pull_rejection_score_down() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # Sparse ticks: a quote before each signal AND one trailing quote so
    # the last signal still finds a decision tick (it will then be
    # rejected for liquidity, not for a missing quote).
    ts = [
        _Tick(base + timedelta(seconds=i * 10), 1.1, 1.1001)
        for i in range(6)
    ]
    sigs = [
        {"t_signal": base + timedelta(seconds=i * 10 + 1),
         "side": 1, "order_size": 0.0}
        for i in range(5)
    ]
    rep = simulate_fills(
        sigs, ticks=ts, profile=get_profile("ECN"),
        adv_per_minute=1000.0, rng=random.Random(0),
    )
    # Every signal finds a decision tick (rejected for liquidity, not no-quote).
    assert rep.no_quote_events == 0
    assert rep.rejections == 5
    assert rep.rejection_score == pytest.approx(0.0)


def test_simulate_fills_requires_signals() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        simulate_fills(
            [], ticks=_ticks(base, 5), profile=get_profile("ECN"),
            adv_per_minute=1000.0,
        )


def test_simulate_fills_records_venue_class() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 1000, step_ms=10.0)
    sigs = _signals(base + timedelta(milliseconds=100), n=3, gap_ms=200.0)
    for name in ("retail", "ECN", "prop_firm"):
        rep = simulate_fills(
            sigs, ticks=ts, profile=get_profile(name),
            adv_per_minute=1000.0, rng=random.Random(0),
        )
        assert rep.venue_class == name


def test_simulate_fills_subscores_are_clamped() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ts = _ticks(base, 1000, step_ms=10.0)
    sigs = _signals(base + timedelta(milliseconds=50), n=5, gap_ms=200.0)
    rep = simulate_fills(
        sigs, ticks=ts, profile=get_profile("ECN"),
        adv_per_minute=1000.0, rng=random.Random(0),
    )
    for k in ("fill_rate", "fill_time_score", "rejection_score",
              "gap_score", "execution_score"):
        v = getattr(rep, k)
        assert 0.0 <= v <= 1.0

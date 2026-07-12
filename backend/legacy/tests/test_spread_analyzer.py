"""Unit tests for engines/spread_analyzer.py (P0B Phase 1, §2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from engines.spread_analyzer import (
    DEFAULT_TOLERANCE_BPS,
    compute_spread_score,
    get_tolerance_bps,
    rollup_spread_minutes,
    spread_score_from_fills,
)


@dataclass(frozen=True)
class _Tick:
    ts_utc: datetime
    bid: float
    ask: float


def test_get_tolerance_bps_known_and_fallback() -> None:
    assert get_tolerance_bps("EURUSD") == DEFAULT_TOLERANCE_BPS["EURUSD"]
    assert get_tolerance_bps("ZZZZZZ") == 2.0


# ── rollup_spread_minutes ────────────────────────────────────────────

def test_rollup_emits_one_bar_per_minute_with_ohlc() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = [
        _Tick(base + timedelta(seconds=0),  1.1000, 1.1001),
        _Tick(base + timedelta(seconds=15), 1.1000, 1.1003),  # widen
        _Tick(base + timedelta(seconds=30), 1.1000, 1.1002),
        _Tick(base + timedelta(seconds=59), 1.1000, 1.1001),
        _Tick(base + timedelta(seconds=60), 1.1000, 1.1004),  # next min
    ]
    bars = rollup_spread_minutes(ticks, symbol="EURUSD")
    assert len(bars) == 2
    b0, b1 = bars
    assert b0.tick_count == 4
    assert b0.spread_open == pytest.approx(0.0001)
    assert b0.spread_high == pytest.approx(0.0003)
    assert b0.spread_low == pytest.approx(0.0001)
    assert b0.spread_close == pytest.approx(0.0001)
    assert b0.spread_mean == pytest.approx((0.0001 + 0.0003 + 0.0002 + 0.0001) / 4)
    assert b1.tick_count == 1
    assert b1.spread_open == pytest.approx(0.0004)


def test_rollup_skips_broken_ticks() -> None:
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = [
        _Tick(base, 1.1000, 1.1001),
        _Tick(base + timedelta(seconds=10), 0.0, 1.1001),     # broken bid
        _Tick(base + timedelta(seconds=20), 1.1003, 1.1002),  # inverted
    ]
    bars = rollup_spread_minutes(ticks, symbol="EURUSD")
    assert len(bars) == 1
    assert bars[0].tick_count == 1


def test_rollup_empty_input_returns_empty() -> None:
    assert rollup_spread_minutes([], symbol="EURUSD") == []


# ── compute_spread_score ─────────────────────────────────────────────

def test_compute_spread_score_perfect_match_scores_one() -> None:
    # 1.0 bps realised vs 1.0 bps assumed, tolerance 1.0 → score 1.0.
    out = compute_spread_score(
        fill_spread=1.10005 * 1.0e-4,  # 1 bp wide
        mid=1.10005,
        assumed_cost_bps=1.0,
        tolerance_bps=1.0,
    )
    assert out.spread_score == pytest.approx(1.0, abs=1e-6)
    assert out.realised_cost_bps == pytest.approx(1.0, abs=1e-6)


def test_compute_spread_score_outside_tolerance_clamps_to_zero() -> None:
    out = compute_spread_score(
        fill_spread=1.10005 * 5e-4,  # 5 bps realised
        mid=1.10005,
        assumed_cost_bps=1.0,
        tolerance_bps=1.0,
    )
    assert out.spread_score == pytest.approx(0.0)


def test_compute_spread_score_defaults_when_assumed_missing() -> None:
    out = compute_spread_score(
        fill_spread=1.10005 * 0.8e-4,
        mid=1.10005,
        assumed_cost_bps=None,
        tolerance_bps=1.0,
        symbol="EURUSD",
    )
    assert "ASSUMED_SPREAD_DEFAULTED" in out.flags
    assert out.assumed_cost_bps == pytest.approx(0.8)


def test_compute_spread_score_invalid_mid_returns_flagged_zero() -> None:
    out = compute_spread_score(
        fill_spread=0.0001, mid=0.0,
        assumed_cost_bps=1.0, tolerance_bps=1.0,
    )
    assert out.spread_score == 0.0
    assert "INVALID_MID" in out.flags


def test_compute_spread_score_rejects_non_positive_tolerance() -> None:
    with pytest.raises(ValueError):
        compute_spread_score(
            fill_spread=0.0001, mid=1.1,
            assumed_cost_bps=1.0, tolerance_bps=0.0,
        )


# ── spread_score_from_fills ──────────────────────────────────────────

def test_spread_score_from_fills_uses_median_bps() -> None:
    fills = [
        {"fill_spread": 1.1 * 1e-4, "mid": 1.1},   # 1 bp
        {"fill_spread": 1.1 * 1.2e-4, "mid": 1.1}, # 1.2 bps
        {"fill_spread": 1.1 * 0.8e-4, "mid": 1.1}, # 0.8 bps
    ]
    out = spread_score_from_fills(
        fills, symbol="EURUSD", assumed_cost_bps=1.0, tolerance_bps=1.0,
    )
    assert out.realised_cost_bps == pytest.approx(1.0, abs=1e-3)
    assert out.spread_score == pytest.approx(1.0, abs=1e-3)


def test_spread_score_from_fills_requires_at_least_one_fill() -> None:
    with pytest.raises(ValueError):
        spread_score_from_fills(
            [], symbol="EURUSD", assumed_cost_bps=1.0,
        )


def test_spread_score_from_fills_resolves_tolerance_from_symbol() -> None:
    fills = [{"fill_spread": 1.1 * 1e-4, "mid": 1.1}]
    out = spread_score_from_fills(
        fills, symbol="USDJPY", assumed_cost_bps=1.0,
    )
    assert out.tolerance_bps == DEFAULT_TOLERANCE_BPS["USDJPY"]

"""Unit tests for engines/slippage_model.py (P0B Phase 1, §3).

Pure-function tests — no Mongo, no API, no filesystem.
"""
from __future__ import annotations

import math

import pytest

from engines.slippage_model import (
    ALPHA,
    K_IMPACT,
    TOLERANCE_BPS,
    compute_slippage,
    rolling_adv_per_minute,
    slippage_score,
)


# ── rolling_adv_per_minute ───────────────────────────────────────────

def test_rolling_adv_expanding_window_before_full() -> None:
    out = rolling_adv_per_minute([10.0, 20.0, 30.0], window=60)
    # Expanding mean: 10, 15, 20
    assert out == pytest.approx([10.0, 15.0, 20.0])


def test_rolling_adv_trailing_window_after_full() -> None:
    # window=3 keeps tail of last 3 values once enough data exists.
    out = rolling_adv_per_minute([1.0, 2.0, 3.0, 4.0, 5.0], window=3)
    # i<3 expanding: [1, 1.5, 2]; from i=3 trailing-3: (2+3+4)/3=3, (3+4+5)/3=4
    assert out == pytest.approx([1.0, 1.5, 2.0, 3.0, 4.0])


def test_rolling_adv_empty_returns_empty() -> None:
    assert rolling_adv_per_minute([], window=60) == []


def test_rolling_adv_rejects_non_positive_window() -> None:
    with pytest.raises(ValueError):
        rolling_adv_per_minute([1.0, 2.0], window=0)


# ── compute_slippage ─────────────────────────────────────────────────

def test_compute_slippage_buy_basic_decomposition() -> None:
    out = compute_slippage(
        side=1,
        bid=1.1000, ask=1.1002,
        mid_before=1.1001, mid_after=1.1001,
        order_size=10.0, adv_per_minute=1000.0,
    )
    expected_half = (1.1002 - 1.1000) / 2.0           # 0.0001
    expected_impact = K_IMPACT * (10.0 / 1000.0) ** ALPHA  # 0.5 * sqrt(0.01)
    assert out.half_spread == pytest.approx(expected_half)
    assert out.impact == pytest.approx(expected_impact)
    assert out.queue_drift == pytest.approx(0.0)
    assert out.slippage_price == pytest.approx(expected_half + expected_impact)
    assert out.slippage_bps == pytest.approx(
        (expected_half + expected_impact) / 1.1001 * 1e4
    )


def test_compute_slippage_sell_is_signed_negative() -> None:
    out = compute_slippage(
        side=-1,
        bid=1.1000, ask=1.1002,
        mid_before=1.1001, mid_after=1.1001,
        order_size=0.0, adv_per_minute=1000.0,
    )
    # order_size=0 → impact=0; queue_drift=0; only half_spread remains.
    assert out.slippage_price == pytest.approx(-0.0001)
    assert out.slippage_bps < 0


def test_compute_slippage_queue_drift_uses_mid_after() -> None:
    out = compute_slippage(
        side=1,
        bid=1.1000, ask=1.1000,                       # zero spread
        mid_before=1.1000, mid_after=1.1005,          # +5 pips drift
        order_size=0.0, adv_per_minute=1000.0,
    )
    assert out.half_spread == pytest.approx(0.0)
    assert out.impact == pytest.approx(0.0)
    assert out.queue_drift == pytest.approx(0.0005)
    assert out.slippage_price == pytest.approx(0.0005)


def test_compute_slippage_impact_grows_with_size_sqrt() -> None:
    small = compute_slippage(
        side=1, bid=1.1, ask=1.1, mid_before=1.1, mid_after=1.1,
        order_size=1.0, adv_per_minute=100.0,
    )
    big = compute_slippage(
        side=1, bid=1.1, ask=1.1, mid_before=1.1, mid_after=1.1,
        order_size=4.0, adv_per_minute=100.0,
    )
    # α=0.5 → impact(4x) / impact(1x) == 2.0
    assert big.impact / small.impact == pytest.approx(2.0, rel=1e-6)


def test_compute_slippage_thin_adv_does_not_explode() -> None:
    # adv_per_minute=0 must be floored, not divide-by-zero.
    out = compute_slippage(
        side=1, bid=1.1, ask=1.1001, mid_before=1.10005, mid_after=1.10005,
        order_size=1.0, adv_per_minute=0.0,
    )
    assert math.isfinite(out.impact)
    assert out.impact > 0


@pytest.mark.parametrize("side", [0, 2, -2])
def test_compute_slippage_rejects_bad_side(side: int) -> None:
    with pytest.raises(ValueError):
        compute_slippage(
            side=side, bid=1.1, ask=1.1, mid_before=1.1, mid_after=1.1,
            order_size=1.0, adv_per_minute=1000.0,
        )


@pytest.mark.parametrize("bid,ask", [(0.0, 1.1), (-1.0, 1.1), (1.1, 1.0)])
def test_compute_slippage_rejects_bad_bid_ask(bid: float, ask: float) -> None:
    with pytest.raises(ValueError):
        compute_slippage(
            side=1, bid=bid, ask=ask, mid_before=1.1, mid_after=1.1,
            order_size=1.0, adv_per_minute=1000.0,
        )


def test_compute_slippage_rejects_negative_order_size() -> None:
    with pytest.raises(ValueError):
        compute_slippage(
            side=1, bid=1.1, ask=1.1, mid_before=1.1, mid_after=1.1,
            order_size=-1.0, adv_per_minute=1000.0,
        )


def test_compute_slippage_rejects_non_positive_mid_before() -> None:
    with pytest.raises(ValueError):
        compute_slippage(
            side=1, bid=1.1, ask=1.1, mid_before=0.0, mid_after=1.1,
            order_size=1.0, adv_per_minute=1000.0,
        )


# ── slippage_score ───────────────────────────────────────────────────

def _fill(side: int = 1, bid: float = 1.1, ask: float = 1.1001,
          mid_before: float = 1.10005, mid_after: float = 1.10005,
          order_size: float = 0.0, adv: float = 1000.0) -> dict:
    return {
        "side": side, "bid": bid, "ask": ask,
        "mid_before": mid_before, "mid_after": mid_after,
        "order_size": order_size, "adv_per_minute": adv,
    }


def test_slippage_score_perfect_match_scores_one() -> None:
    # zero-impact, zero-drift buy → realised slip = half_spread/mid in bps.
    # bid=1.1 ask=1.1001 mid=1.10005 → half_spread=0.00005
    # bps = 0.00005 / 1.10005 * 1e4 ≈ 0.4545 bps
    fills = [_fill(order_size=0.0)] * 5
    out = slippage_score(
        fills=fills, assumed_slippage_bps=0.4545, tolerance_bps=1.0,
    )
    assert out.slippage_score == pytest.approx(1.0, abs=1e-3)
    assert out.median_slippage_bps == pytest.approx(0.4545, abs=1e-3)


def test_slippage_score_outside_tolerance_clamps_to_zero() -> None:
    fills = [_fill(order_size=0.0)] * 3
    out = slippage_score(
        fills=fills, assumed_slippage_bps=10.0, tolerance_bps=TOLERANCE_BPS,
    )
    assert out.slippage_score == pytest.approx(0.0)


def test_slippage_score_records_p95_without_feeding_score() -> None:
    # Build fills where one outlier dominates p95 but not the median.
    fills = [_fill(order_size=0.0)] * 9 + [
        # Wide outlier: keep mid_before == mid_after so queue_drift stays 0
        # and the wider half_spread shows up cleanly in bps.
        _fill(order_size=0.0, ask=1.1010,
              mid_before=1.10055, mid_after=1.10055),
    ]
    out = slippage_score(
        fills=fills, assumed_slippage_bps=0.4545, tolerance_bps=1.0,
    )
    # Median still aligns with assumed → score stays high.
    assert out.slippage_score > 0.9
    # But p95 is dragged up by the outlier.
    assert out.p95_slippage_bps > out.median_slippage_bps


def test_slippage_score_requires_at_least_one_fill() -> None:
    with pytest.raises(ValueError):
        slippage_score(fills=[], assumed_slippage_bps=0.5)


def test_slippage_score_rejects_non_positive_tolerance() -> None:
    with pytest.raises(ValueError):
        slippage_score(
            fills=[_fill()], assumed_slippage_bps=0.5, tolerance_bps=0.0,
        )


def test_slippage_score_uses_passed_k_impact_and_alpha() -> None:
    # Doubling k_impact must move the median (and so the score).
    fills = [_fill(order_size=5.0, adv=100.0)] * 3
    out_a = slippage_score(
        fills=fills, assumed_slippage_bps=0.0, tolerance_bps=10.0,
        k_impact=0.5, alpha=0.5,
    )
    out_b = slippage_score(
        fills=fills, assumed_slippage_bps=0.0, tolerance_bps=10.0,
        k_impact=1.0, alpha=0.5,
    )
    assert out_b.median_slippage_bps > out_a.median_slippage_bps

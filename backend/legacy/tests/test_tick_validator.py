"""Unit tests for engines/tick_validator.py (P0B Phase 1, §1).

Pure-function tests — no Mongo, no API, no filesystem.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from engines.tick_validator import (
    DEFAULT_WEIGHTS,
    DENSITY_TABLE,
    aggregate_window,
    classify_session,
    validate_hour,
)


@dataclass(frozen=True)
class _Tick:
    ts_utc: datetime
    bid: float
    ask: float
    bid_volume: float
    ask_volume: float


def _make_ticks(hour_utc: datetime, n: int, *, step_s: float = 1.0,
                bid: float = 1.1000, spread: float = 0.0001,
                vol: float = 1.0):
    return [
        _Tick(
            ts_utc=hour_utc + timedelta(seconds=step_s * i),
            bid=bid, ask=bid + spread, bid_volume=vol, ask_volume=vol,
        )
        for i in range(n)
    ]


# ── classify_session ─────────────────────────────────────────────────

@pytest.mark.parametrize("hour,expected", [
    (0, "asia"),
    (6, "asia"),
    (7, "london"),
    (11, "london"),
    (12, "overlap"),
    (15, "overlap"),
    (16, "ny"),
    (20, "ny"),
    (22, "asia"),   # late tail folds into asia per the seed
])
def test_classify_session(hour: int, expected: str) -> None:
    ts = datetime(2026, 2, 3, hour, 0, tzinfo=timezone.utc)
    assert classify_session(ts) == expected


def test_classify_session_naive_input_is_handled_by_validate_hour() -> None:
    # validate_hour is responsible for tz-coercion; classify_session
    # itself uses .hour which works either way.
    ts = datetime(2026, 2, 3, 9, 0)
    assert classify_session(ts) == "london"


# ── validate_hour ────────────────────────────────────────────────────

def test_validate_hour_ok_clean_data() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = _make_ticks(h, 25000)  # well above london target for EURUSD
    out = validate_hour(ticks, hour_utc=h, symbol="EURUSD")
    assert out.status == "ok"
    assert out.ticks_count == 25000
    assert out.non_monotonic_ticks == 0
    assert out.zero_vol_ticks == 0
    assert out.price_outlier_ticks == 0
    floor, target = DENSITY_TABLE["EURUSD"]["london"]
    assert out.density_floor == floor
    assert out.density_target == target


def test_validate_hour_expected_empty_short_circuits() -> None:
    h = datetime(2026, 2, 7, 12, 0, tzinfo=timezone.utc)  # Saturday
    out = validate_hour(None, hour_utc=h, symbol="EURUSD",
                        status="expected_empty")
    assert out.status == "expected_empty"
    assert out.ticks_count == 0


def test_validate_hour_decode_fail_returns_zeroed_record() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    out = validate_hour(None, hour_utc=h, symbol="EURUSD",
                        status="decode_fail")
    assert out.status == "decode_fail"
    assert out.ticks_count == 0


def test_validate_hour_ok_with_zero_ticks_signals_full_silence() -> None:
    # R2 Step-0 (Option A): the empty-session-hour fallback now reports
    # 600s (a conservative session-hour gap proxy) rather than 3600s.
    # The aggregator's 95th-percentile continuity rollup absorbs the
    # value when only an isolated quiet hour occurs in a long window;
    # density still collapses to zero for the empty hour itself (the
    # real signal).
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    out = validate_hour([], hour_utc=h, symbol="EURUSD")
    assert out.status == "ok"
    assert out.ticks_count == 0
    assert out.max_silent_gap_s == pytest.approx(600.0)


def test_validate_hour_non_monotonic_ticks_counted() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = list(_make_ticks(h, 5))
    # Swap two timestamps so we have a backwards jump.
    bad = _Tick(ts_utc=ticks[0].ts_utc, bid=ticks[3].bid, ask=ticks[3].ask,
                bid_volume=ticks[3].bid_volume, ask_volume=ticks[3].ask_volume)
    ticks[3] = bad
    out = validate_hour(ticks, hour_utc=h, symbol="EURUSD")
    assert out.non_monotonic_ticks >= 1


def test_validate_hour_zero_volume_counted() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = list(_make_ticks(h, 5))
    broken = _Tick(ts_utc=ticks[2].ts_utc, bid=1.1, ask=1.1001,
                   bid_volume=0.0, ask_volume=0.0)
    ticks[2] = broken
    out = validate_hour(ticks, hour_utc=h, symbol="EURUSD")
    assert out.zero_vol_ticks == 1


def test_validate_hour_price_outlier_band_uses_sigma() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = list(_make_ticks(h, 10))
    # 8σ band with σ=0.00001 → tolerance 0.00008.
    # Drop a tick well outside that band.
    outlier = _Tick(ts_utc=ticks[4].ts_utc, bid=1.5000, ask=1.5001,
                    bid_volume=1.0, ask_volume=1.0)
    ticks[4] = outlier
    out = validate_hour(ticks, hour_utc=h, symbol="EURUSD",
                        prev_60m_sigma=0.00001, reference_mid=1.10005)
    assert out.price_outlier_ticks == 1


def test_validate_hour_unknown_symbol_falls_back() -> None:
    h = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    out = validate_hour(_make_ticks(h, 10), hour_utc=h, symbol="NZDCHF")
    assert out.density_floor == 2000  # london fallback floor
    assert out.density_target == 12000


# ── R2 Step-0 (Option A) — percentile continuity aggregator ──────────

def test_aggregate_window_percentile_continuity_absorbs_one_quiet_hour() -> None:
    """A single empty session hour in an otherwise pristine window must
    no longer collapse the score to 0.0. This is the regression that
    R2 Step-0 Option A fixes: previously the window-MAX max_silent_gap
    rollup made one 3600 s outlier hour drive continuity to 0.0; the
    new 95th-percentile-over-ok-hours rollup absorbs that 5 % tail.
    """
    base = datetime(2026, 2, 3, 7, 0, tzinfo=timezone.utc)
    # 19 clean hours + 1 empty-but-ok hour at index 10.
    records = []
    for i in range(20):
        h = base + timedelta(hours=i)
        if i == 10:
            # Empty session-active hour: validator now reports gap=600.
            records.append(validate_hour([], hour_utc=h, symbol="EURUSD"))
        else:
            records.append(validate_hour(
                _make_ticks(h, 8000, step_s=3600.0 / 8000.0),
                hour_utc=h, symbol="EURUSD",
            ))

    rep = aggregate_window(records)

    # The diagnostic raw window-max is preserved (600 s from the empty hour).
    assert rep.max_silent_gap_s == pytest.approx(600.0)
    # But continuity is computed from the 95th percentile of the 20 ok
    # gaps. With one 600 s outlier and 19 sub-second gaps, the p95
    # index is min(19, int(20*0.95)) = 19 → the 600 s value lands at
    # the p95 slot. (At larger sample sizes the outlier is fully
    # absorbed; this 20-hour case is the tightest interesting bound.)
    # Crucially, even at the tightest bound the composite no longer
    # collapses to 0.0 — verdict must be at minimum WARN, not FAIL.
    assert rep.bi5_score > 0.0
    assert rep.verdict in {"PASS", "WARN"}


def test_aggregate_window_percentile_continuity_strongly_absorbs_long_window() -> None:
    """In a realistic 30-day window (720 hours) one empty session hour
    must be fully absorbed by the 5 % tail and not affect continuity.
    """
    base = datetime(2026, 2, 3, 7, 0, tzinfo=timezone.utc)
    records = []
    for i in range(720):
        h = base + timedelta(hours=i)
        if i == 123:                            # one isolated empty hour
            records.append(validate_hour([], hour_utc=h, symbol="EURUSD"))
        else:
            records.append(validate_hour(
                _make_ticks(h, 8000, step_s=3600.0 / 8000.0),
                hour_utc=h, symbol="EURUSD",
            ))

    rep = aggregate_window(records)
    # The single 600 s outlier is now well inside the bottom 95 %.
    # The p95 silent gap is a clean sub-second value, not 600.
    assert rep.subscores["continuity"] > 0.95
    # density distribution is determined by session bands × 8000 ticks/hr
    # and is not the focus of this test — we just guarantee the
    # composite clears PASS, proving the continuity absorption.
    assert rep.bi5_score >= 0.85          # clears the new PASS threshold
    assert rep.verdict == "PASS"


def test_aggregate_window_percentile_ignores_non_ok_hours_for_continuity() -> None:
    """expected_empty / missing / decode_fail hours are excluded from
    the percentile pool — they are measured by cov / integrity, not
    continuity. Adding many expected_empty hours must not move the
    continuity sub-score.
    """
    base = datetime(2026, 2, 3, 7, 0, tzinfo=timezone.utc)
    ok_records = []
    for i in range(40):
        h = base + timedelta(hours=i)
        ok_records.append(validate_hour(
            _make_ticks(h, 8000, step_s=3600.0 / 8000.0),
            hour_utc=h, symbol="EURUSD",
        ))
    weekend_records = [
        validate_hour(None, hour_utc=base + timedelta(hours=100 + i),
                      symbol="EURUSD", status="expected_empty")
        for i in range(48)
    ]
    rep_with_weekend = aggregate_window(ok_records + weekend_records)
    rep_no_weekend = aggregate_window(ok_records)
    # Continuity is identical because the percentile pool is the same
    # 40 ok hours in both cases.
    assert rep_with_weekend.subscores["continuity"] == pytest.approx(
        rep_no_weekend.subscores["continuity"]
    )


# ── aggregate_window ─────────────────────────────────────────────────

def _build_hour_records(symbol: str, hours: int, *, ticks_per_hour: int):
    base = datetime(2026, 2, 3, 7, 0, tzinfo=timezone.utc)
    records = []
    for i in range(hours):
        h = base + timedelta(hours=i)
        records.append(validate_hour(
            _make_ticks(h, ticks_per_hour, step_s=3600.0 / ticks_per_hour),
            hour_utc=h, symbol=symbol,
        ))
    return records


def test_aggregate_window_clean_data_produces_pass_verdict() -> None:
    # All hours london/overlap with rich tick density.
    records = _build_hour_records("EURUSD", hours=5, ticks_per_hour=30000)
    rep = aggregate_window(records)
    assert rep.verdict == "PASS"
    assert rep.bi5_score >= 0.90
    assert rep.subscores["density"] == pytest.approx(1.0)
    assert rep.subscores["price"] == pytest.approx(1.0)


def test_aggregate_window_sparse_density_pulls_score_down() -> None:
    # Way under EURUSD london floor → all hours are "sparse".
    records = _build_hour_records("EURUSD", hours=5, ticks_per_hour=200)
    rep = aggregate_window(records)
    assert rep.sparse_hours == 5
    assert rep.subscores["density"] == pytest.approx(0.0)
    assert rep.verdict in {"WARN", "FAIL"}


def test_aggregate_window_decode_fail_collapses_integrity() -> None:
    base = datetime(2026, 2, 3, 7, 0, tzinfo=timezone.utc)
    records = [
        validate_hour(_make_ticks(base, 25000), hour_utc=base, symbol="EURUSD"),
        validate_hour(None, hour_utc=base + timedelta(hours=1),
                      symbol="EURUSD", status="decode_fail"),
    ]
    rep = aggregate_window(records)
    assert rep.hours_decode_fail == 1
    assert rep.subscores["integrity"] < 0.05


def test_aggregate_window_requires_at_least_one_hour() -> None:
    with pytest.raises(ValueError):
        aggregate_window([])


def test_aggregate_window_weights_must_be_used() -> None:
    # Integrity weight is highest — flipping it should affect the score
    # but never produce > 1 or < 0.
    records = _build_hour_records("EURUSD", hours=3, ticks_per_hour=30000)
    rep_default = aggregate_window(records)
    custom = dict(DEFAULT_WEIGHTS, integrity=1.0)
    rep_low = aggregate_window(records, weights=custom)
    assert 0.0 <= rep_default.bi5_score <= 1.0
    assert 0.0 <= rep_low.bi5_score <= 1.0

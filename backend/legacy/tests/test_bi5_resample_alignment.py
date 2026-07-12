"""Phase 27.4 — BI5 1m → strategy-TF resample alignment tests.

Verifies the resampling boundary convention introduced when BI5 became
a single-source 1m realism stream. Pure-function tests over
``engines.bi5_realism._resample_1m_to_tf`` — no Mongo, no HTTP, no
fixtures.

Boundary policy under test:
    * left-closed, left-labelled
    * H1 bar at 14:00 covers [14:00, 15:00)
    * OHLCV aggregation: open=first, high=max, low=min, close=last,
      volume=sum
    * Trailing partial bucket dropped when 1m feed ends mid-bucket
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines.bi5_realism import _resample_1m_to_tf            # noqa: E402


def _make_1m_stream(
    start: datetime, n_minutes: int, base_close: float = 1.1000,
) -> list:
    """Build a deterministic 1m stream where each bar's close is
    ``base_close + (i / 10000.0)`` and OHLC are tight bands around
    close. Volume is constant (1.0) so volume-sum tests are easy.
    """
    out = []
    for i in range(n_minutes):
        ts = start + timedelta(minutes=i)
        c = base_close + (i / 10000.0)
        out.append({
            "timestamp": ts.isoformat(),
            "open":   c - 0.0001,
            "high":   c + 0.0002,
            "low":    c - 0.0002,
            "close":  c,
            "volume": 1.0,
        })
    return out


# ── Tests ──────────────────────────────────────────────────────────


def test_h1_bucket_aligns_left_closed_left_labelled():
    """An H1 bar labelled 14:00 must aggregate 1m bars at 14:00..14:59
    and MUST NOT include the 15:00 bar."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    # 120 minutes covers two complete H1 buckets: [14:00, 15:00) and
    # [15:00, 16:00). Both labelled at their left edge.
    stream = _make_1m_stream(start, 120)
    bars, partial = _resample_1m_to_tf(stream, "H1")

    assert len(bars) == 2, f"expected 2 H1 bars, got {len(bars)}"
    assert partial == 0, "no partial buckets expected with exact alignment"

    first_label = datetime.fromisoformat(bars[0]["timestamp"])
    second_label = datetime.fromisoformat(bars[1]["timestamp"])
    assert first_label == start
    assert second_label == start + timedelta(hours=1)


def test_ohlcv_aggregation_rules():
    """open=first, high=max, low=min, close=last, volume=sum."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    stream = _make_1m_stream(start, 60, base_close=1.1000)
    bars, _ = _resample_1m_to_tf(stream, "H1")

    assert len(bars) == 1
    bar = bars[0]
    # First 1m bar's open: 1.1000 - 0.0001 = 1.0999
    assert bar["open"] == pytest.approx(1.0999, abs=1e-6)
    # Last 1m bar (i=59) close: 1.1000 + 59/10000 = 1.1059
    assert bar["close"] == pytest.approx(1.1059, abs=1e-6)
    # Highest high: last bar's high = 1.1059 + 0.0002 = 1.1061
    assert bar["high"] == pytest.approx(1.1061, abs=1e-6)
    # Lowest low: first bar's low = 1.0999 - 0.0001 = 1.0998
    assert bar["low"] == pytest.approx(1.0998, abs=1e-6)
    # Volume sum: 60 × 1.0 = 60
    assert bar["volume"] == pytest.approx(60.0, abs=1e-6)


def test_trailing_partial_bucket_is_dropped():
    """When 1m data ends mid-bucket the trailing partial H1 must be
    dropped to avoid PF distortion."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    # 90 minutes = one complete H1 bucket [14:00, 15:00) + a partial
    # [15:00, 15:30). The partial must NOT appear in the output.
    stream = _make_1m_stream(start, 90)
    bars, partial = _resample_1m_to_tf(stream, "H1")

    assert len(bars) == 1, f"expected 1 H1 bar (partial dropped), got {len(bars)}"
    assert partial == 1, "expected 1 partial bucket dropped"
    assert datetime.fromisoformat(bars[0]["timestamp"]) == start


def test_m15_resample_independent_of_h1():
    """Same 1m stream resampled to M15 produces 4× more bars than H1."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    stream = _make_1m_stream(start, 120)  # 2 hours

    h1_bars, _ = _resample_1m_to_tf(stream, "H1")
    m15_bars, _ = _resample_1m_to_tf(stream, "M15")

    assert len(h1_bars) == 2
    assert len(m15_bars) == 8
    # Both views of the same 1m base must have identical first close.
    assert h1_bars[0]["open"] == m15_bars[0]["open"]


def test_m1_passthrough_via_resample_helper():
    """Resampling 1m → M1 returns the input unchanged (no aggregation
    artefacts)."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    stream = _make_1m_stream(start, 30)
    bars, partial = _resample_1m_to_tf(stream, "M1")

    # M1 bucket size is 1 minute — every input bar yields one output
    # bar with no merging.
    assert len(bars) == len(stream)
    assert partial == 0
    assert bars[0]["close"] == pytest.approx(stream[0]["close"], abs=1e-9)
    assert bars[-1]["close"] == pytest.approx(stream[-1]["close"], abs=1e-9)


def test_empty_input_returns_empty():
    bars, partial = _resample_1m_to_tf([], "H1")
    assert bars == []
    assert partial == 0


def test_unknown_target_tf_returns_empty():
    """Defensive: an unknown TF must not raise; it returns empty."""
    start = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    stream = _make_1m_stream(start, 60)
    bars, partial = _resample_1m_to_tf(stream, "H7")  # invalid
    assert bars == []
    assert partial == 0


def test_h4_aggregates_240_one_minute_bars():
    """One H4 bucket aggregates exactly 240 1m bars."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    stream = _make_1m_stream(start, 480)  # 8 hours = two H4 buckets
    bars, partial = _resample_1m_to_tf(stream, "H4")
    assert len(bars) == 2
    assert partial == 0

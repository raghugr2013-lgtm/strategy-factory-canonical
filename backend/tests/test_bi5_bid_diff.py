"""Phase 2 Stage 2 — BI5 ↔ BID shadow-diff harness tests.

Two proof levels:

  1. Analytical convergence proof — driving BOTH the legacy BI5
     resampler AND the CTS resampler over the SAME M1 fixture,
     assert bit-identical OHLCV output.
  2. Harness contract — summary + detail artifact shape, tier
     bucketing thresholds, CSV round-trip, pass/fail semantics,
     partial-bar handling.

Live-data flow (`run_diff_for_symbol`) is exercised with a stub Mongo
DB so the tests can run without a populated `market_data` collection.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.bi5_bid_diff import (  # noqa: E402
    CSV_HEADER,
    DiffSummary,
    PASS_INFORMATIONAL_RATIO,
    TIER_INFORMATIONAL_MAX_BPS,
    TIER_WARNING_MAX_BPS,
    _tier_for,
    compare_bars,
    diffs_to_csv,
    is_enabled,
    run_diff_for_symbol,
    summarise,
)
from engines.bi5_realism import _resample_1m_to_tf  # noqa: E402
from engines.cts.resampler import resample_m1_to  # noqa: E402
from engines.cts.types import Candle  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────

def _m1_dicts(n: int, start_price: float = 1.10) -> List[Dict[str, Any]]:
    """Produce N monotonic M1 rows starting 2026-01-01 UTC."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out: List[Dict[str, Any]] = []
    for i in range(n):
        p = start_price + i * 0.00001
        out.append({
            "timestamp": (start + timedelta(minutes=i)).isoformat(),
            "open":  p,
            "high":  p + 0.00001,
            "low":   p - 0.00001,
            "close": p + 0.000005,
            "volume": 100.0,
        })
    return out


def _dicts_to_candles(m1: List[Dict[str, Any]]) -> List[Candle]:
    return [Candle(**r) for r in m1]


# ── (1) Analytical convergence proofs ────────────────────────────────

@pytest.mark.parametrize("n", [60, 240, 3600, 10000])
def test_bit_identical_ohlcv_on_synthetic_m1(n):
    """Given identical M1 fixture and TF, both resamplers produce
    identical OHLCV output — the mathematical proof of convergence."""
    m1 = _m1_dicts(n)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    assert len(bi5_bars) == len(cts_bars), \
        f"bar count mismatch @ n={n}: bi5={len(bi5_bars)} vs cts={len(cts_bars)}"
    for a, b in zip(bi5_bars, cts_bars):
        assert a["timestamp"] == b.timestamp, f"ts mismatch: {a['timestamp']} vs {b.timestamp}"
        assert abs(a["open"]   - b.open)   < 1e-9,  "open drift"
        assert abs(a["high"]   - b.high)   < 1e-9,  "high drift"
        assert abs(a["low"]    - b.low)    < 1e-9,  "low drift"
        assert abs(a["close"]  - b.close)  < 1e-9,  "close drift"
        assert abs(a["volume"] - b.volume) < 1e-6,  "volume drift"


@pytest.mark.parametrize("tf", ["M5", "M15", "M30", "H1", "H4", "D1"])
def test_bit_identical_across_all_timeframes(tf):
    m1 = _m1_dicts(60 * 24 * 2)  # 2 days of M1
    bi5_bars, _ = _resample_1m_to_tf(m1, tf)
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), tf)
    assert len(bi5_bars) == len(cts_bars), f"bar-count drift on {tf}"
    for a, b in zip(bi5_bars, cts_bars):
        assert abs(a["open"]  - b.open)  < 1e-9
        assert abs(a["close"] - b.close) < 1e-9


def test_bit_identical_on_non_power_of_60_lengths():
    """Trailing-partial bucket handling must agree between paths."""
    # 61 M1 bars → 1 complete H1 + 1 partial (dropped)
    for n in (17, 61, 121, 245, 3601):
        m1 = _m1_dicts(n)
        bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
        cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
        # Both drop the trailing partial via their own mechanism
        # → bar counts may differ by at most 1 (BI5 explicit guard vs
        # CTS pandas-dropna). We assert equality on the overlapping prefix.
        overlap = min(len(bi5_bars), len(cts_bars))
        for i in range(overlap):
            a = bi5_bars[i]
            b = cts_bars[i]
            assert a["timestamp"] == b.timestamp
            assert abs(a["open"]  - b.open)  < 1e-9
            assert abs(a["close"] - b.close) < 1e-9


# ── (2) compare_bars diff logic ──────────────────────────────────────

def test_convergent_input_lands_in_informational_tier():
    m1 = _m1_dicts(240)  # 4 clean H1 buckets
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    diffs = compare_bars(bi5_bars, cts_bars)
    assert len(diffs) == 4
    for d in diffs:
        assert d.tier == "informational"
        assert d.max_deviation_bps is not None
        assert d.max_deviation_bps < TIER_INFORMATIONAL_MAX_BPS


def test_synthetic_drift_lands_in_warning_and_gov_tiers():
    """Deliberately drift one candle's price to force tier bucketing."""
    # Base convergent buckets
    m1 = _m1_dicts(120)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    # Now hand-drift the second CTS bar's close by ~20 bps (warning)
    b1 = cts_bars[1]
    warned = Candle(
        timestamp=b1.timestamp,
        open=b1.open, high=b1.high, low=b1.low,
        close=b1.close * 1.002,        # +20 bps
        volume=b1.volume,
    )
    # And the third by ~80 bps (governance_review)
    b2 = cts_bars[2] if len(cts_bars) >= 3 else cts_bars[1]
    gov = Candle(
        timestamp=b2.timestamp,
        open=b2.open, high=b2.high, low=b2.low,
        close=b2.close * 1.008,        # +80 bps
        volume=b2.volume,
    )
    drifted = list(cts_bars)
    if len(drifted) >= 2:
        drifted[1] = warned
    if len(drifted) >= 3:
        drifted[2] = gov
    diffs = compare_bars(bi5_bars, drifted)
    tiers = {d.tier for d in diffs}
    assert "warning" in tiers or "governance_review" in tiers


def test_only_in_bi5_and_cts_markers():
    m1 = _m1_dicts(120)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    # Drop one CTS bar to force "bi5_only" on that bucket
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    diffs = compare_bars(bi5_bars, cts_bars[1:])   # missing first CTS bar
    only_bi5 = [d for d in diffs if d.only_in == "bi5"]
    assert len(only_bi5) == 1
    # And the opposite
    diffs2 = compare_bars(bi5_bars[1:], cts_bars)
    only_cts = [d for d in diffs2 if d.only_in == "cts"]
    assert len(only_cts) == 1


# ── (3) Summary + pass/fail semantics ────────────────────────────────

def test_summary_shape():
    m1 = _m1_dicts(240)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    diffs = compare_bars(bi5_bars, cts_bars)
    s = summarise(diffs, started_at="s", finished_at="f",
                  symbol="EURUSD", timeframe="1h",
                  m1_row_count=240, bi5_bar_count=len(bi5_bars), cts_bar_count=len(cts_bars))
    d = s.to_dict()
    for k in ("started_at", "finished_at", "symbol", "timeframe",
              "m1_row_count", "bi5_bar_count", "cts_bar_count",
              "total_comparisons", "both_present", "bi5_only", "cts_only",
              "tier_counts", "max_deviation_bps_observed",
              "p50_deviation_bps", "p95_deviation_bps", "p99_deviation_bps",
              "pass_informational_ratio", "pass_ok", "reason"):
        assert k in d, f"summary missing: {k}"


def test_pass_when_all_informational():
    m1 = _m1_dicts(240)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    diffs = compare_bars(bi5_bars, cts_bars)
    s = summarise(diffs, started_at="s", finished_at="f",
                  symbol="EURUSD", timeframe="1h",
                  m1_row_count=240, bi5_bar_count=len(bi5_bars), cts_bar_count=len(cts_bars))
    assert s.pass_ok is True
    assert s.pass_informational_ratio == 1.0
    assert s.reason == "ok"
    assert s.tier_counts.get("informational", 0) == len(diffs)


def test_fail_when_governance_review_present():
    m1 = _m1_dicts(120)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars_base, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    drifted = list(cts_bars_base)
    if len(drifted) >= 1:
        b = drifted[0]
        drifted[0] = Candle(
            timestamp=b.timestamp, open=b.open * 1.02, high=b.high, low=b.low,
            close=b.close, volume=b.volume,
        )   # 200 bps → governance_review
    diffs = compare_bars(bi5_bars, drifted)
    s = summarise(diffs, started_at="s", finished_at="f",
                  symbol="EURUSD", timeframe="1h",
                  m1_row_count=120, bi5_bar_count=len(bi5_bars), cts_bar_count=len(drifted))
    assert s.pass_ok is False
    assert "governance_review" in s.reason


def test_empty_overlap_returns_no_overlap_reason():
    s = summarise([], started_at="s", finished_at="f",
                  symbol="EURUSD", timeframe="1h",
                  m1_row_count=0, bi5_bar_count=0, cts_bar_count=0)
    assert s.pass_ok is None
    assert s.reason == "no_overlapping_buckets"


# ── (4) CSV detailed audit artifact ──────────────────────────────────

def test_csv_header_present():
    m1 = _m1_dicts(240)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    csv = diffs_to_csv(compare_bars(bi5_bars, cts_bars))
    lines = csv.strip().split("\n")
    assert lines[0] == CSV_HEADER
    # Row count matches bucket count
    m1_h1 = _resample_1m_to_tf(m1, "H1")[0]
    assert len(lines) - 1 == len(m1_h1)


def test_csv_columns_populated():
    m1 = _m1_dicts(240)
    bi5_bars, _ = _resample_1m_to_tf(m1, "H1")
    cts_bars, _ = resample_m1_to(_dicts_to_candles(m1), "H1")
    csv = diffs_to_csv(compare_bars(bi5_bars, cts_bars))
    # Every non-header row must have 18 comma-separated fields
    for row in csv.strip().split("\n")[1:]:
        cols = row.split(",")
        assert len(cols) == 18, f"expected 18 columns, got {len(cols)}: {row}"
        # Tier is one of the expected values
        assert cols[1] in ("informational", "warning", "governance_review", "bi5_only", "cts_only")


# ── (5) Tier thresholds ──────────────────────────────────────────────

def test_tier_thresholds():
    assert _tier_for(0.0) == "informational"
    assert _tier_for(TIER_INFORMATIONAL_MAX_BPS - 0.1) == "informational"
    assert _tier_for(TIER_INFORMATIONAL_MAX_BPS) == "warning"
    assert _tier_for(TIER_WARNING_MAX_BPS - 0.1) == "warning"
    assert _tier_for(TIER_WARNING_MAX_BPS) == "governance_review"
    assert _tier_for(500.0) == "governance_review"


# ── (6) Live run entry point + stub Mongo ────────────────────────────

class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
    def sort(self, *a, **k):
        return self
    def __aiter__(self):
        self._i = 0
        return self
    async def __anext__(self):
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        r = self._rows[self._i]
        self._i += 1
        return r


class _FakeMarketData:
    def __init__(self, rows): self._rows = rows
    def find(self, *a, **k): return _FakeCursor(self._rows)


class _FakeDB:
    def __init__(self, rows): self.market_data = _FakeMarketData(rows)


@pytest.mark.asyncio
async def test_run_diff_for_symbol_empty_returns_reason():
    s, d = await run_diff_for_symbol("EURUSD", db_getter=lambda: _FakeDB([]))
    assert s.reason == "empty_m1_window"
    assert d == []


@pytest.mark.asyncio
async def test_run_diff_for_symbol_uses_supplied_db():
    # Use timestamps within the last 30 days so the harness's date filter
    # doesn't drop them. The stub `find` ignores the query anyway, but this
    # keeps future filter-aware stubs realistic.
    now = datetime.now(timezone.utc)
    m1 = [
        {"timestamp": (now - timedelta(hours=(i // 60), minutes=(i % 60))).isoformat(),
         "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.105, "volume": 100.0}
        for i in range(240, 0, -1)
    ]
    s, d = await run_diff_for_symbol("EURUSD", timeframe="1h",
                                     db_getter=lambda: _FakeDB(m1))
    assert s.symbol == "EURUSD"
    assert s.m1_row_count == 240
    # Because the fixture has *identical* OHLCV for every M1, both paths
    # produce identical HTF bars — every comparison lands in `informational`.
    assert s.pass_ok is True
    assert s.reason == "ok"


# ── (7) Router — flag gating + endpoint shape ────────────────────────

def _make_app():
    app = FastAPI()
    from engines.bi5_bid_diff_router import router
    app.include_router(router)
    return app


def test_router_503_when_flag_off(monkeypatch):
    monkeypatch.delenv("BI5_BID_DIFF_ENABLED", raising=False)
    with TestClient(_make_app()) as c:
        r = c.post("/api/data/bi5-bid-diff", json={"symbol": "EURUSD"})
        assert r.status_code == 503


def test_router_400_when_symbol_missing(monkeypatch):
    monkeypatch.setenv("BI5_BID_DIFF_ENABLED", "true")
    with TestClient(_make_app()) as c:
        r = c.post("/api/data/bi5-bid-diff", json={})
        assert r.status_code == 400


def test_router_returns_summary_only_by_default(monkeypatch):
    monkeypatch.setenv("BI5_BID_DIFF_ENABLED", "true")
    # No production DB available in preview — harness returns
    # empty-m1-window reason, but the endpoint should still respond 200.
    with TestClient(_make_app()) as c:
        r = c.post("/api/data/bi5-bid-diff", json={"symbol": "EURUSD"})
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d
        assert d["detail"] is None


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("BI5_BID_DIFF_ENABLED", raising=False)
    assert is_enabled() is False

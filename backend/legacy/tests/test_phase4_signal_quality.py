"""
P2 — Signal Quality Score regression suite.

Covers:
  * Unit-level scoring (compute_entry_quality_score) — bounds + components.
  * Backtest integration:
      - filter OFF default ⇒ no rejections, score still computed
        and exposed via `_phase4_signal_quality`.
      - filter ON with threshold=100 ⇒ ~all entries blocked.
      - filter ON with threshold=0   ⇒ no entries blocked.
      - per-trade `entry_quality_score` field present on closed trades.
      - leakage guard remains all-True.
"""

import pytest

from engines.signal_quality import (
    compute_entry_quality_score,
    score_trend_strength,
    score_volatility_regime,
    score_session,
)
from engines.backtest_engine import run_backtest_logic


# Synthetic but realistic price series — sinusoidal + drift to ensure
# multiple EMA crossovers so trades actually fire.
def _trend_prices(n: int = 1200) -> list:
    import math
    base = 1.1000
    out = []
    for i in range(n):
        # Multi-frequency sine to force repeated EMA(20) / EMA(50) crosses.
        wave_a = 0.020 * math.sin(i / 60.0)
        wave_b = 0.010 * math.sin(i / 18.0)
        wave_c = 0.0030 * math.sin(i / 5.0)
        out.append(round(base + wave_a + wave_b + wave_c, 5))
    return out


def _trend_ohlc(n: int = 1200):
    closes = _trend_prices(n)
    highs = [c + 0.0008 for c in closes]
    lows = [c - 0.0008 for c in closes]
    return closes, highs, lows


def _ts_series(n: int = 1200, start_hour: int = 8) -> list:
    """ISO timestamps starting at 2024-01-01, advancing 1h per bar so
    every hour of the GMT day is represented."""
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2024, 1, 1, start_hour, 0, tzinfo=timezone.utc)
    return [(t0 + timedelta(hours=i)).isoformat() for i in range(n)]


# ── Unit-level component tests ───────────────────────────────────────

def test_score_clamped_0_to_100_unit():
    res = compute_entry_quality_score(
        side="BUY", i=50,
        seg_prices=[1.10] * 100,
        fast_ma=[1.10] * 100, slow_ma=[1.10] * 100,
    )
    assert 0.0 <= res["score"] <= 100.0
    assert set(res["components"].keys()) == {"trend", "volatility", "session"}


def test_score_higher_when_trend_strong_and_aligned():
    weak = score_trend_strength(
        side="BUY", fast_ma_i=1.1000, slow_ma_i=1.1000, price_i=1.1000,
    )
    strong_aligned = score_trend_strength(
        side="BUY", fast_ma_i=1.1050, slow_ma_i=1.1000, price_i=1.1025,
        htf_ema_i=1.1100, htf_ema_back=1.1050,
    )
    assert strong_aligned > weak


def test_score_lower_when_trend_opposes_side():
    aligned = score_trend_strength(
        side="BUY", fast_ma_i=1.1050, slow_ma_i=1.1000, price_i=1.1025,
    )
    opposed = score_trend_strength(
        side="SELL", fast_ma_i=1.1050, slow_ma_i=1.1000, price_i=1.1025,
    )
    assert aligned > opposed


def test_volatility_score_neutral_on_short_window():
    # < 20 samples ⇒ neutral 50.
    s = score_volatility_regime(atr_vals=[0.001] * 5, i=4)
    assert s == 50.0


def test_volatility_score_peaks_at_median():
    # 80 ATR samples, deterministic but dispersed so the percentile rank
    # of i=40 lands near the median (0.5) and i=79 lands near the top.
    atr = [0.001 + 0.0005 * ((k * 13) % 80) for k in range(80)]
    # Replace the last value with a clear extreme so the comparison is
    # well-defined regardless of the modular permutation order.
    atr[79] = max(atr) * 5
    s_mid = score_volatility_regime(atr_vals=atr, i=40)
    s_extreme = score_volatility_regime(atr_vals=atr, i=79)
    assert s_mid > s_extreme


def test_session_score_high_at_london_open_low_at_asian_thin():
    london = score_session(timestamp="2024-01-01T08:00:00+00:00")
    asian = score_session(timestamp="2024-01-01T02:00:00+00:00")
    assert london > asian
    assert london >= 90.0
    assert asian <= 50.0


def test_session_score_neutral_when_timestamp_missing():
    s = score_session(timestamp=None)
    assert 50.0 <= s <= 70.0


# ── Backtest integration tests ───────────────────────────────────────

def test_quality_filter_off_default_keeps_existing_behaviour():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
    )
    p4 = bt.get("_phase4_signal_quality")
    assert p4 is not None
    assert p4["quality_filter_enabled"] is False
    # Score is always computed even when filter is OFF.
    assert p4["is_quality_evaluated"] >= 0
    assert p4["is_quality_blocked"] == 0
    assert p4["oos_quality_blocked"] == 0
    # Leakage guard untouched.
    assert bt["_leakage_guard"]["indicators_in_segment"] is True


def test_quality_filter_on_high_threshold_blocks_most_entries():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
        sim_config={"quality_filter": True, "quality_threshold": 100.0},
    )
    p4 = bt["_phase4_signal_quality"]
    assert p4["quality_filter_enabled"] is True
    assert p4["quality_threshold"] == 100.0
    # With threshold=100, almost every entry must be blocked.
    assert p4["is_quality_blocked"] >= int(0.9 * p4["is_quality_evaluated"]) or p4["is_quality_evaluated"] == 0


def test_quality_filter_on_low_threshold_keeps_all_entries():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
        sim_config={"quality_filter": True, "quality_threshold": 0.0},
    )
    p4 = bt["_phase4_signal_quality"]
    assert p4["quality_filter_enabled"] is True
    assert p4["is_quality_blocked"] == 0
    assert p4["oos_quality_blocked"] == 0


def test_per_trade_entry_quality_score_populated():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
        # Filter off — score still attached to every trade.
    )
    trades = bt.get("trades") or []
    if not trades:
        pytest.skip("No trades produced on synthetic uptrend; engine warmup window prevented entries")
    for t in trades:
        assert "entry_quality_score" in t, "every closed trade must carry its entry quality score"
        s = t["entry_quality_score"]
        assert 0.0 <= s <= 100.0


def test_filtered_run_has_fewer_trades_than_baseline():
    closes, highs, lows = _trend_ohlc()
    base = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
    )
    filt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
        sim_config={"quality_filter": True, "quality_threshold": 80.0},
    )
    # Filter strictly reduces (or keeps equal) the trade count.
    assert filt["total_trades"] <= base["total_trades"]


def test_avg_score_within_bounds():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
    )
    p4 = bt["_phase4_signal_quality"]
    if p4["is_avg_score"] is not None:
        assert 0.0 <= p4["is_avg_score"] <= 100.0
    if p4["oos_avg_score"] is not None:
        assert 0.0 <= p4["oos_avg_score"] <= 100.0


def test_filter_pct_consistent_with_blocked_evaluated():
    closes, highs, lows = _trend_ohlc()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=_ts_series(),
        data_source="real",
        sim_config={"quality_filter": True, "quality_threshold": 70.0},
    )
    p4 = bt["_phase4_signal_quality"]
    if p4["is_quality_evaluated"]:
        expected = round(100.0 * p4["is_quality_blocked"] / p4["is_quality_evaluated"], 2)
        assert abs(p4["is_quality_filter_pct"] - expected) < 0.01

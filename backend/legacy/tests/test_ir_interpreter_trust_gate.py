"""Phase 28-B — Trust-Gate Validation.

The mathematical proof of semantic continuity between:
    legacy `_signal_<strategy_type>` function  ===  IR interpreter
                                                    (with the matching
                                                     reference IR)

If this gate passes:
    * mutation engine (IR-native) → backtest (legacy or IR) → export
      becomes the same semantic object.
    * Phase C (cBot transpiler) becomes safe to begin.

If this gate fails:
    * halt Phase B; do NOT proceed to Phase C; investigate the operator
      whose IR-output diverges from its legacy counterpart.

Tolerance gate (operator-locked):
    Signal-level: EXACT match required at every bar (the strongest
    possible parity — if signals match, downstream PF/DD/trades match
    by construction since both feed the same `_run_segment_loop`).
"""
from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines.backtest_engine import (                          # noqa: E402
    _atr, _ema, _rsi,
    _signal_breakout, _signal_mean_reversion,
    _signal_trend_following,
)
from engines.ir_interpreter import (                           # noqa: E402
    IRInterpreter, build_legacy_reference_ir,
)


# ── Synthetic deterministic price series ─────────────────────────


def _make_oscillating_series(
    n: int = 600, base: float = 1.1000, amp: float = 0.0050,
    period: int = 50, drift: float = 0.0,
):
    """Deterministic series that genuinely produces EMA crosses, RSI
    extremes and BB band touches. Returns (prices, highs, lows,
    timestamps)."""
    prices = []
    highs = []
    lows = []
    timestamps = []
    rng = random.Random(42)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        # Sin oscillation + slow drift + small noise → guarantees lots
        # of EMA cross events for the trust gate.
        base_p = base + amp * math.sin(2 * math.pi * i / period) + drift * i
        noise = (rng.random() - 0.5) * 0.0010
        c = base_p + noise
        h = c + 0.0005 + (rng.random() * 0.0003)
        lo = c - 0.0005 - (rng.random() * 0.0003)
        prices.append(c)
        highs.append(h)
        lows.append(lo)
        timestamps.append(start + timedelta(hours=i))
    return prices, highs, lows, timestamps


# ── Signal-sequence comparators ──────────────────────────────────


def _signal_series_legacy(strategy_type, prices, highs, lows,
                          fast_period=20, slow_period=50,
                          rsi_cfg=None, bb_cfg=None):
    fast_ma = _ema(prices, fast_period)
    slow_ma = _ema(prices, slow_period)
    rsi_vals = _rsi(prices, (rsi_cfg or {}).get("period", 14)) if rsi_cfg else [None] * len(prices)
    if bb_cfg:
        period = bb_cfg.get("period", 20)
        sd = float(bb_cfg.get("std_dev", 2.0))
        bb_mid = [None] * len(prices)
        bb_upper = [None] * len(prices)
        bb_lower = [None] * len(prices)
        for i in range(period - 1, len(prices)):
            window = prices[i - period + 1 : i + 1]
            sma = sum(window) / period
            var = sum((p - sma) ** 2 for p in window) / period
            stdv = math.sqrt(var)
            bb_mid[i] = sma
            bb_upper[i] = sma + sd * stdv
            bb_lower[i] = sma - sd * stdv
    else:
        bb_upper = bb_lower = None

    signals = []
    for i in range(len(prices)):
        if i < 1:
            signals.append(None)
            continue
        if strategy_type == "trend_following":
            signals.append(_signal_trend_following(
                i, prices, fast_ma, slow_ma, rsi_vals, rsi_cfg
            ))
        elif strategy_type == "breakout":
            signals.append(_signal_breakout(
                i, prices, fast_ma, rsi_vals, rsi_cfg
            ))
        elif strategy_type == "mean_reversion":
            signals.append(_signal_mean_reversion(
                i, prices, rsi_vals, rsi_cfg, bb_upper, bb_lower
            ))
        else:
            signals.append(None)
    return signals


def _signal_series_ir(ir, prices, highs, lows, timestamps,
                      timeframe="H1"):
    interp = IRInterpreter(
        ir, prices=prices, highs=highs, lows=lows,
        timestamps=timestamps, strategy_timeframe=timeframe,
    )
    return [interp.signal_at(i) for i in range(len(prices))]


def _compare(legacy_sig, ir_sig, name):
    assert len(legacy_sig) == len(ir_sig), (
        f"{name}: length mismatch legacy={len(legacy_sig)} ir={len(ir_sig)}"
    )
    diverging = [
        (i, legacy_sig[i], ir_sig[i])
        for i in range(len(legacy_sig)) if legacy_sig[i] != ir_sig[i]
    ]
    legacy_count = sum(1 for s in legacy_sig if s is not None)
    ir_count = sum(1 for s in ir_sig if s is not None)
    if diverging:
        sample = diverging[:5]
        pytest.fail(
            f"\n{name} trust-gate FAILED:\n"
            f"  legacy signal count: {legacy_count}\n"
            f"  ir     signal count: {ir_count}\n"
            f"  divergences: {len(diverging)} bars (first 5: {sample})\n"
        )
    # Sanity: the gate only proves something if there actually were
    # signals to compare. Refuse to declare success on an all-None pair.
    assert legacy_count > 0, (
        f"{name} trust-gate WARNING: legacy produced 0 signals; "
        f"the synthetic series was too quiet to exercise the operator. "
        f"Increase amplitude or duration of the test fixture."
    )


# ── The four trust-gate validations ─────────────────────────────


class TestTrustGate:

    def test_trend_following_no_rsi_filter(self):
        prices, highs, lows, ts = _make_oscillating_series()
        legacy = _signal_series_legacy(
            "trend_following", prices, highs, lows,
            fast_period=20, slow_period=50, rsi_cfg=None,
        )
        ref_ir = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50, rsi_cfg=None,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "trend_following / no rsi")

    def test_trend_following_with_rsi_filter(self):
        prices, highs, lows, ts = _make_oscillating_series()
        rsi_cfg = {"period": 14, "buy_threshold": 50, "sell_threshold": 50}
        legacy = _signal_series_legacy(
            "trend_following", prices, highs, lows,
            fast_period=20, slow_period=50, rsi_cfg=rsi_cfg,
        )
        ref_ir = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50, rsi_cfg=rsi_cfg,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "trend_following / rsi(50)")

    def test_breakout_no_rsi(self):
        prices, highs, lows, ts = _make_oscillating_series()
        legacy = _signal_series_legacy(
            "breakout", prices, highs, lows,
            fast_period=20, slow_period=50, rsi_cfg=None,
        )
        ref_ir = build_legacy_reference_ir(
            "breakout", fast_period=20, slow_period=50, rsi_cfg=None,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "breakout / no rsi")

    def test_breakout_with_rsi_filter(self):
        prices, highs, lows, ts = _make_oscillating_series()
        rsi_cfg = {"period": 14, "buy_threshold": 55, "sell_threshold": 45}
        legacy = _signal_series_legacy(
            "breakout", prices, highs, lows,
            fast_period=20, slow_period=50, rsi_cfg=rsi_cfg,
        )
        ref_ir = build_legacy_reference_ir(
            "breakout", fast_period=20, slow_period=50, rsi_cfg=rsi_cfg,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "breakout / rsi(55,45)")

    def test_mean_reversion_rsi_only(self):
        # Stronger oscillation so RSI hits 30/70.
        prices, highs, lows, ts = _make_oscillating_series(
            n=600, amp=0.0150, period=30,
        )
        rsi_cfg = {"period": 14, "buy_threshold": 30, "sell_threshold": 70}
        legacy = _signal_series_legacy(
            "mean_reversion", prices, highs, lows,
            fast_period=20, slow_period=50,
            rsi_cfg=rsi_cfg, bb_cfg=None,
        )
        ref_ir = build_legacy_reference_ir(
            "mean_reversion", fast_period=20, slow_period=50,
            rsi_cfg=rsi_cfg, bb_cfg=None,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "mean_reversion / rsi-only")

    def test_mean_reversion_rsi_plus_bb(self):
        prices, highs, lows, ts = _make_oscillating_series(
            n=600, amp=0.0150, period=30,
        )
        rsi_cfg = {"period": 14, "buy_threshold": 30, "sell_threshold": 70}
        bb_cfg = {"period": 20, "std_dev": 2.0}
        legacy = _signal_series_legacy(
            "mean_reversion", prices, highs, lows,
            fast_period=20, slow_period=50,
            rsi_cfg=rsi_cfg, bb_cfg=bb_cfg,
        )
        ref_ir = build_legacy_reference_ir(
            "mean_reversion", fast_period=20, slow_period=50,
            rsi_cfg=rsi_cfg, bb_cfg=bb_cfg,
        )
        ir_sig = _signal_series_ir(ref_ir, prices, highs, lows, ts)
        _compare(legacy, ir_sig, "mean_reversion / rsi+bb")


class TestInterpreterIndicatorParity:
    """Confirm the interpreter's precomputed indicators are bit-
    identical to the legacy primitives — the foundation of the gate."""

    def test_ema_arrays_identical(self):
        prices, highs, lows, _ = _make_oscillating_series()
        ir = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50, rsi_cfg=None,
        )
        interp = IRInterpreter(ir, prices=prices, highs=highs, lows=lows)
        ir_fast = interp._indicator_data["ema_fast"]["series"]
        ir_slow = interp._indicator_data["ema_slow"]["series"]
        leg_fast = _ema(prices, 20)
        leg_slow = _ema(prices, 50)
        assert ir_fast == leg_fast
        assert ir_slow == leg_slow

    def test_rsi_array_identical(self):
        prices, highs, lows, _ = _make_oscillating_series()
        ir = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50,
            rsi_cfg={"period": 14, "buy_threshold": 50,
                     "sell_threshold": 50},
        )
        interp = IRInterpreter(ir, prices=prices, highs=highs, lows=lows)
        ir_rsi = interp._indicator_data["rsi"]["series"]
        leg_rsi = _rsi(prices, 14)
        assert ir_rsi == leg_rsi

    def test_atr_array_identical(self):
        prices, highs, lows, _ = _make_oscillating_series()
        ir_dict = {
            "ir_version": 1,
            "metadata": {"name": "x", "pair": "EURUSD", "timeframe": "H1"},
            "indicators": [
                {"id": "ema_fast", "kind": "EMA", "params": {"period": 20}},
                {"id": "ema_slow", "kind": "EMA", "params": {"period": 50}},
                {"id": "atr", "kind": "ATR", "params": {"period": 14}},
            ],
            "entry_long":  {"op": "CROSS_UP",   "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}]},
            "entry_short": {"op": "CROSS_DOWN", "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}]},
            "exit": {"stop_loss":   {"kind": "atr_mult", "indicator": "atr", "mult": 1.5},
                     "take_profit": {"kind": "atr_mult", "indicator": "atr", "mult": 3.0}},
        }
        from engines.strategy_ir import validate_ir
        ir = validate_ir(ir_dict)
        interp = IRInterpreter(ir, prices=prices, highs=highs, lows=lows)
        ir_atr = interp._indicator_data["atr"]["series"]
        leg_atr = _atr(highs, lows, prices, 14)
        assert ir_atr == leg_atr

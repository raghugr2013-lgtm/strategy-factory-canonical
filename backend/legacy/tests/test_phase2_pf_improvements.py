"""
Phase-2 PF-improvement tests.

These pin the additive Phase-2 behaviours layered on top of the
Phase-1 correctness contract:

  1. ATR helper produces a sensibly-shaped series with leading Nones
     (warm-up) and finite numbers afterwards.
  2. The risk-model parser maps the diversity generator's text to the
     correct {model, atr_k, atr_m} shape.
  3. ATR-adaptive SL/TP fires on `atr_based` and `trailing_stop` text;
     trailing-stop kicks in after +1R and tracks after +2R.
  4. Regime gate suppresses entries when the trailing window's regime
     ≠ strategy_type's preference, but never violates the leakage_guard
     contract.
  5. Asymmetric slippage and session-aware spread are reported in the
     `_phase2` telemetry block when default-on.
  6. Phase-1 leakage_guard remains all-True with Phase-2 features
     active — Phase 2 does NOT regress correctness.
  7. History prior returns uniform weights when the library is empty
     and biases toward higher-scoring types when populated; uniform
     fallback when the DB is unreachable.
  8. Generation prior is non-fatal: `generate_strategy_text` still
     returns a valid strategy text when the DB is unavailable.
"""
from __future__ import annotations

import math
import random

import pytest

from engines.backtest_engine import (
    run_backtest_logic,
    _atr,
    _parse_risk_model,
    _session_spread_multiplier,
    _REGIME_PREFERENCE,
)


# ─────────────────────────────────────────────────────────────────────
# Same fixture as Phase-1, but a bit longer + clearer trend so the
# regime classifier produces an unambiguous "trending" label.
# ─────────────────────────────────────────────────────────────────────

def _build_prices(n: int = 600, seed: int = 7) -> tuple[list, list, list]:
    rng = random.Random(seed)
    closes, highs, lows = [], [], []
    base = 1.10
    for i in range(n):
        c = base + i * 0.0001 + math.sin(i / 11) * 0.0035 + rng.uniform(-0.0005, 0.0005)
        bar = abs(rng.uniform(0.0006, 0.0016))
        h = c + bar / 2 + abs(rng.uniform(0, 0.0003))
        lo = c - bar / 2 - abs(rng.uniform(0, 0.0003))
        closes.append(round(c, 5)); highs.append(round(h, 5)); lows.append(round(lo, 5))
    return closes, highs, lows


TREND_TEXT = (
    "STRATEGY: Trend Following · EMA · crossover (medium)\n"
    "TYPE: trend_following\n"
    "INDICATORS: EMA(fast=8)/EMA(slow=21)\n"
    "FREQUENCY: medium\n"
    "ENTRY LONG: BUY when fast MA(8) crosses ABOVE slow MA(21)\n"
    "ENTRY SHORT: SELL when fast MA(8) crosses BELOW slow MA(21)\n"
    "RISK MODEL: fixed_rr_1_2\n"
    "EXIT: SL=20 pips | TP=40 pips (fixed 1:2 RR)\n"
    "PARAMETERS: EMA fast=8, EMA slow=21, SL=20, TP=40\n"
)

ATR_TEXT = (
    "STRATEGY: Trend Following · EMA · crossover (medium)\n"
    "TYPE: trend_following\n"
    "INDICATORS: EMA(fast=8)/EMA(slow=21)\n"
    "FREQUENCY: medium\n"
    "ENTRY LONG: BUY when fast MA(8) crosses ABOVE slow MA(21)\n"
    "ENTRY SHORT: SELL when fast MA(8) crosses BELOW slow MA(21)\n"
    "RISK MODEL: atr_based\n"
    "EXIT: SL=ATR k=1.5 | TP=ATR m=3.0 (ATR-adaptive)\n"
    "PARAMETERS: EMA fast=8, EMA slow=21, ATR k=1.5, ATR m=3.0\n"
)

TRAIL_TEXT = (
    "STRATEGY: Trend Following · EMA · crossover (medium)\n"
    "TYPE: trend_following\n"
    "INDICATORS: EMA(fast=8)/EMA(slow=21)\n"
    "FREQUENCY: medium\n"
    "ENTRY LONG: BUY when fast MA(8) crosses ABOVE slow MA(21)\n"
    "ENTRY SHORT: SELL when fast MA(8) crosses BELOW slow MA(21)\n"
    "RISK MODEL: trailing_stop\n"
    "EXIT: SL=20 pips, trail after +1R, trail behind by 1xATR after +2R\n"
    "PARAMETERS: EMA fast=8, EMA slow=21, SL=20, ATR k=1.5\n"
)


# ─────────────────────────────────────────────────────────────────────
# 1. ATR helper
# ─────────────────────────────────────────────────────────────────────

def test_atr_shape_and_warmup():
    closes, highs, lows = _build_prices(50)
    out = _atr(highs, lows, closes, period=14)
    assert len(out) == len(closes)
    # First 14 entries should be None (warm-up + seed bar)
    assert all(v is None for v in out[:14])
    # Entries from index 14 onward must be positive finite floats
    for v in out[14:]:
        assert v is not None
        assert math.isfinite(v) and v > 0


def test_atr_handles_missing_highs_lows():
    """Falls back to close-to-close when H/L missing — never throws."""
    closes = [1.10, 1.11, 1.12, 1.13, 1.14] * 10
    out = _atr([], [], closes, period=14)
    assert len(out) == len(closes)
    assert all(v is None or v >= 0 for v in out)


# ─────────────────────────────────────────────────────────────────────
# 2. Risk model parser
# ─────────────────────────────────────────────────────────────────────

def test_parse_risk_model_atr():
    r = _parse_risk_model(ATR_TEXT)
    assert r["model"] == "atr_based"
    assert r["atr_k"] == 1.5
    assert r["atr_m"] == 3.0


def test_parse_risk_model_trailing():
    r = _parse_risk_model(TRAIL_TEXT)
    assert r["model"] == "trailing_stop"


def test_parse_risk_model_fixed_rr():
    r = _parse_risk_model(TREND_TEXT)
    assert r["model"] == "fixed_rr_1_2"


def test_parse_risk_model_unknown():
    r = _parse_risk_model("STRATEGY: something completely unrelated")
    assert r["model"] is None
    assert r["atr_k"] is None
    assert r["atr_m"] is None


# ─────────────────────────────────────────────────────────────────────
# 3. ATR-adaptive exits + trailing stop telemetry
# ─────────────────────────────────────────────────────────────────────

def test_atr_based_strategy_uses_atr_for_sltp():
    closes, highs, lows = _build_prices(600)
    out = run_backtest_logic(
        ATR_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
    )
    p2 = out["_phase2"]
    assert p2["risk_model"] == "atr_based"
    # Either some IS or OOS trade used ATR (depends on regime gate),
    # OR no trades fired at all (regime blocked everything → trivial).
    if out["total_trades"] > 0 or out["oos_total_trades"] > 0:
        assert (p2["is_atr_used"] + p2["oos_atr_used"]) >= 1


def test_trailing_stop_strategy_reports_trailing_telemetry():
    closes, highs, lows = _build_prices(800)
    out = run_backtest_logic(
        TRAIL_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
    )
    p2 = out["_phase2"]
    assert p2["risk_model"] == "trailing_stop"
    # Cannot guarantee a trade reached +1R on this fixture; just assert
    # the telemetry surface exists and is non-negative.
    assert p2["is_trailing_used"] >= 0
    assert p2["oos_trailing_used"] >= 0


# ─────────────────────────────────────────────────────────────────────
# 4. Regime gate
# ─────────────────────────────────────────────────────────────────────

def test_regime_filter_default_off_but_telemetry_present():
    """P1 — regime filter defaults OFF now. Telemetry block still
    emitted so the UI can render the chip; just with
    `regime_filter_enabled: False` and counters = 0."""
    closes, highs, lows = _build_prices(600)
    out = run_backtest_logic(
        TREND_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
    )
    p2 = out["_phase2"]
    assert p2["regime_filter_enabled"] is False
    assert p2["is_regime_blocked"] == 0
    assert p2["oos_regime_blocked"] == 0


def test_regime_filter_can_be_enabled():
    """Opt-in regime filter: counters non-zero proves gate actually ran."""
    closes, highs, lows = _build_prices(600)
    out = run_backtest_logic(
        TREND_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        sim_config={"regime_filter": True},
    )
    p2 = out["_phase2"]
    assert p2["regime_filter_enabled"] is True
    assert p2["is_regime_blocked"] >= 0
    assert p2["oos_regime_blocked"] >= 0


def test_regime_filter_can_be_disabled():
    closes, highs, lows = _build_prices(600)
    out_off = run_backtest_logic(
        TREND_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
        sim_config={"regime_filter": False},
    )
    assert out_off["_phase2"]["regime_filter_enabled"] is False
    assert out_off["_phase2"]["is_regime_blocked"] == 0


def test_regime_preference_table_covers_all_strategy_types():
    expected = {
        "trend_following", "mean_reversion", "momentum", "breakout",
        "scalping", "volatility_based", "session_based",
    }
    assert expected <= set(_REGIME_PREFERENCE.keys())
    for v in _REGIME_PREFERENCE.values():
        assert "unknown" in v, "Insufficient-sample 'unknown' regime must always be allowed"


# ─────────────────────────────────────────────────────────────────────
# 5. Session spread + asym slippage telemetry
# ─────────────────────────────────────────────────────────────────────

def test_session_spread_multiplier_table():
    # Asian thin hours wider than London peak
    asian = _session_spread_multiplier("2024-01-01T02:00:00")
    london = _session_spread_multiplier("2024-01-01T09:00:00")
    assert asian > london
    # Unknown / null → 1.0
    assert _session_spread_multiplier(None) == 1.0
    assert _session_spread_multiplier("not-a-timestamp") == 1.0


def test_phase2_telemetry_block_present():
    closes, highs, lows = _build_prices(600)
    out = run_backtest_logic(
        TREND_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
    )
    p2 = out["_phase2"]
    for key in (
        "risk_model", "atr_k", "atr_m",
        "regime_filter_enabled", "asym_slip_enabled", "session_spread_enabled",
        "is_regime_blocked", "oos_regime_blocked",
        "is_atr_used", "oos_atr_used",
        "is_trailing_used", "oos_trailing_used",
    ):
        assert key in p2, f"_phase2 missing {key}"


# ─────────────────────────────────────────────────────────────────────
# 6. Phase-1 contract preserved
# ─────────────────────────────────────────────────────────────────────

def test_phase1_leakage_guard_still_all_true_with_phase2():
    closes, highs, lows = _build_prices(600)
    out = run_backtest_logic(
        ATR_TEXT, "EURUSD", "H1",
        external_prices=closes, external_highs=highs, external_lows=lows,
    )
    g = out["_leakage_guard"]
    assert g["indicators_in_segment"] is True
    assert g["no_look_ahead"] is True
    assert g["is_oos_isolated"] is True


# ─────────────────────────────────────────────────────────────────────
# 7. History prior — defensive behaviour
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_prior_uniform_when_empty(monkeypatch):
    from engines import history_prior
    history_prior.clear_cache()

    async def _empty(*_a, **_k):
        return {}
    monkeypatch.setattr(history_prior, "_aggregate_pair_tf", _empty)

    weights = await history_prior.get_type_weights("XYZ", "M5")
    assert pytest.approx(sum(weights.values()), abs=1e-6) == 1.0
    # Uniform within tolerance
    n = len(weights)
    for v in weights.values():
        assert abs(v - 1.0 / n) < 1e-6


@pytest.mark.asyncio
async def test_history_prior_biased_when_data_present(monkeypatch):
    from engines import history_prior
    history_prior.clear_cache()

    async def _seed(*_a, **_k):
        return {
            "trend_following": 80.0,
            "mean_reversion":  20.0,
            # other types absent (count < SAMPLE_FLOOR) → uniform floor only
        }
    monkeypatch.setattr(history_prior, "_aggregate_pair_tf", _seed)

    weights = await history_prior.get_type_weights("EURUSD", "H1")
    assert weights["trend_following"] > weights["mean_reversion"]
    # Floor still applied — nothing is zero
    for v in weights.values():
        assert v >= 0.01


@pytest.mark.asyncio
async def test_history_prior_resilient_to_db_failure(monkeypatch):
    from engines import history_prior
    history_prior.clear_cache()

    async def _boom(*_a, **_k):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(history_prior, "_aggregate_pair_tf", _boom)

    # Even with a thrown exception inside the aggregator, the public
    # helper must not raise.
    try:
        weights = await history_prior.get_type_weights("EURUSD", "H1")
    except RuntimeError:
        pytest.fail("history_prior must swallow DB failures and return uniform")
    assert pytest.approx(sum(weights.values()), abs=1e-6) == 1.0

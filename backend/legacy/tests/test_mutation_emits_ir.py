"""Phase 28-A — Mutation engine emits valid IR for every covered type.

End-to-end coverage: feed each mutation type a synthetic base strategy
and verify the resulting variant carries a validated ``strategy_ir``
block with ``ir_status='ir_native'`` (or ``'legacy'`` for not-yet-covered
mutations, per operator decision).

Also exercises the IR renderer so the human-readable text is non-empty
and references the expected indicators/predicates.
"""
from __future__ import annotations

import sys


_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines.mutation_engine import (                          # noqa: E402
    MUTATION_TYPES, mutate_strategy, mutate_strategy_by_types,
)
from engines.strategy_ir import is_valid_ir       # noqa: E402
from engines.strategy_ir_renderer import render_ir_to_text     # noqa: E402


def _base():
    return {
        "strategy_text": "Base EMA crossover on EURUSD H1 with RSI(14) filter.",
        "pair": "EURUSD",
        "timeframe": "H1",
        "style": "trend_following",
        "parameters": {"ema_fast": 50, "ema_slow": 200, "rsi_period": 14},
    }


# ── Bulk smoke test — every mutation type produces a variant ─────


def test_mutate_strategy_returns_variants_with_ir_status():
    variants = mutate_strategy(_base(), max_variants=15)
    assert len(variants) >= 5
    for v in variants:
        assert "ir_status" in v
        assert v["ir_status"] in ("ir_native", "legacy")
        assert v.get("mutation_type") in MUTATION_TYPES


def test_every_root_mutation_emits_ir_native_block():
    """Phase 28-A coverage target — the v1 IR vocabulary covers all
    seven root mutations + four additive filters + three risk_reward
    ratios + filter_remove_rsi = 15 total."""
    expected_native = {
        "trend_pullback", "session_london_breakout", "session_asian_range",
        "volatility_atr_breakout", "volatility_bollinger_squeeze",
        "mean_reversion_rsi", "mean_reversion_bollinger",
    }
    variants = mutate_strategy(_base(), max_variants=15)
    seen_native = {v["mutation_type"] for v in variants
                   if v.get("ir_status") == "ir_native"}
    # Every root mutation must be in seen_native.
    missing = expected_native - seen_native
    assert not missing, f"missing IR-native coverage: {missing}"


def test_emitted_ir_validates_against_schema():
    variants = mutate_strategy(_base(), max_variants=15)
    native = [v for v in variants if v.get("ir_status") == "ir_native"]
    assert native, "no IR-native variants emitted"
    for v in native:
        ir = v["strategy_ir"]
        assert is_valid_ir(ir), f"invalid IR for {v['mutation_type']}: {ir}"


def test_render_ir_to_text_produces_human_readable_output():
    variants = mutate_strategy(_base(), max_variants=15)
    native = next(v for v in variants if v.get("ir_status") == "ir_native")
    rendered = render_ir_to_text(native["strategy_ir"])
    assert "STRATEGY:" in rendered
    assert "ENTRY LONG:" in rendered
    assert "EXIT:" in rendered


# ── Per-mutation semantic checks ─────────────────────────────────


def test_trend_pullback_ir_has_three_ema_indicators():
    variants = mutate_strategy_by_types(_base(), ["trend_pullback"])
    assert len(variants) == 1
    ir = variants[0]["strategy_ir"]
    ema_ids = {i["id"] for i in ir["indicators"] if i["kind"] == "EMA"}
    assert {"ema_fast", "ema_mid", "ema_slow"}.issubset(ema_ids)
    # Exit is ATR-based, not fixed-pip.
    assert ir["exit"]["stop_loss"]["kind"] == "atr_mult"
    assert ir["exit"]["take_profit"]["kind"] == "atr_mult"


def test_session_london_breakout_has_session_filter_and_time_exit():
    variants = mutate_strategy_by_types(_base(), ["session_london_breakout"])
    ir = variants[0]["strategy_ir"]
    assert ir["session_filter"] is not None
    assert ir["session_filter"]["open"] == "07:00"
    assert ir["session_filter"]["close"] == "11:00"
    assert ir["exit"]["time_exit"]["close_all_gmt"] == "16:00"
    assert ir["entry_long"]["op"] == "RANGE_BREAK_UP"
    assert ir["entry_long"]["window_start_gmt"] == "06:00"


def test_session_asian_range_uses_range_fraction_exits():
    variants = mutate_strategy_by_types(_base(), ["session_asian_range"])
    ir = variants[0]["strategy_ir"]
    assert ir["exit"]["stop_loss"]["kind"] == "range_fraction"
    assert ir["exit"]["stop_loss"]["ratio"] == 0.5
    assert ir["exit"]["take_profit"]["ratio"] == 1.0
    assert ir["exit"]["time_exit"]["close_all_gmt"] == "15:00"


def test_volatility_atr_breakout_has_atr_filter():
    variants = mutate_strategy_by_types(_base(), ["volatility_atr_breakout"])
    ir = variants[0]["strategy_ir"]
    assert ir["volatility_filter"] is not None
    assert ir["volatility_filter"]["indicator"] == "atr"
    assert ir["exit"]["stop_loss"]["kind"] == "atr_mult"


def test_bb_squeeze_uses_squeeze_predicate_and_band_break():
    variants = mutate_strategy_by_types(_base(), ["volatility_bollinger_squeeze"])
    ir = variants[0]["strategy_ir"]
    ops = [a["op"] for a in ir["entry_long"]["args"]]
    assert "BB_SQUEEZE_PERCENTILE" in ops
    assert "BAND_BREAK_UPPER" in ops


def test_mean_reversion_rsi_uses_indicator_cross_tp():
    variants = mutate_strategy_by_types(_base(), ["mean_reversion_rsi"])
    ir = variants[0]["strategy_ir"]
    assert ir["exit"]["take_profit"]["kind"] == "indicator_cross"
    assert ir["exit"]["take_profit"]["indicator"] == "rsi"
    assert ir["exit"]["take_profit"]["level"] == 50.0


def test_mean_reversion_bollinger_uses_band_touch():
    variants = mutate_strategy_by_types(_base(), ["mean_reversion_bollinger"])
    ir = variants[0]["strategy_ir"]
    assert ir["entry_long"]["op"] == "BAND_TOUCH_LOWER"
    assert ir["entry_short"]["op"] == "BAND_TOUCH_UPPER"


# ── Composer mutations — filter_add_* — now emit `ir_native` (Phase 28-B+) ──
# Phase 28-A documented that composers required a base IR to layer onto
# and intentionally fell back to ir_status='legacy'. Phase 28-B+ threads
# a canonical base IR (derived via ``_derive_base_ir``) through every
# mutate_strategy call so composers now produce IR-native mutations.
# Detailed semantic + bit-exact legacy parity for composers lives in
# ``tests/test_composer_mutation_ir_parity.py``.


def test_composer_mutations_now_ir_native():
    """filter_add_*, mtf_htf_*, filter_remove_rsi, and risk_reward_* now
    receive a canonical base IR derived from the base strategy text and
    must produce ir_status='ir_native' for any mappable base."""
    composer_types = {"filter_add_rsi", "filter_add_volatility",
                      "filter_add_trend", "mtf_htf_confirmation",
                      "filter_remove_rsi",
                      "risk_reward_1_1", "risk_reward_1_1_5", "risk_reward_1_2"}
    variants = mutate_strategy(_base(), max_variants=15)
    composer_variants = [v for v in variants
                         if v["mutation_type"] in composer_types]
    assert composer_variants, "no composer variants present"
    for v in composer_variants:
        assert v["ir_status"] == "ir_native", (
            f"composer {v['mutation_type']} regressed to legacy"
        )
        assert v["strategy_ir"] is not None
        assert v["strategy_ir"]["ir_version"] == 1


# ── Architectural invariants ─────────────────────────────────────


def test_existing_strategy_text_still_emitted():
    """Phase 28-A is ADDITIVE — strategy_text must still be present on
    every variant so legacy consumers continue to work."""
    variants = mutate_strategy(_base(), max_variants=15)
    for v in variants:
        assert v.get("strategy_text"), \
            f"strategy_text missing from {v.get('mutation_type')}"


def test_existing_parameters_dict_still_emitted():
    """Same back-compat check for the legacy parameters dict."""
    variants = mutate_strategy(_base(), max_variants=15)
    for v in variants:
        assert "parameters" in v, \
            f"parameters missing from {v.get('mutation_type')}"


def test_variant_fingerprint_still_present():
    variants = mutate_strategy(_base(), max_variants=15)
    for v in variants:
        assert v.get("variant_fingerprint")

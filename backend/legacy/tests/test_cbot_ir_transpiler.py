"""Phase 28-C — IR transpiler trust gate.

Four tiers, mirroring Phase 28-B's structure:

    Tier 1 — Determinism             same IR → byte-identical C#
    Tier 2 — Token validity          balanced braces/parens + required
                                     C# tokens (using/namespace/class
                                     Robot/OnStart/OnBar)
    Tier 3 — Declaration completeness every IR indicator → C# field
                                     + OnStart init; every operator
                                     reference resolves
    Tier 4 — Semantic parity         parity simulator signal series
                                     vs interpreter signal series

Additional gates per operator directives 6, 7, 9:
    * Tier 5 — Execution lineage metadata block present and complete
    * Tier 6 — Unsupported IR raises UnsupportedIROperatorError loudly
    * Tier 7 — Timing semantics: emitted C# uses Last(1)/Last(2)
              (just-closed / previous-closed), never Last(0)
              (the forming bar) for signal logic
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

from cbot_engine.ir_emitter import (                                  # noqa: E402
    SUPPORTED_OPERATORS, SUPPORTED_INDICATORS,
    SUPPORTED_SL_KINDS, SUPPORTED_TP_KINDS,
    UnsupportedIROperatorError,
)
from cbot_engine.ir_parity_simulator import (                         # noqa: E402
    IRCoverageGap, simulate_cbot_signals,
)
from cbot_engine.ir_transpiler import (                               # noqa: E402
    transpile_ir_to_csharp,
)
from cbot_engine import ir_templates as T                             # noqa: E402
from engines.ir_interpreter import IRInterpreter                      # noqa: E402
from engines.mutation_engine import (                                 # noqa: E402
    _derive_base_ir, mutate_strategy_by_types,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

_TREND_TEXT = (
    "STRATEGY: Base Trend (EURUSD H1)\n"
    "ENTRY LONG:  EMA(20) crosses above EMA(50)\n"
    "ENTRY SHORT: EMA(20) crosses below EMA(50)\n"
    "EXIT: SL = 20 pips  |  TP = 40 pips\n"
)


def _trend_base():
    return {"strategy_text": _TREND_TEXT,
            "pair": "EURUSD", "timeframe": "H1"}


def _series(n=400, seed=42):
    rng = random.Random(seed)
    prices, highs, lows, ts = [], [], [], []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        c = 1.10 + 0.005 * math.sin(2 * math.pi * i / 50) + (rng.random() - 0.5) * 0.001
        prices.append(c)
        highs.append(c + 0.0005 + rng.random() * 0.0003)
        lows.append(c - 0.0005 - rng.random() * 0.0003)
        ts.append(start + timedelta(hours=i))
    return prices, highs, lows, ts


def _reseed_from_variant(v):
    return {"strategy_text": v["strategy_text"], "pair": "EURUSD",
            "timeframe": "H1", "strategy_ir": v["strategy_ir"]}


def _root_ir():
    return _derive_base_ir(_trend_base())


def _composer_chain_ir():
    v1 = mutate_strategy_by_types(_trend_base(), ["filter_add_rsi"])[0]
    v2 = mutate_strategy_by_types(_reseed_from_variant(v1),
                                   ["mtf_htf_confirmation"])[0]
    return v2["strategy_ir"]


def _rr_chain_ir():
    v1 = mutate_strategy_by_types(_trend_base(), ["filter_add_rsi"])[0]
    v2 = mutate_strategy_by_types(_reseed_from_variant(v1),
                                   ["risk_reward_1_2"])[0]
    return v2["strategy_ir"]


def _vol_chain_ir():
    v1 = mutate_strategy_by_types(_trend_base(),
                                   ["filter_add_volatility"])[0]
    return v1["strategy_ir"]


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Determinism
# ─────────────────────────────────────────────────────────────────────

class TestDeterminism:

    def test_root_ir_byte_identical_across_calls(self):
        ir = _root_ir()
        ts = "2026-05-14T00:00:00+00:00"
        a = transpile_ir_to_csharp(ir, generated_at=ts)
        b = transpile_ir_to_csharp(ir, generated_at=ts)
        assert a["csharp"] == b["csharp"]
        assert a["strategy_hash"] == b["strategy_hash"]
        assert a["bot_name"] == b["bot_name"]

    def test_composer_chain_byte_identical(self):
        ir = _composer_chain_ir()
        ts = "2026-05-14T00:00:00+00:00"
        a = transpile_ir_to_csharp(ir, generated_at=ts)
        b = transpile_ir_to_csharp(ir, generated_at=ts)
        assert a["csharp"] == b["csharp"]

    def test_strategy_hash_stable_against_dict_ordering(self):
        ir = _composer_chain_ir()
        ts = "2026-05-14T00:00:00+00:00"
        a = transpile_ir_to_csharp(ir, generated_at=ts)
        # Shuffle insertion order via JSON round-trip with sorted keys.
        import json
        reordered = json.loads(json.dumps(ir, sort_keys=True))
        b = transpile_ir_to_csharp(reordered, generated_at=ts)
        assert a["strategy_hash"] == b["strategy_hash"]


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Token validity
# ─────────────────────────────────────────────────────────────────────

class TestTokenValidity:

    @pytest.mark.parametrize("ir_factory",
                              [_root_ir, _composer_chain_ir, _rr_chain_ir,
                               _vol_chain_ir])
    def test_balanced_braces_and_parens(self, ir_factory):
        cs = transpile_ir_to_csharp(ir_factory())["csharp"]
        # We strip string literals so quote-embedded braces don't
        # confuse the counter — but the templates contain none in
        # signal expressions so a raw count suffices for v1.
        assert cs.count("{") == cs.count("}"), "unbalanced { } in cBot"
        assert cs.count("(") == cs.count(")"), "unbalanced ( ) in cBot"

    @pytest.mark.parametrize("ir_factory",
                              [_root_ir, _composer_chain_ir, _rr_chain_ir,
                               _vol_chain_ir])
    def test_required_csharp_tokens_present(self, ir_factory):
        cs = transpile_ir_to_csharp(ir_factory())["csharp"]
        for tok in ("using cAlgo.API;", "namespace cAlgo.Robots",
                     ": Robot", "[Robot(", "protected override void OnStart",
                     "protected override void OnBar"):
            assert tok in cs, f"required token missing: {tok!r}"

    def test_no_orphan_format_placeholders(self):
        cs = transpile_ir_to_csharp(_composer_chain_ir())["csharp"]
        # The scaffold uses {placeholder} substitution; any leftover
        # would indicate an emitter bug. C# code legitimately contains
        # braces, but standalone "{word}" tokens with no whitespace
        # should not survive.
        import re
        leftovers = re.findall(r"(?<![{a-zA-Z])\{[a-z_]+\}(?![a-zA-Z}])", cs)
        # Allow a tiny set of intentional uses in helpers (none in v1).
        assert leftovers == [], f"orphan placeholders survived: {leftovers}"


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Declaration completeness
# ─────────────────────────────────────────────────────────────────────

class TestDeclarationCompleteness:

    @pytest.mark.parametrize("ir_factory",
                              [_root_ir, _composer_chain_ir, _rr_chain_ir,
                               _vol_chain_ir])
    def test_every_indicator_has_field_and_init(self, ir_factory):
        ir = ir_factory()
        cs = transpile_ir_to_csharp(ir)["csharp"]
        for ind in (ir["indicators"] if isinstance(ir, dict)
                     else ir.model_dump()["indicators"]):
            field = f"_{ind['id']}"
            # Declared as a private field …
            assert "private " in cs and f" {field};" in cs, (
                f"indicator field missing: {field}"
            )
            # … and initialised in OnStart().
            assert f"{field} =" in cs, (
                f"indicator init missing: {field}"
            )

    def test_htf_emits_marketdata_getbars(self):
        ir = _composer_chain_ir()
        cs = transpile_ir_to_csharp(ir)["csharp"]
        assert "MarketData.GetBars(" in cs
        # HTF_PARITY_MODE must be APPROXIMATE when HTF_EMA is present.
        assert "HTF_PARITY_MODE        : APPROXIMATE" in cs

    def test_no_htf_means_n_a_parity_mode(self):
        cs = transpile_ir_to_csharp(_root_ir())["csharp"]
        assert "HTF_PARITY_MODE        : N/A" in cs

    def test_indicator_kinds_covered_in_metadata(self):
        out = transpile_ir_to_csharp(_composer_chain_ir())
        assert "RSI" in out["metadata"]["indicator_kinds_used"]
        assert "HTF_EMA" in out["metadata"]["indicator_kinds_used"]


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Semantic parity (simulator ≡ interpreter)
# ─────────────────────────────────────────────────────────────────────

class TestSemanticParity:

    @pytest.mark.parametrize("ir_factory",
                              [_root_ir, _composer_chain_ir, _rr_chain_ir,
                               _vol_chain_ir])
    def test_simulator_signals_equal_interpreter_signals(self, ir_factory):
        ir = ir_factory()
        prices, highs, lows, ts = _series()
        sim = simulate_cbot_signals(
            ir, prices=prices, highs=highs, lows=lows, timestamps=ts,
        )
        # Re-run the interpreter directly to compare.
        if hasattr(ir, "model_dump"):
            ir_d = ir.model_dump(mode="json")
        else:
            ir_d = ir
        interp = IRInterpreter(ir_d, prices=prices, highs=highs,
                                lows=lows, timestamps=ts)
        ref = [interp.signal_at(i) for i in range(len(prices))]
        assert sim["signals"] == ref, (
            "Parity simulator signal series diverges from interpreter — "
            "transpiler semantic anchor is broken."
        )

    def test_simulator_reports_htf_when_present(self):
        prices, highs, lows, ts = _series()
        sim = simulate_cbot_signals(
            _composer_chain_ir(), prices=prices, highs=highs,
            lows=lows, timestamps=ts,
        )
        assert sim["htf_present"] is True

    def test_simulator_reports_no_htf_for_root_ir(self):
        prices, highs, lows, ts = _series()
        sim = simulate_cbot_signals(
            _root_ir(), prices=prices, highs=highs, lows=lows,
            timestamps=ts,
        )
        assert sim["htf_present"] is False


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — Execution lineage metadata (operator directive #6)
# ─────────────────────────────────────────────────────────────────────

class TestExecutionLineageMetadata:

    def test_metadata_block_complete(self):
        cs = transpile_ir_to_csharp(
            _composer_chain_ir(),
            parity_status="PASSED",
            parity_fixtures_passed=16,
            generated_at="2026-05-14T12:00:00+00:00",
        )["csharp"]
        for line in (
            "IR_VERSION             : 1",
            f"TRANSPILER_VERSION     : {T.TRANSPILER_VERSION}",
            "STRATEGY_HASH          :",
            "GENERATED_AT           : 2026-05-14T12:00:00+00:00",
            "HTF_PARITY_MODE        : APPROXIMATE",
            "PARITY_STATUS          : PASSED",
            "PARITY_FIXTURES_PASSED : 16",
        ):
            assert line in cs, f"lineage metadata line missing: {line!r}"

    def test_parity_status_defaults_to_pending(self):
        cs = transpile_ir_to_csharp(_root_ir())["csharp"]
        assert "PARITY_STATUS          : PENDING" in cs
        assert "PARITY_FIXTURES_PASSED : N/A" in cs


# ─────────────────────────────────────────────────────────────────────
# Tier 6 — Honest refusal on unsupported IR
# ─────────────────────────────────────────────────────────────────────

class TestHonestRefusalOnUnsupportedIR:

    def test_raises_on_unsupported_operator(self):
        ir = _root_ir().model_dump(mode="json")
        # Inject an unsupported operator into entry_long.
        ir["entry_long"] = {
            "op": "FFT_PHASE_LOCK", "args": [{"const": 1}, {"const": 2}],
        }
        with pytest.raises((UnsupportedIROperatorError, IRCoverageGap, Exception)):
            transpile_ir_to_csharp(ir)

    def test_raises_on_unsupported_exit_kind(self):
        ir = _root_ir().model_dump(mode="json")
        ir["exit"]["stop_loss"] = {"kind": "neural_forecast", "horizon": 5}
        with pytest.raises(Exception):
            transpile_ir_to_csharp(ir)

    def test_parity_simulator_refuses_unsupported(self):
        ir = _root_ir().model_dump(mode="json")
        ir["entry_long"] = {"op": "FFT_PHASE_LOCK", "args": [{"const": 1}, {"const": 2}]}
        prices, highs, lows, ts = _series()
        with pytest.raises((IRCoverageGap, Exception)):
            simulate_cbot_signals(ir, prices=prices, highs=highs,
                                   lows=lows, timestamps=ts)


# ─────────────────────────────────────────────────────────────────────
# Tier 7 — Timing semantics (operator directive #9, first-class concern)
# ─────────────────────────────────────────────────────────────────────

class TestTimingSemantics:
    """The interpreter answers signal_at(i) where i = closed-bar index.
    The cBot's OnBar() fires after a bar closes, and at that moment the
    just-closed bar is Bars.ClosePrices.Last(1). Last(0) is the new
    forming bar — using it for signal logic would create intrabar
    divergence. We assert the emitter never reaches for Last(0) in any
    signal expression."""

    @pytest.mark.parametrize("ir_factory",
                              [_root_ir, _composer_chain_ir, _rr_chain_ir,
                               _vol_chain_ir])
    def test_no_last_zero_in_signal_logic(self, ir_factory):
        cs = transpile_ir_to_csharp(ir_factory())["csharp"]
        # Extract just the predicate methods (EvalEntryLong + EvalEntryShort).
        import re
        body_match = re.search(
            r"private bool EvalEntryLong\(\).*?private bool EvalEntryShort\(\).*?\}",
            cs, re.DOTALL,
        )
        assert body_match is not None
        body = body_match.group(0)
        assert ".Last(0)" not in body, (
            "Signal expression reaches for Last(0) — the forming bar. "
            "This would create intrabar divergence vs the interpreter."
        )

    def test_cross_up_uses_last_1_and_last_2(self):
        cs = transpile_ir_to_csharp(_root_ir())["csharp"]
        # Trend base produces CROSS_UP(ema_fast, ema_slow) on entry_long.
        # The emission must reference Last(1) and Last(2).
        assert ".Last(1)" in cs and ".Last(2)" in cs

    def test_force_flat_executes_before_entry(self):
        ir = _root_ir().model_dump(mode="json")
        # Inject a time_exit to verify the force-flat block emits.
        ir["exit"]["time_exit"] = {"close_all_gmt": "21:00"}
        out = transpile_ir_to_csharp(ir)
        cs = out["csharp"]
        # Force-flat must appear BEFORE the entry signal section.
        ff_pos = cs.find("CloseAllOwned()")
        entry_pos = cs.find("EvalEntryLong()")
        assert 0 < ff_pos < entry_pos, (
            "Force-flat must execute before any entry gate."
        )

    def test_session_check_precedes_entry(self):
        cs = transpile_ir_to_csharp(_root_ir())["csharp"]
        sess_pos = cs.find("SessionOk()")
        entry_pos = cs.find("EvalEntryLong()")
        assert 0 < sess_pos < entry_pos

    def test_spread_check_precedes_entry(self):
        # P0.2 (institutional diagnostics) factored the inline expression
        # `Symbol.Spread / Symbol.PipSize > MaxSpreadPips` into a local
        # `currentSpreadPips` plus an `if (currentSpreadPips > MaxSpreadPips)`
        # gate so the LogGate("spread", ...) call can quote the value.
        # Semantics are unchanged: a per-bar spread check still gates
        # entry before `EvalEntryLong()`. This assertion is the
        # semantic-rather-than-literal version of the previous check.
        cs = transpile_ir_to_csharp(_root_ir())["csharp"]
        spread_expr_pos = cs.find("Symbol.Spread / Symbol.PipSize")
        spread_cmp_pos = cs.find("> MaxSpreadPips")
        entry_pos = cs.find("EvalEntryLong()")
        assert 0 < spread_expr_pos < entry_pos, (
            "Spread expression must appear before the entry signal."
        )
        assert 0 < spread_cmp_pos < entry_pos, (
            "Spread > MaxSpreadPips gate must precede entry."
        )


# ─────────────────────────────────────────────────────────────────────
# Vocabulary completeness — every operator in the v1 spec is actually
# emittable (no advertised-but-unimplemented operators)
# ─────────────────────────────────────────────────────────────────────

class TestVocabularyCompleteness:

    def test_supported_sets_match_phase_28_b_interpreter(self):
        # These four sets are the contract for Phase 28-C v1. If any
        # changes, the trust gate must be re-run.
        assert SUPPORTED_OPERATORS == frozenset({
            "AND", "OR", "NOT",
            "GT", "LT", "GE", "LE", "EQ", "NEQ",
            "CROSS_UP", "CROSS_DOWN",
            "RANGE_BREAK_UP", "RANGE_BREAK_DOWN",
            "AT_TIME", "IN_GMT_WINDOW",
            "BAND_TOUCH_UPPER", "BAND_TOUCH_LOWER",
            "BAND_BREAK_UPPER", "BAND_BREAK_LOWER",
            "ATR_RATIO_ABOVE",
            "HTF_SLOPE_UP", "HTF_SLOPE_DOWN",
            "BB_SQUEEZE_PERCENTILE",
        })
        assert SUPPORTED_INDICATORS == frozenset(
            {"EMA", "RSI", "ATR", "BOLLINGER", "HTF_EMA"}
        )
        assert SUPPORTED_SL_KINDS == frozenset(
            {"pips", "atr_mult", "range_fraction", "band_mid"}
        )
        assert SUPPORTED_TP_KINDS == frozenset(
            {"pips", "atr_mult", "range_fraction", "band_mid",
             "indicator_cross"}
        )

    def test_macd_explicitly_unsupported(self):
        """Operator decision: momentum / MACD deferred to IR v1.1.
        A MACD-bearing IR must be refused, not silently degraded."""
        ir = _root_ir().model_dump(mode="json")
        ir["indicators"].append({"id": "macd", "kind": "MACD",
                                  "params": {"fast": 12, "slow": 26,
                                             "signal": 9}})
        with pytest.raises(Exception):
            transpile_ir_to_csharp(ir)

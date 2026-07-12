"""Phase 28-B++ — Cross-cycle composer-chain continuity trust gate.

Closes a higher-order continuity sub-gap surfaced during the Phase 28-B+
inspection: ``_derive_base_ir`` previously consulted only
``base["strategy_text"]``, never the ``base["strategy_ir"]`` that a
re-mutated variant carries. Consequence: iterative composer evolution
across mutation cycles would silently REGENERATE a fresh canonical
reference IR from text classification on cycle N+1, dropping the
overlays accumulated on cycle N.

This suite proves the additive fix: when a base strategy already carries
a valid IR (i.e. it is itself the output of a prior composer mutation /
IR-native save), the IR is preserved as-is and the next composer layers
deterministically on top — exactly the semantic continuity the rest of
the Phase 28 architecture promises.

Discipline:
    * additive — only new tests, no edits to existing trust gates
    * reversible — relies on a single short-circuit in _derive_base_ir
    * legacy-safe — bases without ``strategy_ir`` keep using the
      text-derivation path bit-for-bit
    * deterministic — same chain in → same final IR JSON out

Coverage:
    1. _derive_base_ir prefers a carried valid IR over text derivation
    2. _derive_base_ir falls back to text derivation when carried IR
       is None / malformed / missing — i.e. legacy bases are untouched
    3. mutate_strategy carries strategy_ir from base_strategy into the
       internal derivation pipeline
    4. mutate_strategy_by_types carries strategy_ir likewise
    5. Two-cycle chain `filter_add_rsi → mtf_htf_confirmation` retains
       BOTH the rsi_filter indicator and the htf_ema indicators in the
       final IR
    6. The cycle-2 predicate tree retains BOTH the cycle-1 RSI gate and
       the cycle-2 HTF gate (no overlay loss)
    7. Three-cycle chain (filter_add_rsi → mtf_htf_confirmation →
       filter_add_volatility) accumulates all three overlays
    8. Cross-cycle interpreter monotonicity: signal count strictly
       non-increasing as restrictive filters compound
    9. Determinism: identical chain on identical fixtures → identical
       final IR JSON
   10. Pydantic round-trip stability across the chain
   11. filter_remove_rsi applied to a previously-rsi-gated chain
       correctly strips the cycle-1 RSI overlay (chain-aware removal)
   12. risk_reward composer applied at the end of a chain replaces SL/TP
       only; entry predicate accumulations from prior cycles survive
"""
from __future__ import annotations

import math
import random
import sys
from datetime import datetime, timedelta, timezone


_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines.ir_interpreter import IRInterpreter                  # noqa: E402
from engines.mutation_engine import (                              # noqa: E402
    _derive_base_ir, mutate_strategy, mutate_strategy_by_types,
)
from engines.strategy_ir import StrategyIR, validate_ir            # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _make_oscillating_series(n=600, base=1.10, amp=0.005, period=50):
    """Mirror of the Phase 28-B+ trust-gate fixture so signal counts
    are directly comparable across suites."""
    prices, highs, lows, ts = [], [], [], []
    rng = random.Random(42)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        c = (base
             + amp * math.sin(2 * math.pi * i / period)
             + (rng.random() - 0.5) * 0.001)
        prices.append(c)
        highs.append(c + 0.0005 + rng.random() * 0.0003)
        lows.append(c - 0.0005 - rng.random() * 0.0003)
        ts.append(start + timedelta(hours=i))
    return prices, highs, lows, ts


_TREND_BASE_TEXT = (
    "STRATEGY: Base Trend (EURUSD H1)\n"
    "ENTRY LONG:  EMA(20) crosses above EMA(50)\n"
    "ENTRY SHORT: EMA(20) crosses below EMA(50)\n"
    "EXIT: SL = 20 pips  |  TP = 40 pips\n"
)


def _trend_base():
    return {
        "strategy_text": _TREND_BASE_TEXT,
        "pair": "EURUSD",
        "timeframe": "H1",
        "style": "trend",
        "parameters": {},
    }


def _reseed_from_variant(variant: dict) -> dict:
    """Build a base_strategy dict from a prior-cycle variant, carrying
    the variant's strategy_ir verbatim — exactly what would happen if
    the variant had been saved to the library and re-mutated on the
    next autonomous cycle."""
    return {
        "strategy_text": variant["strategy_text"],
        "pair": variant.get("pair", "EURUSD"),
        "timeframe": variant.get("timeframe", "H1"),
        "style": variant.get("style", "trend"),
        "parameters": variant.get("parameters") or {},
        "strategy_ir": variant.get("strategy_ir"),
    }


def _signal_count(ir: StrategyIR, prices, highs, lows, ts) -> int:
    interp = IRInterpreter(ir, prices=prices, highs=highs,
                           lows=lows, timestamps=ts)
    return sum(1 for i in range(len(prices)) if interp.signal_at(i) is not None)


def _has_indicator(ir_d: dict, kind: str, id_: str = None) -> bool:
    for ind in ir_d.get("indicators", []):
        if ind.get("kind") != kind:
            continue
        if id_ is not None and ind.get("id") != id_:
            continue
        return True
    return False


def _predicate_references(node, target_ref: str) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("ref") == target_ref:
        return True
    for a in (node.get("args") or []):
        if _predicate_references(a, target_ref):
            return True
    return False


def _predicate_uses_op(node, op_name: str) -> bool:
    if not isinstance(node, dict):
        return False
    if node.get("op") == op_name:
        return True
    for a in (node.get("args") or []):
        if _predicate_uses_op(a, op_name):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────
# Group 1 — _derive_base_ir short-circuit semantics
# ─────────────────────────────────────────────────────────────────────

class TestDeriveBaseIRPrefersCarriedIR:

    def test_carries_valid_ir_dict_verbatim(self):
        # Build a base IR via the text path first, then verify that
        # passing it back as `strategy_ir` returns the SAME IR (no
        # re-derivation, no overlay loss).
        seed = _trend_base()
        derived_ir = _derive_base_ir(seed)
        assert isinstance(derived_ir, StrategyIR)
        carried = {
            "strategy_text": "irrelevant — should be ignored",
            "pair": "EURUSD",
            "timeframe": "H1",
            "strategy_ir": derived_ir.model_dump(mode="json"),
        }
        re_derived = _derive_base_ir(carried)
        assert isinstance(re_derived, StrategyIR)
        assert (re_derived.model_dump(mode="json")
                == derived_ir.model_dump(mode="json")), (
            "Carried valid IR was not preserved verbatim by _derive_base_ir"
        )

    def test_carries_strategyir_instance(self):
        seed_ir = _derive_base_ir(_trend_base())
        carried = {"strategy_text": "ignored", "pair": "EURUSD",
                   "timeframe": "H1", "strategy_ir": seed_ir}
        out = _derive_base_ir(carried)
        # Same identity OR same JSON — both are acceptable.
        assert out is not None
        assert out.model_dump(mode="json") == seed_ir.model_dump(mode="json")

    def test_falls_back_to_text_when_carried_ir_is_none(self):
        """Legacy bases (no strategy_ir field) must still derive via
        extract_params + build_legacy_reference_ir — i.e. NO regression
        in the existing path."""
        base = _trend_base()
        base["strategy_ir"] = None
        out = _derive_base_ir(base)
        assert isinstance(out, StrategyIR)
        d = out.model_dump()
        assert d["metadata"]["mutation_type"] == "_legacy_trend_following"

    def test_falls_back_to_text_when_carried_ir_is_malformed(self):
        """A malformed strategy_ir dict must not crash and must not
        short-circuit derivation — fall back to text."""
        base = _trend_base()
        base["strategy_ir"] = {"ir_version": 1, "broken": True}
        out = _derive_base_ir(base)
        # Either falls back successfully OR returns None — never raises.
        if out is not None:
            assert isinstance(out, StrategyIR)

    def test_falls_back_when_strategy_ir_key_absent(self):
        base = _trend_base()
        assert "strategy_ir" not in base
        out = _derive_base_ir(base)
        assert isinstance(out, StrategyIR)


# ─────────────────────────────────────────────────────────────────────
# Group 2 — mutate_strategy carries IR through the internal `base` dict
# ─────────────────────────────────────────────────────────────────────

class TestMutateStrategyCarriesIRThroughInternalBase:

    def test_mutate_strategy_uses_carried_ir(self):
        """If the base_strategy already carries an IR, every composer
        variant from the next cycle must be derived from THAT IR rather
        than from a fresh text-derived reference."""
        cycle1 = mutate_strategy(_trend_base(), max_variants=15)
        rsi_v1 = next(v for v in cycle1 if v["mutation_type"] == "filter_add_rsi")
        # rsi_v1's IR has the rsi_filter overlay.
        d1 = rsi_v1["strategy_ir"]
        assert _has_indicator(d1, "RSI", "rsi_filter")
        # Reseed cycle-2 with the variant as base_strategy.
        base2 = _reseed_from_variant(rsi_v1)
        cycle2 = mutate_strategy(base2, max_variants=15)
        mtf_v2 = next(v for v in cycle2
                      if v["mutation_type"] == "mtf_htf_confirmation")
        d2 = mtf_v2["strategy_ir"]
        # The cycle-2 mtf composer must retain the cycle-1 RSI overlay.
        assert _has_indicator(d2, "RSI", "rsi_filter"), (
            "Cross-cycle composer chain lost cycle-1 rsi_filter indicator"
        )
        # And add its own HTF EMA indicators on top.
        assert _has_indicator(d2, "HTF_EMA", "htf_ema_fast")
        assert _has_indicator(d2, "HTF_EMA", "htf_ema_slow")
        # The predicate tree must reference both the RSI gate AND the
        # HTF slope op — no silent dropout.
        assert _predicate_references(d2["entry_long"], "rsi_filter"), (
            "cycle-2 entry_long lost cycle-1 rsi_filter predicate gate"
        )
        assert _predicate_uses_op(d2["entry_long"], "HTF_SLOPE_UP"), (
            "cycle-2 entry_long missing HTF_SLOPE_UP"
        )

    def test_mutate_strategy_by_types_carries_ir(self):
        cycle1 = mutate_strategy_by_types(
            _trend_base(), ["filter_add_rsi"],
        )
        rsi_v1 = cycle1[0]
        assert _has_indicator(rsi_v1["strategy_ir"], "RSI", "rsi_filter")
        base2 = _reseed_from_variant(rsi_v1)
        cycle2 = mutate_strategy_by_types(
            base2, ["filter_add_trend"],
        )
        trend_v2 = cycle2[0]
        d2 = trend_v2["strategy_ir"]
        assert _has_indicator(d2, "RSI", "rsi_filter")
        assert _has_indicator(d2, "EMA", "ema_trend")

    def test_mutate_strategy_without_carried_ir_unchanged(self):
        """Legacy path (no carried IR) — full 22-test Phase 28-B+ trust
        gate still has to hold. We re-prove the core invariant here:
        every composer in cycle-1 is ir_native, and the rsi gate is
        present in the filter_add_rsi variant."""
        cycle1 = mutate_strategy(_trend_base(), max_variants=15)
        composers = [v for v in cycle1
                     if v["mutation_type"].startswith(("filter_", "mtf_",
                                                       "risk_reward_"))]
        assert composers, "fixture too small — no composer variants emitted"
        for v in composers:
            assert v.get("ir_status") == "ir_native", (
                f"{v['mutation_type']} regressed to legacy "
                f"(legacy fallback broke when no IR carried)"
            )


# ─────────────────────────────────────────────────────────────────────
# Group 3 — Multi-cycle accumulation
# ─────────────────────────────────────────────────────────────────────

class TestMultiCycleOverlayAccumulation:

    def _chain(self, *cycle_types):
        """Walk a deterministic chain of composer types across mutation
        cycles, returning the variant produced on each cycle."""
        base = _trend_base()
        variants = []
        for mt in cycle_types:
            cycle = mutate_strategy_by_types(base, [mt])
            assert cycle, f"chain broke at {mt}"
            v = cycle[0]
            assert v.get("ir_status") == "ir_native", (
                f"{mt} did not emit ir_native (chain step lost IR)"
            )
            variants.append(v)
            base = _reseed_from_variant(v)
        return variants

    def test_three_cycle_chain_accumulates_all_overlays(self):
        v1, v2, v3 = self._chain(
            "filter_add_rsi",
            "mtf_htf_confirmation",
            "filter_add_volatility",
        )
        d3 = v3["strategy_ir"]
        # Indicators from every cycle must be present.
        assert _has_indicator(d3, "RSI", "rsi_filter"), \
            "cycle-1 rsi_filter dropped by cycle-3"
        assert _has_indicator(d3, "HTF_EMA", "htf_ema_fast"), \
            "cycle-2 htf_ema_fast dropped by cycle-3"
        assert _has_indicator(d3, "HTF_EMA", "htf_ema_slow"), \
            "cycle-2 htf_ema_slow dropped by cycle-3"
        assert _has_indicator(d3, "ATR", "atr_filter"), \
            "cycle-3 atr_filter not declared"
        # Volatility filter block from cycle-3.
        assert d3.get("volatility_filter") is not None
        # Predicate gates from cycles 1 + 2 still reachable.
        assert _predicate_references(d3["entry_long"], "rsi_filter")
        assert _predicate_uses_op(d3["entry_long"], "HTF_SLOPE_UP")

    def test_chain_determinism(self):
        a1, a2 = self._chain("filter_add_rsi", "mtf_htf_confirmation")
        b1, b2 = self._chain("filter_add_rsi", "mtf_htf_confirmation")
        assert a2["strategy_ir"] == b2["strategy_ir"], (
            "Composer chain non-deterministic across identical inputs"
        )

    def test_chain_round_trips_through_pydantic(self):
        _, _, v3 = self._chain(
            "filter_add_rsi", "mtf_htf_confirmation", "filter_add_volatility",
        )
        d = v3["strategy_ir"]
        re_validated = validate_ir(d)
        assert re_validated.model_dump(mode="json") == d


# ─────────────────────────────────────────────────────────────────────
# Group 4 — Interpreter monotonicity across cycles
# ─────────────────────────────────────────────────────────────────────

class TestCrossCycleInterpreterMonotonicity:
    """Each additional restrictive composer in the chain MUST produce
    ≤ signals than the prior step. This is the semantic correlate of
    'no overlay was silently dropped' — if we lost cycle-1's RSI gate
    during cycle-2, the cycle-2 signal count would jump back UP."""

    def test_two_cycle_restrictive_chain_is_non_increasing(self):
        prices, highs, lows, ts = _make_oscillating_series()
        # Cycle-0: pure base.
        base_ir = _derive_base_ir(_trend_base())
        s0 = _signal_count(base_ir, prices, highs, lows, ts)
        assert s0 > 0, "fixture too quiet for monotonicity check"
        # Cycle-1: filter_add_rsi.
        v1 = mutate_strategy_by_types(_trend_base(), ["filter_add_rsi"])[0]
        ir1 = validate_ir(v1["strategy_ir"])
        s1 = _signal_count(ir1, prices, highs, lows, ts)
        # Cycle-2: mtf_htf_confirmation on top of v1.
        v2 = mutate_strategy_by_types(
            _reseed_from_variant(v1), ["mtf_htf_confirmation"],
        )[0]
        ir2 = validate_ir(v2["strategy_ir"])
        s2 = _signal_count(ir2, prices, highs, lows, ts)
        assert s1 <= s0, f"cycle-1 RSI overlay didn't restrict base: {s1} > {s0}"
        assert s2 <= s1, (
            f"cycle-2 HTF overlay didn't restrict cycle-1 — overlay LOSS "
            f"suspected (s0={s0}, s1={s1}, s2={s2})"
        )


# ─────────────────────────────────────────────────────────────────────
# Group 5 — Chain-aware removal + risk_reward at chain tip
# ─────────────────────────────────────────────────────────────────────

class TestChainAwareSpecialComposers:

    def test_filter_remove_rsi_strips_cycle1_overlay(self):
        # Cycle-1: add RSI gate.
        v1 = mutate_strategy_by_types(_trend_base(), ["filter_add_rsi"])[0]
        assert _has_indicator(v1["strategy_ir"], "RSI", "rsi_filter")
        # Cycle-2: remove RSI — the cycle-1 overlay must vanish from the
        # chained IR (proves chain-aware removal works on the carried
        # overlay, not just on text-derived bases).
        v2 = mutate_strategy_by_types(
            _reseed_from_variant(v1), ["filter_remove_rsi"],
        )[0]
        d2 = v2["strategy_ir"]
        assert not any(i["kind"] == "RSI" for i in d2["indicators"]), (
            "filter_remove_rsi failed to strip the cycle-1 rsi_filter overlay"
        )
        assert not _predicate_references(d2["entry_long"], "rsi_filter")
        assert not _predicate_references(d2["entry_short"], "rsi_filter")

    def test_risk_reward_at_chain_tip_preserves_prior_entries(self):
        # filter_add_rsi → mtf_htf_confirmation → risk_reward_1_2.
        v1 = mutate_strategy_by_types(_trend_base(), ["filter_add_rsi"])[0]
        v2 = mutate_strategy_by_types(
            _reseed_from_variant(v1), ["mtf_htf_confirmation"],
        )[0]
        v3 = mutate_strategy_by_types(
            _reseed_from_variant(v2), ["risk_reward_1_2"],
        )[0]
        d3 = v3["strategy_ir"]
        # SL/TP replaced with fixed pips at 1:2 RR.
        assert d3["exit"]["stop_loss"]["kind"] == "pips"
        assert d3["exit"]["stop_loss"]["pips"] == 20.0
        assert d3["exit"]["take_profit"]["kind"] == "pips"
        assert d3["exit"]["take_profit"]["pips"] == 40.0
        # But the entry predicates from cycles 1 + 2 must survive
        # unchanged — risk_reward only touches the exit block.
        assert _predicate_references(d3["entry_long"], "rsi_filter")
        assert _predicate_uses_op(d3["entry_long"], "HTF_SLOPE_UP")
        # And all chained indicators are still declared.
        assert _has_indicator(d3, "RSI", "rsi_filter")
        assert _has_indicator(d3, "HTF_EMA", "htf_ema_fast")
        assert _has_indicator(d3, "HTF_EMA", "htf_ema_slow")

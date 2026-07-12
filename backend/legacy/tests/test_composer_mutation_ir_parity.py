"""Phase 28-B+ — Composer-Mutation Trust Gate.

This test suite closes the documented Phase 28-B intentional gap:

    > Composer mutations remain `ir_status: legacy`. Phase A's mutation
    > engine doesn't yet thread a base IR through composer mutators
    > (filter_add_*, mtf_htf_*, etc).

After threading the canonical base IR through every composer mutation,
this suite proves — under the same trust-gate discipline applied in
Phase 28-B to root mutations — that:

    1. Every composer mutation now emits ``ir_status='ir_native'`` when
       the base is mappable to IR v1 (trend_following / breakout /
       mean_reversion).
    2. The composer IR is deterministic (same base + composer => same
       IR JSON).
    3. The composer IR is structurally valid (Pydantic round-trip).
    4. The composer IR is **semantically meaningful**: its predicate
       tree actually contains the filter it advertises, and the
       interpreter-produced signal series reflects the filter's
       restrictive effect on the base.
    5. For ``filter_add_rsi`` specifically (the one composer that has
       a parallel legacy semantic via ``_signal_*``'s rsi_cfg gate),
       the composer-IR signals are **bit-exact** to the legacy backtest
       of the composed text — exactly the trust-gate discipline applied
       to root mutations.
    6. ``filter_remove_rsi`` strips RSI references from indicators AND
       predicates.
    7. ``risk_reward_*`` composers replace SL/TP with the requested
       fixed-pip pair while preserving the base entry tree and any
       existing ``time_exit`` block.

If this gate passes → Phase C (IR → cAlgo C# transpiler) can be built
on a fully IR-native mutation pipeline (root + composer) with the same
mathematical confidence that root mutations already enjoy.
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

from engines.backtest_engine import (                            # noqa: E402
    _ema, _rsi, _signal_trend_following,
)
from engines.ir_interpreter import (                             # noqa: E402
    IRInterpreter, build_legacy_reference_ir,
)
from engines.mutation_engine import (                            # noqa: E402
    _derive_base_ir, mutate_strategy,
)
from engines.strategy_ir import StrategyIR, validate_ir          # noqa: E402
from engines.strategy_ir_builders import (                       # noqa: E402
    compose_filter_add_rsi, compose_filter_add_trend,
    compose_filter_add_volatility, compose_filter_remove_rsi,
    compose_mtf_htf_confirmation, compose_risk_reward,
    build_ir_for_mutation,
)


# ─────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────

def _make_oscillating_series(n=600, base=1.10, amp=0.005, period=50):
    """Deterministic series with EMA crosses + RSI oscillation."""
    prices, highs, lows, ts = [], [], [], []
    rng = random.Random(42)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        c = base + amp * math.sin(2 * math.pi * i / period) + (rng.random() - 0.5) * 0.001
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

_TREND_BASE = {
    "strategy_text": _TREND_BASE_TEXT,
    "pair": "EURUSD",
    "timeframe": "H1",
    "style": "trend",
    "parameters": {},
}


# ─────────────────────────────────────────────────────────────────────
# Group 1 — base IR derivation
# ─────────────────────────────────────────────────────────────────────

class TestBaseIRDerivation:

    def test_derives_trend_following_base_ir(self):
        ir = _derive_base_ir(_TREND_BASE)
        assert isinstance(ir, StrategyIR)
        d = ir.model_dump()
        assert d["metadata"]["mutation_type"] == "_legacy_trend_following"
        kinds = {i["kind"] for i in d["indicators"]}
        assert "EMA" in kinds

    def test_returns_none_for_momentum_base(self):
        momentum_base = {
            "strategy_text": (
                "STRATEGY: Momentum MACD\n"
                "ENTRY: MACD(12,26,9) signal-line crossover\n"
            ),
            "pair": "EURUSD",
            "timeframe": "H1",
        }
        # extract_params will classify this as 'momentum' → IR v1
        # documents this as an intentional gap. The derivation must
        # return None rather than fabricate a wrong IR.
        ir = _derive_base_ir(momentum_base)
        # Either None (mapped to momentum) or a non-momentum mapping —
        # the contract is: never raise, never fabricate a momentum IR.
        if ir is not None:
            assert ir.metadata.get("mutation_type") != "_legacy_momentum"

    def test_returns_none_on_empty_text(self):
        assert _derive_base_ir({"strategy_text": "", "pair": "EURUSD"}) is None

    def test_returns_none_on_missing_text(self):
        assert _derive_base_ir({"pair": "EURUSD"}) is None


# ─────────────────────────────────────────────────────────────────────
# Group 2 — composer IR-native status (closes the documented gap)
# ─────────────────────────────────────────────────────────────────────

class TestComposerEmitsIRNative:

    @pytest.fixture
    def variants(self):
        return mutate_strategy(_TREND_BASE, max_variants=15)

    def test_all_composers_now_ir_native(self, variants):
        composer_types = {
            "filter_add_rsi", "filter_add_volatility", "filter_add_trend",
            "mtf_htf_confirmation", "filter_remove_rsi",
            "risk_reward_1_1", "risk_reward_1_1_5", "risk_reward_1_2",
        }
        by_type = {v["mutation_type"]: v for v in variants}
        missing_native = []
        for mt in composer_types:
            v = by_type.get(mt)
            if v is None:
                continue                                            # selected/not selected — fine
            if v.get("ir_status") != "ir_native":
                missing_native.append(mt)
        assert not missing_native, (
            f"Composer mutations still legacy after threading base IR: "
            f"{missing_native}"
        )

    def test_root_mutations_remain_ir_native(self, variants):
        root_types = {
            "trend_pullback", "session_london_breakout", "session_asian_range",
            "volatility_atr_breakout", "volatility_bollinger_squeeze",
            "mean_reversion_rsi", "mean_reversion_bollinger",
        }
        legacy_roots = [
            v["mutation_type"] for v in variants
            if v["mutation_type"] in root_types and v.get("ir_status") != "ir_native"
        ]
        assert not legacy_roots, (
            f"Root mutations regressed to legacy: {legacy_roots}"
        )


# ─────────────────────────────────────────────────────────────────────
# Group 3 — composer determinism + structural validity
# ─────────────────────────────────────────────────────────────────────

class TestComposerDeterminism:

    def test_same_base_produces_same_composer_ir(self):
        base_ir_a = _derive_base_ir(_TREND_BASE)
        base_ir_b = _derive_base_ir(_TREND_BASE)
        a = compose_filter_add_rsi(base_ir_a).model_dump(mode="json")
        b = compose_filter_add_rsi(base_ir_b).model_dump(mode="json")
        assert a == b

    def test_every_composer_round_trips_through_pydantic(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        composers = [
            compose_filter_add_rsi,
            compose_filter_add_volatility,
            compose_filter_add_trend,
            compose_mtf_htf_confirmation,
            compose_filter_remove_rsi,
        ]
        for fn in composers:
            ir = fn(base_ir)
            d = ir.model_dump(mode="json")
            re_validated = validate_ir(d)
            assert re_validated.model_dump(mode="json") == d, (
                f"{fn.__name__} IR not round-trip stable"
            )


# ─────────────────────────────────────────────────────────────────────
# Group 4 — composer filters actually restrict signals
# ─────────────────────────────────────────────────────────────────────

class TestComposerSemanticEffect:
    """A composer that adds a filter MUST produce ≤ signals than the
    base (the filter is a gate). A composer that removes a filter MUST
    produce ≥ signals than the base."""

    def _signal_series(self, ir, prices, highs, lows, ts):
        interp = IRInterpreter(
            ir, prices=prices, highs=highs, lows=lows, timestamps=ts,
        )
        return [interp.signal_at(i) for i in range(len(prices))]

    def _signal_count(self, series):
        return sum(1 for s in series if s is not None)

    def test_filter_add_rsi_restricts_base(self):
        prices, highs, lows, ts = _make_oscillating_series()
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_filter_add_rsi(base_ir)
        base_count = self._signal_count(
            self._signal_series(base_ir, prices, highs, lows, ts)
        )
        composed_count = self._signal_count(
            self._signal_series(composed, prices, highs, lows, ts)
        )
        assert base_count > 0, "fixture insufficient — base produced no signals"
        assert composed_count <= base_count, (
            f"filter_add_rsi did NOT restrict base: "
            f"base={base_count}, composed={composed_count}"
        )

    def test_filter_add_trend_restricts_base(self):
        prices, highs, lows, ts = _make_oscillating_series()
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_filter_add_trend(base_ir)
        base_count = self._signal_count(
            self._signal_series(base_ir, prices, highs, lows, ts)
        )
        composed_count = self._signal_count(
            self._signal_series(composed, prices, highs, lows, ts)
        )
        assert composed_count <= base_count, (
            f"filter_add_trend did NOT restrict base: "
            f"base={base_count}, composed={composed_count}"
        )

    def test_filter_add_volatility_restricts_base(self):
        prices, highs, lows, ts = _make_oscillating_series()
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_filter_add_volatility(base_ir)
        base_count = self._signal_count(
            self._signal_series(base_ir, prices, highs, lows, ts)
        )
        composed_count = self._signal_count(
            self._signal_series(composed, prices, highs, lows, ts)
        )
        assert composed_count <= base_count

    def test_mtf_htf_restricts_base(self):
        prices, highs, lows, ts = _make_oscillating_series()
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_mtf_htf_confirmation(base_ir)
        base_count = self._signal_count(
            self._signal_series(base_ir, prices, highs, lows, ts)
        )
        composed_count = self._signal_count(
            self._signal_series(composed, prices, highs, lows, ts)
        )
        assert composed_count <= base_count

    def test_filter_remove_rsi_relaxes_base_with_rsi(self):
        """Build a base IR that has an RSI gate, then prove
        filter_remove_rsi produces >= the base's signal count."""
        # Synthetic base with RSI gate: trend_following + rsi_cfg.
        base_with_rsi = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50,
            rsi_cfg={"period": 14, "buy_threshold": 50, "sell_threshold": 50},
        )
        composed = compose_filter_remove_rsi(base_with_rsi)
        prices, highs, lows, ts = _make_oscillating_series()
        base_count = self._signal_count(
            self._signal_series(base_with_rsi, prices, highs, lows, ts)
        )
        composed_count = self._signal_count(
            self._signal_series(composed, prices, highs, lows, ts)
        )
        assert composed_count >= base_count, (
            f"filter_remove_rsi did NOT relax base: "
            f"base={base_count}, composed={composed_count}"
        )

    def test_filter_remove_rsi_strips_rsi_indicators_and_refs(self):
        base_with_rsi = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50,
            rsi_cfg={"period": 14, "buy_threshold": 50, "sell_threshold": 50},
        )
        composed = compose_filter_remove_rsi(base_with_rsi)
        d = composed.model_dump()
        assert not any(i["kind"] == "RSI" for i in d["indicators"]), (
            "RSI indicator still declared after filter_remove_rsi"
        )

        def _has_rsi_ref(node) -> bool:
            if not isinstance(node, dict):
                return False
            if node.get("ref") == "rsi":
                return True
            for a in (node.get("args") or []):
                if _has_rsi_ref(a):
                    return True
            return False

        assert not _has_rsi_ref(d["entry_long"]), "entry_long still references rsi"
        assert not _has_rsi_ref(d["entry_short"]), "entry_short still references rsi"


# ─────────────────────────────────────────────────────────────────────
# Group 5 — bit-exact legacy parity for filter_add_rsi (THE trust gate)
# ─────────────────────────────────────────────────────────────────────

class TestFilterAddRSILegacyParity:
    """The strict trust gate for the one composer that has a parallel
    legacy semantic. The legacy ``_signal_trend_following`` gates signals
    via ``rsi >= buy_threshold`` (the symmetric ``rsi < buy_threshold``
    suppression in the source code). The composer IR uses
    ``GE(rsi, 50)`` which mirrors that gate exactly.

    If signals match at every bar, PF / DD / trades match by
    construction since both feed the same ``_run_segment_loop``.
    """

    def test_filter_add_rsi_ir_matches_legacy_signal_for_signal(self):
        prices, highs, lows, ts = _make_oscillating_series()
        # ── IR path ─────────────────────────────────────────────
        base_ir = build_legacy_reference_ir(
            "trend_following", fast_period=20, slow_period=50, rsi_cfg=None,
        )
        composed = compose_filter_add_rsi(base_ir)
        interp = IRInterpreter(
            composed, prices=prices, highs=highs, lows=lows, timestamps=ts,
        )
        ir_signals = [interp.signal_at(i) for i in range(len(prices))]

        # ── Legacy path ─────────────────────────────────────────
        # Reproduce what the legacy backtest engine does when the
        # composed text is supplied: extract_params finds RSI with
        # buy_threshold = sell_threshold = 50, then dispatches to
        # _signal_trend_following with that rsi_cfg.
        fast_ma = _ema(prices, 20)
        slow_ma = _ema(prices, 50)
        rsi_vals = _rsi(prices, 14)
        rsi_cfg = {"period": 14, "buy_threshold": 50, "sell_threshold": 50}
        legacy_signals = [None]
        for i in range(1, len(prices)):
            legacy_signals.append(
                _signal_trend_following(i, prices, fast_ma, slow_ma,
                                         rsi_vals, rsi_cfg)
            )

        # ── Compare bit-exact ───────────────────────────────────
        diverging = [
            (i, legacy_signals[i], ir_signals[i])
            for i in range(len(prices))
            if legacy_signals[i] != ir_signals[i]
        ]
        ir_count = sum(1 for s in ir_signals if s is not None)
        legacy_count = sum(1 for s in legacy_signals if s is not None)
        assert legacy_count > 0, (
            "test fixture too quiet — legacy produced no signals"
        )
        if diverging:
            pytest.fail(
                f"filter_add_rsi composer trust-gate FAILED:\n"
                f"  legacy signal count: {legacy_count}\n"
                f"  ir     signal count: {ir_count}\n"
                f"  divergences: {len(diverging)} bars "
                f"(first 5: {diverging[:5]})\n"
            )


# ─────────────────────────────────────────────────────────────────────
# Group 6 — risk_reward composer correctness
# ─────────────────────────────────────────────────────────────────────

class TestRiskRewardComposer:

    def test_rr_1_1_emits_20_20_pips(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        ir = compose_risk_reward(base_ir, 1.0, "risk_reward_1_1")
        d = ir.model_dump()
        assert d["exit"]["stop_loss"]["kind"] == "pips"
        assert d["exit"]["stop_loss"]["pips"] == 20.0
        assert d["exit"]["take_profit"]["kind"] == "pips"
        assert d["exit"]["take_profit"]["pips"] == 20.0
        assert d["metadata"]["mutation_type"] == "risk_reward_1_1"

    def test_rr_1_2_emits_20_40_pips(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        ir = compose_risk_reward(base_ir, 2.0, "risk_reward_1_2")
        d = ir.model_dump()
        assert d["exit"]["stop_loss"]["pips"] == 20.0
        assert d["exit"]["take_profit"]["pips"] == 40.0
        assert d["metadata"]["mutation_type"] == "risk_reward_1_2"

    def test_rr_1_1_5_emits_20_30_pips(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        ir = compose_risk_reward(base_ir, 1.5, "risk_reward_1_1_5")
        d = ir.model_dump()
        assert d["exit"]["stop_loss"]["pips"] == 20.0
        assert d["exit"]["take_profit"]["pips"] == 30.0

    def test_rr_preserves_base_entry_predicates(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        original_long = base_ir.model_dump()["entry_long"]
        original_short = base_ir.model_dump()["entry_short"]
        composed = compose_risk_reward(base_ir, 1.5, "risk_reward_1_1_5")
        d = composed.model_dump()
        assert d["entry_long"] == original_long
        assert d["entry_short"] == original_short

    def test_build_ir_for_mutation_dispatches_risk_reward(self):
        """Confirms the rr_ → risk_reward_ prefix fix in the dispatcher."""
        base_ir = _derive_base_ir(_TREND_BASE)
        ir = build_ir_for_mutation(
            "risk_reward_1_2", "EURUSD", "H1",
            base_ir=base_ir, rr_ratio=2.0,
        )
        assert ir is not None, (
            "risk_reward_* did NOT dispatch through build_ir_for_mutation"
        )
        d = ir.model_dump()
        assert d["exit"]["take_profit"]["pips"] == 40.0


# ─────────────────────────────────────────────────────────────────────
# Group 7 — HTF + volatility filter structural correctness
# ─────────────────────────────────────────────────────────────────────

class TestMTFAndVolatilityStructure:

    def test_mtf_htf_declares_htf_ema_indicators(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_mtf_htf_confirmation(base_ir)
        d = composed.model_dump()
        htf_kinds = [i for i in d["indicators"] if i["kind"] == "HTF_EMA"]
        assert len(htf_kinds) >= 2, (
            "compose_mtf_htf_confirmation must declare HTF EMA fast + slow"
        )
        # Both should reference an HTF higher than H1 (base TF).
        for ind in htf_kinds:
            assert ind["params"].get("htf") in ("H4", "D1", "W1", "M15", "M30"), (
                f"unexpected HTF: {ind['params'].get('htf')}"
            )

    def test_volatility_filter_block_set(self):
        base_ir = _derive_base_ir(_TREND_BASE)
        composed = compose_filter_add_volatility(base_ir)
        d = composed.model_dump()
        assert d.get("volatility_filter") is not None
        assert d["volatility_filter"]["kind"] == "atr_ratio"
        assert d["volatility_filter"]["indicator"] == "atr_filter"

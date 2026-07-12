"""
P1.4 — Tests for engines.htf_parity (dormant HTF parity validator).

Five tiers, mirroring the discipline used by P0.4 / P1.2 / P1.6:

  Tier 1 — Dormancy contract: no production engine imports the module.
  Tier 2 — Pure helpers (timeframe map, IR introspection, aggregation).
  Tier 3 — Validator NOT_APPLICABLE branch + signal-summary shape.
  Tier 4 — End-to-end divergence reporting on a synthetic HTF IR.
  Tier 5 — Feature-flag manifest integration.

Discipline:
  * Pure tests; no Mongo writes, no LLM, no network.
  * Synthetic fixtures only — deterministic, repeatable.
  * The dormancy test (Tier 1) is the institutional gate that
    prevents drive-by activation. Any new production import of
    ``engines.htf_parity`` must update the whitelist in the same PR.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Dormancy contract
# ─────────────────────────────────────────────────────────────────────
class TestDormancy:
    """Institutional invariant: no module under ``backend/engines/``
    may import ``engines.htf_parity`` until a separately-reviewed
    wiring pass updates the whitelist below.
    """

    _AUTHORIZED_IMPORTERS: set = set()  # empty: P1.4 is fully dormant

    def test_no_engine_consumer(self):
        """Grep the engines/ tree for actual imports of htf_parity.

        Allowed:
          * the module itself (``engines/htf_parity.py``)
          * the test bundle (``backend/tests/``)
          * the latent endpoint (``backend/api/latent/htf_parity.py``)
        """
        backend = Path(__file__).resolve().parent.parent
        engines_dir = backend / "engines"
        offenders: List[str] = []
        for py in engines_dir.rglob("*.py"):
            if py.name == "htf_parity.py":
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "from engines.htf_parity" in stripped
                    or "import engines.htf_parity" in stripped
                ):
                    rel = str(py.relative_to(backend))
                    if rel not in self._AUTHORIZED_IMPORTERS:
                        offenders.append(rel)
                        break
        assert not offenders, (
            f"P1.4 dormancy violated — engines/ imports htf_parity in: "
            f"{offenders}. Update _AUTHORIZED_IMPORTERS only via a "
            "reviewed wiring pass."
        )

    def test_default_flag_is_off(self):
        # Force a clean read regardless of host env.
        prior = os.environ.pop("ENABLE_HTF_PARITY_VALIDATION", None)
        try:
            from engines.htf_parity import is_enabled
            assert is_enabled() is False
        finally:
            if prior is not None:
                os.environ["ENABLE_HTF_PARITY_VALIDATION"] = prior

    def test_flag_truthy_values(self):
        from engines.htf_parity import is_enabled
        for v in ("true", "TRUE", "1", "yes", "on"):
            os.environ["ENABLE_HTF_PARITY_VALIDATION"] = v
            try:
                assert is_enabled() is True, f"expected truthy for {v!r}"
            finally:
                os.environ.pop("ENABLE_HTF_PARITY_VALIDATION", None)


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Pure helpers
# ─────────────────────────────────────────────────────────────────────
class TestPureHelpers:
    def test_htf_for_known(self):
        from engines.htf_parity import htf_for
        assert htf_for("H1") == ("H4", 4)
        assert htf_for("M15") == ("H1", 4)
        assert htf_for("D1") == ("W1", 5)

    def test_htf_for_unknown_returns_none(self):
        from engines.htf_parity import htf_for
        assert htf_for("Q1") is None
        assert htf_for("") is None

    def test_is_htf_ir(self):
        from engines.htf_parity import is_htf_ir
        non_htf = {"indicators": [{"id": "ema", "kind": "EMA",
                                    "params": {"period": 20}}]}
        htf = {"indicators": [
            {"id": "h",  "kind": "HTF_EMA", "params": {"period": 50}},
        ]}
        assert is_htf_ir(non_htf) is False
        assert is_htf_ir(htf) is True

    def test_aggregate_htf_closes_basic(self):
        from engines.htf_parity import aggregate_htf_closes
        # 8 H1 bars → expect 2 complete H4 bars (the last 4 bars are
        # still open at the moment of bar 7).
        base = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        ts = [base + timedelta(hours=h) for h in range(8)]
        prices = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        out = aggregate_htf_closes(prices, ts, ltf="H1", htf="H4")
        # Bars 0..3 still inside bucket 0 → no closed HTF yet
        assert out[0] is None
        assert out[3] is None
        # Bars 4..7 sit in bucket 1; bucket 0's final close (4.0) is
        # now visible.
        for i in range(4, 8):
            assert out[i] == 4.0

    def test_aggregate_htf_closes_empty(self):
        from engines.htf_parity import aggregate_htf_closes
        assert aggregate_htf_closes([], [], ltf="H1", htf="H4") == []

    def test_true_htf_ema_series_shape(self):
        from engines.htf_parity import true_htf_ema_series
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ts = [base + timedelta(hours=h) for h in range(80)]
        prices = [1.0 + 0.001 * h for h in range(80)]
        out = true_htf_ema_series(prices, ts, ltf="H1", htf="H4", period=5)
        assert len(out) == len(prices)
        # Leading bars must be None (warmup before first closed HTF bar);
        # late bars must be float once EMA warmup completes.
        assert out[0] is None
        assert any(v is not None for v in out[40:])


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Validator NOT_APPLICABLE + ERROR branches
# ─────────────────────────────────────────────────────────────────────
def _non_htf_ir() -> Dict[str, Any]:
    """A trend-following IR with no HTF dependency — parity is
    trivially exact.
    """
    return {
        "ir_version": 1,
        "metadata":   {"name": "NonHtfRef", "pair": "EURUSD",
                       "timeframe": "H1", "mutation_type": "_legacy_trend_following"},
        "indicators": [
            {"id": "ema_fast", "kind": "EMA", "params": {"period": 5}},
            {"id": "ema_slow", "kind": "EMA", "params": {"period": 20}},
        ],
        "entry_long":  {"op": "CROSS_UP",
                        "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}]},
        "entry_short": {"op": "CROSS_DOWN",
                        "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}]},
        "exit": {"stop_loss":  {"kind": "pips", "pips": 20.0},
                  "take_profit": {"kind": "pips", "pips": 40.0}},
    }


def _htf_ir() -> Dict[str, Any]:
    """An IR that uses HTF_SLOPE_UP/DOWN — the only HTF predicate the
    v1 transpiler emits and the validator targets.
    """
    return {
        "ir_version": 1,
        "metadata":   {"name": "HtfRef", "pair": "EURUSD",
                       "timeframe": "H1", "mutation_type": "_htf_trend"},
        "indicators": [
            {"id": "htf_fast", "kind": "HTF_EMA",
             "params": {"period": 8, "htf": "H4"}},
            {"id": "htf_slow", "kind": "HTF_EMA",
             "params": {"period": 21, "htf": "H4"}},
        ],
        "entry_long":  {"op": "HTF_SLOPE_UP",   "args": [],
                        "htf_ema_fast": "htf_fast",
                        "htf_ema_slow": "htf_slow"},
        "entry_short": {"op": "HTF_SLOPE_DOWN", "args": [],
                        "htf_ema_fast": "htf_fast",
                        "htf_ema_slow": "htf_slow"},
        "exit": {"stop_loss":  {"kind": "pips", "pips": 20.0},
                  "take_profit": {"kind": "pips", "pips": 40.0}},
    }


def _make_h1_fixture(n: int = 200, seed: int = 1):
    """Deterministic synthetic H1 fixture. Sine-wave-with-drift so
    HTF EMA series have meaningful slope flips.
    """
    import math
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ts = [base + timedelta(hours=h) for h in range(n)]
    prices = []
    for h in range(n):
        x = (1.1
             + 0.05 * math.sin(h / 8.0)
             + 0.02 * math.sin(h / 31.0 + 0.7 * seed)
             + 0.0005 * h)
        prices.append(round(x, 6))
    highs = [p + 0.0008 for p in prices]
    lows = [p - 0.0008 for p in prices]
    return prices, highs, lows, ts


class TestValidatorContract:
    def test_not_applicable_when_ir_has_no_htf(self):
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture()
        r = validate_htf_parity(
            _non_htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="H1",
        )
        assert r["verdict"] == "NOT_APPLICABLE"
        assert r["htf_present"] is False
        assert r["advisory_only"] is True

    def test_error_on_length_mismatch(self):
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture()
        r = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs[:-1], lows=lows, timestamps=ts,
            strategy_timeframe="H1",
        )
        assert r["verdict"] == "ERROR"
        assert "length mismatch" in (r.get("details") or "")

    def test_error_on_missing_timestamps(self):
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, _ts = _make_h1_fixture()
        r = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=[],
            strategy_timeframe="H1",
        )
        assert r["verdict"] == "ERROR"
        assert "timestamps" in (r.get("details") or "")

    def test_error_on_unknown_timeframe(self):
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture()
        r = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="Q1",
        )
        assert r["verdict"] == "ERROR"


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — End-to-end divergence quantification
# ─────────────────────────────────────────────────────────────────────
class TestDivergenceReporting:
    def test_htf_validator_runs_end_to_end(self):
        """On a realistic HTF IR + synthetic fixture, the validator
        returns a structured verdict in the allowed vocabulary.
        """
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture(n=400, seed=3)
        r = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="H1",
            tolerance_pct=10.0,
        )
        assert r["verdict"] in ("EXACT", "WITHIN_TOLERANCE", "DIVERGENT")
        assert r["htf_present"] is True
        assert r["ltf"] == "H1"
        assert r["htf"] == "H4"
        assert r["compared_bars"] == len(prices)
        assert 0 <= r["diverging_bars"] <= r["compared_bars"]
        assert 0.0 <= r["divergence_pct"] <= 100.0
        # Signal summaries must be present and structurally consistent.
        for key in ("baseline_summary", "true_htf_summary"):
            s = r[key]
            assert {"long", "short", "none"} <= set(s.keys())
            assert s["long"] + s["short"] + s["none"] == r["compared_bars"]

    def test_tolerance_bands_separate_verdicts(self):
        """A tight tolerance pushes any non-zero divergence into
        DIVERGENT; a loose tolerance keeps it WITHIN_TOLERANCE.
        """
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture(n=400, seed=5)
        tight = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="H1",
            tolerance_pct=0.0,
        )
        loose = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="H1",
            tolerance_pct=100.0,
        )
        # If everything matches, both should be EXACT.
        if tight["diverging_bars"] == 0:
            assert tight["verdict"] == "EXACT"
            assert loose["verdict"] == "EXACT"
        else:
            assert tight["verdict"] == "DIVERGENT"
            assert loose["verdict"] in ("WITHIN_TOLERANCE", "EXACT")

    def test_dormant_field_reflects_flag(self):
        from engines.htf_parity import validate_htf_parity
        prices, highs, lows, ts = _make_h1_fixture(n=200)
        # OFF (default)
        os.environ.pop("ENABLE_HTF_PARITY_VALIDATION", None)
        r_off = validate_htf_parity(
            _htf_ir(),
            prices=prices, highs=highs, lows=lows, timestamps=ts,
            strategy_timeframe="H1",
        )
        assert r_off["dormant"] is True
        # ON
        os.environ["ENABLE_HTF_PARITY_VALIDATION"] = "true"
        try:
            r_on = validate_htf_parity(
                _htf_ir(),
                prices=prices, highs=highs, lows=lows, timestamps=ts,
                strategy_timeframe="H1",
            )
            assert r_on["dormant"] is False
            # Activation must NOT change the verdict — the validator
            # is a pure function of inputs.
            assert r_on["verdict"] == r_off["verdict"]
            assert r_on["compared_bars"] == r_off["compared_bars"]
            assert r_on["diverging_bars"] == r_off["diverging_bars"]
        finally:
            os.environ.pop("ENABLE_HTF_PARITY_VALIDATION", None)


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — Feature-flag manifest integration
# ─────────────────────────────────────────────────────────────────────
class TestFeatureFlagManifest:
    def test_flags_registered(self):
        from engines.feature_flags import all_flags
        snapshot = all_flags()
        assert "ENABLE_HTF_PARITY_VALIDATION" in snapshot
        assert "HTF_PARITY_MAX_DIVERGENCE_PCT" in snapshot

    def test_flag_scope_is_htf_parity(self):
        from engines.feature_flags import scope_index
        idx = scope_index()
        assert "htf_parity" in idx
        assert "ENABLE_HTF_PARITY_VALIDATION" in idx["htf_parity"]
        assert "HTF_PARITY_MAX_DIVERGENCE_PCT" in idx["htf_parity"]

    def test_defaults_are_dormant(self):
        from engines.feature_flags import all_flags
        snap = all_flags()
        assert snap["ENABLE_HTF_PARITY_VALIDATION"]["default"] is False
        assert snap["ENABLE_HTF_PARITY_VALIDATION"]["is_dormant"] is True
        assert snap["HTF_PARITY_MAX_DIVERGENCE_PCT"]["default"] == 5.0


if __name__ == "__main__":   # pragma: no cover
    pytest.main([__file__, "-v"])

"""
P0.4 — Tests for the dormant cBot trade-lifecycle parity module.

Scope (institutional discipline — no expansion beyond P0.4):

    1. The module imports cleanly.
    2. ``is_enabled()`` is False by default (env-flag dormant).
    3. ``simulate_trades(...)`` is callable WHILE THE FLAG IS OFF (the
       function is pure — the flag only governs whether any production
       call-site CONSULTS it, not whether the function itself can be
       called by tests/operators).
    4. The simulator is deterministic — same inputs → bit-identical
       trade list across repeat invocations.
    5. The simulator never crashes on the canonical fixture used by
       the signal-parity trust gate.
    6. ``compare_trade_series`` returns PASSED when a simulator output
       is compared against itself (the lower-bound property — the only
       guarantee we can make without a second execution path).
    7. The simulator's signal source agrees with
       ``simulate_cbot_signals`` — i.e. it does not introduce a
       second, divergent signal generator.
    8. **Dormancy / no-behavior-drift invariant**: NO production code
       path imports ``engines.cbot_trade_parity``. (Tested
       statically by grep — failure here would mean the module has
       been wired in without re-opening P0.4 for review.)

These tests intentionally use the same _TREND_TEXT fixture as
``test_cbot_ir_transpiler.py`` so the IR and price series are
exercised by both signal-parity and trade-parity in identical shape.
"""
from __future__ import annotations

import math
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from cbot_engine.ir_parity_simulator import simulate_cbot_signals  # noqa: E402
from engines import cbot_trade_parity as TP                         # noqa: E402
from engines.mutation_engine import _derive_base_ir                 # noqa: E402


_TREND_TEXT = (
    "STRATEGY: Base Trend (EURUSD H1)\n"
    "ENTRY LONG:  EMA(20) crosses above EMA(50)\n"
    "ENTRY SHORT: EMA(20) crosses below EMA(50)\n"
    "EXIT: SL = 20 pips  |  TP = 40 pips\n"
)


def _ir():
    return _derive_base_ir({
        "strategy_text": _TREND_TEXT,
        "pair":          "EURUSD",
        "timeframe":     "H1",
    })


def _series(n: int = 400, seed: int = 42):
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


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — dormancy
# ─────────────────────────────────────────────────────────────────────
class TestDormancy:

    def test_module_imports(self):
        # Module-level import already happened at the top of the file.
        assert hasattr(TP, "simulate_trades")
        assert hasattr(TP, "compare_trade_series")
        assert hasattr(TP, "is_enabled")

    def test_flag_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_CBOT_TRADE_PARITY", raising=False)
        assert TP.is_enabled() is False

    def test_flag_respects_env_override(self, monkeypatch):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        assert TP.is_enabled() is True
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "false")
        assert TP.is_enabled() is False

    def test_first_n_respects_env(self, monkeypatch):
        monkeypatch.setenv("CBOT_TRADE_PARITY_FIRST_N", "12")
        assert TP.first_n_default() == 12
        monkeypatch.delenv("CBOT_TRADE_PARITY_FIRST_N", raising=False)
        assert TP.first_n_default() == 50

    def test_first_n_malformed_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CBOT_TRADE_PARITY_FIRST_N", "not-an-int")
        assert TP.first_n_default() == 50

    def test_no_production_caller(self):
        """The dormancy contract requires that the ONLY production
        module importing ``engines.cbot_trade_parity`` is the
        operator-approved P1.3 wiring site
        (``engines/cbot_parity.py::sign_off_parity``). Any *other*
        production importer means the module has been wired in
        without re-opening P1.3 for institutional review.

        The feature_flags manifest mentions the module by NAME in the
        ``intent`` docstring (e.g. "consumed only by
        engines.cbot_trade_parity") — that is documentation, not an
        importer, and is excluded.
        """
        backend_root = Path(_BACKEND)
        # Match actual import statements, not free-text manifest mentions.
        cmd = [
            "grep", "-rEln",
            r"^[[:space:]]*(from|import)[[:space:]]+engines\.cbot_trade_parity",
            str(backend_root),
            "--include=*.py",
        ]
        out = subprocess.run(cmd, capture_output=True, text=True)
        # P1.3 — the ONLY production importer authorized by the
        # institutional record is `engines/cbot_parity.py`. The import
        # is wrapped in a flag-gated branch (`_trade_parity_enabled()`),
        # so its presence does NOT alter behaviour when the flag is OFF.
        authorized_importers = {"engines/cbot_parity.py"}
        hits = [
            line for line in out.stdout.splitlines()
            if line
            and "cbot_trade_parity" not in Path(line).name
            and "/tests/" not in line
            and "__pycache__" not in line
            and not any(line.endswith(a) for a in authorized_importers)
        ]
        assert hits == [], (
            "engines.cbot_trade_parity has unauthorized importers. "
            "Authorized: " + ", ".join(sorted(authorized_importers)) +
            "\nFound:\n  " + "\n  ".join(hits)
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — pip-size resolver
# ─────────────────────────────────────────────────────────────────────
class TestPipSize:

    def test_eurusd(self):
        assert TP.resolve_pip_size("EURUSD") == 0.0001

    def test_usdjpy(self):
        assert TP.resolve_pip_size("USDJPY") == 0.01

    def test_xauusd(self):
        assert TP.resolve_pip_size("XAUUSD") == 0.1

    def test_xagusd(self):
        assert TP.resolve_pip_size("XAGUSD") == 0.001

    def test_explicit_override_wins(self):
        assert TP.resolve_pip_size("USDJPY", override=0.123) == 0.123

    def test_unknown_pair_defaults(self):
        assert TP.resolve_pip_size("DOGEEUR") == 0.0001
        assert TP.resolve_pip_size(None) == 0.0001


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — simulator contract
# ─────────────────────────────────────────────────────────────────────
class TestSimulateTrades:

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            TP.simulate_trades(_ir(), prices=[1.1, 1.2], highs=[1.2], lows=[1.1])

    def test_runs_on_canonical_fixture(self):
        prices, highs, lows, ts = _series()
        report = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD",
        )
        assert "trades" in report
        assert "summary" in report
        assert "parity_inputs" in report
        # Dormant flag is OFF in the test env → report.dormant must be True.
        assert report["dormant"] is True
        assert report["parity_inputs"]["intrabar_mode"] == "worst_case"
        # Numbers must add up.
        s = report["summary"]
        assert s["total_trades"] == len(report["trades"])
        assert s["buy_count"] + s["sell_count"] == s["total_trades"]
        assert (
            s["sl_hits"] + s["tp_hits"] + s["open_at_end"]
            == s["total_trades"]
        )

    def test_deterministic(self):
        prices, highs, lows, ts = _series()
        a = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD",
        )
        b = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD",
        )
        assert a["trades"] == b["trades"]
        assert a["summary"] == b["summary"]

    def test_first_n_truncates(self):
        prices, highs, lows, ts = _series(n=600)
        full = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD", first_n=10,
        )
        assert full["summary"]["first_n"] == 10
        assert len(full["trades"]) <= 10

    def test_signal_source_is_the_canonical_one(self):
        """Trade parity MUST consume the same signal series the
        signal-parity simulator emits. This pins the invariant that
        trade-parity is a strict superset of signal-parity."""
        prices, highs, lows, ts = _series()
        sig = simulate_cbot_signals(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
        )
        trade_report = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD", first_n=10_000,
        )
        # Each trade's entry_bar must correspond to a BUY/SELL signal
        # on the PREVIOUS bar (next-bar-open convention).
        for t in trade_report["trades"]:
            entry_idx = t["entry_bar"]
            sig_idx = entry_idx - 1
            assert 0 <= sig_idx < len(sig["signals"])
            assert sig["signals"][sig_idx] == t["side"], (
                f"trade at entry_bar={entry_idx} side={t['side']} but "
                f"canonical signal at bar {sig_idx} = {sig['signals'][sig_idx]}"
            )


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — compare_trade_series
# ─────────────────────────────────────────────────────────────────────
class TestCompareTradeSeries:

    def test_both_empty_is_empty(self):
        v = TP.compare_trade_series([], [])
        assert v["verdict"] == "EMPTY"

    def test_self_compare_passes(self):
        prices, highs, lows, ts = _series()
        r = TP.simulate_trades(
            _ir(), prices=prices, highs=highs, lows=lows, timestamps=ts,
            pair="EURUSD",
        )
        v = TP.compare_trade_series(r["trades"], r["trades"])
        # If the simulator produced ZERO trades on this fixture the
        # verdict will be EMPTY (still legal — no divergence to flag).
        assert v["verdict"] in ("PASSED", "EMPTY")
        assert v["first_divergence"] is None

    def test_length_mismatch_flags_first_divergence(self):
        a = [{"side": "BUY", "entry_bar": 1, "exit_bar": 5,
              "entry_price": 1.1, "exit_reason": "TP"}]
        b: list = []
        v = TP.compare_trade_series(a, b)
        assert v["verdict"] == "MISMATCH"
        assert v["first_divergence"] == 0

    def test_side_mismatch_flagged(self):
        a = [{"side": "BUY", "entry_bar": 1, "exit_bar": 5,
              "entry_price": 1.1, "exit_reason": "TP"}]
        b = [{"side": "SELL", "entry_bar": 1, "exit_bar": 5,
              "entry_price": 1.1, "exit_reason": "TP"}]
        v = TP.compare_trade_series(a, b)
        assert v["verdict"] == "MISMATCH"
        assert "side" in v["reason"]

    def test_exit_reason_mismatch_flagged(self):
        a = [{"side": "BUY", "entry_bar": 1, "exit_bar": 5,
              "entry_price": 1.1, "exit_reason": "TP"}]
        b = [{"side": "BUY", "entry_bar": 1, "exit_bar": 5,
              "entry_price": 1.1, "exit_reason": "SL"}]
        v = TP.compare_trade_series(a, b)
        assert v["verdict"] == "MISMATCH"
        assert "exit_reason" in v["reason"]


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — feature-flag manifest integration
# ─────────────────────────────────────────────────────────────────────
class TestFeatureFlagManifestIntegration:

    def test_flags_registered(self):
        from engines.feature_flags import all_flags
        names = set(all_flags().keys())
        assert "ENABLE_CBOT_TRADE_PARITY" in names
        assert "CBOT_TRADE_PARITY_FIRST_N" in names

    def test_flag_default_is_dormant(self):
        from engines.feature_flags import all_flags
        flags = all_flags()
        spec = flags.get("ENABLE_CBOT_TRADE_PARITY")
        assert spec is not None, "ENABLE_CBOT_TRADE_PARITY missing from manifest"
        assert spec["default"] is False
        assert spec["kind"] == "bool"
        assert spec["is_dormant"] is True

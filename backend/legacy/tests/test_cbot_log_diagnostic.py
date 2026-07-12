"""
Pass 9 — Tests for the operator-side cBot log diagnostic.

This is the consumption-side closure for the "compiled but non-trading"
audit gap. The emission side (LogGate instrumentation in
``cbot_engine/ir_templates.py``) is verified by the existing scaffold
regression suite. These tests verify:

  * the regex matches BOTH emission formats (verbosity=1 and
    verbosity=2);
  * the verdict logic correctly classifies trading / dead_bot /
    log_empty / no_gates_seen;
  * every gate reason emitted by the scaffold has a recommendation
    entry (contract invariant);
  * sample-line capture is bounded by the operator-supplied cap.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines import cbot_log_diagnostic as DIAG  # noqa: E402


_VERBOSE_LINE = (
    "2026-01-04 10:00:00 [BotXYZ] [Gate] reason=spread "
    "bar_time=2026-01-04T10:00:00 spread_pips=2.30 owned=0 "
    "spread=2.30 > MaxSpreadPips=2.00"
)
_CONCISE_LINE = (
    "2026-01-04 10:00:00 [BotXYZ] [Gate] spread: "
    "spread=2.30 > MaxSpreadPips=2.00"
)
_TRADE_LINE = (
    "2026-01-04 10:05:00 [BotXYZ] ExecuteMarketOrder BUY 1000 EURUSD"
)


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — regex parity with the scaffold's actual emission format
# ─────────────────────────────────────────────────────────────────────
class TestRegexParity:

    def test_verbose_form_matches(self):
        report = DIAG.parse_log(_VERBOSE_LINE)
        assert report["gate_lines_found"] == 1
        assert report["by_reason"] == {"spread": 1}

    def test_concise_form_matches(self):
        report = DIAG.parse_log(_CONCISE_LINE)
        assert report["gate_lines_found"] == 1
        assert report["by_reason"] == {"spread": 1}

    def test_case_insensitivity(self):
        # cTrader Cloud sometimes uppercases marker tokens.
        report = DIAG.parse_log("[GATE] reason=Spread detail=foo")
        assert report["by_reason"] == {"spread": 1}

    def test_every_scaffold_reason_has_recommendation(self):
        """Contract invariant: every reason emitted by the scaffold
        MUST appear in the diagnostic's recommendation table.
        """
        scaffold_path = Path(_BACKEND) / "cbot_engine" / "ir_templates.py"
        src = scaffold_path.read_text()
        emitted = set(re.findall(r'LogGate\("([a-z_]+)"', src))
        # The diagnostic's recommendation keys MUST cover every emitted reason.
        rec_keys = set(DIAG.known_reasons())
        missing = emitted - rec_keys
        assert missing == set(), (
            "Scaffold emits gate reasons that the diagnostic doesn't "
            f"recognise: {sorted(missing)}. Add them to "
            "engines/cbot_log_diagnostic.py::_RECOMMENDATIONS."
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — verdict classification
# ─────────────────────────────────────────────────────────────────────
class TestVerdict:

    def test_empty_log(self):
        assert DIAG.parse_log("")["verdict"] == "log_empty"

    def test_no_gates_no_trades(self):
        report = DIAG.parse_log(
            "2026-01-04 10:00:00 starting...\n"
            "2026-01-04 10:00:01 warmup complete\n"
        )
        assert report["verdict"] == "no_gates_seen"
        assert "Enable LogVerbosity" in report["recommendation"]

    def test_dead_bot_identifies_top_blocker(self):
        text = "\n".join([_CONCISE_LINE] * 100)
        report = DIAG.parse_log(text)
        assert report["verdict"] == "dead_bot"
        assert report["top_blocker"] == "spread"
        assert report["top_blocker_pct"] == 100.0
        assert "MaxSpreadPips" in report["recommendation"]

    def test_trading_verdict_when_trades_present(self):
        text = "\n".join([_CONCISE_LINE, _TRADE_LINE, _CONCISE_LINE])
        report = DIAG.parse_log(text)
        assert report["verdict"] == "trading"
        assert report["trade_lines"] >= 1

    def test_mixed_gate_reasons_picks_dominant(self):
        text = "\n".join(
            [_CONCISE_LINE] * 60 +
            ["[Gate] volatility: ATR(14)=0.0001 < MinAtrPips=0.0005"] * 40
        )
        report = DIAG.parse_log(text)
        assert report["verdict"] == "dead_bot"
        assert report["top_blocker"] == "spread"
        assert report["top_blocker_pct"] == 60.0
        assert report["by_reason"] == {"spread": 60, "volatility": 40}


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — sample-line capture bounds
# ─────────────────────────────────────────────────────────────────────
class TestSampleLines:

    def test_default_cap_is_five(self):
        text = "\n".join([_CONCISE_LINE] * 100)
        report = DIAG.parse_log(text)
        assert len(report["sample_lines"]["spread"]) == 5

    def test_explicit_cap_respected(self):
        text = "\n".join([_CONCISE_LINE] * 100)
        report = DIAG.parse_log(text, max_sample_lines_per_reason=12)
        assert len(report["sample_lines"]["spread"]) == 12

    def test_cap_ceiling_is_fifty(self):
        text = "\n".join([_CONCISE_LINE] * 200)
        # Even a request for 9999 should clamp to 50.
        report = DIAG.parse_log(text, max_sample_lines_per_reason=9999)
        assert len(report["sample_lines"]["spread"]) == 50


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — operator workflow simulation
# ─────────────────────────────────────────────────────────────────────
class TestOperatorWorkflows:

    @pytest.mark.parametrize("reason,expected_token", [
        ("session",          "session_start_gmt"),
        ("volatility",       "MinAtrPips"),
        ("volume_min",       "VolumeInUnitsMin"),
        ("max_concurrent",   "single-position"),
        ("sl_tp_invalid",    "ATR"),
        ("symbol_metadata",  "market-universe"),
        ("daily_lockout",    "MaxDailyLossPct"),
        ("emergency_halt",   "EmergencyHalt"),
        ("cooldown",         "CoolDownBars"),
        ("max_trades_day",   "MaxTradesPerDay"),
    ])
    def test_recommendation_contains_actionable_token(
        self, reason, expected_token,
    ):
        # Hand-craft a dead-bot log with this reason as dominant.
        line = f"[Gate] {reason}: synthetic detail"
        report = DIAG.parse_log("\n".join([line] * 10))
        assert report["verdict"] == "dead_bot"
        assert report["top_blocker"] == reason
        assert expected_token in report["recommendation"]

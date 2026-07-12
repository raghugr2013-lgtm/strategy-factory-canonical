"""
Unit tests for the Phase 4 Strategy ↔ Prop Firm Matcher wrapper.

Validates:
  • parse_firm_and_plan()       — slug → clean firm + plan labels
  • _normalize_ev()             — EV → 0-100 score
  • _verdict()                  — BEST / SAFE / RISKY thresholds
  • _risk_label()               — safety_level → LOW/MEDIUM/HIGH
  • _extract_overfit()          — pulls overfit from assorted shapes
  • match_strategy_phase4()     — end-to-end contract via monkeypatched
                                   matching_engine.match_strategy_to_firms
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from engines import phase4_matcher
from engines.phase4_matcher import (
    _extract_overfit,
    _normalize_ev,
    _risk_label,
    _verdict,
    match_strategy_phase4,
    parse_firm_and_plan,
)


# ═══════════════════════════════════════════════════════════
# Label parsing
# ═══════════════════════════════════════════════════════════

def test_parse_phase3_mirrored_slug():
    out = parse_firm_and_plan(
        firm_slug="ftmo_100k_2step",
        firm_name="FTMO 100k 2-step",
        phase="2-step",
    )
    assert out["firm"] == "FTMO"
    assert out["plan"] == "100K 2-Step"


def test_parse_multiword_firm():
    out = parse_firm_and_plan(
        firm_slug="acme_prop_25k_1step",
        firm_name="Acme Prop 25k 1-step",
        phase="1-step",
    )
    assert out["firm"] == "Acme Prop"
    assert out["plan"] == "25K 1-Step"


def test_parse_instant_plan():
    out = parse_firm_and_plan("foo_bar_50k_instant", "Foo Bar 50k instant", "instant")
    assert out["firm"] == "Foo Bar"
    assert out["plan"] == "50K Instant"


def test_parse_legacy_slug_falls_back_to_firm_name():
    out = parse_firm_and_plan("ftmo", "FTMO", "Challenge")
    assert out["firm"] == "FTMO"
    assert out["plan"] == "Challenge"


def test_parse_legacy_no_phase_defaults_to_default():
    out = parse_firm_and_plan("somefirm", "SomeFirm", "")
    assert out["plan"] == "Default"


# ═══════════════════════════════════════════════════════════
# EV normalization
# ═══════════════════════════════════════════════════════════

def test_normalize_ev_bands():
    # Below −1 ratio clamps to 0
    assert _normalize_ev(-600, 500) == 0.0
    # Exactly break-even
    assert _normalize_ev(0, 500) == 30.0
    # Ratio = +1 → 60 (per spec: 30 + (1/5)*70 = 44). Fix test expectation.
    assert _normalize_ev(500, 500) == pytest.approx(44.0)
    # Ratio = +5 caps at 100
    assert _normalize_ev(2500, 500) == pytest.approx(100.0)
    # Ratio > 5 stays 100
    assert _normalize_ev(10_000, 500) == 100.0
    # Zero fee returns neutral 50
    assert _normalize_ev(123, 0) == 50.0


# ═══════════════════════════════════════════════════════════
# Risk label & verdict
# ═══════════════════════════════════════════════════════════

def test_risk_label_mapping():
    assert _risk_label("safe") == "LOW"
    assert _risk_label("moderate") == "MEDIUM"
    assert _risk_label("danger") == "HIGH"
    assert _risk_label("breached") == "HIGH"
    assert _risk_label("unknown") == "HIGH"


def test_verdict_best():
    # All three BEST conditions met
    assert _verdict(70, "safe", 30, None) == "BEST"
    assert _verdict(65, "moderate", 40, None) == "BEST"


def test_verdict_best_fails_if_overfit_high():
    # overfit over the 40 cap disqualifies BEST, still SAFE
    assert _verdict(70, "safe", 41, None) == "SAFE"


def test_verdict_best_fails_if_safety_danger():
    assert _verdict(70, "danger", 10, None) == "RISKY"


def test_verdict_safe_band():
    # Prob ≥ 50, not-breached, no failure → SAFE
    assert _verdict(55, "moderate", 70, None) == "SAFE"


def test_verdict_risky_on_violation():
    # Breached safety with any prob → RISKY
    assert _verdict(80, "breached", 10, None) == "RISKY"


def test_verdict_risky_low_prob():
    assert _verdict(30, "safe", 20, None) == "RISKY"


def test_verdict_risky_on_failure_reason():
    assert _verdict(55, "moderate", 20, "max_drawdown_breached") == "RISKY"


# ═══════════════════════════════════════════════════════════
# Overfit extraction
# ═══════════════════════════════════════════════════════════

def test_extract_overfit_top_level():
    assert _extract_overfit({"overfit_score": 72}) == 72.0


def test_extract_overfit_nested_report():
    assert _extract_overfit({"report": {"overfit_score": 55}}) == 55.0


def test_extract_overfit_missing_returns_zero():
    assert _extract_overfit(None) == 0.0
    assert _extract_overfit({}) == 0.0
    assert _extract_overfit({"unrelated": "data"}) == 0.0


def test_extract_overfit_clamps_to_0_100():
    assert _extract_overfit({"overfit_score": 150}) == 100.0
    assert _extract_overfit({"overfit_score": -10}) == 0.0


# ═══════════════════════════════════════════════════════════
# End-to-end via monkeypatched engine
# ═══════════════════════════════════════════════════════════

def _raw_engine_output() -> Dict[str, Any]:
    """
    Synthetic shape of what `matching_engine.match_strategy_to_firms`
    returns when `include_probability=True`. Two firms — one strong, one
    marginal — plus one rejected.
    """
    return {
        "top_matches": [
            {
                "firm": "FTMO 100k 2-step",
                "firm_slug": "ftmo_100k_2step",
                "phase": "2-step",
                "status": "pass",
                "score": 82.0,
                "score_breakdown": {},
                "drawdown_buffer": {"total_dd": 5.0, "daily_dd": 2.5},
                "days_taken": 14,
                "trading_days": 18,
                "profit_pct": 10.2,
                "profit_target_pct": 10.0,
                "max_drawdown_pct": 4.1,
                "max_daily_drawdown_pct": 2.2,
                "failure_reason": None,
                "flags": [],
                "drawdown_type": "static",
                "probability": {
                    "pass_probability": 72.0,
                    "confidence_interval": [65.0, 79.0],
                    "risk_label": "low",
                    "avg_days_to_pass": 15.0,
                    "failure_breakdown": {},
                    "structural_robustness": {"score": 90, "label": "robust"},
                },
                "expected_value": {
                    "expected_value": 1500.0,
                    "challenge_fee": 540.0,
                    "potential_reward": 4800,
                    "breakeven_probability": 10.0,
                    "ev_grade": "good",
                },
                "safety_margin": {
                    "risk_level": "safe",
                    "margin_score": 82.0,
                    "total_dd_buffer": 5.0,
                    "daily_dd_buffer": 2.5,
                },
                "decision": {"recommendation": "strong_go", "grade": "A"},
            },
            {
                "firm": "Acme Prop 50k 1-step",
                "firm_slug": "acme_prop_50k_1step",
                "phase": "1-step",
                "status": "fail",
                "score": 25.0,
                "score_breakdown": {},
                "drawdown_buffer": {"total_dd": 0.5, "daily_dd": 0.2},
                "days_taken": 30,
                "trading_days": 28,
                "profit_pct": 3.0,
                "profit_target_pct": 8.0,
                "max_drawdown_pct": 9.5,
                "max_daily_drawdown_pct": 4.8,
                "failure_reason": "max_drawdown_breached",
                "flags": ["dd_pressure"],
                "drawdown_type": "trailing",
                "probability": {
                    "pass_probability": 28.0,
                    "confidence_interval": [20.0, 36.0],
                    "risk_label": "high",
                    "avg_days_to_pass": 0,
                    "failure_breakdown": {"max_drawdown_breached": 75.0},
                    "structural_robustness": {"score": 40, "label": "fragile"},
                },
                "expected_value": {
                    "expected_value": -310.0,
                    "challenge_fee": 400.0,
                    "potential_reward": 3600,
                    "breakeven_probability": 25.0,
                    "ev_grade": "negative",
                },
                "safety_margin": {
                    "risk_level": "danger",
                    "margin_score": 15.0,
                    "total_dd_buffer": 0.5,
                    "daily_dd_buffer": 0.2,
                },
                "decision": {"recommendation": "avoid", "grade": "D"},
            },
        ],
        "rejected": [
            {
                "firm": "BadFirm",
                "firm_slug": "badfirm_10k_2step",
                "phase": "2-step",
                "reason": "max_drawdown_too_high",
            },
        ],
        "profile_summary": {
            "sharpe_ratio": 1.6,
            "equity_curve_smoothness": 80,
            "win_rate": 55,
            "max_drawdown_pct": 5,
            "total_return_pct": 10,
            "trades_per_day": 2,
        },
        "firms_analyzed": 3,
        "firms_compatible": 2,
        "firms_rejected": 1,
    }


@pytest.mark.asyncio
async def test_match_strategy_phase4_reshapes_and_ranks(monkeypatch):
    async def fake_engine(**_kwargs):
        return _raw_engine_output()

    monkeypatch.setattr(phase4_matcher, "match_strategy_to_firms", fake_engine)

    result = await match_strategy_phase4(
        trades=[{"net_pnl": 10}],
        validation_report={"overfit_score": 25},
        n_simulations=10,
    )

    ranked = result["ranked_matches"]
    assert len(ranked) == 2

    # Top match should still be FTMO — realism preserves ordering.
    top = ranked[0]
    assert top["firm"] == "FTMO"
    assert top["plan"] == "100K 2-Step"
    # Raw values preserved for transparency
    assert top["pass_probability_raw"] == 72.0
    assert top["expected_value_raw"] == 1500.0
    # Realism applied: 2-step haircut + low trade-count cap → < raw
    assert top["pass_probability"] < 72.0
    assert top["challenge_type"] == "2step"
    assert "ftmo" in (top["firm_strictness"] or "").lower() or "strict" in (top["firm_strictness"] or "").lower()
    assert isinstance(top["realism_notes"], list) and len(top["realism_notes"]) > 0
    # EV recomputed from adjusted probability
    assert top["expected_value"] != 1500.0
    assert top["risk"] == "LOW"
    assert top["score"] > ranked[1]["score"]
    assert result["overfit_score"] == 25.0

    # Second match should be RISKY (failed + danger safety)
    second = ranked[1]
    assert second["firm"] == "Acme Prop"
    assert second["plan"] == "50K 1-Step"
    assert second["risk"] == "HIGH"
    assert second["verdict"] == "RISKY"
    assert second["challenge_type"] == "1step"

    # Rejected list passes through untouched
    assert len(result["rejected"]) == 1

    # Weights surfaced for transparency
    assert set(result["weights"].keys()) == {
        "pass_probability", "expected_value", "safety",
        "stability", "overfit_penalty",
    }


@pytest.mark.asyncio
async def test_match_strategy_phase4_overfit_reduces_score(monkeypatch):
    async def fake_engine(**_kwargs):
        return _raw_engine_output()

    monkeypatch.setattr(phase4_matcher, "match_strategy_to_firms", fake_engine)

    # Low overfit
    low = await match_strategy_phase4(
        trades=[{"net_pnl": 10}], validation_report={"overfit_score": 0}
    )
    # High overfit — same input, should reduce every score by (0.15 * 80 = 12)
    high = await match_strategy_phase4(
        trades=[{"net_pnl": 10}], validation_report={"overfit_score": 80}
    )

    for lo_row, hi_row in zip(low["ranked_matches"], high["ranked_matches"]):
        # Overfit penalty should strictly reduce the score
        assert hi_row["score"] <= lo_row["score"]
    # And the BEST verdict should flip away from BEST when overfit > 40
    hi_top = high["ranked_matches"][0]
    assert hi_top["verdict"] != "BEST"


@pytest.mark.asyncio
async def test_match_strategy_phase4_propagates_engine_error(monkeypatch):
    async def fake_engine(**_kwargs):
        return {
            "top_matches": [],
            "rejected": [],
            "profile_summary": {},
            "error": "No trades provided",
        }

    monkeypatch.setattr(phase4_matcher, "match_strategy_to_firms", fake_engine)
    out = await match_strategy_phase4(trades=[])
    assert out["ranked_matches"] == []
    assert out["error"] == "No trades provided"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

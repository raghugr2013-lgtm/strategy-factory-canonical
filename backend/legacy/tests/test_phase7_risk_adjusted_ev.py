"""
Phase 7 — Risk-Adjusted Expected Value tests.

Verifies:
  1. High probability + low DD + robust         → strong positive EV
  2. High probability + high DD                   → EV reduced vs low-DD case
  3. Low probability                              → negative EV (below breakeven)
  4. Fragile robustness                           → EV reduced vs robust counterpart
  5. Back-compat: omitting Phase-7 inputs gives a finite, sensible EV
"""

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engines.expected_value import (
    calculate_expected_value,
    _robustness_factor,
    _risk_penalty,
    _risk_band,
    ROBUSTNESS_FACTORS,
    LOW_PROB_PENALTY,
)


FIRM_FEE = 540
FIRM_BAL = 100_000
FIRM_SPLIT = 80
FIRM_MONTHLY = 5.0
FIRM_MONTHS = 6


def _ev(prob, *, label=None, score=None, dd=None):
    return calculate_expected_value(
        pass_probability=prob,
        challenge_fee=FIRM_FEE,
        funded_balance=FIRM_BAL,
        profit_split_pct=FIRM_SPLIT,
        monthly_target_pct=FIRM_MONTHLY,
        expected_months=FIRM_MONTHS,
        structural_robustness_label=label,
        structural_robustness_score=score,
        strategy_max_dd_pct=dd,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. High probability + low DD + robust → strong positive EV
# ══════════════════════════════════════════════════════════════════════════
class TestHighProbLowDD:
    def test_strong_positive_ev(self):
        r = _ev(85.0, label="robust", dd=3.0)
        assert r["expected_value"] > 0
        assert r["ev_grade"] in ("good", "excellent")
        assert r["risk_adjustment"]["robustness_factor"] == 1.0
        assert r["risk_adjustment"]["risk_penalty"] == 1.0
        assert r["risk_adjustment"]["risk_band"] == "low"
        assert r["risk_adjustment"]["low_prob_penalty"] == 1.0


# ══════════════════════════════════════════════════════════════════════════
# 2. High probability + high DD → EV reduced vs low-DD baseline
# ══════════════════════════════════════════════════════════════════════════
class TestHighProbHighDD:
    def test_high_dd_reduces_ev(self):
        low_dd = _ev(85.0, label="robust", dd=3.0)["expected_value"]
        high_dd = _ev(85.0, label="robust", dd=15.0)["expected_value"]
        assert high_dd < low_dd
        # High DD penalty is applied on the cost side.
        assert _ev(85.0, label="robust", dd=15.0)["risk_adjustment"]["risk_penalty"] == 2.0
        assert _ev(85.0, label="robust", dd=15.0)["risk_adjustment"]["risk_band"] == "high"


# ══════════════════════════════════════════════════════════════════════════
# 3. Low probability → negative EV
# ══════════════════════════════════════════════════════════════════════════
class TestLowProbabilityNegativeEV:
    def test_very_low_prob_negative_ev(self):
        # Probability well below breakeven with risk multipliers applied.
        r = _ev(3.0, label="fragile", dd=15.0)
        assert r["expected_value"] < 0, r
        assert r["ev_grade"] == "negative"
        assert r["risk_adjustment"]["low_prob_penalty"] == LOW_PROB_PENALTY

    def test_threshold_penalty_applied_just_under_50(self):
        # 49.9% → penalty active.
        r = _ev(49.9, label="robust", dd=3.0)
        assert r["risk_adjustment"]["low_prob_penalty"] == LOW_PROB_PENALTY

    def test_threshold_penalty_NOT_applied_at_50(self):
        # Exactly 50% → no low-prob penalty.
        r = _ev(50.0, label="robust", dd=3.0)
        assert r["risk_adjustment"]["low_prob_penalty"] == 1.0


# ══════════════════════════════════════════════════════════════════════════
# 4. Fragile strategy → EV reduced vs robust counterpart
# ══════════════════════════════════════════════════════════════════════════
class TestFragileReducesEV:
    def test_fragile_below_robust(self):
        robust = _ev(70.0, label="robust", dd=5.0)["expected_value"]
        moderate = _ev(70.0, label="moderate", dd=5.0)["expected_value"]
        fragile = _ev(70.0, label="fragile", dd=5.0)["expected_value"]
        assert robust > moderate > fragile

    def test_fragile_factor_scales_reward(self):
        r = _ev(60.0, label="fragile", dd=3.0)
        assert r["risk_adjustment"]["robustness_factor"] == ROBUSTNESS_FACTORS["fragile"]

    def test_score_used_when_label_missing(self):
        # Score > 80 → robust factor. Score < 50 → fragile.
        a = _ev(70.0, score=90.0, dd=3.0)["risk_adjustment"]["robustness_factor"]
        b = _ev(70.0, score=30.0, dd=3.0)["risk_adjustment"]["robustness_factor"]
        assert a == 1.0
        assert b == 0.5


# ══════════════════════════════════════════════════════════════════════════
# 5. Helper unit tests + back-compat
# ══════════════════════════════════════════════════════════════════════════
class TestRiskAdjustmentHelpers:
    def test_robustness_factor_priority_label_over_score(self):
        # Label should win even if score disagrees.
        assert _robustness_factor(score=20.0, label="robust") == 1.0
        assert _robustness_factor(score=95.0, label="fragile") == 0.5

    def test_risk_penalty_bands(self):
        assert _risk_penalty(0.0) == 1.0      # unknown / none → neutral
        assert _risk_penalty(2.0) == 1.0      # low
        assert _risk_penalty(4.99) == 1.0     # boundary low
        assert _risk_penalty(5.0) == 1.5      # medium starts at 5
        assert _risk_penalty(9.99) == 1.5
        assert _risk_penalty(10.0) == 2.0     # high starts at 10
        assert _risk_penalty(50.0) == 2.0

    def test_risk_band_labels(self):
        assert _risk_band(None) == "unknown"
        assert _risk_band(4.0) == "low"
        assert _risk_band(7.0) == "medium"
        assert _risk_band(12.0) == "high"


class TestBackwardCompatibility:
    def test_omitting_phase7_inputs_gives_legacy_like_ev(self):
        # No robustness, no DD → multipliers default to 1.0 (only low-prob
        # penalty may still apply). Formula collapses to near-legacy output
        # for p ≥ 50%.
        r = _ev(80.0)
        assert r["risk_adjustment"]["robustness_factor"] == 1.0
        assert r["risk_adjustment"]["risk_penalty"] == 1.0
        assert r["risk_adjustment"]["low_prob_penalty"] == 1.0
        # Legacy formula at 80%: 0.8 * 24000 - 0.2 * 540 = 19200 - 108 = 19092
        assert r["expected_value"] == 19092.0

    def test_response_keys_preserved(self):
        r = _ev(80.0, label="robust", dd=3.0)
        for key in (
            "expected_value", "ev_grade", "risk_reward_ratio",
            "breakeven_probability", "pass_probability", "challenge_fee",
            "potential_reward", "roi_if_pass", "economics",
        ):
            assert key in r, f"missing key: {key}"
        # New Phase 7 block.
        assert "risk_adjustment" in r

    def test_breakeven_probability_rises_with_risk(self):
        low_risk = _ev(60.0, label="robust", dd=3.0)["breakeven_probability"]
        high_risk = _ev(60.0, label="fragile", dd=15.0)["breakeven_probability"]
        assert high_risk > low_risk

"""
Phase 6 — Mutation Integrity Guard tests.

Validates that `_is_improvement` rejects mutations whose probability or
drawdown gains are accompanied by a significant structural-robustness drop,
and accepts mutations that genuinely improve edge without sacrificing it.

All tests are pure-logic (no MC, no backtest): they feed hand-crafted
original/mutated evaluation dicts directly into `_is_improvement`.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engines.strategy_mutation import _is_improvement, ROBUSTNESS_DROP_THRESHOLD


# ══════════════════════════════════════════════════════════════════════════
# Fixture factory
# ══════════════════════════════════════════════════════════════════════════
def _eval(
    *,
    pass_prob: float,
    robustness: float | None,
    max_dd: float = 10.0,
    profit_factor: float = 1.5,
    total_return_pct: float = 20.0,
    sim_status: str = "pass",
) -> dict:
    return {
        "backtest": {
            "net_profit": 1000,
            "total_return_pct": total_return_pct,
            "win_rate": 55,
            "profit_factor": profit_factor,
            "max_drawdown_pct": max_dd,
            "total_trades": 100,
        },
        "profile": {"sharpe_ratio": 1.0},
        "simulation": {
            "status": sim_status,
            "max_drawdown_pct": max_dd,
            "max_daily_dd_pct": 2.0,
            "failure_reason": None if sim_status == "pass" else "total_dd",
        },
        "probability": {
            "pass_probability": pass_prob,
            "risk_label": "low",
            "avg_days_to_pass": 10,
            "structural_robustness_score": robustness,
            "structural_robustness_label": (
                "robust" if robustness is not None and robustness > 80
                else "moderate" if robustness is not None and robustness >= 50
                else "fragile" if robustness is not None
                else None
            ),
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. Probability up + robustness collapse → REJECT
# ══════════════════════════════════════════════════════════════════════════
class TestRejectProbabilityUpRobustnessDown:
    def test_big_prob_gain_with_robustness_collapse_rejected(self):
        original = _eval(pass_prob=55.0, robustness=80.0)
        mutated = _eval(pass_prob=75.0, robustness=50.0)   # 30-pt robustness drop
        ok, reason = _is_improvement(original, mutated)
        assert ok is False, reason
        assert "robustness" in reason.lower()

    def test_boundary_drop_of_exactly_threshold_still_allowed(self):
        # Drop EQUAL to threshold is allowed (guard checks > threshold).
        original = _eval(pass_prob=55.0, robustness=80.0)
        mutated = _eval(pass_prob=70.0, robustness=80.0 - ROBUSTNESS_DROP_THRESHOLD)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True, reason

    def test_drop_just_above_threshold_rejected(self):
        original = _eval(pass_prob=55.0, robustness=80.0)
        mutated = _eval(
            pass_prob=70.0,
            robustness=80.0 - ROBUSTNESS_DROP_THRESHOLD - 0.1,
        )
        ok, reason = _is_improvement(original, mutated)
        assert ok is False
        assert "robustness" in reason.lower()


# ══════════════════════════════════════════════════════════════════════════
# 2. Probability up AND robustness maintained/improved → ACCEPT
# ══════════════════════════════════════════════════════════════════════════
class TestAcceptProbabilityUpRobustnessStable:
    def test_prob_up_robustness_same_accepted(self):
        original = _eval(pass_prob=55.0, robustness=80.0)
        mutated = _eval(pass_prob=75.0, robustness=80.0)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True
        assert "probability improved" in reason.lower()

    def test_prob_up_robustness_up_accepted(self):
        original = _eval(pass_prob=55.0, robustness=70.0)
        mutated = _eval(pass_prob=75.0, robustness=85.0)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True

    def test_prob_up_small_robustness_dip_accepted(self):
        # 5-pt dip is under the 10-pt threshold → accept
        original = _eval(pass_prob=55.0, robustness=80.0)
        mutated = _eval(pass_prob=75.0, robustness=75.0)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════
# 3. Drawdown reduction + robustness maintained → ACCEPT
#    Drawdown reduction + robustness collapse    → REJECT
# ══════════════════════════════════════════════════════════════════════════
class TestDrawdownPath:
    def test_dd_reduced_robustness_maintained_accepted(self):
        original = _eval(
            pass_prob=60.0, robustness=85.0,
            max_dd=10.0, profit_factor=1.5,
        )
        mutated = _eval(
            pass_prob=60.0, robustness=85.0,
            max_dd=6.0,  profit_factor=1.5,   # 40% DD reduction, PF steady
        )
        ok, reason = _is_improvement(original, mutated)
        assert ok is True
        assert "drawdown" in reason.lower()

    def test_dd_reduced_robustness_collapsed_rejected(self):
        original = _eval(
            pass_prob=60.0, robustness=85.0,
            max_dd=10.0, profit_factor=1.5,
        )
        mutated = _eval(
            pass_prob=60.0, robustness=60.0,   # 25-pt drop
            max_dd=6.0,  profit_factor=1.5,
        )
        ok, reason = _is_improvement(original, mutated)
        assert ok is False
        assert "robustness" in reason.lower()


# ══════════════════════════════════════════════════════════════════════════
# 4. Legacy back-compat — robustness missing on either side → guard skipped
# ══════════════════════════════════════════════════════════════════════════
class TestBackwardCompatibilityWhenRobustnessMissing:
    def test_no_robustness_original(self):
        original = _eval(pass_prob=55.0, robustness=None)
        mutated = _eval(pass_prob=75.0, robustness=40.0)
        ok, reason = _is_improvement(original, mutated)
        # Guard inactive → falls through to the probability-improvement branch.
        assert ok is True

    def test_no_robustness_mutated(self):
        original = _eval(pass_prob=55.0, robustness=85.0)
        mutated = _eval(pass_prob=75.0, robustness=None)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True

    def test_no_robustness_either_side_preserves_existing_logic(self):
        original = _eval(pass_prob=55.0, robustness=None)
        mutated = _eval(pass_prob=75.0, robustness=None)
        ok, reason = _is_improvement(original, mutated)
        assert ok is True


# ══════════════════════════════════════════════════════════════════════════
# 5. Non-guarded acceptance paths are NOT affected by the new logic
# ══════════════════════════════════════════════════════════════════════════
class TestUnguardedPathsStillWork:
    def test_simulation_status_flip_accepted(self):
        # Probability is flat and neither DD nor PF improved; only the sim
        # status flipped fail → pass. Existing logic must still accept.
        original = _eval(pass_prob=40.0, robustness=80.0, sim_status="fail")
        mutated = _eval(pass_prob=40.0, robustness=80.0, sim_status="pass")
        ok, reason = _is_improvement(original, mutated)
        assert ok is True
        assert "status" in reason.lower()

    def test_no_change_no_improvement(self):
        original = _eval(pass_prob=60.0, robustness=80.0)
        mutated = _eval(pass_prob=60.0, robustness=80.0)
        ok, reason = _is_improvement(original, mutated)
        assert ok is False
        assert "no significant" in reason.lower()

    def test_return_collapse_blocks_acceptance(self):
        # Return drops > 50% → the pre-existing "major trade-off" guard still
        # rejects, even with probability gain.
        original = _eval(pass_prob=55.0, robustness=80.0, total_return_pct=30.0)
        mutated = _eval(pass_prob=80.0, robustness=80.0, total_return_pct=10.0)
        ok, reason = _is_improvement(original, mutated)
        assert ok is False
        assert "return" in reason.lower()

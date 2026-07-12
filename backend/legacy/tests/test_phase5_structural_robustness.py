"""
Tests for the structural robustness score (Phase 5 upgrade).

Score definition:
    score = 100 × (block_pass_prob / legacy_pass_prob)
    clamped to [0, 100]; if legacy == 0 → score = 0.

Labels:
    > 80  → robust
    50–80 → moderate
    < 50  → fragile
"""

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engines.pass_probability import (
    _robustness_label,
    _structural_robustness,
    estimate_pass_probability,
)
from tests.test_phase5_block_monte_carlo import (
    BASE_CFG,
    _cluster_scenario,
    _stable_scenario,
)


# ══════════════════════════════════════════════════════════════════════════
# 1. Unit tests for the scoring helpers
# ══════════════════════════════════════════════════════════════════════════
class TestStructuralRobustnessUnit:
    def test_identical_probabilities_score_100(self):
        r = _structural_robustness(block_prob=75.0, legacy_prob=75.0)
        assert r["score"] == 100.0
        assert r["label"] == "robust"

    def test_half_ratio_scores_50_labels_moderate(self):
        r = _structural_robustness(block_prob=30.0, legacy_prob=60.0)
        assert r["score"] == 50.0
        assert r["label"] == "moderate"

    def test_fragile_when_block_much_lower(self):
        r = _structural_robustness(block_prob=10.0, legacy_prob=90.0)
        # 100 * 10 / 90 ≈ 11.1
        assert r["score"] < 50.0
        assert r["label"] == "fragile"

    def test_clamped_above_100(self):
        # Block should never exceed legacy, but protect the clamp anyway.
        r = _structural_robustness(block_prob=90.0, legacy_prob=45.0)
        assert r["score"] == 100.0
        assert r["label"] == "robust"

    def test_clamped_below_zero(self):
        r = _structural_robustness(block_prob=-5.0, legacy_prob=50.0)
        assert r["score"] == 0.0

    def test_legacy_zero_returns_zero(self):
        r = _structural_robustness(block_prob=20.0, legacy_prob=0.0)
        assert r["score"] == 0.0
        assert r["label"] == "fragile"

    def test_both_zero_returns_zero(self):
        r = _structural_robustness(block_prob=0.0, legacy_prob=0.0)
        assert r["score"] == 0.0
        assert r["label"] == "fragile"

    def test_attached_fields(self):
        r = _structural_robustness(block_prob=40.0, legacy_prob=80.0)
        assert r["block_pass_probability"] == 40.0
        assert r["legacy_pass_probability"] == 80.0

    def test_label_boundaries(self):
        assert _robustness_label(100.0) == "robust"
        assert _robustness_label(80.1)  == "robust"
        assert _robustness_label(80.0)  == "moderate"    # > 80 is strict
        assert _robustness_label(50.0)  == "moderate"
        assert _robustness_label(49.9)  == "fragile"
        assert _robustness_label(0.0)   == "fragile"


# ══════════════════════════════════════════════════════════════════════════
# 2. Integration: score attached to pass_probability output
# ══════════════════════════════════════════════════════════════════════════
class TestRobustnessInPassProbabilityOutput:
    def test_stable_strategy_is_robust(self):
        r = estimate_pass_probability(
            _stable_scenario(n_days=12), BASE_CFG,
            n_simulations=40, seed=1,
        )
        sr = r["structural_robustness"]
        # Stable strategy → legacy and block give the same answer → high score.
        assert sr["score"] >= 80.0, sr
        assert sr["label"] == "robust"
        assert sr["block_pass_probability"] == r["pass_probability"]

    def test_clustered_strategy_is_not_robust(self):
        r = estimate_pass_probability(
            _cluster_scenario(), BASE_CFG,
            n_simulations=80, seed=42,
            min_block_days=5, max_block_days=5,
        )
        sr = r["structural_robustness"]
        # Cluster-sensitive scenario: legacy inflates → ratio < 1 → score < 100.
        assert sr["score"] < 100.0, sr
        assert sr["label"] in ("moderate", "fragile")
        # The block half of the MC genuinely exposes the DD → block < legacy.
        assert sr["block_pass_probability"] < sr["legacy_pass_probability"]

    def test_score_absent_when_legacy_method_used(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG,
            n_simulations=20, seed=1,
            shuffle_method="legacy",
        )
        # No robustness score when the caller already chose legacy.
        assert "structural_robustness" not in r or r.get("structural_robustness") is None

    def test_score_absent_when_disabled(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG,
            n_simulations=20, seed=1,
            compute_robustness=False,
        )
        assert "structural_robustness" not in r

    def test_deterministic_across_calls(self):
        trades = _cluster_scenario()
        r1 = estimate_pass_probability(
            trades, BASE_CFG, n_simulations=40, seed=99,
            min_block_days=5, max_block_days=5,
        )
        r2 = estimate_pass_probability(
            trades, BASE_CFG, n_simulations=40, seed=99,
            min_block_days=5, max_block_days=5,
        )
        assert r1["structural_robustness"] == r2["structural_robustness"]


# ══════════════════════════════════════════════════════════════════════════
# 3. Back-compat check: existing shape still intact
# ══════════════════════════════════════════════════════════════════════════
class TestBackwardCompatibility:
    def test_other_keys_preserved_alongside_robustness(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG, n_simulations=20, seed=1,
        )
        for key in (
            "pass_probability", "confidence_interval", "risk_label",
            "n_simulations", "passes", "fails", "avg_days_to_pass",
            "failure_breakdown", "method_comparison", "baseline",
            "simulation_details", "shuffle_method",
        ):
            assert key in r, f"missing key: {key}"
        assert "structural_robustness" in r

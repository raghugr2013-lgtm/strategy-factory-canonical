"""
Phase 5 upgrade tests — Block-based Monte Carlo.

Demonstrates that block-based shuffling preserves cluster structure, which
in turn reduces the pass-probability inflation produced by the legacy
day-level shuffle.

Structure:
  1. Unit tests for `_block_shuffle_trades` (preserves intra-day order,
     preserves day order inside a block, shuffles blocks).
  2. Old-vs-new comparison on a constructed cluster-breach scenario:
     legacy shuffle inflates pass rate; block shuffle exposes the cluster.
  3. Back-compat assertions on the public API signature / response keys.
  4. Regression: existing well-behaved strategy still yields sensible output.
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engines.pass_probability import (
    _block_shuffle_trades,
    _group_by_day,
    estimate_pass_probability,
    DEFAULT_MIN_BLOCK_DAYS,
    DEFAULT_MAX_BLOCK_DAYS,
)


# ══════════════════════════════════════════════════════════════════════════
# Shared config / trade builders
# ══════════════════════════════════════════════════════════════════════════
BASE_CFG = dict(
    name="TEST",
    initial_balance=100_000,
    profit_target_pct=10.0,
    max_daily_dd_pct=5.0,
    max_total_dd_pct=8.0,
    min_trading_days=5,
    time_limit_days=0,
    drawdown_type="static",
)


def _cluster_scenario(n_days: int = 30, bad_at_start: int = 5) -> list:
    """
    Constructed scenario that exposes cluster sensitivity.

      - First `bad_at_start` days: -$3,000 each (-$15k clustered loss).
      - Remaining days: +$1,000 each.
      - Net PnL over 30 days = +$10,000 (hits 10% profit target — but only if
        the cluster doesn't breach the 8% total-DD floor first).

    For `drawdown_type == "static"` with 8% DD limit ($8k), any sequence where
    5 consecutive -$3k losses land against a peak ≥ 100k breaches total DD.
    Since every shuffle that *keeps* the cluster intact produces such a path,
    block-shuffle (which keeps the cluster together) drives the pass rate
    near 0. Day-level shuffle breaks the cluster apart → pass rate stays high.
    """
    base = datetime(2024, 1, 1)
    trades = []
    for i in range(n_days):
        day = (base + timedelta(days=i)).strftime("%Y-%m-%d")
        pnl = -3000 if i < bad_at_start else 1000
        trades.append({
            "net_pnl": pnl,
            "floating_min_pnl": pnl if pnl < 0 else -200,
            "lot_size": 1.0,
            "timestamp": f"{day}T10:00:00",
        })
    return trades


def _stable_scenario(n_days: int = 10) -> list:
    base = datetime(2024, 1, 1)
    return [
        {
            "net_pnl": 1500,
            "floating_min_pnl": -200,
            "lot_size": 1.0,
            "timestamp": f"{(base + timedelta(days=i)).strftime('%Y-%m-%d')}T10:00:00",
        }
        for i in range(n_days)
    ]


# ══════════════════════════════════════════════════════════════════════════
# 1. Unit tests for _block_shuffle_trades
# ══════════════════════════════════════════════════════════════════════════
class TestBlockShuffleUnit:
    def test_preserves_all_trades(self):
        trades = _cluster_scenario()
        rng = random.Random(1)
        shuffled = _block_shuffle_trades(trades, rng, min_block_days=5, max_block_days=5)
        assert len(shuffled) == len(trades)
        assert sorted(t["timestamp"] for t in shuffled) == sorted(t["timestamp"] for t in trades)

    def test_preserves_intra_day_order(self):
        # Two trades on the same day, identifiable by "tag".
        base = datetime(2024, 1, 1)
        trades = []
        for d in range(10):
            day_str = (base + timedelta(days=d)).strftime("%Y-%m-%d")
            trades.append({"net_pnl": 100, "lot_size": 1.0, "tag": f"{d}-A",
                           "timestamp": f"{day_str}T09:00:00"})
            trades.append({"net_pnl": 200, "lot_size": 1.0, "tag": f"{d}-B",
                           "timestamp": f"{day_str}T15:00:00"})

        rng = random.Random(7)
        shuffled = _block_shuffle_trades(trades, rng, min_block_days=2, max_block_days=2)

        # For each day, A must appear before B.
        seen_a = {}
        for t in shuffled:
            d_prefix = t["tag"].split("-")[0]
            if t["tag"].endswith("-A"):
                seen_a[d_prefix] = True
            else:
                assert seen_a.get(d_prefix), f"B for day {d_prefix} appeared before A"

    def test_preserves_day_order_within_block(self):
        """Within any block, the days must still appear in ascending calendar order."""
        trades = _cluster_scenario(n_days=30)
        rng = random.Random(123)
        shuffled = _block_shuffle_trades(trades, rng, min_block_days=5, max_block_days=5)

        shuffled_days = [t["timestamp"][:10] for t in shuffled]
        # Split back into blocks of 5 consecutive days in the output.
        for i in range(0, 30, 5):
            block_days = shuffled_days[i:i + 5]
            # Calendar-sorted within the block → day order preserved
            assert block_days == sorted(block_days), (
                f"Block starting at {i} is not calendar-sorted: {block_days}"
            )

    def test_actually_shuffles_blocks(self):
        """Different seeds should produce at least one different block ordering."""
        trades = _cluster_scenario()
        outputs = {
            tuple(t["timestamp"] for t in _block_shuffle_trades(
                trades, random.Random(seed), min_block_days=5, max_block_days=5
            ))
            for seed in range(5)
        }
        assert len(outputs) > 1, "block shuffle produced identical output across 5 seeds"

    def test_small_dataset_returns_unchanged(self):
        """Fewer days than 2 × min_block → cannot form 2 blocks → returns original."""
        trades = [
            {"net_pnl": 100, "timestamp": "2024-01-01T10:00:00", "lot_size": 1.0},
            {"net_pnl": 200, "timestamp": "2024-01-02T10:00:00", "lot_size": 1.0},
        ]
        rng = random.Random(0)
        out = _block_shuffle_trades(trades, rng, min_block_days=5, max_block_days=10)
        assert out == trades


# ══════════════════════════════════════════════════════════════════════════
# 2. Old-vs-new comparison: block shuffle ≤ legacy shuffle
# ══════════════════════════════════════════════════════════════════════════
class TestLegacyVsBlockComparison:
    """
    Invariant: on a scenario whose failure is driven by a clustered
    drawdown, legacy day-shuffle breaks the cluster and inflates pass
    probability, while block shuffle keeps the cluster together and
    produces a lower (more realistic) pass rate.

      block_pass_rate  <=  legacy_pass_rate          (non-strict)
      shuffle-only rate gap >= 10 percentage points  (strict)
    """

    @pytest.fixture(scope="class")
    def scenario(self):
        return _cluster_scenario()

    def test_block_shuffle_deflates_vs_legacy(self, scenario):
        block = estimate_pass_probability(
            scenario, BASE_CFG,
            n_simulations=80, seed=42,
            shuffle_method="block_based",
            min_block_days=5, max_block_days=5,
        )
        legacy = estimate_pass_probability(
            scenario, BASE_CFG,
            n_simulations=80, seed=42,
            shuffle_method="legacy",
        )

        # Overall pass probability should go DOWN (or at least not up).
        assert block["pass_probability"] <= legacy["pass_probability"], (
            f"block {block['pass_probability']} > legacy {legacy['pass_probability']}"
        )

        # On the shuffle half of the runs specifically, the inflation gap
        # should be large on this cluster-sensitive scenario.
        block_shuffle_rate = block["method_comparison"]["shuffle_pass_rate"]
        legacy_shuffle_rate = legacy["method_comparison"]["shuffle_pass_rate"]
        gap = legacy_shuffle_rate - block_shuffle_rate
        assert gap >= 10.0, (
            f"Expected shuffle-rate gap ≥ 10pp. "
            f"block_shuffle_pass_rate={block_shuffle_rate}, "
            f"legacy_shuffle_pass_rate={legacy_shuffle_rate}, gap={gap}"
        )

    def test_block_shuffle_exposes_cluster_failures(self, scenario):
        """Block shuffle should surface total_dd failures more often than legacy."""
        block = estimate_pass_probability(
            scenario, BASE_CFG,
            n_simulations=80, seed=42,
            shuffle_method="block_based",
            min_block_days=5, max_block_days=5,
        )
        legacy = estimate_pass_probability(
            scenario, BASE_CFG,
            n_simulations=80, seed=42,
            shuffle_method="legacy",
        )
        # At minimum, block method must register *some* total_dd failures
        # on this scenario — the very failure type a cluster is supposed to
        # produce. Legacy should not flag any because the cluster is gone.
        assert block["failure_breakdown"].get("total_dd", 0) > 0
        # Block fails-count must be >= legacy fails-count on this scenario.
        assert block["fails"] >= legacy["fails"]


# ══════════════════════════════════════════════════════════════════════════
# 3. Backward compatibility — public API / response shape
# ══════════════════════════════════════════════════════════════════════════
class TestBackwardCompatibility:
    def test_default_is_block_based(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG, n_simulations=10, seed=1
        )
        assert r["shuffle_method"] == "block_based"

    def test_response_keys_preserved(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG, n_simulations=10, seed=1
        )
        for key in (
            "pass_probability", "confidence_interval", "risk_label",
            "n_simulations", "passes", "fails", "avg_days_to_pass",
            "failure_breakdown", "method_comparison", "baseline",
            "simulation_details",
        ):
            assert key in r, f"missing key: {key}"

    def test_simulation_detail_method_values_unchanged(self):
        """Existing tests expect method ∈ {'shuffle', 'perturb'} — must stay."""
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG, n_simulations=20, seed=1
        )
        methods = {d["method"] for d in r["simulation_details"]}
        assert methods <= {"shuffle", "perturb"}, f"got unexpected methods: {methods}"

    def test_method_comparison_keys_unchanged(self):
        r = estimate_pass_probability(
            _stable_scenario(), BASE_CFG, n_simulations=10, seed=1
        )
        mc = r["method_comparison"]
        assert "shuffle_pass_rate" in mc
        assert "perturb_pass_rate" in mc

    def test_invalid_shuffle_method_raises(self):
        with pytest.raises(ValueError):
            estimate_pass_probability(
                _stable_scenario(), BASE_CFG,
                n_simulations=10, seed=1,
                shuffle_method="random_walk",
            )

    def test_defaults_exported(self):
        assert DEFAULT_MIN_BLOCK_DAYS == 5
        assert DEFAULT_MAX_BLOCK_DAYS == 10


# ══════════════════════════════════════════════════════════════════════════
# 4. Regression — stable strategy still gets sensible output
# ══════════════════════════════════════════════════════════════════════════
class TestNoRegressionOnStableStrategy:
    def test_stable_strategy_high_pass_rate(self):
        r = estimate_pass_probability(
            _stable_scenario(n_days=12), BASE_CFG,
            n_simulations=40, seed=1,
        )
        # 12 days × +$1,500 = +$18k, hits the 10% profit target easily,
        # no bad days to trigger drawdown → should still pass most runs.
        assert r["pass_probability"] >= 70.0, r["pass_probability"]
        assert r["risk_label"] in ("low", "medium")
        assert len(r["simulation_details"]) == 40

    def test_seed_reproducibility(self):
        trades = _stable_scenario()
        r1 = estimate_pass_probability(trades, BASE_CFG, n_simulations=20, seed=99)
        r2 = estimate_pass_probability(trades, BASE_CFG, n_simulations=20, seed=99)
        assert r1["pass_probability"] == r2["pass_probability"]
        assert r1["simulation_details"] == r2["simulation_details"]


# ══════════════════════════════════════════════════════════════════════════
# 5. Helper sanity: _group_by_day preserves order
# ══════════════════════════════════════════════════════════════════════════
class TestGroupByDay:
    def test_preserves_first_seen_order(self):
        trades = _cluster_scenario(n_days=6)
        order, _ = _group_by_day(trades)
        assert order == sorted(order)

    def test_empty_input(self):
        order, day_map = _group_by_day([])
        assert order == []
        assert dict(day_map) == {}

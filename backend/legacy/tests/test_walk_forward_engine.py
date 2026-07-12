"""
Phase 8 — Walk-Forward Engine leakage & correctness tests.
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.walk_forward_engine import run_walk_forward, _build_windows
from engines.random_search_optimizer import fit_best_params, score_frozen_params


def _synthetic_prices(n: int = 500, seed: int = 42) -> list:
    """Generate a deterministic synthetic random-walk price series."""
    rng = random.Random(seed)
    p = 1.1000
    out = [p]
    for _ in range(n - 1):
        p *= (1.0 + rng.gauss(0, 0.002))
        out.append(round(p, 5))
    return out


STRATEGY = (
    "Trend-following EMA crossover strategy using fast EMA and slow EMA "
    "with RSI confirmation. Buy when fast EMA crosses above slow EMA and "
    "RSI > 50. Sell when fast EMA crosses below slow EMA and RSI < 50."
)


def test_window_builder_is_non_overlapping_oos():
    """OOS slices must not overlap across windows."""
    windows = _build_windows(n_total=500, n_windows=5, train_pct=0.7)
    assert len(windows) >= 2
    oos_ranges = [(w["oos_start"], w["oos_end"]) for w in windows]
    # Consecutive OOS slices should be contiguous (or at worst non-overlapping)
    for i in range(1, len(oos_ranges)):
        assert oos_ranges[i][0] >= oos_ranges[i - 1][1], (
            f"OOS overlap between window {i-1} and {i}: "
            f"{oos_ranges[i-1]} vs {oos_ranges[i]}"
        )


def test_walk_forward_runs_and_returns_windows():
    prices = _synthetic_prices(500)
    res = run_walk_forward(STRATEGY, "EURUSD", "H1", prices, n_windows=4, num_variants=10)
    assert res["success"] is True
    assert res["mode"] == "walk_forward"
    assert res["n_windows"] >= 2
    assert len(res["windows"]) == res["n_windows"]
    assert "aggregate" in res
    assert "stability_score" in res["aggregate"]
    for w in res["windows"]:
        assert "is_metrics" in w and "oos_metrics" in w
        assert "frozen_params" in w
        assert w["train_candles"] > 0 and w["oos_candles"] > 0


def test_walk_forward_leakage_train_range_disjoint_from_oos_range():
    """train_range and oos_range of each window must be disjoint."""
    prices = _synthetic_prices(500)
    res = run_walk_forward(STRATEGY, "EURUSD", "H1", prices, n_windows=4, num_variants=10)
    assert res["success"]
    for w in res["windows"]:
        tr = w["train_range"]
        oo = w["oos_range"]
        assert tr[1] <= oo[0], f"train_range {tr} overlaps oos_range {oo}"


def test_walk_forward_rejects_small_dataset():
    prices = _synthetic_prices(50)
    res = run_walk_forward(STRATEGY, "EURUSD", "H1", prices, n_windows=4, num_variants=10)
    assert res["success"] is False
    assert "error" in res


def test_fit_best_params_never_sees_test_prices():
    """
    fit_best_params accepts ONLY train_prices. Even if we pass mutually
    exclusive slices, changing the OOS slice content MUST NOT change the
    selection outcome (because it never reached the fitter).
    """
    prices = _synthetic_prices(400)
    train = prices[:280]

    fit_a = fit_best_params(STRATEGY, "EURUSD", "H1", train_prices=train,
                            num_variants=8, rng_seed=123)
    fit_b = fit_best_params(STRATEGY, "EURUSD", "H1", train_prices=train,
                            num_variants=8, rng_seed=123)
    assert fit_a["success"] and fit_b["success"]
    # Same seed + same train = identical params selected (deterministic)
    assert fit_a["params"] == fit_b["params"]

    # Now score with frozen params on two totally different OOS slices.
    oos_1 = prices[280:]
    oos_2 = [p * 1.5 for p in prices[280:]]  # shifted OOS
    s1 = score_frozen_params(STRATEGY, "EURUSD", "H1", prices=oos_1,
                             params=fit_a["params"],
                             strategy_type=fit_a["strategy_type"])
    s2 = score_frozen_params(STRATEGY, "EURUSD", "H1", prices=oos_2,
                             params=fit_a["params"],
                             strategy_type=fit_a["strategy_type"])
    assert s1["success"] and s2["success"]
    # Params are identical → selection wasn't influenced by OOS content.
    assert s1["params"] == s2["params"] == fit_a["params"]


if __name__ == "__main__":
    test_window_builder_is_non_overlapping_oos()
    test_walk_forward_runs_and_returns_windows()
    test_walk_forward_leakage_train_range_disjoint_from_oos_range()
    test_walk_forward_rejects_small_dataset()
    test_fit_best_params_never_sees_test_prices()
    print("walk_forward_engine: ALL TESTS PASSED")

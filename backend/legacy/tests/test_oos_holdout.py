"""
Phase 8 — OOS Holdout leakage & correctness tests.
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.oos_holdout import run_oos_holdout


STRATEGY = (
    "Mean reversion strategy using RSI period 14. Buy when RSI < 30, sell "
    "when RSI > 70. Use Bollinger Bands for confirmation."
)


def _synthetic_prices(n: int = 400, seed: int = 7) -> list:
    rng = random.Random(seed)
    p = 1.2000
    out = [p]
    for _ in range(n - 1):
        p *= (1.0 + rng.gauss(0, 0.0015))
        out.append(round(p, 5))
    return out


def test_holdout_basic():
    prices = _synthetic_prices(400)
    res = run_oos_holdout(STRATEGY, "GBPUSD", "H1", prices,
                          train_pct=0.8, num_variants=15)
    assert res["success"] is True
    assert res["mode"] == "holdout"
    # 80/20 split must match prices length
    assert res["train_candles"] + res["oos_candles"] == len(prices)
    # Frozen params must exist and be a dict
    assert isinstance(res["frozen_params"], dict) and res["frozen_params"]
    # Both metrics blocks must be present
    for k in ("net_profit", "total_return_pct", "total_trades", "max_drawdown_pct"):
        assert k in res["train_metrics"]
        assert k in res["oos_metrics"]
    # Degradation must be a number
    assert "return_pct_degradation" in res["degradation"]


def test_holdout_rejects_small_dataset():
    res = run_oos_holdout(STRATEGY, "GBPUSD", "H1", _synthetic_prices(50))
    assert res["success"] is False
    assert "error" in res


def test_holdout_oos_slice_is_unseen_by_fit():
    """
    If we swap the OOS slice after the split point with a different one,
    the frozen_params must remain unchanged (fit only ran on train).
    """
    prices = _synthetic_prices(400)

    r1 = run_oos_holdout(STRATEGY, "GBPUSD", "H1", prices,
                         train_pct=0.8, num_variants=10)
    assert r1["success"]

    # Build a second price series that shares train prefix but has a totally
    # different OOS tail.
    split = int(len(prices) * 0.8)
    tampered = prices[:split] + [p * 2.5 for p in prices[split:]]
    r2 = run_oos_holdout(STRATEGY, "GBPUSD", "H1", tampered,
                         train_pct=0.8, num_variants=10)
    assert r2["success"]

    # Frozen params MUST be identical (train-only selection).
    assert r1["frozen_params"] == r2["frozen_params"], (
        "LEAKAGE: frozen params changed when OOS slice changed"
    )


if __name__ == "__main__":
    test_holdout_basic()
    test_holdout_rejects_small_dataset()
    test_holdout_oos_slice_is_unseen_by_fit()
    print("oos_holdout: ALL TESTS PASSED")

"""
Phase 8 — validation_engine mode switching + combined report tests.
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.validation_engine import run_validation
from engines.validation_report import build_validation_report


def _prices(n=400, seed=11):
    rng = random.Random(seed)
    p = 150.0
    out = [p]
    for _ in range(n - 1):
        p *= (1.0 + rng.gauss(0, 0.0018))
        out.append(round(p, 3))
    return out


STRATEGY = "Trend following EMA crossover with RSI filter on USDJPY."


def test_mode_basic_default():
    res = run_validation(STRATEGY, "USDJPY", "H1", _prices(200))
    assert res["success"]
    assert res["mode"] == "basic"
    assert "stability" in res and "segments" in res


def test_mode_walk_forward():
    res = run_validation(STRATEGY, "USDJPY", "H1", _prices(500),
                         mode="walk_forward",
                         wf_n_windows=3, wf_num_variants=8)
    assert res["success"]
    assert res["mode"] == "walk_forward"
    assert "aggregate" in res
    assert res["n_windows"] >= 2


def test_mode_holdout():
    res = run_validation(STRATEGY, "USDJPY", "H1", _prices(400),
                         mode="holdout",
                         holdout_train_pct=0.8, holdout_num_variants=10)
    assert res["success"]
    assert res["mode"] == "holdout"
    assert "frozen_params" in res


def test_mode_full_composes_report():
    res = run_validation(STRATEGY, "USDJPY", "H1", _prices(500),
                         mode="full",
                         wf_n_windows=3, wf_num_variants=6,
                         holdout_num_variants=8)
    assert res["success"]
    assert res["mode"] == "full"
    assert "overfit_score" in res and "stability_score" in res
    assert "walk_forward" in res and "oos_holdout" in res and "basic" in res
    assert res["verdict"] in ("ROBUST", "ACCEPTABLE", "OVERFIT", "FRAGILE", "UNKNOWN")


def test_report_builder_handles_missing_components():
    rep = build_validation_report(walk_forward=None, oos_holdout=None, basic=None)
    assert rep["overfit_score"]["score"] is None
    assert rep["stability_score"]["score"] is None
    assert rep["verdict"] == "UNKNOWN"


if __name__ == "__main__":
    test_mode_basic_default()
    test_mode_walk_forward()
    test_mode_holdout()
    test_mode_full_composes_report()
    test_report_builder_handles_missing_components()
    print("validation_modes: ALL TESTS PASSED")

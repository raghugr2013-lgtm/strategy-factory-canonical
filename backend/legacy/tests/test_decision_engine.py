"""
Phase 8.5 — Decision Engine tests (rule coverage + output shape).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.decision_engine import decide


def _report(overfit=20, stability=70, wf_oos_ret=3.0, ho_oos_ret=2.0,
            holdout_flag=False):
    return {
        "overfit_score": {"score": overfit, "grade": "A"},
        "stability_score": {"score": stability, "grade": "A"},
        "walk_forward": {
            "success": True,
            "aggregate": {"oos_avg_return_pct": wf_oos_ret,
                          "oos_profitable_ratio": 0.8,
                          "mean_degradation_pct": 10,
                          "stability_score": stability},
            "windows": [],
        },
        "oos_holdout": {
            "success": True,
            "oos_metrics": {"total_return_pct": ho_oos_ret,
                            "sharpe_ratio": 1.0,
                            "total_trades": 20,
                            "net_profit": 100},
            "overfit": {"flagged": holdout_flag, "reason": None},
        },
    }


def _ev(val=300, grade="good"):
    return {"expected_value": val, "ev_grade": grade}


def test_reject_when_oos_negative():
    res = decide(_report(overfit=10, stability=80, wf_oos_ret=-1.5), _ev(500),
                 pass_probability=70)
    assert res["decision"]["verdict"] == "REJECT"
    assert "OOS return is negative" in res["decision"]["reason"]


def test_reject_when_overfit_high():
    res = decide(_report(overfit=80, stability=80, wf_oos_ret=2.0), _ev(500),
                 pass_probability=70)
    assert res["decision"]["verdict"] == "REJECT"
    assert "Overfit score" in res["decision"]["reason"]


def test_reject_when_holdout_flag_and_oos_zero():
    res = decide(_report(overfit=30, stability=70, wf_oos_ret=0, ho_oos_ret=0,
                         holdout_flag=True), _ev(200), pass_probability=60)
    assert res["decision"]["verdict"] == "REJECT"


def test_trade_when_all_green():
    res = decide(_report(overfit=20, stability=75, wf_oos_ret=4.0), _ev(400),
                 pass_probability=70)
    assert res["decision"]["verdict"] == "TRADE"
    assert res["decision"]["confidence"] > 60
    assert res["scores"]["oos_return_pct"] == 4.0


def test_risky_when_ev_zero_but_stable():
    res = decide(_report(overfit=25, stability=70, wf_oos_ret=1.0), _ev(-50, "negative"),
                 pass_probability=55)
    assert res["decision"]["verdict"] == "RISKY"
    assert "EV non-positive" in res["decision"]["reason"]


def test_risky_when_low_stability():
    res = decide(_report(overfit=30, stability=40, wf_oos_ret=1.0), _ev(200),
                 pass_probability=65)
    assert res["decision"]["verdict"] == "RISKY"


def test_output_schema():
    res = decide(_report(), _ev(), pass_probability=60)
    assert set(res.keys()) == {"decision", "scores", "thresholds"}
    assert set(res["decision"].keys()) == {"verdict", "confidence", "reason"}
    for k in ("overfit", "stability", "expected_value", "ev_score",
              "pass_probability", "oos_return_pct"):
        assert k in res["scores"]


def test_handles_missing_inputs_gracefully():
    res = decide(validation_report=None, expected_value=None, pass_probability=None)
    assert res["decision"]["verdict"] in ("TRADE", "RISKY", "REJECT")
    assert "confidence" in res["decision"]
    # Nothing known → can't satisfy TRADE, no REJECT trigger → RISKY
    assert res["decision"]["verdict"] == "RISKY"


def test_probability_accepts_wrapper_dict():
    prob = {"pass_probability": 72}
    res = decide(_report(), _ev(), pass_probability=prob)
    assert res["scores"]["pass_probability"] == 72


if __name__ == "__main__":
    test_reject_when_oos_negative()
    test_reject_when_overfit_high()
    test_reject_when_holdout_flag_and_oos_zero()
    test_trade_when_all_green()
    test_risky_when_ev_zero_but_stable()
    test_risky_when_low_stability()
    test_output_schema()
    test_handles_missing_inputs_gracefully()
    test_probability_accepts_wrapper_dict()
    print("decision_engine: ALL TESTS PASSED")

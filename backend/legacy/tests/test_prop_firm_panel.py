"""
Phase 9 — Prop Firm Intelligence Panel tests.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.prop_firm_panel import build_prop_firm_panel
from engines.strategy_ranking_engine import rank_strategies


def _sim(status="pass", reason=None, max_dd=3.5, daily_dd=1.2,
         dd_limit=10.0, daily_limit=5.0, firm="FTMO"):
    return {
        "status": status,
        "failure_reason": reason,
        "max_drawdown_pct": max_dd,
        "max_daily_drawdown_pct": daily_dd,
        "max_total_dd_limit_pct": dd_limit,
        "max_daily_dd_limit_pct": daily_limit,
        "consistency_violated": False,
        "rules_used": {"firm_name": firm},
    }


def _validation(stability=72):
    return {"stability_score": {"score": stability}}


# ── Status rule tests ─────────────────────────────────────────────────

def test_safe_when_no_violations_and_high_prob():
    panel = build_prop_firm_panel(
        simulation=_sim(),
        pass_probability=68,
        validation_report=_validation(72),
        decision={"verdict": "TRADE"},
    )
    assert panel["status"] == "SAFE"
    assert panel["violations"] == {"daily_dd": 0, "max_dd": 0, "consistency": 0,
                                    "profit_target": 0, "min_days": 0}
    assert "Ready for prop firm" in panel["recommendation"]


def test_fail_when_max_dd_violation():
    panel = build_prop_firm_panel(
        simulation=_sim(status="fail", reason="max_total_drawdown", max_dd=11.0),
        pass_probability=60,
    )
    assert panel["status"] == "FAIL"
    assert panel["violations"]["max_dd"] == 1


def test_fail_when_daily_dd_violation():
    panel = build_prop_firm_panel(
        simulation=_sim(status="fail", reason="max_daily_drawdown",
                        daily_dd=6.0, max_dd=3.0),
        pass_probability=60,
    )
    assert panel["status"] == "FAIL"
    assert panel["violations"]["daily_dd"] == 1


def test_fail_when_decision_reject():
    panel = build_prop_firm_panel(
        simulation=_sim(),
        pass_probability=70,
        decision={"verdict": "REJECT"},
    )
    assert panel["status"] == "FAIL"
    assert "rejected" in panel["recommendation"].lower()


def test_risky_when_pass_prob_low():
    panel = build_prop_firm_panel(
        simulation=_sim(),
        pass_probability=35,
        decision={"verdict": "RISKY"},
    )
    assert panel["status"] == "RISKY"
    assert "35" in panel["recommendation"]


def test_soft_violation_detected_from_dd_numbers():
    """Even if failure_reason is empty, DD exceeding limit must be counted."""
    sim = _sim(status="fail", reason=None, max_dd=12.0, dd_limit=10.0)
    panel = build_prop_firm_panel(simulation=sim, pass_probability=60)
    assert panel["violations"]["max_dd"] == 1
    assert panel["status"] == "FAIL"


def test_output_schema_keys_always_present():
    panel = build_prop_firm_panel()
    for key in ("pass_probability", "max_drawdown", "daily_drawdown",
                "consistency_score", "violations", "status", "recommendation"):
        assert key in panel
    assert set(panel["violations"].keys()) == {"daily_dd", "max_dd", "consistency",
                                                 "profit_target", "min_days"}


def test_probability_dict_accepted():
    panel = build_prop_firm_panel(
        simulation=_sim(),
        pass_probability={"pass_probability": 65},
    )
    assert panel["pass_probability"] == 65


def test_consistency_from_validation_report():
    panel = build_prop_firm_panel(
        simulation=_sim(),
        validation_report=_validation(stability=48),
    )
    assert panel["consistency_score"] == 48.0


# ── Ranking engine integration ────────────────────────────────────────

def test_ranking_attaches_panel_when_sim_present():
    pool = [
        {
            "strategy_id": "with_sim",
            "decision": {"verdict": "TRADE"},
            "validation_report": _validation(70),
            "pass_probability": 65,
            "simulation": _sim(),
        },
        {
            "strategy_id": "bare",
            "decision": {"verdict": "TRADE"},
        },
    ]
    ranked = rank_strategies(pool, top_n=5)
    with_sim = next(r for r in ranked if r["strategy_id"] == "with_sim")
    bare = next(r for r in ranked if r["strategy_id"] == "bare")
    assert "prop_firm_panel" in with_sim
    assert with_sim["prop_firm_panel"]["status"] in ("SAFE", "RISKY", "FAIL")
    # Bare strategy has no simulation/validation/decision/pp → still gets attached because decision present
    # (decision alone is enough to build a meaningful panel)
    assert "prop_firm_panel" in bare
    assert bare["prop_firm_panel"]["status"] in ("SAFE", "RISKY", "FAIL")


def test_ranking_attach_panel_disabled():
    pool = [
        {
            "strategy_id": "a",
            "decision": {"verdict": "TRADE"},
            "simulation": _sim(),
        },
    ]
    ranked = rank_strategies(pool, attach_panel=False)
    assert "prop_firm_panel" not in ranked[0]


if __name__ == "__main__":
    test_safe_when_no_violations_and_high_prob()
    test_fail_when_max_dd_violation()
    test_fail_when_daily_dd_violation()
    test_fail_when_decision_reject()
    test_risky_when_pass_prob_low()
    test_soft_violation_detected_from_dd_numbers()
    test_output_schema_keys_always_present()
    test_probability_dict_accepted()
    test_consistency_from_validation_report()
    test_ranking_attaches_panel_when_sim_present()
    test_ranking_attach_panel_disabled()
    print("prop_firm_panel: ALL TESTS PASSED")

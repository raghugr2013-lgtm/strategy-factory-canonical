"""
Phase 8.7 — Strategy Refinement Engine tests.
"""
import os
import sys
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.refinement_engine import (
    refine_strategy, refine_top_candidates, _diagnose_from_reports,
)


def _prices(n=300, seed=7, vol=0.003):
    rng = random.Random(seed)
    p = 1.10
    out = [p]
    for _ in range(n - 1):
        p *= (1.0 + rng.gauss(0, vol))
        out.append(round(p, 5))
    return out


RULES = {
    "initial_balance": 10000,
    "profit_target_pct": 8.0,
    "max_daily_dd_pct": 5.0,
    "max_total_dd_pct": 10.0,
    "min_trading_days": 1,
    "time_limit_days": 0,
    "drawdown_type": "static",
    "name": "FTMO",
}


STRATEGY = (
    "Trend following EMA crossover strategy using fast EMA and slow EMA on EURUSD H1. "
    "Buy when fast EMA crosses above slow EMA. Sell on reverse. RSI filter."
)


# ── Diagnosis coverage ────────────────────────────────────────────────

def test_diagnose_high_dd_from_backtest():
    issues = _diagnose_from_reports(
        validation_report=None,
        decision=None,
        prop_firm_panel=None,
        base_backtest={"max_drawdown_pct": 22.5},
    )
    types = [i["type"] for i in issues]
    assert "high_drawdown" in types


def test_diagnose_overfit_and_low_stability():
    vr = {
        "overfit_score": {"score": 75},
        "stability_score": {"score": 30},
    }
    issues = _diagnose_from_reports(vr, None, None)
    types = [i["type"] for i in issues]
    assert "overfit" in types and "low_stability" in types


def test_diagnose_reject_verdict():
    issues = _diagnose_from_reports(None, {"verdict": "REJECT"}, None)
    assert any(i["type"] == "decision_reject" for i in issues)


def test_diagnose_panel_violations():
    panel = {
        "pass_probability": 20,
        "max_drawdown": 12.0,
        "daily_drawdown": 6.0,
        "violations": {"daily_dd": 1, "max_dd": 1, "consistency": 0,
                       "profit_target": 0, "min_days": 0},
    }
    issues = _diagnose_from_reports(None, None, panel)
    types = {i["type"] for i in issues}
    assert "sim_daily_dd_breach" in types
    assert "sim_total_dd_breach" in types
    assert "low_probability" in types
    assert "high_drawdown" in types


def test_no_issues_returns_nothing_to_refine():
    res = refine_strategy({
        "strategy_text": STRATEGY,
        "pair": "EURUSD", "timeframe": "H1",
        "prices": _prices(200),
        "rules_config": RULES,
        "validation_report": {"overfit_score": {"score": 10},
                              "stability_score": {"score": 80}},
        "decision": {"verdict": "TRADE"},
        "prop_firm_panel": {"pass_probability": 75, "max_drawdown": 3.0,
                             "daily_drawdown": 1.0,
                             "violations": {"daily_dd": 0, "max_dd": 0,
                                            "consistency": 0, "profit_target": 0,
                                            "min_days": 0}},
    })
    assert res["success"] is True
    assert res["improved"] is False
    assert res["cycles_run"] == 0


# ── Guard rails ───────────────────────────────────────────────────────

def test_rejects_missing_prices():
    res = refine_strategy({
        "strategy_text": STRATEGY,
        "pair": "EURUSD", "timeframe": "H1",
        "prices": [], "rules_config": RULES,
        "decision": {"verdict": "REJECT"},
    })
    assert res["success"] is False
    assert "prices" in res["error"].lower() or "60" in res["error"]


def test_rejects_missing_rules():
    res = refine_strategy({
        "strategy_text": STRATEGY, "pair": "EURUSD", "timeframe": "H1",
        "prices": _prices(200), "rules_config": {},
        "decision": {"verdict": "REJECT"},
    })
    assert res["success"] is False
    assert "rules" in res["error"].lower()


def test_rejects_empty_strategy_text():
    res = refine_strategy({"strategy_text": "", "rules_config": RULES,
                            "prices": _prices(200)})
    assert res["success"] is False


# ── End-to-end refinement ─────────────────────────────────────────────

def test_refinement_runs_with_issues_present():
    """
    Feed reports that flag high DD + low probability → engine must attempt
    at least one cycle and return a structured result (improved True/False
    depends on whether mutations actually help on this synthetic series;
    we only assert shape + safe execution).
    """
    res = refine_strategy({
        "strategy_text": STRATEGY,
        "pair": "EURUSD", "timeframe": "H1",
        "prices": _prices(300),
        "rules_config": RULES,
        "validation_report": {"overfit_score": {"score": 60},
                              "stability_score": {"score": 35}},
        "decision": {"verdict": "RISKY"},
        "prop_firm_panel": {
            "pass_probability": 30, "max_drawdown": 14.0,
            "daily_drawdown": 4.0,
            "violations": {"daily_dd": 0, "max_dd": 0, "consistency": 0,
                           "profit_target": 0, "min_days": 0},
        },
        "base_params": {"fast_period": 8, "slow_period": 21,
                        "sl_pips": 20, "tp_pips": 35,
                        "rsi_period": 14, "rsi_buy_threshold": 50,
                        "rsi_sell_threshold": 50},
    }, max_cycles=2, variants_per_cycle=4, mc_simulations=10)

    assert res["success"] is True
    assert "original" in res and "history" in res
    assert isinstance(res["history"], list)
    # Must contain at least one attempted cycle
    assert len(res["history"]) >= 1


def test_refine_top_candidates_wiring():
    ranked = [
        {"strategy_id": "alpha", "score": 72, "verdict": "RISKY"},
        {"strategy_id": "beta", "score": 65, "verdict": "RISKY"},
    ]
    inputs = {
        "alpha": {
            "strategy_text": STRATEGY,
            "pair": "EURUSD", "timeframe": "H1",
            "prices": _prices(250, seed=11), "rules_config": RULES,
            "decision": {"verdict": "RISKY"},
            "prop_firm_panel": {"pass_probability": 35, "max_drawdown": 12.0,
                                "daily_drawdown": 3.5,
                                "violations": {"daily_dd": 0, "max_dd": 0,
                                               "consistency": 0, "profit_target": 0,
                                               "min_days": 0}},
            "base_params": {"sl_pips": 25, "tp_pips": 40,
                            "fast_period": 8, "slow_period": 21},
        }
    }
    out = refine_top_candidates(ranked, inputs, top_n=3, max_cycles=1,
                                variants_per_cycle=3, mc_simulations=8)
    # Only alpha has inputs → only alpha processed
    assert len(out) == 1
    assert out[0]["strategy_id"] == "alpha"
    assert "success" in out[0]


if __name__ == "__main__":
    test_diagnose_high_dd_from_backtest()
    test_diagnose_overfit_and_low_stability()
    test_diagnose_reject_verdict()
    test_diagnose_panel_violations()
    test_no_issues_returns_nothing_to_refine()
    test_rejects_missing_prices()
    test_rejects_missing_rules()
    test_rejects_empty_strategy_text()
    test_refinement_runs_with_issues_present()
    test_refine_top_candidates_wiring()
    print("refinement_engine: ALL TESTS PASSED")

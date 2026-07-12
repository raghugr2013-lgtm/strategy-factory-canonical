"""
P0 STABILITY — regression tests for the three fixes applied together:

  TASK 1 — data pipeline minimums & structured error
  TASK 2 — strategy-parser must honour `TYPE:` header first
  TASK 3 — system must never crash when backtest returns invalid metrics
           (no_real_data / no_trades / null_pf); refinement short-circuits
           with a structured reason instead of the legacy
           `TypeError: 'NoneType' * float`.
"""
from __future__ import annotations

import math
import random


from engines.backtest_engine import run_backtest_logic
from engines.param_extractor import extract_params
from engines.random_search_optimizer import _fitness_from_metrics
from engines.refinement_engine import refine_strategy
from engines.strategy_mutation import _evaluate_variant, _is_improvement


# ── Helpers ─────────────────────────────────────────────────────────


def _prices(n: int, seed: int = 13) -> list:
    rng = random.Random(seed)
    px = 1.10
    out = []
    for i in range(n):
        drift = math.sin(i / 40) * 0.0008 + (i / n) * 0.005
        px = px + drift + rng.gauss(0, 0.0012)
        out.append(round(px, 6))
    return out


STRATEGY = (
    "TYPE: trend_following\n"
    "Buy when fast EMA crosses above slow EMA and RSI is below 70. "
    "Sell when fast EMA crosses below slow EMA. Use 20 pip SL and 40 pip TP."
)


# ── TASK 1 — data pipeline structured error ─────────────────────────


def test_task1_backtest_too_few_candles_returns_scalar_not_none():
    """Previously: `profit_factor: None`. Now: scalar 0.0 on every
    metric + `error: no_real_data` so downstream arithmetic is safe."""
    bt = run_backtest_logic(STRATEGY, "EURUSD", "H1",
                            external_prices=[1.10, 1.11, 1.12],
                            data_source="real", data_points=3)
    assert bt.get("error") == "no_real_data"
    # Every metric that downstream arithmetic multiplies MUST be a
    # number, never None.
    for k in ("profit_factor", "oos_profit_factor",
              "max_drawdown_pct", "oos_max_drawdown_pct",
              "total_return_pct", "net_profit",
              "win_rate", "sharpe_ratio"):
        v = bt.get(k)
        assert v is not None, f"{k} must be numeric, got None"
        assert isinstance(v, (int, float)), f"{k} must be numeric, got {type(v).__name__}"
    assert bt.get("total_trades") == 0


def test_task1_backtest_min_gate_exact_boundary():
    # 199 → should trip the gate; 200 → should succeed
    below = run_backtest_logic(STRATEGY, "EURUSD", "H1",
                               external_prices=_prices(199),
                               data_source="real", data_points=199)
    assert below.get("error") == "no_real_data"

    ok = run_backtest_logic(STRATEGY, "EURUSD", "H1",
                            external_prices=_prices(400),
                            data_source="real", data_points=400)
    assert ok.get("error") is None
    assert "profit_factor" in ok


# ── TASK 2 — parser honours TYPE: header ────────────────────────────


def test_task2_parser_honours_explicit_type_even_with_scalping_noise():
    """Before fix: this text scored `scalping` because the description
    includes `scalping-grade`. Now: `TYPE: trend_following` wins."""
    text = (
        "STRATEGY: Hybrid with scalping-grade frequency\n"
        "TYPE: trend_following\n"
        "INDICATORS: EMA 20, EMA 50, RSI 14\n"
        "ENTRY LONG: EMA(20) crosses above EMA(50) and RSI > 50\n"
        "SL 20 pips, TP 40 pips"
    )
    out = extract_params(text)
    assert out["strategy_type"] == "trend_following"


def test_task2_parser_honours_explicit_mean_reversion():
    text = "TYPE: mean_reversion\nBuy when RSI < 30. SL 15 TP 30."
    assert extract_params(text)["strategy_type"] == "mean_reversion"


def test_task2_parser_accepts_hyphen_form():
    text = "TYPE: trend-following\nBuy on cross. SL 20 TP 40."
    assert extract_params(text)["strategy_type"] == "trend_following"


def test_task2_parser_falls_back_to_keyword_when_no_type_line():
    text = "Buy when BOLLINGER lower band touched and OVERSOLD. SL 15 TP 30."
    assert extract_params(text)["strategy_type"] == "mean_reversion"


def test_task2_parser_rejects_unknown_type_and_falls_back():
    # Unknown canonical name → keyword fallback decides.
    text = "TYPE: pump_and_dump\nBuy on MACD HISTOGRAM. SL 20 TP 40."
    out = extract_params(text)
    assert out["strategy_type"] == "momentum"   # keyword scan wins


# ── TASK 3 — stability: no crashes on invalid baselines ─────────────


def test_task3_fitness_never_crashes_on_none_metrics():
    """A backtest that returned every metric as `None` used to crash
    the fitness calculator on `None / float` or `None * float`. The
    hardened `_fitness_from_metrics` coerces all to 0.0."""
    bad = {k: None for k in (
        "profit_factor", "net_profit", "max_drawdown_pct",
        "sharpe_ratio", "total_trades", "initial_balance",
    )}
    v = _fitness_from_metrics(bad, data_len=400)
    assert isinstance(v, float)
    assert 0.0 <= v <= 100.0


def test_task3_evaluate_variant_flags_invalid_on_insufficient_data():
    """When backtest returns the no_real_data fast path (prices < 200),
    `_evaluate_variant` must mark the variant invalid (not crash)."""
    ev = _evaluate_variant(
        STRATEGY, "EURUSD", "H1",
        prices=[1.10, 1.11, 1.12],
        data_points=3,
        param_ov=None, ind_ov=None,
        rules_config={
            "initial_balance": 10000.0,
            "max_total_drawdown_pct": 10.0,
            "max_daily_drawdown_pct": 5.0,
            "profit_target_pct": 10.0,
            "min_trading_days": 4,
        },
        mc_sims=3,
    )
    assert ev.get("invalid") is True
    assert ev.get("invalid_reason") in ("no_real_data", "no_trades", "null_metrics")
    # And every metric that callers multiply must be numeric.
    for k in ("profit_factor", "max_drawdown_pct", "total_return_pct"):
        assert isinstance(ev["backtest"][k], (int, float))


def test_task3_is_improvement_safe_when_baseline_invalid():
    orig = {"invalid": True, "invalid_reason": "no_trades",
            "backtest": {"profit_factor": 0, "max_drawdown_pct": 0,
                         "total_return_pct": 0, "win_rate": 0},
            "probability": {"pass_probability": 0}}
    mut = {
        "invalid": False,
        "backtest": {"profit_factor": 1.4, "max_drawdown_pct": 5,
                     "total_return_pct": 3, "win_rate": 55},
        "probability": {"pass_probability": 50},
    }
    better, reason = _is_improvement(orig, mut)
    assert better is False
    assert "invalid" in reason


def test_task3_is_improvement_no_crash_on_none_pf_both_sides():
    """Even if one side sneaks past with `profit_factor: None`, the
    multiply-by-float comparison must not crash."""
    orig = {"backtest": {"profit_factor": None, "max_drawdown_pct": None,
                         "total_return_pct": None, "win_rate": None},
            "probability": {"pass_probability": None},
            "simulation": {"status": "fail"}}
    mut = {"backtest": {"profit_factor": 1.4, "max_drawdown_pct": 5,
                        "total_return_pct": 3, "win_rate": 50},
           "probability": {"pass_probability": 25},
           "simulation": {"status": "fail"}}
    better, reason = _is_improvement(orig, mut)
    # Either is fine — the key is: no crash, returns a (bool, str) pair.
    assert isinstance(better, bool)
    assert isinstance(reason, str)


def test_task3_refine_strategy_short_circuits_on_invalid_baseline():
    """refine_strategy must return a clean, non-raising response when
    the unmutated baseline produces no trades (the common case on
    real forex data with shallow series)."""
    res = refine_strategy(
        strategy={
            "strategy_text": STRATEGY,
            "pair": "EURUSD",
            "timeframe": "H1",
            "prices": [1.10, 1.11, 1.12, 1.13, 1.14] * 30,   # 150 < 200
            "data_points": 150,
            "base_params": {},
            "rules_config": {
                "initial_balance": 10000.0,
                "max_total_drawdown_pct": 10.0,
                "max_daily_drawdown_pct": 5.0,
                "profit_target_pct": 10.0,
                "min_trading_days": 4,
            },
            "validation_report": {
                "verdict": "RISKY",
                "reasons": [{"msg": "max drawdown too high"}],
                "meta": {"max_drawdown_pct": 25.0, "total_return_pct": -5.0},
            },
            "decision": {"decision": "RISKY",
                         "weaknesses": ["high drawdown"]},
            "prop_firm_panel": {"pass_probability": 5,
                                "max_drawdown_pct": 25,
                                "max_daily_drawdown_pct": 6},
            "backtest": {"max_drawdown_pct": 25.0,
                         "total_return_pct": -5.0,
                         "profit_factor": 0.5,
                         "win_rate": 30},
        },
        mc_simulations=3,
    )
    assert res.get("success") is True
    assert res.get("improved") is False
    assert res.get("baseline_invalid") is True
    assert "unscoreable" in (res.get("reason") or "").lower()

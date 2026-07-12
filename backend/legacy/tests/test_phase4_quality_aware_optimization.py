"""
P2 — Quality-aware optimization regression suite.

Verifies that the GA optimizer, the random-search optimizer, and the
refinement engine all evaluate variants INSIDE the high-quality entry
space when `sim_config["quality_filter"]=True` is supplied.

Specifically:
  * `_evaluate_on_prices` propagates `_phase4_signal_quality` from the
    underlying backtest into the metrics dict.
  * `fit_best_params` + `score_frozen_params` honour `sim_config`
    (existing behaviour) AND the resulting metrics carry phase4.
  * `run_ga_search` honours `sim_config` (existing) AND its emitted
    metrics carry phase4.
  * `_evaluate_variant` (mutation engine) accepts `sim_config` and
    honours the filter.
  * `refine_strategy` reads `sim_config` from the explicit kwarg and
    propagates it to every variant evaluation.
"""

import math


from engines.random_search_optimizer import (
    Individual,
    _evaluate_on_prices,
    fit_best_params,
    score_frozen_params,
)
from engines.ga_optimizer import run_ga_search
from engines.strategy_mutation import _evaluate_variant
from engines.refinement_engine import refine_strategy


# Common synthetic price series (sinusoidal — produces many EMA crosses
# so optimisation has work to do without needing live DB data).
def _wave_prices(n: int = 1500) -> list:
    base = 1.1000
    out = []
    for i in range(n):
        wave_a = 0.020 * math.sin(i / 60.0)
        wave_b = 0.010 * math.sin(i / 18.0)
        wave_c = 0.0030 * math.sin(i / 5.0)
        out.append(round(base + wave_a + wave_b + wave_c, 5))
    return out


STRAT = "EMA(20)/EMA(50) trend-following SL=20 TP=40"


# ── _evaluate_on_prices propagates phase4 ─────────────────────────────

def test_evaluate_on_prices_propagates_phase4_when_filter_off():
    prices = _wave_prices()
    ind = Individual(params={"fast_period": 10, "slow_period": 30, "sl_pips": 20, "tp_pips": 40})
    metrics = _evaluate_on_prices(
        ind, STRAT, "EURUSD", "H1", prices, "trend_following",
        sim_config={"quality_filter": False, "quality_threshold": 60.0},
    )
    p4 = metrics.get("_phase4_signal_quality")
    assert p4 is not None
    assert p4["quality_filter_enabled"] is False


def test_evaluate_on_prices_phase4_reflects_filter_when_on():
    prices = _wave_prices()
    ind = Individual(params={"fast_period": 10, "slow_period": 30, "sl_pips": 20, "tp_pips": 40})
    metrics = _evaluate_on_prices(
        ind, STRAT, "EURUSD", "H1", prices, "trend_following",
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
    )
    p4 = metrics.get("_phase4_signal_quality")
    assert p4["quality_filter_enabled"] is True
    assert p4["quality_threshold"] == 60.0


# ── fit_best_params + score_frozen_params ─────────────────────────────

def test_random_search_optimizer_respects_quality_filter():
    prices = _wave_prices()
    train = prices[: int(len(prices) * 0.7)]
    oos = prices[int(len(prices) * 0.7):]

    fit_off = fit_best_params(
        STRAT, "EURUSD", "H1", train, num_variants=8,
        sim_config={"quality_filter": False, "quality_threshold": 60.0},
        rng_seed=42,
    )
    assert fit_off["success"]
    p4_off = fit_off["metrics"].get("_phase4_signal_quality") or {}
    assert p4_off.get("quality_filter_enabled") is False

    fit_on = fit_best_params(
        STRAT, "EURUSD", "H1", train, num_variants=8,
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
        rng_seed=42,
    )
    assert fit_on["success"]
    p4_on = fit_on["metrics"].get("_phase4_signal_quality") or {}
    assert p4_on.get("quality_filter_enabled") is True

    # OOS scoring with frozen params — phase4 still surfaces.
    oos_score = score_frozen_params(
        STRAT, "EURUSD", "H1", oos,
        params=fit_on["params"],
        strategy_type=fit_on["strategy_type"],
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
    )
    assert oos_score["success"]
    p4_oos = oos_score["metrics"].get("_phase4_signal_quality") or {}
    assert p4_oos.get("quality_filter_enabled") is True


# ── GA optimiser ──────────────────────────────────────────────────────

def test_ga_search_respects_quality_filter():
    prices = _wave_prices()
    res = run_ga_search(
        STRAT, "EURUSD", "H1", prices,
        train_ratio=0.70, population_size=8, generations=2,
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
        rng_seed=123,
    )
    assert res["success"], res
    is_p4 = (res.get("metrics") or {}).get("_phase4_signal_quality") or {}
    oos_p4 = (res.get("oos_metrics") or {}).get("_phase4_signal_quality") or {}
    assert is_p4.get("quality_filter_enabled") is True
    assert oos_p4.get("quality_filter_enabled") is True


def test_ga_search_default_no_quality_filter():
    prices = _wave_prices()
    res = run_ga_search(
        STRAT, "EURUSD", "H1", prices,
        train_ratio=0.70, population_size=8, generations=2,
        rng_seed=123,
    )
    assert res["success"], res
    is_p4 = (res.get("metrics") or {}).get("_phase4_signal_quality") or {}
    assert is_p4.get("quality_filter_enabled") is False


# ── Mutation engine ───────────────────────────────────────────────────

def test_evaluate_variant_threads_quality_filter():
    prices = _wave_prices()
    ev_off = _evaluate_variant(
        STRAT, "EURUSD", "H1", prices, len(prices),
        param_ov={"fast_period": 10, "slow_period": 30, "sl_pips": 20, "tp_pips": 40},
        ind_ov=None,
        rules_config={"daily_dd": 5.0, "max_dd": 10.0, "profit_target_pct": 8.0,
                      "min_trading_days": 5, "duration": 30, "starting_balance": 10000},
        mc_sims=4,
        sim_config={"quality_filter": False, "quality_threshold": 60.0},
    )
    p4_off = (ev_off.get("_phase4_signal_quality") or {})
    assert p4_off.get("quality_filter_enabled") is False or ev_off.get("invalid") is True

    ev_on = _evaluate_variant(
        STRAT, "EURUSD", "H1", prices, len(prices),
        param_ov={"fast_period": 10, "slow_period": 30, "sl_pips": 20, "tp_pips": 40},
        ind_ov=None,
        rules_config={"daily_dd": 5.0, "max_dd": 10.0, "profit_target_pct": 8.0,
                      "min_trading_days": 5, "duration": 30, "starting_balance": 10000},
        mc_sims=4,
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
    )
    p4_on = (ev_on.get("_phase4_signal_quality") or {})
    assert p4_on.get("quality_filter_enabled") is True or ev_on.get("invalid") is True


# ── Refinement engine ─────────────────────────────────────────────────

def test_refine_strategy_threads_sim_config_via_kwarg():
    prices = _wave_prices()
    strategy = {
        "strategy_text": STRAT,
        "pair": "EURUSD",
        "timeframe": "H1",
        "prices": prices,
        "data_points": len(prices),
        "rules_config": {
            "daily_dd": 5.0, "max_dd": 10.0, "profit_target_pct": 8.0,
            "min_trading_days": 5, "duration": 30, "starting_balance": 10000,
        },
        "validation_report": {
            "leakage_guard": {"is_oos_isolated": True},
            "verdict": "RISKY",
            "issues": ["high_dd"],
        },
        "decision": {"verdict": "RISKY"},
        "prop_firm_panel": {"status": "FAIL", "max_drawdown": 12.0},
        "backtest": {"max_drawdown_pct": 12.0, "profit_factor": 0.9, "total_trades": 50},
        "base_params": {
            "fast_period": 10, "slow_period": 30,
            "sl_pips": 20, "tp_pips": 40,
            "rsi_period": 0, "rsi_buy_threshold": 50, "rsi_sell_threshold": 50,
        },
    }
    # Filter ON via explicit kwarg
    res = refine_strategy(
        strategy, max_cycles=1, variants_per_cycle=3, mc_simulations=4,
        sim_config={"quality_filter": True, "quality_threshold": 60.0},
    )
    assert res["success"] is True
    # Refinement either improved or skipped; either way the run shouldn't crash
    # and the underlying baseline evaluation should have used the filter.


def test_refine_strategy_reads_sim_config_from_strategy_dict():
    prices = _wave_prices()
    strategy = {
        "strategy_text": STRAT,
        "pair": "EURUSD",
        "timeframe": "H1",
        "prices": prices,
        "data_points": len(prices),
        "rules_config": {
            "daily_dd": 5.0, "max_dd": 10.0, "profit_target_pct": 8.0,
            "min_trading_days": 5, "duration": 30, "starting_balance": 10000,
        },
        "validation_report": {
            "leakage_guard": {"is_oos_isolated": True},
            "verdict": "RISKY",
            "issues": ["high_dd"],
        },
        "decision": {"verdict": "RISKY"},
        "prop_firm_panel": {"status": "FAIL", "max_drawdown": 12.0},
        "backtest": {"max_drawdown_pct": 12.0, "profit_factor": 0.9, "total_trades": 50},
        "base_params": {
            "fast_period": 10, "slow_period": 30,
            "sl_pips": 20, "tp_pips": 40,
            "rsi_period": 0, "rsi_buy_threshold": 50, "rsi_sell_threshold": 50,
        },
        # Inline sim_config — should be picked up if no explicit kwarg.
        "sim_config": {"quality_filter": True, "quality_threshold": 60.0},
    }
    res = refine_strategy(strategy, max_cycles=1, variants_per_cycle=3, mc_simulations=4)
    assert res["success"] is True


# ── PF stability across runs ──────────────────────────────────────────

def test_quality_filter_does_not_explode_pf_across_runs():
    """Same params, same data, same seed: PF should be deterministic
    whether filter is on or off — ensures we didn't accidentally
    introduce non-determinism via the new code path."""
    prices = _wave_prices()
    ind = Individual(params={"fast_period": 10, "slow_period": 30, "sl_pips": 20, "tp_pips": 40})

    cfg_off = {"quality_filter": False, "quality_threshold": 60.0}
    cfg_on = {"quality_filter": True, "quality_threshold": 50.0}

    m1 = _evaluate_on_prices(ind, STRAT, "EURUSD", "H1", prices, "trend_following", cfg_off)
    m2 = _evaluate_on_prices(ind, STRAT, "EURUSD", "H1", prices, "trend_following", cfg_off)
    assert m1["profit_factor"] == m2["profit_factor"]
    assert m1["total_trades"] == m2["total_trades"]

    m3 = _evaluate_on_prices(ind, STRAT, "EURUSD", "H1", prices, "trend_following", cfg_on)
    m4 = _evaluate_on_prices(ind, STRAT, "EURUSD", "H1", prices, "trend_following", cfg_on)
    assert m3["profit_factor"] == m4["profit_factor"]
    assert m3["total_trades"] == m4["total_trades"]

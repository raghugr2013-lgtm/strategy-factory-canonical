"""
Random Search Optimization Engine (Phase 1).
Generates 50-100 random parameter variants, evaluates each on a train/test split,
scores by composite fitness (net profit, Sharpe ratio, max drawdown, trade frequency),
and selects the top 10.

Architecture is designed for Genetic Algorithm upgrade (Phase 2):
  - SearchSpace defines per-type parameter ranges with uniform sampling
  - Individual wraps a parameter set + fitness metrics
  - evaluate() is the fitness function (drop-in replacement for GA)
  - select_top() is the selection operator
"""

import math
import random
import logging
from dataclasses import dataclass, field
from engines.backtest_engine import run_backtest_logic
from engines.param_extractor import extract_params

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# Search Space — per-strategy-type parameter ranges
# GA-ready: each param has (min, max, step) for uniform random sampling
# ═══════════════════════════════════════════════════════

SEARCH_SPACES = {
    "trend_following": {
        "fast_period":        (3, 15, 1),
        "slow_period":        (12, 50, 1),
        "rsi_period":         (7, 25, 1),
        "rsi_buy_threshold":  (40, 60, 1),
        "rsi_sell_threshold": (40, 60, 1),
        "sl_pips":            (8, 50, 1),
        "tp_pips":            (15, 80, 1),
    },
    "mean_reversion": {
        "rsi_period":         (7, 25, 1),
        "rsi_buy_threshold":  (15, 40, 1),
        "rsi_sell_threshold": (60, 85, 1),
        "bb_period":          (10, 35, 1),
        "bb_std_dev":         (1.0, 3.0, 0.25),
        "sl_pips":            (8, 40, 1),
        "tp_pips":            (15, 60, 1),
    },
    "momentum": {
        "macd_fast":          (5, 20, 1),
        "macd_slow":          (18, 40, 1),
        "macd_signal":        (5, 15, 1),
        "rsi_period":         (7, 25, 1),
        "rsi_buy_threshold":  (35, 60, 1),
        "rsi_sell_threshold": (40, 65, 1),
        "sl_pips":            (10, 50, 1),
        "tp_pips":            (20, 80, 1),
    },
    "breakout": {
        "fast_period":        (3, 20, 1),
        "rsi_period":         (7, 25, 1),
        "rsi_buy_threshold":  (45, 65, 1),
        "rsi_sell_threshold": (35, 55, 1),
        "sl_pips":            (10, 50, 1),
        "tp_pips":            (20, 80, 1),
    },
    "scalping": {
        "fast_period":        (2, 10, 1),
        "slow_period":        (8, 20, 1),
        "rsi_period":         (7, 20, 1),
        "rsi_buy_threshold":  (40, 55, 1),
        "rsi_sell_threshold": (45, 60, 1),
        "sl_pips":            (5, 20, 1),
        "tp_pips":            (10, 35, 1),
    },
}


@dataclass
class Individual:
    """Single parameter set with fitness metrics. GA-ready chromosome."""
    params: dict
    # Filled after evaluation
    train_metrics: dict = field(default_factory=dict)
    test_metrics: dict = field(default_factory=dict)
    fitness: float = 0.0
    sharpe_ratio: float = 0.0
    overfit_score: float = 0.0
    # P2-stability — filled by `ga_optimizer._evaluate_individual_with_oos`
    # when the GA is in OOS-aware-selection mode. Never populated by the
    # pure random-search path.
    oos_metrics: dict = field(default_factory=dict)
    selection_score: float = 0.0
    pf_gap: float = 0.0


# ═══════════════════════════════════════════════════════
# Random Sampling
# ═══════════════════════════════════════════════════════

def _sample_param(lo, hi, step):
    """Sample a single parameter uniformly within [lo, hi] snapped to step."""
    if step >= 1:
        return random.randint(int(lo), int(hi))
    steps = int(round((hi - lo) / step))
    return round(lo + random.randint(0, steps) * step, 4)


def _generate_random_individual(space: dict, strategy_type: str) -> Individual:
    """Generate one random parameter set from the search space."""
    while True:
        params = {k: _sample_param(*v) for k, v in space.items()}
        if _validate_params(params, strategy_type):
            return Individual(params=params)


def _validate_params(params: dict, strategy_type: str) -> bool:
    """Reject invalid parameter combinations."""
    if "fast_period" in params and "slow_period" in params:
        if params["fast_period"] >= params["slow_period"]:
            return False
    if "sl_pips" in params and "tp_pips" in params:
        if params["sl_pips"] >= params["tp_pips"]:
            return False
    if "macd_fast" in params and "macd_slow" in params:
        if params["macd_fast"] >= params["macd_slow"]:
            return False
    if strategy_type == "mean_reversion":
        if "rsi_buy_threshold" in params and "rsi_sell_threshold" in params:
            if params["rsi_buy_threshold"] >= params["rsi_sell_threshold"]:
                return False
    return True


# ═══════════════════════════════════════════════════════
# Fitness Evaluation
# ═══════════════════════════════════════════════════════

def _params_to_overrides(params: dict) -> tuple:
    """Convert flat params dict to (param_overrides, indicators_override)."""
    overrides = {}
    indicators = {}
    if "fast_period" in params:
        overrides["fast_period"] = params["fast_period"]
    if "slow_period" in params:
        overrides["slow_period"] = params["slow_period"]
    if "sl_pips" in params:
        overrides["sl_pips"] = params["sl_pips"]
    if "tp_pips" in params:
        overrides["tp_pips"] = params["tp_pips"]
    if "rsi_period" in params:
        indicators["rsi"] = {
            "period": params["rsi_period"],
            "buy_threshold": params.get("rsi_buy_threshold", 50),
            "sell_threshold": params.get("rsi_sell_threshold", 50),
        }
    if "macd_fast" in params:
        indicators["macd"] = {
            "fast": params["macd_fast"],
            "slow": params["macd_slow"],
            "signal": params["macd_signal"],
        }
    if "bb_period" in params:
        indicators["bollinger"] = {
            "period": params["bb_period"],
            "std_dev": params["bb_std_dev"],
        }
    return overrides, indicators if indicators else None


def _calc_sharpe(trades: list, initial_balance: float) -> float:
    """
    Annualized Sharpe ratio from trade-level returns.
    Assumes ~252 trading days/year. Returns 0 if <2 trades.
    """
    if len(trades) < 2:
        return 0.0
    returns = [t["net_pnl"] / initial_balance for t in trades]
    mean_r = sum(returns) / len(returns)
    if len(returns) < 2:
        return 0.0
    variance = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
    std_r = math.sqrt(variance)
    if std_r < 1e-10:
        return 0.0
    # Annualize: assume ~252 trades/year as proxy
    annualized = (mean_r / std_r) * math.sqrt(min(len(trades), 252))
    return round(annualized, 3)


def _calc_trade_frequency_score(total_trades: int, data_points: int) -> float:
    """
    Score trade frequency 0-100. Sweet spot is 0.5-3 trades per 100 bars.
    Too few (<5 total) or too many (>10% of bars) gets penalized.
    """
    if data_points == 0 or total_trades == 0:
        return 0.0
    ratio = total_trades / data_points * 100  # trades per 100 bars
    if ratio < 0.1:
        return 10.0  # too few
    if ratio <= 0.5:
        return 30.0 + (ratio / 0.5) * 40.0
    if ratio <= 3.0:
        return 70.0 + min(30.0, (1.0 - abs(ratio - 1.5) / 1.5) * 30.0)
    if ratio <= 10.0:
        return max(10.0, 70.0 - (ratio - 3.0) * 8.0)
    return 5.0  # overtrading


def _evaluate(
    individual: Individual,
    strategy_text: str,
    pair: str,
    timeframe: str,
    train_prices: list,
    test_prices: list,
    strategy_type: str,
    sim_config: dict,
) -> Individual:
    """
    Evaluate an individual on TRAIN data, then validate on TEST data.
    Composite fitness scored on TRAIN results; overfit_score from train vs test gap.
    """
    param_ov, ind_ov = _params_to_overrides(individual.params)

    # ── Train backtest ──
    train_bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=train_prices,
        data_source="real_train",
        data_points=len(train_prices),
        sim_config=sim_config,
        param_overrides=param_ov if param_ov else None,
        indicators_override=ind_ov,
        strategy_type_override=strategy_type,
    )

    # ── Test backtest ──
    test_bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=test_prices,
        data_source="real_test",
        data_points=len(test_prices),
        sim_config=sim_config,
        param_overrides=param_ov if param_ov else None,
        indicators_override=ind_ov,
        strategy_type_override=strategy_type,
    )

    train_trades = train_bt.get("trades", [])
    test_trades = test_bt.get("trades", [])
    initial_bal = train_bt.get("initial_balance", 10000.0)

    train_sharpe = _calc_sharpe(train_trades, initial_bal)
    test_sharpe = _calc_sharpe(test_trades, initial_bal)

    # ── Composite fitness (on TRAIN data) ──
    # Weights: net_profit 25%, sharpe 30%, drawdown 25%, frequency 20%
    net_profit = train_bt.get("net_profit", 0)
    max_dd_pct = train_bt.get("max_drawdown_pct", 0)
    total_trades = train_bt.get("total_trades", 0)

    profit_score = max(0, min(100, 50 + net_profit / (initial_bal * 0.002)))
    sharpe_score = max(0, min(100, 50 + train_sharpe * 20))
    dd_score = max(0, 100 - max_dd_pct * 4)
    freq_score = _calc_trade_frequency_score(total_trades, len(train_prices))

    fitness = round(
        profit_score * 0.25 +
        sharpe_score * 0.30 +
        dd_score * 0.25 +
        freq_score * 0.20,
        2,
    )

    # ── Overfit detection ──
    train_ret = train_bt.get("total_return_pct", 0)
    test_ret = test_bt.get("total_return_pct", 0)
    if train_ret > 0:
        overfit_ratio = 1.0 - (test_ret / train_ret) if train_ret != 0 else 0
    else:
        overfit_ratio = 0.0 if test_ret <= 0 else -1.0
    overfit_score = round(max(0, min(1, overfit_ratio)), 3)

    individual.train_metrics = {
        "net_profit": train_bt.get("net_profit", 0),
        "total_return_pct": round(train_ret, 2),
        "win_rate": train_bt.get("win_rate", 0),
        "total_trades": total_trades,
        "max_drawdown_pct": round(max_dd_pct, 2),
        "profit_factor": train_bt.get("profit_factor", 0),
        "sharpe_ratio": train_sharpe,
        "total_costs": train_bt.get("total_costs", 0),
        "equity_curve": train_bt.get("equity_curve", []),
    }
    individual.test_metrics = {
        "net_profit": test_bt.get("net_profit", 0),
        "total_return_pct": round(test_ret, 2),
        "win_rate": test_bt.get("win_rate", 0),
        "total_trades": test_bt.get("total_trades", 0),
        "max_drawdown_pct": round(test_bt.get("max_drawdown_pct", 0), 2),
        "profit_factor": test_bt.get("profit_factor", 0),
        "sharpe_ratio": test_sharpe,
        "total_costs": test_bt.get("total_costs", 0),
        "equity_curve": test_bt.get("equity_curve", []),
    }
    individual.fitness = fitness
    individual.sharpe_ratio = train_sharpe
    individual.overfit_score = overfit_score

    return individual


# ═══════════════════════════════════════════════════════
# Phase 8 — Leakage-free helpers (reusable by walk-forward / holdout)
# ═══════════════════════════════════════════════════════

def _evaluate_on_prices(
    individual: Individual,
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    strategy_type: str,
    sim_config: dict,
    label: str = "is",
) -> dict:
    """
    Run a single backtest with frozen params on ONE price slice and return
    a compact metrics dict. Used by walk-forward / holdout so we can score
    on IS *only* during selection, and on OOS *only* after params are frozen.
    No cross-contamination.
    """
    param_ov, ind_ov = _params_to_overrides(individual.params)
    bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=prices,
        data_source=f"real_{label}",
        data_points=len(prices),
        sim_config=sim_config,
        param_overrides=param_ov if param_ov else None,
        indicators_override=ind_ov,
        strategy_type_override=strategy_type,
    )
    trades = bt.get("trades", [])
    initial_bal = bt.get("initial_balance", 10000.0)
    sharpe = _calc_sharpe(trades, initial_bal)
    return {
        "net_profit": bt.get("net_profit", 0),
        "total_return_pct": round(bt.get("total_return_pct", 0), 2),
        "win_rate": bt.get("win_rate", 0),
        "total_trades": bt.get("total_trades", 0),
        "max_drawdown_pct": round(bt.get("max_drawdown_pct", 0), 2),
        "profit_factor": bt.get("profit_factor", 0),
        "sharpe_ratio": sharpe,
        "total_costs": bt.get("total_costs", 0),
        "initial_balance": initial_bal,
        "final_balance": bt.get("final_balance", initial_bal),
        # P2 — propagate signal-quality telemetry from the underlying
        # backtest so GA / random-search optimisation paths can surface
        # avg_score and filter % alongside their PF/DD numbers.
        "_phase4_signal_quality": bt.get("_phase4_signal_quality"),
    }


def _fitness_from_metrics(metrics: dict, data_len: int) -> float:
    """Composite fitness from IS metrics ONLY. No OOS input allowed here.

    P0 hardening: coerces every metric to a float with 0.0 fallback so a
    backtest that returned `None` for any field can never crash the
    arithmetic. Invalid / no-trade backtests land at fitness ~= 50 but
    with near-zero trade-frequency score, so they lose to any real
    competitor.
    """
    def _f(k: str, default: float = 0.0) -> float:
        v = metrics.get(k, default)
        try:
            return float(v) if v is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    initial_bal = _f("initial_balance", 10000.0) or 10000.0
    profit_score = max(0, min(100, 50 + _f("net_profit") / (initial_bal * 0.002)))
    sharpe_score = max(0, min(100, 50 + _f("sharpe_ratio") * 20))
    dd_score = max(0, 100 - _f("max_drawdown_pct") * 4)
    freq_score = _calc_trade_frequency_score(int(_f("total_trades")), data_len)
    return round(
        profit_score * 0.25 + sharpe_score * 0.30 + dd_score * 0.25 + freq_score * 0.20,
        2,
    )


def fit_best_params(
    strategy_text: str,
    pair: str,
    timeframe: str,
    train_prices: list,
    num_variants: int = 50,
    sim_config: dict = None,
    rng_seed: int = None,
) -> dict:
    """
    STRICT in-sample parameter fitting.
    Runs num_variants random backtests on train_prices ONLY, picks the best
    by fitness, and returns {params, metrics, fitness, strategy_type}.

    This function NEVER sees test/OOS data. It is the canonical building
    block for walk-forward and holdout engines.
    """
    if not train_prices or len(train_prices) < 30:
        return {
            "success": False,
            "error": f"fit_best_params requires >=30 candles, got {len(train_prices) if train_prices else 0}",
        }

    if rng_seed is not None:
        random.seed(rng_seed)

    sim_config = sim_config or {}
    extraction = extract_params(strategy_text)
    strategy_type = extraction.get("strategy_type", "trend_following")
    space = SEARCH_SPACES.get(strategy_type, SEARCH_SPACES["trend_following"])

    best = None
    best_fit = float("-inf")
    evaluated = 0
    for _ in range(max(5, int(num_variants))):
        ind = _generate_random_individual(space, strategy_type)
        metrics = _evaluate_on_prices(
            ind, strategy_text, pair, timeframe,
            train_prices, strategy_type, sim_config, label="is",
        )
        fit = _fitness_from_metrics(metrics, len(train_prices))
        evaluated += 1
        if fit > best_fit:
            best_fit = fit
            best = {"individual": ind, "metrics": metrics, "fitness": fit}

    if best is None:
        return {"success": False, "error": "No variant evaluated"}

    return {
        "success": True,
        "strategy_type": strategy_type,
        "params": best["individual"].params,
        "metrics": best["metrics"],
        "fitness": best["fitness"],
        "variants_evaluated": evaluated,
    }


def score_frozen_params(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    params: dict,
    strategy_type: str,
    sim_config: dict = None,
) -> dict:
    """
    STRICT out-of-sample scoring with FROZEN params.
    Never sees IS data. Never re-optimises. Pure replay on an unseen slice.
    """
    if not prices or len(prices) < 15:
        return {
            "success": False,
            "error": f"score_frozen_params requires >=15 candles, got {len(prices) if prices else 0}",
        }
    sim_config = sim_config or {}
    # Wrap raw params back into an Individual so we can reuse _evaluate_on_prices
    ind = Individual(params=dict(params))
    metrics = _evaluate_on_prices(
        ind, strategy_text, pair, timeframe,
        prices, strategy_type, sim_config, label="oos",
    )
    return {"success": True, "metrics": metrics, "params": dict(params)}


# ═══════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════

def run_random_search(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    num_variants: int = 75,
    train_ratio: float = 0.70,
    sim_config: dict = None,
) -> dict:
    """
    Random Search Optimization (Phase 1).

    1. Enforce real data (reject if prices is None or too short)
    2. Split prices into train (70%) / test (30%)
    3. Extract strategy type from text
    4. Generate num_variants random parameter sets
    5. Evaluate each on train, validate on test
    6. Score composite fitness; rank; return top 10

    Returns dict with results, top_10, train_test_info, overfit warnings.
    """
    # ── Validate real data ──
    if not prices or len(prices) < 60:
        return {
            "success": False,
            "error": f"Optimization requires real historical data. Found {len(prices) if prices else 0} candles, need at least 60. Download data via Market Data tab first.",
            "method": "random_search",
        }

    num_variants = max(20, min(num_variants, 200))
    sim_config = sim_config or {}

    # ── Train/test split ──
    split_idx = int(len(prices) * train_ratio)
    train_prices = prices[:split_idx]
    test_prices = prices[split_idx:]

    if len(train_prices) < 30 or len(test_prices) < 15:
        return {
            "success": False,
            "error": f"Insufficient data for train/test split. Train: {len(train_prices)}, Test: {len(test_prices)}. Need at least 30 train + 15 test candles.",
            "method": "random_search",
        }

    # ── Detect strategy type ──
    extraction = extract_params(strategy_text)
    strategy_type = extraction.get("strategy_type", "trend_following")
    space = SEARCH_SPACES.get(strategy_type, SEARCH_SPACES["trend_following"])

    logger.info(
        f"RandomSearch: type={strategy_type}, variants={num_variants}, "
        f"train={len(train_prices)}, test={len(test_prices)}"
    )

    # ── Generate + evaluate random individuals ──
    population = []
    for i in range(num_variants):
        ind = _generate_random_individual(space, strategy_type)
        _evaluate(ind, strategy_text, pair, timeframe,
                  train_prices, test_prices, strategy_type, sim_config)
        population.append(ind)

    # ── Sort by fitness descending ──
    # NOTE (Phase 8 — leakage guard):
    # `x.fitness` is computed inside `_evaluate` using TRAIN metrics ONLY
    # (net_profit, sharpe, max_dd, trade frequency — all on train_prices).
    # The test_metrics dict is computed for REPORTING only (overfit_score,
    # test_return_pct) and is NEVER used in selection. Do not change this.
    population.sort(key=lambda x: x.fitness, reverse=True)

    # ── Build results ──
    top_n = 10
    top_10 = []
    for rank, ind in enumerate(population[:top_n], 1):
        top_10.append({
            "rank": rank,
            "parameters": ind.params,
            "fitness": ind.fitness,
            "sharpe_ratio": ind.sharpe_ratio,
            "overfit_score": ind.overfit_score,
            "train": ind.train_metrics,
            "test": ind.test_metrics,
            "fitness_breakdown": {
                "profit": round(max(0, min(100, 50 + ind.train_metrics["net_profit"] / (sim_config.get("initial_balance", 10000) * 0.002))) * 0.25, 1),
                "sharpe": round(max(0, min(100, 50 + ind.sharpe_ratio * 20)) * 0.30, 1),
                "drawdown": round(max(0, 100 - ind.train_metrics["max_drawdown_pct"] * 4) * 0.25, 1),
                "frequency": round(_calc_trade_frequency_score(ind.train_metrics["total_trades"], len(train_prices)) * 0.20, 1),
            },
        })

    # ── Population statistics ──
    all_fitness = [ind.fitness for ind in population]
    all_sharpe = [ind.sharpe_ratio for ind in population]
    profitable_train = sum(1 for ind in population if ind.train_metrics.get("net_profit", 0) > 0)
    profitable_test = sum(1 for ind in population if ind.test_metrics.get("net_profit", 0) > 0)
    avg_overfit = sum(ind.overfit_score for ind in population) / len(population) if population else 0

    # ── Overfit warnings ──
    warnings = []
    best = population[0] if population else None
    if best and best.overfit_score > 0.5:
        warnings.append(
            f"High overfitting risk: best variant's test return is {best.test_metrics['total_return_pct']}% "
            f"vs train {best.train_metrics['total_return_pct']}% (overfit score {best.overfit_score})"
        )
    if best and best.test_metrics.get("net_profit", 0) < 0 and best.train_metrics.get("net_profit", 0) > 0:
        warnings.append("Best variant is profitable on train but negative on test — likely overfitted")
    if avg_overfit > 0.4:
        warnings.append(f"Average overfit score across population is high ({avg_overfit:.2f})")
    if profitable_test < num_variants * 0.2:
        warnings.append(f"Only {profitable_test}/{num_variants} variants are profitable on test data")

    return {
        "success": True,
        "method": "random_search",
        "strategy_type": strategy_type,
        "num_variants": num_variants,
        "train_test_split": {
            "train_candles": len(train_prices),
            "test_candles": len(test_prices),
            "train_ratio": round(train_ratio, 2),
            "total_candles": len(prices),
        },
        "top_10": top_10,
        "best": top_10[0] if top_10 else None,
        "population_stats": {
            "mean_fitness": round(sum(all_fitness) / len(all_fitness), 2) if all_fitness else 0,
            "max_fitness": round(max(all_fitness), 2) if all_fitness else 0,
            "min_fitness": round(min(all_fitness), 2) if all_fitness else 0,
            "mean_sharpe": round(sum(all_sharpe) / len(all_sharpe), 3) if all_sharpe else 0,
            "profitable_on_train": profitable_train,
            "profitable_on_test": profitable_test,
            "avg_overfit_score": round(avg_overfit, 3),
        },
        "scoring_weights": {
            "net_profit": 0.25,
            "sharpe_ratio": 0.30,
            "max_drawdown": 0.25,
            "trade_frequency": 0.20,
        },
        "warnings": warnings,
        "search_space": {k: {"min": v[0], "max": v[1], "step": v[2]} for k, v in space.items()},
        # GA-ready metadata
        "_ga_ready": {
            "population_size": num_variants,
            "chromosome_length": len(space),
            "selection_method": "top_k",
            "crossover": "not_implemented",
            "mutation": "not_implemented",
            "generations": 1,
            "upgrade_path": "Replace run_random_search loop with generational GA: select parents -> crossover -> mutate -> evaluate -> repeat",
        },
    }

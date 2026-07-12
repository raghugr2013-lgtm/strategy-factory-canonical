"""
Strategy-type-aware Optimization Engine.
Detects strategy type, builds indicator-specific parameter grids,
and optimizes only the parameters relevant to each strategy's signal logic.

Supported grids:
  - trend_following: EMA fast/slow, RSI period/thresholds, SL, TP
  - mean_reversion: RSI period/thresholds, BB period/std_dev, SL, TP
  - momentum: MACD fast/slow/signal, RSI period/threshold, SL, TP
  - breakout: EMA fast, RSI thresholds, SL, TP
"""
import logging
from itertools import product
from engines.backtest_engine import run_backtest_logic
from engines.ranking_engine import calculate_score
from engines.param_extractor import extract_params

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# Strategy-type-specific parameter grids
# ═══════════════════════════════════════════════════════

GRID_TREND_FOLLOWING = {
    "fast_period": [5, 8, 10],
    "slow_period": [13, 20, 25],
    "rsi_period": [10, 14],
    "rsi_buy_threshold": [45, 50, 55],
    "rsi_sell_threshold": [45, 50, 55],
    "sl_pips": [15, 20, 30],
    "tp_pips": [25, 35, 50],
}

GRID_MEAN_REVERSION = {
    "rsi_period": [10, 14, 20],
    "rsi_buy_threshold": [25, 30, 35],
    "rsi_sell_threshold": [65, 70, 75],
    "bb_period": [15, 20, 25],
    "bb_std_dev": [1.5, 2.0, 2.5],
    "sl_pips": [10, 15, 20],
    "tp_pips": [20, 25, 35],
}

GRID_MOMENTUM = {
    "macd_fast": [8, 12, 16],
    "macd_slow": [21, 26, 30],
    "macd_signal": [7, 9, 12],
    "rsi_period": [10, 14],
    "rsi_buy_threshold": [40, 50],
    "rsi_sell_threshold": [50, 60],
    "sl_pips": [15, 20, 30],
    "tp_pips": [30, 40, 55],
}

GRID_BREAKOUT = {
    "fast_period": [5, 8, 13],
    "rsi_period": [10, 14],
    "rsi_buy_threshold": [50, 55, 60],
    "rsi_sell_threshold": [40, 45, 50],
    "sl_pips": [15, 20, 30],
    "tp_pips": [30, 40, 55],
}

GRID_SCALPING = {
    "fast_period": [3, 5, 7],
    "slow_period": [10, 13, 15],
    "rsi_period": [10, 14],
    "rsi_buy_threshold": [45, 50],
    "rsi_sell_threshold": [50, 55],
    "sl_pips": [8, 10, 15],
    "tp_pips": [14, 18, 25],
}

TYPE_GRIDS = {
    "trend_following": GRID_TREND_FOLLOWING,
    "mean_reversion": GRID_MEAN_REVERSION,
    "momentum": GRID_MOMENTUM,
    "breakout": GRID_BREAKOUT,
    "scalping": GRID_SCALPING,
}


def _combo_to_overrides(combo: dict, strategy_type: str) -> tuple:
    """
    Split a flat parameter combo into (param_overrides, indicators_override)
    that the backtest engine expects.
    """
    param_overrides = {}
    indicators = {}

    # Core MA params
    if "fast_period" in combo:
        param_overrides["fast_period"] = combo["fast_period"]
    if "slow_period" in combo:
        param_overrides["slow_period"] = combo["slow_period"]
    if "sl_pips" in combo:
        param_overrides["sl_pips"] = combo["sl_pips"]
    if "tp_pips" in combo:
        param_overrides["tp_pips"] = combo["tp_pips"]

    # RSI params
    if "rsi_period" in combo:
        indicators["rsi"] = {
            "period": combo["rsi_period"],
            "buy_threshold": combo.get("rsi_buy_threshold", 50),
            "sell_threshold": combo.get("rsi_sell_threshold", 50),
        }

    # MACD params
    if "macd_fast" in combo:
        indicators["macd"] = {
            "fast": combo["macd_fast"],
            "slow": combo["macd_slow"],
            "signal": combo["macd_signal"],
        }

    # Bollinger Bands params
    if "bb_period" in combo:
        indicators["bollinger"] = {
            "period": combo["bb_period"],
            "std_dev": combo["bb_std_dev"],
        }

    return param_overrides, indicators if indicators else None


def _validate_combo(combo: dict, strategy_type: str) -> bool:
    """Reject invalid parameter combinations."""
    # fast < slow for EMA
    if "fast_period" in combo and "slow_period" in combo:
        if combo["fast_period"] >= combo["slow_period"]:
            return False
    # SL < TP
    if "sl_pips" in combo and "tp_pips" in combo:
        if combo["sl_pips"] >= combo["tp_pips"]:
            return False
    # MACD fast < slow
    if "macd_fast" in combo and "macd_slow" in combo:
        if combo["macd_fast"] >= combo["macd_slow"]:
            return False
    # RSI buy < sell for mean_reversion (buy on oversold, sell on overbought)
    if strategy_type == "mean_reversion":
        if "rsi_buy_threshold" in combo and "rsi_sell_threshold" in combo:
            if combo["rsi_buy_threshold"] >= combo["rsi_sell_threshold"]:
                return False
    return True


def _build_typed_variations(
    grid: dict, strategy_type: str, base_combo: dict, max_variations: int = 120
) -> list:
    """Build all valid combinations from a strategy-type-specific grid."""
    keys = list(grid.keys())
    all_combos = list(product(*[grid[k] for k in keys]))

    variations = []
    for combo_tuple in all_combos:
        combo = dict(zip(keys, combo_tuple))
        if not _validate_combo(combo, strategy_type):
            continue
        variations.append(combo)

    # Include base params as variation #0, but only if valid
    # Restrict base_combo to keys in the grid so comparison is fair
    if base_combo:
        base_grid_only = {k: base_combo[k] for k in keys if k in base_combo}
        if _validate_combo(base_grid_only, strategy_type) and base_grid_only not in variations:
            variations.insert(0, base_grid_only)

    return variations[:max_variations]


def _extract_base_combo(extraction: dict, strategy_type: str) -> dict:
    """Build a base combo dict from extracted parameters for comparison."""
    base = {}
    overrides = extraction.get("overrides") or {}
    indicators = extraction.get("indicators") or {}

    # Core params
    if "fast_period" in overrides:
        base["fast_period"] = overrides["fast_period"]
    if "slow_period" in overrides:
        base["slow_period"] = overrides["slow_period"]
    if "sl_pips" in overrides:
        base["sl_pips"] = overrides["sl_pips"]
    if "tp_pips" in overrides:
        base["tp_pips"] = overrides["tp_pips"]

    # RSI
    if "rsi" in indicators:
        base["rsi_period"] = indicators["rsi"]["period"]
        base["rsi_buy_threshold"] = indicators["rsi"]["buy_threshold"]
        base["rsi_sell_threshold"] = indicators["rsi"]["sell_threshold"]

    # MACD
    if "macd" in indicators:
        base["macd_fast"] = indicators["macd"]["fast"]
        base["macd_slow"] = indicators["macd"]["slow"]
        base["macd_signal"] = indicators["macd"]["signal"]

    # BB
    if "bollinger" in indicators:
        base["bb_period"] = indicators["bollinger"]["period"]
        base["bb_std_dev"] = indicators["bollinger"]["std_dev"]

    return base


def _combo_to_display(combo: dict, strategy_type: str) -> dict:
    """Format a combo dict for display in results."""
    display = {}
    if "fast_period" in combo:
        display["fast_period"] = combo["fast_period"]
    if "slow_period" in combo:
        display["slow_period"] = combo["slow_period"]
    display["sl_pips"] = combo.get("sl_pips")
    display["tp_pips"] = combo.get("tp_pips")
    if "rsi_period" in combo:
        display["rsi_period"] = combo["rsi_period"]
        display["rsi_buy_threshold"] = combo.get("rsi_buy_threshold")
        display["rsi_sell_threshold"] = combo.get("rsi_sell_threshold")
    if "macd_fast" in combo:
        display["macd_fast"] = combo["macd_fast"]
        display["macd_slow"] = combo["macd_slow"]
        display["macd_signal"] = combo["macd_signal"]
    if "bb_period" in combo:
        display["bb_period"] = combo["bb_period"]
        display["bb_std_dev"] = combo["bb_std_dev"]
    return {k: v for k, v in display.items() if v is not None}


def run_optimization(
    strategy_text: str,
    pair: str,
    timeframe: str,
    sim_config: dict = None,
    external_prices: list = None,
    data_source: str = "sample",
    data_points: int = 0,
) -> dict:
    """
    Run strategy-type-aware parameter optimization.
    Detects strategy type, builds the right grid, and only optimizes
    parameters that the strategy's signal logic actually uses.
    """
    # Step 1: Extract strategy type and base params from text
    extraction = extract_params(strategy_text)
    strategy_type = extraction.get("strategy_type", "trend_following")
    base_combo = _extract_base_combo(extraction, strategy_type)

    logger.info(f"Optimization: type={strategy_type}, base_combo={base_combo}")

    # Step 2: Run baseline backtest (no overrides — uses extracted params)
    base_bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=external_prices,
        data_source=data_source,
        data_points=data_points,
        sim_config=sim_config,
    )

    # Fill in any missing base params from actual backtest results
    bt_params = base_bt.get("parameters", {})
    if "fast_period" not in base_combo:
        base_combo["fast_period"] = bt_params.get("fast_sma", 8)
    if "slow_period" not in base_combo:
        base_combo["slow_period"] = bt_params.get("slow_sma", 21)
    if "sl_pips" not in base_combo:
        base_combo["sl_pips"] = bt_params.get("stop_loss_pips", 20)
    if "tp_pips" not in base_combo:
        base_combo["tp_pips"] = bt_params.get("take_profit_pips", 35)

    # Default indicator params if not extracted
    if strategy_type in ("trend_following", "mean_reversion", "momentum", "breakout", "scalping"):
        if "rsi_period" not in base_combo:
            base_combo["rsi_period"] = 14
            base_combo["rsi_buy_threshold"] = 50
            base_combo["rsi_sell_threshold"] = 50
            if strategy_type == "mean_reversion":
                base_combo["rsi_buy_threshold"] = 30
                base_combo["rsi_sell_threshold"] = 70

    # Auto-correct inverted RSI thresholds for mean_reversion
    # (extraction sometimes reverses buy/sell for counter-trend strategies)
    if strategy_type == "mean_reversion":
        bt = base_combo.get("rsi_buy_threshold", 30)
        st = base_combo.get("rsi_sell_threshold", 70)
        if bt > st:
            base_combo["rsi_buy_threshold"] = st
            base_combo["rsi_sell_threshold"] = bt
    if strategy_type == "momentum" and "macd_fast" not in base_combo:
        base_combo["macd_fast"] = 12
        base_combo["macd_slow"] = 26
        base_combo["macd_signal"] = 9
    if strategy_type == "mean_reversion" and "bb_period" not in base_combo:
        base_combo["bb_period"] = 20
        base_combo["bb_std_dev"] = 2.0

    # Step 3: Select grid based on strategy type
    grid = TYPE_GRIDS.get(strategy_type, GRID_TREND_FOLLOWING)
    variations = _build_typed_variations(grid, strategy_type, base_combo)

    logger.info(f"Optimization: {len(variations)} variations for {strategy_type}")

    # Step 4: Backtest each variation
    results = []
    for i, combo in enumerate(variations):
        param_ov, ind_ov = _combo_to_overrides(combo, strategy_type)

        bt = run_backtest_logic(
            strategy_text, pair, timeframe,
            external_prices=external_prices,
            data_source=data_source,
            data_points=data_points,
            sim_config=sim_config,
            param_overrides=param_ov if param_ov else None,
            indicators_override=ind_ov,
            strategy_type_override=strategy_type,
        )
        scoring = calculate_score(bt)

        is_original = (combo == base_combo)

        results.append({
            "variation_id": i,
            "parameters": _combo_to_display(combo, strategy_type),
            "metrics": {
                "net_profit": bt.get("net_profit", 0),
                "total_return_pct": bt.get("total_return_pct", 0),
                "win_rate": bt.get("win_rate", 0),
                "total_trades": bt.get("total_trades", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "max_drawdown_pips": bt.get("max_drawdown_pips", 0),
                "profit_factor": bt.get("profit_factor", 0),
                "risk_adjusted_return": bt.get("risk_adjusted_return", 0),
                "total_pnl_pips": bt.get("total_pnl_pips", 0),
            },
            "score": scoring["score"],
            "grade": scoring["grade"],
            "score_breakdown": scoring["breakdown"],
            "is_original": is_original,
        })

    # Step 5: Sort and rank
    results.sort(key=lambda x: x["score"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
        r["is_best"] = (i == 0)

    original = next((r for r in results if r["is_original"]), None)
    best = results[0] if results else None

    # Calculate improvement
    improvement = None
    if original and best and not best["is_original"]:
        improvement = {
            "score_delta": round(best["score"] - original["score"], 1),
            "profit_delta": round(
                best["metrics"]["net_profit"] - original["metrics"]["net_profit"], 2
            ),
            "original_rank": original["rank"],
        }

    return {
        "strategy_type": strategy_type,
        "total_variations": len(results),
        "best": best,
        "top_5": results[:5],
        "original": original,
        "improvement": improvement,
        "all_results": results[:20],
        "grid_used": list(grid.keys()),
    }

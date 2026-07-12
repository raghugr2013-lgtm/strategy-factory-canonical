"""
Strategy Validation Engine.
Walk-forward testing, multi-period backtesting, and Monte Carlo
trade resampling for robustness analysis.
Reuses existing backtest engine for each segment.

Phase 8 — supports modes:
  * "basic"        (default, unchanged legacy behaviour)
  * "walk_forward" (true rolling WF with IS/OOS separation)
  * "holdout"      (strict 80/20 train/OOS)
  * "full"         (basic + walk_forward + holdout composed via validation_report)
"""
import math
from engines.backtest_engine import run_backtest_logic
from engines.monte_carlo_engine import run_monte_carlo
from engines.safety_engine import run_safety_analysis


MAX_SEGMENTS = 6
MIN_CANDLES_PER_SEGMENT = 30


def _split_into_segments(prices: list, num_segments: int) -> list:
    """Split price list into equal-sized segments."""
    n = len(prices)
    seg_size = n // num_segments
    segments = []
    for i in range(num_segments):
        start = i * seg_size
        end = start + seg_size if i < num_segments - 1 else n
        segments.append(prices[start:end])
    return segments


def _calc_stability_score(segment_results: list) -> dict:
    """
    Calculate stability metrics from segment backtest results.
    Returns a 0-100 stability score and breakdown.
    """
    if not segment_results:
        return {"score": 0, "breakdown": {}}

    returns = [r["total_return_pct"] for r in segment_results]
    win_rates = [r["win_rate"] for r in segment_results]
    drawdowns = [r["max_drawdown_pct"] for r in segment_results]
    profits = [r["net_profit"] for r in segment_results]

    # 1. Consistency: % of profitable segments (0-30 pts)
    profitable_segs = sum(1 for p in profits if p > 0)
    consistency_pct = (profitable_segs / len(profits)) * 100
    consistency_score = min(30, (consistency_pct / 100) * 30)

    # 2. Return stability: low std dev of returns is good (0-25 pts)
    if len(returns) > 1:
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(variance)
        # Lower std = more stable. Score inversely proportional to coefficient of variation
        cv = (std_ret / abs(mean_ret)) if abs(mean_ret) > 0.01 else std_ret
        return_stability = max(0, min(25, 25 - cv * 5))
    else:
        return_stability = 12.5

    # 3. Drawdown stability: consistent drawdown levels (0-25 pts)
    if len(drawdowns) > 1:
        mean_dd = sum(drawdowns) / len(drawdowns)
        dd_variance = sum((d - mean_dd) ** 2 for d in drawdowns) / len(drawdowns)
        dd_std = math.sqrt(dd_variance)
        # Low DD and low DD variation = good
        dd_score = max(0, min(25, 25 - mean_dd * 0.5 - dd_std * 2))
    else:
        dd_score = 12.5

    # 4. Win rate consistency (0-20 pts)
    if len(win_rates) > 1:
        mean_wr = sum(win_rates) / len(win_rates)
        wr_variance = sum((w - mean_wr) ** 2 for w in win_rates) / len(win_rates)
        wr_std = math.sqrt(wr_variance)
        wr_score = max(0, min(20, 20 - wr_std * 0.5))
    else:
        wr_score = 10

    total = round(consistency_score + return_stability + dd_score + wr_score, 1)

    # Grade
    if total >= 75:
        grade = "A"
    elif total >= 60:
        grade = "B"
    elif total >= 45:
        grade = "C"
    elif total >= 30:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": total,
        "grade": grade,
        "breakdown": {
            "consistency": round(consistency_score, 1),
            "return_stability": round(return_stability, 1),
            "drawdown_stability": round(dd_score, 1),
            "win_rate_consistency": round(wr_score, 1),
        },
        "profitable_segments": profitable_segs,
        "total_segments": len(profits),
        "consistency_pct": round(consistency_pct, 1),
    }


def run_validation(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    data_source: str = "real",
    sim_config: dict = None,
    mode: str = "basic",
    wf_n_windows: int = 5,
    wf_train_pct: float = 0.70,
    wf_num_variants: int = 40,
    holdout_train_pct: float = 0.80,
    holdout_num_variants: int = 60,
) -> dict:
    """
    Run validation on a strategy.

    mode:
      * "basic"        (default) — legacy segment-split + 70/30 + MC + safety
      * "walk_forward" — rolling IS/OOS with re-optimization
      * "holdout"      — strict 80/20 optimize-then-OOS
      * "full"         — basic + walk_forward + holdout composed
    """
    mode = (mode or "basic").lower()
    if mode == "walk_forward":
        from engines.walk_forward_engine import run_walk_forward
        return run_walk_forward(
            strategy_text, pair, timeframe, prices,
            n_windows=wf_n_windows,
            train_pct=wf_train_pct,
            num_variants=wf_num_variants,
            sim_config=sim_config,
        )
    if mode == "holdout":
        from engines.oos_holdout import run_oos_holdout
        return run_oos_holdout(
            strategy_text, pair, timeframe, prices,
            train_pct=holdout_train_pct,
            num_variants=holdout_num_variants,
            sim_config=sim_config,
        )
    if mode == "full":
        from engines.walk_forward_engine import run_walk_forward
        from engines.oos_holdout import run_oos_holdout
        from engines.validation_report import build_validation_report
        from engines.decision_engine import decide
        basic_result = _run_basic_validation(
            strategy_text, pair, timeframe, prices, data_source, sim_config
        )
        wf_result = run_walk_forward(
            strategy_text, pair, timeframe, prices,
            n_windows=wf_n_windows,
            train_pct=wf_train_pct,
            num_variants=wf_num_variants,
            sim_config=sim_config,
        )
        ho_result = run_oos_holdout(
            strategy_text, pair, timeframe, prices,
            train_pct=holdout_train_pct,
            num_variants=holdout_num_variants,
            sim_config=sim_config,
        )
        report = build_validation_report(
            walk_forward=wf_result,
            oos_holdout=ho_result,
            basic=basic_result,
        )
        report["success"] = True
        report["mode"] = "full"
        report["data_source"] = data_source
        report["total_candles"] = len(prices) if prices else 0
        # Phase 8.5 — attach final trading decision (EV + probability can be
        # layered in by the API endpoint; here we decide on validation alone).
        report["decision_report"] = decide(validation_report=report)
        return report

    # Default: basic
    return _run_basic_validation(
        strategy_text, pair, timeframe, prices, data_source, sim_config
    )


def _run_basic_validation(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    data_source: str = "real",
    sim_config: dict = None,
) -> dict:
    """
    Legacy basic validation (unchanged behaviour).
    Splits data into segments, backtests each, and calculates stability.
    """
    total_candles = len(prices)

    # Determine segment count based on data size
    if total_candles < MIN_CANDLES_PER_SEGMENT * 2:
        return {
            "success": False,
            "error": f"Not enough data for validation. Need at least {MIN_CANDLES_PER_SEGMENT * 2} candles, have {total_candles}.",
        }

    num_segments = min(MAX_SEGMENTS, total_candles // MIN_CANDLES_PER_SEGMENT)
    num_segments = max(2, num_segments)

    segments = _split_into_segments(prices, num_segments)

    # --- Walk-forward: backtest each segment ---
    segment_results = []
    for i, seg_prices in enumerate(segments):
        if len(seg_prices) < 10:
            continue
        bt = run_backtest_logic(
            strategy_text, pair, timeframe,
            external_prices=seg_prices,
            data_source=data_source,
            data_points=len(seg_prices),
            sim_config=sim_config,
        )
        segment_results.append({
            "segment": i + 1,
            "candles": len(seg_prices),
            "total_trades": bt.get("total_trades", 0),
            "net_profit": bt.get("net_profit", 0),
            "total_return_pct": bt.get("total_return_pct", 0),
            "win_rate": bt.get("win_rate", 0),
            "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
            "profit_factor": bt.get("profit_factor", 0),
        })

    # --- Train/Test split (70/30) ---
    split_idx = int(total_candles * 0.7)
    train_prices = prices[:split_idx]
    test_prices = prices[split_idx:]

    train_result = None
    test_result = None

    if len(train_prices) >= 10:
        bt_train = run_backtest_logic(
            strategy_text, pair, timeframe,
            external_prices=train_prices,
            data_source=data_source,
            data_points=len(train_prices),
            sim_config=sim_config,
        )
        train_result = {
            "label": "Train (70%)",
            "candles": len(train_prices),
            "total_trades": bt_train.get("total_trades", 0),
            "net_profit": bt_train.get("net_profit", 0),
            "total_return_pct": bt_train.get("total_return_pct", 0),
            "win_rate": bt_train.get("win_rate", 0),
            "max_drawdown_pct": bt_train.get("max_drawdown_pct", 0),
            "profit_factor": bt_train.get("profit_factor", 0),
        }

    if len(test_prices) >= 10:
        bt_test = run_backtest_logic(
            strategy_text, pair, timeframe,
            external_prices=test_prices,
            data_source=data_source,
            data_points=len(test_prices),
            sim_config=sim_config,
        )
        test_result = {
            "label": "Test (30%)",
            "candles": len(test_prices),
            "total_trades": bt_test.get("total_trades", 0),
            "net_profit": bt_test.get("net_profit", 0),
            "total_return_pct": bt_test.get("total_return_pct", 0),
            "win_rate": bt_test.get("win_rate", 0),
            "max_drawdown_pct": bt_test.get("max_drawdown_pct", 0),
            "profit_factor": bt_test.get("profit_factor", 0),
        }

    # --- Full-period baseline ---
    bt_full = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=prices,
        data_source=data_source,
        data_points=total_candles,
        sim_config=sim_config,
    )
    full_result = {
        "label": "Full Period",
        "candles": total_candles,
        "total_trades": bt_full.get("total_trades", 0),
        "net_profit": bt_full.get("net_profit", 0),
        "total_return_pct": bt_full.get("total_return_pct", 0),
        "win_rate": bt_full.get("win_rate", 0),
        "max_drawdown_pct": bt_full.get("max_drawdown_pct", 0),
        "profit_factor": bt_full.get("profit_factor", 0),
    }

    # --- Calculate stability ---
    stability = _calc_stability_score(segment_results)

    # --- Overfit detection ---
    overfit_warning = None
    if train_result and test_result:
        train_ret = train_result["total_return_pct"]
        test_ret = test_result["total_return_pct"]
        if train_ret > 0 and test_ret < train_ret * 0.3:
            overfit_warning = "Possible overfitting: test performance significantly worse than train"
        elif train_ret > 0 and test_ret < 0:
            overfit_warning = "Likely overfitting: profitable on train data but negative on test data"

    # --- Monte Carlo simulation ---
    monte_carlo = None
    full_trades = bt_full.get("trades", [])
    if full_trades and len(full_trades) >= 3:
        mc_balance = sim_config.get("initial_balance", 10000.0) if sim_config else 10000.0
        monte_carlo = run_monte_carlo(
            trades=full_trades,
            num_simulations=100,
            initial_balance=mc_balance,
        )

    # --- Safety analysis on full-period backtest ---
    safety = run_safety_analysis(bt_full, timeframe=timeframe)

    return {
        "success": True,
        "mode": "basic",
        "data_source": data_source,
        "total_candles": total_candles,
        "num_segments": len(segment_results),
        "segments": segment_results,
        "train_test": {
            "train": train_result,
            "test": test_result,
        },
        "full_period": full_result,
        "stability": stability,
        "overfit_warning": overfit_warning,
        "monte_carlo": monte_carlo,
        "safety": safety,
    }

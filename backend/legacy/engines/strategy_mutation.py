"""
Strategy Mutation Engine (Phase 6).

Automatically adjusts strategy parameters to improve pass probability,
drawdown safety, and consistency. Works by:
  1. Diagnosing issues from profile + probability data
  2. Generating controlled parameter mutations
  3. Re-evaluating each mutation (backtest → profile → probability)
  4. Comparing original vs mutated, keeping only improvements

Mutations are small, controlled changes — not random search.
Each mutation targets a specific diagnosed issue.
"""

import logging
from engines.param_extractor import extract_params
from engines.backtest_engine import run_backtest_logic
from engines.strategy_profiler import profile_strategy
from engines.challenge_simulator import simulate_challenge
from engines.pass_probability import estimate_pass_probability

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Diagnosis: identify what's wrong
# ═══════════════════════════════════════════════════════

def _diagnose(profile: dict, probability: float, sim_result: dict) -> list:
    """
    Identify issues from strategy profile + simulation data.
    Returns list of issue dicts with type and severity.
    """
    issues = []
    risk = profile.get("risk", {})
    behavior = profile.get("behavior", {})
    stability = profile.get("stability", {})
    consistency = profile.get("consistency", {})

    max_dd = risk.get("max_drawdown_pct", 0)
    daily_dd_p90 = risk.get("daily_dd_distribution", {}).get("p90", 0)
    win_rate = behavior.get("win_rate", 0)
    total_return = stability.get("total_return_pct", 0)
    top_day = consistency.get("profit_distribution", {}).get("top_day_pct", 0)
    max_cons_losses = consistency.get("max_consecutive_losses", 0)

    sim_dd = sim_result.get("max_drawdown_pct", 0) if sim_result else 0
    sim_daily_dd = sim_result.get("max_daily_drawdown_pct", 0) if sim_result else 0
    fail_reason = sim_result.get("failure_reason") if sim_result else None

    # High drawdown
    if max_dd > 15 or sim_dd > 8:
        issues.append({
            "type": "high_drawdown",
            "severity": "critical" if max_dd > 25 else "high",
            "detail": f"Max DD {max_dd}%, sim DD {sim_dd}%",
            "mutations": ["tighten_sl", "reduce_position"],
        })

    # Daily DD too close to firm limits
    if daily_dd_p90 > 2.5 or sim_daily_dd > 3:
        issues.append({
            "type": "daily_dd_pressure",
            "severity": "high",
            "detail": f"Daily DD p90={daily_dd_p90}%, sim daily DD={sim_daily_dd}%",
            "mutations": ["tighten_sl", "reduce_position"],
        })

    # Low pass probability
    if probability < 30:
        issues.append({
            "type": "low_probability",
            "severity": "critical" if probability < 10 else "high",
            "detail": f"Pass probability {probability}%",
            "mutations": ["tighten_sl", "widen_tp", "adjust_rsi"],
        })

    # Low win rate
    if win_rate < 35:
        issues.append({
            "type": "low_win_rate",
            "severity": "medium",
            "detail": f"Win rate {win_rate}%",
            "mutations": ["widen_tp", "tighten_sl", "adjust_rsi"],
        })

    # Poor risk-reward
    rr = behavior.get("risk_reward_ratio", 0)
    if rr < 1.0 and rr > 0:
        issues.append({
            "type": "poor_risk_reward",
            "severity": "medium",
            "detail": f"R:R {rr}",
            "mutations": ["widen_tp", "tighten_sl"],
        })

    # Low consistency (profit concentrated in few days)
    if top_day > 50:
        issues.append({
            "type": "low_consistency",
            "severity": "medium",
            "detail": f"Top day has {top_day}% of total profit",
            "mutations": ["reduce_position", "tighten_sl"],
        })

    # Too many consecutive losses
    if max_cons_losses > 5:
        issues.append({
            "type": "streak_risk",
            "severity": "medium",
            "detail": f"Max {max_cons_losses} consecutive losses",
            "mutations": ["tighten_sl", "adjust_rsi"],
        })

    # Slow profit growth (negative return)
    if total_return < 0:
        issues.append({
            "type": "unprofitable",
            "severity": "critical",
            "detail": f"Return {total_return}%",
            "mutations": ["widen_tp", "adjust_periods", "adjust_rsi"],
        })

    # Specific failure reasons from sim
    if fail_reason == "daily_dd":
        if not any(i["type"] == "daily_dd_pressure" for i in issues):
            issues.append({
                "type": "sim_daily_dd_breach",
                "severity": "critical",
                "detail": "Challenge failed on daily DD",
                "mutations": ["tighten_sl", "reduce_position"],
            })
    elif fail_reason == "total_dd":
        if not any(i["type"] == "high_drawdown" for i in issues):
            issues.append({
                "type": "sim_total_dd_breach",
                "severity": "critical",
                "detail": "Challenge failed on total DD",
                "mutations": ["tighten_sl", "reduce_position"],
            })

    return issues


# ═══════════════════════════════════════════════════════
# Mutation generators: each returns a list of override dicts
# ═══════════════════════════════════════════════════════

def _gen_mutations(base_params: dict, issues: list) -> list:
    """
    Generate mutation variants based on diagnosed issues.
    Each mutation is a dict with name, description, param_overrides, indicators_override.
    """
    sl = base_params.get("sl_pips", 20)
    tp = base_params.get("tp_pips", 35)
    fast = base_params.get("fast_period", 8)
    slow = base_params.get("slow_period", 21)
    rsi_period = base_params.get("rsi_period", 14)
    rsi_buy = base_params.get("rsi_buy_threshold", 50)
    rsi_sell = base_params.get("rsi_sell_threshold", 50)

    # Collect unique mutation types needed
    needed = set()
    for issue in issues:
        for m in issue.get("mutations", []):
            needed.add(m)

    mutations = []

    if "tighten_sl" in needed:
        # Tighten SL by 15%, 25%, 35%
        for pct, label in [(0.15, "mild"), (0.25, "moderate"), (0.35, "aggressive")]:
            new_sl = max(5, round(sl * (1 - pct)))
            if new_sl != sl:
                mutations.append({
                    "name": f"tighten_sl_{label}",
                    "description": f"Reduce SL from {sl} to {new_sl} pips (-{int(pct*100)}%)",
                    "param_overrides": {"sl_pips": new_sl, "tp_pips": tp,
                                        "fast_period": fast, "slow_period": slow},
                    "indicators_override": None,
                    "changes": [f"SL: {sl} → {new_sl} pips"],
                })

    if "widen_tp" in needed:
        # Widen TP by 20%, 40%
        for pct, label in [(0.20, "mild"), (0.40, "moderate")]:
            new_tp = round(tp * (1 + pct))
            if new_tp != tp:
                mutations.append({
                    "name": f"widen_tp_{label}",
                    "description": f"Increase TP from {tp} to {new_tp} pips (+{int(pct*100)}%)",
                    "param_overrides": {"sl_pips": sl, "tp_pips": new_tp,
                                        "fast_period": fast, "slow_period": slow},
                    "indicators_override": None,
                    "changes": [f"TP: {tp} → {new_tp} pips"],
                })

    if "reduce_position" in needed:
        # Tighten SL + slightly widen TP (risk reduction combo)
        new_sl = max(5, round(sl * 0.75))
        new_tp = round(tp * 1.15)
        mutations.append({
            "name": "risk_reduction_combo",
            "description": f"SL {sl}→{new_sl}, TP {tp}→{new_tp} (tighter risk, wider reward)",
            "param_overrides": {"sl_pips": new_sl, "tp_pips": new_tp,
                                "fast_period": fast, "slow_period": slow},
            "indicators_override": None,
            "changes": [f"SL: {sl} → {new_sl} pips", f"TP: {tp} → {new_tp} pips"],
        })

    if "adjust_rsi" in needed and rsi_period > 0:
        # Adjust RSI thresholds to be more selective
        new_buy = min(55, rsi_buy + 5)
        new_sell = max(45, rsi_sell - 5)
        mutations.append({
            "name": "stricter_rsi",
            "description": f"RSI buy {rsi_buy}→{new_buy}, sell {rsi_sell}→{new_sell} (more selective)",
            "param_overrides": {"sl_pips": sl, "tp_pips": tp,
                                "fast_period": fast, "slow_period": slow},
            "indicators_override": {
                "rsi": {"period": rsi_period, "buy_threshold": new_buy, "sell_threshold": new_sell},
            },
            "changes": [f"RSI buy: {rsi_buy} → {new_buy}", f"RSI sell: {rsi_sell} → {new_sell}"],
        })

    if "adjust_periods" in needed:
        # Try longer periods (smoother signals)
        new_fast = min(fast + 3, slow - 2)
        new_slow = slow + 5
        if new_fast < new_slow:
            mutations.append({
                "name": "longer_periods",
                "description": f"EMA fast {fast}→{new_fast}, slow {slow}→{new_slow} (smoother)",
                "param_overrides": {"sl_pips": sl, "tp_pips": tp,
                                    "fast_period": new_fast, "slow_period": new_slow},
                "indicators_override": None,
                "changes": [f"Fast: {fast} → {new_fast}", f"Slow: {slow} → {new_slow}"],
            })

    # Always add a combined mutation: tighter SL + wider TP + stricter RSI
    if len(issues) > 0:
        new_sl = max(5, round(sl * 0.80))
        new_tp = round(tp * 1.25)
        combined_ind = None
        combined_changes = [f"SL: {sl} → {new_sl}", f"TP: {tp} → {new_tp}"]
        if rsi_period > 0:
            combined_ind = {
                "rsi": {"period": rsi_period,
                         "buy_threshold": min(55, rsi_buy + 3),
                         "sell_threshold": max(45, rsi_sell - 3)},
            }
            combined_changes.append("RSI adjusted")
        mutations.append({
            "name": "combined_improvement",
            "description": "Combined: tighter SL, wider TP, stricter RSI",
            "param_overrides": {"sl_pips": new_sl, "tp_pips": new_tp,
                                "fast_period": fast, "slow_period": slow},
            "indicators_override": combined_ind,
            "changes": combined_changes,
        })

    return mutations


# ═══════════════════════════════════════════════════════
# Evaluation helper
# ═══════════════════════════════════════════════════════

def _evaluate_variant(strategy_text, pair, timeframe, prices, data_points,
                      param_ov, ind_ov, rules_config, mc_sims,
                      sim_config=None):
    """Run backtest → profile → probability for a mutation variant.

    P0 stability: if the backtest returns an `error` (e.g. no_real_data)
    OR zero trades, we short-circuit and return a well-formed
    `{"invalid": True, ...}` block so the caller can filter it out
    without the None-propagation crash that used to occur when
    `_is_improvement` tried `None * 1.15`.

    P2 quality-aware refinement: optional `sim_config` is forwarded to
    `run_backtest_logic`, so when refinement runs under
    `sim_config={"quality_filter": True, "quality_threshold": ...}`
    every mutation variant is evaluated INSIDE the high-quality entry
    space — the same constraint live system uses.
    """
    bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=prices, data_source="real",
        data_points=data_points,
        param_overrides=param_ov,
        indicators_override=ind_ov,
        sim_config=sim_config,
    )

    # P0 — structured invalid-strategy signal. Any of: explicit backtest
    # error, zero trades, or None/negative balances => unscoreable.
    _err = bt.get("error")
    _trades_count = int(bt.get("total_trades") or 0)
    _pf = bt.get("profit_factor")
    if _err or _trades_count == 0 or _pf is None:
        reason = _err or ("no_trades" if _trades_count == 0 else "null_metrics")
        return {
            "invalid": True,
            "invalid_reason": reason,
            "backtest": {
                "net_profit": float(bt.get("net_profit") or 0),
                "total_return_pct": float(bt.get("total_return_pct") or 0),
                "win_rate": float(bt.get("win_rate") or 0),
                "profit_factor": float(bt.get("profit_factor") or 0),
                "max_drawdown_pct": float(bt.get("max_drawdown_pct") or 0),
                "total_trades": _trades_count,
            },
            "profile": {"type": "", "risk_level": "very_high",
                        "sharpe_ratio": 0.0, "equity_smoothness": 0.0},
            "simulation": {"status": "fail", "max_drawdown_pct": 0.0,
                           "max_daily_dd_pct": 0.0, "failure_reason": reason},
            "probability": {"pass_probability": 0.0, "risk_label": "very_high",
                            "avg_days_to_pass": 0,
                            "structural_robustness_score": 0.0,
                            "structural_robustness_label": "unknown"},
            "trades": [],
        }

    trades = bt.get("trades", [])
    dna = profile_strategy(trades)

    prob_result = estimate_pass_probability(
        trades, rules_config, n_simulations=mc_sims
    )

    sim_result = simulate_challenge(trades, rules_config)

    return {
        "invalid": False,
        "backtest": {
            "net_profit": float(bt.get("net_profit") or 0),
            "total_return_pct": float(bt.get("total_return_pct") or 0),
            "win_rate": float(bt.get("win_rate") or 0),
            "profit_factor": float(bt.get("profit_factor") or 0),
            "max_drawdown_pct": float(bt.get("max_drawdown_pct") or 0),
            "total_trades": _trades_count,
        },
        "profile": {
            "type": dna.get("classification", {}).get("type", ""),
            "risk_level": dna.get("classification", {}).get("risk_level", ""),
            "sharpe_ratio": dna.get("stability", {}).get("sharpe_ratio", 0),
            "equity_smoothness": dna.get("stability", {}).get("equity_curve_smoothness", 0),
        },
        "simulation": {
            "status": sim_result.get("status", "fail"),
            "max_drawdown_pct": sim_result.get("max_drawdown_pct", 0),
            "max_daily_dd_pct": sim_result.get("max_daily_drawdown_pct", 0),
            "failure_reason": sim_result.get("failure_reason"),
        },
        "probability": {
            "pass_probability": prob_result.get("pass_probability", 0),
            "risk_label": prob_result.get("risk_label", "very_high"),
            "avg_days_to_pass": prob_result.get("avg_days_to_pass", 0),
            "structural_robustness_score": (
                prob_result.get("structural_robustness") or {}
            ).get("score"),
            "structural_robustness_label": (
                prob_result.get("structural_robustness") or {}
            ).get("label"),
        },
        "trades": trades,
        # P2 — surface the quality block from the backtest so callers
        # (refinement, dashboards) can verify the variant was evaluated
        # under the same quality filter as the live pipeline.
        "_phase4_signal_quality": bt.get("_phase4_signal_quality"),
    }


# ═══════════════════════════════════════════════════════
# Selection: keep only improvements
# ═══════════════════════════════════════════════════════

# Phase 6 guard: reject mutations that improve probability at the cost of
# structural robustness (i.e. trading real edge for favorable trade sequencing).
ROBUSTNESS_DROP_THRESHOLD = 10.0   # percentage-point drop that triggers rejection


def _is_improvement(original: dict, mutated: dict) -> tuple:
    """
    Check if mutation is an improvement over original.
    Returns (is_better: bool, reason: str).
    Improvement = probability up OR drawdown down without major trade-off.

    Phase 6 integrity guard: a mutation is rejected if its probability or
    drawdown gains come with a `structural_robustness_score` drop greater
    than ROBUSTNESS_DROP_THRESHOLD (default 10 pts). This prevents the
    engine from rewarding path-dependency artifacts.

    P0 stability: if either side is marked `invalid` (no trades / no
    real data / null metrics) we cannot compare them at all. Return
    (False, reason) so the mutation is skipped instead of crashing on
    `None * 1.15`.
    """
    if original.get("invalid"):
        return False, f"baseline_invalid: {original.get('invalid_reason','unknown')}"
    if mutated.get("invalid"):
        return False, f"mutant_invalid: {mutated.get('invalid_reason','unknown')}"

    # Coerce every metric to a float with `0.0` default so a bad row
    # downstream cannot re-introduce the `None * float` crash.
    def _f(d: dict, *path, default: float = 0.0) -> float:
        cur = d
        for p in path:
            cur = (cur or {}).get(p, {}) if p != path[-1] else (cur or {}).get(p, default)
        try:
            return float(cur) if cur is not None else float(default)
        except (TypeError, ValueError):
            return float(default)

    orig_prob = _f(original, "probability", "pass_probability")
    mut_prob  = _f(mutated,  "probability", "pass_probability")

    orig_dd = _f(original, "backtest", "max_drawdown_pct")
    mut_dd  = _f(mutated,  "backtest", "max_drawdown_pct")

    orig_pf = _f(original, "backtest", "profit_factor")
    mut_pf  = _f(mutated,  "backtest", "profit_factor")

    orig_ret = _f(original, "backtest", "total_return_pct")
    mut_ret  = _f(mutated,  "backtest", "total_return_pct")

    orig_rob = (original.get("probability") or {}).get("structural_robustness_score")
    mut_rob = (mutated.get("probability") or {}).get("structural_robustness_score")

    def _robustness_regressed() -> bool:
        # Skip guard when either side lacks a score (legacy callers / no MC).
        if orig_rob is None or mut_rob is None:
            return False
        return (orig_rob - mut_rob) > ROBUSTNESS_DROP_THRESHOLD

    # Major trade-off: return drops by more than 50%
    if orig_ret > 0 and mut_ret < orig_ret * 0.5:
        return False, f"return dropped too much ({orig_ret}% → {mut_ret}%)"

    # Probability improved
    if mut_prob > orig_prob + 5:
        if _robustness_regressed():
            return False, (
                f"probability up ({orig_prob}% → {mut_prob}%) but structural "
                f"robustness dropped {orig_rob} → {mut_rob} (> {ROBUSTNESS_DROP_THRESHOLD} pts)"
            )
        return True, f"probability improved {orig_prob}% → {mut_prob}%"

    # Drawdown reduced significantly
    if mut_dd < orig_dd * 0.8 and mut_pf >= orig_pf * 0.85:
        if _robustness_regressed():
            return False, (
                f"drawdown reduced ({orig_dd}% → {mut_dd}%) but structural "
                f"robustness dropped {orig_rob} → {mut_rob} (> {ROBUSTNESS_DROP_THRESHOLD} pts)"
            )
        return True, f"drawdown reduced {orig_dd}% → {mut_dd}%"

    # Profit factor improved meaningfully
    if mut_pf > orig_pf * 1.15 and mut_dd <= orig_dd * 1.1:
        return True, f"profit factor improved {orig_pf} → {mut_pf}"

    # Simulation status flipped from fail to pass
    if original["simulation"]["status"] == "fail" and mutated["simulation"]["status"] == "pass":
        return True, "simulation status: fail → pass"

    return False, "no significant improvement"


# ═══════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════

def mutate_strategy(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    data_points: int,
    rules_config: dict,
    mc_simulations: int = 20,
) -> dict:
    """
    Mutate a strategy to improve prop firm pass probability.

    1. Extract base parameters
    2. Run original evaluation (backtest → profile → sim → probability)
    3. Diagnose issues
    4. Generate controlled mutations
    5. Evaluate each mutation
    6. Compare and select best improvement

    Returns dict with original, best_mutation, all_mutations, diagnosis.
    """
    if not prices or len(prices) < 50:
        return {
            "success": False,
            "error": "Real market data required (min 50 candles)",
        }

    # ── Extract base parameters ──
    extraction = extract_params(strategy_text)
    raw = extraction.get("raw", {})
    overrides = extraction.get("overrides", {})
    strategy_type = extraction.get("strategy_type", "trend_following")

    base_params = {
        "fast_period": overrides.get("fast_period", raw.get("fast_sma", 8)),
        "slow_period": overrides.get("slow_period", raw.get("slow_sma", 21)),
        "sl_pips": overrides.get("sl_pips", raw.get("stop_loss_pips", 20)),
        "tp_pips": overrides.get("tp_pips", raw.get("take_profit_pips", 35)),
        "rsi_period": raw.get("rsi_period", 14),
        "rsi_buy_threshold": raw.get("rsi_buy_threshold", 50),
        "rsi_sell_threshold": raw.get("rsi_sell_threshold", 50),
    }

    # ── Evaluate original ──
    original = _evaluate_variant(
        strategy_text, pair, timeframe, prices, data_points,
        None, None, rules_config, mc_simulations
    )

    # ── Diagnose ──
    orig_prob = original["probability"]["pass_probability"]
    issues = _diagnose(
        {"risk": {
            "max_drawdown_pct": original["backtest"]["max_drawdown_pct"],
            "daily_dd_distribution": {"p90": original["simulation"]["max_daily_dd_pct"]},
        },
        "behavior": {
            "win_rate": original["backtest"]["win_rate"],
            "risk_reward_ratio": 0,
            "trades_per_day": 0,
        },
        "stability": {
            "profit_factor": original["backtest"]["profit_factor"],
            "total_return_pct": original["backtest"]["total_return_pct"],
        },
        "consistency": {
            "profit_distribution": {"top_day_pct": 0},
            "max_consecutive_losses": 0,
        }},
        orig_prob,
        original["simulation"],
    )

    if not issues:
        return {
            "success": True,
            "action": "no_mutation_needed",
            "original": {
                "backtest": original["backtest"],
                "profile": original["profile"],
                "simulation": original["simulation"],
                "probability": original["probability"],
            },
            "best_mutation": None,
            "mutations_tested": 0,
            "diagnosis": [],
            "base_params": base_params,
            "strategy_type": strategy_type,
        }

    # ── Generate mutations ──
    mutations = _gen_mutations(base_params, issues)

    # ── Evaluate each mutation ──
    mutation_results = []
    for mut in mutations:
        try:
            result = _evaluate_variant(
                strategy_text, pair, timeframe, prices, data_points,
                mut["param_overrides"], mut.get("indicators_override"),
                rules_config, mc_simulations,
            )
            is_better, reason = _is_improvement(original, result)

            mutation_results.append({
                "name": mut["name"],
                "description": mut["description"],
                "changes": mut["changes"],
                "backtest": result["backtest"],
                "profile": result["profile"],
                "simulation": result["simulation"],
                "probability": result["probability"],
                "is_improvement": is_better,
                "improvement_reason": reason,
                "param_overrides": mut["param_overrides"],
                "indicators_override": mut.get("indicators_override"),
            })
        except Exception as e:
            logger.warning(f"Mutation {mut['name']} failed: {e}")
            mutation_results.append({
                "name": mut["name"],
                "description": mut["description"],
                "changes": mut["changes"],
                "error": str(e),
                "is_improvement": False,
            })

    # ── Select best ──
    improvements = [m for m in mutation_results if m.get("is_improvement")]
    improvements.sort(
        key=lambda x: x.get("probability", {}).get("pass_probability", 0),
        reverse=True,
    )

    best = improvements[0] if improvements else None

    # Compute improvement delta
    if best:
        orig_p = original["probability"]["pass_probability"]
        mut_p = best["probability"]["pass_probability"]
        improvement_delta = round(mut_p - orig_p, 1)
    else:
        improvement_delta = 0

    return {
        "success": True,
        "action": "mutation_applied" if best else "no_improvement_found",
        "original": {
            "backtest": original["backtest"],
            "profile": original["profile"],
            "simulation": original["simulation"],
            "probability": original["probability"],
        },
        "best_mutation": best,
        "original_probability": original["probability"]["pass_probability"],
        "mutated_probability": best["probability"]["pass_probability"] if best else orig_prob,
        "improvement": improvement_delta,
        "mutations_tested": len(mutation_results),
        "mutations_improved": len(improvements),
        "all_mutations": mutation_results,
        "diagnosis": [{"type": i["type"], "severity": i["severity"], "detail": i["detail"]} for i in issues],
        "base_params": base_params,
        "strategy_type": strategy_type,
    }

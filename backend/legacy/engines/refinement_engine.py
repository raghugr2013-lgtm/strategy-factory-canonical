"""
Phase 8.7 — Strategy Refinement Engine.

Automatically improves weak strategies by reading the structured output of
Phase 8 (validation), 8.5 (decision), and 9 (prop firm panel), mapping the
issues onto concrete mutation types, and iterating a small number of
cycles — keeping only variants that genuinely improve the weak areas.

Reuses existing building blocks (no duplication):
    * `engines.strategy_mutation._gen_mutations`  — variant generator
    * `engines.strategy_mutation._evaluate_variant` — backtest + profile + sim + prob
    * `engines.validation_engine.run_validation`    — mode="full" for IS/OOS re-check
    * `engines.decision_engine.decide`              — final verdict re-compute
    * `engines.prop_firm_panel.build_prop_firm_panel`— final readiness re-compute

Designed to run on the TOP candidates only (called from the ranking layer).

Input:
    strategy = {
        "strategy_text": str,
        "pair": str, "timeframe": str,
        "prices": list[float],               # real candle closes
        "data_points": int,                  # optional
        "rules_config": dict,                # firm rules (required for prob/sim)
        "validation_report": dict or None,
        "decision": dict or None,            # from decision_engine.decide
        "prop_firm_panel": dict or None,
        "base_params": dict or None,         # current params (fast/slow/sl/tp/rsi...)
    }
    max_cycles: int = 2   (1-3)
    variants_per_cycle: int = 5

Output:
    {
      "success": bool,
      "improved": bool,
      "cycles_run": int,
      "issues": [...],                    # initial diagnosis
      "best_variant": {...},              # winning mutation + its metrics
      "original": {...},                  # starting metrics
      "refined_strategy": {               # ready to re-rank
          "strategy_text": ...,
          "param_overrides": ...,
          "indicators_override": ...,
          "validation_report": ...,       # full-mode re-validation (best effort)
          "decision": ...,
          "prop_firm_panel": ...,
      },
      "improvement": {                    # deltas
          "max_drawdown_pct": {"from": .., "to": .., "delta": ..},
          "pass_probability": {"from": .., "to": .., "delta": ..},
          "overfit_score":    {"from": .., "to": .., "delta": ..},
          "stability_score":  {"from": .., "to": .., "delta": ..},
      },
      "history": [ {cycle, chosen, reason}, ... ]
    }
"""
from __future__ import annotations

import logging
from engines.strategy_mutation import (
    _gen_mutations, _evaluate_variant, _is_improvement,
)

logger = logging.getLogger(__name__)


MAX_CYCLES_DEFAULT = 2
VARIANTS_PER_CYCLE_DEFAULT = 5
MAX_VARIANTS_PER_CYCLE = 8


# ── Issue detection from Phase 8/8.5/9 outputs ────────────────────────

def _safe_num(v, default=None):
    return v if isinstance(v, (int, float)) else default


def _diagnose_from_reports(
    validation_report: dict | None,
    decision: dict | None,
    prop_firm_panel: dict | None,
    base_backtest: dict | None = None,
) -> list[dict]:
    """
    Convert Phase 8/8.5/9 findings into the `issues` shape expected by
    `_gen_mutations` in strategy_mutation.py.
    """
    issues: list[dict] = []

    # ── High drawdown (from base backtest or prop firm panel) ──
    max_dd = _safe_num((base_backtest or {}).get("max_drawdown_pct"))
    if max_dd is None and prop_firm_panel:
        max_dd = _safe_num(prop_firm_panel.get("max_drawdown"))
    if max_dd is not None and max_dd > 10:
        issues.append({
            "type": "high_drawdown",
            "severity": "critical" if max_dd > 20 else "high",
            "detail": f"Max DD {max_dd:.2f}%",
            "mutations": ["tighten_sl", "reduce_position"],
        })

    # ── Daily DD pressure / violation (from prop firm panel) ──
    if prop_firm_panel:
        daily_dd = _safe_num(prop_firm_panel.get("daily_drawdown"))
        if daily_dd is not None and daily_dd > 3:
            issues.append({
                "type": "daily_dd_pressure",
                "severity": "high",
                "detail": f"Daily DD {daily_dd:.2f}%",
                "mutations": ["tighten_sl", "reduce_position"],
            })
        if (prop_firm_panel.get("violations") or {}).get("max_dd", 0):
            issues.append({
                "type": "sim_total_dd_breach",
                "severity": "critical",
                "detail": "Prop panel flagged total DD breach.",
                "mutations": ["tighten_sl", "reduce_position"],
            })
        if (prop_firm_panel.get("violations") or {}).get("daily_dd", 0):
            issues.append({
                "type": "sim_daily_dd_breach",
                "severity": "critical",
                "detail": "Prop panel flagged daily DD breach.",
                "mutations": ["tighten_sl", "reduce_position"],
            })
        if (prop_firm_panel.get("violations") or {}).get("consistency", 0):
            issues.append({
                "type": "low_consistency",
                "severity": "medium",
                "detail": "Consistency rule violation.",
                "mutations": ["reduce_position", "tighten_sl"],
            })

    # ── Low pass probability ──
    prob = None
    if prop_firm_panel:
        prob = _safe_num(prop_firm_panel.get("pass_probability"))
    if prob is not None and prob < 50:
        issues.append({
            "type": "low_probability",
            "severity": "critical" if prob < 25 else "high",
            "detail": f"Pass probability {prob:.0f}%",
            "mutations": ["tighten_sl", "widen_tp", "adjust_rsi"],
        })

    # ── Overfit (validation_report) ──
    overfit_score = None
    if validation_report:
        ov = validation_report.get("overfit_score")
        if isinstance(ov, dict):
            overfit_score = _safe_num(ov.get("score"))
        elif isinstance(ov, (int, float)):
            overfit_score = float(ov)
    if overfit_score is not None and overfit_score >= 50:
        issues.append({
            "type": "overfit",
            "severity": "critical" if overfit_score >= 70 else "high",
            "detail": f"Overfit score {overfit_score:.0f}/100",
            # Simpler params + stricter selectivity
            "mutations": ["adjust_periods", "adjust_rsi"],
        })

    # ── Low stability ──
    stab = None
    if validation_report:
        st = validation_report.get("stability_score")
        if isinstance(st, dict):
            stab = _safe_num(st.get("score"))
        elif isinstance(st, (int, float)):
            stab = float(st)
    if stab is not None and stab < 50:
        issues.append({
            "type": "low_stability",
            "severity": "high",
            "detail": f"Stability {stab:.0f}/100",
            "mutations": ["adjust_periods", "adjust_rsi", "reduce_position"],
        })

    # ── Decision = REJECT or RISKY ──
    verdict = None
    if isinstance(decision, dict):
        inner = decision.get("decision") if isinstance(decision.get("decision"), dict) else decision
        verdict = inner.get("verdict") if isinstance(inner, dict) else None
    elif isinstance(decision, str):
        verdict = decision
    if verdict == "REJECT":
        issues.append({
            "type": "decision_reject",
            "severity": "critical",
            "detail": "Decision engine = REJECT",
            "mutations": ["tighten_sl", "widen_tp", "adjust_rsi", "adjust_periods"],
        })
    elif verdict == "RISKY":
        issues.append({
            "type": "decision_risky",
            "severity": "medium",
            "detail": "Decision engine = RISKY",
            "mutations": ["tighten_sl", "widen_tp", "adjust_rsi"],
        })

    return issues


# ── Post-refinement re-scoring (best-effort; tolerant to partial inputs) ─

def _rescore_refined(
    strategy_text: str, pair: str, timeframe: str,
    prices: list, rules_config: dict,
    best_eval: dict,
) -> tuple[dict, dict, dict]:
    """
    Rebuild decision + prop panel (and optionally a light validation report)
    for the refined variant. Validation is skipped on tiny datasets.
    Returns (validation_report | None, decision_dict, prop_firm_panel).
    """
    from engines.decision_engine import decide
    from engines.prop_firm_panel import build_prop_firm_panel

    # Validation (optional; mode="full" is expensive — keep it lean).
    validation_report = None
    if prices and len(prices) >= 200:
        try:
            from engines.validation_engine import run_validation
            validation_report = run_validation(
                strategy_text, pair, timeframe, prices,
                mode="full",
                wf_n_windows=3, wf_num_variants=10,
                holdout_num_variants=15,
            )
        except Exception as e:
            logger.warning(f"refined re-validation failed: {e}")
            validation_report = None

    # Decision (Phase 8.5)
    pp = best_eval.get("probability", {}).get("pass_probability")
    dec = decide(validation_report=validation_report,
                 expected_value=None,
                 pass_probability=pp)

    # Prop firm panel (Phase 9) — synthesize a minimal simulation dict from
    # the mutation evaluator output.
    sim_seed = {
        "status": best_eval.get("simulation", {}).get("status"),
        "failure_reason": best_eval.get("simulation", {}).get("failure_reason"),
        "max_drawdown_pct": best_eval.get("simulation", {}).get("max_drawdown_pct", 0),
        "max_daily_drawdown_pct": best_eval.get("simulation", {}).get("max_daily_dd_pct", 0),
        "max_total_dd_limit_pct": (rules_config or {}).get("max_total_dd_pct", 10.0),
        "max_daily_dd_limit_pct": (rules_config or {}).get("max_daily_dd_pct", 5.0),
        "rules_used": {"firm_name": (rules_config or {}).get("name", "Custom")},
    }
    panel = build_prop_firm_panel(
        simulation=sim_seed,
        pass_probability=pp,
        validation_report=validation_report,
        decision=dec,
    )
    return validation_report, dec, panel


# ── Public API ────────────────────────────────────────────────────────

def refine_strategy(
    strategy: dict,
    max_cycles: int = MAX_CYCLES_DEFAULT,
    variants_per_cycle: int = VARIANTS_PER_CYCLE_DEFAULT,
    mc_simulations: int = 20,
    sim_config: dict | None = None,
) -> dict:
    """
    Iteratively improve a weak strategy using existing mutation primitives.

    Each cycle:
        1. Diagnose issues from validation_report + decision + prop_firm_panel
        2. Generate up to `variants_per_cycle` mutation variants
        3. Evaluate each (backtest + profile + probability + challenge sim)
        4. Pick the best that actually improves over the current baseline
        5. Make it the new baseline; repeat (up to `max_cycles`)

    P2 — Quality-aware refinement: when `sim_config["quality_filter"] is
    True`, every variant (including the unmutated baseline) is evaluated
    inside the high-quality entry space. This ensures refinement does
    not "win" just by accepting more low-quality trades.
    """
    strategy_text = strategy.get("strategy_text") or ""
    pair = strategy.get("pair", "EURUSD")
    timeframe = strategy.get("timeframe", "H1")
    prices = strategy.get("prices") or []
    data_points = strategy.get("data_points") or len(prices)
    rules_config = strategy.get("rules_config") or {}
    base_params = dict(strategy.get("base_params") or {})
    # P2 — optional sim_config (quality filter etc). Allow it to be
    # passed via the `strategy` dict OR via the explicit kwarg; the
    # kwarg wins so the caller has the final say.
    if sim_config is None:
        sim_config = strategy.get("sim_config")
    max_cycles = max(1, min(int(max_cycles), 3))
    variants_per_cycle = max(3, min(int(variants_per_cycle), MAX_VARIANTS_PER_CYCLE))

    if not strategy_text:
        return {"success": False, "improved": False,
                "error": "strategy_text is required."}
    if not prices or len(prices) < 60:
        return {"success": False, "improved": False,
                "error": f"Need at least 60 price points to refine (got {len(prices)})."}
    if not rules_config:
        return {"success": False, "improved": False,
                "error": "rules_config is required (firm rules)."}

    # ── Initial diagnosis from reports ──
    issues = _diagnose_from_reports(
        strategy.get("validation_report"),
        strategy.get("decision"),
        strategy.get("prop_firm_panel"),
        strategy.get("backtest"),
    )
    if not issues:
        return {
            "success": True,
            "improved": False,
            "cycles_run": 0,
            "issues": [],
            "reason": "No weaknesses detected — nothing to refine.",
        }

    # ── Baseline evaluation (unmutated) ──
    current = _evaluate_variant(
        strategy_text, pair, timeframe, prices, data_points,
        param_ov=base_params if base_params else None,
        ind_ov=None,
        rules_config=rules_config,
        mc_sims=mc_simulations,
        sim_config=sim_config,
    )
    # P0 — if the unmutated baseline is unscoreable (no trades, no real
    # data, null PF) we cannot meaningfully refine it: every mutation
    # comparison would either crash or be a coin-flip. Short-circuit
    # with a structured reason instead.
    if current.get("invalid"):
        return {
            "success": True,
            "improved": False,
            "cycles_run": 0,
            "issues": [it.get("name") for it in issues],
            "reason": (
                f"Baseline strategy is unscoreable "
                f"({current.get('invalid_reason','no_trades')}) — "
                "refinement skipped."
            ),
            "baseline_invalid": True,
            "invalid_reason": current.get("invalid_reason"),
        }
    original_snapshot = {
        "max_drawdown_pct": current["backtest"]["max_drawdown_pct"],
        "pass_probability": current["probability"]["pass_probability"],
        "total_return_pct": current["backtest"]["total_return_pct"],
        "profit_factor": current["backtest"]["profit_factor"],
        "win_rate": current["backtest"]["win_rate"],
    }

    history: list[dict] = []
    best_variant = None
    current_params = dict(base_params) if base_params else {
        "fast_period": 8, "slow_period": 21,
        "sl_pips": 20, "tp_pips": 35,
        "rsi_period": 0, "rsi_buy_threshold": 50, "rsi_sell_threshold": 50,
    }

    # ── Iterate up to max_cycles ──
    for cycle in range(1, max_cycles + 1):
        variants = _gen_mutations(current_params, issues)[:variants_per_cycle]
        if not variants:
            history.append({"cycle": cycle, "chosen": None, "reason": "no variants generated"})
            break

        best_this_cycle = None
        best_reason = None
        for mv in variants:
            try:
                ev = _evaluate_variant(
                    strategy_text, pair, timeframe, prices, data_points,
                    param_ov=mv["param_overrides"],
                    ind_ov=mv["indicators_override"],
                    rules_config=rules_config,
                    mc_sims=mc_simulations,
                    sim_config=sim_config,
                )
            except Exception as e:
                logger.warning(f"variant {mv['name']} eval failed: {e}")
                continue
            better, reason = _is_improvement(current, ev)
            if better and (
                best_this_cycle is None
                or ev["probability"]["pass_probability"]
                > best_this_cycle["ev"]["probability"]["pass_probability"]
            ):
                best_this_cycle = {"variant": mv, "ev": ev, "reason": reason}
                best_reason = reason

        if not best_this_cycle:
            history.append({"cycle": cycle, "chosen": None,
                            "reason": "no variant improved baseline"})
            break

        # Accept: promote to new baseline
        chosen = best_this_cycle["variant"]
        current = best_this_cycle["ev"]
        current_params = {**current_params, **(chosen.get("param_overrides") or {})}
        best_variant = best_this_cycle
        history.append({
            "cycle": cycle,
            "chosen": chosen["name"],
            "description": chosen["description"],
            "changes": chosen["changes"],
            "reason": best_reason,
        })

        # Re-diagnose for next cycle using the new metrics
        pseudo_panel = {
            "max_drawdown": current["backtest"]["max_drawdown_pct"],
            "daily_drawdown": current["simulation"]["max_daily_dd_pct"],
            "pass_probability": current["probability"]["pass_probability"],
            "violations": {
                "daily_dd": 1 if current["simulation"]["failure_reason"] == "max_daily_drawdown" else 0,
                "max_dd": 1 if current["simulation"]["failure_reason"] == "max_total_drawdown" else 0,
                "consistency": 0, "profit_target": 0, "min_days": 0,
            },
        }
        issues = _diagnose_from_reports(
            validation_report=None,
            decision=None,
            prop_firm_panel=pseudo_panel,
            base_backtest=current["backtest"],
        )
        if not issues:
            history.append({"cycle": cycle + 1, "chosen": None,
                            "reason": "all weaknesses resolved"})
            break

    if best_variant is None:
        return {
            "success": True,
            "improved": False,
            "cycles_run": len(history),
            "issues": issues,
            "original": original_snapshot,
            "history": history,
            "reason": "No mutation beat the baseline.",
        }

    # ── Re-score the refined variant (Phase 8.5 + 9) ──
    best_ev = best_variant["ev"]
    vr, dec, panel = _rescore_refined(
        strategy_text, pair, timeframe, prices, rules_config, best_ev,
    )

    refined_snapshot = {
        "max_drawdown_pct": best_ev["backtest"]["max_drawdown_pct"],
        "pass_probability": best_ev["probability"]["pass_probability"],
        "total_return_pct": best_ev["backtest"]["total_return_pct"],
        "profit_factor": best_ev["backtest"]["profit_factor"],
        "win_rate": best_ev["backtest"]["win_rate"],
    }

    def _delta(name: str, a_val, b_val) -> dict:
        if a_val is None or b_val is None:
            return {"from": a_val, "to": b_val, "delta": None}
        return {"from": round(a_val, 2), "to": round(b_val, 2),
                "delta": round(b_val - a_val, 2)}

    improvement = {
        "max_drawdown_pct": _delta("dd",
                                   original_snapshot["max_drawdown_pct"],
                                   refined_snapshot["max_drawdown_pct"]),
        "pass_probability": _delta("pp",
                                   original_snapshot["pass_probability"],
                                   refined_snapshot["pass_probability"]),
        "total_return_pct": _delta("ret",
                                   original_snapshot["total_return_pct"],
                                   refined_snapshot["total_return_pct"]),
        "profit_factor": _delta("pf",
                                original_snapshot["profit_factor"],
                                refined_snapshot["profit_factor"]),
    }

    return {
        "success": True,
        "improved": True,
        "cycles_run": sum(1 for h in history if h.get("chosen")),
        "issues_initial": _diagnose_from_reports(
            strategy.get("validation_report"),
            strategy.get("decision"),
            strategy.get("prop_firm_panel"),
            strategy.get("backtest"),
        ),
        "original": original_snapshot,
        "refined_snapshot": refined_snapshot,
        "improvement": improvement,
        "best_variant": {
            "name": best_variant["variant"]["name"],
            "description": best_variant["variant"]["description"],
            "changes": best_variant["variant"]["changes"],
            "param_overrides": best_variant["variant"]["param_overrides"],
            "indicators_override": best_variant["variant"]["indicators_override"],
        },
        "refined_strategy": {
            "strategy_text": strategy_text,
            "param_overrides": current_params,
            "indicators_override": best_variant["variant"]["indicators_override"],
            "validation_report": vr,
            "decision": dec,
            "prop_firm_panel": panel,
        },
        "history": history,
    }


def refine_top_candidates(
    ranked_list: list,
    strategy_inputs_by_id: dict,
    top_n: int = 3,
    max_cycles: int = MAX_CYCLES_DEFAULT,
    variants_per_cycle: int = VARIANTS_PER_CYCLE_DEFAULT,
    mc_simulations: int = 20,
    sim_config: dict | None = None,
) -> list:
    """
    Apply refinement to the top N ranked strategies only.

    Args:
        ranked_list: output of `engines.strategy_ranking_engine.rank_strategies`.
        strategy_inputs_by_id: map {strategy_id: full strategy dict} with the
                               fields required by `refine_strategy`.
        top_n: how many ranked strategies to refine (default 3).
        sim_config: optional per-call simulation config. P2 — when this
                   contains `quality_filter=True`, every refinement
                   variant is evaluated under the same quality gate as
                   the live system.

    Returns:
        list of refinement results (one per processed strategy).
    """
    if not ranked_list or not strategy_inputs_by_id:
        return []
    out = []
    for entry in ranked_list[:max(0, int(top_n))]:
        sid = entry.get("strategy_id")
        src = strategy_inputs_by_id.get(sid)
        if not src:
            continue
        result = refine_strategy(
            src,
            max_cycles=max_cycles,
            variants_per_cycle=variants_per_cycle,
            mc_simulations=mc_simulations,
            sim_config=sim_config,
        )
        result["strategy_id"] = sid
        out.append(result)
    return out

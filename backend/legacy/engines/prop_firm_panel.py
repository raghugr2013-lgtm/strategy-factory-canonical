"""
Phase 9 — Prop Firm Intelligence Panel.

Converts raw engine outputs (challenge simulation, pass probability,
validation report, decision) into a single, UI-ready panel dict with a
clear SAFE / RISKY / FAIL readiness status.

Pure composition — no new metrics are computed, no simulations run.

Input (all optional, tolerant to partial data):
    simulation         : dict from engines.challenge_simulator.simulate_challenge
    pass_probability   : scalar % OR dict from engines.pass_probability
    validation_report  : dict from engines.validation_report / validation_engine full mode
    decision           : dict from engines.decision_engine.decide

Output:
    {
      "pass_probability": float | None,
      "max_drawdown":      float | None,      # total DD %
      "daily_drawdown":    float | None,      # worst single-day DD %
      "consistency_score": float | None,      # 0-100 (from validation stability)
      "violations": {"daily_dd": int, "max_dd": int, "consistency": int,
                     "profit_target": int, "min_days": int},
      "status": "SAFE" | "RISKY" | "FAIL",
      "recommendation": "short message"
    }
"""
from __future__ import annotations


RISKY_PROB_THRESHOLD = 50.0   # < this = RISKY (unless other factors fail it)


# ── Extractors ────────────────────────────────────────────────────────

def _pass_prob(pass_probability, simulation: dict | None) -> float | None:
    if isinstance(pass_probability, (int, float)):
        return float(pass_probability)
    if isinstance(pass_probability, dict):
        if isinstance(pass_probability.get("pass_probability"), (int, float)):
            return float(pass_probability["pass_probability"])
        inner = pass_probability.get("probability")
        if isinstance(inner, dict) and isinstance(inner.get("pass_probability"), (int, float)):
            return float(inner["pass_probability"])
    if simulation and simulation.get("status") == "pass":
        return 100.0
    return None


def _get_verdict(decision) -> str | None:
    if isinstance(decision, dict):
        if isinstance(decision.get("decision"), dict):
            return decision["decision"].get("verdict")
        return decision.get("verdict")
    return None


def _consistency(validation_report: dict | None) -> float | None:
    """Reuse validation stability score as consistency proxy."""
    if not validation_report:
        return None
    st = validation_report.get("stability_score")
    if isinstance(st, dict) and isinstance(st.get("score"), (int, float)):
        return float(st["score"])
    if isinstance(st, (int, float)):
        return float(st)
    basic = validation_report.get("basic") or {}
    if basic.get("stability") and isinstance(basic["stability"].get("score"), (int, float)):
        return float(basic["stability"]["score"])
    return None


def _count_violations(simulation: dict | None) -> tuple[dict, list[str]]:
    """
    Count rule violations from challenge_simulator output.
    Returns (counts_dict, human_readable_reasons).
    """
    counts = {"daily_dd": 0, "max_dd": 0, "consistency": 0,
              "profit_target": 0, "min_days": 0}
    reasons: list[str] = []
    if not simulation:
        return counts, reasons

    status = simulation.get("status")
    reason = simulation.get("failure_reason")

    if reason == "max_daily_drawdown":
        counts["daily_dd"] = 1
        reasons.append("Daily drawdown limit exceeded.")
    elif reason == "max_total_drawdown":
        counts["max_dd"] = 1
        reasons.append("Total drawdown limit exceeded.")
    elif reason == "consistency_rule" or simulation.get("consistency_violated"):
        counts["consistency"] = 1
        reasons.append("Consistency rule violated.")
    elif reason == "profit_target_not_reached":
        counts["profit_target"] = 1
        reasons.append("Profit target not reached.")
    elif reason == "min_days_not_met":
        counts["min_days"] = 1
        reasons.append("Minimum trading days not met.")
    elif status == "fail" and reason:
        reasons.append(f"Failed: {reason}.")

    # Soft-check: DD seen exceeded limit even if status didn't mark it (edge
    # cases with partial replay).
    dd_seen = simulation.get("max_drawdown_pct")
    dd_limit = simulation.get("max_total_dd_limit_pct")
    if (isinstance(dd_seen, (int, float)) and isinstance(dd_limit, (int, float))
            and dd_limit > 0 and dd_seen >= dd_limit and counts["max_dd"] == 0):
        counts["max_dd"] = 1
        reasons.append(f"Total DD {dd_seen:.2f}% ≥ limit {dd_limit:.2f}%.")

    ddd_seen = simulation.get("max_daily_drawdown_pct")
    ddd_limit = simulation.get("max_daily_dd_limit_pct")
    if (isinstance(ddd_seen, (int, float)) and isinstance(ddd_limit, (int, float))
            and ddd_limit > 0 and ddd_seen >= ddd_limit and counts["daily_dd"] == 0):
        counts["daily_dd"] = 1
        reasons.append(f"Daily DD {ddd_seen:.2f}% ≥ limit {ddd_limit:.2f}%.")

    return counts, reasons


# ── Public API ────────────────────────────────────────────────────────

def build_prop_firm_panel(
    simulation: dict | None = None,
    pass_probability=None,
    validation_report: dict | None = None,
    decision=None,
) -> dict:
    """
    Produce the Prop Firm Intelligence Panel. See module docstring.
    """
    prob = _pass_prob(pass_probability, simulation)
    verdict = _get_verdict(decision)
    consistency = _consistency(validation_report)
    violations, violation_reasons = _count_violations(simulation)
    any_violation = any(v > 0 for v in violations.values())

    max_dd = simulation.get("max_drawdown_pct") if simulation else None
    daily_dd = simulation.get("max_daily_drawdown_pct") if simulation else None

    # ── Status rules ──
    #   1. Any rule violation                → FAIL
    #   2. Decision = REJECT                 → FAIL
    #   3. Pass probability < 50             → RISKY
    #   4. Otherwise                         → SAFE
    if any_violation:
        status = "FAIL"
    elif verdict == "REJECT":
        status = "FAIL"
    elif prob is not None and prob < RISKY_PROB_THRESHOLD:
        status = "RISKY"
    elif verdict == "RISKY":
        status = "RISKY"
    else:
        status = "SAFE"

    # ── Recommendation (short) ──
    if status == "FAIL":
        if violation_reasons:
            recommendation = violation_reasons[0]
        elif verdict == "REJECT":
            recommendation = "Strategy rejected — do not take the challenge."
        else:
            recommendation = "Challenge failed — review drawdown and targets."
    elif status == "RISKY":
        bits = []
        if prob is not None:
            bits.append(f"pass probability {prob:.0f}%")
        if verdict == "RISKY":
            bits.append("decision flagged risky")
        if consistency is not None and consistency < 50:
            bits.append(f"low consistency {consistency:.0f}")
        recommendation = "Proceed with caution: " + (", ".join(bits) if bits else "mixed signals") + "."
    else:
        bits = ["no rule violations"]
        if prob is not None:
            bits.append(f"pass probability {prob:.0f}%")
        if consistency is not None:
            bits.append(f"consistency {consistency:.0f}/100")
        recommendation = "Ready for prop firm: " + ", ".join(bits) + "."

    return {
        "pass_probability": None if prob is None else round(prob, 2),
        "max_drawdown": None if max_dd is None else round(max_dd, 2),
        "daily_drawdown": None if daily_dd is None else round(daily_dd, 2),
        "consistency_score": None if consistency is None else round(consistency, 1),
        "violations": violations,
        "status": status,
        "recommendation": recommendation,
        "meta": {
            "verdict": verdict,
            "firm": (simulation or {}).get("rules_used", {}).get("firm_name"),
            "challenge_status": (simulation or {}).get("status"),
            "failure_reason": (simulation or {}).get("failure_reason"),
        },
    }

"""
Phase 8 — Combined Validation Report.

Aggregates walk-forward + holdout results (and optionally the legacy
basic segment validation) into a single JSON payload with derived
overfit_score and stability_score for UI/decision-engine consumption.

Pure composition — performs no backtests itself. Input dicts come from
walk_forward_engine.run_walk_forward, oos_holdout.run_oos_holdout, and
the basic validation_engine.run_validation.
"""
from __future__ import annotations


def _derive_overfit_score(walk_forward: dict | None, holdout: dict | None) -> dict:
    """
    Overfit score 0-100: higher = MORE overfit (worse).
    Combines:
      * Holdout return-degradation (0 best, 100 worst)   weight 50%
      * Walk-forward mean degradation                    weight 30%
      * Walk-forward OOS profitable ratio (inverted)     weight 20%
    """
    components = {}
    score = 0.0
    weight_sum = 0.0

    if holdout and holdout.get("success"):
        deg = holdout.get("degradation", {}).get("return_pct_degradation", 0)
        # Map degradation in [-200, 200] to a 0-100 overfit component.
        # deg <= 0  → no overfit (0). deg >= 100 → max overfit (100).
        ho_comp = max(0.0, min(100.0, deg))
        components["holdout_degradation"] = round(ho_comp, 1)
        score += ho_comp * 0.5
        weight_sum += 0.5

    if walk_forward and walk_forward.get("success"):
        wf_deg = walk_forward.get("aggregate", {}).get("mean_degradation_pct", 0)
        wf_deg_comp = max(0.0, min(100.0, wf_deg))
        components["wf_mean_degradation"] = round(wf_deg_comp, 1)
        score += wf_deg_comp * 0.3
        weight_sum += 0.3

        profit_ratio = walk_forward.get("aggregate", {}).get("oos_profitable_ratio", 0)
        # 1.0 ratio → 0 overfit pts; 0.0 ratio → 100 pts
        wf_profit_comp = max(0.0, min(100.0, (1.0 - profit_ratio) * 100.0))
        components["wf_oos_profitability"] = round(wf_profit_comp, 1)
        score += wf_profit_comp * 0.2
        weight_sum += 0.2

    if weight_sum == 0:
        return {"score": None, "grade": "N/A", "components": components}

    normalized = round(score / weight_sum, 1)
    if normalized <= 15:
        grade = "A"
    elif normalized <= 30:
        grade = "B"
    elif normalized <= 50:
        grade = "C"
    elif normalized <= 70:
        grade = "D"
    else:
        grade = "F"

    return {"score": normalized, "grade": grade, "components": components}


def _derive_stability_score(
    walk_forward: dict | None,
    basic: dict | None,
) -> dict:
    """
    Stability 0-100 (higher = better). Prefers walk-forward result; falls
    back to the basic segment stability if WF is unavailable.
    """
    components = {}
    if walk_forward and walk_forward.get("success"):
        wf_stab = walk_forward.get("aggregate", {}).get("stability_score", 0)
        components["walk_forward"] = wf_stab
    if basic and basic.get("success"):
        basic_stab = basic.get("stability", {}).get("score", 0)
        components["basic_segments"] = basic_stab

    if not components:
        return {"score": None, "grade": "N/A", "components": components}

    if "walk_forward" in components:
        score = components["walk_forward"]
    else:
        score = components.get("basic_segments", 0)

    if score >= 75:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 45:
        grade = "C"
    elif score >= 30:
        grade = "D"
    else:
        grade = "F"
    return {"score": round(score, 1), "grade": grade, "components": components}


def build_validation_report(
    walk_forward: dict | None = None,
    oos_holdout: dict | None = None,
    basic: dict | None = None,
) -> dict:
    """
    Compose the combined Phase 8 validation report.

    Input dicts may be None when a particular mode wasn't run.
    The output schema is additive and UI-friendly.
    """
    overfit = _derive_overfit_score(walk_forward, oos_holdout)
    stability = _derive_stability_score(walk_forward, basic)

    verdict = "UNKNOWN"
    notes = []
    if overfit["score"] is not None and stability["score"] is not None:
        if overfit["score"] <= 30 and stability["score"] >= 60:
            verdict = "ROBUST"
            notes.append("Low overfit + high stability.")
        elif overfit["score"] <= 50 and stability["score"] >= 45:
            verdict = "ACCEPTABLE"
            notes.append("Moderate overfit risk; usable with caution.")
        elif overfit["score"] >= 70:
            verdict = "OVERFIT"
            notes.append("High overfit signal — reject or re-optimize.")
        else:
            verdict = "FRAGILE"
            notes.append("Unstable OOS performance.")

    if oos_holdout and oos_holdout.get("success") and oos_holdout.get("overfit", {}).get("flagged"):
        notes.append("Holdout overfit flag: " + str(oos_holdout["overfit"].get("reason")))

    return {
        "walk_forward": walk_forward,
        "oos_holdout": oos_holdout,
        "basic": basic,
        "overfit_score": overfit,
        "stability_score": stability,
        "verdict": verdict,
        "notes": notes,
    }

"""
Phase 8.5 — Decision Engine.

Single responsibility: turn the numbers produced by upstream engines into a
one-line trading decision: TRADE | RISKY | REJECT.

Inputs (all optional — engine uses whatever is provided):
    validation_report : dict  — from engines.validation_report.build_validation_report
                                (or a 'full'-mode validation_engine result).
                                Required keys it reads:
                                    overfit_score.score       (0-100, higher = worse)
                                    stability_score.score     (0-100, higher = better)
                                    walk_forward.aggregate.oos_avg_return_pct
                                    oos_holdout.oos_metrics.total_return_pct
                                    oos_holdout.overfit.flagged
    expected_value    : dict  — from engines.expected_value.calculate_expected_value
                                Reads: expected_value (USD), ev_grade
    pass_probability  : dict or float — from engines.pass_probability or a raw %

Output:
    {
      "decision": {"verdict": "TRADE"|"RISKY"|"REJECT",
                   "confidence": 0-100,
                   "reason": str},
      "scores":   {"overfit": 0-100,      # higher = MORE overfit (worse)
                   "stability": 0-100,    # higher = better
                   "expected_value": float,
                   "ev_score": 0-100,     # normalised EV
                   "pass_probability": 0-100,
                   "oos_return_pct": float or None}
    }

Rules (intentionally simple — no overengineering):
    1. If OOS return < 0  (either WF avg or holdout)          → REJECT
    2. If overfit_score ≥ 70                                  → REJECT
    3. If EV > 0 AND stability ≥ 60 AND overfit ≤ 40
       AND pass_probability ≥ 50                              → TRADE
    4. Everything else                                        → RISKY
Confidence is a weighted blend of the four scores, clamped 0-100.
"""
from __future__ import annotations


# ── Tunables (kept small on purpose) ──────────────────────────────────
REJECT_OVERFIT_SCORE = 70          # hard reject threshold
TRADE_OVERFIT_SCORE = 40           # must be at or below for TRADE
TRADE_STABILITY_SCORE = 60         # must be at or above for TRADE
TRADE_PASS_PROB = 50.0             # must be at or above for TRADE


def _extract_overfit(validation_report: dict | None) -> float | None:
    if not validation_report:
        return None
    ov = validation_report.get("overfit_score")
    if isinstance(ov, dict):
        return ov.get("score")
    if isinstance(ov, (int, float)):
        return float(ov)
    return None


def _extract_stability(validation_report: dict | None) -> float | None:
    if not validation_report:
        return None
    st = validation_report.get("stability_score")
    if isinstance(st, dict):
        return st.get("score")
    if isinstance(st, (int, float)):
        return float(st)
    # Fallback: legacy 'basic' validation
    basic = validation_report.get("basic") or {}
    if basic.get("stability"):
        return basic["stability"].get("score")
    return None


def _extract_oos_return(validation_report: dict | None) -> float | None:
    """Prefer walk-forward OOS avg, fall back to holdout OOS."""
    if not validation_report:
        return None
    wf = validation_report.get("walk_forward") or {}
    if wf.get("success") and wf.get("aggregate"):
        return wf["aggregate"].get("oos_avg_return_pct")
    ho = validation_report.get("oos_holdout") or {}
    if ho.get("success") and ho.get("oos_metrics"):
        return ho["oos_metrics"].get("total_return_pct")
    return None


def _extract_ev(expected_value: dict | None) -> tuple[float | None, str | None]:
    if not expected_value:
        return None, None
    return expected_value.get("expected_value"), expected_value.get("ev_grade")


def _extract_prob(pass_probability) -> float | None:
    if pass_probability is None:
        return None
    if isinstance(pass_probability, (int, float)):
        return float(pass_probability)
    if isinstance(pass_probability, dict):
        # Accept either a wrapper or the raw block
        if "pass_probability" in pass_probability:
            return float(pass_probability["pass_probability"])
        if "probability" in pass_probability and isinstance(pass_probability["probability"], dict):
            return float(pass_probability["probability"].get("pass_probability", 0))
    return None


def _ev_to_score(ev_usd: float | None) -> float:
    """Map EV in USD to a 0-100 score. 0 EV → 50. $500 EV → ~85. Negative → <50."""
    if ev_usd is None:
        return 50.0
    score = 50.0 + ev_usd / 15.0   # $750 EV = 100, −$750 = 0
    return round(max(0.0, min(100.0, score)), 1)


def _confidence(
    overfit: float | None,
    stability: float | None,
    ev_score: float,
    pass_prob: float | None,
) -> float:
    """
    Weighted blend 0-100.
    Weights: stability 30%, (100-overfit) 30%, ev_score 20%, pass_prob 20%.
    Missing components contribute a neutral 50 and their weight is kept so
    confidence doesn't swing wildly based on what we were given.
    """
    stab = 50.0 if stability is None else stability
    ov_inv = 50.0 if overfit is None else max(0.0, 100.0 - overfit)
    prob = 50.0 if pass_prob is None else pass_prob
    conf = stab * 0.30 + ov_inv * 0.30 + ev_score * 0.20 + prob * 0.20
    return round(max(0.0, min(100.0, conf)), 1)


def decide(
    validation_report: dict | None = None,
    expected_value: dict | None = None,
    pass_probability=None,
) -> dict:
    """
    Produce a final TRADE / RISKY / REJECT verdict with confidence + reason.
    See module docstring for the exact rule set.
    """
    overfit = _extract_overfit(validation_report)
    stability = _extract_stability(validation_report)
    oos_return = _extract_oos_return(validation_report)
    ev_usd, ev_grade = _extract_ev(expected_value)
    prob = _extract_prob(pass_probability)
    ev_score = _ev_to_score(ev_usd)

    # Holdout explicit overfit flag (strong signal)
    holdout_flag = False
    if validation_report:
        ho = validation_report.get("oos_holdout") or {}
        holdout_flag = bool((ho.get("overfit") or {}).get("flagged"))

    verdict = None
    reason = None

    # Rule 1: OOS negative → REJECT
    if oos_return is not None and oos_return < 0:
        verdict = "REJECT"
        reason = f"OOS return is negative ({oos_return:.2f}%)."

    # Rule 2: High overfit → REJECT
    elif overfit is not None and overfit >= REJECT_OVERFIT_SCORE:
        verdict = "REJECT"
        reason = f"Overfit score {overfit:.0f}/100 exceeds reject threshold ({REJECT_OVERFIT_SCORE})."

    elif holdout_flag and (oos_return is None or oos_return <= 0):
        verdict = "REJECT"
        reason = "Holdout flagged overfitting (profitable on train, weak/negative on OOS)."

    # Rule 3: All green → TRADE
    elif (
        ev_usd is not None and ev_usd > 0
        and stability is not None and stability >= TRADE_STABILITY_SCORE
        and overfit is not None and overfit <= TRADE_OVERFIT_SCORE
        and (prob is None or prob >= TRADE_PASS_PROB)
    ):
        verdict = "TRADE"
        reason = (
            f"Positive EV (${ev_usd:.0f}), stability {stability:.0f}/100, "
            f"overfit {overfit:.0f}/100"
            + (f", pass prob {prob:.0f}%." if prob is not None else ".")
        )

    # Rule 4: Everything else → RISKY
    else:
        verdict = "RISKY"
        bits = []
        if ev_usd is None:
            bits.append("EV unknown")
        elif ev_usd <= 0:
            bits.append(f"EV non-positive (${ev_usd:.0f})")
        if stability is None:
            bits.append("stability unknown")
        elif stability < TRADE_STABILITY_SCORE:
            bits.append(f"stability low ({stability:.0f}/100)")
        if overfit is not None and overfit > TRADE_OVERFIT_SCORE:
            bits.append(f"overfit elevated ({overfit:.0f}/100)")
        if prob is not None and prob < TRADE_PASS_PROB:
            bits.append(f"pass prob low ({prob:.0f}%)")
        reason = "Mixed signals: " + ("; ".join(bits) if bits else "metrics incomplete") + "."

    confidence = _confidence(overfit, stability, ev_score, prob)

    return {
        "decision": {
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason,
        },
        "scores": {
            "overfit": overfit,
            "stability": stability,
            "expected_value": ev_usd,
            "ev_grade": ev_grade,
            "ev_score": ev_score,
            "pass_probability": prob,
            "oos_return_pct": oos_return,
        },
        "thresholds": {
            "reject_overfit": REJECT_OVERFIT_SCORE,
            "trade_overfit_max": TRADE_OVERFIT_SCORE,
            "trade_stability_min": TRADE_STABILITY_SCORE,
            "trade_pass_prob_min": TRADE_PASS_PROB,
        },
    }

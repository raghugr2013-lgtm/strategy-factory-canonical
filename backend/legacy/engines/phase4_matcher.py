"""
Phase 4 — Strategy ↔ Prop Firm Matcher (wrapper).

Thin orchestrator around the existing `matching_engine.match_strategy_to_firms`.
Shapes its output into the Phase 4 contract:

    [{
        "firm": "FTMO",
        "plan": "100K 2-Step",
        "score": 78.4,
        "pass_probability": 72.5,
        "expected_value": 1230.5,
        "risk": "LOW" | "MEDIUM" | "HIGH",
        "verdict": "BEST" | "SAFE" | "RISKY",
        ...supporting fields...
    }, ...]

Ranking formula (composite 0-100):
    final_score =
          0.35 * pass_probability
        + 0.25 * normalize_ev(ev, fee)
        + 0.20 * safety_margin_score
        + 0.10 * stability_score(profile)
        − 0.15 * overfit_score          # overfit is a penalty, not a bonus

Verdict:
    BEST  — pass_probability ≥ 65  AND  safety ∈ {safe, moderate}  AND  overfit ≤ 40
    SAFE  — pass_probability ≥ 50  AND  no violations
    RISKY — everything else

Risk:
    LOW    ← safety_margin.risk_level = "safe"
    MEDIUM ← safety_margin.risk_level = "moderate"
    HIGH   ← safety_margin.risk_level ∈ {"danger", "breached"}

DOES NOT modify the existing matching engine. Additive only.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from engines.matching_engine import match_strategy_to_firms

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Ranking weights (0.35 + 0.25 + 0.20 + 0.10 = 0.90 positive;
# overfit applies a subtractive penalty up to −0.15 × 100 = −15).
# ═══════════════════════════════════════════════════════════
W_PASS_PROB = 0.35
W_EV = 0.25
W_SAFETY = 0.20
W_STABILITY = 0.10
W_OVERFIT_PENALTY = 0.15

# Verdict thresholds (from approved spec)
BEST_MIN_PROB = 65.0
BEST_MAX_OVERFIT = 40.0
SAFE_MIN_PROB = 50.0
SAFE_ALLOWED_SAFETY = {"safe", "moderate"}

# Safety → risk label mapping
_RISK_MAP = {
    "safe": "LOW",
    "moderate": "MEDIUM",
    "danger": "HIGH",
    "breached": "HIGH",
}

# ═══════════════════════════════════════════════════════════
# Realism layer — firm + challenge-type + conservative caps
# ═══════════════════════════════════════════════════════════

# Per-firm strictness profile. `dd_strictness` multiplies the DD-proximity
# score penalty; `consistency_strictness` multiplies the variance penalty.
# `scaling_bonus` gives a small push for firms with favourable scaling plans.
# Values > 1 = stricter firm.
FIRM_PROFILES: Dict[str, Dict[str, float]] = {
    "ftmo":       {"dd_strictness": 1.35, "consistency_strictness": 1.25, "scaling_bonus": 0.0,
                   "label": "strict — tight DD & consistency"},
    "fundednext": {"dd_strictness": 1.00, "consistency_strictness": 1.00, "scaling_bonus": 2.0,
                   "label": "balanced — moderate rules"},
    "the5ers":    {"dd_strictness": 0.90, "consistency_strictness": 1.15, "scaling_bonus": 4.0,
                   "label": "scaling-friendly — lower targets, gradual"},
    "pipfarm":    {"dd_strictness": 0.95, "consistency_strictness": 0.90, "scaling_bonus": 1.5,
                   "label": "flexible — lenient DD"},
}
_DEFAULT_FIRM_PROFILE = {
    "dd_strictness": 1.05, "consistency_strictness": 1.05, "scaling_bonus": 0.0,
    "label": "unknown firm — default strictness",
}

# Challenge-type multipliers on the raw Monte-Carlo pass probability.
# Rationale:
#   1-step    → simplest, full prob
#   2-step    → must pass both stages; conditional prob ≈ p² but most MC
#               engines measure a single pass — apply a conservative haircut
#   instant   → low fee but scaling/payout restrictions reduce realized EV
#   plan      → unknown legacy type, mild haircut
CHALLENGE_TYPE_MODIFIERS: Dict[str, Dict[str, float]] = {
    "1step":   {"prob_mult": 1.00, "label": "1-step (single evaluation)"},
    "2step":   {"prob_mult": 0.82, "label": "2-step (must clear both phases)"},
    "instant": {"prob_mult": 0.88, "label": "instant (scaling gated)"},
    "plan":    {"prob_mult": 0.92, "label": "generic plan"},
}
_DEFAULT_CHALLENGE_TYPE = "2step"


def _firm_profile(firm_slug: str) -> Dict[str, float]:
    """Resolve strictness profile. Matches the base firm name before the
    Phase-3 plan suffix (e.g. ftmo_100k_2step → ftmo)."""
    if not firm_slug:
        return _DEFAULT_FIRM_PROFILE
    key = firm_slug.lower()
    if key in FIRM_PROFILES:
        return FIRM_PROFILES[key]
    base = key.split("_", 1)[0]
    return FIRM_PROFILES.get(base, _DEFAULT_FIRM_PROFILE)


def _challenge_type_from_slug(firm_slug: str, phase: str = "") -> str:
    """Extract 1step / 2step / instant from Phase-3 slug, falling back to
    the legacy `phase` string from the challenge rule doc."""
    s = (firm_slug or "").lower()
    for t in ("1step", "2step", "instant"):
        if s.endswith(f"_{t}"):
            return t
    ph = (phase or "").lower()
    if "1-step" in ph or "1 step" in ph:
        return "1step"
    if "2-step" in ph or "2 step" in ph or "phase" in ph:
        return "2step"
    if "instant" in ph:
        return "instant"
    return _DEFAULT_CHALLENGE_TYPE


def _firm_dd_limit_pct(match: Dict[str, Any]) -> float:
    """Infer the firm's max total-DD limit from the engine's buffer telemetry:
         buffer_remaining = limit − observed_dd
    """
    dd_buffer = (match.get("drawdown_buffer") or {}).get("total_dd")
    observed = match.get("max_drawdown_pct")
    if dd_buffer is None or observed is None:
        return 0.0
    try:
        return max(0.0, float(dd_buffer) + float(observed))
    except (TypeError, ValueError):
        return 0.0


def apply_realism(
    pass_prob_raw: float,
    total_trades: int,
    profile_summary: Dict[str, Any],
    match: Dict[str, Any],
    firm_slug: str,
    phase: str,
) -> Dict[str, Any]:
    """
    Core realism layer. Returns a dict with the adjusted pass_probability
    plus the notes / multipliers applied. All fields are surfaced in the
    final API payload so the reduction is explainable, not magic.

    Steps (in order):
      1. Hard cap at 95   (MC 100 % is almost always a small-sample artefact).
      2. Trade-count gate — aggressive cap below 30 trades.
      3. Variance gate    — equity-curve smoothness < 50 → proportional haircut.
      4. Sharpe gate      — Sharpe < 1.0 → stability haircut.
      5. DD-proximity     — observed DD > 60 % of firm limit → tail-risk haircut
                            (amplified by firm-specific `dd_strictness`).
      6. Challenge-type   — 1-step / 2-step / instant multiplier.
    """
    notes: List[str] = []
    firm_prof = _firm_profile(firm_slug)
    challenge_type = _challenge_type_from_slug(firm_slug, phase)
    type_mod = CHALLENGE_TYPE_MODIFIERS.get(challenge_type, CHALLENGE_TYPE_MODIFIERS["plan"])

    p = float(pass_prob_raw or 0.0)

    # 1. Hard cap
    if p > 95.0:
        notes.append("capped_at_95")
        p = 95.0

    # 2. Trade-count reliability gate (60 @ 0 trades, 80 @ 30+, linear)
    if total_trades < 30:
        cap = 60.0 + (total_trades / 30.0) * 20.0
        if p > cap:
            notes.append(f"low_trade_count_{total_trades}_trades")
            p = cap

    # 3. Variance gate
    smoothness = float(profile_summary.get("equity_curve_smoothness", 0) or 0)
    cons_strict = float(firm_prof.get("consistency_strictness", 1.0))
    if smoothness < 50:
        base_factor = 0.7 + (smoothness / 50.0) * 0.3            # 0→0.7, 50→1.0
        factor = max(0.55, 1.0 - (1.0 - base_factor) * cons_strict)
        p *= factor
        notes.append(f"variance_penalty_x{round(factor,2)}")

    # 4. Sharpe gate
    sharpe = float(profile_summary.get("sharpe_ratio", 0) or 0)
    if sharpe < 1.0:
        base_factor = 0.85 + (max(0.0, sharpe) / 1.0) * 0.15    # 0→0.85, 1.0→1.0
        factor = max(0.65, 1.0 - (1.0 - base_factor) * cons_strict)
        p *= factor
        notes.append(f"low_sharpe_x{round(factor,2)}")

    # 5. DD-proximity (firm-specific strictness)
    firm_dd_limit = _firm_dd_limit_pct(match)
    observed_dd = float(match.get("max_drawdown_pct", 0) or 0)
    dd_used = 0.0
    if firm_dd_limit > 0:
        dd_used = min(1.0, observed_dd / firm_dd_limit)
        if dd_used > 0.6:
            base_factor = 1.0 - (dd_used - 0.6) * 0.5            # used=1.0 → 0.8
            dd_strict = float(firm_prof.get("dd_strictness", 1.0))
            factor = max(0.50, 1.0 - (1.0 - base_factor) * dd_strict)
            p *= factor
            notes.append(f"dd_pressure_{round(dd_used*100)}pct")

    # 6. Challenge-type haircut
    p *= float(type_mod.get("prob_mult", 1.0))
    if type_mod.get("prob_mult", 1.0) < 1.0:
        notes.append(f"{challenge_type}_x{round(type_mod['prob_mult'],2)}")

    p = max(0.0, min(100.0, p))
    return {
        "pass_probability": round(p, 1),
        "pass_probability_raw": round(float(pass_prob_raw or 0.0), 1),
        "realism_notes": notes,
        "challenge_type": challenge_type,
        "challenge_type_label": type_mod.get("label", challenge_type),
        "firm_strictness": firm_prof.get("label", ""),
        "dd_used_pct": round(dd_used * 100, 1),
        "firm_dd_limit_pct": round(firm_dd_limit, 2),
    }


def realistic_ev(pass_prob_pct: float, fee: float, reward: float) -> float:
    """
    EV = p · reward − (1 − p) · fee
    Uses the ADJUSTED pass probability so inflated raw prob no longer
    propagates into inflated EV. Returns dollars.
    """
    if fee is None or fee <= 0:
        return 0.0
    p = max(0.0, min(1.0, (pass_prob_pct or 0.0) / 100.0))
    r = float(reward or 0.0)
    return p * r - (1.0 - p) * float(fee)

# ═══════════════════════════════════════════════════════════
# Plan-label parsing
# ═══════════════════════════════════════════════════════════

# Matches slugs produced by Phase-3 mirror:
#   "{firm}_{N}k_{type}"   where type ∈ {1step, 2step, instant, plan}
_PLAN_SLUG_RE = re.compile(
    r"^(?P<base>.+?)_(?P<size>\d+)k_(?P<type>1step|2step|instant|plan)$"
)
_TYPE_LABEL = {
    "1step": "1-Step",
    "2step": "2-Step",
    "instant": "Instant",
    "plan": "Plan",
}


def _titlecase_firm(base_slug: str) -> str:
    """Turn 'acme_prop' → 'Acme Prop'. Preserves known acronyms (FTMO)."""
    parts = base_slug.split("_")
    out: List[str] = []
    for p in parts:
        if not p:
            continue
        if p.isalpha() and len(p) <= 5 and p.islower() and p in {"ftmo", "fpfx", "myff"}:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out) or base_slug


def parse_firm_and_plan(firm_slug: str, firm_name: str, phase: str) -> Dict[str, str]:
    """
    Split a firm entry into user-facing firm + plan labels.

    • Phase-3 mirrored slugs ("ftmo_100k_2step") → firm="FTMO", plan="100K 2-Step".
    • Legacy / single-plan firms → firm=firm_name as-is, plan=phase (e.g. "Challenge").
    """
    m = _PLAN_SLUG_RE.match(firm_slug or "")
    if m:
        base = m.group("base")
        size = int(m.group("size"))
        ptype = _TYPE_LABEL.get(m.group("type"), "Plan")
        return {
            "firm": _titlecase_firm(base),
            "plan": f"{size}K {ptype}",
        }
    # Fallback — no size/type suffix
    clean_name = (firm_name or "").strip() or firm_slug or "Unknown"
    clean_plan = (phase or "").strip() or "Default"
    # Avoid duplicating the firm name inside the plan label
    if clean_plan.lower() == clean_name.lower():
        clean_plan = "Default"
    return {"firm": clean_name, "plan": clean_plan}


# ═══════════════════════════════════════════════════════════
# Ranking helpers
# ═══════════════════════════════════════════════════════════

def _normalize_ev(ev: float, fee: float) -> float:
    """
    Map EV into a 0–100 score relative to challenge fee.
      ratio ≤ −1  → 0
      ratio = 0   → 30
      ratio = +1  → 60
      ratio ≥ +5  → 100
    Mirrors the band used by the existing decision engine so the two stay
    directionally consistent.
    """
    if fee is None or fee <= 0:
        return 50.0
    ratio = ev / fee
    if ratio <= -1:
        return 0.0
    if ratio <= 0:
        return 30.0 * (1.0 + ratio)
    if ratio <= 5:
        return 30.0 + (ratio / 5.0) * 70.0
    return 100.0


def _stability_score(profile_summary: Dict[str, Any]) -> float:
    """
    Blend Sharpe (cap 4) and equity-curve smoothness (cap 100) into 0–100.
    Uses the same primitives the existing engine exposes.
    """
    sharpe = float(profile_summary.get("sharpe_ratio", 0) or 0)
    sharpe_pts = max(0.0, min(50.0, sharpe * 12.5))  # 4.0 → 50
    smoothness = float(profile_summary.get("equity_curve_smoothness", 0) or 0)
    smooth_pts = max(0.0, min(50.0, smoothness / 2.0))  # 100 → 50
    return round(sharpe_pts + smooth_pts, 1)


def _extract_overfit(validation_report: Optional[Dict[str, Any]]) -> float:
    """
    Pull overfit score (0-100, higher = more overfit) from a validation
    report. Looks for, in priority order:
      validation.overfit_score
      validation.report.overfit_score
      validation.combined.overfit_score
    Missing / malformed → 0 (treat as no penalty rather than max penalty,
    matching the existing pipeline's handling of absent validation).
    """
    if not isinstance(validation_report, dict):
        return 0.0
    for key in ("overfit_score", "overfit", "overfitScore"):
        v = validation_report.get(key)
        if isinstance(v, (int, float)):
            return max(0.0, min(100.0, float(v)))
    for container in ("report", "combined", "full", "validation"):
        nested = validation_report.get(container)
        if isinstance(nested, dict):
            pulled = _extract_overfit(nested)
            if pulled:
                return pulled
    return 0.0


def _verdict(
    pass_probability: float,
    safety_level: str,
    overfit: float,
    failure_reason: Optional[str],
) -> str:
    """Verdict per approved spec.

    "No violations" for SAFE is interpreted as the safety level being in
    the allowed band {safe, moderate} AND the challenge not having failed
    (no failure_reason). This keeps SAFE monotonic w.r.t. BEST: everything
    that qualifies as BEST also qualifies as SAFE by construction.
    """
    no_violations = (
        safety_level in SAFE_ALLOWED_SAFETY and failure_reason is None
    )

    if (
        pass_probability >= BEST_MIN_PROB
        and safety_level in SAFE_ALLOWED_SAFETY
        and overfit <= BEST_MAX_OVERFIT
    ):
        return "BEST"
    if pass_probability >= SAFE_MIN_PROB and no_violations:
        return "SAFE"
    return "RISKY"


def _risk_label(safety_level: str) -> str:
    return _RISK_MAP.get((safety_level or "").lower(), "HIGH")


# ═══════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════

async def match_strategy_phase4(
    trades: List[dict],
    initial_balance: float = 10000,
    validation_report: Optional[Dict[str, Any]] = None,
    n_simulations: int = 30,
) -> Dict[str, Any]:
    """
    Phase-4 wrapper — calls the existing matching engine with probability
    + EV enabled, then re-shapes results to the Phase-4 contract.

    Returns:
      {
        "ranked_matches": [ ...firm×plan records... ],     # sorted desc by final_score
        "rejected":       [ ...from prefilter... ],
        "profile_summary": {...},
        "firms_analyzed": int,
        "firms_compatible": int,
        "firms_rejected": int,
        "overfit_score": float,        # echoed for transparency
      }
    """
    # Run the existing (untouched) engine with probability + EV/safety/decision on.
    raw = await match_strategy_to_firms(
        trades=trades,
        initial_balance=initial_balance,
        include_probability=True,
        n_simulations=n_simulations,
    )

    if raw.get("error"):
        return {
            "ranked_matches": [],
            "rejected": [],
            "profile_summary": raw.get("profile_summary", {}),
            "firms_analyzed": 0,
            "firms_compatible": 0,
            "firms_rejected": 0,
            "overfit_score": 0.0,
            "error": raw["error"],
        }

    overfit = _extract_overfit(validation_report)
    overfit_penalty = W_OVERFIT_PENALTY * overfit
    profile_summary = raw.get("profile_summary", {}) or {}
    stability_pts = _stability_score(profile_summary)
    total_trades = len(trades or [])

    ranked: List[Dict[str, Any]] = []
    for m in raw.get("top_matches", []):
        firm_slug = m.get("firm_slug", "")
        firm_name = m.get("firm", "")
        phase = m.get("phase", "")

        probability_block = m.get("probability", {}) or {}
        pass_prob_raw = float(probability_block.get("pass_probability", 0) or 0)

        ev_block = m.get("expected_value", {}) or {}
        ev_dollars_raw = float(ev_block.get("expected_value", 0) or 0)
        fee = float(ev_block.get("challenge_fee", 0) or 0)
        reward = float(ev_block.get("potential_reward", 0) or 0)

        # ── Realism wiring (Phase 4 final step) ────────────────
        # Apply firm + challenge-type + reliability gates to the raw
        # Monte-Carlo probability, then recompute EV with the adjusted
        # probability so both feed the composite score consistently.
        realism = apply_realism(
            pass_prob_raw=pass_prob_raw,
            total_trades=total_trades,
            profile_summary=profile_summary,
            match=m,
            firm_slug=firm_slug,
            phase=phase,
        )
        pass_prob = float(realism["pass_probability"])
        ev_dollars = realistic_ev(pass_prob, fee, reward)
        ev_pts = _normalize_ev(ev_dollars, fee)
        # ───────────────────────────────────────────────────────

        safety_block = m.get("safety_margin", {}) or {}
        safety_level = (safety_block.get("risk_level") or "moderate").lower()
        safety_pts = float(safety_block.get("margin_score", 0) or 0)

        failure_reason = m.get("failure_reason")

        # Composite score with overfit subtracted
        final_score = (
            W_PASS_PROB * pass_prob
            + W_EV * ev_pts
            + W_SAFETY * safety_pts
            + W_STABILITY * stability_pts
            - overfit_penalty
        )
        final_score = round(max(0.0, min(100.0, final_score)), 1)

        verdict = _verdict(pass_prob, safety_level, overfit, failure_reason)
        risk = _risk_label(safety_level)
        labels = parse_firm_and_plan(firm_slug, firm_name, phase)

        ranked.append({
            "firm": labels["firm"],
            "plan": labels["plan"],
            "firm_slug": firm_slug,
            "score": final_score,
            "pass_probability": round(pass_prob, 1),
            "expected_value": round(ev_dollars, 2),
            "risk": risk,
            "verdict": verdict,
            # supporting transparency fields
            "status": m.get("status", ""),
            "safety_level": safety_level,
            "overfit_score": round(overfit, 1),
            # ── Realism layer outputs ──
            "realism_notes": realism.get("realism_notes", []),
            "challenge_type": realism.get("challenge_type"),
            "challenge_type_label": realism.get("challenge_type_label"),
            "firm_strictness": realism.get("firm_strictness"),
            "pass_probability_raw": realism.get("pass_probability_raw"),
            "expected_value_raw": round(ev_dollars_raw, 2),
            "dd_used_pct": realism.get("dd_used_pct"),
            "firm_dd_limit_pct": realism.get("firm_dd_limit_pct"),
            "score_components": {
                "pass_prob_pts": round(W_PASS_PROB * pass_prob, 2),
                "ev_pts": round(W_EV * ev_pts, 2),
                "safety_pts": round(W_SAFETY * safety_pts, 2),
                "stability_pts": round(W_STABILITY * stability_pts, 2),
                "overfit_penalty": round(overfit_penalty, 2),
            },
            "drawdown": {
                "max_drawdown_pct": m.get("max_drawdown_pct", 0),
                "max_daily_drawdown_pct": m.get("max_daily_drawdown_pct", 0),
                "dd_type": m.get("drawdown_type", "static"),
            },
            "ev_details": {
                "challenge_fee": fee,
                "potential_reward": ev_block.get("potential_reward"),
                "breakeven_probability": ev_block.get("breakeven_probability"),
                "grade": ev_block.get("ev_grade"),
            },
            "probability_details": {
                "confidence_interval": probability_block.get("confidence_interval"),
                "avg_days_to_pass": probability_block.get("avg_days_to_pass"),
                "risk_label": probability_block.get("risk_label"),
            },
            "flags": m.get("flags", []),
            "failure_reason": failure_reason,
        })

    # Highest composite score first
    ranked.sort(key=lambda r: r["score"], reverse=True)

    return {
        "ranked_matches": ranked,
        "rejected": raw.get("rejected", []),
        "profile_summary": profile_summary,
        "firms_analyzed": raw.get("firms_analyzed", 0),
        "firms_compatible": raw.get("firms_compatible", 0),
        "firms_rejected": raw.get("firms_rejected", 0),
        "overfit_score": round(overfit, 1),
        "weights": {
            "pass_probability": W_PASS_PROB,
            "expected_value": W_EV,
            "safety": W_SAFETY,
            "stability": W_STABILITY,
            "overfit_penalty": W_OVERFIT_PENALTY,
        },
    }

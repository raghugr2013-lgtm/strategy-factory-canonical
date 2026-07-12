"""
Expected Value + Safety Margin Engine (Phase 7, risk-adjusted).

Decision-quality metrics that answer: "Is this strategy worth taking
for a prop firm challenge?" Moves from "can it pass" to "is it worth it".

Components:
  - Expected Value: risk-adjusted formula (Phase 7 refinement):

        EV = (p_pass × reward × robustness_factor)
             − ((1 − p_pass) × fee × risk_penalty × low_prob_penalty)

      where
        robustness_factor ∈ {1.0, 0.8, 0.5}   from structural_robustness label
        risk_penalty      ∈ {1.0, 1.5, 2.0}   from strategy max drawdown
        low_prob_penalty  = 1.5 when pass_probability < 50% else 1.0

  - Safety Margin: DD buffer distances from firm limits
  - Decision Score: composite of probability + EV + safety
"""

import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════
# Default firm economics (override via parameters)
# ═══════════════════════════════════════════════════════

DEFAULT_ECONOMICS = {
    "ftmo": {
        "challenge_fee": 540,
        "funded_balance": 100000,
        "profit_split_pct": 80,
        "monthly_target_pct": 5.0,
        "expected_months": 6,
    },
    "fundednext": {
        "challenge_fee": 549,
        "funded_balance": 100000,
        "profit_split_pct": 80,
        "monthly_target_pct": 5.0,
        "expected_months": 6,
    },
    "pipfarm": {
        "challenge_fee": 500,
        "funded_balance": 100000,
        "profit_split_pct": 75,
        "monthly_target_pct": 5.0,
        "expected_months": 6,
    },
}


# ═══════════════════════════════════════════════════════
# Risk adjustment helpers (Phase 7 refinement)
# ═══════════════════════════════════════════════════════

ROBUSTNESS_FACTORS = {"robust": 1.0, "moderate": 0.8, "fragile": 0.5}
DEFAULT_ROBUSTNESS_FACTOR = 1.0

LOW_PROB_THRESHOLD_PCT = 50.0
LOW_PROB_PENALTY = 1.5


def _robustness_factor(score: float = None, label: str = None) -> float:
    """Map a structural_robustness (score or label) to a reward multiplier.

    Precedence: label > score. Missing → neutral 1.0 (no adjustment).
    """
    if label in ROBUSTNESS_FACTORS:
        return ROBUSTNESS_FACTORS[label]
    if score is None:
        return DEFAULT_ROBUSTNESS_FACTOR
    if score > 80:
        return ROBUSTNESS_FACTORS["robust"]
    if score >= 50:
        return ROBUSTNESS_FACTORS["moderate"]
    return ROBUSTNESS_FACTORS["fragile"]


def _risk_penalty(strategy_max_dd_pct: float = None) -> float:
    """Map strategy max drawdown (%) to a fail-side cost multiplier.

    <5% → 1.0 (low)      5–10% → 1.5 (medium)      ≥10% → 2.0 (high)

    Missing / non-positive → neutral 1.0 (no adjustment).
    """
    if strategy_max_dd_pct is None or strategy_max_dd_pct <= 0:
        return 1.0
    if strategy_max_dd_pct < 5.0:
        return 1.0
    if strategy_max_dd_pct < 10.0:
        return 1.5
    return 2.0


def _risk_band(strategy_max_dd_pct: float = None) -> str:
    if strategy_max_dd_pct is None or strategy_max_dd_pct <= 0:
        return "unknown"
    if strategy_max_dd_pct < 5.0:
        return "low"
    if strategy_max_dd_pct < 10.0:
        return "medium"
    return "high"


# ═══════════════════════════════════════════════════════
# Expected Value Calculation (risk-adjusted, Phase 7)
# ═══════════════════════════════════════════════════════

def calculate_expected_value(
    pass_probability: float,
    challenge_fee: float = 540,
    funded_balance: float = 100000,
    profit_split_pct: float = 80,
    monthly_target_pct: float = 5.0,
    expected_months: int = 6,
    firm_slug: str = None,
    structural_robustness_score: float = None,
    structural_robustness_label: str = None,
    strategy_max_dd_pct: float = None,
) -> dict:
    """
    Risk-adjusted expected monetary value of taking a prop firm challenge.

    Formula (Phase 7):
        EV = (p_pass × reward × robustness_factor)
             − ((1 − p_pass) × fee × risk_penalty × low_prob_penalty)

    Expected_Reward = funded_balance × monthly_target% × months × profit_split%

    Additional (optional) inputs:
        structural_robustness_score / label  — from pass_probability engine.
          → robust (>80) = 1.0,  moderate (50–80) = 0.8,  fragile (<50) = 0.5.
        strategy_max_dd_pct  — strategy's observed max drawdown.
          → low (<5%) = 1.0,  medium (5–10%) = 1.5,  high (≥10%) = 2.0.

    When probability < 50%, a further LOW_PROB_PENALTY (=1.5) is applied to
    the fail-side cost term — reflecting that low-survivability strategies
    carry extra downside that a linear model understates.

    Back-compat: when robustness and DD inputs are omitted, both multipliers
    default to 1.0 and the formula reduces to `p × reward − (1−p) × fee`
    plus the low-prob penalty (1.5× cost when p < 50%). Callers that want
    strictly legacy behaviour can also disable the low-prob penalty by
    passing `pass_probability >= 50`.
    """
    # Auto-load economics if firm_slug provided
    if firm_slug and firm_slug.lower() in DEFAULT_ECONOMICS:
        econ = DEFAULT_ECONOMICS[firm_slug.lower()]
        challenge_fee = challenge_fee or econ["challenge_fee"]
        funded_balance = funded_balance or econ["funded_balance"]
        profit_split_pct = profit_split_pct or econ["profit_split_pct"]
        monthly_target_pct = monthly_target_pct or econ["monthly_target_pct"]
        expected_months = expected_months or econ["expected_months"]

    p_pass = pass_probability / 100.0
    p_fail = 1.0 - p_pass

    # Expected reward from funded account
    monthly_profit = funded_balance * (monthly_target_pct / 100.0)
    total_profit = monthly_profit * expected_months
    trader_share = total_profit * (profit_split_pct / 100.0)

    # Phase 7 risk-adjustment multipliers
    robustness_factor = _robustness_factor(
        structural_robustness_score, structural_robustness_label
    )
    risk_penalty = _risk_penalty(strategy_max_dd_pct)
    low_prob_penalty = (
        LOW_PROB_PENALTY if pass_probability < LOW_PROB_THRESHOLD_PCT else 1.0
    )

    # Risk-adjusted Expected Value
    reward_side = p_pass * trader_share * robustness_factor
    cost_side = p_fail * challenge_fee * risk_penalty * low_prob_penalty
    ev = reward_side - cost_side

    # Risk-Reward ratio: potential reward / risk (fee)
    rr_ratio = trader_share / challenge_fee if challenge_fee > 0 else 0

    # Breakeven probability — solve the full Phase-7 formula for p=pass_prob/100
    # where EV = 0. For p >= 0.5 the low_prob_penalty is 1.0; below 0.5 it is 1.5.
    # Standard formula (p ≥ 0.5 regime, no low-prob penalty):
    denom = trader_share * robustness_factor + challenge_fee * risk_penalty
    breakeven_prob = (
        (challenge_fee * risk_penalty) / denom * 100
        if denom > 0
        else 100
    )

    # ROI if pass
    roi_if_pass = (
        ((trader_share - challenge_fee) / challenge_fee) * 100
        if challenge_fee > 0
        else 0
    )

    # EV classification
    if ev > challenge_fee * 2:
        ev_grade = "excellent"
    elif ev > challenge_fee:
        ev_grade = "good"
    elif ev > 0:
        ev_grade = "marginal"
    else:
        ev_grade = "negative"

    return {
        "expected_value": round(ev, 2),
        "ev_grade": ev_grade,
        "risk_reward_ratio": round(rr_ratio, 2),
        "breakeven_probability": round(breakeven_prob, 1),
        "pass_probability": round(pass_probability, 1),
        "challenge_fee": challenge_fee,
        "potential_reward": round(trader_share, 2),
        "roi_if_pass": round(roi_if_pass, 1),
        "risk_adjustment": {
            "robustness_factor": robustness_factor,
            "robustness_label": structural_robustness_label,
            "robustness_score": structural_robustness_score,
            "risk_penalty": risk_penalty,
            "risk_band": _risk_band(strategy_max_dd_pct),
            "strategy_max_dd_pct": strategy_max_dd_pct,
            "low_prob_penalty": low_prob_penalty,
            "low_prob_threshold_pct": LOW_PROB_THRESHOLD_PCT,
        },
        "economics": {
            "funded_balance": funded_balance,
            "profit_split_pct": profit_split_pct,
            "monthly_target_pct": monthly_target_pct,
            "expected_months": expected_months,
            "monthly_profit": round(monthly_profit, 2),
            "total_profit_before_split": round(total_profit, 2),
        },
    }


# ═══════════════════════════════════════════════════════
# Safety Margin Calculation
# ═══════════════════════════════════════════════════════

def calculate_safety_margin(
    strategy_max_dd_pct: float,
    strategy_daily_dd_pct: float,
    firm_total_dd_limit: float,
    firm_daily_dd_limit: float,
    strategy_dd_p90: float = 0,
    drawdown_type: str = "static",
) -> dict:
    """
    Calculate safety margins between strategy drawdowns and firm limits.

    Returns:
        dict with daily_dd_buffer, total_dd_buffer, risk_level, margin_score.
    """
    total_dd_buffer = firm_total_dd_limit - strategy_max_dd_pct
    daily_dd_buffer = firm_daily_dd_limit - strategy_daily_dd_pct

    # Also check p90 daily DD
    daily_dd_p90_buffer = firm_daily_dd_limit - strategy_dd_p90 if strategy_dd_p90 > 0 else daily_dd_buffer

    # Risk level based on tightest margin
    min_buffer = min(total_dd_buffer, daily_dd_buffer)

    if min_buffer < 0:
        risk_level = "breached"
    elif min_buffer < 1.0:
        risk_level = "danger"
    elif min_buffer < 3.0:
        risk_level = "moderate"
    else:
        risk_level = "safe"

    # Margin score 0-100: how much room is left
    total_margin_score = max(0, min(100, (total_dd_buffer / max(firm_total_dd_limit, 1)) * 100))
    daily_margin_score = max(0, min(100, (daily_dd_buffer / max(firm_daily_dd_limit, 1)) * 100))
    margin_score = round((total_margin_score + daily_margin_score) / 2, 1)

    # Trailing DD is harder — penalize margin score
    if drawdown_type == "trailing":
        margin_score = round(margin_score * 0.85, 1)

    return {
        "total_dd_buffer": round(total_dd_buffer, 2),
        "daily_dd_buffer": round(daily_dd_buffer, 2),
        "daily_dd_p90_buffer": round(daily_dd_p90_buffer, 2),
        "risk_level": risk_level,
        "margin_score": margin_score,
        "drawdown_type": drawdown_type,
        "strategy_max_dd_pct": round(strategy_max_dd_pct, 2),
        "strategy_daily_dd_pct": round(strategy_daily_dd_pct, 2),
        "firm_total_dd_limit": firm_total_dd_limit,
        "firm_daily_dd_limit": firm_daily_dd_limit,
    }


# ═══════════════════════════════════════════════════════
# Decision Score: composite of probability + EV + safety
# ═══════════════════════════════════════════════════════

def calculate_decision_score(
    pass_probability: float,
    ev_data: dict,
    safety_data: dict,
) -> dict:
    """
    Composite decision score 0-100 combining:
      - Pass probability: 35% weight
      - Expected value:   35% weight
      - Safety margin:    30% weight

    Returns dict with score, grade, recommendation.
    """
    # Probability component (0-100, direct mapping)
    prob_score = min(100, max(0, pass_probability))

    # EV component: normalize EV relative to challenge fee
    ev = ev_data.get("expected_value", 0)
    fee = ev_data.get("challenge_fee", 540)
    if fee > 0:
        ev_ratio = ev / fee
        # Map: -1 → 0, 0 → 30, +1 → 60, +5 → 100
        if ev_ratio <= -1:
            ev_score = 0
        elif ev_ratio <= 0:
            ev_score = 30 * (1 + ev_ratio)
        elif ev_ratio <= 5:
            ev_score = 30 + (ev_ratio / 5) * 70
        else:
            ev_score = 100
    else:
        ev_score = 50

    # Safety component (margin_score is already 0-100)
    safety_score = safety_data.get("margin_score", 0)

    # Composite
    decision_score = round(
        prob_score * 0.35 +
        ev_score * 0.35 +
        safety_score * 0.30,
        1,
    )

    # Grade
    if decision_score >= 75:
        grade = "A"
        recommendation = "strong_go"
    elif decision_score >= 55:
        grade = "B"
        recommendation = "go"
    elif decision_score >= 35:
        grade = "C"
        recommendation = "caution"
    elif decision_score >= 20:
        grade = "D"
        recommendation = "avoid"
    else:
        grade = "F"
        recommendation = "reject"

    return {
        "decision_score": decision_score,
        "grade": grade,
        "recommendation": recommendation,
        "components": {
            "probability_score": round(prob_score, 1),
            "probability_weight": 0.35,
            "ev_score": round(ev_score, 1),
            "ev_weight": 0.35,
            "safety_score": round(safety_score, 1),
            "safety_weight": 0.30,
        },
    }


# ═══════════════════════════════════════════════════════
# Integration: enrich a matching result with EV + safety + decision
# ═══════════════════════════════════════════════════════

def enrich_match_with_decision(
    match_data: dict,
    firm_rules: dict,
    challenge_fee: float = None,
    funded_balance: float = None,
    profit_split_pct: float = None,
    monthly_target_pct: float = None,
    expected_months: int = None,
) -> dict:
    """
    Take a single firm match result (from matching engine) and add
    EV + safety margin + decision score.

    Args:
        match_data: dict from matching engine with probability, drawdown data
        firm_rules: the firm's rule document from DB
    """
    firm_slug = match_data.get("firm_slug", "")
    prob_block = match_data.get("probability", {}) or {}
    prob = prob_block.get("pass_probability", 0)
    strategy_max_dd = match_data.get("max_drawdown_pct", 0)
    strategy_daily_dd = match_data.get("max_daily_drawdown_pct", 0)

    # Phase 7 risk inputs (robustness + DD) — all optional; silently ignored
    # when absent so older callers keep working.
    robustness = prob_block.get("structural_robustness") or {}
    robustness_score = robustness.get("score")
    robustness_label = robustness.get("label")

    rules = firm_rules.get("rules", {})
    total_dd_limit = rules.get("total_dd", {}).get("max_pct", 10)
    daily_dd_limit = rules.get("daily_dd", {}).get("max_pct", 5)
    dd_type = rules.get("total_dd", {}).get("type", "static")

    # Economics: use provided or defaults
    econ = DEFAULT_ECONOMICS.get(firm_slug, {})
    fee = challenge_fee or econ.get("challenge_fee", 540)
    bal = funded_balance or firm_rules.get("initial_balance", 100000)
    split = profit_split_pct or econ.get("profit_split_pct", 80)
    monthly = monthly_target_pct or econ.get("monthly_target_pct", 5.0)
    months = expected_months or econ.get("expected_months", 6)

    # Calculate EV (Phase 7 — risk-adjusted)
    ev_data = calculate_expected_value(
        prob, fee, bal, split, monthly, months, firm_slug,
        structural_robustness_score=robustness_score,
        structural_robustness_label=robustness_label,
        strategy_max_dd_pct=strategy_max_dd,
    )

    # Calculate safety margin
    safety_data = calculate_safety_margin(
        strategy_max_dd, strategy_daily_dd,
        total_dd_limit, daily_dd_limit,
        drawdown_type=dd_type,
    )

    # Calculate decision score
    decision_data = calculate_decision_score(prob, ev_data, safety_data)

    return {
        "expected_value": ev_data,
        "safety_margin": safety_data,
        "decision": decision_data,
    }

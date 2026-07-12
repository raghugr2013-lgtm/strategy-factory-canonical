"""
Strategy ↔ Prop Firm Matching Engine (Phase 4).

Matches each strategy with the most suitable prop firm challenges by:
  1. Profiling the strategy (DNA from Phase 3)
  2. Pre-filtering firms based on DNA compatibility
  3. Running challenge simulation for compatible firms (Phase 1)
  4. Scoring each match (pass status, DD buffer, profit efficiency)
  5. Ranking and returning top matches + rejected firms

Does NOT include Monte Carlo / probability — that's a future phase.
"""

import logging
from engines.strategy_profiler import profile_strategy
from engines.challenge_simulator import simulate_challenge
from engines.rule_engine import get_all_rules, rules_to_sim_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Pre-Filtering: DNA vs Firm Rules
# ═══════════════════════════════════════════════════════

def _prefilter(profile: dict, firm_doc: dict) -> dict:
    """
    Check strategy DNA against firm rules. Returns a dict with:
      compatible (bool), flags (list of warning strings), reject_reason (str or None).
    A firm is rejected only for hard incompatibilities.
    Flags are soft warnings that don't block but reduce the score.
    """
    flags = []
    reject_reason = None

    classification = profile.get("classification", {})
    risk = profile.get("risk", {})
    behavior = profile.get("behavior", {})
    stability = profile.get("stability", {})
    consistency = profile.get("consistency", {})

    rules = firm_doc.get("rules", {})
    daily_dd = rules.get("daily_dd", {})
    total_dd = rules.get("total_dd", {})
    consistency_rule = rules.get("consistency", {})
    restrictions = rules.get("restrictions", {})

    risk_level = classification.get("risk_level", "medium")
    max_dd_pct = risk.get("max_drawdown_pct", 0)
    daily_dd_p90 = risk.get("daily_dd_distribution", {}).get("p90", 0)
    tpd = behavior.get("trades_per_day", 0)
    total_return = stability.get("total_return_pct", 0)
    profit_factor = stability.get("profit_factor", 0)
    top_day_pct = consistency.get("profit_distribution", {}).get("top_day_pct", 0)

    firm_daily_limit = daily_dd.get("max_pct", 100) if daily_dd.get("enabled") else 100
    firm_total_limit = total_dd.get("max_pct", 100) if total_dd.get("enabled") else 100
    firm_dd_type = total_dd.get("type", "static")

    # ── Hard reject: strategy's historical max DD already exceeds firm's total DD limit ──
    if max_dd_pct > firm_total_limit * 1.5:
        reject_reason = f"max_drawdown_too_high: strategy max DD {max_dd_pct}% exceeds {firm_total_limit * 1.5}% (1.5x firm limit {firm_total_limit}%)"
        return {"compatible": False, "flags": flags, "reject_reason": reject_reason}

    # ── Hard reject: strategy is net negative with poor profit factor ──
    if total_return < 0 and profit_factor < 0.5:
        reject_reason = f"unprofitable_strategy: return {total_return}%, PF {profit_factor}"
        return {"compatible": False, "flags": flags, "reject_reason": reject_reason}

    # ── Soft flags ──
    # DD pressure
    if max_dd_pct > firm_total_limit * 0.8:
        flags.append(f"dd_pressure: max DD {max_dd_pct}% is close to firm limit {firm_total_limit}%")

    if daily_dd_p90 > firm_daily_limit * 0.6:
        flags.append(f"daily_dd_pressure: p90 daily DD {daily_dd_p90}% vs firm limit {firm_daily_limit}%")

    # Trailing DD is harder for volatile strategies
    if firm_dd_type == "trailing" and risk_level == "high":
        flags.append("trailing_dd_risk: high-risk strategy with trailing drawdown firm is challenging")

    # Consistency rule compatibility
    if consistency_rule.get("enabled"):
        max_daily_profit = consistency_rule.get("max_daily_profit_pct")
        if max_daily_profit and top_day_pct > max_daily_profit:
            flags.append(f"consistency_risk: top day has {top_day_pct}% of total profit, firm limit is {max_daily_profit}%")

    # Restriction flags
    if restrictions:
        if restrictions.get("news_blackout_minutes") and tpd > 5:
            flags.append("news_restriction: high-frequency strategy may be affected by news blackout rules")
        if not restrictions.get("weekend_hold_allowed", True) and classification.get("type") == "swing":
            flags.append("weekend_restriction: swing strategy cannot hold over weekends at this firm")

    # Profitability concern
    if total_return < 5:
        flags.append(f"low_profitability: strategy return {total_return}% may not reach profit target easily")

    return {"compatible": True, "flags": flags, "reject_reason": None}


# ═══════════════════════════════════════════════════════
# Scoring: post-simulation evaluation
# ═══════════════════════════════════════════════════════

def _score_match(sim_result: dict, firm_doc: dict, profile: dict, flags: list) -> dict:
    """
    Compute match score from simulation result + DNA.
    Components:
      - pass_status:        50 points if pass, 0 if fail
      - drawdown_buffer:    0-25 points (how far from DD limits)
      - profit_efficiency:  0-15 points (speed to reach target)
      - stability_bonus:    0-10 points (Sharpe + smoothness from DNA)
    Total: 0-100.
    Flags reduce score by 2 each.
    """
    status = sim_result.get("status", "fail")
    max_dd = sim_result.get("max_drawdown_pct", 0)
    max_daily_dd = sim_result.get("max_daily_drawdown_pct", 0)
    days_taken = sim_result.get("days_taken", 999)
    profit_pct = sim_result.get("profit_pct", 0)
    target_pct = sim_result.get("profit_target_pct", 10)

    rules = firm_doc.get("rules", {})
    total_dd_limit = rules.get("total_dd", {}).get("max_pct", 100)
    daily_dd_limit = rules.get("daily_dd", {}).get("max_pct", 100)
    time_limit = rules.get("time_limit", {}).get("calendar_days", 0)

    # ── Pass status: 50 points ──
    pass_score = 50 if status == "pass" else 0

    # ── Drawdown buffer: 0-25 points ──
    # How much room is left before hitting DD limits
    total_dd_buffer = max(0, total_dd_limit - max_dd)
    daily_dd_buffer = max(0, daily_dd_limit - max_daily_dd)
    # Normalize: full marks if >50% of limit unused
    total_dd_score = min(25, (total_dd_buffer / max(total_dd_limit, 1)) * 25 * 2)
    daily_dd_score = min(25, (daily_dd_buffer / max(daily_dd_limit, 1)) * 25 * 2)
    dd_buffer_score = round((total_dd_score + daily_dd_score) / 2, 1)

    # ── Profit efficiency: 0-15 points ──
    # How quickly the target is reached
    if status == "pass" and days_taken > 0:
        if time_limit > 0:
            speed_ratio = 1 - (days_taken / time_limit)
        else:
            speed_ratio = max(0, 1 - days_taken / 30)  # benchmark: 30 days
        efficiency_score = round(max(0, min(15, speed_ratio * 15)), 1)
    elif profit_pct > 0:
        efficiency_score = round(min(10, (profit_pct / max(target_pct, 1)) * 10), 1)
    else:
        efficiency_score = 0

    # ── Stability bonus: 0-10 points ──
    stability = profile.get("stability", {})
    sharpe = stability.get("sharpe_ratio", 0)
    smoothness = stability.get("equity_curve_smoothness", 0)
    sharpe_pts = min(5, max(0, sharpe) * 2.5)
    smooth_pts = min(5, smoothness / 20)
    stability_score = round(sharpe_pts + smooth_pts, 1)

    # ── Flag penalty ──
    flag_penalty = len(flags) * 2

    total_score = round(max(0, min(100,
        pass_score + dd_buffer_score + efficiency_score + stability_score - flag_penalty
    )), 1)

    return {
        "score": total_score,
        "components": {
            "pass_status": pass_score,
            "drawdown_buffer": dd_buffer_score,
            "profit_efficiency": efficiency_score,
            "stability_bonus": stability_score,
            "flag_penalty": flag_penalty,
        },
        "drawdown_buffer_pct": {
            "total_dd": round(total_dd_buffer, 2),
            "daily_dd": round(daily_dd_buffer, 2),
        },
    }


# ═══════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════

async def match_strategy_to_firms(
    trades: list,
    initial_balance: float = 10000,
    profile: dict = None,
    include_probability: bool = False,
    n_simulations: int = 30,
) -> dict:
    """
    Match a strategy against all available prop firms.

    1. Profile the strategy (or use provided profile)
    2. Load all firm rules from DB
    3. Pre-filter firms based on DNA compatibility
    4. Simulate challenge for each compatible firm
    5. Score and rank matches
    6. Optionally run Monte Carlo probability estimation

    Returns dict with top_matches, rejected, profile summary.
    """
    from engines.pass_probability import estimate_pass_probability

    # ── Step 1: Profile ──
    if not profile:
        profile = profile_strategy(trades, initial_balance)

    if not trades:
        return {
            "top_matches": [],
            "rejected": [],
            "profile": profile,
            "error": "No trades provided",
        }

    # ── Step 2: Load all firm rules ──
    all_firms = await get_all_rules()
    if not all_firms:
        return {
            "top_matches": [],
            "rejected": [],
            "profile": profile,
            "error": "No firm rules found in database",
        }

    top_matches = []
    rejected = []

    for firm_doc in all_firms:
        slug = firm_doc.get("firm_slug", "")
        name = firm_doc.get("firm_name", slug)
        phase = firm_doc.get("phase", "")

        # ── Step 3: Pre-filter ──
        filter_result = _prefilter(profile, firm_doc)

        if not filter_result["compatible"]:
            rejected.append({
                "firm": name,
                "firm_slug": slug,
                "phase": phase,
                "reason": filter_result["reject_reason"],
            })
            continue

        flags = filter_result["flags"]

        # ── Step 4: Simulate ──
        sim_config = await rules_to_sim_config(firm_doc)
        sim_result = simulate_challenge(trades, sim_config)

        # ── Step 5: Score ──
        scoring = _score_match(sim_result, firm_doc, profile, flags)

        match_entry = {
            "firm": name,
            "firm_slug": slug,
            "phase": phase,
            "status": sim_result.get("status", "fail"),
            "score": scoring["score"],
            "score_breakdown": scoring["components"],
            "drawdown_buffer": scoring["drawdown_buffer_pct"],
            "days_taken": sim_result.get("days_taken", 0),
            "trading_days": sim_result.get("trading_days", 0),
            "profit_pct": sim_result.get("profit_pct", 0),
            "profit_target_pct": sim_result.get("profit_target_pct", 0),
            "max_drawdown_pct": sim_result.get("max_drawdown_pct", 0),
            "max_daily_drawdown_pct": sim_result.get("max_daily_drawdown_pct", 0),
            "failure_reason": sim_result.get("failure_reason"),
            "flags": flags,
            "drawdown_type": firm_doc.get("rules", {}).get("total_dd", {}).get("type", "static"),
        }

        # ── Step 6: Monte Carlo probability (optional) ──
        if include_probability:
            prob_result = estimate_pass_probability(
                trades, sim_config, n_simulations=n_simulations
            )
            match_entry["probability"] = {
                "pass_probability": prob_result["pass_probability"],
                "confidence_interval": prob_result["confidence_interval"],
                "risk_label": prob_result["risk_label"],
                "avg_days_to_pass": prob_result["avg_days_to_pass"],
                "failure_breakdown": prob_result["failure_breakdown"],
                "structural_robustness": prob_result.get("structural_robustness"),
            }

            # ── Step 7: EV + Safety + Decision (when probability is available) ──
            from engines.expected_value import enrich_match_with_decision
            decision_data = enrich_match_with_decision(
                match_entry, firm_doc,
            )
            match_entry["expected_value"] = decision_data["expected_value"]
            match_entry["safety_margin"] = decision_data["safety_margin"]
            match_entry["decision"] = decision_data["decision"]

        top_matches.append(match_entry)

    # ── Sort by score descending ──
    top_matches.sort(key=lambda x: x["score"], reverse=True)

    # ── Build profile summary for response ──
    classification = profile.get("classification", {})
    profile_summary = {
        "type": classification.get("type", "unknown"),
        "risk_level": classification.get("risk_level", "unknown"),
        "consistency_level": classification.get("consistency_level", "unknown"),
        "speed": classification.get("speed", "unknown"),
        "tags": classification.get("tags", []),
        "sharpe_ratio": profile.get("stability", {}).get("sharpe_ratio", 0),
        "win_rate": profile.get("behavior", {}).get("win_rate", 0),
        "max_drawdown_pct": profile.get("risk", {}).get("max_drawdown_pct", 0),
        "total_return_pct": profile.get("stability", {}).get("total_return_pct", 0),
        "trades_per_day": profile.get("behavior", {}).get("trades_per_day", 0),
    }

    return {
        "top_matches": top_matches,
        "rejected": rejected,
        "profile_summary": profile_summary,
        "firms_analyzed": len(all_firms),
        "firms_compatible": len(top_matches),
        "firms_rejected": len(rejected),
    }

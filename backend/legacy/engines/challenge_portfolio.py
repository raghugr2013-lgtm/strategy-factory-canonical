"""
Challenge Portfolio Engine (Phase 8) — Capital allocation across prop-firm challenges.

Given a list of strategy-firm matches already enriched with Phase 7 EV
and a capital budget, select the subset that maximizes total risk-adjusted
expected value subject to:

    sum(challenge_fee) <= budget
    len(selected)      <= max_challenges   (optional)

Algorithm: greedy by EV-to-cost ratio (`ev / fee`). Simple, interpretable,
produces an optimal 0/1 knapsack solution when no single item violates
the budget by itself and costs are not wildly heterogeneous. Clearly
marked as a heuristic — Phase 8 is intentionally minimal.

No other engines are modified. No DB, no network.
"""

from __future__ import annotations

from typing import Optional
import math


# ═══════════════════════════════════════════════════════════════════════
# Candidate extraction
# ═══════════════════════════════════════════════════════════════════════
def _extract_candidate(match: dict) -> Optional[dict]:
    """
    Pull the minimal fields we need out of a matching_engine entry.

    Returns a normalized candidate dict, or None if the match is missing
    a firm slug or a usable cost (cannot participate in capital budgeting).
    """
    firm_slug = match.get("firm_slug") or match.get("firm") or match.get("firm_name")
    if not firm_slug:
        return None

    prob_block = match.get("probability") or {}
    ev_block = match.get("expected_value") or {}

    ev = ev_block.get("expected_value")
    if ev is None:
        return None

    fee = ev_block.get("challenge_fee")
    if fee is None or fee <= 0:
        return None

    pass_probability = prob_block.get("pass_probability") or match.get("pass_probability") or 0.0

    robustness = prob_block.get("structural_robustness") or {}

    return {
        "firm_slug": firm_slug,
        "firm_name": match.get("firm_name") or firm_slug,
        "strategy_id": match.get("strategy_id"),
        "pass_probability": float(pass_probability),
        "expected_value": float(ev),
        "challenge_fee": float(fee),
        "ev_per_dollar": float(ev) / float(fee),
        "robustness_label": robustness.get("label"),
        "robustness_score": robustness.get("score"),
        "ev_grade": ev_block.get("ev_grade"),
        "max_drawdown_pct": match.get("max_drawdown_pct"),
        "risk_band": (ev_block.get("risk_adjustment") or {}).get("risk_band"),
    }


# ═══════════════════════════════════════════════════════════════════════
# Greedy selection
# ═══════════════════════════════════════════════════════════════════════
def _greedy_select(
    candidates: list,
    budget: float,
    max_challenges: Optional[int],
) -> list:
    """
    Sort by (ev_per_dollar desc, expected_value desc) then pick while both
    the remaining-budget and max_challenges constraints allow.

    Candidates with ev <= 0 are skipped — we never spend capital on
    negative-EV challenges even if there's budget to spare.
    """
    ranked = sorted(
        (c for c in candidates if c["expected_value"] > 0),
        key=lambda c: (c["ev_per_dollar"], c["expected_value"]),
        reverse=True,
    )

    selected = []
    remaining = float(budget)
    cap = max_challenges if max_challenges is not None else math.inf

    for cand in ranked:
        if len(selected) >= cap:
            break
        if cand["challenge_fee"] <= remaining + 1e-9:
            selected.append(cand)
            remaining -= cand["challenge_fee"]

    return selected


# ═══════════════════════════════════════════════════════════════════════
# Risk summary
# ═══════════════════════════════════════════════════════════════════════
def _risk_summary(selected: list) -> dict:
    if not selected:
        return {
            "avg_pass_probability": 0.0,
            "avg_ev_per_dollar": 0.0,
            "robustness_breakdown": {},
            "risk_band_breakdown": {},
            "negative_ev_count": 0,
        }

    n = len(selected)
    avg_prob = sum(c["pass_probability"] for c in selected) / n
    avg_ratio = sum(c["ev_per_dollar"] for c in selected) / n

    rob_counts: dict[str, int] = {}
    band_counts: dict[str, int] = {}
    for c in selected:
        rob = c.get("robustness_label") or "unknown"
        band = c.get("risk_band") or "unknown"
        rob_counts[rob] = rob_counts.get(rob, 0) + 1
        band_counts[band] = band_counts.get(band, 0) + 1

    return {
        "avg_pass_probability": round(avg_prob, 1),
        "avg_ev_per_dollar": round(avg_ratio, 2),
        "robustness_breakdown": rob_counts,
        "risk_band_breakdown": band_counts,
        "negative_ev_count": 0,  # selection stage filters these out
    }


# ═══════════════════════════════════════════════════════════════════════
# Public entry point
# ═══════════════════════════════════════════════════════════════════════
def build_challenge_portfolio(
    matches: list,
    budget: float,
    max_challenges: Optional[int] = None,
) -> dict:
    """
    Select a subset of challenges that maximizes aggregate EV within budget.

    Args:
        matches: list of matching-engine entries that already include a
                 Phase-7 `expected_value` block (see enrich_match_with_decision).
                 Entries missing firm_slug, fee, or EV are skipped.
        budget: maximum total challenge_fee across the selected set.
        max_challenges: optional cap on how many challenges can be selected.

    Returns:
        {
          "selected":       [candidate, ...],      # in selection order
          "skipped":        [candidate, ...],      # considered but not picked
          "total_ev":       float,                 # sum of EV of selected
          "total_cost":     float,                 # sum of fees of selected
          "budget":         float,
          "remaining_budget": float,
          "max_challenges": int | None,
          "n_selected":     int,
          "n_considered":   int,
          "risk_summary":   {...},
          "algorithm":      "greedy_ev_per_dollar",
        }
    """
    if budget is None or budget < 0:
        raise ValueError("budget must be non-negative")
    if max_challenges is not None and max_challenges < 0:
        raise ValueError("max_challenges must be non-negative")

    candidates = [c for c in (_extract_candidate(m) for m in matches) if c is not None]

    selected = _greedy_select(candidates, budget, max_challenges)
    selected_ids = {id(c) for c in selected}
    skipped = [c for c in candidates if id(c) not in selected_ids]

    total_ev = round(sum(c["expected_value"] for c in selected), 2)
    total_cost = round(sum(c["challenge_fee"] for c in selected), 2)
    remaining = round(float(budget) - total_cost, 2)

    return {
        "selected": selected,
        "skipped": skipped,
        "total_ev": total_ev,
        "total_cost": total_cost,
        "budget": float(budget),
        "remaining_budget": remaining,
        "max_challenges": max_challenges,
        "n_selected": len(selected),
        "n_considered": len(candidates),
        "risk_summary": _risk_summary(selected),
        "algorithm": "greedy_ev_per_dollar",
    }

"""
Phase 8.6 — Strategy Ranking Engine.

Takes a list of strategy dicts (each carrying decision / validation_report /
expected_value / pass_probability) and returns them ranked by a single,
explainable composite score.

Input tolerance: every field is optional. A strategy with nothing known
gets a neutral score of 50 and a RISKY assumption. Missing `decision` is
treated as RISKY.

Formula (0-100, higher = better):

    score = 0.35 * verdict_factor          # TRADE=100, RISKY=50, REJECT=0
          + 0.25 * stability_score          # from validation_report (0-100)
          + 0.20 * pass_probability         # 0-100
          + 0.20 * ev_score                 # EV normalized to 0-100
          - 0.40 * overfit_penalty          # overfit 0-100 subtracted with weight

Then clamped to [0, 100].

REJECT strategies are excluded from the returned ranking by default.

Output:
  [
    { "rank": 1,
      "strategy_id": "...",
      "score": 78.4,
      "verdict": "TRADE",
      "reason": "short explanation",
      "breakdown": { verdict: 35.0, stability: 18.7, ev: 15.6,
                     probability: 13.5, overfit_penalty: -7.2 } },
    ...
  ]
"""
from __future__ import annotations


# ── Tunables ──────────────────────────────────────────────────────────
TOP_N_DEFAULT = 5
VERDICT_FACTOR = {"TRADE": 100.0, "RISKY": 50.0, "REJECT": 0.0}


# ── Extractors (tolerant to multiple input shapes) ────────────────────

def _get_id(s: dict) -> str:
    for k in ("strategy_id", "id", "combo_key", "name"):
        v = s.get(k)
        if v:
            return str(v)
    return "unknown"


def _get_verdict(s: dict) -> str:
    dec = s.get("decision")
    if isinstance(dec, dict):
        inner = dec.get("decision") if isinstance(dec.get("decision"), dict) else dec
        v = inner.get("verdict") if isinstance(inner, dict) else None
        if v in VERDICT_FACTOR:
            return v
    if isinstance(dec, str) and dec in VERDICT_FACTOR:
        return dec
    return "RISKY"


def _get_stability(s: dict) -> float | None:
    """Prefer explicit scalar, then validation_report."""
    if isinstance(s.get("stability_score"), (int, float)):
        return float(s["stability_score"])
    vr = s.get("validation_report")
    if isinstance(vr, dict):
        st = vr.get("stability_score")
        if isinstance(st, dict) and isinstance(st.get("score"), (int, float)):
            return float(st["score"])
        if isinstance(st, (int, float)):
            return float(st)
        basic = vr.get("basic") or {}
        if basic.get("stability") and isinstance(basic["stability"].get("score"), (int, float)):
            return float(basic["stability"]["score"])
    return None


def _get_overfit(s: dict) -> float | None:
    if isinstance(s.get("overfit_score"), (int, float)):
        return float(s["overfit_score"])
    vr = s.get("validation_report")
    if isinstance(vr, dict):
        ov = vr.get("overfit_score")
        if isinstance(ov, dict) and isinstance(ov.get("score"), (int, float)):
            return float(ov["score"])
        if isinstance(ov, (int, float)):
            return float(ov)
    return None


def _get_ev_usd(s: dict) -> float | None:
    ev = s.get("expected_value")
    if isinstance(ev, dict):
        for k in ("expected_value", "ev"):
            if isinstance(ev.get(k), (int, float)):
                return float(ev[k])
    if isinstance(ev, (int, float)):
        return float(ev)
    return None


def _get_pass_prob(s: dict) -> float | None:
    pp = s.get("pass_probability")
    if isinstance(pp, (int, float)):
        return float(pp)
    if isinstance(pp, dict):
        if isinstance(pp.get("pass_probability"), (int, float)):
            return float(pp["pass_probability"])
        inner = pp.get("probability")
        if isinstance(inner, dict) and isinstance(inner.get("pass_probability"), (int, float)):
            return float(inner["pass_probability"])
    return None


def _ev_to_score(ev_usd: float | None) -> float:
    """0 EV → 50 pts. +$750 → 100. -$750 → 0."""
    if ev_usd is None:
        return 50.0
    return max(0.0, min(100.0, 50.0 + ev_usd / 15.0))


# ── Core scorer ───────────────────────────────────────────────────────

def _score_strategy(s: dict) -> dict:
    verdict = _get_verdict(s)
    stability = _get_stability(s)
    overfit = _get_overfit(s)
    ev_usd = _get_ev_usd(s)
    pass_prob = _get_pass_prob(s)

    v_pts = VERDICT_FACTOR[verdict] * 0.35
    stab_pts = (50.0 if stability is None else stability) * 0.25
    prob_pts = (50.0 if pass_prob is None else pass_prob) * 0.20
    ev_pts = _ev_to_score(ev_usd) * 0.20
    overfit_pen = (0.0 if overfit is None else overfit) * 0.40

    raw = v_pts + stab_pts + prob_pts + ev_pts - overfit_pen
    score = round(max(0.0, min(100.0, raw)), 1)

    # Short reason
    bits = [f"verdict={verdict}"]
    if stability is not None:
        bits.append(f"stability {stability:.0f}")
    if overfit is not None:
        bits.append(f"overfit {overfit:.0f}")
    if ev_usd is not None:
        bits.append(f"EV ${ev_usd:.0f}")
    if pass_prob is not None:
        bits.append(f"prob {pass_prob:.0f}%")
    reason = ", ".join(bits)

    return {
        "strategy_id": _get_id(s),
        "score": score,
        "verdict": verdict,
        "reason": reason,
        "breakdown": {
            "verdict": round(v_pts, 1),
            "stability": round(stab_pts, 1),
            "probability": round(prob_pts, 1),
            "ev": round(ev_pts, 1),
            "overfit_penalty": round(-overfit_pen, 1),
        },
    }


# ── Public API ────────────────────────────────────────────────────────

def rank_strategies(
    strategies: list,
    top_n: int = TOP_N_DEFAULT,
    include_rejects: bool = False,
    attach_panel: bool = True,
) -> list:
    """
    Rank strategies by composite score, descending.

    Args:
        strategies: list of strategy dicts (see module docstring for shape).
        top_n:      keep only the top N (default 5). Use 0 or None for all.
        include_rejects: if True, REJECT verdicts are kept in the result.
                         Default False — REJECTs are always excluded.
        attach_panel: if True (default), attach a Prop Firm Intelligence
                         Panel to each ranked entry when the source strategy
                         carries a `simulation` / `validation_report` /
                         `decision` / `pass_probability` payload.

    Returns:
        list of {rank, strategy_id, score, verdict, reason, breakdown,
                 prop_firm_panel?}
    """
    if not strategies:
        return []

    scored_pairs = [(s, _score_strategy(s)) for s in strategies]
    if not include_rejects:
        scored_pairs = [(src, out) for src, out in scored_pairs if out["verdict"] != "REJECT"]

    scored_pairs.sort(key=lambda p: p[1]["score"], reverse=True)
    if top_n and top_n > 0:
        scored_pairs = scored_pairs[:top_n]

    out: list = []
    for i, (src, entry) in enumerate(scored_pairs, start=1):
        entry["rank"] = i
        if attach_panel:
            panel = _maybe_build_panel(src)
            if panel is not None:
                entry["prop_firm_panel"] = panel
        out.append(entry)
    return out


def _maybe_build_panel(src: dict) -> dict | None:
    """Attach a Prop Firm panel when there's enough info in the source item."""
    sim = src.get("simulation")
    vr = src.get("validation_report")
    dec = src.get("decision")
    pp = src.get("pass_probability")
    if sim is None and vr is None and dec is None and pp is None:
        return None
    from engines.prop_firm_panel import build_prop_firm_panel
    return build_prop_firm_panel(
        simulation=sim,
        pass_probability=pp,
        validation_report=vr,
        decision=dec,
    )


def rank_summary(strategies: list, top_n: int = TOP_N_DEFAULT) -> dict:
    """Convenience wrapper returning ranking + headline stats."""
    ranked = rank_strategies(strategies, top_n=top_n)
    all_scored = [_score_strategy(s) for s in (strategies or [])]
    verdict_counts = {"TRADE": 0, "RISKY": 0, "REJECT": 0}
    for s in all_scored:
        verdict_counts[s["verdict"]] = verdict_counts.get(s["verdict"], 0) + 1
    return {
        "ranked": ranked,
        "total_candidates": len(all_scored),
        "verdict_counts": verdict_counts,
        "top_n": top_n,
    }

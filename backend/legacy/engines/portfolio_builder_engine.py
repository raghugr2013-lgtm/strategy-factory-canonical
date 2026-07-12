"""Phase 4 — Portfolio Builder Engine.

Combines top strategies (sourced from the Phase 3 Auto Selection engine)
into a safe, diversified portfolio for prop-firm deployment.

Pipeline:
    auto_selection.run_auto_selection()
    → filter gates (pass prob, env confidence, match score, PASS/RISKY)
    → correlation / duplication filter (same pair+tf; same strategy type cap)
    → portfolio construction (3–5, prefer unique pair/tf/style)
    → risk allocation (normalise `safe_risk` across a total-risk cap)
    → combined metrics (PF, DD, pass_probability, stability, diversification)

Additive only. Does NOT modify:
    - auto_selection_engine
    - mutation engine / scoring logic
    - ingestion system
    - prop firm engine
    - Phase 7 portfolio_engine (the existing `/api/portfolio/*` routes stay
      untouched — this is a separate service mounted at
      `/api/portfolio-builder/*`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import auto_selection_engine as ase

logger = logging.getLogger(__name__)

COLLECTION = "portfolio_builder_runs"

# ── Defaults (per the Phase 4 spec) ─────────────────────────────────────
DEFAULT_POOL_SIZE = 10
DEFAULT_TARGET_MIN = 3
DEFAULT_TARGET_MAX = 5
DEFAULT_MIN_PASS_PROB = 60.0
DEFAULT_MIN_ENV_CONF = 0.7
DEFAULT_MIN_MATCH_SCORE = 0.8
DEFAULT_ALLOW_RISKY = False
DEFAULT_TOTAL_RISK_CAP = 3.0          # percent (spec range 2–4%)
DEFAULT_MAX_SAME_TYPE = 2             # cap clones of same strategy type

# Coarse style inference — cheap and explainable. Future hook: use the
# real style metadata on the strategy record if/when that lands.
_TREND_KEYS = (
    "trend", "macd", "ema", "sma", "breakout", "momentum",
    "ichimoku", "adx", "donchian", "supertrend",
)
_MR_KEYS = (
    "rsi", "reversion", "bolli", "stoch", "oscillator", "mean",
    "cci", "williams",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _style_of(type_str: Optional[str]) -> str:
    s = (type_str or "").lower()
    if any(k in s for k in _TREND_KEYS):
        return "trend"
    if any(k in s for k in _MR_KEYS):
        return "mean_reversion"
    return "other"


# ── Filter: pass/risky + quality gates ─────────────────────────────────
def _filter_candidates(
    pool: List[Dict[str, Any]],
    *,
    allow_risky: bool,
    min_pp: float,
    min_env_conf: float,
    min_match: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in pool:
        status = (c.get("status") or "").upper()
        if status == "FAIL":
            continue
        if status == "RISKY" and not allow_risky:
            continue
        if (c.get("pass_probability") or 0.0) < min_pp:
            continue
        if (c.get("env_confidence") or 0.0) < min_env_conf:
            continue
        if (c.get("match_score") or 0.0) < min_match:
            continue
        out.append(c)
    return out


# ── Diversification filter (correlation placeholder) ───────────────────
def _apply_diversification(
    cands: List[Dict[str, Any]], *, max_same_type: int,
) -> List[Dict[str, Any]]:
    """Drop duplicates sharing the same pair+timeframe (keep the strongest
    deploy_score) and cap near-clones by strategy `type`. Equity-level
    correlation is a future hook."""
    ordered = sorted(cands, key=lambda c: -(c.get("deploy_score") or 0.0))
    seen_pair_tf: set = set()
    type_count: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for c in ordered:
        key = ((c.get("pair") or "").upper(), (c.get("timeframe") or "").upper())
        if key in seen_pair_tf:
            continue
        t = (c.get("type") or "unknown").lower()
        if type_count.get(t, 0) >= max_same_type:
            continue
        seen_pair_tf.add(key)
        type_count[t] = type_count.get(t, 0) + 1
        out.append(c)
    return out


# ── Portfolio construction ─────────────────────────────────────────────
def _select_portfolio(
    cands: List[Dict[str, Any]],
    *,
    target_min: int,
    target_max: int,
) -> List[Dict[str, Any]]:
    """Pick up to `target_max` entries, strongly preferring unique pair,
    then unique timeframe, then unique style. Falls back to best-score
    fill if the preferred pool is exhausted."""
    if not cands:
        return []
    ordered = sorted(cands, key=lambda c: -(c.get("deploy_score") or 0.0))

    selected: List[Dict[str, Any]] = []
    used_pairs: set = set()
    used_tfs: set = set()
    used_styles: set = set()

    # Pass 1 — insist on unique pair (the strongest diversification axis).
    for c in ordered:
        if len(selected) >= target_max:
            break
        pair = (c.get("pair") or "").upper()
        if pair and pair in used_pairs:
            continue
        selected.append(c)
        used_pairs.add(pair)
        used_tfs.add((c.get("timeframe") or "").upper())
        used_styles.add(_style_of(c.get("type")))

    # Pass 2 — fill to target_max with any remaining (duplicates of pair
    # already rejected in diversification, so this mostly adds style mix).
    if len(selected) < target_max:
        picked = {c["strategy_hash"] for c in selected}
        for c in ordered:
            if len(selected) >= target_max:
                break
            if c["strategy_hash"] in picked:
                continue
            selected.append(c)
            picked.add(c["strategy_hash"])

    return selected[:target_max] if len(selected) >= target_min else selected


# ── Risk allocation ────────────────────────────────────────────────────
def _allocate_risk(
    strategies: List[Dict[str, Any]], *, total_cap: float,
) -> Dict[str, Dict[str, float]]:
    """Normalise per-strategy `safe_risk` so the sum == total_cap (%)."""
    if not strategies:
        return {}
    raw = [max(0.01, float(s.get("safe_risk") or 1.0)) for s in strategies]
    total = sum(raw) or 1.0
    alloc: Dict[str, Dict[str, float]] = {}
    for s, r in zip(strategies, raw):
        weight = r / total
        alloc[s["strategy_hash"]] = {
            "risk_pct": round(weight * total_cap, 3),
            "weight": round(weight, 4),
            "safe_risk_raw": round(r, 3),
        }
    return alloc


# ── Combined metrics ───────────────────────────────────────────────────
def _blend_metrics(
    strategies: List[Dict[str, Any]],
    allocation: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    if not strategies:
        return {
            "expected_pf": None,
            "expected_dd": None,
            "pass_probability": None,
            "stability_score": None,
            "diversification_score": 0.0,
        }
    n = len(strategies)
    weights = [
        allocation.get(s["strategy_hash"], {}).get("weight", 1.0 / n)
        for s in strategies
    ]

    # Weighted PF (approximation — treats weight as capital share)
    pf_pairs = [
        (s.get("strategy_best_pf"), w)
        for s, w in zip(strategies, weights)
        if isinstance(s.get("strategy_best_pf"), (int, float))
    ]
    if pf_pairs:
        wsum = sum(w for _, w in pf_pairs) or 1.0
        expected_pf = round(sum(pf * w for pf, w in pf_pairs) / wsum, 3)
    else:
        expected_pf = None

    # Combined DD — worst-case sum of per-strategy risk allocation (%)
    expected_dd = round(
        sum(a.get("risk_pct", 0.0) for a in allocation.values()), 3,
    ) if allocation else None

    # Blended pass probability (weighted)
    pass_prob = round(
        sum((s.get("pass_probability") or 0.0) * w for s, w in zip(strategies, weights)),
        2,
    )

    stabs = [s.get("strategy_stability") for s in strategies if s.get("strategy_stability") is not None]
    stability = round(sum(stabs) / len(stabs), 3) if stabs else None

    pairs = {(s.get("pair") or "").upper() for s in strategies if s.get("pair")}
    tfs = {(s.get("timeframe") or "").upper() for s in strategies if s.get("timeframe")}
    styles = {_style_of(s.get("type")) for s in strategies}
    # Diversification: avg of (unique pairs / n), (unique tfs / n),
    # (styles covered out of 3 possible buckets).
    div_score = round(
        (len(pairs) / n + len(tfs) / n + min(len(styles), 3) / 3) / 3, 3,
    )

    return {
        "expected_pf": expected_pf,
        "expected_dd": expected_dd,
        "pass_probability": pass_prob,
        "stability_score": stability,
        "diversification_score": div_score,
    }


# ── Public API ─────────────────────────────────────────────────────────
async def build_portfolio(
    *,
    pool_size: int = DEFAULT_POOL_SIZE,
    target_min: int = DEFAULT_TARGET_MIN,
    target_max: int = DEFAULT_TARGET_MAX,
    min_pass_probability: float = DEFAULT_MIN_PASS_PROB,
    min_env_confidence: float = DEFAULT_MIN_ENV_CONF,
    min_match_score: float = DEFAULT_MIN_MATCH_SCORE,
    allow_risky: bool = DEFAULT_ALLOW_RISKY,
    total_risk_cap: float = DEFAULT_TOTAL_RISK_CAP,
    max_same_type: int = DEFAULT_MAX_SAME_TYPE,
    persist: bool = False,
    run_missing_matches: bool = True,
) -> Dict[str, Any]:
    """Build a portfolio from the current Auto Selection top-N. Safe to
    call without any pre-existing auto-selection run: we call the engine
    directly (without persisting the intermediate selection)."""

    target_min = min(target_min, target_max)

    # Step 1 — candidate pool from Auto Selection.
    # We ask for more than `pool_size` so that gating/diversification
    # has room to drop losers before we cap at pool_size.
    sel_filters = dict(
        top_n=max(pool_size * 2, 20),
        run_missing_matches=run_missing_matches,
        persist=False,
        # Leave the auto-selection gates permissive — we apply the
        # Phase-4 specific gates (pass%, env conf, match) ourselves.
        min_pass_probability=0.0,
        min_match_score=-1.0,
        min_env_confidence=0.0,
        pass_only=False,
    )
    try:
        selection = await ase.run_auto_selection(**sel_filters)
    except Exception:
        logger.exception("portfolio-builder: auto_selection call failed")
        selection = {"top": [], "considered": 0, "eligible": 0}

    pool = list(selection.get("top") or [])[:pool_size]

    # Step 2 — quality gates.
    filtered = _filter_candidates(
        pool,
        allow_risky=allow_risky,
        min_pp=min_pass_probability,
        min_env_conf=min_env_confidence,
        min_match=min_match_score,
    )

    # Step 3 — diversification / correlation-placeholder.
    diversified = _apply_diversification(filtered, max_same_type=max_same_type)

    # Step 4 — portfolio construction (3–5).
    selected = _select_portfolio(
        diversified, target_min=target_min, target_max=target_max,
    )

    # Step 5 — risk allocation.
    allocation = _allocate_risk(selected, total_cap=total_risk_cap)

    # Step 6 — combined metrics.
    metrics = _blend_metrics(selected, allocation)

    # Step 7 — output payload.
    result: Dict[str, Any] = {
        "status": "ok" if len(selected) >= target_min else "insufficient_candidates",
        "pool_considered": selection.get("considered", 0),
        "pool_size": len(pool),
        "filtered_count": len(filtered),
        "diversified_count": len(diversified),
        "selected_count": len(selected),
        "strategies": selected,
        "allocation": allocation,
        "total_risk": round(
            sum(a.get("risk_pct", 0.0) for a in allocation.values()), 3,
        ),
        "expected_pf": metrics["expected_pf"],
        "expected_dd": metrics["expected_dd"],
        "pass_probability": metrics["pass_probability"],
        "stability_score": metrics["stability_score"],
        "diversification_score": metrics["diversification_score"],
        "filters": {
            "pool_size": pool_size,
            "target_min": target_min,
            "target_max": target_max,
            "min_pass_probability": min_pass_probability,
            "min_env_confidence": min_env_confidence,
            "min_match_score": min_match_score,
            "allow_risky": allow_risky,
            "total_risk_cap": total_risk_cap,
            "max_same_type": max_same_type,
        },
        "built_at": _now_iso(),
        "persisted": False,
    }

    if persist and selected:
        saved = await save_portfolio(result)
        result["persisted"] = True
        result["portfolio_id"] = saved.get("portfolio_id")

    return result


async def save_portfolio(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a built portfolio for later recall. Caller-owned save —
    never auto-persists during /build unless `persist=True` is passed."""
    db = get_db()
    ts = _now_iso()
    # Build a deep-copy-ish insertion doc so Mongo cannot pollute the
    # caller's dict with an ObjectId.
    insert_doc: Dict[str, Any] = {
        "portfolio_id": ts,
        "saved_at": ts,
        "meta": {k: v for k, v in portfolio.items()},
    }
    await db[COLLECTION].insert_one(insert_doc)
    # Return a projection-safe response (strip the _id Mongo added).
    return {
        "portfolio_id": insert_doc["portfolio_id"],
        "saved_at": insert_doc["saved_at"],
    }


async def get_recent(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = (
        db[COLLECTION]
        .find({}, {"_id": 0})
        .sort("saved_at", -1)
        .limit(max(1, min(limit, 50)))
    )
    return [d async for d in cursor]

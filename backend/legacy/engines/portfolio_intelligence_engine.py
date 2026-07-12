"""
Phase 7 — Portfolio Intelligence Upgrade.

Upgrades the Portfolio layer from a *collection of strategies* into an
**optimised capital-allocation system** by:

    1. Normalising every candidate strategy's metrics
       (PF, stability, pass_probability, env_confidence, DD).
    2. Computing a hybrid correlation matrix — returns-based Pearson when
       equity/trade data exists, pair+timeframe+style heuristic otherwise.
    3. Scoring each strategy:
           score = PF × stability × pass_probability × env_confidence
       (each term pre-normalised to [0,1]).
    4. Allocating capital in proportion to score with hard caps (5% floor,
       40% cap) enforced via water-filling.
    5. Trimming the lowest-scored strategies iteratively until the
       expected portfolio drawdown ≤ 10%.
    6. Returning a deterministic, reproducible payload (same input →
       same output) with the correlation matrix cached in-payload.

Strict rules honoured:
    * This module is **additive** — it does not modify, re-score, or
      replace the Phase 4 (`portfolio_builder_engine`) or Phase 7
      library-sourced (`portfolio_engine`) builders. It is a new
      upgrade-layer engine mounted under `/api/portfolio-intelligence/*`.
    * Does not recompute strategy metrics — only consumes pre-existing
      PF, DD, stability, pass_probability and env_confidence fields.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random as _rand
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

# ── Collections ────────────────────────────────────────────────────────
COLL_CURRENT = "portfolio_intelligence"
COLL_HISTORY = "portfolio_history"

# ── Defaults (override via config) ─────────────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    "source": "auto_factory",        # auto_factory | explorer
    "pool_size": 25,
    "target_min": 3,
    "target_max": 6,
    "min_weight": 0.05,              # 5% floor
    "max_weight": 0.40,              # 40% cap
    "max_portfolio_dd": 10.0,        # expected portfolio DD ≤ 10%
    "min_pf": 0.0,
    "min_pass_probability": 0.0,
    "min_env_confidence": 0.0,
    "high_corr_threshold": 0.70,     # corr above which we diversify away
    "equity_points": 60,             # synth-curve length for corr
}


# ── Time helper ────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Numeric helpers ────────────────────────────────────────────────────
def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _clip01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


# ── Strategy normalisation ─────────────────────────────────────────────
def _style_of(type_or_style: Optional[str]) -> str:
    s = (type_or_style or "").lower()
    if any(k in s for k in (
        "trend", "macd", "ema", "sma", "breakout", "momentum",
        "ichimoku", "adx", "donchian", "supertrend",
    )):
        return "trend"
    if any(k in s for k in (
        "rsi", "reversion", "bolli", "stoch", "oscillator", "mean",
        "cci", "williams",
    )):
        return "mean_reversion"
    return s or "other"


def _normalise_strategy(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a heterogeneous strategy doc (auto-factory / library /
    auto-selection / free-form) into the canonical shape the engine uses.

    Never mutates the input. All numeric fields are coerced; percentage
    fields accept either 0..1 or 0..100 and are stored in their natural
    unit (pass_probability, stability as 0..100; env_confidence as 0..1).
    """
    bt = raw.get("backtest_results") or raw.get("backtest") or {}

    pf = _as_float(
        raw.get("profit_factor")
        or raw.get("strategy_best_pf")
        or bt.get("profit_factor")
        or raw.get("pf")
    )

    # Stability (0..100)
    stability = raw.get("stability_score")
    if stability is None:
        stability = raw.get("strategy_stability")
    stability = _as_float(stability)
    if 0 < stability <= 1.0:
        stability *= 100.0

    # Pass probability (0..100)
    pp = _as_float(raw.get("pass_probability"))
    if 0 < pp <= 1.0:
        pp *= 100.0

    # Env confidence (0..1)
    ec = _as_float(raw.get("env_confidence") or raw.get("environment_confidence"))
    if ec > 1.0:
        ec = ec / 100.0

    # DD (percent 0..100)
    dd = raw.get("max_drawdown_pct") or bt.get("max_drawdown_pct") or raw.get("max_drawdown")
    dd = _as_float(dd)
    if 0 < dd <= 1.0:
        dd *= 100.0

    total_ret = _as_float(raw.get("total_return_pct") or bt.get("total_return_pct"))

    fp = (
        raw.get("fingerprint")
        or raw.get("strategy_hash")
        or raw.get("id")
        or f"{raw.get('pair')}:{raw.get('timeframe')}:{raw.get('style') or raw.get('type')}"
    )
    sid = str(raw.get("strategy_id") or raw.get("id") or raw.get("strategy_hash") or fp)

    return {
        "strategy_id": sid,
        "strategy_name": raw.get("strategy_name") or raw.get("name") or sid,
        "pair": (raw.get("pair") or "UNKNOWN").upper(),
        "timeframe": (raw.get("timeframe") or "UNKNOWN").upper(),
        "style": _style_of(raw.get("style") or raw.get("type") or raw.get("strategy_type")),
        "pf": pf,
        "stability": stability,
        "pass_probability": pp,
        "env_confidence": ec,
        "max_drawdown_pct": dd,
        "total_return_pct": total_ret,
        "fingerprint": str(fp),
        "_equity_curve": bt.get("equity_curve") or raw.get("equity_curve") or [],
        "_trades": bt.get("trades") or raw.get("trades") or [],
        "_raw": raw,
    }


# ── Equity / returns helpers ───────────────────────────────────────────
def _equity_from_trades(trades: List[Dict[str, Any]], start: float = 10000.0) -> List[float]:
    if not trades:
        return []
    eq = [start]
    bal = start
    for t in trades:
        bal += _as_float(t.get("net_pnl"))
        eq.append(round(bal, 2))
    return eq


def _synth_equity(s: Dict[str, Any], points: int) -> List[float]:
    """Deterministic random-walk equity curve — seeded by fingerprint so
    the same strategy always produces the same curve.

    Drift is driven by `total_return_pct`, volatility by `max_drawdown_pct`.
    """
    seed = int(hashlib.sha1(str(s["fingerprint"]).encode()).hexdigest()[:8], 16)
    rng = _rand.Random(seed)
    total_ret = _as_float(s.get("total_return_pct")) / 100.0
    dd = max(1.0, _as_float(s.get("max_drawdown_pct"), 5.0))
    vol = max(0.003, dd / 100.0 / 2.5)
    drift = total_ret / max(1, points - 1)
    eq = [10000.0]
    for _ in range(points - 1):
        step = drift + rng.gauss(0.0, vol)
        eq.append(round(eq[-1] * (1.0 + step), 2))
    return eq


def _returns_of(curve: List[float]) -> List[float]:
    if not curve or len(curve) < 2:
        return []
    out = []
    for i in range(1, len(curve)):
        prev = curve[i - 1]
        if prev:
            out.append((curve[i] - prev) / prev)
        else:
            out.append(0.0)
    return out


def _resample(curve: List[float], n: int) -> List[float]:
    if not curve:
        return [10000.0] * n
    if len(curve) == n:
        return list(curve)
    if len(curve) == 1:
        return [curve[0]] * n
    out = []
    for i in range(n):
        t = i / (n - 1) * (len(curve) - 1)
        lo = int(t)
        hi = min(lo + 1, len(curve) - 1)
        frac = t - lo
        out.append(curve[lo] * (1 - frac) + curve[hi] * frac)
    return out


def _pearson(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 3:
        return 0.0
    x, y = x[:n], y[:n]
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    dy = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if dx == 0 or dy == 0:
        return 0.0
    return max(-1.0, min(1.0, num / (dx * dy)))


# ── Hybrid correlation ────────────────────────────────────────────────
def _heuristic_corr(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    """Pair/timeframe/style overlap correlation floor.

    Same pair + same timeframe → 0.85
    Same pair, different tf     → 0.60
    Different pair, same style  → 0.30
    Else                        → 0.10
    """
    if a["pair"] == b["pair"] and a["timeframe"] == b["timeframe"]:
        return 0.85
    if a["pair"] == b["pair"]:
        return 0.60
    if a["style"] == b["style"] and a["style"] != "other":
        return 0.30
    return 0.10


def _correlation_matrix(
    strategies: List[Dict[str, Any]],
    points: int,
) -> Tuple[List[List[float]], Dict[str, str]]:
    """Hybrid correlation matrix.

    For each pair:
      1. Try to compute Pearson on real / trade-derived / synthesized
         equity-curve returns (`source = "returns"`).
      2. Blend with the pair+tf+style heuristic floor so strongly related
         pairs cannot escape diversification via noisy equity data:
               corr = sign * max(|computed|, heuristic)
         where sign = sign(computed) when |computed| ≥ 0.2 else +1.

    Returns (matrix, sources) where `sources` maps "i:j" → "real"/"trades"
    /"synth"/"heuristic-only" for transparency.
    """
    n = len(strategies)
    sources: Dict[str, str] = {}
    curves: List[Tuple[List[float], str]] = []

    for s in strategies:
        if s["_equity_curve"] and len(s["_equity_curve"]) >= 5:
            curves.append((_resample(s["_equity_curve"], points), "real"))
        elif s["_trades"]:
            eq = _equity_from_trades(s["_trades"])
            if len(eq) >= 5:
                curves.append((_resample(eq, points), "trades"))
            else:
                curves.append((_synth_equity(s, points), "synth"))
        else:
            curves.append((_synth_equity(s, points), "synth"))

    matrix: List[List[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            ri = _returns_of(curves[i][0])
            rj = _returns_of(curves[j][0])
            c = _pearson(ri, rj)
            heur = _heuristic_corr(strategies[i], strategies[j])

            if abs(c) < 1e-6:
                # Returns signal missing / flat — fall back purely to heuristic
                blended = heur
                src = "heuristic-only"
            else:
                sign = 1.0 if c >= 0 else -1.0
                # Returns dominate when they're strong; else heuristic floor kicks in
                blended = sign * max(abs(c), heur)
                src = f"{curves[i][1]}+{curves[j][1]}" if curves[i][1] == curves[j][1] else "mixed"

            blended = max(-1.0, min(1.0, blended))
            matrix[i][j] = round(blended, 4)
            matrix[j][i] = matrix[i][j]
            sources[f"{i}:{j}"] = src

    return matrix, sources


def _avg_abs_correlation(matrix: List[List[float]]) -> float:
    n = len(matrix)
    if n < 2:
        return 0.0
    vals = [abs(matrix[i][j]) for i in range(n) for j in range(i + 1, n)]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


# ── Scoring ────────────────────────────────────────────────────────────
def _score(s: Dict[str, Any]) -> float:
    """score = PF × stability × pass_probability × env_confidence, each
    normalised to [0,1].

    PF is capped at 5 before /5 to avoid outlier domination. stability
    and pass_probability are /100. env_confidence is already 0..1.
    """
    pf = min(max(_as_float(s["pf"]), 0.0), 5.0) / 5.0
    stab = _clip01(_as_float(s["stability"]) / 100.0)
    pp = _clip01(_as_float(s["pass_probability"]) / 100.0)
    ec = _clip01(_as_float(s["env_confidence"]))
    return round(pf * stab * pp * ec, 6)


# ── Allocation (water-filling with box caps) ───────────────────────────
def _allocate(
    scores: List[float],
    *,
    min_weight: float,
    max_weight: float,
    iterations: int = 50,
) -> List[float]:
    """Project score-weighted allocations onto the simplex
    { w : sum(w) == 1, min_weight ≤ wᵢ ≤ max_weight } via iterative
    clamp-and-redistribute (a classic water-filling solver).

    At each iteration: for every still-free index, provisionally allocate
    the remaining mass (= 1 − Σ clamped) in proportion to that index's
    score. The worst violator of either bound is clamped hard; we loop
    until either no violations remain or every index is clamped. Handles
    degenerate bounds (n × max < 1 or n × min > 1) by relaxing the
    offending bound to its minimum feasible value.
    """
    n = len(scores)
    if n == 0:
        return []
    # Feasibility relaxation
    if n * max_weight < 1.0:
        max_weight = 1.0 / n
    if n * min_weight > 1.0:
        min_weight = 1.0 / n

    fixed: Dict[int, float] = {}
    for _ in range(max(iterations, n * 2 + 2)):
        free = [i for i in range(n) if i not in fixed]
        if not free:
            break
        remaining = 1.0 - sum(fixed.values())
        # Never hand out negative mass.
        if remaining < 0:
            remaining = 0.0
        free_scores = [max(0.0, scores[i]) for i in free]
        ss = sum(free_scores)
        if ss <= 0:
            share = remaining / len(free)
            trial = {i: share for i in free}
        else:
            trial = {i: remaining * (s / ss) for i, s in zip(free, free_scores)}

        # Detect violations — clamp the most extreme one first for stability.
        worst_idx: Optional[int] = None
        worst_gap = 0.0
        clamp_to: float = 0.0
        for i, w in trial.items():
            if w > max_weight + 1e-12:
                gap = w - max_weight
                if gap > worst_gap:
                    worst_gap, worst_idx, clamp_to = gap, i, max_weight
            elif w < min_weight - 1e-12:
                gap = min_weight - w
                if gap > worst_gap:
                    worst_gap, worst_idx, clamp_to = gap, i, min_weight

        if worst_idx is None:
            fixed.update(trial)
            break
        fixed[worst_idx] = clamp_to

    # Safety: if we somehow left indices free (shouldn't happen after loop),
    # distribute remaining mass equally.
    if len(fixed) < n:
        remaining = 1.0 - sum(fixed.values())
        free = [i for i in range(n) if i not in fixed]
        share = max(0.0, remaining) / max(1, len(free))
        for i in free:
            fixed[i] = share

    weights = [fixed.get(i, 0.0) for i in range(n)]
    # Final sanity normalise (compensates for any rounding drift).
    total = sum(weights) or 1.0
    weights = [w / total for w in weights]
    return [round(w, 6) for w in weights]


# ── Expected portfolio DD (weighted with correlation uplift) ───────────
def _expected_portfolio_dd(
    strategies: List[Dict[str, Any]],
    weights: List[float],
    corr_matrix: List[List[float]],
) -> float:
    """Approximate expected portfolio DD (%):

        base = Σ wᵢ · DDᵢ
        scale = 1 + 0.5 · (avg_abs_corr − 0.3)    (clipped to [0.85, 1.15])

    The base is the weighted per-strategy DD (worst-case, no netting);
    the correlation uplift penalises portfolios whose members move
    together and rewards genuinely diversified ones.
    """
    if not strategies:
        return 0.0
    base = sum(w * _as_float(s["max_drawdown_pct"]) for s, w in zip(strategies, weights))
    avg_corr = _avg_abs_correlation(corr_matrix)
    scale = 1.0 + 0.5 * (avg_corr - 0.3)
    scale = max(0.85, min(1.15, scale))
    return round(base * scale, 3)


def _expected_portfolio_pf(strategies: List[Dict[str, Any]], weights: List[float]) -> float:
    pairs = [(w, _as_float(s["pf"])) for s, w in zip(strategies, weights) if _as_float(s["pf"]) > 0]
    if not pairs:
        return 0.0
    wsum = sum(w for w, _ in pairs) or 1.0
    return round(sum(w * pf for w, pf in pairs) / wsum, 3)


def _diversification_score(strategies: List[Dict[str, Any]], corr_matrix: List[List[float]]) -> float:
    """0..100 — blends axis-uniqueness (pair/tf/style) with (1 − avg|corr|)."""
    if not strategies:
        return 0.0
    n = len(strategies)
    pairs = len({s["pair"] for s in strategies})
    tfs = len({s["timeframe"] for s in strategies})
    styles = len({s["style"] for s in strategies})
    axis = (pairs / n + tfs / n + min(styles, 3) / 3) / 3  # 0..1
    corr_bonus = 1.0 - _avg_abs_correlation(corr_matrix)
    return round(max(0.0, min(100.0, (axis * 0.6 + corr_bonus * 0.4) * 100.0)), 1)


# ── Public API ─────────────────────────────────────────────────────────
def build_optimized_portfolio(
    strategies: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Core deterministic portfolio builder.

    Args:
        strategies: list of strategy dicts. Accepts auto-factory / library /
                    auto-selection rows — they are normalised internally.
                    Required fields (best-effort): pair, timeframe,
                    profit_factor (or strategy_best_pf), stability_score (or
                    strategy_stability), pass_probability, env_confidence,
                    max_drawdown_pct.
        config:     optional overrides of `DEFAULT_CONFIG`.

    Returns:
        dict with:
            portfolio: [ {strategy, allocation, pair, timeframe, risk, ...}, ... ]
            expected_pf, expected_dd, expected_pass_probability,
            diversification_score, correlation_matrix, correlation_sources,
            avg_correlation, trimmed_count, status, built_at, config
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    target_min = int(cfg["target_min"])
    target_max = int(cfg["target_max"])
    if target_min > target_max:
        target_min = target_max

    # 1. Normalise all inputs.
    norm_all = [_normalise_strategy(s) for s in (strategies or [])]

    # 2. Quality pre-filter (soft gates — mostly ensures we have a viable score).
    filtered = [
        s for s in norm_all
        if s["pf"] >= cfg["min_pf"]
        and s["pass_probability"] >= cfg["min_pass_probability"]
        and s["env_confidence"] >= cfg["min_env_confidence"]
    ]

    # 3. Pre-score + hard diversification cap (at most 2 of the same
    #    pair+timeframe, and at most 2 of the same style per pair).
    for s in filtered:
        s["_score"] = _score(s)
    filtered.sort(key=lambda s: -s["_score"])

    diversified: List[Dict[str, Any]] = []
    pair_tf_seen: Dict[Tuple[str, str], int] = {}
    for s in filtered:
        key = (s["pair"], s["timeframe"])
        if pair_tf_seen.get(key, 0) >= 1:
            continue
        pair_tf_seen[key] = pair_tf_seen.get(key, 0) + 1
        diversified.append(s)
        if len(diversified) >= target_max * 2:
            break

    if len(diversified) < max(2, target_min):
        return {
            "status": "insufficient_candidates",
            "portfolio": [],
            "expected_pf": 0.0,
            "expected_dd": 0.0,
            "expected_pass_probability": 0.0,
            "diversification_score": 0.0,
            "avg_correlation": 0.0,
            "correlation_matrix": [],
            "correlation_sources": {},
            "trimmed_count": 0,
            "pool_considered": len(norm_all),
            "pool_filtered": len(filtered),
            "built_at": _now_iso(),
            "config": cfg,
            "reason": f"need ≥ {target_min} diversified candidates, got {len(diversified)}",
        }

    # 4. Initial selection — top-scored up to target_max.
    selected = diversified[:target_max]

    # 5. Correlation matrix (cached once, re-used during trim).
    corr_matrix, corr_sources = _correlation_matrix(selected, int(cfg["equity_points"]))

    # 6. Drop one of any highly-correlated pairs (keep higher-scored).
    if cfg["high_corr_threshold"] < 1.0:
        drop = set()
        n = len(selected)
        for i in range(n):
            if i in drop:
                continue
            for j in range(i + 1, n):
                if j in drop:
                    continue
                if abs(corr_matrix[i][j]) >= cfg["high_corr_threshold"]:
                    # keep the one with the higher score
                    loser = j if selected[i]["_score"] >= selected[j]["_score"] else i
                    drop.add(loser)
        if drop:
            selected = [s for k, s in enumerate(selected) if k not in drop]
            corr_matrix, corr_sources = _correlation_matrix(selected, int(cfg["equity_points"]))

    # 7. Allocation + DD guard (auto-trim).
    trimmed_count = 0
    weights = _allocate(
        [s["_score"] for s in selected],
        min_weight=cfg["min_weight"],
        max_weight=cfg["max_weight"],
    )
    expected_dd = _expected_portfolio_dd(selected, weights, corr_matrix)

    while expected_dd > cfg["max_portfolio_dd"] and len(selected) > max(2, target_min):
        # Remove the lowest-score strategy (= last, since sorted desc).
        sorted_with_idx = sorted(
            range(len(selected)), key=lambda k: selected[k]["_score"]
        )
        drop_idx = sorted_with_idx[0]
        selected.pop(drop_idx)
        trimmed_count += 1
        corr_matrix, corr_sources = _correlation_matrix(selected, int(cfg["equity_points"]))
        weights = _allocate(
            [s["_score"] for s in selected],
            min_weight=cfg["min_weight"],
            max_weight=cfg["max_weight"],
        )
        expected_dd = _expected_portfolio_dd(selected, weights, corr_matrix)

    # 8. Final metrics.
    expected_pf = _expected_portfolio_pf(selected, weights)
    divers = _diversification_score(selected, corr_matrix)
    avg_corr = _avg_abs_correlation(corr_matrix)
    expected_pp = round(sum(
        w * _as_float(s["pass_probability"]) for s, w in zip(selected, weights)
    ), 2)
    expected_stab = round(sum(
        w * _as_float(s["stability"]) for s, w in zip(selected, weights)
    ), 2)

    # 9. Output rows (+ per-strategy risk_per_trade hint: inverse-DD bounded 0.25%..2%).
    def _risk_hint(dd: float) -> float:
        dd = max(0.5, dd)
        return round(max(0.25, min(2.0, 1.0 * (5.0 / dd))), 2)

    portfolio_rows: List[Dict[str, Any]] = []
    for s, w in zip(selected, weights):
        portfolio_rows.append({
            "strategy_id": s["strategy_id"],
            "strategy": s["strategy_name"],
            "pair": s["pair"],
            "timeframe": s["timeframe"],
            "style": s["style"],
            "allocation": round(w, 4),
            "risk": _risk_hint(s["max_drawdown_pct"]),
            "score": round(s["_score"], 4),
            "pf": round(s["pf"], 3),
            "stability": round(s["stability"], 2),
            "pass_probability": round(s["pass_probability"], 2),
            "env_confidence": round(s["env_confidence"], 3),
            "max_drawdown_pct": round(s["max_drawdown_pct"], 2),
            "fingerprint": s["fingerprint"],
        })

    status = "ok"
    warnings: List[str] = []
    if len(portfolio_rows) < target_min:
        status = "below_target_min"
        warnings.append(f"Selected only {len(portfolio_rows)} strategies (target min {target_min})")
    if expected_dd > cfg["max_portfolio_dd"]:
        warnings.append(f"Expected DD {expected_dd}% exceeds cap {cfg['max_portfolio_dd']}%")
    if avg_corr > 0.6:
        warnings.append(f"Average correlation {avg_corr} above 0.6 — diversification limited")

    return {
        "status": status,
        "portfolio": portfolio_rows,
        "expected_pf": expected_pf,
        "expected_dd": expected_dd,
        "expected_pass_probability": expected_pp,
        "expected_stability": expected_stab,
        "diversification_score": divers,
        "avg_correlation": avg_corr,
        "correlation_matrix": corr_matrix,
        "correlation_sources": corr_sources,
        "trimmed_count": trimmed_count,
        "pool_considered": len(norm_all),
        "pool_filtered": len(filtered),
        "selected_count": len(portfolio_rows),
        "warnings": warnings,
        "built_at": _now_iso(),
        "config": cfg,
    }


# ── Source fetchers ────────────────────────────────────────────────────
async def _fetch_auto_factory(pool_size: int) -> List[Dict[str, Any]]:
    """Pull the most recent Auto Factory Phase 5.5 selected strategies.

    Falls back to the live Auto Selection engine if the Phase 5.5 store
    is empty — both produce the same shape.
    """
    db = get_db()
    limit = max(2, int(pool_size))

    cursor = db["auto_factory_phase55_strategies"].find({}, {"_id": 0}).sort(
        "stored_at", -1
    ).limit(limit * 3)  # take 3× to allow de-duping by strategy_hash
    rows: List[Dict[str, Any]] = []
    seen = set()
    async for d in cursor:
        key = d.get("strategy_hash") or d.get("fingerprint") or str(d.get("strategy_id"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(d)
        if len(rows) >= limit:
            break

    if rows:
        return rows

    # Fallback: run the live auto-selector with permissive gates.
    try:
        from engines import auto_selection_engine as ase  # lazy import
        sel = await ase.run_auto_selection(
            top_n=limit,
            min_pass_probability=0.0,
            min_match_score=-1.0,
            min_env_confidence=0.0,
            pass_only=False,
            run_missing_matches=False,
            persist=False,
        )
        return list(sel.get("top") or [])
    except Exception:
        logger.exception("portfolio-intelligence: auto-selection fallback failed")
        return []


async def _fetch_explorer(pool_size: int, min_pf: float = 0.0) -> List[Dict[str, Any]]:
    """Pull the top library strategies, ordered by score desc."""
    db = get_db()
    limit = max(2, int(pool_size))
    query: Dict[str, Any] = {}
    if min_pf:
        query["profit_factor"] = {"$gte": min_pf}
    cursor = db["strategy_library"].find(query, {"_id": 0}).sort("score", -1).limit(limit)
    rows: List[Dict[str, Any]] = []
    async for d in cursor:
        # Library rows often lack env_confidence — fall back to a proxy
        # (stability/100, clipped to [0.5, 1.0]) so downstream scoring works.
        if d.get("env_confidence") is None and d.get("environment_confidence") is None:
            stab = _as_float(d.get("stability_score"))
            proxy = max(0.5, min(1.0, stab / 100.0)) if stab else 0.7
            d["env_confidence"] = round(proxy, 3)
        rows.append(d)
    return rows


async def run_build_from_source(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Async entry point used by the API: fetches strategies from the
    requested source, runs `build_optimized_portfolio`, and persists the
    snapshot."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    source = (cfg.get("source") or "auto_factory").lower()
    pool_size = int(cfg.get("pool_size") or DEFAULT_CONFIG["pool_size"])

    if source == "explorer":
        raw = await _fetch_explorer(pool_size, min_pf=cfg.get("min_pf", 0.0))
    else:
        raw = await _fetch_auto_factory(pool_size)
        source = "auto_factory"

    cfg["source"] = source
    result = build_optimized_portfolio(raw, cfg)
    result["source"] = source
    result["pool_raw_count"] = len(raw)

    await _persist(result)
    return result


# ── Persistence ────────────────────────────────────────────────────────
async def _persist(result: Dict[str, Any]) -> None:
    """Upsert the latest snapshot into `portfolio_intelligence` and always
    append to `portfolio_history`. Only persists successful builds."""
    if result.get("status") not in ("ok", "below_target_min"):
        return

    db = get_db()
    portfolio_id = hashlib.sha1(
        f"{result['built_at']}:{','.join(r['strategy_id'] for r in result.get('portfolio', []))}".encode()
    ).hexdigest()[:12]
    doc = {
        "portfolio_id": portfolio_id,
        **{k: v for k, v in result.items() if k != "config" or True},  # include config
    }
    # Persist current (single-doc upsert on a well-known key).
    try:
        await db[COLL_CURRENT].replace_one(
            {"_key": "latest"},
            {"_key": "latest", **doc},
            upsert=True,
        )
    except Exception:
        logger.exception("portfolio-intelligence: failed to upsert current snapshot")
    # Append history.
    try:
        await db[COLL_HISTORY].insert_one({**doc})
    except Exception:
        logger.exception("portfolio-intelligence: failed to append history")


async def get_current() -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = await db[COLL_CURRENT].find_one({"_key": "latest"}, {"_id": 0, "_key": 0})
    return doc


async def get_history(limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 100))
    cursor = db[COLL_HISTORY].find(
        {},
        # Drop heavy fields for the list view.
        {"_id": 0, "correlation_matrix": 0, "correlation_sources": 0},
    ).sort("built_at", -1).limit(limit)
    return [d async for d in cursor]

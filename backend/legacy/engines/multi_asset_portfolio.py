"""
P4 — Multi-Asset Portfolio Rollout.

Orchestrates strategy generation across multiple pairs and combines the
survivors into a single portfolio block. Adds per-asset quality gates
so pathologically bad assets cannot pollute the portfolio.

Public API
----------
    run_asset_gate(strategy_template, pair, timeframe, prices, seeds, threshold)
        Run a deterministic 5-seed GA on a baseline template. Pass when
        median OOS PF ≥ `threshold` (default 1.10).

    combine_per_pair_cards(pair_results, top_n=None)
        Pool the top strategies across pairs and call the existing
        `portfolio_combiner.combine_top_strategies`. Returns the
        standard portfolio block plus a per-asset contribution
        breakdown.

Strict contract:
    * Never raises. On any error returns `{"success": False, "error": "..."}`
    * Additive only — no changes to single-asset pipeline.
"""
from __future__ import annotations

import logging
import statistics as stats
from typing import Iterable, Sequence

from engines.ga_optimizer import run_ga_search
from engines.portfolio_combiner import combine_top_strategies

logger = logging.getLogger(__name__)

# Deterministic per-style baselines for the asset gate. The gate
# measures how tradable the asset itself is — not the user's specific
# strategy — so a single well-known template per style is enough.
GATE_TEMPLATES = {
    "trend-following": "EMA(20)/EMA(50) trend-following SL=20 TP=40",
    "mean-reversion":  "RSI(14) mean-reversion with BB(20) — SL=30 TP=60",
    "momentum":        "MACD(12,26,9) momentum strategy SL=25 TP=50",
    "breakout":        "EMA(20) breakout strategy SL=20 TP=40",
}
DEFAULT_GATE_STYLE = "trend-following"

DEFAULT_GATE_SEEDS: tuple = (7, 42, 101, 314, 2718)
DEFAULT_GATE_POP = 10
DEFAULT_GATE_GENS = 3
DEFAULT_GATE_THRESHOLD = 1.10
DEFAULT_GATE_MAX_DD = 30.0   # % — also reject assets with unrecoverable DD
DEFAULT_GATE_TRAIN_RATIO = 0.70


def _safe_float(v, default: float | None = None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _median(values: Sequence[float]) -> float | None:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return None
    try:
        return float(stats.median(cleaned))
    except Exception:
        return None


def run_asset_gate(
    pair: str,
    timeframe: str,
    prices: list,
    *,
    style: str = DEFAULT_GATE_STYLE,
    seeds: Iterable[int] = DEFAULT_GATE_SEEDS,
    threshold: float = DEFAULT_GATE_THRESHOLD,
    max_dd_pct: float = DEFAULT_GATE_MAX_DD,
    population: int = DEFAULT_GATE_POP,
    generations: int = DEFAULT_GATE_GENS,
    train_ratio: float = DEFAULT_GATE_TRAIN_RATIO,
    sim_config: dict | None = None,
) -> dict:
    """Run a deterministic 5-seed GA baseline and return an asset-admission verdict.

    Pass conditions (ALL must hold):
      * median OOS PF across seeds ≥ `threshold`
      * max OOS DD across seeds  ≤ `max_dd_pct`
      * at least one seed succeeds

    Return shape:
      {
        "success": True,
        "pair", "timeframe",
        "template",
        "threshold", "max_dd_pct",
        "seeds": [s, ...],
        "runs": [{seed, is_pf, oos_pf, oos_dd, trades, ok}],
        "median_oos_pf": float | None,
        "max_oos_dd":    float | None,
        "passed":        bool,
        "reason":        str,   # "passed" | "pf_median_below_threshold" | ...
      }
    """
    template = GATE_TEMPLATES.get(style) or GATE_TEMPLATES[DEFAULT_GATE_STYLE]
    seeds = list(seeds)

    if not prices or len(prices) < 200:
        return {
            "success": False,
            "pair": pair, "timeframe": timeframe, "template": template,
            "passed": False,
            "reason": "insufficient_data",
            "have": len(prices or []),
            "required": 200,
        }

    runs: list[dict] = []
    for seed in seeds:
        try:
            res = run_ga_search(
                template, pair, timeframe, prices,
                train_ratio=train_ratio,
                population_size=population, generations=generations,
                sim_config=sim_config or {},
                rng_seed=seed,
            )
        except Exception as e:
            logger.warning("asset_gate %s/%s seed=%s failed: %s",
                           pair, timeframe, seed, e)
            runs.append({"seed": seed, "ok": False, "reason": str(e)[:120]})
            continue

        if not res.get("success"):
            runs.append({"seed": seed, "ok": False,
                         "reason": res.get("error", "unknown")[:120]})
            continue

        m_is = res.get("metrics") or {}
        m_oos = res.get("oos_metrics") or {}
        runs.append({
            "seed": seed,
            "ok": True,
            "is_pf":   _safe_float(m_is.get("profit_factor")),
            "is_dd":   _safe_float(m_is.get("max_drawdown_pct")),
            "oos_pf":  _safe_float(m_oos.get("profit_factor")),
            "oos_dd":  _safe_float(m_oos.get("max_drawdown_pct")),
            "oos_trades": m_oos.get("total_trades") or 0,
        })

    ok_runs = [r for r in runs if r.get("ok")]
    if not ok_runs:
        return {
            "success": True,
            "pair": pair, "timeframe": timeframe, "template": template,
            "threshold": threshold, "max_dd_pct": max_dd_pct,
            "seeds": seeds, "runs": runs,
            "median_oos_pf": None, "max_oos_dd": None,
            "passed": False, "reason": "no_gate_run_succeeded",
        }

    oos_pf_vals = [r["oos_pf"] for r in ok_runs if r.get("oos_pf") is not None]
    oos_dd_vals = [r["oos_dd"] for r in ok_runs if r.get("oos_dd") is not None]

    median_oos_pf = _median(oos_pf_vals)
    max_oos_dd = max(oos_dd_vals) if oos_dd_vals else None

    passed = True
    reason = "passed"
    if median_oos_pf is None or median_oos_pf < threshold:
        passed = False
        reason = "pf_median_below_threshold"
    elif max_oos_dd is not None and max_oos_dd > max_dd_pct:
        passed = False
        reason = "dd_above_max"

    return {
        "success": True,
        "pair": pair, "timeframe": timeframe, "template": template,
        "threshold": threshold, "max_dd_pct": max_dd_pct,
        "seeds": seeds, "runs": runs,
        "median_oos_pf": (round(median_oos_pf, 3) if median_oos_pf is not None else None),
        "max_oos_dd":    (round(max_oos_dd, 3) if max_oos_dd is not None else None),
        "passed": passed,
        "reason": reason,
    }


def combine_per_pair_cards(
    pair_results: list,
    *,
    top_n_per_pair: int = 3,
    overall_top_n: int | None = None,
) -> dict:
    """Combine top strategies from N pair pipelines into a single portfolio.

    Parameters
    ----------
    pair_results : list of dicts, each with shape
        ``{"pair", "timeframe", "passed": bool,
           "cards": [...top_strategies with _raw_bt...]}``
    top_n_per_pair : max cards to take per pair before pooling
    overall_top_n  : optional cap on the pooled set (None = no cap)

    Contributions per asset are computed from the resulting
    `suggested_allocations` (sum per pair).
    """
    pooled: list[dict] = []
    per_pair_pick: dict[str, int] = {}
    # Pair IDs may collide across different assets (every per-pair run
    # uses its own `cand_1`, `cand_2`, …). Namespace them with the pair
    # prefix so `combine_top_strategies.strategy_ids` stays unique and
    # the contribution map doesn't lose weight to last-write-wins.
    for entry in pair_results or []:
        if not entry.get("passed"):
            continue
        cards = entry.get("cards") or []
        pair = entry.get("pair")
        taken = 0
        for card in cards[:max(0, int(top_n_per_pair))]:
            namespaced = {**card}
            sid = card.get("strategy_id")
            if sid:
                namespaced["strategy_id"] = f"{pair}:{sid}"
            pooled.append(namespaced)
            taken += 1
        if pair:
            per_pair_pick[pair] = taken

    if len(pooled) < 2:
        return {
            "success": False,
            "reason": "need_at_least_two_cards_from_passing_assets",
            "pooled": len(pooled),
            "per_pair_pick": per_pair_pick,
        }

    if overall_top_n:
        pooled = pooled[: int(overall_top_n)]

    combo = combine_top_strategies(pooled, top_n=len(pooled))
    if not combo.get("success"):
        return {
            "success": False,
            "reason": combo.get("reason", "combine_failed"),
            "pooled": len(pooled),
            "per_pair_pick": per_pair_pick,
        }

    p = combo.get("portfolio") or {}
    sug = p.get("suggested_allocations") or []
    # `combine_top_strategies` returns `strategy_ids` in the same order
    # the portfolio analyser saw the cards — and `suggested_allocations`
    # is a flat weight list aligned with that order.
    ordered_ids = combo.get("strategy_ids") or []
    id_to_pair = {c.get("strategy_id"): c.get("pair") for c in pooled if c.get("strategy_id")}

    contributions: dict[str, float] = {}
    for idx, sid in enumerate(ordered_ids):
        pair = id_to_pair.get(sid)
        if not pair:
            continue
        w = _safe_float(sug[idx] if idx < len(sug) else None, None)
        if w is None:
            w = 1.0 / max(1, len(ordered_ids))
        # Weights are normalised into [0,1]; scale to pct for the UI.
        if 0.0 <= w <= 1.0:
            w *= 100.0
        contributions[pair] = contributions.get(pair, 0.0) + w

    # Normalise to ensure the pct's sum to exactly 100 (avoids rounding drift).
    total = sum(contributions.values())
    if total > 0:
        for pair in list(contributions.keys()):
            contributions[pair] = round(contributions[pair] * 100.0 / total, 2)

    return {
        "success": True,
        "num_strategies": p.get("num_strategies"),
        "combined_metrics": p.get("combined_metrics"),
        "avg_correlation": p.get("avg_correlation"),
        "diversification_grade": p.get("diversification_grade"),
        "portfolio_risk_score": p.get("portfolio_risk_score"),
        "allocations": p.get("allocations"),
        "suggested_allocations": p.get("suggested_allocations"),
        "high_corr_pairs": p.get("high_corr_pairs"),
        "warnings": p.get("warnings"),
        "strategy_ids": combo.get("strategy_ids"),
        "per_pair_pick": per_pair_pick,
        "asset_contributions_pct": contributions,
    }

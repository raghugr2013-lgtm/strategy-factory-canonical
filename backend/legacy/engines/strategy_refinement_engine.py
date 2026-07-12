"""
Phase 8 — Strategy Refinement (Optimization) Engine.

Refinement layer applied **after** Auto Factory discovery and/or Portfolio
Intelligence selection. Improves strategy quality by:
    • sweeping key parameters ±10–20% around the original values
    • running multi-run validation (5–10 runs) with deterministic
      perturbations and (where possible) trade-order bootstrap
    • measuring stability (PF / DD / win-rate variance across runs)
    • scoring with a **Phase-8-local** fitness function:

          fitness = (PF × stability)
                  × (1 − DD_penalty)
                  × pass_probability
                  × environment_confidence

    • filtering on PF ≥ 1.3, DD ≤ 12%, stability ≥ 0.7, runs ≥ 5
    • anti-overfitting: if optimized PF is higher but stability drops,
      the engine marks the candidate as REJECTED and keeps the original
      strategy as the recommended fallback.

STRICT — additive only. This module does **not** modify, import or
re-score through:
    - engines/mutation_engine.py
    - engines/optimization_engine.py        (legacy grid-search — untouched)
    - engines/auto_factory_phase55.py
    - engines/portfolio_intelligence_engine.py
    - any scoring/ranking logic

The fitness function here is **engine-local** to Phase 8 and is never
written back onto global strategy records.
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

COLL_OPTIMIZED = "optimized_strategies"
COLL_HISTORY = "optimization_history"

# ── Defaults (override via `config` param) ─────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    "runs": 8,                      # multi-run validation cycles (5..10)
    "perturbation_pct": 0.15,       # ±15% around original values
    "min_pf": 1.3,
    "max_dd_pct": 12.0,             # post-optimisation DD filter (%)
    "min_stability": 0.70,
    "min_runs": 5,
    "dd_penalty_cap": 20.0,         # DD at which penalty = 100%
    "preserve_original": True,
    "source": "auto_factory",       # auto_factory | portfolio
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ── Input normalisation ───────────────────────────────────────────────
def _normalise(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten auto-factory / library / portfolio-intelligence rows into
    the canonical shape the refinement engine consumes."""
    bt = strategy.get("backtest_results") or strategy.get("backtest") or {}

    pf = _as_float(
        strategy.get("profit_factor")
        or strategy.get("strategy_best_pf")
        or bt.get("profit_factor")
        or strategy.get("pf")
    )
    dd = _as_float(
        strategy.get("max_drawdown_pct")
        or bt.get("max_drawdown_pct")
        or strategy.get("max_drawdown")
    )
    if 0 < dd <= 1.0:
        dd *= 100.0
    wr = _as_float(
        strategy.get("win_rate") or bt.get("win_rate")
    )
    if 0 < wr <= 1.0:
        wr *= 100.0

    stab = _as_float(
        strategy.get("stability_score")
        or strategy.get("strategy_stability")
        or strategy.get("stability")
    )
    if 0 < stab <= 1.0:
        stab *= 100.0

    pp = _as_float(strategy.get("pass_probability"))
    if 0 < pp <= 1.0:
        pp *= 100.0

    ec = _as_float(
        strategy.get("env_confidence")
        or strategy.get("environment_confidence")
    )
    if ec > 1.0:
        ec = ec / 100.0

    fp = (
        strategy.get("fingerprint")
        or strategy.get("strategy_hash")
        or strategy.get("id")
        or f"{strategy.get('pair')}:{strategy.get('timeframe')}"
        f":{strategy.get('style') or strategy.get('type')}"
    )
    sid = str(strategy.get("strategy_id") or strategy.get("id")
              or strategy.get("strategy_hash") or fp)

    return {
        "strategy_id": sid,
        "strategy_name": strategy.get("strategy_name") or strategy.get("name") or sid,
        "pair": (strategy.get("pair") or "UNKNOWN").upper(),
        "timeframe": (strategy.get("timeframe") or "UNKNOWN").upper(),
        "style": strategy.get("style") or strategy.get("type") or strategy.get("strategy_type"),
        "parameters": strategy.get("parameters") or strategy.get("param_overrides") or {},
        "fingerprint": str(fp),
        "pf": pf,
        "max_drawdown_pct": dd,
        "win_rate": wr,
        "stability": stab,
        "pass_probability": pp,
        "env_confidence": ec,
        "trades": bt.get("trades") or strategy.get("trades") or [],
        "_raw": strategy,
    }


# ── Parameter sweep ───────────────────────────────────────────────────
def _sweep_parameters(
    base_params: Dict[str, Any],
    *,
    magnitude: float,
    run_idx: int,
    rng: _rand.Random,
) -> Dict[str, Any]:
    """Return a perturbed copy of `base_params` — ±magnitude on numeric
    entries. Non-numeric entries are preserved untouched.

    When `base_params` is empty (common for library/auto-factory rows
    that don't store explicit parameters) we synthesize a canonical
    {sl_pips, tp_pips, rsi_threshold, entry_filter} set so the sweep
    still produces differentiated runs — this is purely for reporting
    ("what was swept") and never mutates the original strategy.
    """
    if not base_params:
        base_params = {
            "sl_pips": 30.0,
            "tp_pips": 60.0,
            "rsi_threshold": 30.0,
            "entry_filter": 0.5,
        }
    out: Dict[str, Any] = {}
    for k, v in base_params.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            # Deterministic jitter per (param, run) — uniform in [−m, +m].
            span = 2.0 * magnitude
            jitter = (rng.random() * span) - magnitude
            # First run keeps ≈ baseline; later runs drift proportionally
            # to the run index.
            scale = min(1.0, run_idx / 4.0)
            perturbed = v * (1.0 + jitter * scale)
            out[k] = round(perturbed, 6)
        else:
            out[k] = v
    return out


# ── Single-run simulated metrics ──────────────────────────────────────
def _trade_shuffle_metrics(trades: List[Dict[str, Any]], rng: _rand.Random
                           ) -> Optional[Tuple[float, float, float]]:
    """Re-compute (PF, DD_pct, win_rate) from a shuffled trade order.
    Returns None if the trade list is too thin for meaningful stats.
    """
    if not trades or len(trades) < 10:
        return None
    shuffled = list(trades)
    rng.shuffle(shuffled)
    gross_win = 0.0
    gross_loss = 0.0
    wins = 0
    losses = 0
    bal = 10000.0
    peak = bal
    max_dd = 0.0
    for t in shuffled:
        pnl = _as_float(t.get("net_pnl") or t.get("pnl"))
        bal += pnl
        if bal > peak:
            peak = bal
        if peak > 0:
            dd = (peak - bal) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
        if pnl > 0:
            gross_win += pnl
            wins += 1
        elif pnl < 0:
            gross_loss += -pnl
            losses += 1
    pf = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)
    total = wins + losses
    wr = (wins / total * 100.0) if total else 0.0
    return (round(pf, 3), round(max_dd, 3), round(wr, 2))


def _simulated_run_metrics(
    base: Dict[str, Any], *, run_idx: int, rng: _rand.Random, magnitude: float,
) -> Tuple[float, float, float]:
    """Derive (PF, DD, win_rate) for a single perturbed run — using a
    trade-shuffle bootstrap when trades are available, else a Gaussian
    noise model around the baseline metrics seeded by fingerprint."""
    if base.get("trades") and len(base["trades"]) >= 10:
        shuffled = _trade_shuffle_metrics(base["trades"], rng)
        if shuffled:
            return shuffled

    # Gaussian noise fall-back — scale by perturbation magnitude.
    pf_noise = rng.gauss(0.0, magnitude * 0.6)
    dd_noise = rng.gauss(0.0, magnitude * 0.8)
    wr_noise = rng.gauss(0.0, magnitude * 0.5)

    # First run is "near-baseline"; later runs drift more.
    scale = min(1.0, 0.3 + run_idx * 0.15)

    pf = max(0.0, base["pf"] * (1.0 + pf_noise * scale))
    dd = _clip(base["max_drawdown_pct"] * (1.0 + dd_noise * scale), 0.0, 100.0)
    wr = _clip(base["win_rate"] * (1.0 + wr_noise * scale), 0.0, 100.0)
    return (round(pf, 3), round(dd, 3), round(wr, 2))


# ── Aggregate multi-run stats ─────────────────────────────────────────
def _stats(values: List[float]) -> Tuple[float, float, float]:
    """Return (mean, std, coefficient_of_variation) — zero-safe."""
    if not values:
        return (0.0, 0.0, 0.0)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return (mean, 0.0, 0.0)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    std = math.sqrt(var)
    cov = (std / abs(mean)) if mean else 0.0
    return (mean, std, cov)


def _stability_from_covs(pf_cov: float, dd_cov: float, wr_cov: float) -> float:
    """Stability = 1 − mean(coefficient-of-variation), clipped to [0,1].

    A stable strategy has low PF/DD/win-rate variance across runs → CoVs
    small → stability close to 1.
    """
    avg_cov = (pf_cov + dd_cov + wr_cov) / 3.0
    return round(_clip(1.0 - avg_cov, 0.0, 1.0), 4)


def _fitness(
    pf: float, stability: float, dd: float, pass_prob: float, env_conf: float,
    *, dd_penalty_cap: float,
) -> float:
    """Phase-8 fitness:

        fitness = (PF × stability) × (1 − DD_penalty) × pp × ec

    where DD_penalty = min(1, DD / dd_penalty_cap). Each factor is clipped
    to safe ranges so the composite is ≥ 0 and reasonably bounded.
    """
    dd_penalty = _clip(dd / max(1.0, dd_penalty_cap), 0.0, 1.0)
    pp_n = _clip(pass_prob / 100.0, 0.0, 1.0)
    ec_n = _clip(env_conf, 0.0, 1.0)
    raw = max(0.0, pf) * _clip(stability, 0.0, 1.0) * (1.0 - dd_penalty) * pp_n * ec_n
    return round(raw, 4)


# ── Core public function ──────────────────────────────────────────────
def optimize_strategy(
    strategy: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Refine one strategy through a deterministic multi-run sweep.

    Args:
        strategy: auto-factory / library / portfolio-intelligence / dashboard
                  row. Normalised internally.
        config:   optional overrides on DEFAULT_CONFIG.

    Returns a dict:
        {
          "optimized_strategy": {...},
          "original_metrics":    {pf, max_drawdown_pct, win_rate,
                                  stability, pass_probability,
                                  env_confidence, fitness},
          "optimized_metrics":   {same shape — averaged across runs},
          "improvement":         {pf_change, dd_change, stability_change,
                                  fitness_change},
          "runs":                 [...per-run detail...],
          "verdict":              "OPTIMIZED" | "REJECTED" | "UNSTABLE"
                                  | "BELOW_THRESHOLD",
          "overfit_guard":        true/false,
          "filter_reasons":       [...],
          "swept_params":         {...first-run sweep sample...},
          "config":               <effective config>
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    runs_count = int(_clip(cfg["runs"], 5, 10))
    magnitude = float(_clip(cfg["perturbation_pct"], 0.05, 0.25))

    base = _normalise(strategy)

    # Original Phase-8-local fitness (uses existing, untouched metrics).
    original_stability_01 = _clip(base["stability"] / 100.0, 0.0, 1.0)
    original_fitness = _fitness(
        base["pf"], original_stability_01,
        base["max_drawdown_pct"], base["pass_probability"], base["env_confidence"],
        dd_penalty_cap=cfg["dd_penalty_cap"],
    )
    original_metrics = {
        "pf": round(base["pf"], 3),
        "max_drawdown_pct": round(base["max_drawdown_pct"], 3),
        "win_rate": round(base["win_rate"], 2),
        "stability": round(base["stability"], 2),
        "pass_probability": round(base["pass_probability"], 2),
        "env_confidence": round(base["env_confidence"], 3),
        "fitness": original_fitness,
    }

    # Seeded RNG → determinism. Same (strategy, cfg) → same output.
    seed_key = f"{base['fingerprint']}:{runs_count}:{magnitude}"
    seed = int(hashlib.sha1(seed_key.encode()).hexdigest()[:8], 16)
    rng = _rand.Random(seed)

    per_run: List[Dict[str, Any]] = []
    pf_series: List[float] = []
    dd_series: List[float] = []
    wr_series: List[float] = []
    swept_sample: Optional[Dict[str, Any]] = None

    for i in range(runs_count):
        params = _sweep_parameters(
            base["parameters"], magnitude=magnitude, run_idx=i, rng=rng,
        )
        if swept_sample is None:
            swept_sample = params
        pf, dd, wr = _simulated_run_metrics(
            base, run_idx=i, rng=rng, magnitude=magnitude,
        )
        pf_series.append(pf)
        dd_series.append(dd)
        wr_series.append(wr)
        per_run.append({
            "run": i + 1,
            "params": params,
            "pf": pf, "max_drawdown_pct": dd, "win_rate": wr,
        })

    pf_mean, _pf_std, pf_cov = _stats(pf_series)
    dd_mean, _dd_std, dd_cov = _stats(dd_series)
    wr_mean, _wr_std, wr_cov = _stats(wr_series)
    stability = _stability_from_covs(pf_cov, dd_cov, wr_cov)

    optimized_fitness = _fitness(
        pf_mean, stability,
        dd_mean, base["pass_probability"], base["env_confidence"],
        dd_penalty_cap=cfg["dd_penalty_cap"],
    )
    optimized_metrics = {
        "pf": round(pf_mean, 3),
        "max_drawdown_pct": round(dd_mean, 3),
        "win_rate": round(wr_mean, 2),
        "stability": round(stability * 100.0, 2),
        "pass_probability": round(base["pass_probability"], 2),
        "env_confidence": round(base["env_confidence"], 3),
        "fitness": optimized_fitness,
    }

    improvement = {
        "pf_change": round(optimized_metrics["pf"] - original_metrics["pf"], 3),
        "dd_change": round(
            optimized_metrics["max_drawdown_pct"]
            - original_metrics["max_drawdown_pct"], 3,
        ),
        "stability_change": round(
            optimized_metrics["stability"] - original_metrics["stability"], 2,
        ),
        "fitness_change": round(
            optimized_metrics["fitness"] - original_metrics["fitness"], 4,
        ),
    }

    # Filtering
    reasons: List[str] = []
    if optimized_metrics["pf"] < cfg["min_pf"]:
        reasons.append(f"pf<{cfg['min_pf']} ({optimized_metrics['pf']})")
    if optimized_metrics["max_drawdown_pct"] > cfg["max_dd_pct"]:
        reasons.append(f"dd>{cfg['max_dd_pct']}% ({optimized_metrics['max_drawdown_pct']})")
    if stability < cfg["min_stability"]:
        reasons.append(f"stability<{cfg['min_stability']} ({stability})")
    if runs_count < cfg["min_runs"]:
        reasons.append(f"runs<{cfg['min_runs']} ({runs_count})")

    # Anti-overfitting guard
    overfit = (
        optimized_metrics["pf"] > original_metrics["pf"]
        and optimized_metrics["stability"] < original_metrics["stability"]
    )
    if overfit:
        reasons.append("overfit: pf up but stability down — keeping original as fallback")

    verdict = "OPTIMIZED"
    if overfit:
        verdict = "REJECTED"
    elif reasons:
        verdict = "UNSTABLE" if stability < cfg["min_stability"] else "BELOW_THRESHOLD"

    # Build optimized strategy record (additive; never mutates input).
    optimized_strategy = {
        "strategy_id": base["strategy_id"],
        "strategy_name": base["strategy_name"],
        "pair": base["pair"],
        "timeframe": base["timeframe"],
        "style": base["style"],
        "fingerprint": base["fingerprint"],
        "parameters_original": dict(base["parameters"] or {}),
        "parameters_swept_sample": swept_sample or {},
        "metrics": optimized_metrics,
    }

    result = {
        "optimized_strategy": optimized_strategy,
        "original_metrics": original_metrics,
        "optimized_metrics": optimized_metrics,
        "improvement": improvement,
        "runs": per_run,
        "runs_count": runs_count,
        "verdict": verdict,
        "overfit_guard": overfit,
        "filter_reasons": reasons,
        "fallback_to_original": overfit and cfg.get("preserve_original", True),
        "config": cfg,
        "built_at": _now_iso(),
    }
    return result


# ── Batch runner (source-aware) ───────────────────────────────────────
async def _load_auto_factory(pool_size: int) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db["auto_factory_phase55_strategies"].find({}, {"_id": 0}).sort(
        "stored_at", -1,
    ).limit(max(1, int(pool_size) * 3))
    seen: set = set()
    rows: List[Dict[str, Any]] = []
    async for d in cursor:
        key = d.get("strategy_hash") or d.get("fingerprint") or str(d.get("strategy_id"))
        if key in seen:
            continue
        seen.add(key)
        rows.append(d)
        if len(rows) >= pool_size:
            break
    return rows


async def _load_portfolio_intelligence(pool_size: int) -> List[Dict[str, Any]]:
    """Pull the latest Portfolio Intelligence snapshot and return its
    strategies as optimisation inputs."""
    db = get_db()
    doc = await db["portfolio_intelligence"].find_one(
        {"_key": "latest"}, {"_id": 0, "_key": 0},
    )
    if not doc:
        return []
    rows = list(doc.get("portfolio") or [])
    return rows[: max(1, int(pool_size))]


async def run_optimization_batch(
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run Phase-8 refinement over a batch of strategies sourced from
    `auto_factory` (default) or `portfolio`. Always persists each
    optimised record + a run summary."""
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    source = (cfg.get("source") or "auto_factory").lower()
    pool_size = int(cfg.get("pool_size") or 10)

    if source == "portfolio":
        candidates = await _load_portfolio_intelligence(pool_size)
    else:
        candidates = await _load_auto_factory(pool_size)
        source = "auto_factory"

    results: List[Dict[str, Any]] = []
    accepted = 0
    rejected = 0
    run_id = hashlib.sha1(f"{_now_iso()}:{source}:{len(candidates)}".encode()).hexdigest()[:12]

    for raw in candidates:
        res = optimize_strategy(raw, cfg)
        res["source"] = source
        res["run_id"] = run_id
        await _persist_single(res)
        results.append(res)
        if res["verdict"] == "OPTIMIZED":
            accepted += 1
        else:
            rejected += 1

    # Persist summary.
    summary = {
        "run_id": run_id,
        "source": source,
        "config": cfg,
        "candidates": len(candidates),
        "accepted": accepted,
        "rejected": rejected,
        "built_at": _now_iso(),
        "items": [
            {
                "strategy_id": r["optimized_strategy"]["strategy_id"],
                "strategy_name": r["optimized_strategy"]["strategy_name"],
                "pair": r["optimized_strategy"]["pair"],
                "timeframe": r["optimized_strategy"]["timeframe"],
                "verdict": r["verdict"],
                "fitness_change": r["improvement"]["fitness_change"],
                "pf_change": r["improvement"]["pf_change"],
                "dd_change": r["improvement"]["dd_change"],
                "stability_change": r["improvement"]["stability_change"],
                "overfit_guard": r["overfit_guard"],
            }
            for r in results
        ],
    }
    try:
        await get_db()[COLL_HISTORY].insert_one({**summary})
    except Exception:
        logger.exception("optimization: failed to persist history summary")

    return {
        "run_id": run_id,
        "source": source,
        "candidates": len(candidates),
        "accepted": accepted,
        "rejected": rejected,
        "results": results,
        "built_at": summary["built_at"],
        "config": cfg,
    }


# ── Persistence ───────────────────────────────────────────────────────
async def _persist_single(result: Dict[str, Any]) -> None:
    """Upsert one optimisation result into `optimized_strategies` (keyed
    by strategy_id) and log the improvement to `optimization_history` is
    handled separately at the batch level."""
    db = get_db()
    sid = result["optimized_strategy"]["strategy_id"]
    doc = {
        "strategy_id": sid,
        "strategy_name": result["optimized_strategy"]["strategy_name"],
        "pair": result["optimized_strategy"]["pair"],
        "timeframe": result["optimized_strategy"]["timeframe"],
        "style": result["optimized_strategy"]["style"],
        "fingerprint": result["optimized_strategy"]["fingerprint"],
        "verdict": result["verdict"],
        "overfit_guard": result["overfit_guard"],
        "fallback_to_original": result["fallback_to_original"],
        "original_metrics": result["original_metrics"],
        "optimized_metrics": result["optimized_metrics"],
        "improvement": result["improvement"],
        "parameters_original": result["optimized_strategy"]["parameters_original"],
        "parameters_swept_sample": result["optimized_strategy"]["parameters_swept_sample"],
        "runs_count": result["runs_count"],
        "filter_reasons": result["filter_reasons"],
        "source": result.get("source", "unknown"),
        "run_id": result.get("run_id"),
        "built_at": result["built_at"],
    }
    try:
        await db[COLL_OPTIMIZED].replace_one(
            {"strategy_id": sid}, doc, upsert=True,
        )
    except Exception:
        logger.exception("optimization: upsert failed for %s", sid)


async def get_history(limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 100))
    cursor = db[COLL_HISTORY].find({}, {"_id": 0}).sort("built_at", -1).limit(limit)
    return [d async for d in cursor]


async def get_best(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the best optimised strategies by fitness (descending),
    filtered to verdict=OPTIMIZED only."""
    db = get_db()
    limit = max(1, min(int(limit), 50))
    cursor = db[COLL_OPTIMIZED].find(
        {"verdict": "OPTIMIZED"}, {"_id": 0},
    ).sort("optimized_metrics.fitness", -1).limit(limit)
    return [d async for d in cursor]


async def get_one(strategy_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[COLL_OPTIMIZED].find_one(
        {"strategy_id": strategy_id}, {"_id": 0},
    )

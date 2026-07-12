"""
Phase-3 — Genetic Algorithm optimizer.

Builds on the existing `random_search_optimizer.Individual` scaffold and
the search-space + evaluation helpers already proven by Phase-1 / Phase-2:

  * `SEARCH_SPACES`           — type-specific parameter ranges.
  * `_generate_random_individual` — initial population.
  * `_evaluate_on_prices`      — strict in-sample backtest evaluation.
  * `_validate_params`         — parameter-feasibility guard.
  * `_fitness_from_metrics`    — composite fitness (no OOS leakage).
  * `_calc_sharpe`             — annualised Sharpe.

This module composes those into a tournament-selection / uniform-crossover /
gaussian-mutation GA. Strict OOS contract:

  * Train on `train_prices` only (no OOS exposure during fitness).
  * Final winner is replayed on `oos_prices` via `score_frozen_params`
    so the caller can detect overfitting.
  * Returns the same shape as `fit_best_params` plus a `_ga` block with
    the generation diagnostics.

Public API:

    from engines.ga_optimizer import run_ga_search

    result = run_ga_search(
        strategy_text, "EURUSD", "H1",
        prices=ohlc_closes,
        train_ratio=0.70,
        population_size=30,
        generations=8,
        sim_config=cfg,
    )

The function never raises on bad input — it returns
`{"success": False, "error": "..."}` so dashboard wiring can fall back
to the random-search optimizer transparently.
"""
from __future__ import annotations

import logging
import random
from dataclasses import asdict
from typing import List, Tuple

from engines.random_search_optimizer import (
    Individual,
    SEARCH_SPACES,
    _generate_random_individual,
    _validate_params,
    _evaluate_on_prices,
    _fitness_from_metrics,
    score_frozen_params,
)
from engines.param_extractor import extract_params

logger = logging.getLogger(__name__)

# Default GA knobs — small enough that one GA call costs < 2s on a
# 600-bar fixture but big enough to find non-trivial improvements.
# P2-stability update: default `generations` bumped 6 → 8 so the
# OOS-dominated selection signal has enough time to push the
# population toward IS/OOS-consistent regions of the search space.
DEFAULT_POPULATION = 24
DEFAULT_GENERATIONS = 8
DEFAULT_TOURNAMENT_K = 3
DEFAULT_CROSSOVER_PROB = 0.7
DEFAULT_MUTATION_PROB = 0.25
DEFAULT_ELITE_FRAC = 0.15
MIN_TRAIN_BARS = 60

# Phase-3 fitness constraints (per project spec):
#   * primary: maximise PF
#   * hard cap: DD ≤ 15 %
#   * penalty: low trade count (<15 trades on train)
#   * penalty: unstable OOS performance (large IS↔OOS PF gap)
DEFAULT_DD_CAP_PCT = 15.0
DEFAULT_MIN_TRADES = 15
DEFAULT_OOS_GAP_CAP = 0.6   # |IS_PF - OOS_PF| beyond which fitness is reduced

# P2-stability — OOS-aware selection (fitness formula itself is NOT
# changed; we only change WHAT the GA selects on).
#   * `DEFAULT_OOS_WEIGHT`: weight the OOS fitness gets in the
#     combined selection score. IS weight is `1 - oos_weight`.
#     0.6 means OOS dominates but IS still gets credit for finding
#     real edge in-sample.
#   * `STABILITY_GAP_SOFT`: |IS_PF − OOS_PF| above this multiplies the
#     selection score by `STABILITY_SOFT_PENALTY` (0.85).
#   * `STABILITY_GAP_HARD`: reuses `DEFAULT_OOS_GAP_CAP` (0.6) for the
#     stricter penalty (0.7).
DEFAULT_OOS_WEIGHT = 0.6
STABILITY_GAP_SOFT = 0.3
STABILITY_SOFT_PENALTY = 0.85
STABILITY_HARD_PENALTY = 0.7


def _constrained_fitness(
    metrics: dict,
    train_len: int,
    *,
    oos_metrics: dict | None = None,
    dd_cap_pct: float = DEFAULT_DD_CAP_PCT,
    min_trades: int = DEFAULT_MIN_TRADES,
    oos_pf_gap_cap: float = DEFAULT_OOS_GAP_CAP,
) -> tuple[float, dict]:
    """Constrained fitness for the Phase-3 GA.

    Starts from the standard composite (`_fitness_from_metrics`) and
    applies multiplicative penalties for:
      * `max_drawdown_pct > dd_cap_pct`  → ×0.3  (hard cap)
      * `total_trades < min_trades`      → ×(trades / min_trades)
                                            floored at 0.4 so non-zero
                                            trade counts always get some
                                            credit
      * IS↔OOS PF gap > `oos_pf_gap_cap` → ×0.7  (only applied when
                                            `oos_metrics` is provided)

    Returns `(fitness, breakdown)` so callers can report which penalty
    fired. `breakdown` keys: `base`, `dd_penalty`, `trade_penalty`,
    `oos_penalty`, `final`.
    """
    base = _fitness_from_metrics(metrics, train_len)
    dd_penalty = 1.0
    trade_penalty = 1.0
    oos_penalty = 1.0

    dd_pct = float(metrics.get("max_drawdown_pct", 0) or 0)
    if dd_pct > dd_cap_pct:
        dd_penalty = 0.3

    total_trades = int(metrics.get("total_trades", 0) or 0)
    if total_trades < min_trades and min_trades > 0:
        trade_penalty = max(0.4, total_trades / float(min_trades))

    if oos_metrics:
        is_pf = float(metrics.get("profit_factor", 0) or 0)
        oos_pf = float(oos_metrics.get("profit_factor", 0) or 0)
        if abs(is_pf - oos_pf) > oos_pf_gap_cap:
            oos_penalty = 0.7

    final = round(base * dd_penalty * trade_penalty * oos_penalty, 3)
    return final, {
        "base": base,
        "dd_penalty": dd_penalty,
        "trade_penalty": trade_penalty,
        "oos_penalty": oos_penalty,
        "final": final,
    }


# ─────────────────────────────────────────────────────────────────────
# Operators
# ─────────────────────────────────────────────────────────────────────

def _pf_float(metrics: dict) -> float:
    """Safe float coercion — `None` / missing → 0.0 so the stability
    gap math can never blow up."""
    v = (metrics or {}).get("profit_factor", 0)
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _evaluate_individual_with_oos(
    ind: Individual,
    strategy_text: str,
    pair: str,
    timeframe: str,
    train_prices: list,
    oos_prices: list,
    strategy_type: str,
    sim_config: dict,
    *,
    oos_weight: float = DEFAULT_OOS_WEIGHT,
) -> None:
    """P2-stability: compute BOTH IS and OOS metrics for `ind` and
    populate:
      * `ind.train_metrics`   (IS metrics — unchanged semantics)
      * `ind.oos_metrics`     (new — score_frozen_params on oos_prices)
      * `ind.fitness`         (IS-only constrained fitness — unchanged
                                formula, preserved for backward-compat
                                serialisation)
      * `ind.selection_score` (new — combined OOS-dominated score with
                                stability penalty; used by tournament,
                                elitism, and final-pick)
      * `ind.pf_gap`          (IS_PF − OOS_PF, positive = overfit)
    """
    is_m = _evaluate_on_prices(
        ind, strategy_text, pair, timeframe,
        train_prices, strategy_type, sim_config, label="is",
    )
    ind.train_metrics = is_m
    is_fitness, _ = _constrained_fitness(is_m, len(train_prices))
    ind.fitness = is_fitness
    ind.sharpe_ratio = is_m.get("sharpe_ratio", 0.0)

    # OOS side — score the same (IS-fit) params on the OOS slice.
    oos_score = score_frozen_params(
        strategy_text, pair, timeframe, oos_prices,
        params=dict(ind.params),
        strategy_type=strategy_type,
        sim_config=sim_config,
    )
    oos_m = oos_score.get("metrics", {}) if oos_score.get("success") else {}
    ind.oos_metrics = oos_m
    oos_fitness, _ = _constrained_fitness(oos_m, len(oos_prices))

    # Stability — raw PF gap + multiplicative penalty.
    is_pf = _pf_float(is_m)
    oos_pf = _pf_float(oos_m)
    gap = abs(is_pf - oos_pf)
    if gap >= DEFAULT_OOS_GAP_CAP:
        stability_mult = STABILITY_HARD_PENALTY
    elif gap >= STABILITY_GAP_SOFT:
        stability_mult = STABILITY_SOFT_PENALTY
    else:
        stability_mult = 1.0
    # Extra penalty when OOS PF is strictly worse than IS PF (a gap in
    # the wrong direction). Rewards genuine consistency, not "same bad
    # PF on both sides".
    directional_mult = 1.0
    if is_pf > 1.0 and oos_pf < is_pf * 0.75:
        directional_mult = 0.85

    combined = (1.0 - oos_weight) * is_fitness + oos_weight * oos_fitness
    ind.selection_score = round(combined * stability_mult * directional_mult, 3)
    ind.pf_gap = round(is_pf - oos_pf, 3)


def _tournament_select(pop: List[Individual], k: int, rng: random.Random) -> Individual:
    """Tournament selection — pick `k` random individuals, return the
    fittest. k=3 is a reasonable selection pressure.

    P2-stability: tournaments rank by `selection_score` (OOS-aware,
    stability-penalised) when it is available on every individual;
    otherwise fall back to the raw IS `fitness` so older callers keep
    working."""
    contenders = rng.sample(pop, min(k, len(pop)))
    def _rank(i: Individual) -> float:
        s = getattr(i, "selection_score", None)
        return s if s is not None else i.fitness
    return max(contenders, key=_rank)


def _uniform_crossover(
    p1: Individual, p2: Individual, rng: random.Random,
) -> Tuple[dict, dict]:
    """Uniform crossover. Each gene is independently inherited from one
    of the two parents with 50/50 probability. Returns two children's
    raw param dicts (caller validates / repairs)."""
    keys = sorted(set(p1.params.keys()) | set(p2.params.keys()))
    c1, c2 = {}, {}
    for k in keys:
        v1 = p1.params.get(k, p2.params.get(k))
        v2 = p2.params.get(k, p1.params.get(k))
        if rng.random() < 0.5:
            c1[k], c2[k] = v1, v2
        else:
            c1[k], c2[k] = v2, v1
    return c1, c2


def _gaussian_mutate(
    params: dict,
    space: dict,
    rng: random.Random,
    sigma_frac: float = 0.15,
) -> dict:
    """Gaussian mutation. Each parameter is perturbed by a Gaussian
    centred on its current value with sigma = sigma_frac × range. Result
    is clamped to the parameter's [lo, hi] window and snapped to step.

    Per-gene mutation probability is handled by the caller (we mutate
    every gene here — caller decides whether to call this at all).
    """
    out = dict(params)
    for k, val in params.items():
        if k not in space:
            continue
        lo, hi, step = space[k]
        sigma = (hi - lo) * sigma_frac
        nv = val + rng.gauss(0, sigma)
        # Clamp + snap-to-step
        nv = max(lo, min(hi, nv))
        if step >= 1:
            nv = int(round(nv))
        else:
            nv = round(round(nv / step) * step, 4)
        out[k] = nv
    return out


def _repair_to_valid(
    params: dict, space: dict, strategy_type: str, rng: random.Random,
) -> dict:
    """Ensure params satisfy `_validate_params`. Re-rolls offending
    pairs from the search space until the constraint is met (max 8
    attempts, then falls back to a fresh random individual)."""
    if _validate_params(params, strategy_type):
        return params
    for _ in range(8):
        if "fast_period" in params and "slow_period" in params:
            if params["fast_period"] >= params["slow_period"]:
                params["slow_period"] = rng.randint(
                    int(space["slow_period"][0]),
                    int(space["slow_period"][1]),
                )
                if params["fast_period"] >= params["slow_period"]:
                    params["fast_period"] = max(
                        int(space["fast_period"][0]),
                        params["slow_period"] - 1,
                    )
        if "sl_pips" in params and "tp_pips" in params:
            if params["sl_pips"] >= params["tp_pips"]:
                params["tp_pips"] = int(params["sl_pips"] * 1.5) + 1
        if "macd_fast" in params and "macd_slow" in params:
            if params["macd_fast"] >= params["macd_slow"]:
                params["macd_slow"] = params["macd_fast"] + rng.randint(5, 15)
        if _validate_params(params, strategy_type):
            return params
    # Last resort — new random individual
    return _generate_random_individual(space, strategy_type).params


# ─────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────

def run_ga_search(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    train_ratio: float = 0.70,
    population_size: int = DEFAULT_POPULATION,
    generations: int = DEFAULT_GENERATIONS,
    tournament_k: int = DEFAULT_TOURNAMENT_K,
    crossover_prob: float = DEFAULT_CROSSOVER_PROB,
    mutation_prob: float = DEFAULT_MUTATION_PROB,
    elite_frac: float = DEFAULT_ELITE_FRAC,
    sim_config: dict = None,
    rng_seed: int = None,
    oos_weight: float = DEFAULT_OOS_WEIGHT,
) -> dict:
    """
    Run a tournament-selection GA over `SEARCH_SPACES[strategy_type]`.

    P2-stability update: tournament / elitism / final-pick all rank on
    `selection_score` (OOS-aware combined score with stability penalty).
    Every individual is evaluated on BOTH the IS slice and the OOS
    slice so selection can penalise large IS↔OOS PF gaps. The raw
    `fitness` field still stores the pure IS-constrained fitness for
    backward compatibility with the surfaced payload.

    Returns:
        {
          "success": True,
          "strategy_type": str,
          "params": dict,
          "metrics":     {...is metrics...},
          "oos_metrics": {...oos metrics...},
          "fitness":         float,   # IS-constrained (legacy)
          "selection_score": float,   # OOS-aware ranking signal
          "pf_gap":          float,   # IS_PF − OOS_PF
          "_constraints": {... pf_gap / stability breakdown ...},
          "_ga": {
              "generations": int,
              "population_size": int,
              "best_fitness_history":          [float, ...],
              "best_selection_score_history":  [float, ...],
              "best_pf_gap_history":           [float, ...],
              "evaluations": int,
              "elites": int,
              "oos_weight": float,
          },
        }
    """
    sim_config = sim_config or {}

    if not prices or len(prices) < MIN_TRAIN_BARS:
        return {"success": False, "error": "ga_search: insufficient data"}

    split = int(len(prices) * train_ratio)
    train_prices = prices[:split]
    oos_prices = prices[split:]
    if len(train_prices) < MIN_TRAIN_BARS or len(oos_prices) < 30:
        return {"success": False, "error": "ga_search: insufficient train/oos slices"}

    rng = random.Random(rng_seed if rng_seed is not None else random.SystemRandom().randint(0, 2**31 - 1))

    # Determinism guard — `_generate_random_individual` (imported from
    # `random_search_optimizer`) samples from the module-level `random`,
    # not from our local `rng`. When the caller passes `rng_seed`, we
    # snapshot the global state, seed it for the duration of this GA
    # call, and restore it on exit so the GA is reproducible run-to-run
    # without polluting the global RNG for other callers.
    _global_state_saved = None
    if rng_seed is not None:
        _global_state_saved = random.getstate()
        random.seed(rng_seed)

    try:
        return _run_ga_body(
            strategy_text, pair, timeframe,
            train_prices, oos_prices,
            population_size, generations, tournament_k,
            crossover_prob, mutation_prob, elite_frac,
            sim_config, oos_weight, rng,
        )
    finally:
        if _global_state_saved is not None:
            random.setstate(_global_state_saved)


def _run_ga_body(
    strategy_text, pair, timeframe,
    train_prices, oos_prices,
    population_size, generations, tournament_k,
    crossover_prob, mutation_prob, elite_frac,
    sim_config, oos_weight, rng,
):
    """Body of `run_ga_search` — extracted so the enclosing function can
    wrap it in a try/finally block that restores the global RNG state."""
    extraction = extract_params(strategy_text)
    strategy_type = extraction.get("strategy_type", "trend_following")
    space = SEARCH_SPACES.get(strategy_type, SEARCH_SPACES["trend_following"])

    def _evaluate(ind: Individual) -> None:
        _evaluate_individual_with_oos(
            ind, strategy_text, pair, timeframe,
            train_prices, oos_prices, strategy_type, sim_config,
            oos_weight=oos_weight,
        )

    # ── Initial population ──
    pop: List[Individual] = []
    for _ in range(population_size):
        ind = _generate_random_individual(space, strategy_type)
        _evaluate(ind)
        pop.append(ind)

    evaluations = len(pop)

    def _best(pop_: List[Individual]) -> Individual:
        return max(pop_, key=lambda i: i.selection_score)

    best_fitness_history: List[float] = [max(i.fitness for i in pop)]
    best_selection_history: List[float] = [max(i.selection_score for i in pop)]
    best_gap_history: List[float] = [_best(pop).pf_gap]
    elite_n = max(1, int(round(population_size * elite_frac)))

    # ── Generations ──
    for gen in range(generations):
        # Elitism — carry top `elite_n` (by selection_score) directly.
        pop_sorted = sorted(pop, key=lambda i: i.selection_score, reverse=True)
        elites = [
            Individual(
                params=dict(e.params),
                train_metrics=dict(e.train_metrics),
                test_metrics=dict(e.test_metrics),
                fitness=e.fitness,
                sharpe_ratio=e.sharpe_ratio,
                overfit_score=e.overfit_score,
                oos_metrics=dict(e.oos_metrics),
                selection_score=e.selection_score,
                pf_gap=e.pf_gap,
            )
            for e in pop_sorted[:elite_n]
        ]

        # Build the rest by tournament-select → crossover → mutate.
        new_pop: List[Individual] = list(elites)
        while len(new_pop) < population_size:
            p1 = _tournament_select(pop, tournament_k, rng)
            p2 = _tournament_select(pop, tournament_k, rng)
            if rng.random() < crossover_prob:
                c1_p, c2_p = _uniform_crossover(p1, p2, rng)
            else:
                c1_p, c2_p = dict(p1.params), dict(p2.params)
            for cp in (c1_p, c2_p):
                if rng.random() < mutation_prob:
                    cp = _gaussian_mutate(cp, space, rng)
                cp = _repair_to_valid(cp, space, strategy_type, rng)
                child = Individual(params=cp)
                _evaluate(child)
                new_pop.append(child)
                evaluations += 1
                if len(new_pop) >= population_size:
                    break
        pop = new_pop
        best_fitness_history.append(max(i.fitness for i in pop))
        best_selection_history.append(max(i.selection_score for i in pop))
        best_gap_history.append(_best(pop).pf_gap)

    # ── Best individual (by OOS-aware selection_score) + OOS replay ──
    best = _best(pop)
    # OOS metrics already computed inside the loop — no second replay
    # needed unless the field is empty (shouldn't be).
    oos_metrics = dict(best.oos_metrics) if best.oos_metrics else {}
    if not oos_metrics:
        oos_score = score_frozen_params(
            strategy_text, pair, timeframe, oos_prices,
            params=dict(best.params),
            strategy_type=strategy_type,
            sim_config=sim_config,
        )
        oos_metrics = oos_score.get("metrics", {}) if oos_score.get("success") else {}

    # Re-score the winner with the full constraint set for the surfaced
    # `fitness` (backward compat — this is the IS-constrained figure
    # the dashboard used before P2-stability).
    final_fitness, breakdown = _constrained_fitness(
        best.train_metrics, len(train_prices),
        oos_metrics=oos_metrics or None,
    )

    return {
        "success": True,
        "strategy_type": strategy_type,
        "params": dict(best.params),
        "metrics": dict(best.train_metrics),
        "oos_metrics": oos_metrics,
        "fitness": float(final_fitness),
        "selection_score": float(best.selection_score),
        "pf_gap": float(best.pf_gap),
        "_constraints": {
            "dd_cap_pct": DEFAULT_DD_CAP_PCT,
            "min_trades": DEFAULT_MIN_TRADES,
            "oos_pf_gap_cap": DEFAULT_OOS_GAP_CAP,
            "stability_gap_soft": STABILITY_GAP_SOFT,
            "is_dd_pct": float(best.train_metrics.get("max_drawdown_pct", 0) or 0),
            "oos_dd_pct": float((oos_metrics or {}).get("max_drawdown_pct", 0) or 0),
            "is_trades": int(best.train_metrics.get("total_trades", 0) or 0),
            "is_pf": float(best.train_metrics.get("profit_factor", 0) or 0),
            "oos_pf": float((oos_metrics or {}).get("profit_factor", 0) or 0),
            "pf_gap": float(best.pf_gap),
            "breakdown": breakdown,
            "dd_violation": float(best.train_metrics.get("max_drawdown_pct", 0) or 0) > DEFAULT_DD_CAP_PCT,
        },
        "_ga": {
            "generations": generations,
            "population_size": population_size,
            "tournament_k": tournament_k,
            "crossover_prob": crossover_prob,
            "mutation_prob": mutation_prob,
            "elites": elite_n,
            "oos_weight": oos_weight,
            "best_fitness_history": [round(f, 3) for f in best_fitness_history],
            "best_selection_score_history": [round(s, 3) for s in best_selection_history],
            "best_pf_gap_history": [round(g, 3) for g in best_gap_history],
            "evaluations": evaluations,
        },
    }


# Convenience pickler — easier debugging in tests
def individual_to_dict(ind: Individual) -> dict:
    """Return a plain-dict view of the dataclass for diagnostics."""
    return asdict(ind)

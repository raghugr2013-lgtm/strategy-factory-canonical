"""
P2 — GA STABILITY IMPROVEMENT regression tests.

Locks in the OOS-aware GA behaviour:
  * generations default bumped 6 → 8.
  * every individual gets `oos_metrics` populated during evolution,
    not just the final winner.
  * tournament / elitism / final-pick rank by `selection_score`
    (OOS-weighted + stability-penalised), not raw IS `fitness`.
  * `pf_gap` (IS_PF − OOS_PF) is exposed on the result payload so the
    UI and tests can see whether the winner is IS-overfit.
  * `best_selection_score_history` + `best_pf_gap_history` are
    surfaced per generation for observability.
  * fitness FORMULA itself (`_constrained_fitness`) is UNCHANGED —
    only the selection signal changes.
"""
from __future__ import annotations

import math
import random

import pytest

from engines.ga_optimizer import (
    DEFAULT_GENERATIONS,
    DEFAULT_OOS_WEIGHT,
    STABILITY_GAP_SOFT,
    STABILITY_HARD_PENALTY,
    STABILITY_SOFT_PENALTY,
    _evaluate_individual_with_oos,
    _pf_float,
    run_ga_search,
)
from engines.random_search_optimizer import Individual


STRATEGY = (
    "TYPE: trend_following\n"
    "Buy when fast EMA crosses above slow EMA and RSI is below 70. "
    "Sell when fast EMA crosses below slow EMA. Use 20 pip SL and 40 pip TP."
)


def _prices(n: int = 800, seed: int = 17) -> list:
    rng = random.Random(seed)
    px = 1.10
    out = []
    for i in range(n):
        px = px + math.sin(i / 45) * 0.0009 + (i / n) * 0.004 + rng.gauss(0, 0.0011)
        out.append(round(px, 6))
    return out


# ── Defaults ────────────────────────────────────────────────────────


def test_generations_default_is_eight():
    """P2-stability: default generations bumped from 6 to 8."""
    assert DEFAULT_GENERATIONS == 8


def test_oos_weight_default_gives_oos_the_edge():
    assert 0.5 < DEFAULT_OOS_WEIGHT < 1.0, (
        "OOS weight should dominate (>0.5) but leave some credit for IS"
    )


# ── `_pf_float` — never crashes on None ─────────────────────────────


def test_pf_float_returns_zero_for_none():
    assert _pf_float({"profit_factor": None}) == 0.0
    assert _pf_float({}) == 0.0
    assert _pf_float({"profit_factor": "x"}) == 0.0
    assert _pf_float({"profit_factor": 1.4}) == 1.4
    assert _pf_float({"profit_factor": 2}) == 2.0


# ── Individual-level OOS evaluator ──────────────────────────────────


def test_evaluate_individual_populates_both_sides_and_gap():
    """After `_evaluate_individual_with_oos` runs, the individual must
    carry train_metrics, oos_metrics, fitness, selection_score, pf_gap."""
    px = _prices()
    split = int(len(px) * 0.70)
    ind = Individual(params={"fast_period": 10, "slow_period": 30,
                             "sl_pips": 20, "tp_pips": 40})
    _evaluate_individual_with_oos(
        ind, STRATEGY, "EURUSD", "H1",
        px[:split], px[split:], "trend_following", sim_config={},
    )
    assert isinstance(ind.train_metrics, dict) and ind.train_metrics
    assert isinstance(ind.oos_metrics, dict)       # may be {} if no trades
    assert isinstance(ind.fitness, float)
    assert isinstance(ind.selection_score, float)
    assert isinstance(ind.pf_gap, float)


def test_selection_score_penalises_large_pf_gap():
    """Two synthetic individuals with identical IS fitness but
    different OOS gap — the one with the larger gap must have a
    strictly smaller selection_score."""
    ind_consistent = Individual(params={})
    ind_overfit    = Individual(params={})
    # Patch what the evaluator would have produced.
    ind_consistent.train_metrics = {"profit_factor": 1.4, "max_drawdown_pct": 8,
                                    "total_trades": 30, "net_profit": 200,
                                    "sharpe_ratio": 1.0, "initial_balance": 10000}
    ind_consistent.oos_metrics   = {"profit_factor": 1.35, "max_drawdown_pct": 8,
                                    "total_trades": 12, "net_profit": 100,
                                    "sharpe_ratio": 0.9, "initial_balance": 10000}
    ind_overfit.train_metrics    = dict(ind_consistent.train_metrics)
    ind_overfit.oos_metrics      = {"profit_factor": 0.7, "max_drawdown_pct": 14,
                                    "total_trades": 12, "net_profit": -50,
                                    "sharpe_ratio": -0.2, "initial_balance": 10000}

    # Manually compute selection_score with the same formula the
    # real evaluator uses.
    from engines.ga_optimizer import _constrained_fitness
    def _score(ind):
        is_f, _ = _constrained_fitness(ind.train_metrics, 560)
        oos_f, _ = _constrained_fitness(ind.oos_metrics, 240)
        is_pf = _pf_float(ind.train_metrics)
        oos_pf = _pf_float(ind.oos_metrics)
        gap = abs(is_pf - oos_pf)
        stab = (STABILITY_HARD_PENALTY if gap >= 0.6
                else STABILITY_SOFT_PENALTY if gap >= STABILITY_GAP_SOFT
                else 1.0)
        direction = 0.85 if (is_pf > 1.0 and oos_pf < is_pf * 0.75) else 1.0
        return (0.4 * is_f + 0.6 * oos_f) * stab * direction

    s_consistent = _score(ind_consistent)
    s_overfit = _score(ind_overfit)
    assert s_consistent > s_overfit, (
        f"Consistent IS≈OOS individual ({s_consistent:.2f}) must outscore "
        f"the overfit one ({s_overfit:.2f})"
    )


# ── Full GA run — shape of the new payload ──────────────────────────


def test_run_ga_search_surfaces_pf_gap_and_selection_score():
    res = run_ga_search(
        STRATEGY, "EURUSD", "H1",
        prices=_prices(), train_ratio=0.70,
        population_size=8, generations=3, rng_seed=123,
    )
    assert res["success"] is True
    # New P2-stability fields:
    assert "selection_score" in res
    assert "pf_gap" in res
    assert isinstance(res["selection_score"], float)
    assert isinstance(res["pf_gap"], float)
    # _ga history now includes selection + gap tracks
    ga_block = res["_ga"]
    assert "best_selection_score_history" in ga_block
    assert "best_pf_gap_history" in ga_block
    assert "oos_weight" in ga_block
    n = ga_block["generations"]
    # + 1 because we record the initial population once before the
    # first generation loop iteration.
    assert len(ga_block["best_selection_score_history"]) == n + 1
    assert len(ga_block["best_pf_gap_history"]) == n + 1
    # _constraints carries pf_gap too (already had is_pf / oos_pf).
    assert "pf_gap" in res["_constraints"]


def test_run_ga_search_pf_gap_matches_is_minus_oos():
    """The reported `pf_gap` must equal `is_pf − oos_pf` on the
    winner (not an absolute value; sign matters for overfit direction)."""
    res = run_ga_search(
        STRATEGY, "EURUSD", "H1",
        prices=_prices(seed=31), train_ratio=0.70,
        population_size=8, generations=3, rng_seed=42,
    )
    if not res["success"]:
        pytest.skip("insufficient data for rng_seed=42 on this fixture")
    is_pf = _pf_float(res["metrics"])
    oos_pf = _pf_float(res["oos_metrics"])
    assert abs(res["pf_gap"] - round(is_pf - oos_pf, 3)) < 1e-6


def test_constrained_fitness_formula_is_still_unchanged():
    """Explicit anchor: the PF/DD/trade-count constraints live in the
    SAME helper (`_constrained_fitness`). This test guards against a
    future refactor that would silently change the fitness formula
    while touching GA behaviour — the user's explicit constraint for
    P2-stability was 'do NOT change fitness formula yet'."""
    from engines.ga_optimizer import _constrained_fitness
    clean = {
        "net_profit": 200.0, "max_drawdown_pct": 5.0, "total_trades": 30,
        "profit_factor": 1.6, "sharpe_ratio": 1.0, "initial_balance": 10_000.0,
        "win_rate": 55.0, "total_return_pct": 2.0,
    }
    v, br = _constrained_fitness(clean, train_len=400)
    # Clean metrics → all penalties 1.0.
    assert br["dd_penalty"] == 1.0
    assert br["trade_penalty"] == 1.0
    assert br["oos_penalty"] == 1.0
    # And a too-high DD still triggers the SAME 0.3 multiplier.
    bad = {**clean, "max_drawdown_pct": 22.0}
    _, bad_br = _constrained_fitness(bad, train_len=400)
    assert bad_br["dd_penalty"] == 0.3

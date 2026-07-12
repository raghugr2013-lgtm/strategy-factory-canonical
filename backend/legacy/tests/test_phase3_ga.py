"""
Phase-3 — Genetic Algorithm optimizer tests.

Verifies the GA-level constraints documented in the project plan:
  * primary objective: maximise Profit Factor
  * hard cap: DD ≤ 15 % → constrained fitness must shrink past it
  * penalty for low trade count
  * penalty for unstable OOS performance (large IS↔OOS PF gap)

Plus an end-to-end smoke run of `run_ga_search` on a real fixture.
"""
from __future__ import annotations

import math
import random

from engines.ga_optimizer import (
    DEFAULT_DD_CAP_PCT,
    DEFAULT_MIN_TRADES,
    DEFAULT_OOS_GAP_CAP,
    _constrained_fitness,
    run_ga_search,
)


STRATEGY_TEXT = (
    "Buy when fast EMA crosses above slow EMA and RSI is below 70. "
    "Sell when fast EMA crosses below slow EMA or RSI is above 80. "
    "Use 20 pip stop loss and 40 pip take profit."
)


def _make_prices(n: int = 600, seed: int = 21) -> list:
    rng = random.Random(seed)
    px = 1.10
    out = []
    for i in range(n):
        drift = math.sin(i / 35.0) * 0.0008 + (i / n) * 0.005
        px = px + drift + rng.gauss(0, 0.0011)
        out.append(round(px, 6))
    return out


# ── Constraint-shape unit tests ──────────────────────────────────────


def _good_metrics() -> dict:
    return {
        "net_profit": 200.0, "max_drawdown_pct": 5.0, "total_trades": 30,
        "profit_factor": 1.6, "sharpe_ratio": 1.0, "initial_balance": 10_000.0,
        "win_rate": 55.0, "total_return_pct": 2.0,
    }


def test_constrained_fitness_no_penalty_for_clean_metrics():
    final, breakdown = _constrained_fitness(_good_metrics(), train_len=400)
    assert breakdown["dd_penalty"] == 1.0
    assert breakdown["trade_penalty"] == 1.0
    assert breakdown["oos_penalty"] == 1.0
    assert final == breakdown["base"]


def test_constrained_fitness_dd_cap_kicks_in_above_15_percent():
    bad = {**_good_metrics(), "max_drawdown_pct": DEFAULT_DD_CAP_PCT + 5.0}
    final, breakdown = _constrained_fitness(bad, train_len=400)
    assert breakdown["dd_penalty"] == 0.3, "DD cap penalty must hit when DD > 15%"
    assert final < breakdown["base"]


def test_constrained_fitness_low_trade_count_penalty():
    light = {**_good_metrics(), "total_trades": 5}
    final, breakdown = _constrained_fitness(light, train_len=400)
    assert breakdown["trade_penalty"] < 1.0
    # Floor at 0.4 — never collapses fitness to 0
    assert breakdown["trade_penalty"] >= 0.4
    assert final < breakdown["base"]


def test_constrained_fitness_oos_gap_penalty():
    is_m = {**_good_metrics(), "profit_factor": 2.0}
    oos_m = {**_good_metrics(), "profit_factor": 1.0}  # gap = 1.0 > cap
    final, breakdown = _constrained_fitness(is_m, train_len=400, oos_metrics=oos_m)
    assert breakdown["oos_penalty"] == 0.7
    assert final < breakdown["base"]


def test_constrained_fitness_no_oos_penalty_when_gap_small():
    is_m = {**_good_metrics(), "profit_factor": 1.5}
    oos_m = {**_good_metrics(), "profit_factor": 1.4}  # gap = 0.1
    _, breakdown = _constrained_fitness(is_m, train_len=400, oos_metrics=oos_m)
    assert breakdown["oos_penalty"] == 1.0


# ── Smoke-test run_ga_search ─────────────────────────────────────────


def test_run_ga_search_smoke_returns_constraints_and_oos_replay():
    res = run_ga_search(
        STRATEGY_TEXT, "EURUSD", "H1",
        prices=_make_prices(),
        train_ratio=0.70,
        population_size=8,
        generations=3,
        rng_seed=1234,
        sim_config={"mtf_filter": False, "regime_filter": False},
    )
    assert res.get("success") is True
    assert "params" in res and isinstance(res["params"], dict)
    assert "metrics" in res
    assert "oos_metrics" in res, "OOS replay block must be present (frozen-params replay)"
    cons = res.get("_constraints")
    assert cons is not None
    assert cons["dd_cap_pct"] == DEFAULT_DD_CAP_PCT
    assert cons["min_trades"] == DEFAULT_MIN_TRADES
    assert cons["oos_pf_gap_cap"] == DEFAULT_OOS_GAP_CAP
    assert "breakdown" in cons
    ga = res.get("_ga") or {}
    assert len(ga.get("best_fitness_history", [])) == ga.get("generations", -1) + 1


def test_run_ga_search_handles_short_data_gracefully():
    res = run_ga_search(
        STRATEGY_TEXT, "EURUSD", "H1",
        prices=_make_prices(n=40),
    )
    assert res.get("success") is False
    assert "error" in res

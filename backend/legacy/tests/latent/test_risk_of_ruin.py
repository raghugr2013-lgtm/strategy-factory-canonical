"""Unit tests for engines.risk_of_ruin (latent — Phase 4 P4.14)."""
from __future__ import annotations

import pytest

from engines import risk_of_ruin as ror

pytestmark = pytest.mark.latent


# ─────────────────────────────────────────────────────────────────────
# Closed-form gambler's ruin
# ─────────────────────────────────────────────────────────────────────

def test_closed_form_negative_ev_returns_one():
    # win 30% with 1:1 payoff is negative EV — ruin is certain.
    assert ror.closed_form_ror(win_rate=0.30, payoff_ratio=1.0) == 1.0


def test_closed_form_strong_edge_returns_low_ror():
    # 60% win, 2:1 payoff, 100 units capital — RoR should be tiny.
    ror_val = ror.closed_form_ror(
        win_rate=0.60, payoff_ratio=2.0, capital_units=100,
    )
    assert 0.0 <= ror_val <= 0.01


def test_closed_form_zero_capital_clamped_to_one_unit():
    # Defensive: capital_units<=0 must not crash (clamped to 1).
    r = ror.closed_form_ror(win_rate=0.55, payoff_ratio=1.5, capital_units=0)
    assert 0.0 <= r <= 1.0


def test_closed_form_zero_win_rate_is_certain_ruin():
    assert ror.closed_form_ror(win_rate=0.0, payoff_ratio=2.0) == 1.0


# ─────────────────────────────────────────────────────────────────────
# Monte-Carlo RoR
# ─────────────────────────────────────────────────────────────────────

def test_monte_carlo_insufficient_trades_returns_error():
    res = ror.monte_carlo_ror(trades=[{"pnl": 1.0}] * 3)
    assert res["error"] == "insufficient_trades"
    assert res["ror"] is None


def test_monte_carlo_positive_distribution_low_ror():
    # All-winning distribution → near-zero ruin probability.
    trades = [{"pnl": 1.0} for _ in range(60)]
    res = ror.monte_carlo_ror(
        trades=trades, dd_limit_pct=20.0, n_simulations=200,
    )
    assert 0.0 <= res["ror"] <= 0.05
    assert res["n_simulations"] == 200


def test_monte_carlo_losing_distribution_high_ror():
    # All-losing distribution → very high ruin probability.
    trades = [{"pnl": -1.0} for _ in range(60)]
    res = ror.monte_carlo_ror(
        trades=trades, dd_limit_pct=20.0, n_simulations=200,
    )
    assert res["ror"] >= 0.95


def test_monte_carlo_deterministic_with_seed():
    trades = [{"pnl": 0.5}, {"pnl": -0.4}, {"pnl": 0.8}, {"pnl": -0.6}] * 20
    r1 = ror.monte_carlo_ror(trades, n_simulations=500, seed=42)
    r2 = ror.monte_carlo_ror(trades, n_simulations=500, seed=42)
    assert r1["ror"] == r2["ror"]


# ─────────────────────────────────────────────────────────────────────
# Deploy-score weight enforcement (the dormancy contract)
# ─────────────────────────────────────────────────────────────────────

def test_default_weight_is_zero():
    """CRITICAL — must remain 0.0 until operator explicitly raises it.
    A regression here means RoR has silently become authoritative."""
    assert ror.deploy_score_weight() == 0.0

"""
Tests for execution_engine + its integration with challenge_simulator.

Validates:
  1. Backward compatibility — simulator output is identical when execution is
     absent or explicitly disabled.
  2. Spread reduces net_pnl by exactly the configured cost.
  3. Slippage is bounded by max_slippage, reproducible with a seed,
     and adverse (never adds to PnL).
  4. Intrabar worst-case: winner trades whose exit candle contains both SL and
     TP are flipped to SL losses for BUY and SELL, and floating_min_pnl is
     deepened accordingly.
  5. DD regression: enabling execution produces worse (or equal) max DD.
  6. Already-losing trades are NOT flipped.
  7. Trades missing candle context are skipped by the intrabar step (no crash).
"""
from __future__ import annotations

import copy

import pytest

from engines.execution_engine import (
    apply_execution,
    apply_execution_to_trades,
    resolve_config,
    summarize_config,
)
from engines.challenge_simulator import simulate_challenge


# ─── fixtures ────────────────────────────────────────────────────────────

BASE_RULES: dict = {
    "initial_balance": 100_000,
    "profit_target_pct": 10.0,
    "max_daily_dd_pct": 5.0,
    "max_total_dd_pct": 10.0,
    "min_trading_days": 1,
    "time_limit_days": 0,
    "drawdown_type": "static",
}


def _simple_trades():
    """Three trades: +500 win, -200 loss, +300 win. Same day for simplicity."""
    return [
        {"net_pnl": 500.0,  "timestamp": "2024-01-02T10:00:00"},
        {"net_pnl": -200.0, "timestamp": "2024-01-02T12:00:00"},
        {"net_pnl": 300.0,  "timestamp": "2024-01-02T14:00:00"},
    ]


# ─── 1. Backward compatibility ──────────────────────────────────────────

def test_resolve_config_defaults_to_disabled():
    cfg = resolve_config(None)
    assert cfg["enabled"] is False
    assert cfg["spread"] == 0.0
    assert cfg["max_slippage"] == 0.0
    assert cfg["commission_per_trade"] == 0.0
    assert cfg["intrabar_mode"] == "worst_case"


def test_simulator_output_identical_when_execution_absent():
    trades = _simple_trades()
    r1 = simulate_challenge(copy.deepcopy(trades), BASE_RULES)
    r2 = simulate_challenge(copy.deepcopy(trades), {**BASE_RULES, "execution": {"enabled": False}})
    for k in ("final_balance", "final_equity", "max_drawdown_pct", "max_daily_drawdown_pct"):
        assert r1[k] == r2[k], f"mismatch on {k}"


def test_simulator_response_carries_execution_summary():
    rules = {**BASE_RULES, "execution": {"enabled": True, "spread": 2.5, "max_slippage": 1.0}}
    res = simulate_challenge(_simple_trades(), rules)
    exec_summary = res["rules_used"]["execution"]
    assert exec_summary["enabled"] is True
    assert exec_summary["spread"] == 2.5
    assert exec_summary["max_slippage"] == 1.0
    assert exec_summary["intrabar_mode"] == "worst_case"


# ─── 2. Spread ───────────────────────────────────────────────────────────

def test_spread_reduces_net_pnl_exactly():
    cfg = {"enabled": True, "spread": 3.0, "max_slippage": 0.0}
    trade = {"net_pnl": 100.0}
    adj = apply_execution(trade, cfg)
    assert adj["net_pnl"] == pytest.approx(97.0)
    assert adj["_exec_spread_cost"] == 3.0


def test_spread_also_deepens_floating_min_pnl():
    cfg = {"enabled": True, "spread": 5.0, "max_slippage": 0.0}
    trade = {"net_pnl": 100.0, "floating_min_pnl": -10.0}
    adj = apply_execution(trade, cfg)
    assert adj["floating_min_pnl"] == pytest.approx(-15.0)


# ─── 3. Slippage ─────────────────────────────────────────────────────────

def test_slippage_is_bounded_and_deterministic_with_seed():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 5.0, "seed": 42}
    trades = [{"net_pnl": 100.0} for _ in range(20)]
    adjusted = apply_execution_to_trades(trades, {"execution": cfg})
    for t in adjusted:
        # adverse → always subtracted
        assert t["net_pnl"] <= 100.0
        slip = 100.0 - t["net_pnl"]
        assert 0.0 <= slip <= 5.0
    # Rerun with same seed → identical outputs
    adjusted2 = apply_execution_to_trades(trades, {"execution": cfg})
    assert [t["net_pnl"] for t in adjusted] == [t["net_pnl"] for t in adjusted2]


def test_slippage_never_adds_to_pnl():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 10.0, "seed": 1}
    adj = apply_execution({"net_pnl": 50.0}, cfg)
    assert adj["net_pnl"] <= 50.0


# ─── 4. Intrabar worst-case ─────────────────────────────────────────────

def _winning_buy_with_both_levels_in_candle():
    # entry=1.1000, sl=1.0950 (50 pips stop), tp=1.1050 (50 pips target)
    # candle_low=1.0940 (below SL) AND candle_high=1.1060 (above TP) → both hit
    return {
        "net_pnl": 500.0,
        "side": "BUY",
        "entry_price": 1.1000,
        "sl_price": 1.0950,
        "tp_price": 1.1050,
        "candle_high": 1.1060,
        "candle_low": 1.0940,
        "sl_loss_amount": 500.0,   # 1:1 RR so SL loss magnitude = TP win magnitude
        "floating_min_pnl": -100.0,
        "timestamp": "2024-01-02T10:00:00",
    }


def _winning_sell_with_both_levels_in_candle():
    # entry=1.2000, sl=1.2050, tp=1.1950
    # candle_high=1.2060 (above SL) AND candle_low=1.1940 (below TP) → both hit
    return {
        "net_pnl": 500.0,
        "side": "SELL",
        "entry_price": 1.2000,
        "sl_price": 1.2050,
        "tp_price": 1.1950,
        "candle_high": 1.2060,
        "candle_low": 1.1940,
        "sl_loss_amount": 500.0,
        "floating_min_pnl": -50.0,
        "timestamp": "2024-01-02T10:00:00",
    }


def test_intrabar_flip_buy_winner_to_sl_loss():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 0.0}
    trade = _winning_buy_with_both_levels_in_candle()
    adj = apply_execution(trade, cfg)
    assert adj["_exec_intrabar_flipped"] is True
    assert adj["net_pnl"] == pytest.approx(-500.0)
    assert adj["floating_min_pnl"] <= -500.0  # deepened to at least SL loss


def test_intrabar_flip_sell_winner_to_sl_loss():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 0.0}
    trade = _winning_sell_with_both_levels_in_candle()
    adj = apply_execution(trade, cfg)
    assert adj["_exec_intrabar_flipped"] is True
    assert adj["net_pnl"] == pytest.approx(-500.0)
    assert adj["floating_min_pnl"] <= -500.0


def test_intrabar_no_flip_when_only_tp_in_candle():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 0.0}
    trade = _winning_buy_with_both_levels_in_candle()
    trade["candle_low"] = 1.0980  # above SL → SL NOT hit intrabar
    adj = apply_execution(trade, cfg)
    assert adj.get("_exec_intrabar_flipped") is not True
    assert adj["net_pnl"] == pytest.approx(500.0)


def test_intrabar_does_not_flip_losers():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 0.0}
    trade = _winning_buy_with_both_levels_in_candle()
    trade["net_pnl"] = -500.0  # already a loss
    adj = apply_execution(trade, cfg)
    assert adj.get("_exec_intrabar_flipped") is not True
    assert adj["net_pnl"] == pytest.approx(-500.0)


def test_intrabar_skipped_when_candle_fields_missing():
    cfg = {"enabled": True, "spread": 0.0, "max_slippage": 0.0}
    trade = {"net_pnl": 500.0, "side": "BUY"}  # no sl/tp/candle fields
    adj = apply_execution(trade, cfg)
    assert adj.get("_exec_intrabar_flipped") is not True
    assert adj["net_pnl"] == pytest.approx(500.0)


# ─── 5. DD regression: execution → worse DD ─────────────────────────────

def test_enabling_execution_increases_or_matches_drawdown():
    # 10 trades with a couple of losers; the spread+slippage costs will deepen DD.
    trades = [{"net_pnl": 200.0 if i % 3 else -400.0, "timestamp": f"2024-01-0{(i%9)+1}T10:00:00"}
              for i in range(10)]
    clean = simulate_challenge(copy.deepcopy(trades), BASE_RULES)
    realistic = simulate_challenge(
        copy.deepcopy(trades),
        {**BASE_RULES, "execution": {"enabled": True, "spread": 5.0, "max_slippage": 2.0, "seed": 7}},
    )
    # Execution costs are always ≥ 0 → drawdown must be ≥ clean drawdown.
    assert realistic["max_drawdown_pct"] >= clean["max_drawdown_pct"]
    assert realistic["final_balance"] <= clean["final_balance"]


# ─── 6. Config summarizer ───────────────────────────────────────────────

def test_summarize_config_echoes_inputs():
    out = summarize_config({"execution": {"enabled": True, "spread": 1.5, "max_slippage": 0.5}})
    assert out == {
        "enabled": True,
        "spread": 1.5,
        "max_slippage": 0.5,
        "commission_per_trade": 0.0,
        "intrabar_mode": "worst_case",
    }


def test_invalid_intrabar_mode_falls_back_to_worst_case():
    out = summarize_config({"execution": {"enabled": True, "intrabar_mode": "totally-bogus"}})
    assert out["intrabar_mode"] == "worst_case"

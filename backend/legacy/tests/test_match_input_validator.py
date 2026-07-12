"""Phase 19 — match_input_validator unit tests."""
from __future__ import annotations

from engines.match_input_validator import (
    MIN_TRADES_OK,
    diagnostics_block,
    inspect_trades,
    is_actionable_for_match,
    validate_match_inputs,
)


# ── validate_match_inputs ────────────────────────────────────────────

def test_valid_inputs():
    ok, msg = validate_match_inputs(10000, 30)
    assert ok is True and msg == "ok"


def test_zero_balance_rejected():
    ok, msg = validate_match_inputs(0, 30)
    assert ok is False
    assert "greater than zero" in msg


def test_negative_balance_rejected():
    ok, msg = validate_match_inputs(-100, 30)
    assert ok is False


def test_zero_simulations_rejected():
    ok, msg = validate_match_inputs(10000, 0)
    assert ok is False
    assert "at least 1" in msg


def test_old_strict_bounds_no_longer_reject():
    # Both used to 422 under old Field(ge=1000) / Field(ge=10).
    ok, _ = validate_match_inputs(500, 5)
    assert ok is True


def test_simulation_overflow_capped():
    ok, msg = validate_match_inputs(10000, 5000)
    assert ok is False
    assert "1000" in msg


# ── inspect_trades ───────────────────────────────────────────────────

def test_inspect_empty_trades():
    out = inspect_trades([])
    assert out["sufficiency"] == "empty"
    assert out["trade_count"] == 0
    assert "trades" in out["missing"]


def test_inspect_low_trade_count():
    trades = [{"net_pnl": 1.0} for _ in range(5)]
    out = inspect_trades(trades)
    assert out["sufficiency"] == "low"
    assert out["has_pnl"] is True


def test_inspect_warning_count():
    trades = [{"net_pnl": 1.0} for _ in range(15)]
    out = inspect_trades(trades)
    assert out["sufficiency"] == "warning"


def test_inspect_ok_count():
    trades = [{"net_pnl": 1.0} for _ in range(MIN_TRADES_OK + 1)]
    out = inspect_trades(trades)
    assert out["sufficiency"] == "ok"
    # Equity-curve / DD / consistency missing → flagged
    assert "equity_curve" in " ".join(out["missing"])


def test_inspect_with_full_metrics():
    trades = [
        {"net_pnl": 1.0, "balance": 10000 + i, "drawdown": 0.5, "is_win": True}
        for i in range(MIN_TRADES_OK + 1)
    ]
    out = inspect_trades(trades)
    assert out["has_equity_curve"] is True
    assert out["has_daily_drawdown"] is True
    assert out["has_consistency_metrics"] is True


# ── is_actionable_for_match ──────────────────────────────────────────

def test_actionable_strict_blocks_no_pnl():
    trades = [{"foo": "bar"}]   # dict but no net_pnl
    ok, why = is_actionable_for_match(trades, relaxed_mode=False)
    assert ok is False
    assert "net_pnl" in why


def test_actionable_relaxed_allows_no_pnl():
    trades = [{"foo": "bar"}]
    ok, why = is_actionable_for_match(trades, relaxed_mode=True)
    assert ok is True
    assert why == "relaxed_mode_active"


def test_actionable_strict_passes_with_pnl():
    trades = [{"net_pnl": 1.0}]
    ok, _ = is_actionable_for_match(trades, relaxed_mode=False)
    assert ok is True


def test_actionable_blocks_empty():
    ok, why = is_actionable_for_match([], relaxed_mode=True)
    assert ok is False


# ── diagnostics_block ────────────────────────────────────────────────

def test_diagnostics_envelope_shape():
    block = diagnostics_block(
        [{"net_pnl": 1.0}], initial_balance=10000, n_simulations=30,
        relaxed_mode=False,
    )
    assert block["mode"] == "strict"
    assert block["initial_balance"] == 10000.0
    assert block["n_simulations"] == 30
    assert "trades" in block
    assert "thresholds" in block
    assert block["thresholds"]["min_trades_ok"] == MIN_TRADES_OK


def test_diagnostics_relaxed_mode_label():
    block = diagnostics_block(
        None, initial_balance=500, n_simulations=5, relaxed_mode=True,
    )
    assert block["mode"] == "relaxed"
    assert block["initial_balance"] == 500.0

"""Phase 28-A — Strategy-IR schema invariants.

Pure-function tests over ``engines.strategy_ir``. No Mongo, no HTTP,
no fixtures. Verify:

  * Pydantic schema accepts every operator in the v1 vocabulary.
  * Schema rejects malformed predicates (wrong arity, missing extras,
    undeclared indicator refs).
  * ``ir_version`` is locked at 1.
  * Round-trip via ``model_dump(mode='json')`` → ``validate_ir`` is
    bit-stable.
"""
from __future__ import annotations

import sys

import pytest
from pydantic import ValidationError

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines.strategy_ir import (                              # noqa: E402
    IR_VERSION, StrategyIR, validate_ir, is_valid_ir,
)


# ── Helpers ────────────────────────────────────────────────────────


def _minimum_valid_ir() -> dict:
    """The smallest IR that validates. Used as a base for negative
    tests that mutate one field at a time."""
    return {
        "ir_version": 1,
        "metadata": {"name": "min", "pair": "EURUSD", "timeframe": "H1"},
        "indicators": [
            {"id": "ema_fast", "kind": "EMA", "params": {"period": 20}},
            {"id": "ema_slow", "kind": "EMA", "params": {"period": 50}},
        ],
        "entry_long": {
            "op": "CROSS_UP",
            "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}],
        },
        "entry_short": {
            "op": "CROSS_DOWN",
            "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}],
        },
        "exit": {
            "stop_loss":   {"kind": "pips", "pips": 20.0},
            "take_profit": {"kind": "pips", "pips": 40.0},
        },
        "risk": {"kind": "percent_of_balance", "percent": 1.0,
                 "max_concurrent_positions": 1, "max_spread_pips": 3.0},
    }


# ── Positive tests ─────────────────────────────────────────────────


def test_minimum_ir_validates():
    ir = validate_ir(_minimum_valid_ir())
    assert isinstance(ir, StrategyIR)
    assert ir.ir_version == IR_VERSION


def test_ir_version_locked_at_1():
    bad = _minimum_valid_ir()
    bad["ir_version"] = 2
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_round_trip_is_stable():
    """validate_ir(ir.model_dump(mode='json')) must equal the original."""
    ir1 = validate_ir(_minimum_valid_ir())
    dumped = ir1.model_dump(mode="json")
    ir2 = validate_ir(dumped)
    assert ir1.model_dump(mode="json") == ir2.model_dump(mode="json")


def test_logical_operators_accept_multiple_args():
    ir = _minimum_valid_ir()
    ir["entry_long"] = {
        "op": "AND",
        "args": [
            {"op": "GT", "args": [{"ref": "ema_fast"}, {"const": 1.0}]},
            {"op": "LT", "args": [{"ref": "ema_slow"}, {"const": 2.0}]},
            {"op": "EQ", "args": [{"const": 1}, {"const": 1}]},
        ],
    }
    validate_ir(ir)


def test_session_filter_accepts_force_flat():
    ir = _minimum_valid_ir()
    ir["session_filter"] = {
        "kind": "gmt_window", "open": "07:00",
        "close": "11:00", "force_flat_at": "16:00",
    }
    validated = validate_ir(ir)
    assert validated.session_filter.force_flat_at == "16:00"


def test_atr_ratio_filter_validates():
    ir = _minimum_valid_ir()
    ir["indicators"].append({"id": "atr", "kind": "ATR", "params": {"period": 14}})
    ir["volatility_filter"] = {
        "kind": "atr_ratio", "indicator": "atr",
        "baseline_period": 20, "min_ratio": 0.8,
    }
    validate_ir(ir)


def test_atr_mult_exit_validates():
    ir = _minimum_valid_ir()
    ir["indicators"].append({"id": "atr", "kind": "ATR", "params": {"period": 14}})
    ir["exit"]["stop_loss"]   = {"kind": "atr_mult", "indicator": "atr", "mult": 1.5}
    ir["exit"]["take_profit"] = {"kind": "atr_mult", "indicator": "atr", "mult": 3.0}
    validate_ir(ir)


def test_range_break_predicate_requires_window():
    ir = _minimum_valid_ir()
    ir["entry_long"] = {
        "op": "RANGE_BREAK_UP", "args": [],
        "window_start_gmt": "06:00", "window_end_gmt": "07:00",
    }
    validate_ir(ir)


def test_bb_predicate_requires_indicator():
    ir = _minimum_valid_ir()
    ir["indicators"].append(
        {"id": "bb", "kind": "BOLLINGER", "params": {"period": 20, "std_dev": 2.0}}
    )
    ir["entry_long"] = {
        "op": "BAND_BREAK_UPPER", "args": [], "indicator": "bb",
    }
    validate_ir(ir)


def test_htf_slope_predicate_validates():
    ir = _minimum_valid_ir()
    ir["indicators"].append(
        {"id": "htf_f", "kind": "HTF_EMA", "params": {"period": 50, "htf": "H4"}}
    )
    ir["indicators"].append(
        {"id": "htf_s", "kind": "HTF_EMA", "params": {"period": 200, "htf": "H4"}}
    )
    ir["entry_long"] = {
        "op": "AND",
        "args": [
            {"op": "CROSS_UP", "args": [{"ref": "ema_fast"}, {"ref": "ema_slow"}]},
            {"op": "HTF_SLOPE_UP", "args": [],
             "htf_ema_fast": "htf_f", "htf_ema_slow": "htf_s"},
        ],
    }
    validate_ir(ir)


# ── Negative tests ─────────────────────────────────────────────────


def test_and_requires_at_least_two_args():
    bad = _minimum_valid_ir()
    bad["entry_long"] = {"op": "AND", "args": [
        {"op": "GT", "args": [{"const": 1}, {"const": 0}]},
    ]}
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_not_requires_exactly_one_arg():
    bad = _minimum_valid_ir()
    bad["entry_long"] = {"op": "NOT", "args": [
        {"op": "GT", "args": [{"const": 1}, {"const": 0}]},
        {"op": "GT", "args": [{"const": 2}, {"const": 0}]},
    ]}
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_comparison_requires_two_args():
    bad = _minimum_valid_ir()
    bad["entry_long"] = {"op": "GT", "args": [{"const": 1}]}
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_range_break_requires_window_extras():
    bad = _minimum_valid_ir()
    bad["entry_long"] = {"op": "RANGE_BREAK_UP", "args": []}
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_undeclared_indicator_ref_rejected():
    bad = _minimum_valid_ir()
    bad["entry_long"] = {
        "op": "GT", "args": [{"ref": "ghost_indicator"}, {"const": 1.0}]
    }
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_exit_with_undeclared_atr_indicator_rejected():
    bad = _minimum_valid_ir()
    bad["exit"]["stop_loss"] = {
        "kind": "atr_mult", "indicator": "ghost_atr", "mult": 1.5,
    }
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_session_filter_rejects_malformed_time():
    bad = _minimum_valid_ir()
    bad["session_filter"] = {
        "kind": "gmt_window", "open": "noon", "close": "11:00",
    }
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_risk_percent_capped():
    bad = _minimum_valid_ir()
    bad["risk"]["percent"] = 20.0
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_extra_fields_forbidden_on_root():
    bad = _minimum_valid_ir()
    bad["secret_field"] = "nope"
    with pytest.raises(ValidationError):
        validate_ir(bad)


def test_is_valid_ir_truthy_check():
    assert is_valid_ir(_minimum_valid_ir()) is True
    assert is_valid_ir("a string") is False
    assert is_valid_ir(None) is False
    assert is_valid_ir({"ir_version": 1}) is False  # missing required fields

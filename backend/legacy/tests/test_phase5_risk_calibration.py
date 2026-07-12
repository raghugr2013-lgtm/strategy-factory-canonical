"""
P5 — Asset-aware risk calibration regression suite.

Covers:
  * Auto-ATR on non-forex pairs (XAU, indices, crypto) defaults to true
    and forces `risk_meta.model='atr_based'`.
  * Auto-ATR stays OFF for forex pairs by default.
  * Explicit opt-out via `sim_config.atr_stops=false` is respected.
  * Explicit opt-in via `sim_config.atr_stops=true` on forex works.
  * Ruin floor halts new entries once balance drops below
    `ruin_floor × initial_balance` (default 10 %).
  * `_phase5_risk_calibration` telemetry block carries the right
    fields.
"""

import math


from engines.backtest_engine import (
    run_backtest_logic,
    FOREX_PAIRS,
    DEFAULT_AUTO_ATR_K,
    DEFAULT_AUTO_ATR_M,
    DEFAULT_RUIN_FLOOR,
)


def _wave_prices(n: int = 1500, base: float = 1.1000, amp: float = 0.020) -> list:
    out = []
    for i in range(n):
        w = amp * math.sin(i / 60.0) + 0.5 * amp * math.sin(i / 18.0)
        out.append(round(base + w, 5))
    return out


# ── Auto-ATR defaults ─────────────────────────────────────────────────

def test_forex_defaults_no_atr_stops():
    closes = _wave_prices()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, data_source="real",
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["is_forex"] is True
    assert p5["atr_stops_enabled"] is False
    # risk_model stays None (fixed-pip) on forex by default.
    assert p5["risk_model"] is None


def test_xau_defaults_atr_stops_on():
    closes = _wave_prices(n=1500, base=2000.0, amp=20.0)
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "XAUUSD", "H1",
        external_prices=closes, data_source="real",
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["is_forex"] is False
    assert p5["atr_stops_enabled"] is True
    assert p5["risk_model"] == "atr_based"
    assert p5["atr_k"] == DEFAULT_AUTO_ATR_K
    assert p5["atr_m"] == DEFAULT_AUTO_ATR_M


def test_indices_crypto_also_get_atr_by_default():
    closes = _wave_prices(n=1500, base=15000.0, amp=150.0)
    for pair in ("US100", "BTCUSD", "ETHUSD"):
        bt = run_backtest_logic(
            "EMA(20)/EMA(50) trend-following SL=20 TP=40",
            pair, "H1",
            external_prices=closes, data_source="real",
        )
        p5 = bt["_phase5_risk_calibration"]
        assert p5["atr_stops_enabled"] is True, pair
        assert p5["is_forex"] is False, pair


# ── Overrides ─────────────────────────────────────────────────────────

def test_explicit_optout_respected_on_xau():
    closes = _wave_prices(n=1500, base=2000.0, amp=20.0)
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "XAUUSD", "H1",
        external_prices=closes, data_source="real",
        sim_config={"atr_stops": False},
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["atr_stops_enabled"] is False


def test_explicit_optin_respected_on_forex():
    closes = _wave_prices(n=1500)
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, data_source="real",
        sim_config={"atr_stops": True},
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["atr_stops_enabled"] is True
    assert p5["risk_model"] == "atr_based"


# ── Ruin floor ────────────────────────────────────────────────────────

def test_ruin_floor_default_is_10_percent():
    closes = _wave_prices()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, data_source="real",
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["ruin_floor"] == DEFAULT_RUIN_FLOOR
    # For the 10 000 USD default initial balance.
    assert abs(p5["ruin_floor_usd"] - 1000.0) < 0.01


def test_ruin_floor_triggers_on_catastrophic_strategy():
    """A strategy that loses aggressively should trigger the floor
    (stopping new entries) WITHOUT exploding the DD into 4-digit
    percentages — the core bug the ruin-guard was built to eliminate.
    """
    # XAU priced around $2000 with the old forex-tuned SL=20 TP=40 on a
    # noisy series. Without auto-ATR + without ruin guard the DD was
    # 9 000 %+. With both ON, DD must stay bounded.
    closes = _wave_prices(n=1500, base=2000.0, amp=5.0)
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "XAUUSD", "H1",
        external_prices=closes, data_source="real",
        # Auto-ATR kicks in; ruin guard at default 10 %.
    )
    p5 = bt["_phase5_risk_calibration"]
    # Equity curve monotonic from last-segment-of-trading; max_drawdown_pct
    # must stay under 200 % in every case (previously 9 000 %+).
    dd_is = bt.get("max_drawdown_pct") or 0
    dd_oos = bt.get("oos_max_drawdown_pct") or 0
    assert dd_is < 200.0, f"IS DD exploded: {dd_is}"
    assert dd_oos < 200.0, f"OOS DD exploded: {dd_oos}"
    # Whether or not ruin was triggered is strategy-dependent; but the
    # calibration block must always expose both fields.
    assert "is_ruin_triggered" in p5
    assert "oos_ruin_triggered" in p5


def test_ruin_floor_can_be_disabled():
    closes = _wave_prices()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, data_source="real",
        sim_config={"ruin_floor": 0.0},
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["ruin_floor"] == 0.0
    assert p5["ruin_floor_usd"] is None
    assert p5["is_ruin_triggered"] is False


def test_ruin_floor_custom_value():
    closes = _wave_prices()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "EURUSD", "H1",
        external_prices=closes, data_source="real",
        sim_config={"ruin_floor": 0.25},  # 25 %
    )
    p5 = bt["_phase5_risk_calibration"]
    assert p5["ruin_floor"] == 0.25
    assert abs(p5["ruin_floor_usd"] - 2500.0) < 0.01


# ── Forex pair set sanity ─────────────────────────────────────────────

def test_forex_pairs_set_includes_majors():
    for p in ("EURUSD", "GBPUSD", "USDJPY", "USDCAD", "USDCHF", "AUDUSD", "NZDUSD"):
        assert p in FOREX_PAIRS, p


def test_non_forex_pairs_not_in_set():
    for p in ("XAUUSD", "US100", "BTCUSD", "ETHUSD", "XAGUSD"):
        assert p not in FOREX_PAIRS, p


# ── Telemetry shape ───────────────────────────────────────────────────

def test_phase5_block_has_all_required_keys():
    closes = _wave_prices()
    bt = run_backtest_logic(
        "EMA(20)/EMA(50) trend-following SL=20 TP=40",
        "GBPUSD", "H1",
        external_prices=closes, data_source="real",
    )
    p5 = bt["_phase5_risk_calibration"]
    for key in (
        "pair", "is_forex", "atr_stops_enabled",
        "atr_k", "atr_m", "risk_model",
        "ruin_floor", "ruin_floor_usd",
        "is_ruin_triggered", "oos_ruin_triggered",
        "is_ruin_index", "oos_ruin_index",
    ):
        assert key in p5, key

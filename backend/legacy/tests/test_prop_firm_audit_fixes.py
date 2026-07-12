"""P6 — Prop Firm Rule Engine audit fix regression tests.

Pins the 5 fixes applied during the focused audit-patch pass:
  #1 floating_min_pnl surfaced from backtest trade dict (mae_usd)
  #2 intracandle MAE uses bar high/low (not closes only)
  #3 weekend-boundary force-close with spread penalty
  #4 daily DD timezone conversion (NY 17:00 broker day)
  #5 rules_to_sim_config auto-enables execution.worst_case
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta


# ─── Fix #1 ─ floating_min_pnl surfaced on trade dict ────────────────

def test_backtest_trade_dict_carries_floating_min_pnl():
    """Every closed trade must include `floating_min_pnl` (== mae_usd)
    so `challenge_simulator` uses the real MAE instead of the
    `net_pnl × 2` estimate path."""
    from engines.backtest_engine import run_backtest_logic
    import math

    # Alternating-trend sinusoid guarantees EMA crossovers → real trades.
    prices = [
        1.1000 + 0.02 * math.sin(i / 30.0) + 0.0001 * math.sin(i)
        for i in range(1500)
    ]
    res = run_backtest_logic(
        "EMA(10)/EMA(30) trend-following SL=15 TP=30",
        "EURUSD", "H1", external_prices=prices, data_points=len(prices),
    )
    trades = res.get("trades") or []
    assert trades, "expected at least one trade"
    missing = [
        t for t in trades
        if "floating_min_pnl" not in t or t["floating_min_pnl"] is None
    ]
    assert not missing, (
        f"{len(missing)} trades missing floating_min_pnl — simulator would "
        f"fall back to net_pnl × 2 estimate"
    )
    for t in trades:
        # mae_usd is a positive magnitude; floating_min_pnl must be ≤ 0.
        assert t["floating_min_pnl"] == -t["mae_usd"], (
            f"floating_min_pnl {t['floating_min_pnl']} must equal -mae_usd {-t['mae_usd']}"
        )
        assert t["floating_min_pnl"] <= 0, (
            f"floating_min_pnl {t['floating_min_pnl']} must be ≤ 0 for the simulator"
        )


# ─── Fix #2 ─ intracandle MAE uses bar high/low ──────────────────────

def test_intracandle_mae_widens_with_high_low():
    """Feeding the engine a dataset where the bar LOWS dip far below
    the closes must yield a larger (more negative) MAE than running
    the same engine with lows equal to closes (close-only path)."""
    from engines.backtest_engine import run_backtest_logic
    import math

    closes = [
        1.1000 + 0.02 * math.sin(i / 30.0) + 0.0001 * math.sin(i)
        for i in range(1500)
    ]
    # Large low spikes below close; highs slightly above close.
    lows = [c - 0.00150 for c in closes]
    highs = [c + 0.00010 for c in closes]

    res_with_ohlc = run_backtest_logic(
        "EMA(10)/EMA(30) trend-following SL=50 TP=100",
        "EURUSD", "H1", external_prices=closes, data_points=len(closes),
        external_highs=highs, external_lows=lows,
    )
    res_closes_only = run_backtest_logic(
        "EMA(10)/EMA(30) trend-following SL=50 TP=100",
        "EURUSD", "H1", external_prices=closes, data_points=len(closes),
    )

    tr_ohlc = res_with_ohlc.get("trades") or []
    tr_closes = res_closes_only.get("trades") or []
    assert tr_ohlc, "ohlc run produced no trades"
    assert tr_closes, "closes-only run produced no trades"
    # mae_usd is a POSITIVE magnitude of the worst adverse excursion.
    # The OHLC path should see larger (more adverse) excursions than
    # closes-only because bar lows dip further than bar closes.
    worst_ohlc = max(t["mae_usd"] for t in tr_ohlc)
    worst_closes = max(t["mae_usd"] for t in tr_closes)
    assert worst_ohlc > worst_closes, (
        f"intracandle MAE magnitude should exceed closes-only; "
        f"ohlc={worst_ohlc} closes={worst_closes}"
    )


# ─── Fix #3 ─ weekend force-close + penalty ──────────────────────────

def test_weekend_boundary_closes_open_positions():
    """Bars with timestamp Friday ≥ 20:00 UTC must force-close any
    open position (exit_reason='WEEKEND')."""
    from engines.backtest_engine import run_backtest_logic
    import math

    # 720 H1 bars = 30 days — crosses 4 Friday-20:00 boundaries.
    start = datetime(2024, 1, 8, 0, 0, tzinfo=timezone.utc)   # Monday
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(720)]
    # Very slow drift so trades stay open across multiple days.
    prices = [
        1.1000 + 0.005 * math.sin(i / 120.0) + 0.0001 * math.sin(i / 5.0)
        for i in range(720)
    ]

    res = run_backtest_logic(
        "EMA(10)/EMA(30) trend-following SL=500 TP=1000",
        "EURUSD", "H1", external_prices=prices, data_points=720,
        external_highs=[p + 0.0001 for p in prices],
        external_lows=[p - 0.0001 for p in prices],
        external_timestamps=timestamps,
    )
    trades = res.get("trades") or []
    assert trades, "expected trades"
    weekend_exits = [t for t in trades if t.get("result") == "WEEKEND"]
    assert weekend_exits, (
        f"expected at least one WEEKEND force-close; "
        f"got {len(trades)} trades with exits "
        f"{[(t.get('result'), t.get('exit_time')) for t in trades[:5]]}"
    )
    for t in weekend_exits:
        et = t["exit_time"]
        dt = datetime.fromisoformat(et.replace("Z", "+00:00"))
        assert dt.weekday() == 4 and dt.hour >= 20, (
            f"WEEKEND trade exit_time {et} not in Friday ≥ 20:00 UTC window"
        )


# ─── Fix #4 ─ NY 17:00 broker-day timezone ───────────────────────────

def test_parse_date_converts_utc_to_ny_broker_day():
    """The broker day starts at 17:00 NY, so the UTC timestamps that
    fall before the reset belong to the PREVIOUS broker day."""
    from engines.challenge_simulator import _parse_date

    # 2024-01-15 is a Monday. In winter, NY is UTC-5 so:
    #   * UTC 21:30 Jan 15 → NY 16:30 Jan 15 → broker day Jan 14 (started 17:00 Jan 14 NY)
    #   * UTC 22:00 Jan 15 → NY 17:00 Jan 15 → broker day Jan 15 STARTS
    assert _parse_date("2024-01-15T21:30:00+00:00") == "2024-01-14"
    assert _parse_date("2024-01-15T22:00:00+00:00") == "2024-01-15"
    # UTC Tuesday 02:00 → NY 21:00 Monday → still broker day Jan 15.
    assert _parse_date("2024-01-16T02:00:00+00:00") == "2024-01-15"
    # UTC Tuesday 22:00 → NY 17:00 Tuesday → broker day Jan 16.
    assert _parse_date("2024-01-16T22:00:00+00:00") == "2024-01-16"


def test_parse_date_crosses_broker_day_boundary():
    """Two trades on the same UTC date but straddling the NY 17:00
    reset must end up on DIFFERENT broker days."""
    from engines.challenge_simulator import _parse_date

    a = _parse_date("2024-01-15T22:00:00+00:00")   # 17:00 NY Jan 15 → day 15
    b = _parse_date("2024-01-16T21:59:00+00:00")   # 16:59 NY Jan 16 → day 15
    c = _parse_date("2024-01-16T22:00:00+00:00")   # 17:00 NY Jan 16 → day 16
    assert a == b, f"{a!r} and {b!r} should be the same broker day"
    assert a != c, f"{a!r} and {c!r} should differ (broker day rollover)"


# ─── Fix #5 ─ rules_to_sim_config auto-enables execution.worst_case ──

@pytest.mark.asyncio
async def test_rules_to_sim_config_emits_execution_worst_case():
    from engines.rule_engine import rules_to_sim_config

    rule_doc = {
        "firm_name": "FTMO",
        "phase": "Challenge",
        "initial_balance": 100_000,
        "rules": {
            "daily_dd":      {"enabled": True, "type": "equity",  "max_pct": 5.0},
            "total_dd":      {"enabled": True, "type": "static",  "max_pct": 10.0},
            "profit_target": {"enabled": True, "target_pct": 10.0},
            "min_trading_days": {"enabled": True, "days": 4},
            "time_limit":    {"enabled": True, "calendar_days": 30},
            "consistency":   {"enabled": False},
            "position_sizing": {"enabled": True, "max_lot_per_trade": 20.0},
        },
    }
    cfg = await rules_to_sim_config(rule_doc)
    exec_cfg = cfg.get("execution")
    assert isinstance(exec_cfg, dict), "execution block missing"
    assert exec_cfg.get("enabled") is True, "execution.enabled must default True"
    assert exec_cfg.get("intrabar_mode") == "worst_case", (
        "intrabar_mode must default to 'worst_case' to activate the SL-before-TP flip"
    )

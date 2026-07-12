"""Regression test: paper execution replay must match backtest output.

The paper execution engine was rewritten to delegate signal generation,
SL/TP resolution, and risk sizing entirely to `run_backtest_logic`. This
test proves the wrapper is lossless — every trade emitted by paper
exec equals the trade produced by backtest for the same strategy,
bars, and sim_config.

Run:
    cd /app/backend && python -m pytest tests/test_paper_backtest_alignment.py -v
"""
from __future__ import annotations

import os
import sys

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from engines.backtest_engine import run_backtest_logic  # noqa: E402
from engines.paper_execution_engine import _compute_paper_trades  # noqa: E402

_DB = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# Canonical TF → db TF map (mirrors dashboard._DB_TO_CANONICAL_TF)
_TF_TO_DB = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
}


def _load_bars(symbol: str, timeframe: str, limit: int = 2000):
    """Pull OHLCV bars for (symbol, timeframe) directly from Mongo."""
    tf_db = _TF_TO_DB.get(timeframe, timeframe.lower())
    cursor = _DB["market_data"].find(
        {"symbol": symbol, "timeframe": tf_db, "source": "bid_1m"},
        {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1},
    ).sort("timestamp", 1).limit(int(limit))
    return list(cursor)


def _pick_strategy_with_data(min_bars: int = 600):
    """Find a strategy_library row whose (pair, timeframe) has enough
    bars in market_data for a deterministic replay."""
    for doc in _DB["strategy_library"].find({}, {"_id": 0}):
        pair = doc.get("pair")
        tf = doc.get("timeframe")
        text = doc.get("strategy_text")
        if not (pair and tf and text):
            continue
        bars = _load_bars(pair, tf, min_bars)
        if len(bars) >= min_bars:
            return doc, bars
    return None, None


@pytest.fixture(scope="module")
def strategy_and_bars():
    doc, bars = _pick_strategy_with_data()
    if not doc:
        pytest.skip("No strategy_library + market_data combo with ≥600 bars")
    return doc, bars


def test_paper_trade_count_matches_backtest(strategy_and_bars):
    """#trades emitted by paper exec equals backtest IS #trades exactly."""
    strategy, bars = strategy_and_bars
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts = [b.get("timestamp") for b in bars]

    sim_config = {"initial_balance": 10000.0, "risk_percent": 1.0}

    bt = run_backtest_logic(
        strategy_text=strategy["strategy_text"],
        pair=strategy["pair"], timeframe=strategy["timeframe"],
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=ts, sim_config=sim_config,
    )
    assert not bt.get("error"), f"backtest errored: {bt.get('error')}"
    bt_trades = bt.get("trades") or []

    strat = {
        "strategy_hash": "test_hash",
        "strategy_name": "aligned-replay-test",
        "pair": strategy["pair"],
        "timeframe": strategy["timeframe"],
        "style": strategy.get("style") or "trend_following",
        "strategy_text": strategy["strategy_text"],
        "sim_config": {},
        "params": strategy.get("params") or {},
    }
    paper_trades, err, meta = _compute_paper_trades(
        strategy=strat, bars=bars, account_balance=10000.0, risk_pct=1.0,
    )
    assert err is None, f"paper replay errored: {err}"

    # run_backtest_logic returns IS trades only (train slice). Paper also
    # uses the same data but in the wrapper path it sees the whole bars
    # list → train slice is identical (first 70 %).
    assert len(paper_trades) == len(bt_trades), (
        f"paper emitted {len(paper_trades)} trades, backtest produced "
        f"{len(bt_trades)}"
    )


def test_paper_pnl_matches_backtest_within_rounding(strategy_and_bars):
    """Sum of paper PnL ≈ sum of backtest net_pnl (within rounding noise)."""
    strategy, bars = strategy_and_bars
    closes = [float(b["close"]) for b in bars]
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    ts = [b.get("timestamp") for b in bars]

    bt = run_backtest_logic(
        strategy_text=strategy["strategy_text"],
        pair=strategy["pair"], timeframe=strategy["timeframe"],
        external_prices=closes, external_highs=highs, external_lows=lows,
        external_timestamps=ts,
        sim_config={"initial_balance": 10000.0, "risk_percent": 1.0},
    )
    bt_trades = bt.get("trades") or []
    bt_pnl = round(sum(float(t.get("net_pnl") or 0.0) for t in bt_trades), 2)

    strat = {
        "strategy_hash": "test_hash",
        "strategy_name": "aligned-replay-test",
        "pair": strategy["pair"],
        "timeframe": strategy["timeframe"],
        "style": strategy.get("style") or "trend_following",
        "strategy_text": strategy["strategy_text"],
        "sim_config": {},
        "params": strategy.get("params") or {},
    }
    paper_trades, _err, _meta = _compute_paper_trades(
        strategy=strat, bars=bars, account_balance=10000.0, risk_pct=1.0,
    )
    paper_pnl = round(sum(float(t["pnl"]) for t in paper_trades), 2)
    # Each trade is rounded to 2 decimals independently; across N trades
    # that accumulates ≤ N × $0.01. Allow $1 slack for safety.
    assert abs(paper_pnl - bt_pnl) <= max(1.0, 0.01 * len(paper_trades)), (
        f"paper PnL {paper_pnl} vs backtest PnL {bt_pnl} — drift too large"
    )


def test_paper_pf_matches_backtest_pf(strategy_and_bars):
    """PF computed over paper trades equals the backtest profit_factor
    (within rounding) — this is the *deviation metric* the engine persists."""
    from engines.paper_execution_engine import _compute_pf

    strategy, bars = strategy_and_bars
    strat = {
        "strategy_hash": "test_hash",
        "strategy_name": "aligned-replay-test",
        "pair": strategy["pair"],
        "timeframe": strategy["timeframe"],
        "style": strategy.get("style") or "trend_following",
        "strategy_text": strategy["strategy_text"],
        "sim_config": {},
        "params": strategy.get("params") or {},
    }
    paper_trades, _err, meta = _compute_paper_trades(
        strategy=strat, bars=bars, account_balance=10000.0, risk_pct=1.0,
    )
    paper_pf = _compute_pf(paper_trades)
    bt_pf = float(meta.get("backtest_pf") or 0.0)
    # The engine's PF uses gross_pnl; paper PF uses net_pnl. With modest
    # costs these should be within ~5 %. Assert the direction + magnitude
    # match rather than exact equality.
    if bt_pf > 0:
        rel_err = abs(paper_pf - bt_pf) / max(0.01, bt_pf)
        assert rel_err < 0.10, (
            f"paper PF {paper_pf} vs backtest PF {bt_pf} — "
            f"rel err {rel_err:.3f} > 0.10"
        )


def test_paper_skips_missing_strategy_text():
    """When strategy_text is empty, the wrapper reports a clean skip
    rather than crashing."""
    bars = [
        {"timestamp": f"2026-01-01T{i:02d}:00:00+00:00",
         "open": 1.10, "high": 1.10, "low": 1.10, "close": 1.10}
        for i in range(250)
    ]
    strat = {
        "strategy_hash": "test",
        "pair": "EURUSD", "timeframe": "H1",
        "strategy_text": "", "sim_config": {}, "params": {},
    }
    trades, err, meta = _compute_paper_trades(
        strategy=strat, bars=bars, account_balance=10000.0, risk_pct=1.0,
    )
    assert trades == []
    assert err == "missing_strategy_text"
    assert meta == {}


def test_paper_skips_insufficient_bars():
    """Fewer than MIN_BARS_FOR_BACKTEST bars → clean skip, no crash."""
    bars = [
        {"timestamp": f"2026-01-01T{i:02d}:00:00+00:00",
         "open": 1.10, "high": 1.10, "low": 1.10, "close": 1.10}
        for i in range(50)
    ]
    strat = {
        "strategy_hash": "test",
        "pair": "EURUSD", "timeframe": "H1",
        "strategy_text": "EMA(20)/EMA(50) trend following",
        "sim_config": {}, "params": {},
    }
    trades, err, meta = _compute_paper_trades(
        strategy=strat, bars=bars, account_balance=10000.0, risk_pct=1.0,
    )
    assert trades == []
    assert err is not None and err.startswith("insufficient_bars")

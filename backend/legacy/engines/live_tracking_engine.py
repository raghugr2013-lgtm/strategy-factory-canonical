"""
Live Performance Tracking (Paper Trading) Engine.
Processes new candles incrementally, tracks strategy state,
and computes live performance metrics. Uses same signal logic as backtest engine.
"""
from datetime import datetime, timezone
from engines.db import get_db
from engines.param_extractor import extract_params
import logging

logger = logging.getLogger(__name__)

# ── Signal functions (identical to backtest engine) ──

def _ema(prices, period):
    if not prices or period < 1:
        return [None] * len(prices)
    ema = [None] * len(prices)
    k = 2 / (period + 1)
    start = min(period - 1, len(prices) - 1)
    ema[start] = sum(prices[:start + 1]) / (start + 1)
    for i in range(start + 1, len(prices)):
        ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema


def _rsi(prices, period=14):
    rsi = [None] * len(prices)
    if len(prices) < period + 1:
        return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        d = prices[i] - prices[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag = sum(gains) / period
    al = sum(losses) / period
    rsi[period] = 100 - (100 / (1 + ag / al)) if al != 0 else 100
    for i in range(period + 1, len(prices)):
        d = prices[i] - prices[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        rsi[i] = 100 - (100 / (1 + ag / al)) if al != 0 else 100
    return rsi


def _macd(prices, fast=12, slow=26, signal=9):
    ema_fast = _ema(prices, fast)
    ema_slow = _ema(prices, slow)
    n = len(prices)
    line = [None] * n
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            line[i] = ema_fast[i] - ema_slow[i]
    valid = [v for v in line if v is not None]
    sig = _ema(valid, signal) if valid else []
    sig_full = [None] * n
    idx = 0
    for i in range(n):
        if line[i] is not None:
            if idx < len(sig):
                sig_full[i] = sig[idx]
            idx += 1
    hist = [None] * n
    for i in range(n):
        if line[i] is not None and sig_full[i] is not None:
            hist[i] = line[i] - sig_full[i]
    return line, sig_full, hist


def _signal_trend(i, prices, fast_ma, slow_ma, rsi_vals, rsi_cfg):
    if fast_ma[i] is None or slow_ma[i] is None or fast_ma[i-1] is None or slow_ma[i-1] is None:
        return None
    if fast_ma[i] > slow_ma[i] and fast_ma[i-1] <= slow_ma[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] < rsi_cfg.get("buy_threshold", 50):
            return None
        return "BUY"
    if fast_ma[i] < slow_ma[i] and fast_ma[i-1] >= slow_ma[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] > rsi_cfg.get("sell_threshold", 50):
            return None
        return "SELL"
    return None


def _signal_mean_rev(i, prices, rsi_vals, rsi_cfg, bb_upper, bb_lower):
    if not rsi_cfg or rsi_vals[i] is None:
        return None
    if rsi_vals[i] < rsi_cfg.get("buy_threshold", 30):
        if bb_lower[i] is not None and prices[i] > bb_lower[i]:
            return None
        return "BUY"
    if rsi_vals[i] > rsi_cfg.get("sell_threshold", 70):
        if bb_upper[i] is not None and prices[i] < bb_upper[i]:
            return None
        return "SELL"
    return None


def _signal_momentum(i, macd_line, macd_sig, rsi_vals, rsi_cfg):
    if macd_line[i] is None or macd_sig[i] is None or macd_line[i-1] is None or macd_sig[i-1] is None:
        return None
    if macd_line[i] > macd_sig[i] and macd_line[i-1] <= macd_sig[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] < rsi_cfg.get("buy_threshold", 50):
            return None
        return "BUY"
    if macd_line[i] < macd_sig[i] and macd_line[i-1] >= macd_sig[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] > rsi_cfg.get("sell_threshold", 50):
            return None
        return "SELL"
    return None


def _signal_breakout(i, prices, fast_ma, rsi_vals, rsi_cfg):
    if fast_ma[i] is None or fast_ma[i-1] is None:
        return None
    if prices[i] > fast_ma[i] and prices[i-1] <= fast_ma[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] < rsi_cfg.get("buy_threshold", 50):
            return None
        return "BUY"
    if prices[i] < fast_ma[i] and prices[i-1] >= fast_ma[i-1]:
        if rsi_cfg and rsi_vals[i] is not None and rsi_vals[i] > rsi_cfg.get("sell_threshold", 50):
            return None
        return "SELL"
    return None


def _classify_status(bt_metrics: dict, live_metrics: dict) -> str:
    """Compare live vs backtest and classify: STABLE, WARNING, FAILING."""
    bt_wr = bt_metrics.get("win_rate", 0)
    live_wr = live_metrics.get("win_rate", 0)
    bt_dd = bt_metrics.get("max_drawdown_pct", 0)
    live_dd = live_metrics.get("max_drawdown_pct", 0)
    bt_pf = bt_metrics.get("profit_factor", 0)
    live_pf = live_metrics.get("profit_factor", 0)

    issues = 0
    if live_dd > bt_dd * 1.5 + 5:
        issues += 2
    if live_wr < bt_wr * 0.7 - 5:
        issues += 1
    if live_pf < bt_pf * 0.5 and live_pf < 1.0:
        issues += 1
    if live_metrics.get("total_return_pct", 0) < -10:
        issues += 2

    if issues >= 3:
        return "FAILING"
    elif issues >= 1:
        return "WARNING"
    return "STABLE"


def process_strategy_live(strategy: dict, prices: list, timestamps: list) -> dict:
    """
    Process a strategy against prices incrementally.
    Returns full live state: equity, trades, metrics, status.
    Uses the same signal logic as the backtest engine.
    """
    st = strategy.get("strategy_text", "")
    extraction = extract_params(st)
    extracted = extraction.get("extracted", {})

    fast_period = extracted.get("fast_ma", 5)
    slow_period = extracted.get("slow_ma", 15)
    sl_pips = extracted.get("stop_loss_pips", 20)
    tp_pips = extracted.get("take_profit_pips", 40)
    strategy_type = extracted.get("strategy_type", "trend_following")

    # Indicator configs
    rsi_cfg = None
    if extracted.get("rsi_period"):
        rsi_cfg = {"period": extracted["rsi_period"], "buy_threshold": extracted.get("rsi_buy_threshold", 50), "sell_threshold": extracted.get("rsi_sell_threshold", 50)}

    macd_cfg = None
    if extracted.get("macd"):
        macd_cfg = extracted["macd"]

    # Compute indicators
    fast_ma = _ema(prices, fast_period)
    slow_ma = _ema(prices, slow_period)
    rsi_vals = _rsi(prices, rsi_cfg["period"]) if rsi_cfg else [None] * len(prices)
    macd_line, macd_sig, macd_hist = _macd(prices, macd_cfg["fast"], macd_cfg["slow"], macd_cfg["signal"]) if macd_cfg else ([None]*len(prices), [None]*len(prices), [None]*len(prices))

    # Pip settings
    pair = strategy.get("pair", "EURUSD")
    pip_unit = 0.01 if "JPY" in pair or pair in ("XAUUSD", "US100", "BTCUSD", "ETHUSD") else 0.0001
    pip_value = 10.0
    initial_balance = 10000.0
    risk_pct = 1.0
    spread_pips = 1.5

    warmup = max(slow_period + 1, fast_period + 1)
    if macd_cfg:
        warmup = max(warmup, macd_cfg["slow"] + macd_cfg["signal"] + 1)

    trades = []
    position = None
    balance = initial_balance
    peak = initial_balance
    max_dd = 0
    equity = [initial_balance]

    for i in range(warmup, len(prices)):
        signal = None
        if position is None:
            if strategy_type == "mean_reversion":
                signal = _signal_mean_rev(i, prices, rsi_vals, rsi_cfg, [None]*len(prices), [None]*len(prices))
            elif strategy_type == "momentum":
                signal = _signal_momentum(i, macd_line, macd_sig, rsi_vals, rsi_cfg)
            elif strategy_type == "breakout":
                signal = _signal_breakout(i, prices, fast_ma, rsi_vals, rsi_cfg)
            else:
                signal = _signal_trend(i, prices, fast_ma, slow_ma, rsi_vals, rsi_cfg)

        # Entry
        if signal and position is None:
            entry_price = prices[i] + (spread_pips / 2) * pip_unit * (1 if signal == "BUY" else -1)
            risk_amount = balance * (risk_pct / 100)
            lot_size = round(max(risk_amount / (sl_pips * pip_value), 0.01), 2)
            position = {"entry_price": entry_price, "raw": prices[i], "idx": i, "dir": signal, "lot": lot_size}

        # Exit
        elif position is not None:
            entry = position["entry_price"]
            d = position["dir"]
            pnl_pips = ((prices[i] - entry) / pip_unit) if d == "BUY" else ((entry - prices[i]) / pip_unit)
            hit_sl = pnl_pips <= -sl_pips
            hit_tp = pnl_pips >= tp_pips

            # Reverse signal check
            rev = None
            if strategy_type == "mean_reversion":
                rev = _signal_mean_rev(i, prices, rsi_vals, rsi_cfg, [None]*len(prices), [None]*len(prices))
            elif strategy_type == "momentum":
                rev = _signal_momentum(i, macd_line, macd_sig, rsi_vals, rsi_cfg)
            elif strategy_type == "breakout":
                rev = _signal_breakout(i, prices, fast_ma, rsi_vals, rsi_cfg)
            else:
                rev = _signal_trend(i, prices, fast_ma, slow_ma, rsi_vals, rsi_cfg)
            reverse = rev is not None and rev != d

            if hit_sl or hit_tp or reverse or i == len(prices) - 1:
                exit_price = prices[i] - (spread_pips / 2) * pip_unit * (1 if d == "BUY" else -1)
                final_pips = ((exit_price - entry) / pip_unit) if d == "BUY" else ((entry - exit_price) / pip_unit)
                net_pnl = final_pips * pip_value * position["lot"] - 7.0 * position["lot"]
                balance += net_pnl
                if balance > peak:
                    peak = balance
                dd = (peak - balance) / peak * 100 if peak > 0 else 0
                if dd > max_dd:
                    max_dd = dd

                reason = "TP" if hit_tp else ("SL" if hit_sl else ("REV" if reverse else "CLOSE"))
                trades.append({
                    "direction": d, "entry": round(position["raw"], 5), "exit": round(prices[i], 5),
                    "pnl_pips": round(final_pips, 1), "net_pnl": round(net_pnl, 2), "balance": round(balance, 2),
                    "reason": reason, "timestamp": timestamps[i] if i < len(timestamps) else None,
                })
                equity.append(round(balance, 2))
                position = None

    # Metrics
    total = len(trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] <= 0]
    wr = (len(wins) / total * 100) if total > 0 else 0
    gw = abs(sum(t["net_pnl"] for t in wins))
    gl = abs(sum(t["net_pnl"] for t in losses))
    pf = round(gw / gl, 2) if gl > 0 else 0
    net_profit = balance - initial_balance
    ret_pct = (net_profit / initial_balance) * 100

    return {
        "total_trades": total, "win_rate": round(wr, 1), "profit_factor": pf,
        "net_profit": round(net_profit, 2), "total_return_pct": round(ret_pct, 2),
        "max_drawdown_pct": round(max_dd, 2), "final_balance": round(balance, 2),
        "equity_curve": equity, "trades": trades,
        "open_position": position is not None,
        "candles_processed": len(prices),
    }


async def update_tracking(strategy_id: str) -> dict:
    """
    Fetch latest data for a tracked strategy, run paper trading,
    compute metrics, compare with backtest, and save state.
    """
    db = get_db()
    from bson import ObjectId

    # Load tracking record
    tracking = await db.live_tracking.find_one({"strategy_id": strategy_id})
    if not tracking:
        return {"error": "Tracking not found"}

    # Load strategy from library
    strat = await db.strategies.find_one({"_id": ObjectId(strategy_id)})
    if not strat:
        return {"error": "Strategy not found"}

    strat_dict = {k: v for k, v in strat.items() if k != "_id"}
    strat_dict["id"] = str(strat["_id"])

    pair = strat_dict.get("pair", "EURUSD")
    tf_map = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}
    raw_tf = strat_dict.get("timeframe", "H1")
    tf = tf_map.get(raw_tf, raw_tf.lower())

    # Fetch latest candles from DB
    cursor = db.market_data.find(
        {"symbol": pair, "timeframe": tf},
        {"_id": 0, "close": 1, "timestamp": 1},
    ).sort("timestamp", 1)
    docs = await cursor.to_list(length=None)

    if not docs or len(docs) < 20:
        return {"error": f"Not enough data for {pair}/{tf} ({len(docs)} candles)"}

    prices = [d["close"] for d in docs]
    timestamps = [d["timestamp"] for d in docs]

    # Run paper trading
    live = process_strategy_live(strat_dict, prices, timestamps)

    # Compare with backtest
    bt = strat_dict.get("backtest_results", {}) or strat_dict.get("metrics", {})
    status = _classify_status(bt, live)

    # Build alerts
    alerts = []
    if live["max_drawdown_pct"] > 15:
        alerts.append({"type": "DRAWDOWN", "message": f"Live DD {live['max_drawdown_pct']}% exceeds 15% threshold"})
    if status == "FAILING":
        alerts.append({"type": "FAILING", "message": "Strategy performance significantly below backtest"})
    if live.get("total_return_pct", 0) < -10:
        alerts.append({"type": "LOSS", "message": f"Total loss {live['total_return_pct']}% exceeds -10% threshold"})

    # Save state
    now = datetime.now(timezone.utc).isoformat()

    # Track consecutive failures for auto-disable
    prev_failures = tracking.get("consecutive_failures", 0)
    if status == "FAILING":
        consecutive_failures = prev_failures + 1
    else:
        consecutive_failures = 0

    # Auto-disable check
    auto_disable_enabled = tracking.get("auto_disable", True)
    failure_threshold = tracking.get("failure_threshold", 3)
    disable_reason = None

    if auto_disable_enabled and consecutive_failures >= failure_threshold:
        # Build reason
        reasons = []
        if live["max_drawdown_pct"] > 15:
            reasons.append(f"DD {live['max_drawdown_pct']:.1f}%")
        if live.get("total_return_pct", 0) < -10:
            reasons.append(f"Loss {live['total_return_pct']:.1f}%")
        reasons.append(f"FAILING for {consecutive_failures} consecutive updates")
        disable_reason = "; ".join(reasons)

        alerts.append({
            "type": "AUTO_DISABLED",
            "message": f"Auto-disabled: {disable_reason}",
        })

        # Stop tracking
        await db.live_tracking.update_one(
            {"strategy_id": strategy_id},
            {"$set": {
                "live_metrics": live,
                "status": "AUTO_DISABLED",
                "alerts": alerts,
                "last_updated": now,
                "candles_count": len(prices),
                "last_timestamp": timestamps[-1] if timestamps else None,
                "consecutive_failures": consecutive_failures,
                "active": False,
                "auto_disabled": True,
                "disable_reason": disable_reason,
                "disabled_at": now,
            }},
        )

        # Update strategy in library with "Live-Tested: Failed" tag
        from bson import ObjectId as ObjId
        await db.strategies.update_one(
            {"_id": ObjId(strategy_id)},
            {"$set": {
                "live_test_result": "Failed",
                "live_test_reason": disable_reason,
                "live_test_date": now,
            }},
        )

        return {
            "strategy_id": strategy_id,
            "pair": pair,
            "timeframe": raw_tf,
            "status": "AUTO_DISABLED",
            "auto_disabled": True,
            "disable_reason": disable_reason,
            "consecutive_failures": consecutive_failures,
            "live_metrics": live,
            "backtest_metrics": {
                "win_rate": bt.get("win_rate", 0),
                "profit_factor": bt.get("profit_factor", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "total_return_pct": bt.get("total_return_pct", 0),
            },
            "alerts": alerts,
            "candles_count": len(prices),
            "last_updated": now,
        }

    await db.live_tracking.update_one(
        {"strategy_id": strategy_id},
        {"$set": {
            "live_metrics": live,
            "status": status,
            "alerts": alerts,
            "last_updated": now,
            "candles_count": len(prices),
            "last_timestamp": timestamps[-1] if timestamps else None,
            "consecutive_failures": consecutive_failures,
        }},
    )

    return {
        "strategy_id": strategy_id,
        "pair": pair,
        "timeframe": raw_tf,
        "status": status,
        "consecutive_failures": consecutive_failures,
        "live_metrics": live,
        "backtest_metrics": {
            "win_rate": bt.get("win_rate", 0),
            "profit_factor": bt.get("profit_factor", 0),
            "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
            "total_return_pct": bt.get("total_return_pct", 0),
        },
        "alerts": alerts,
        "candles_count": len(prices),
        "last_updated": now,
    }

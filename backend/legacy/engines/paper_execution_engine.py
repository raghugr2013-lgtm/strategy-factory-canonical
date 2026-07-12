"""
Paper Execution Engine — Safe, historical-replay paper trading layer.

This is the FINAL SAFE STEP before real broker/cTrader execution. It runs
portfolio-approved strategies against historical BID/BI5 market data
(stored in the `market_data` collection) using the authoritative
`backtest_engine.run_backtest_logic` as the SOLE source of trade
generation. Paper execution === backtest execution by construction:
same signal logic, same ATR-based SL/TP, same quality filter, same
ruin floor, same weekend close, same Phase 5 risk calibration.

Design goals:
    • Signal logic reuses run_backtest_logic (NO duplication).
    • SL / TP come directly from backtest engine (ATR-based for
      non-forex pairs, pip-based for forex — whichever the strategy
      declared).
    • Daily DD + Total DD hard halts (integrates with monitoring limits).
    • Per-strategy running PF vs backtest PF comparison.
    • Accelerated replay (tick_ms default = 100 ms / emitted trade).
    • Background asyncio loop (cancellable, single-active-run).

ADDITIVE: does NOT touch existing
    • engines/execution_engine.py         (backtest realism)
    • engines/execution_manager.py        (Phase-8 cBot sessions)
    • engines/trade_runner_engine.py      (Phase-5 synthetic runner)
    • engines/portfolio_builder_engine.py (read-only)
    • engines/portfolio_engine.py         (read-only)

Collections owned by this engine:
    execution_runs             — one doc per run (lifecycle + aggregate state)
    execution_trades           — one doc per simulated trade
    execution_equity           — equity-curve snapshots (per emitted trade)
    strategy_deviation_metrics — running PF vs backtest PF history
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.backtest_engine import run_backtest_logic
from engines.db import get_db

logger = logging.getLogger(__name__)

# ── Collections (new, isolated) ─────────────────────────────────────
RUNS_COLL = "execution_runs"
TRADES_COLL = "execution_trades"
EQUITY_COLL = "execution_equity"
DEVIATION_COLL = "strategy_deviation_metrics"

# Upstream (read-only)
PORTFOLIO_BUILDER_COLL = "portfolio_builder_runs"
PORTFOLIO_COLL = "portfolios"
MARKET_DATA_COLL = "market_data"

# ── Defaults (per spec) ─────────────────────────────────────────────
DEFAULT_ACCOUNT_BALANCE = 10_000.0
DEFAULT_RISK_PCT = 1.0            # % per trade
DEFAULT_DAILY_LOSS_LIMIT_PCT = 5.0
DEFAULT_TOTAL_LOSS_LIMIT_PCT = 10.0
DEFAULT_TICK_MS = 100             # accelerated bar: ~100ms per replay bar
DEFAULT_BARS_LIMIT = 2_000        # cap bars replayed per run
DEFAULT_SOURCE = "bid_1m"
MAX_TRADES_IN_STATUS = 25
MIN_BARS_FOR_BACKTEST = 200       # run_backtest_logic hard floor

_lock = asyncio.Lock()

# Runtime registry: run_id → asyncio.Task. Cleared on task completion.
_TASKS: Dict[str, asyncio.Task] = {}


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date_of(ts_iso: Optional[str]) -> str:
    if ts_iso and len(ts_iso) >= 10:
        return ts_iso[:10]
    return datetime.now(timezone.utc).date().isoformat()


def _pip_size_for(pair: Optional[str]) -> float:
    """Return pip size in price units. JPY pairs use 0.01, the rest 0.0001.

    R2 — consolidated through ``engines.market_universe_adapter.resolve_pip_size``.
    Byte-identical when the flag is OFF (the adapter falls back to the
    same substring rules).
    """
    try:
        from engines.market_universe_adapter import (
            resolve_pip_size as _adapter,
        )
        return _adapter(pair)
    except Exception:                                       # pragma: no cover
        p = (pair or "").upper()
        if "JPY" in p:
            return 0.01
        return 0.0001


def _compute_pf(trades: List[Dict[str, Any]]) -> float:
    """Classic profit factor = sum(wins) / sum(|losses|). Returns 0 when no losses."""
    wins = sum(float(t.get("pnl") or 0) for t in trades if (t.get("pnl") or 0) > 0)
    losses = sum(-float(t.get("pnl") or 0) for t in trades if (t.get("pnl") or 0) < 0)
    if losses <= 0:
        return round(wins, 3) if wins > 0 else 0.0
    return round(wins / losses, 3)


# ═════════════════════════════════════════════════════════════════════
# Portfolio loading (read-only)
# ═════════════════════════════════════════════════════════════════════

async def _load_portfolio_strategies(portfolio_id: Optional[str]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Load strategies from an approved portfolio. Tries, in order:
      1. `multi_asset_portfolios` by portfolio_id (P1 rollout — preferred;
         carries `strategy_text` + `params` + `phase5` per strategy so
         paper exec replays the SAME backtest the user approved).
      2. `portfolio_builder_runs` by portfolio_id (Phase 4 builder, legacy).
      3. `portfolios` by run_id (Phase 7 library portfolio, legacy).
         Enriches each strategy with `strategy_text` looked up from
         `strategy_library` by fingerprint / strategy_id.
      4. Most recent doc across these collections when portfolio_id is None.

    Returns (resolved_portfolio_id, [strategy dicts normalised for this engine]).
    Each strategy dict contains:
        strategy_hash, strategy_name, pair, timeframe, style,
        strategy_text  (REQUIRED — paper exec skips strategies without it),
        sim_config,    (carried through to backtest_engine on replay),
        risk_pct, backtest_pf, backtest_win_rate, params.
    """
    db = get_db()

    async def _enrich_with_text(fingerprint: Optional[str], strategy_id: Optional[str]) -> Optional[Dict[str, Any]]:
        """Look up a strategy in `strategy_library` by fingerprint first,
        then by _id (ObjectId). Returns the library doc or None."""
        if not fingerprint and not strategy_id:
            return None
        if fingerprint:
            doc = await db["strategy_library"].find_one(
                {"fingerprint": fingerprint}, {"_id": 0},
            )
            if doc:
                return doc
        if strategy_id:
            # `strategy_id` may be a raw 24-hex ObjectId or a "PAIR:ObjectId"
            # form (as stored on multi_asset_portfolios).
            raw = strategy_id.split(":")[-1]
            try:
                from bson import ObjectId
                doc = await db["strategy_library"].find_one(
                    {"_id": ObjectId(raw)}, {"_id": 0},
                )
                if doc:
                    return doc
            except Exception:
                pass
        return None

    async def _try_multi_asset(pid: Optional[str]):
        q = {"portfolio_id": pid} if pid else {}
        sort_spec = None if pid else [("created_at", -1)]
        find_kwargs = {"sort": sort_spec} if sort_spec else {}
        doc = await db["multi_asset_portfolios"].find_one(q, {"_id": 0}, **find_kwargs)
        if not doc:
            return None
        strategies = doc.get("strategies") or []
        contrib = doc.get("asset_contributions_pct") or {}
        normalised = []
        for s in strategies:
            sid = s.get("strategy_id") or s.get("strategy_hash")
            if not sid:
                continue
            bt = s.get("backtest") or {}
            pair = s.get("pair") or "EURUSD"
            # Derive per-strategy risk_pct from asset contribution share
            # (fallback to default). Contributions sum to 100.
            asset_share = float(contrib.get(pair) or 0.0) / 100.0
            # Enrich with strategy_text + params from strategy_library
            # when the portfolio card was persisted without them (pre-P0
            # saves). paper exec === backtest is impossible without text.
            strategy_text = s.get("strategy_text") or ""
            params = dict(s.get("params") or {})
            style = s.get("style") or "trend_following"
            if not strategy_text:
                lib = await _enrich_with_text(s.get("fingerprint"), sid)
                if lib:
                    strategy_text = lib.get("strategy_text") or ""
                    params = params or dict(lib.get("params") or {})
                    style = style if style != "trend_following" else (lib.get("style") or style)
            normalised.append({
                "strategy_hash": str(sid),
                "strategy_name": s.get("strategy_name") or f"Strategy {str(sid)[:6]}",
                "pair": pair,
                "timeframe": s.get("timeframe") or "H1",
                "style": style,
                "strategy_text": strategy_text,
                "sim_config": dict(s.get("sim_config") or {}),
                "params": params,
                "risk_pct": float(DEFAULT_RISK_PCT * (asset_share if asset_share > 0 else 1.0)),
                "backtest_pf": float(bt.get("profit_factor") or 0.0),
                "backtest_win_rate": float(bt.get("win_rate") or 0.0),
            })
        return (doc.get("portfolio_id"), normalised) if normalised else None

    async def _try_pb(pid: Optional[str]):
        q = {"portfolio_id": pid} if pid else {}
        doc = await db[PORTFOLIO_BUILDER_COLL].find_one(
            q, {"_id": 0}, sort=[("saved_at", -1)] if not pid else None,
        )
        if not doc:
            return None
        meta = doc.get("meta") or {}
        strategies = meta.get("strategies") or []
        allocation = meta.get("allocation") or {}
        normalised = []
        for s in strategies:
            h = s.get("strategy_hash") or s.get("strategy_id") or s.get("_id")
            if not h:
                continue
            alloc = allocation.get(h) or {}
            enriched = None
            fp = s.get("fingerprint") or s.get("strategy_fingerprint")
            if fp:
                enriched = await _enrich_with_text(fp, None)
            normalised.append({
                "strategy_hash": str(h),
                "strategy_name": s.get("strategy_name") or s.get("name") or f"Strategy {str(h)[:6]}",
                "pair": s.get("pair") or (enriched.get("pair") if enriched else "EURUSD"),
                "timeframe": s.get("timeframe") or (enriched.get("timeframe") if enriched else "M15"),
                "style": s.get("style") or s.get("strategy_type") or (enriched.get("style") if enriched else "trend_following"),
                "strategy_text": s.get("strategy_text") or (enriched.get("strategy_text") if enriched else ""),
                "sim_config": dict(s.get("sim_config") or (enriched.get("sim_config") if enriched else {}) or {}),
                "params": dict(s.get("params") or (enriched.get("params") if enriched else {}) or {}),
                "risk_pct": float(alloc.get("risk_pct") or s.get("risk_pct") or DEFAULT_RISK_PCT),
                "backtest_pf": float(s.get("strategy_best_pf") or s.get("profit_factor") or 0.0),
                "backtest_win_rate": float(s.get("win_rate") or 0.0),
            })
        return (doc.get("portfolio_id"), normalised) if normalised else None

    async def _try_portfolios(pid: Optional[str]):
        q = {"run_id": pid} if pid else {}
        doc = await db[PORTFOLIO_COLL].find_one(
            q, {"_id": 0}, sort=[("built_at", -1)] if not pid else None,
        )
        if not doc:
            return None
        strategies = doc.get("strategies") or []
        allocation = {a.get("strategy_id"): a for a in (doc.get("allocation") or [])}
        normalised = []
        for s in strategies:
            sid = s.get("strategy_id") or s.get("strategy_hash")
            if not sid:
                continue
            a = allocation.get(sid) or {}
            enriched = None
            fp = s.get("fingerprint")
            if fp:
                enriched = await _enrich_with_text(fp, None)
            normalised.append({
                "strategy_hash": str(sid),
                "strategy_name": s.get("strategy_name") or s.get("name") or f"Strategy {str(sid)[:6]}",
                "pair": s.get("pair") or (enriched.get("pair") if enriched else "EURUSD"),
                "timeframe": s.get("timeframe") or (enriched.get("timeframe") if enriched else "M15"),
                "style": s.get("style") or s.get("strategy_type") or (enriched.get("style") if enriched else "trend_following"),
                "strategy_text": s.get("strategy_text") or (enriched.get("strategy_text") if enriched else ""),
                "sim_config": dict(s.get("sim_config") or (enriched.get("sim_config") if enriched else {}) or {}),
                "params": dict(s.get("params") or (enriched.get("params") if enriched else {}) or {}),
                "risk_pct": float(a.get("risk_per_trade_pct") or DEFAULT_RISK_PCT),
                "backtest_pf": float(s.get("profit_factor") or (enriched.get("profit_factor") if enriched else 0.0) or 0.0),
                "backtest_win_rate": float(s.get("win_rate") or 0.0),
            })
        return (doc.get("run_id"), normalised) if normalised else None

    for fn in (_try_multi_asset, _try_pb, _try_portfolios):
        r = await fn(portfolio_id)
        if r:
            return r

    raise ValueError(
        "No approved portfolio available. Build one via Multi-Asset Rollout first." if portfolio_id is None
        else f"portfolio not found: {portfolio_id}"
    )


# ═════════════════════════════════════════════════════════════════════
# Market-bar source
# ═════════════════════════════════════════════════════════════════════


async def _load_bars(
    symbol: str, timeframe: str, source: str, limit: int,
) -> List[Dict[str, Any]]:
    """Load real OHLC bars for (symbol, source, timeframe) via the
    unified data-access layer.

    Paper execution is strict: it uses REAL data only. If auto-recovery
    fails to populate the minimum bars for `timeframe`, returns an empty
    list. The run loop then marks the strategy as
    `skipped — insufficient_bars` and continues with the others
    (auto systems must never break due to data).
    """
    from engines.data_access import load_with_recovery
    res = await load_with_recovery(
        symbol, timeframe, auto_recover=True, source=source,
    )
    bars = res["bars"]
    if not bars:
        return []
    if limit and len(bars) > int(limit):
        bars = bars[:int(limit)]
    return bars


# ═════════════════════════════════════════════════════════════════════
# Backtest-driven trade precomputation (paper === backtest)
# ═════════════════════════════════════════════════════════════════════

def _split_ohlc(bars: List[Dict[str, Any]]) -> Tuple[List[float], List[float], List[float], List[Any]]:
    """Split a bar list into (closes, highs, lows, timestamps) arrays
    aligned by index — the shape run_backtest_logic expects."""
    closes, highs, lows, ts = [], [], [], []
    for b in bars:
        closes.append(float(b["close"]))
        highs.append(float(b["high"]))
        lows.append(float(b["low"]))
        ts.append(b.get("timestamp"))
    return closes, highs, lows, ts


def _merge_sim_config(
    strategy_sim: Optional[Dict[str, Any]],
    run_overrides: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge strategy-level sim_config with run-level overrides.
    Run overrides win so operator-set account_balance / risk_percent
    propagate into position sizing."""
    merged: Dict[str, Any] = {}
    if strategy_sim:
        merged.update(strategy_sim)
    if run_overrides:
        merged.update({k: v for k, v in run_overrides.items() if v is not None})
    return merged


def _compute_paper_trades(
    *,
    strategy: Dict[str, Any],
    bars: List[Dict[str, Any]],
    account_balance: float,
    risk_pct: float,
) -> Tuple[List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """Run run_backtest_logic on the loaded bars and return the
    authoritative trade list for this strategy. paper == backtest.

    Returns (trades, error_msg, meta). When error_msg is non-None the
    strategy has no replayable trades (insufficient data / missing
    strategy_text / backtest error) and the caller should skip it.
    """
    strategy_text = (strategy.get("strategy_text") or "").strip()
    if not strategy_text:
        return [], "missing_strategy_text", {}

    if len(bars) < MIN_BARS_FOR_BACKTEST:
        return [], f"insufficient_bars:{len(bars)}<{MIN_BARS_FOR_BACKTEST}", {}

    closes, highs, lows, timestamps = _split_ohlc(bars)
    sim_config = _merge_sim_config(
        strategy.get("sim_config"),
        {
            "initial_balance": float(account_balance),
            "risk_percent": float(risk_pct),
        },
    )

    try:
        result = run_backtest_logic(
            strategy_text=strategy_text,
            pair=strategy["pair"],
            timeframe=strategy["timeframe"],
            external_prices=closes,
            external_highs=highs,
            external_lows=lows,
            external_timestamps=timestamps,
            sim_config=sim_config,
            param_overrides=(strategy.get("params") or None),
            data_source="real",
            data_points=len(closes),
        )
    except Exception as e:
        logger.exception("paper-exec: backtest replay failed for %s", strategy.get("strategy_hash"))
        return [], f"backtest_exception:{e}", {}

    if result.get("error"):
        return [], str(result.get("error")), {}

    raw_trades = result.get("trades") or []
    meta = {
        "backtest_pf": float(result.get("profit_factor") or 0.0),
        "backtest_oos_pf": float(result.get("oos_profit_factor") or 0.0),
        "backtest_total_trades": int(result.get("total_trades") or 0),
        "backtest_max_dd_pct": float(result.get("max_drawdown_pct") or 0.0),
        "phase5": result.get("_phase5_risk_calibration") or {},
        "phase4": result.get("_phase4_signal_quality") or {},
    }

    # Normalise trades into the paper-execution schema. We preserve the
    # authoritative fields from backtest (SL/TP price, direction,
    # entry/exit price, net_pnl, lot_size) so "paper PF" reads identical
    # to "backtest PF".
    pair = strategy["pair"]
    pip = _pip_size_for(pair)
    normalised: List[Dict[str, Any]] = []
    for t in raw_trades:
        entry_idx = int(t.get("entry_idx") or 0)
        exit_idx = int(t.get("exit_idx") or entry_idx)
        entry_px = float(t.get("entry_price") or 0.0)
        exit_px = float(t.get("exit_price") or 0.0)
        sl_px = float(t.get("sl_price") or t.get("sl") or 0.0)
        tp_px = float(t.get("tp_price") or t.get("tp") or 0.0)
        sl_pips = abs(entry_px - sl_px) / pip if pip > 0 and sl_px else 0.0
        tp_pips = abs(tp_px - entry_px) / pip if pip > 0 and tp_px else 0.0
        reward_r = round(tp_pips / max(0.1, sl_pips), 2) if sl_pips else 0.0
        direction = str(t.get("direction") or t.get("side") or "BUY").upper()
        net_pnl = float(t.get("net_pnl") or 0.0)
        result_flag = "WIN" if net_pnl > 0 else ("LOSS" if net_pnl < 0 else "FLAT")
        risk_usd = float(t.get("sl_loss_amount") or 0.0)
        lot = float(t.get("lot_size") or t.get("lots") or 0.0)
        entry_ts = bars[entry_idx].get("timestamp") if entry_idx < len(bars) else None
        exit_ts = bars[exit_idx].get("timestamp") if exit_idx < len(bars) else None

        normalised.append({
            "direction": direction,
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "entry_price": entry_px,
            "exit_price": exit_px,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "sl_price": sl_px,
            "tp_price": tp_px,
            "sl_pips": round(sl_pips, 2),
            "tp_pips": round(tp_pips, 2),
            "lot_size": lot,
            "risk_usd": round(risk_usd, 2),
            "reward_ratio": reward_r,
            "exit_reason": t.get("result") or t.get("outcome") or "flat",
            "pnl": round(net_pnl, 2),
            "result": result_flag,
            "entry_quality_score": t.get("entry_quality_score"),
            "mae_usd": t.get("mae_usd"),
            "mfe_usd": t.get("mfe_usd"),
        })
    return normalised, None, meta


# ═════════════════════════════════════════════════════════════════════
# Deviation tracking
# ═════════════════════════════════════════════════════════════════════

async def _persist_deviation_snapshot(
    run_id: str, strategy_hash: str, running_pf: float,
    backtest_pf: float, trades_count: int,
) -> None:
    """Append a PF deviation snapshot into `strategy_deviation_metrics`."""
    db = get_db()
    dev_pct = None
    if backtest_pf and backtest_pf > 0:
        dev_pct = round((running_pf - backtest_pf) / backtest_pf * 100.0, 2)
    await db[DEVIATION_COLL].insert_one({
        "run_id": run_id,
        "strategy_hash": strategy_hash,
        "running_pf": running_pf,
        "backtest_pf": backtest_pf,
        "pf_deviation_pct": dev_pct,
        "trades_count": trades_count,
        "sampled_at": _now_iso(),
    })


# ═════════════════════════════════════════════════════════════════════
# Core replay loop (one run, per strategy)
# ═════════════════════════════════════════════════════════════════════

async def _run_loop(run_id: str) -> None:
    """Background replay loop. Loads bars once per (pair, timeframe);
    precomputes the authoritative trade list per strategy via
    run_backtest_logic; then streams trades in chronological order
    (by exit bar) applying PnL to the shared account equity and
    enforcing daily/total DD halts."""
    db = get_db()
    try:
        run = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})
        if not run:
            return

        tick_ms = int(run.get("tick_ms") or DEFAULT_TICK_MS)
        bars_limit = int(run.get("bars_limit") or DEFAULT_BARS_LIMIT)
        source = run.get("source") or DEFAULT_SOURCE

        # Pre-load bars per (pair, timeframe) — shared across strategies
        # running the same symbol to save DB round-trips. Paper exec is
        # strict: REAL data only (b1 decision). When recovery fails the
        # corresponding strategies will be skipped in the precompute
        # loop with `insufficient_bars` and the run continues with
        # whichever pairs DID recover.
        bars_cache: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        bars_meta: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for s in run["strategies"]:
            key = (s["pair"], s["timeframe"])
            if key in bars_cache:
                continue
            bars = await _load_bars(key[0], key[1], source, bars_limit)
            bars_cache[key] = bars
            bars_meta[key] = {
                "synthetic": False,
                "count": len(bars),
                "available": bool(bars),
            }

        # Pre-compute the authoritative trade list per strategy via the
        # backtest engine. paper === backtest by construction.
        account_start = float(run["account_balance_start"])
        precomputed: Dict[str, Dict[str, Any]] = {}
        skipped: Dict[str, str] = {}
        for s in run["strategies"]:
            sh = s["strategy_hash"]
            key = (s["pair"], s["timeframe"])
            bars = bars_cache[key]
            trades, err, meta = await asyncio.to_thread(
                _compute_paper_trades,
                strategy=s,
                bars=bars,
                account_balance=account_start,
                risk_pct=float(s.get("risk_pct") or DEFAULT_RISK_PCT),
            )
            if err:
                skipped[sh] = err
                logger.warning("paper-exec: strategy %s skipped — %s", sh, err)
                continue
            precomputed[sh] = {"trades": trades, "meta": meta}

        # Build merged chronological event stream: each event is one
        # completed trade keyed by (exit_idx, entry_idx, strategy_hash)
        # so same-exit-bar trades resolve deterministically.
        events: List[Tuple[int, int, str, Dict[str, Any]]] = []
        for sh, payload in precomputed.items():
            for t in payload["trades"]:
                events.append((t["exit_idx"], t["entry_idx"], sh, t))
        events.sort(key=lambda e: (e[0], e[1], e[2]))

        await db[RUNS_COLL].update_one(
            {"run_id": run_id},
            {"$set": {
                "bars_meta": {f"{k[0]}|{k[1]}": v for k, v in bars_meta.items()},
                "bars_status": "loaded",
                "precomputed_trade_counts": {sh: len(p["trades"]) for sh, p in precomputed.items()},
                "skipped_strategies": skipped,
                "total_precomputed_trades": len(events),
            }},
        )

        # If every strategy was skipped, mark the run as errored-out so
        # the caller can fix the portfolio.
        if not precomputed and skipped:
            await db[RUNS_COLL].update_one(
                {"run_id": run_id},
                {"$set": {
                    "status": "errored",
                    "error": f"all_strategies_skipped: {skipped}",
                    "halted_at": _now_iso(),
                }},
            )
            logger.error("paper-exec: run %s errored — all strategies skipped: %s", run_id, skipped)
            return

        # Per-strategy running state
        strat_trades: Dict[str, List[Dict[str, Any]]] = {sh: [] for sh in precomputed}
        equity = account_start
        peak_equity = account_start
        daily_start_equity = account_start
        daily_start_date = _utc_date_of(run["started_at"])
        max_dd_pct = 0.0

        # Deviation alert bookkeeping (in-memory + persisted per-run doc
        # on each emission). Streak counts consecutive PF samples above
        # the threshold; once streak hits persistence target we fire.
        dev_streaks: Dict[str, int] = {sh: 0 for sh in precomputed}
        dev_alerted: Dict[str, bool] = {sh: False for sh in precomputed}
        _alert_cfg_cache: Dict[str, Any] = {}

        async def _load_alert_config() -> Dict[str, Any]:
            if _alert_cfg_cache.get("_loaded"):
                return _alert_cfg_cache
            try:
                from engines import auto_factory_phase55 as af
                cfg = await af.get_config()
            except Exception:
                cfg = {}
            _alert_cfg_cache.update(cfg)
            _alert_cfg_cache["_loaded"] = True
            return _alert_cfg_cache

        # Trade-by-trade emission
        pointer = 0
        total_events = len(events)
        while True:
            # External stop signal check
            doc = await db[RUNS_COLL].find_one(
                {"run_id": run_id}, {"_id": 0, "status": 1},
            )
            if not doc or doc.get("status") != "running":
                logger.info("paper-exec: run %s stopped externally", run_id)
                break

            if pointer >= total_events:
                # Exhausted all precomputed trades — close run cleanly.
                await db[RUNS_COLL].update_one(
                    {"run_id": run_id},
                    {"$set": {
                        "status": "stopped",
                        "halted_reason": "trades_exhausted",
                        "halted_at": _now_iso(),
                        "equity": equity,
                        "peak_equity": peak_equity,
                        "pnl": round(equity - account_start, 2),
                        "trades_count": sum(len(v) for v in strat_trades.values()),
                        "max_drawdown_pct": round(max_dd_pct, 3),
                    }},
                )
                logger.info("paper-exec: run %s finished — %d trades emitted", run_id, pointer)
                break

            exit_idx_ev, entry_idx_ev, sh, t = events[pointer]
            pointer += 1
            strategy = next((x for x in run["strategies"] if x["strategy_hash"] == sh), None)
            if strategy is None:
                continue

            # Apply PnL to shared equity + DD
            equity = round(equity + float(t["pnl"]), 2)
            peak_equity = max(peak_equity, equity)
            dd_pct = round(max(0.0, (peak_equity - equity) / account_start * 100.0), 3)
            max_dd_pct = max(max_dd_pct, dd_pct)

            trade_doc = {
                "run_id": run_id,
                "strategy_hash": sh,
                "strategy_name": strategy.get("strategy_name"),
                "pair": strategy["pair"],
                "timeframe": strategy["timeframe"],
                "direction": t["direction"],
                # Paper == backtest by construction; expected == actual,
                # deviation == 0. We still emit these fields so any
                # downstream consumer / UI keeps working.
                "expected_entry": round(t["entry_price"], 5),
                "actual_entry": round(t["entry_price"], 5),
                "deviation_pips": 0.0,
                "signal_bar_idx": int(t["entry_idx"]),
                "signal_bar_ts": t.get("entry_ts"),
                "entry_bar_ts": t.get("entry_ts"),
                "sl_price": round(float(t["sl_price"]), 5) if t.get("sl_price") else None,
                "tp_price": round(float(t["tp_price"]), 5) if t.get("tp_price") else None,
                "exit_price": round(float(t["exit_price"]), 5),
                "exit_reason": t.get("exit_reason") or "flat",
                "exit_bar_ts": t.get("exit_ts"),
                "lot_size": float(t.get("lot_size") or 0.0),
                "risk_usd": float(t.get("risk_usd") or 0.0),
                "reward_ratio": float(t.get("reward_ratio") or 0.0),
                "pnl": float(t["pnl"]),
                "result": t["result"],
                "equity_after": equity,
                "dd_pct_after": dd_pct,
                "executed_at": _now_iso(),
                # Carry the signal-quality + MAE/MFE telemetry through
                # so Phase-4 dashboards can render them live.
                "entry_quality_score": t.get("entry_quality_score"),
                "mae_usd": t.get("mae_usd"),
                "mfe_usd": t.get("mfe_usd"),
            }
            strat_trades[sh].append(trade_doc)
            await db[TRADES_COLL].insert_one({**trade_doc})

            # Equity snapshot (per emitted trade)
            await db[EQUITY_COLL].insert_one({
                "run_id": run_id,
                "timestamp": _now_iso(),
                "equity": equity,
                "dd_pct": dd_pct,
                "trades_count": sum(len(v) for v in strat_trades.values()),
            })

            # Per-strategy deviation snapshot every 5 trades
            if len(strat_trades[sh]) % 5 == 0:
                running_pf = _compute_pf(strat_trades[sh])
                bt_pf = float(precomputed[sh]["meta"].get("backtest_pf") or 0.0)
                await _persist_deviation_snapshot(
                    run_id, sh, running_pf, bt_pf, len(strat_trades[sh]),
                )
                try:
                    from engines import paper_execution_alert_bridge as pdb
                    cfg = await _load_alert_config()
                    threshold = float(cfg.get("deviation_threshold", 0.20))
                    persistence = int(cfg.get("deviation_persistence", 5))
                    if pdb.exceeds_threshold(running_pf, bt_pf, threshold):
                        dev_streaks[sh] = dev_streaks.get(sh, 0) + 1
                    else:
                        dev_streaks[sh] = 0
                    if (
                        dev_streaks[sh] >= persistence
                        and not dev_alerted.get(sh)
                        and bt_pf > 0
                    ):
                        alert_res = await pdb.trigger_deviation_alert(
                            run_id=run_id,
                            strategy={**strategy, "trades": len(strat_trades[sh])},
                            running_pf=running_pf,
                            backtest_pf=bt_pf,
                            streak=dev_streaks[sh],
                            config=cfg,
                        )
                        if alert_res.get("sent") or alert_res.get("reason") == "duplicate":
                            dev_alerted[sh] = True
                except Exception:
                    logger.exception("paper-exec: deviation alert check failed (non-fatal)")

            # Daily reset at date rollover (based on wall-clock; replay
            # is accelerated so this mainly protects long-running sessions).
            today = _utc_date_of(_now_iso())
            if today != daily_start_date:
                daily_start_date = today
                daily_start_equity = equity

            # DD halt check
            total_loss_pct = max(0.0, (account_start - equity) / account_start * 100.0)
            daily_loss_pct = max(0.0, (daily_start_equity - equity) / account_start * 100.0)
            limits = run.get("limits") or {}
            halted_reason = None
            if total_loss_pct >= float(limits.get("total_loss_limit_pct") or DEFAULT_TOTAL_LOSS_LIMIT_PCT):
                halted_reason = "total_loss_limit"
            elif daily_loss_pct >= float(limits.get("daily_loss_limit_pct") or DEFAULT_DAILY_LOSS_LIMIT_PCT):
                halted_reason = "daily_loss_limit"

            # Aggregate per-strategy rollups
            strategies_rollup = []
            for s in run["strategies"]:
                sh2 = s["strategy_hash"]
                tlist = strat_trades.get(sh2) or []
                pnl_total = round(sum(t2["pnl"] for t2 in tlist), 2)
                wins = sum(1 for t2 in tlist if t2["result"] == "WIN")
                losses = sum(1 for t2 in tlist if t2["result"] == "LOSS")
                running_pf = _compute_pf(tlist)
                bt_pf = float(
                    (precomputed.get(sh2) or {}).get("meta", {}).get("backtest_pf")
                    or s.get("backtest_pf") or 0.0
                )
                dev_pct = None
                if bt_pf > 0:
                    dev_pct = round((running_pf - bt_pf) / bt_pf * 100.0, 2)
                strategies_rollup.append({
                    **s,
                    "trades": len(tlist),
                    "wins": wins,
                    "losses": losses,
                    "pnl": pnl_total,
                    "running_pf": running_pf,
                    "pf_deviation_pct": dev_pct,
                    "deviation_streak": int(dev_streaks.get(sh2, 0)),
                    "deviation_alerted": bool(dev_alerted.get(sh2, False)),
                    "skipped_reason": skipped.get(sh2),
                    "avg_entry_deviation_pips": 0.0,
                })

            update = {
                "equity": equity,
                "peak_equity": peak_equity,
                "pnl": round(equity - account_start, 2),
                "trades_count": sum(len(v) for v in strat_trades.values()),
                "max_drawdown_pct": round(max_dd_pct, 3),
                "total_loss_pct": round(total_loss_pct, 3),
                "daily_loss_pct": round(daily_loss_pct, 3),
                "strategies": strategies_rollup,
                "last_tick_at": _now_iso(),
                "emitted_events": pointer,
                "total_events": total_events,
            }

            if halted_reason:
                update["status"] = "halted"
                update["halted_reason"] = halted_reason
                update["halted_at"] = _now_iso()
                await db[RUNS_COLL].update_one({"run_id": run_id}, {"$set": update})
                logger.info("paper-exec: run %s halted — %s", run_id, halted_reason)
                break

            await db[RUNS_COLL].update_one({"run_id": run_id}, {"$set": update})

            # Refresh run doc so external stop/config changes are picked up
            run = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0}) or run

            # Accelerated tick between trade emissions
            await asyncio.sleep(max(0.005, tick_ms / 1000.0))

    except asyncio.CancelledError:
        # External cancellation (e.g. stop endpoint). Mark stopped gracefully.
        await db[RUNS_COLL].update_one(
            {"run_id": run_id, "status": "running"},
            {"$set": {"status": "stopped", "halted_reason": "cancelled",
                      "halted_at": _now_iso()}},
        )
        raise
    except Exception as e:
        logger.exception("paper-exec: run %s crashed", run_id)
        await db[RUNS_COLL].update_one(
            {"run_id": run_id},
            {"$set": {"status": "errored", "error": str(e),
                      "halted_at": _now_iso()}},
        )
    finally:
        _TASKS.pop(run_id, None)


# ═════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════

async def start_run(
    *,
    portfolio_id: Optional[str] = None,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    risk_pct: Optional[float] = None,
    daily_loss_limit_pct: float = DEFAULT_DAILY_LOSS_LIMIT_PCT,
    total_loss_limit_pct: float = DEFAULT_TOTAL_LOSS_LIMIT_PCT,
    tick_ms: int = DEFAULT_TICK_MS,
    bars_limit: int = DEFAULT_BARS_LIMIT,
    source: str = DEFAULT_SOURCE,
    slippage_pips: float = 0.5,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Start a new paper-execution run against an approved portfolio."""
    if account_balance <= 0:
        raise ValueError("account_balance must be positive")
    if tick_ms < 5:
        raise ValueError("tick_ms must be ≥ 5")
    if source not in ("bid_1m", "bi5"):
        raise ValueError("source must be 'bid_1m' or 'bi5'")

    async with _lock:
        db = get_db()
        # Enforce single-active-run
        active = await db[RUNS_COLL].find_one({"status": "running"}, {"_id": 0})
        if active:
            raise RuntimeError(f"already_active:{active.get('run_id')}")

        resolved_pid, strategies = await _load_portfolio_strategies(portfolio_id)
        if not strategies:
            raise ValueError("portfolio has no strategies")

        # Apply risk override uniformly if provided
        if risk_pct is not None:
            for s in strategies:
                s["risk_pct"] = float(risk_pct)

        run_id = f"px_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        run = {
            "run_id": run_id,
            "portfolio_id": resolved_pid,
            "status": "running",
            "mode": "paper",
            "started_at": now,
            "halted_at": None,
            "halted_reason": None,
            "account_balance_start": float(account_balance),
            "equity": float(account_balance),
            "peak_equity": float(account_balance),
            "pnl": 0.0,
            "daily_loss_pct": 0.0,
            "total_loss_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "trades_count": 0,
            "tick_ms": int(tick_ms),
            "bars_limit": int(bars_limit),
            "source": source,
            "slippage_pips": float(slippage_pips),
            "seed": seed,
            "limits": {
                "daily_loss_limit_pct": float(daily_loss_limit_pct),
                "total_loss_limit_pct": float(total_loss_limit_pct),
            },
            "strategies": [
                {**s, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0,
                 "running_pf": 0.0, "pf_deviation_pct": None,
                 "avg_entry_deviation_pips": 0.0}
                for s in strategies
            ],
        }
        await db[RUNS_COLL].insert_one({**run})

        # Launch background replay loop
        task = asyncio.create_task(_run_loop(run_id))
        _TASKS[run_id] = task
        logger.info("paper-exec: started run %s (portfolio=%s, strategies=%d)",
                    run_id, resolved_pid, len(strategies))
        return run


async def stop_run(run_id: str) -> Dict[str, Any]:
    db = get_db()
    doc = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})
    if not doc:
        raise ValueError(f"run not found: {run_id}")
    if doc.get("status") != "running":
        return doc
    await db[RUNS_COLL].update_one(
        {"run_id": run_id},
        {"$set": {"status": "stopped", "halted_reason": "manual",
                  "halted_at": _now_iso()}},
    )
    task = _TASKS.get(run_id)
    if task and not task.done():
        task.cancel()
    updated = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})
    return updated


async def get_status(
    run_id: Optional[str] = None, trade_limit: int = MAX_TRADES_IN_STATUS,
) -> Dict[str, Any]:
    db = get_db()
    # Active or most recent
    if run_id is None:
        doc = await db[RUNS_COLL].find_one({"status": "running"}, {"_id": 0})
        if not doc:
            doc = await db[RUNS_COLL].find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    else:
        doc = await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})
        if not doc:
            raise ValueError(f"run not found: {run_id}")
    if not doc:
        return {"active": None, "trades": [], "equity_curve": []}

    rid = doc["run_id"]
    trades = [t async for t in
              db[TRADES_COLL].find({"run_id": rid}, {"_id": 0})
              .sort("executed_at", -1).limit(max(1, min(trade_limit, 200)))]
    equity_curve = [e async for e in
                    db[EQUITY_COLL].find({"run_id": rid}, {"_id": 0})
                    .sort("timestamp", 1).limit(500)]
    return {"active": doc, "trades": trades, "equity_curve": equity_curve}


async def list_trades(
    run_id: Optional[str] = None, limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_db()
    q = {"run_id": run_id} if run_id else {}
    cursor = db[TRADES_COLL].find(q, {"_id": 0}).sort("executed_at", -1).limit(
        max(1, min(limit, 1000)),
    )
    return [t async for t in cursor]


async def list_equity(
    run_id: str, limit: int = 1000,
) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[EQUITY_COLL].find(
        {"run_id": run_id}, {"_id": 0},
    ).sort("timestamp", 1).limit(max(1, min(limit, 5000)))
    return [e async for e in cursor]


async def list_runs(limit: int = 10) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[RUNS_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(
        max(1, min(limit, 50)),
    )
    return [d async for d in cursor]


async def deviation_history(
    strategy_hash: str, limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[DEVIATION_COLL].find(
        {"strategy_hash": strategy_hash}, {"_id": 0},
    ).sort("sampled_at", -1).limit(max(1, min(limit, 500)))
    return [d async for d in cursor]

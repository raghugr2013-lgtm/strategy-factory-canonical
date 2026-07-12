from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging

from engines.strategy_engine import generate_strategy_text
from engines.backtest_engine import run_backtest_logic, TIMEFRAME_MAP
from engines.ranking_engine import rank_strategies
from engines.safety_engine import run_safety_analysis
from engines.db import get_db
from engines.readiness_engine import compute_readiness, failed_red_checks
from cbot_engine.generator import (
    LegacyGeneratorRetiredError,
    generate_cbot_code,
)

router = APIRouter()
logger = logging.getLogger(__name__)

STYLES = ["trend-following", "mean-reversion", "breakout", "scalping", "momentum"]


async def _load_pipeline_data(pair: str, timeframe: str) -> tuple:
    """Load real market data for the pipeline. Returns (prices, highs, lows, data_source, data_points)."""
    db = get_db()
    data_tf = TIMEFRAME_MAP.get(timeframe, timeframe.lower())
    # Per-source isolation: pipeline/auto-factory v1 runs on BID candle data only.
    cursor = db.market_data.find(
        {"symbol": pair, "source": "bid_1m", "timeframe": data_tf},
        {"_id": 0, "open": 1, "high": 1, "low": 1, "close": 1, "timestamp": 1},
    ).sort("timestamp", 1)
    docs = await cursor.to_list(length=None)
    if docs and len(docs) >= 10:
        prices = [d["close"] for d in docs]
        # Phase-1 fix: load OHLC so the execution_engine intrabar SL/TP
        # race can activate. Fall back to close-only when an old document
        # lacks high/low fields (legacy uploads).
        highs = [d.get("high", d["close"]) for d in docs]
        lows = [d.get("low", d["close"]) for d in docs]
        logger.info(f"Pipeline: loaded {len(prices)} candles for {pair}/{data_tf} (OHLC)")
        return prices, highs, lows, "real", len(prices)
    logger.warning(f"Pipeline: no real data for {pair}/{data_tf}, using sample")
    return None, None, None, "sample", 0


def _compute_status(score: float, is_safe: bool, max_dd_pct: float) -> str:
    if score >= 65 and is_safe and max_dd_pct <= 15:
        return "READY"
    elif score >= 40 and max_dd_pct <= 25:
        return "MODERATE"
    return "RISKY"


from engines.strategy_library import _fingerprint

async def _check_duplicate(db, strategy: dict) -> bool:
    try:
        pair = strategy.get("pair")
        timeframe = strategy.get("timeframe")
        style = strategy.get("style", "")
        strategy_text = strategy.get("strategy_text", "")

        params = strategy.get("backtest_results", {}).get("parameters", {})

        fp = _fingerprint(
            pair,
            timeframe,
            style,
            params,
            strategy_text
        )

        existing = await db.strategy_library.find_one({"fingerprint": fp})
        return existing is not None
    except Exception:
        return False

async def _auto_save_strategy(db, s: dict) -> dict:
    """Save a strategy from the pipeline into the library. Returns save result."""
    bt = s.get("backtest_results", {})
    safety = s.get("safety", {})
    ranking = s.get("ranking", {})

    score = ranking.get("score", 0)
    is_safe = safety.get("is_safe", True)
    max_dd = bt.get("max_drawdown_pct", 0)
    status = _compute_status(score, is_safe, max_dd)

    params = bt.get("parameters", {})
    extraction = bt.get("extraction", {})
    raw = extraction.get("raw", {}) if extraction else {}

    indicators_summary = {}
    if raw.get("rsi_period"):
        indicators_summary["rsi"] = {"period": raw["rsi_period"], "buy": raw.get("rsi_buy_threshold"), "sell": raw.get("rsi_sell_threshold")}
    if raw.get("macd"):
        indicators_summary["macd"] = raw["macd"]
    if raw.get("bollinger"):
        indicators_summary["bollinger"] = raw["bollinger"]

    doc = {
        "strategy_text": s.get("strategy_text", ""),
        "pair": s.get("pair", ""),
        "timeframe": s.get("timeframe", ""),
        "strategy_type": bt.get("strategy_type", s.get("style", "trend_following")),
        "parameters": {
            "fast_ema": params.get("fast_sma"),
            "slow_ema": params.get("slow_sma"),
            "stop_loss_pips": params.get("stop_loss_pips"),
            "take_profit_pips": params.get("take_profit_pips"),
        },
        "indicators": indicators_summary,
        "metrics": {
            "net_profit": bt.get("net_profit", 0),
            "total_return_pct": bt.get("total_return_pct", 0),
            "win_rate": bt.get("win_rate", 0),
            "profit_factor": bt.get("profit_factor", 0),
            "total_trades": bt.get("total_trades", 0),
            "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
            "max_drawdown_pips": bt.get("max_drawdown_pips", 0),
            "risk_adjusted_return": bt.get("risk_adjusted_return", 0),
        },
        "safety": {
            "safety_score": safety.get("safety_score", 0),
            "grade": safety.get("grade", "N/A"),
            "is_safe": safety.get("is_safe", True),
            "flags": safety.get("flags", []),
        },
        "ranking": {"score": score, "grade": ranking.get("grade", "N/A")},
        "score": score,
        "status": status,
        "backtest_results": bt,
        "source": "auto_factory",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.strategies.insert_one(doc)
    return {"id": str(result.inserted_id), "status": status, "score": score}


# Phase-1 UI cap — matches the numeric input (1..50) on Dashboard/Workspace/Auto-Factory.
MAX_STRATEGIES = 50


class PipelineRequest(BaseModel):
    pair: str = "EURUSD"
    timeframe: str = "H1"
    count: int = 5
    risk_percent: float = 1.0
    spread_pips: Optional[float] = None
    # Phase 10 — dashboard mode piggy-backs on this endpoint because the
    # preview ingress only allow-lists already-known paths.
    mode: Optional[str] = None           # "dashboard" → dashboard pipeline
    style: Optional[str] = "trend-following"
    firm: Optional[str] = "ftmo"
    top_n: Optional[int] = 5
    refine_top: Optional[int] = 2


@router.post("/run-pipeline")
async def run_pipeline(req: PipelineRequest):
    # Phase 10 — dashboard dispatch (piggy-backs on this allow-listed path).
    logger.info(f"run_pipeline hit mode={req.mode!r} count={req.count}")
    if (req.mode or "").lower() == "dashboard":
        from api.dashboard import dashboard_generate, DashboardGenerateRequest
        return await dashboard_generate(DashboardGenerateRequest(
            pair=req.pair, timeframe=req.timeframe,
            style=req.style or "trend-following",
            firm=req.firm or "ftmo",
            count=req.count,
            top_n=req.top_n or 5,
            refine_top=req.refine_top or 2,
        ))

    count = max(1, min(req.count, MAX_STRATEGIES))
    sim_config = {"risk_percent": req.risk_percent}
    if req.spread_pips is not None:
        sim_config["spread_pips"] = req.spread_pips

    # Load real data ONCE for all backtests
    ext_prices, ext_highs, ext_lows, data_source, data_points = await _load_pipeline_data(req.pair, req.timeframe)

    steps_log = []
    steps_log.append(f"Data: {data_source} ({data_points} candles)")
    strategies_with_bt = []

    # Step 1: Generate strategies
    for i in range(count):
        style = STYLES[i % len(STYLES)]
        try:
            text = await generate_strategy_text(req.pair, req.timeframe, style)
            strategies_with_bt.append({
                "strategy_text": text,
                "pair": req.pair,
                "timeframe": req.timeframe,
                "style": style,
                "index": i,
            })
            steps_log.append(f"Generated strategy {i + 1}/{count} ({style})")
        except Exception as e:
            steps_log.append(f"Failed strategy {i + 1}/{count} ({style}): {str(e)[:80]}")

    if not strategies_with_bt:
        raise HTTPException(status_code=500, detail="All strategy generations failed")

    # Step 2: Backtest each — using real data
    for s in strategies_with_bt:
        try:
            bt = run_backtest_logic(
                s["strategy_text"], s["pair"], s["timeframe"],
                external_prices=ext_prices,
                external_highs=ext_highs,
                external_lows=ext_lows,
                data_source=data_source,
                data_points=data_points,
                sim_config=sim_config,
            )
            s["backtest_results"] = bt
            steps_log.append(
                f"Backtested #{s['index'] + 1} ({s['style']}): "
                f"{bt['total_trades']} trades, PnL ${bt['net_profit']}, WR {bt['win_rate']}% "
                f"[{data_source}: {bt['data_points']} candles]"
            )
        except Exception as e:
            s["backtest_results"] = None
            steps_log.append(f"Backtest failed #{s['index'] + 1}: {str(e)[:80]}")

    # Filter out strategies without backtest results
    valid = [s for s in strategies_with_bt if s.get("backtest_results")]
    if not valid:
        raise HTTPException(status_code=500, detail="All backtests failed")

    # Step 3: Safety analysis for each strategy
    for s in valid:
        bt = s.get("backtest_results", {})
        safety = run_safety_analysis(bt, timeframe=req.timeframe)
        s["safety"] = safety
        status = "SAFE" if safety["is_safe"] else f"UNSAFE ({len(safety['flags'])} flags)"
        steps_log.append(
            f"Safety #{s['index'] + 1}: score={safety['safety_score']} {status} "
            f"({safety['metrics']['trades_per_day']:.1f}/day)"
        )

    # Step 4: Rank (includes safety score in composite)
    ranked = rank_strategies(valid)
    steps_log.append(f"Ranked {len(ranked)} strategies")

    best = ranked[0]
    steps_log.append(
        f"Best: #{best['ranking']['rank']} ({best['style']}) "
        f"Score {best['ranking']['score']}, Grade {best['ranking']['grade']}"
    )

    # Step 5: Generate cBot for winner with full aligned parameters
    cbot = None
    try:
        bt_params = best.get("backtest_results", {}).get("parameters")
        sim_settings = best.get("backtest_results", {}).get("simulation")
        best_safety = best.get("safety", {})
        safety_rules = best_safety.get("thresholds") if best_safety else None
        best_bt = best.get("backtest_results", {})
        extraction = best_bt.get("extraction")
        strategy_type = best_bt.get("strategy_type")

        # Build indicators from extraction data
        indicators = None
        if extraction and extraction.get("raw"):
            raw = extraction["raw"]
            ind = {}
            if raw.get("rsi_period"):
                ind["rsi"] = {
                    "period": raw["rsi_period"],
                    "buy_threshold": raw.get("rsi_buy_threshold", 50),
                    "sell_threshold": raw.get("rsi_sell_threshold", 50),
                }
            if raw.get("macd"):
                ind["macd"] = raw["macd"]
            if raw.get("bollinger"):
                ind["bollinger"] = raw["bollinger"]
            if ind:
                indicators = ind

        cbot = await generate_cbot_code(
            strategy_text=best["strategy_text"],
            pair=best["pair"],
            timeframe=best["timeframe"],
            backtest_params=bt_params,
            sim_settings=sim_settings,
            safety_rules=safety_rules,
            indicators=indicators,
            strategy_type=strategy_type,
            extraction=extraction,
            _caller="api.pipeline.run_full_pipeline",
        )
        steps_log.append(
            f"Generated cBot: {cbot['filename']} "
            f"(type={strategy_type}, indicators={list(indicators.keys()) if indicators else 'EMA'}, safety=yes)"
        )
    except LegacyGeneratorRetiredError as e:
        # P0.1 — explicit, structured, operator-readable. The pipeline
        # is allowed to continue WITHOUT a cBot (best_strategy is still
        # returned for inspection), but the steps_log captures the
        # exact reason so the operator can migrate to the IR-transpiler
        # path. Never silently substitutes a stub.
        steps_log.append(
            f"cBot generation refused: {e.error_code} (phase={e.phase}, "
            f"retired_at={e.retired_at}). Remediation: {e.remediation}"
        )
    except Exception as e:
        steps_log.append(f"cBot generation failed: {str(e)[:80]}")

    return {
        "ranked_strategies": ranked,
        "best_strategy": {
            "strategy_text": best["strategy_text"],
            "pair": best["pair"],
            "timeframe": best["timeframe"],
            "style": best.get("style", ""),
            "backtest_results": best.get("backtest_results"),
            "ranking": best.get("ranking"),
            "safety": best.get("safety"),
        },
        "cbot": cbot,
        "steps_log": steps_log,
        "data_info": {
            "source": data_source,
            "candles": data_points,
        },
        "total_generated": len(strategies_with_bt),
        "total_backtested": len(valid),
    }



class AutoFactoryRequest(BaseModel):
    symbols: List[str] = ["EURUSD"]
    timeframes: List[str] = ["H1"]
    strategies_per_pair: int = 5
    keep_top_n: int = 1
    risk_percent: float = 1.0
    spread_pips: Optional[float] = None
    # Performance filters
    min_trades: int = 5
    min_win_rate: float = 0
    min_score: float = 0
    min_safety_score: float = 0


@router.post("/auto-factory")
async def run_auto_factory(req: AutoFactoryRequest):
    """
    Auto Factory: generate → backtest → safety → rank → filter → auto-save.
    Runs the full pipeline for each symbol/timeframe combination,
    filters by performance thresholds, and saves top strategies to the Library.

    Pre-flight readiness gate (non-overridable): request is rejected with
    HTTP 412 if the system-readiness check reports `overall == "red"`.
    """
    # ── Readiness gate (shared with /api/auto-factory/run) ──────────
    readiness = await compute_readiness()
    if readiness.get("overall") == "red":
        reds = failed_red_checks(readiness)
        raise HTTPException(
            status_code=412,
            detail={
                "code": "readiness_blocked",
                "message": "System is not ready. Fix issues before running Auto Factory.",
                "overall": "red",
                "failed_checks": [
                    {"id": c.get("id"), "label": c.get("label"), "summary": c.get("summary")}
                    for c in reds
                ],
                "readiness": readiness,
            },
        )

    db = get_db()
    strategies_per = max(1, min(req.strategies_per_pair, MAX_STRATEGIES))
    keep_n = max(1, min(req.keep_top_n, 5))

    sim_config = {"risk_percent": req.risk_percent}
    if req.spread_pips is not None:
        sim_config["spread_pips"] = req.spread_pips

    total_generated = 0
    total_backtested = 0
    total_filtered_out = 0
    total_duplicates = 0
    total_saved = 0
    saved_strategies = []
    run_log = []

    for pair in req.symbols[:5]:
        for tf in req.timeframes[:4]:
            run_log.append(f"--- {pair}/{tf} ---")

            # Load data once per pair/tf
            ext_prices, ext_highs, ext_lows, data_source, data_points = await _load_pipeline_data(pair, tf)
            run_log.append(f"Data: {data_source} ({data_points} candles)")

            # Step 1: Generate strategies
            candidates = []
            for i in range(strategies_per):
                style = STYLES[i % len(STYLES)]
                try:
                    text = await generate_strategy_text(pair, tf, style)
                    candidates.append({
                        "strategy_text": text,
                        "pair": pair,
                        "timeframe": tf,
                        "style": style,
                    })
                    total_generated += 1
                except Exception as e:
                    run_log.append(f"  Gen failed ({style}): {str(e)[:60]}")

            if not candidates:
                run_log.append("  All generations failed, skipping")
                continue

            # Step 2: Backtest each
            for s in candidates:
                try:
                    bt = run_backtest_logic(
                        s["strategy_text"], s["pair"], s["timeframe"],
                        external_prices=ext_prices,
                        external_highs=ext_highs,
                        external_lows=ext_lows,
                        data_source=data_source,
                        data_points=data_points,
                        sim_config=sim_config,
                    )
                    s["backtest_results"] = bt
                    total_backtested += 1
                except Exception:
                    s["backtest_results"] = None

            valid = [s for s in candidates if s.get("backtest_results")]
            if not valid:
                run_log.append("  All backtests failed, skipping")
                continue

            # Step 3: Safety analysis
            for s in valid:
                s["safety"] = run_safety_analysis(s["backtest_results"], timeframe=tf)

            # Step 4: Rank
            ranked = rank_strategies(valid)

            # Step 5: Apply performance filters
            filtered = []
            for s in ranked:
                bt = s.get("backtest_results", {})
                safety = s.get("safety", {})
                ranking = s.get("ranking", {})

                passes = True

                # Minimum trades
                if bt.get("total_trades", 0) < 50:
                    passes = False

                # Profit Factor
                if bt.get("profit_factor", 0) < 1.3:
                    passes = False

                # Drawdown
                if bt.get("max_drawdown_pct", 100) > 15:
                    passes = False

                # Win rate sanity
                wr = bt.get("win_rate", 0)
                if wr < 30 or wr > 80:
                    passes = False

                # Safety
                if safety.get("safety_score", 0) < 50:
                    passes = False

                if passes:
                    filtered.append(s)
                else:
                    total_filtered_out += 1

            # Step 6: Take top N
            top = filtered[:keep_n]

            # Step 7: Deduplicate and save
            for s in top:
                bt = s.get("backtest_results", {})
                params = bt.get("parameters", {})

                is_dup = await _check_duplicate(db, s)
                if is_dup:
                    total_duplicates += 1
                    run_log.append(
                        f"  Duplicate skipped: {params.get('fast_sma')}/{params.get('slow_sma')}"
                    )
                    continue

                save_result = await _auto_save_strategy(db, s)
                total_saved += 1

                ranking = s.get("ranking", {})
                bt = s.get("backtest_results", {})

                saved_strategies.append({
                    "id": save_result["id"],
                    "pair": pair,
                    "timeframe": tf,
                    "style": s.get("style", ""),
                    "score": ranking.get("score", 0),
                    "status": save_result["status"],
                    "net_profit": bt.get("net_profit", 0),
                    "win_rate": bt.get("win_rate", 0),
                    "profit_factor": bt.get("profit_factor", 0),
                    "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                    "total_trades": bt.get("total_trades", 0),
                    "safety_score": s.get("safety", {}).get("safety_score", 0),
                })

                run_log.append(
                    f"  SAVED: {pair}/{tf} score={ranking.get('score',0)} "
                    f"PF={bt.get('profit_factor',0)} WR={bt.get('win_rate',0)}% "
                    f"status={save_result['status']}"
                )

            run_log.append(
                f"  {pair}/{tf}: {len(candidates)} gen, {len(valid)} bt, "
                f"{len(filtered)} passed, {len(top)} selected"
            )

    return {
        "success": True,
        "summary": {
            "total_generated": total_generated,
            "total_backtested": total_backtested,
            "total_filtered_out": total_filtered_out,
            "total_duplicates": total_duplicates,
            "total_saved": total_saved,
        },
        "saved_strategies": saved_strategies,
        "run_log": run_log,
        "config": {
            "symbols": req.symbols,
            "timeframes": req.timeframes,
            "strategies_per_pair": strategies_per,
            "keep_top_n": keep_n,
            "filters": {
                "min_trades": req.min_trades,
                "min_win_rate": req.min_win_rate,
                "min_score": req.min_score,
                "min_safety_score": req.min_safety_score,
            },
        },
    }



# ═══════════════════════════════════════════════════════
# Auto Factory v2 — Phase 5.5 (Universe + Multi-Level + Matching)
# ═══════════════════════════════════════════════════════

class AutoFactoryV2Request(BaseModel):
    max_combos: int = 3
    strategies_per_combo: int = 5
    keep_top_n: int = 5
    mc_simulations: int = 20
    seed: Optional[int] = None


@router.post("/run-auto-factory")
async def run_auto_factory_v2(req: AutoFactoryV2Request):
    """
    Auto Factory v2 (Phase 5.5): Universe-based continuous strategy generation.
    Generates, backtests, filters, profiles, matches, and stores top strategies.
    Rotates through universe combinations each cycle.
    """
    from engines.auto_factory import run_auto_factory_cycle

    try:
        result = await run_auto_factory_cycle(
            max_combos=max(1, min(req.max_combos, 10)),
            strategies_per_combo=max(2, min(req.strategies_per_combo, 10)),
            keep_top_n=max(1, min(req.keep_top_n, 5)),
            seed=req.seed,
            mc_simulations=max(10, min(req.mc_simulations, 50)),
        )
        return {"auto_factory": result}
    except Exception as e:
        logger.error(f"Auto factory cycle failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-factory-results")
async def get_auto_factory_results():
    """List all stored auto factory strategies, grouped by combo."""
    db = get_db()
    cursor = db["auto_factory_strategies"].find(
        {}, {"_id": 0}
    ).sort([("combo_key", 1), ("rank", 1)])
    results = []
    async for doc in cursor:
        results.append(doc)

    # Group by combo
    combos = {}
    for r in results:
        key = r.get("combo_key", "unknown")
        if key not in combos:
            combos[key] = []
        combos[key].append(r)

    return {
        "total_strategies": len(results),
        "total_combos": len(combos),
        "combos": combos,
    }

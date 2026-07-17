from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import logging

from engines.backtest_engine import run_backtest_logic, TIMEFRAME_MAP
from engines.ranking_engine import rank_strategies
from engines.analysis_engine import analyze_strategy
from engines.optimization_engine import run_optimization
from engines.validation_engine import run_validation
from engines.monte_carlo_engine import run_monte_carlo
from engines.safety_engine import run_safety_analysis
from engines.param_extractor import extract_params
from engines.db import get_db

router = APIRouter()
# ── Phase-1 canonical routing ──────────────────────────────────────
# `/api/strategies` (list), `/api/strategies/{strategy_id}` (GET+DELETE)
# are owned by the Phase-1 core router (`backend/app/api/strategies.py`),
# which uses the `strategy_id` field as the canonical identifier.
#
# The legacy handlers for those three paths used MongoDB `_id` (ObjectId)
# as their identifier, which conflicted with Phase-1's `strategy_id` and
# caused deployed responses to be inconsistent when both routers mounted.
#
# Fix (canonical bundle architecture): keep every non-conflicting legacy
# endpoint on `router` at its historical path so all advanced functionality
# (`/api/generate-strategy`, `/api/run-backtest`, `/api/rank-strategies`,
#  `/api/strategies/compare`, `/api/mutate-strategy`, `/api/monte-carlo`,
#  `/api/portfolio-analyze`, `/api/rebalance/*`, etc.) is preserved
# verbatim, and move ONLY the 3 conflicting canonical CRUD paths to
# `legacy_router` under `/legacy/strategies*`. This preserves the
# `_id`-based legacy behaviour for anyone who explicitly needs it while
# freeing `/api/strategies*` for Phase-1 CRUD.
#
# Both routers are auto-mounted by `_mount_legacy_routers()` in
# `app/main.py` (it iterates `vars(mod)` looking for `APIRouter`
# instances), so no change to `main.py` is required.
legacy_router = APIRouter(prefix="/legacy")
logger = logging.getLogger(__name__)


async def _load_real_data(pair: str, timeframe: str, date_from: str = None, date_to: str = None) -> tuple:
    """
    Load ALL real market data from MongoDB for a given symbol/timeframe.
    No artificial cap — uses full dataset for accurate backtesting.
    Returns (prices_list, data_source_label, data_points_count, first_ts, last_ts).
    Falls back to empty if no data found.
    """
    db = get_db()
    data_tf = TIMEFRAME_MAP.get(timeframe, timeframe.lower())

    # Per-source isolation: strategy backtests only read from the BID candle
    # stream. bi5 tick-derived rows live in the same collection but MUST NOT
    # be mixed in — they're handled by dedicated tick pipelines.
    query = {"symbol": pair, "source": "bid_1m", "timeframe": data_tf}
    if date_from:
        query.setdefault("timestamp", {})
        query["timestamp"]["$gte"] = date_from
    if date_to:
        query.setdefault("timestamp", {})
        query["timestamp"]["$lte"] = date_to

    cursor = db.market_data.find(
        query, {"_id": 0, "close": 1, "timestamp": 1}
    ).sort("timestamp", 1)
    docs = await cursor.to_list(length=None)  # No cap — load ALL data

    if docs and len(docs) >= 10:
        prices = [d["close"] for d in docs]
        first_ts = docs[0]["timestamp"] if docs else None
        last_ts = docs[-1]["timestamp"] if docs else None
        logger.info(
            f"Loaded {len(prices)} candles for {pair}/{data_tf} "
            f"({first_ts} → {last_ts})"
        )
        return prices, "real", len(prices), first_ts, last_ts

    logger.warning(f"No real data for {pair}/{data_tf} (found {len(docs)} candles), falling back to sample")
    return None, "sample", 0, None, None


class GenerateRequest(BaseModel):
    pair: str = "EURUSD"
    timeframe: str = "H1"
    style: str = "trend-following"


class BacktestRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    use_uploaded_data: bool = False
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0


class SaveRequest(BaseModel):
    strategy_text: str
    pair: str
    timeframe: str
    backtest_results: Optional[dict] = None
    strategy_type: Optional[str] = None
    indicators: Optional[dict] = None
    safety: Optional[dict] = None
    validation: Optional[dict] = None
    monte_carlo: Optional[dict] = None
    ranking: Optional[dict] = None


class StrategyItem(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    backtest_results: Optional[dict] = None
    safety: Optional[dict] = None
    monte_carlo: Optional[dict] = None


class RankRequest(BaseModel):
    strategies: List[StrategyItem]


class AnalyzeRequest(BaseModel):
    strategy_text: str
    backtest_results: Optional[dict] = None


class OptimizeRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    use_uploaded_data: bool = False
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0


class RandomOptimizeRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    num_variants: int = 75
    train_ratio: float = 0.70
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0


class ValidateRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0
    # Phase 8 — validation mode: basic | walk_forward | holdout | full
    mode: str = "basic"
    wf_n_windows: int = 5
    wf_train_pct: float = 0.70
    wf_num_variants: int = 40
    holdout_train_pct: float = 0.80
    holdout_num_variants: int = 60

@router.post("/generate-strategy")
async def generate_strategy(req: GenerateRequest):
    """Generate ONE diverse strategy text with QUALITY-RETRY validation.

    Behaviour:
      • Draws a structurally-diverse strategy from the catalogue.
      • If real market data is available for (pair, timeframe), runs a
        quick backtest and retries up to 3× until thresholds are met:
            total_trades >= MIN_TRADES (20)
            win_rate     >= MIN_WIN_RATE (30%)
        Returns the best-of-attempts strategy with quality metadata.
      • If NO market data is available, gracefully degrades to a single
        offline-safe diverse strategy (no backtest), so the basic
        pipeline runs without the user having to pre-load data.
    """
    from engines.strategy_engine import generate_strategy_text as _gen

    MAX_RETRIES = 3
    MIN_TRADES = 20
    MIN_WIN_RATE = 30.0

    # Try to load real data; fall back to offline-safe single-shot when missing.
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe,
        )
    except Exception as e:
        logger.warning(f"_load_real_data failed: {e}")
        prices, data_source, data_points = [], "none", 0

    if not prices or len(prices) < 200:
        # Offline-safe path — no data to validate against.
        text = await _gen(req.pair, req.timeframe, req.style)
        return {
            "strategy": text,
            "quality": {
                "trades": 0,
                "win_rate": None,
                "data_source": "offline_safe",
                "data_points": data_points,
                "attempts": 1,
                "note": "No market data available — strategy returned without backtest validation.",
            },
        }

    best_strategy = None
    best_trades = 0
    best_win_rate = 0.0
    best_pf = 0.0

    for attempt in range(MAX_RETRIES):
        try:
            text = await _gen(req.pair, req.timeframe, req.style)
            bt = run_backtest_logic(
                text, req.pair, req.timeframe,
                external_prices=prices,
                data_source=data_source,
                data_points=data_points,
            )
            tt = int(bt.get("total_trades", 0) or 0)
            wr = float(bt.get("win_rate", 0) or 0)
            pf = float(bt.get("profit_factor", 0) or 0)
            logger.info(
                f"generate-strategy attempt {attempt+1}: trades={tt} wr={wr}% pf={pf} "
                f"on {data_points} candles ({data_source})"
            )
            # Track best-of for fallback return
            if tt > best_trades or (tt == best_trades and wr > best_win_rate):
                best_strategy = text
                best_trades = tt
                best_win_rate = wr
                best_pf = pf
            if tt >= MIN_TRADES and wr >= MIN_WIN_RATE:
                return {
                    "strategy": text,
                    "quality": {
                        "trades": tt,
                        "win_rate": wr,
                        "profit_factor": pf,
                        "data_source": data_source,
                        "data_points": data_points,
                        "attempts": attempt + 1,
                    },
                }
        except Exception as e:
            logger.error(f"generate-strategy attempt {attempt+1} failed: {e}")
            if attempt == MAX_RETRIES - 1 and not best_strategy:
                raise HTTPException(status_code=500, detail=str(e))

    # Exhausted retries — return the best one we saw, even if below thresholds.
    return {
        "strategy": best_strategy or "",
        "quality": {
            "trades": best_trades,
            "win_rate": best_win_rate,
            "profit_factor": best_pf,
            "data_source": data_source,
            "data_points": data_points,
            "attempts": MAX_RETRIES,
            "note": (
                f"Best of {MAX_RETRIES} attempts ({best_trades} trades, "
                f"{best_win_rate:.1f}% WR). Below quality thresholds — "
                f"consider running the Optimizer or trying a different style."
            ),
        },
    }
@router.post("/run-backtest")
async def run_backtest(req: BacktestRequest):
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe, req.date_from, req.date_to
        )

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        results = run_backtest_logic(
            req.strategy_text, req.pair, req.timeframe,
            external_prices=prices,
            data_source=data_source,
            data_points=data_points,
            sim_config=sim_config,
        )
        # Attach data metadata
        results["data_range"] = {"start": first_ts, "end": last_ts}

        # Run safety analysis on backtest results
        safety = run_safety_analysis(results, timeframe=req.timeframe)
        results["safety"] = safety

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _compute_status(score: float, is_safe: bool, max_dd_pct: float) -> str:
    """Determine strategy status: READY / MODERATE / RISKY."""
    if score >= 65 and is_safe and max_dd_pct <= 15:
        return "READY"
    elif score >= 40 and max_dd_pct <= 25:
        return "MODERATE"
    return "RISKY"


@router.post("/save-strategy")
async def save_strategy(req: SaveRequest):
    db = get_db()
    bt = req.backtest_results or {}
    safety = req.safety or {}
    ranking = req.ranking or {}

    score = ranking.get("score", 0)
    is_safe = safety.get("is_safe", True)
    max_dd = bt.get("max_drawdown_pct", 0)
    status = _compute_status(score, is_safe, max_dd)

    # Extract key parameters
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
    if req.indicators:
        indicators_summary = req.indicators

    doc = {
        "strategy_text": req.strategy_text,
        "pair": req.pair,
        "timeframe": req.timeframe,
        "strategy_type": req.strategy_type or bt.get("strategy_type", "trend_following"),
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
        } if safety else None,
        "validation": req.validation,
        "monte_carlo": req.monte_carlo,
        "ranking": {
            "score": score,
            "grade": ranking.get("grade", "N/A"),
        } if ranking else None,
        "score": score,
        "status": status,
        "backtest_results": req.backtest_results,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.strategies.insert_one(doc)
    return {
        "id": str(result.inserted_id),
        "status": status,
        "score": score,
        "message": "Strategy saved successfully",
    }


@legacy_router.get("/strategies")
async def get_strategies(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_dir: Optional[str] = None,
):
    db = get_db()
    query = {}
    if symbol:
        query["pair"] = symbol
    if timeframe:
        query["timeframe"] = timeframe
    if min_score is not None or max_score is not None:
        score_q = {}
        if min_score is not None:
            score_q["$gte"] = min_score
        if max_score is not None:
            score_q["$lte"] = max_score
        query["score"] = score_q
    if status:
        query["status"] = status

    sort_field = "created_at"
    sort_direction = -1
    if sort_by == "score":
        sort_field = "score"
    elif sort_by == "profit_factor":
        sort_field = "metrics.profit_factor"
    elif sort_by == "drawdown":
        sort_field = "metrics.max_drawdown_pct"
    elif sort_by == "win_rate":
        sort_field = "metrics.win_rate"
    elif sort_by == "net_profit":
        sort_field = "metrics.net_profit"
    if sort_dir == "asc":
        sort_direction = 1

    cursor = db.strategies.find(query, {"_id": 0, "strategy_id": {"$toString": "$_id"}}).sort(sort_field, sort_direction)
    results = []
    async for doc in cursor:
        results.append(doc)
    # Inject string ID
    cursor2 = db.strategies.find(query).sort(sort_field, sort_direction)
    results2 = []
    async for doc in cursor2:
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["id"] = str(doc["_id"])
        results2.append(d)

    return {"strategies": results2[:200]}


@legacy_router.get("/strategies/{strategy_id}")
async def get_strategy_detail(strategy_id: str):
    from bson import ObjectId
    db = get_db()
    try:
        doc = await db.strategies.find_one({"_id": ObjectId(strategy_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid strategy ID")
    if not doc:
        raise HTTPException(status_code=404, detail="Strategy not found")
    d = {k: v for k, v in doc.items() if k != "_id"}
    d["id"] = str(doc["_id"])
    return {"strategy": d}


@legacy_router.delete("/strategies/{strategy_id}")
async def delete_strategy(strategy_id: str):
    from bson import ObjectId
    db = get_db()
    try:
        result = await db.strategies.delete_one({"_id": ObjectId(strategy_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid strategy ID")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {"message": "Strategy deleted", "id": strategy_id}



class CompareRequest(BaseModel):
    strategy_ids: List[str]


@router.post("/strategies/compare")
async def compare_strategies(req: CompareRequest):
    """Fetch multiple strategies with their live tracking status for comparison."""
    from bson import ObjectId
    db = get_db()
    if len(req.strategy_ids) < 2 or len(req.strategy_ids) > 3:
        raise HTTPException(status_code=400, detail="Select 2-3 strategies to compare")

    results = []
    for sid in req.strategy_ids:
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(sid)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid ID: {sid}")
        if not doc:
            raise HTTPException(status_code=404, detail=f"Not found: {sid}")
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["id"] = str(doc["_id"])

        # Get live tracking status
        track = await db.live_tracking.find_one({"strategy_id": sid})
        if track:
            d["live_status"] = track.get("status", "N/A")
            d["live_metrics"] = {k: v for k, v in (track.get("live_metrics") or {}).items()} if track.get("live_metrics") else None
        else:
            d["live_status"] = "N/A"
            d["live_metrics"] = None

        results.append(d)

    return {"strategies": results}



@router.post("/rank-strategies")
async def rank_strategies_endpoint(req: RankRequest):
    try:
        items = [s.model_dump() for s in req.strategies]
        ranked = rank_strategies(items)
        return {"ranked_strategies": ranked}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze-strategy")
async def analyze_strategy_endpoint(req: AnalyzeRequest):
    try:
        analysis = await analyze_strategy(req.strategy_text, req.backtest_results)
        return {"analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExtractParamsRequest(BaseModel):
    strategy_text: str


@router.post("/extract-params")
async def extract_params_endpoint(req: ExtractParamsRequest):
    """Extract trading parameters from strategy text."""
    result = extract_params(req.strategy_text)
    return {"extraction": result}


@router.post("/optimize-strategy")
async def optimize_strategy_endpoint(req: OptimizeRequest):
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe
        )

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        result = run_optimization(
            req.strategy_text, req.pair, req.timeframe,
            sim_config=sim_config,
            external_prices=prices,
            data_source=data_source,
            data_points=data_points,
        )
        result["data_source"] = data_source
        result["data_points"] = data_points if data_points else (len(prices) if prices else 50)
        result["data_range"] = {"start": first_ts, "end": last_ts}
        return {"optimization": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize-random")
async def optimize_random_endpoint(req: RandomOptimizeRequest):
    """Random Search Optimizer with train/test split and Sharpe-based scoring."""
    from engines.random_search_optimizer import run_random_search
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe
        )

        if not prices or data_source == "sample":
            raise HTTPException(
                status_code=400,
                detail=f"Random Search requires real historical data for {req.pair}/{req.timeframe}. "
                       f"Download data via Market Data tab first.",
            )

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        result = run_random_search(
            req.strategy_text, req.pair, req.timeframe,
            prices=prices,
            num_variants=max(20, min(req.num_variants, 200)),
            train_ratio=max(0.5, min(req.train_ratio, 0.85)),
            sim_config=sim_config,
        )

        result["data_source"] = data_source
        result["data_points"] = data_points
        result["data_range"] = {"start": first_ts, "end": last_ts}
        return {"optimization": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Random optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate-strategy")
async def validate_strategy_endpoint(req: ValidateRequest):
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe
        )

        if not prices or len(prices) < 60:
            return {
                "validation": {
                    "success": False,
                    "error": f"Not enough real data for validation. Need at least 60 candles for {req.pair} ({req.timeframe}). Have {data_points}. Download more data first.",
                }
            }

        logger.info(f"Validation: {len(prices)} candles for {req.pair}/{req.timeframe} ({first_ts} → {last_ts})")

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        result = run_validation(
            req.strategy_text, req.pair, req.timeframe,
            prices=prices,
            data_source=data_source,
            sim_config=sim_config,
            mode=req.mode,
            wf_n_windows=req.wf_n_windows,
            wf_train_pct=req.wf_train_pct,
            wf_num_variants=req.wf_num_variants,
            holdout_train_pct=req.holdout_train_pct,
            holdout_num_variants=req.holdout_num_variants,
        )
        result["data_range"] = {"start": first_ts, "end": last_ts}
        return {"validation": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class SafetyCheckRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0
    thresholds: Optional[dict] = None


@router.post("/safety-check")
async def safety_check_endpoint(req: SafetyCheckRequest):
    """Run standalone safety analysis on a strategy's backtest results."""
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe
        )

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        bt = run_backtest_logic(
            req.strategy_text, req.pair, req.timeframe,
            external_prices=prices,
            data_source=data_source,
            data_points=data_points,
            sim_config=sim_config,
        )

        safety = run_safety_analysis(bt, timeframe=req.timeframe, thresholds=req.thresholds)

        return {
            "safety": safety,
            "backtest_summary": {
                "total_trades": bt.get("total_trades", 0),
                "net_profit": bt.get("net_profit", 0),
                "win_rate": bt.get("win_rate", 0),
                "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
                "data_source": data_source,
                "data_points": data_points,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class MonteCarloRequest(BaseModel):
    strategy_text: str
    pair: str = "EURUSD"
    timeframe: str = "H1"
    num_simulations: int = 100
    spread_pips: Optional[float] = None
    risk_percent: float = 1.0


@router.post("/monte-carlo")
async def monte_carlo_endpoint(req: MonteCarloRequest):
    """Run Monte Carlo trade resampling on a strategy's backtest trades."""
    try:
        prices, data_source, data_points, first_ts, last_ts = await _load_real_data(
            req.pair, req.timeframe
        )

        sim_config = {"risk_percent": req.risk_percent}
        if req.spread_pips is not None:
            sim_config["spread_pips"] = req.spread_pips

        # Run backtest to get trade list
        bt = run_backtest_logic(
            req.strategy_text, req.pair, req.timeframe,
            external_prices=prices,
            data_source=data_source,
            data_points=data_points,
            sim_config=sim_config,
        )

        trades = bt.get("trades", [])
        if len(trades) < 3:
            return {
                "monte_carlo": {
                    "success": False,
                    "error": f"Not enough trades ({len(trades)}). Need at least 3 for Monte Carlo.",
                    "num_trades": len(trades),
                    "backtest_summary": {
                        "total_trades": bt.get("total_trades", 0),
                        "win_rate": bt.get("win_rate", 0),
                        "net_profit": bt.get("net_profit", 0),
                    },
                }
            }

        mc_balance = sim_config.get("initial_balance", bt.get("initial_balance", 10000.0))
        mc_result = run_monte_carlo(
            trades=trades,
            num_simulations=req.num_simulations,
            initial_balance=mc_balance,
        )
        mc_result["data_source"] = data_source
        mc_result["data_points"] = data_points if data_points else (len(prices) if prices else 0)
        mc_result["data_range"] = {"start": first_ts, "end": last_ts}

        return {"monte_carlo": mc_result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



class PortfolioRequest(BaseModel):
    strategy_ids: List[str]
    allocations: Optional[List[float]] = None


@router.post("/portfolio-analyze")
async def portfolio_analyze(req: PortfolioRequest):
    """Analyze a portfolio of strategies from the library."""
    from bson import ObjectId
    from engines.portfolio_engine import analyze_portfolio

    if not req.strategy_ids:
        raise HTTPException(status_code=400, detail="No strategy IDs provided")
    if len(req.strategy_ids) > 10:
        raise HTTPException(status_code=400, detail="Max 10 strategies per portfolio")

    db = get_db()
    strategies = []
    for sid in req.strategy_ids:
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(sid)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid strategy ID: {sid}")
        if not doc:
            raise HTTPException(status_code=404, detail=f"Strategy not found: {sid}")
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["id"] = str(doc["_id"])
        strategies.append(d)

    result = analyze_portfolio(strategies, req.allocations)
    return {"portfolio": result}



class AutoPortfolioRequest(BaseModel):
    target_size: int = 4
    max_pair_corr: float = 0.6
    min_score: float = 0
    min_safety: float = 0


@router.post("/portfolio-auto-build")
async def portfolio_auto_build(req: AutoPortfolioRequest):
    """Auto-build optimal portfolio from all strategies in the library."""
    from engines.portfolio_engine import auto_build_portfolio

    db = get_db()
    cursor = db.strategies.find().sort("score", -1)
    candidates = []
    async for doc in cursor:
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["id"] = str(doc["_id"])
        candidates.append(d)

    if not candidates:
        raise HTTPException(status_code=400, detail="No strategies in library")

    result = auto_build_portfolio(
        candidates,
        target_size=max(2, min(req.target_size, 7)),
        max_pair_corr=req.max_pair_corr,
        min_score=req.min_score,
        min_safety=req.min_safety,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Auto-build failed"))

    return result



class LiveAllocationRequest(BaseModel):
    strategy_ids: List[str]
    alloc_rules: Optional[dict] = None
    use_safety_adjustment: bool = True


@router.post("/portfolio-live-allocation")
async def portfolio_live_allocation(req: LiveAllocationRequest):
    """Compute dynamic allocations based on live tracking status."""
    from bson import ObjectId
    from engines.portfolio_engine import compute_dynamic_allocations

    if not req.strategy_ids:
        raise HTTPException(status_code=400, detail="No strategy IDs provided")

    db = get_db()

    # Load strategies
    strategies = []
    for sid in req.strategy_ids:
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(sid)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid ID: {sid}")
        if not doc:
            raise HTTPException(status_code=404, detail=f"Not found: {sid}")
        d = {k: v for k, v in doc.items() if k != "_id"}
        d["id"] = str(doc["_id"])
        strategies.append(d)

    # Load tracking data
    tracking_map = {}
    for sid in req.strategy_ids:
        track = await db.live_tracking.find_one({"strategy_id": sid})
        if track:
            tracking_map[sid] = {k: v for k, v in track.items() if k != "_id"}

    result = compute_dynamic_allocations(
        strategies,
        tracking_map,
        alloc_rules=req.alloc_rules,
        use_safety_adjustment=req.use_safety_adjustment,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Log allocation history (append-only)
    history_doc = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "strategy_ids": req.strategy_ids,
        "num_strategies": result.get("num_strategies", 0),
        "adjustments": [
            {
                "strategy_id": a["strategy_id"],
                "pair": a["pair"],
                "timeframe": a["timeframe"],
                "status": a["status"],
                "allocation": a["allocation"],
                "final_multiplier": a["final_multiplier"],
                "direction": a["direction"],
                "reduced": a["reduced"],
            }
            for a in result.get("adjustments", [])
        ],
        "summary": result.get("summary", {}),
        "alloc_rules": result.get("alloc_rules", {}),
    }
    try:
        await db.allocation_history.insert_one(history_doc)
    except Exception as e:
        logger.warning(f"Failed to log allocation history: {e}")

    return result


@router.get("/allocation-history")
async def get_allocation_history(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    strategy_id: Optional[str] = None,
    limit: int = 50,
):
    """Fetch allocation history with optional filters."""
    db = get_db()
    query = {}
    if strategy_id:
        query["strategy_ids"] = strategy_id
    if symbol:
        query["adjustments.pair"] = symbol
    if timeframe:
        query["adjustments.timeframe"] = timeframe

    cursor = db.allocation_history.find(query, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 200))
    results = []
    async for doc in cursor:
        results.append(doc)

    # Build status transition summary
    status_freq = {"STABLE": 0, "WARNING": 0, "FAILING": 0, "AUTO_DISABLED": 0}
    transitions = []
    for doc in results:
        for a in doc.get("adjustments", []):
            st = a.get("status", "STABLE")
            if st in status_freq:
                status_freq[st] += 1

    # Track transitions between consecutive records per strategy
    by_strategy = {}
    for doc in reversed(results):
        for a in doc.get("adjustments", []):
            sid = a.get("strategy_id", "")
            new_status = a.get("status", "STABLE")
            if sid in by_strategy and by_strategy[sid] != new_status:
                transitions.append({
                    "strategy_id": sid,
                    "pair": a.get("pair", ""),
                    "from": by_strategy[sid],
                    "to": new_status,
                    "timestamp": doc.get("timestamp", ""),
                })
            by_strategy[sid] = new_status

    return {
        "history": results,
        "total": len(results),
        "status_frequency": status_freq,
        "transitions": transitions[-20:],
    }


# ═══════ REBALANCING ═══════

class RebalanceConfigRequest(BaseModel):
    enabled: bool = False
    strategy_ids: List[str] = []
    interval_minutes: int = 60
    max_allocation_pct: float = 50.0
    deviation_threshold_pct: float = 10.0
    alloc_rules: Optional[dict] = None
    use_safety_adjustment: bool = True


@router.get("/rebalance/config")
async def get_rebalance_config():
    """Get current rebalance configuration."""
    db = get_db()
    cfg = await db.rebalance_config.find_one({"_id": "main"}, {"_id": 0})
    if not cfg:
        return {
            "enabled": False,
            "strategy_ids": [],
            "interval_minutes": 60,
            "max_allocation_pct": 50.0,
            "deviation_threshold_pct": 10.0,
            "alloc_rules": None,
            "use_safety_adjustment": True,
            "last_rebalance": None,
            "last_changes": [],
        }
    return cfg


@router.post("/rebalance/config")
async def save_rebalance_config(req: RebalanceConfigRequest):
    """Save rebalance configuration (upsert)."""
    db = get_db()
    doc = {
        "_id": "main",
        "enabled": req.enabled,
        "strategy_ids": req.strategy_ids,
        "interval_minutes": req.interval_minutes,
        "max_allocation_pct": req.max_allocation_pct,
        "deviation_threshold_pct": req.deviation_threshold_pct,
        "alloc_rules": req.alloc_rules,
        "use_safety_adjustment": req.use_safety_adjustment,
    }
    await db.rebalance_config.update_one({"_id": "main"}, {"$set": doc}, upsert=True)
    return {"message": "Config saved", "enabled": req.enabled}


@router.post("/rebalance/run")
async def run_rebalance(reason: str = "manual"):
    """Execute a rebalance cycle using saved config."""
    from bson import ObjectId
    from engines.portfolio_engine import compute_dynamic_allocations

    db = get_db()
    cfg = await db.rebalance_config.find_one({"_id": "main"})
    if not cfg:
        raise HTTPException(status_code=400, detail="No rebalance config saved")
    if not cfg.get("strategy_ids"):
        raise HTTPException(status_code=400, detail="No strategies configured")

    strategy_ids = cfg["strategy_ids"]
    max_alloc = cfg.get("max_allocation_pct", 50.0) / 100.0

    # Load strategies
    strategies = []
    for sid in strategy_ids:
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(sid)})
        except Exception:
            continue
        if doc:
            d = {k: v for k, v in doc.items() if k != "_id"}
            d["id"] = str(doc["_id"])
            strategies.append(d)

    if len(strategies) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 valid strategies")

    # Load tracking data
    tracking_map = {}
    for sid in strategy_ids:
        track = await db.live_tracking.find_one({"strategy_id": sid})
        if track:
            tracking_map[sid] = {k: v for k, v in track.items() if k != "_id"}

    # Compute new allocations
    result = compute_dynamic_allocations(
        strategies,
        tracking_map,
        alloc_rules=cfg.get("alloc_rules"),
        use_safety_adjustment=cfg.get("use_safety_adjustment", True),
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # Apply max allocation cap
    adjustments = result.get("adjustments", [])
    capped = False
    for a in adjustments:
        if a["allocation"] > max_alloc:
            a["allocation"] = round(max_alloc, 4)
            capped = True

    # Re-normalize if capped
    if capped:
        total = sum(a["allocation"] for a in adjustments)
        if total > 0:
            for a in adjustments:
                a["allocation"] = round(a["allocation"] / total, 4)

    # Get previous allocations for comparison
    prev = await db.allocation_history.find_one(
        {"strategy_ids": {"$all": strategy_ids}},
        {"_id": 0},
        sort=[("timestamp", -1)],
    )
    prev_map = {}
    if prev:
        for pa in prev.get("adjustments", []):
            prev_map[pa["strategy_id"]] = pa.get("allocation", 0)

    # Build changes list
    changes = []
    for a in adjustments:
        sid = a["strategy_id"]
        old_alloc = prev_map.get(sid, 0)
        new_alloc = a["allocation"]
        diff = new_alloc - old_alloc
        if abs(diff) > 0.005:
            changes.append({
                "strategy_id": sid,
                "pair": a["pair"],
                "timeframe": a["timeframe"],
                "status": a["status"],
                "old_allocation": round(old_alloc, 4),
                "new_allocation": round(new_alloc, 4),
                "change": round(diff, 4),
                "direction": "INCREASED" if diff > 0 else "DECREASED",
            })

    # Check deviation threshold
    dev_threshold = cfg.get("deviation_threshold_pct", 10.0) / 100.0
    significant = any(abs(c["change"]) >= dev_threshold for c in changes)

    now = datetime.now(timezone.utc).isoformat()

    # Log to allocation_history with rebalance metadata
    history_doc = {
        "timestamp": now,
        "strategy_ids": strategy_ids,
        "num_strategies": len(strategies),
        "adjustments": [
            {
                "strategy_id": a["strategy_id"],
                "pair": a["pair"],
                "timeframe": a["timeframe"],
                "status": a["status"],
                "allocation": a["allocation"],
                "final_multiplier": a.get("final_multiplier", 1.0),
                "direction": a.get("direction", "UNCHANGED"),
                "reduced": a.get("reduced", False),
            }
            for a in adjustments
        ],
        "summary": result.get("summary", {}),
        "alloc_rules": result.get("alloc_rules", {}),
        "rebalance": True,
        "rebalance_reason": reason,
        "changes": changes,
        "capped": capped,
        "max_allocation_pct": cfg.get("max_allocation_pct", 50.0),
    }
    try:
        await db.allocation_history.insert_one(history_doc)
    except Exception as e:
        logger.warning(f"Failed to log rebalance history: {e}")

    # Update last rebalance in config
    await db.rebalance_config.update_one(
        {"_id": "main"},
        {"$set": {
            "last_rebalance": now,
            "last_changes": changes,
            "last_significant": significant,
        }},
    )

    return {
        "rebalanced": True,
        "timestamp": now,
        "reason": reason,
        "num_strategies": len(strategies),
        "changes": changes,
        "significant": significant,
        "capped": capped,
        "adjustments": adjustments,
        "summary": result.get("summary", {}),
    }


@router.get("/rebalance/status")
async def get_rebalance_status():
    """Get last rebalance status and upcoming schedule."""
    db = get_db()
    cfg = await db.rebalance_config.find_one({"_id": "main"}, {"_id": 0})
    if not cfg:
        return {
            "enabled": False,
            "last_rebalance": None,
            "last_changes": [],
            "strategy_count": 0,
        }

    # Get recent rebalance events
    cursor = db.allocation_history.find(
        {"rebalance": True},
        {"_id": 0, "timestamp": 1, "rebalance_reason": 1, "changes": 1, "summary": 1, "capped": 1},
    ).sort("timestamp", -1).limit(10)
    recent = []
    async for doc in cursor:
        recent.append(doc)

    return {
        "enabled": cfg.get("enabled", False),
        "interval_minutes": cfg.get("interval_minutes", 60),
        "max_allocation_pct": cfg.get("max_allocation_pct", 50.0),
        "deviation_threshold_pct": cfg.get("deviation_threshold_pct", 10.0),
        "strategy_count": len(cfg.get("strategy_ids", [])),
        "last_rebalance": cfg.get("last_rebalance"),
        "last_changes": cfg.get("last_changes", []),
        "last_significant": cfg.get("last_significant", False),
        "recent_events": recent,
    }


# ═══════ EXPECTED VALUE + SAFETY MARGIN ENGINE ═══════

class EvaluateDecisionRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[dict]] = None
    firm: Optional[str] = None
    rules_config: Optional[dict] = None
    challenge_fee: Optional[float] = None
    funded_balance: Optional[float] = None
    profit_split_pct: Optional[float] = None
    monthly_target_pct: Optional[float] = None
    expected_months: Optional[int] = None
    mc_simulations: int = 20


@router.post("/evaluate-decision")
async def evaluate_decision_endpoint(req: EvaluateDecisionRequest):
    """
    Full decision evaluation: probability + expected value + safety margin + decision score.
    Answers "is this strategy worth taking for this firm's challenge?"
    """
    from engines.expected_value import calculate_expected_value, calculate_safety_margin, calculate_decision_score
    from engines.pass_probability import estimate_pass_probability
    from engines.challenge_simulator import simulate_challenge
    from engines.strategy_profiler import profile_strategy

    # Resolve trades
    trades = req.strategy_trades
    if req.strategy_id and trades is None:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")
        bt = doc.get("backtest_results") or {}
        trades = bt.get("trades", [])
        if not trades:
            raise HTTPException(status_code=400, detail="Strategy has no backtest trades.")

    if trades is None:
        raise HTTPException(status_code=400, detail="Provide either strategy_id or strategy_trades.")

    # Resolve rules
    rules = req.rules_config
    firm_slug = ""
    firm_doc = None
    if req.firm:
        from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
        firm_doc = await get_rules_by_slug(req.firm.lower())
        if firm_doc:
            rules = await rules_to_sim_config(firm_doc)
            firm_slug = req.firm.lower()
        else:
            from engines.challenge_simulator import get_firm_rules
            rules = get_firm_rules(req.firm)
            firm_slug = req.firm.lower()
    if not rules:
        # Default FTMO
        from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
        firm_doc = await get_rules_by_slug("ftmo")
        if firm_doc:
            rules = await rules_to_sim_config(firm_doc)
            firm_slug = "ftmo"

    if not rules:
        raise HTTPException(status_code=400, detail="Could not resolve firm rules.")

    # Run simulation + probability
    sim_result = simulate_challenge(trades, rules)
    prob_result = estimate_pass_probability(
        trades, rules, n_simulations=max(10, min(req.mc_simulations, 100))
    )
    prob = prob_result.get("pass_probability", 0)

    # Profile for DD data
    dna = profile_strategy(trades)
    max_dd = dna.get("risk", {}).get("max_drawdown_pct", 0)
    daily_dd_p90 = dna.get("risk", {}).get("daily_dd_distribution", {}).get("p90", 0)
    sim_daily_dd = sim_result.get("max_daily_drawdown_pct", 0)

    # Resolve firm rule limits
    if firm_doc:
        total_dd_limit = firm_doc.get("rules", {}).get("total_dd", {}).get("max_pct", 10)
        daily_dd_limit = firm_doc.get("rules", {}).get("daily_dd", {}).get("max_pct", 5)
        dd_type = firm_doc.get("rules", {}).get("total_dd", {}).get("type", "static")
    else:
        total_dd_limit = rules.get("max_total_dd_pct", 10)
        daily_dd_limit = rules.get("max_daily_dd_pct", 5)
        dd_type = rules.get("drawdown_type", "static")

    # Calculate EV
    ev_data = calculate_expected_value(
        prob,
        challenge_fee=req.challenge_fee or 0,
        funded_balance=req.funded_balance or 0,
        profit_split_pct=req.profit_split_pct or 0,
        monthly_target_pct=req.monthly_target_pct or 0,
        expected_months=req.expected_months or 0,
        firm_slug=firm_slug,
    )

    # Calculate safety margin
    safety_data = calculate_safety_margin(
        max_dd, max(sim_daily_dd, daily_dd_p90),
        total_dd_limit, daily_dd_limit,
        strategy_dd_p90=daily_dd_p90,
        drawdown_type=dd_type,
    )

    # Calculate decision score
    decision_data = calculate_decision_score(prob, ev_data, safety_data)

    return {
        "evaluation": {
            "expected_value": ev_data,
            "safety_margin": safety_data,
            "decision": decision_data,
            "probability": {
                "pass_probability": prob,
                "risk_label": prob_result.get("risk_label", ""),
                "confidence_interval": prob_result.get("confidence_interval", []),
            },
            "simulation": {
                "status": sim_result.get("status", ""),
                "profit_pct": sim_result.get("profit_pct", 0),
                "max_drawdown_pct": sim_result.get("max_drawdown_pct", 0),
            },
            "firm": firm_slug or "custom",
        },
    }


# ═══════ STRATEGY MUTATION ENGINE ═══════

class MutateStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_text: Optional[str] = None
    pair: str = "EURUSD"
    timeframe: str = "H1"
    firm: Optional[str] = None
    rules_config: Optional[dict] = None
    mc_simulations: int = 20


@router.post("/mutate-strategy")
async def mutate_strategy_endpoint(req: MutateStrategyRequest):
    """
    Mutate a strategy to improve prop firm pass probability.
    Diagnoses issues, generates controlled mutations, evaluates each,
    and returns the best improvement.
    """
    from engines.strategy_mutation import mutate_strategy

    strategy_text = req.strategy_text
    pair = req.pair
    timeframe = req.timeframe

    if req.strategy_id and not strategy_text:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")
        strategy_text = doc.get("strategy_text", "")
        pair = doc.get("pair", pair)
        timeframe = doc.get("timeframe", timeframe)

    if not strategy_text:
        raise HTTPException(status_code=400, detail="Provide either strategy_id or strategy_text.")

    # Load real market data
    prices, data_source, data_points, _, _ = await _load_real_data(pair, timeframe)
    if not prices or data_source == "sample":
        raise HTTPException(
            status_code=400,
            detail=f"Real market data required for {pair}/{timeframe}. Download data first.",
        )

    # Resolve rules
    rules = req.rules_config
    if req.firm and not rules:
        from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
        rule_doc = await get_rules_by_slug(req.firm.lower())
        if rule_doc:
            rules = await rules_to_sim_config(rule_doc)
        if not rules:
            from engines.challenge_simulator import get_firm_rules
            rules = get_firm_rules(req.firm)
        if not rules:
            raise HTTPException(status_code=400, detail=f"Unknown firm '{req.firm}'")
    if not rules:
        # Default to FTMO
        from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
        rule_doc = await get_rules_by_slug("ftmo")
        if rule_doc:
            rules = await rules_to_sim_config(rule_doc)
        else:
            from engines.challenge_simulator import get_firm_rules
            rules = get_firm_rules("ftmo")

    result = mutate_strategy(
        strategy_text, pair, timeframe, prices, data_points,
        rules, mc_simulations=max(10, min(req.mc_simulations, 50)),
    )
    return {"mutation": result}


# ═══════ PASS PROBABILITY ENGINE (MONTE CARLO) ═══════

class EstimateProbabilityRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[dict]] = None
    firm: Optional[str] = None
    rules_config: Optional[dict] = None
    n_simulations: int = 50
    noise_pct: float = 0.10


@router.post("/estimate-probability")
async def estimate_probability_endpoint(req: EstimateProbabilityRequest):
    """
    Monte Carlo pass probability estimation.
    Runs N simulations with trade shuffling and PnL perturbation.
    """
    from engines.pass_probability import estimate_pass_probability

    trades = req.strategy_trades
    if req.strategy_id and trades is None:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")
        bt = doc.get("backtest_results") or {}
        trades = bt.get("trades", [])
        if not trades:
            raise HTTPException(status_code=400, detail="Strategy has no backtest trades.")

    if trades is None:
        raise HTTPException(status_code=400, detail="Provide either strategy_id or strategy_trades.")

    # Resolve rules
    rules = req.rules_config
    if req.firm and not rules:
        from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
        rule_doc = await get_rules_by_slug(req.firm.lower())
        if rule_doc:
            rules = await rules_to_sim_config(rule_doc)
        else:
            from engines.challenge_simulator import get_firm_rules
            rules = get_firm_rules(req.firm)
        if not rules:
            raise HTTPException(status_code=400, detail=f"Unknown firm '{req.firm}'")

    if not rules:
        raise HTTPException(status_code=400, detail="Provide either firm name or rules_config.")

    result = estimate_pass_probability(
        trades, rules,
        n_simulations=max(10, min(req.n_simulations, 200)),
        noise_pct=max(0.01, min(req.noise_pct, 0.30)),
    )
    return {"probability": result}


# ═══════ STRATEGY ↔ PROP FIRM MATCHING ENGINE ═══════

class MatchStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[dict]] = None
    initial_balance: float = 10000
    include_probability: bool = False
    n_simulations: int = 30


@router.post("/match-strategy")
async def match_strategy_endpoint(req: MatchStrategyRequest):
    """
    Match a strategy against all available prop firms.
    Pre-filters by DNA compatibility, simulates challenges,
    scores and ranks matches. Returns top_matches + rejected.
    """
    from engines.matching_engine import match_strategy_to_firms

    trades = req.strategy_trades
    strategy_meta = None

    if req.strategy_id and trades is None:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")

        bt = doc.get("backtest_results") or {}
        trades = bt.get("trades", [])
        strategy_meta = {
            "id": str(doc["_id"]),
            "pair": doc.get("pair", ""),
            "timeframe": doc.get("timeframe", ""),
        }
        if not trades:
            raise HTTPException(
                status_code=400,
                detail="Strategy has no backtest trades. Run a backtest first.",
            )

    if trades is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either strategy_id or strategy_trades.",
        )

    result = await match_strategy_to_firms(
        trades, req.initial_balance,
        include_probability=req.include_probability,
        n_simulations=req.n_simulations,
    )

    if strategy_meta:
        result["strategy"] = strategy_meta

    return {"matching": result}


# ═══════ STRATEGY PROFILER (DNA LAYER) ═══════

class ProfileStrategyRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[dict]] = None
    initial_balance: float = 10000
    save_profile: bool = True


@router.post("/profile-strategy")
async def profile_strategy_endpoint(req: ProfileStrategyRequest):
    """
    Build a complete behavioral DNA profile for a strategy.
    Accepts strategy_id (loads trades from DB) or strategy_trades (raw).
    Optionally saves the profile to the strategy document.
    """
    from engines.strategy_profiler import profile_strategy

    trades = req.strategy_trades
    strategy_id = None

    if req.strategy_id and trades is None:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")

        bt = doc.get("backtest_results") or {}
        trades = bt.get("trades", [])
        strategy_id = str(doc["_id"])
        if not trades:
            raise HTTPException(
                status_code=400,
                detail="Strategy has no backtest trades. Run a backtest first.",
            )

    if trades is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either strategy_id or strategy_trades.",
        )

    profile = profile_strategy(trades, req.initial_balance)

    # Save profile to strategy document if requested and strategy_id provided
    if req.save_profile and strategy_id:
        db = get_db()
        from bson import ObjectId
        await db.strategies.update_one(
            {"_id": ObjectId(strategy_id)},
            {"$set": {
                "profile": profile,
                "profile_updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        profile["saved"] = True
        profile["strategy_id"] = strategy_id

    return {"profile": profile}


# ═══════ PROP FIRM CHALLENGE SIMULATOR + RULE ENGINE ═══════

class SimulateChallengeRequest(BaseModel):
    strategy_id: Optional[str] = None
    strategy_trades: Optional[List[dict]] = None
    firm: Optional[str] = None
    rules_config: Optional[dict] = None


@router.post("/simulate-challenge")
async def simulate_challenge_endpoint(req: SimulateChallengeRequest):
    """
    Simulate a prop firm challenge for a strategy.
    Accepts either strategy_id (loads trades from DB) or strategy_trades (raw list).
    Accepts either firm name (loads rules from DB) or custom rules_config.
    Phase 2: Rules are loaded dynamically from DB via rule_engine.
    """
    from engines.challenge_simulator import simulate_challenge, get_firm_rules as get_legacy_rules
    from engines.rule_engine import get_rules_by_slug, rules_to_sim_config

    # ── Resolve trades ──
    trades = req.strategy_trades
    strategy_meta = None

    if req.strategy_id and not trades:
        from bson import ObjectId
        db = get_db()
        try:
            doc = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid strategy ID")
        if not doc:
            raise HTTPException(status_code=404, detail="Strategy not found")

        bt = doc.get("backtest_results") or {}
        trades = bt.get("trades", [])
        strategy_meta = {
            "id": str(doc["_id"]),
            "pair": doc.get("pair", ""),
            "timeframe": doc.get("timeframe", ""),
            "strategy_type": doc.get("strategy_type", ""),
        }
        if not trades:
            raise HTTPException(
                status_code=400,
                detail="Strategy has no backtest trades. Run a backtest first.",
            )

    if trades is None and not req.strategy_id:
        raise HTTPException(
            status_code=400,
            detail="Provide either strategy_id or strategy_trades.",
        )

    # ── Resolve rules (Phase 2: DB first, legacy fallback) ──
    rules = req.rules_config
    rule_source = "custom"

    if req.firm and not rules:
        # Try DB-stored rules first
        rule_doc = await get_rules_by_slug(req.firm.lower())
        if rule_doc:
            rules = await rules_to_sim_config(rule_doc)
            rule_source = "database"
        else:
            # Legacy fallback
            rules = get_legacy_rules(req.firm)
            rule_source = "legacy_preset"
            if not rules:
                from engines.rule_engine import get_all_rules
                db_rules = await get_all_rules()
                available = [r["firm_slug"] for r in db_rules]
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown firm '{req.firm}'. Available: {available}",
                )

    if not rules:
        raise HTTPException(
            status_code=400,
            detail="Provide either firm name or rules_config.",
        )

    # ── Run simulation ──
    try:
        result = simulate_challenge(trades, rules)
    except Exception as e:
        logger.error(f"Challenge simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    result["rule_source"] = rule_source
    if strategy_meta:
        result["strategy"] = strategy_meta

    # Phase 9 — Prop Firm Intelligence Panel (additive).
    # If the strategy has a saved validation_report / decision on its doc we
    # layer them in; otherwise the panel uses the simulation alone.
    from engines.prop_firm_panel import build_prop_firm_panel
    validation_report = None
    decision_data = None
    if req.strategy_id:
        from bson import ObjectId
        try:
            doc2 = await get_db().strategies.find_one(
                {"_id": ObjectId(req.strategy_id)},
                {"validation": 1, "decision": 1, "_id": 0},
            )
            if doc2:
                validation_report = doc2.get("validation")
                decision_data = doc2.get("decision")
        except Exception:
            pass
    result["prop_firm_panel"] = build_prop_firm_panel(
        simulation=result,
        pass_probability=None,
        validation_report=validation_report,
        decision=decision_data,
    )

    return {"simulation": result}


@router.get("/challenge-firms")
async def list_challenge_firms():
    """List available prop firm rule presets from DB (with legacy fallback)."""
    from engines.rule_engine import get_all_rules
    db_rules = await get_all_rules()
    firms = {}
    for r in db_rules:
        slug = r.get("firm_slug", "")
        firms[slug] = {
            "name": r.get("firm_name", slug),
            "phase": r.get("phase", ""),
            "initial_balance": r.get("initial_balance", 100000),
            "version": r.get("version", 1),
            "confidence_score": r.get("confidence_score", 0),
            "validated": r.get("validated", False),
            "rules": r.get("rules", {}),
        }
    return {"firms": firms, "source": "database", "count": len(firms)}


# ═══════ RULE ENGINE CRUD ═══════

class CreateRuleRequest(BaseModel):
    firm_slug: str
    firm_name: str
    phase: str = "Challenge"
    initial_balance: float = 100000
    rules: dict
    confidence_score: int = 50
    confidence_notes: str = ""
    validated: bool = False
    manual_override: bool = False


class UpdateRuleRequest(BaseModel):
    rules: Optional[dict] = None
    initial_balance: Optional[float] = None
    phase: Optional[str] = None
    firm_name: Optional[str] = None
    confidence_score: Optional[int] = None
    confidence_notes: Optional[str] = None
    validated: Optional[bool] = None
    manual_override: Optional[bool] = None
    change_note: str = ""


class ValidateRuleRequest(BaseModel):
    confidence_score: int
    notes: str = ""


class OverrideRuleRequest(BaseModel):
    override: bool
    note: str = ""


@router.get("/challenge-rules")
async def list_all_rules():
    """List all rule sets from DB with full schema."""
    from engines.rule_engine import get_all_rules
    rules = await get_all_rules()
    return {"rules": rules, "count": len(rules)}


@router.get("/challenge-rules/{firm_slug}")
async def get_rule_by_slug(firm_slug: str):
    """Get a single firm's full rule set."""
    from engines.rule_engine import get_rules_by_slug
    rule = await get_rules_by_slug(firm_slug)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule set '{firm_slug}' not found")
    return {"rule": rule}


@router.post("/challenge-rules")
async def create_rule_endpoint(req: CreateRuleRequest):
    """Create a new firm rule set."""
    from engines.rule_engine import create_rule
    try:
        doc = await create_rule(req.model_dump())
        return {"rule": doc, "message": "Rule set created"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/challenge-rules/{firm_slug}")
async def update_rule_endpoint(firm_slug: str, req: UpdateRuleRequest):
    """Update an existing firm's rules. Increments version."""
    from engines.rule_engine import update_rule
    updates = {k: v for k, v in req.model_dump().items() if v is not None and k != "change_note"}
    try:
        doc = await update_rule(firm_slug, updates, req.change_note)
        return {"rule": doc, "message": f"Rule set updated to v{doc['version']}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/challenge-rules/{firm_slug}")
async def delete_rule_endpoint(firm_slug: str):
    """Delete a firm's rule set."""
    from engines.rule_engine import delete_rule
    deleted = await delete_rule(firm_slug)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule set '{firm_slug}' not found")
    return {"message": f"Rule set '{firm_slug}' deleted"}


@router.post("/challenge-rules/{firm_slug}/validate")
async def validate_rule_endpoint(firm_slug: str, req: ValidateRuleRequest):
    """Mark a rule set as validated with a confidence score."""
    from engines.rule_engine import validate_rule
    try:
        doc = await validate_rule(firm_slug, req.confidence_score, req.notes)
        return {"rule": doc, "message": "Rule validated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/challenge-rules/{firm_slug}/override")
async def override_rule_endpoint(firm_slug: str, req: OverrideRuleRequest):
    """Set or clear manual override on a rule set."""
    from engines.rule_engine import override_rule
    try:
        doc = await override_rule(firm_slug, req.override, req.note)
        return {"rule": doc, "message": f"Override {'enabled' if req.override else 'disabled'}"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/challenge-rules/{firm_slug}/changelog")
async def get_rule_changelog(firm_slug: str):
    """Get version history for a rule set."""
    from engines.rule_engine import get_rules_by_slug
    rule = await get_rules_by_slug(firm_slug)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule set '{firm_slug}' not found")
    return {
        "firm_slug": firm_slug,
        "current_version": rule.get("version", 1),
        "changelog": rule.get("changelog", []),
    }


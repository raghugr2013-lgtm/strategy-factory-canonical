from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from engines.db import get_db
from engines.live_tracking_engine import update_tracking

router = APIRouter()


class StartTrackingRequest(BaseModel):
    strategy_id: str
    failure_threshold: int = 3
    auto_disable: bool = True


class DataRefreshRequest(BaseModel):
    symbol: str
    timeframe: str
    days_back: int = 1


@router.post("/live/start")
async def start_tracking(req: StartTrackingRequest):
    """Start live tracking for a strategy from the library."""
    from bson import ObjectId
    db = get_db()

    # Verify strategy exists
    try:
        strat = await db.strategies.find_one({"_id": ObjectId(req.strategy_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid strategy ID")
    if not strat:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Check if already tracking
    existing = await db.live_tracking.find_one({"strategy_id": req.strategy_id})
    if existing:
        return {"message": "Already tracking", "id": req.strategy_id, "active": existing.get("active", True)}

    # Create tracking record
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "strategy_id": req.strategy_id,
        "pair": strat.get("pair", ""),
        "timeframe": strat.get("timeframe", ""),
        "strategy_type": strat.get("strategy_type", ""),
        "active": True,
        "status": "STABLE",
        "live_metrics": None,
        "alerts": [],
        "consecutive_failures": 0,
        "failure_threshold": max(2, min(req.failure_threshold, 10)),
        "auto_disable": req.auto_disable,
        "auto_disabled": False,
        "started_at": now,
        "last_updated": now,
        "candles_count": 0,
    }
    await db.live_tracking.insert_one(doc)
    return {"message": "Tracking started", "id": req.strategy_id, "auto_disable": req.auto_disable, "failure_threshold": doc["failure_threshold"]}


@router.post("/live/stop")
async def stop_tracking(req: StartTrackingRequest):
    """Stop live tracking for a strategy."""
    db = get_db()
    result = await db.live_tracking.update_one(
        {"strategy_id": req.strategy_id},
        {"$set": {"active": False, "stopped_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tracking not found")
    return {"message": "Tracking stopped", "id": req.strategy_id}


@router.post("/live/update/{strategy_id}")
async def update_single_tracking(strategy_id: str):
    """Update live metrics for a single tracked strategy."""
    result = await update_tracking(strategy_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/live/update-all")
async def update_all_tracking():
    """Update all active tracked strategies."""
    db = get_db()
    cursor = db.live_tracking.find({"active": True})
    results = []
    async for doc in cursor:
        sid = doc["strategy_id"]
        try:
            r = await update_tracking(sid)
            results.append(r)
        except Exception as e:
            results.append({"strategy_id": sid, "error": str(e)})
    return {"updated": len(results), "results": results}


@router.get("/live/strategies")
async def get_tracked_strategies():
    """Get all tracked strategies with current status."""
    db = get_db()
    cursor = db.live_tracking.find({}, {"_id": 0}).sort("started_at", -1)
    tracked = []
    async for doc in cursor:
        tracked.append(doc)
    return {"tracked": tracked}


@router.post("/live/refresh-data")
async def refresh_market_data(req: DataRefreshRequest):
    """Fetch latest candles from Dukascopy and append to MongoDB."""
    from data_engine.dukascopy_downloader import download_and_store, INSTRUMENT_MAP

    if req.symbol not in INSTRUMENT_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {req.symbol}")

    now = datetime.now(timezone.utc)
    from datetime import timedelta
    date_from = (now - timedelta(days=req.days_back)).strftime("%Y-%m-%d")
    date_to = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    try:
        result = await download_and_store(req.symbol, req.timeframe, date_from, date_to)
        return {
            "success": True,
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "rows_inserted": result.get("rows_inserted", 0),
            "rows_skipped": result.get("rows_skipped", 0),
            "message": result.get("message", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/live/{strategy_id}")
async def remove_tracking(strategy_id: str):
    """Remove a strategy from live tracking."""
    db = get_db()
    result = await db.live_tracking.delete_one({"strategy_id": strategy_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Tracking not found")
    return {"message": "Tracking removed", "id": strategy_id}


class UpdateConfigRequest(BaseModel):
    strategy_id: str
    failure_threshold: Optional[int] = None
    auto_disable: Optional[bool] = None


@router.post("/live/config")
async def update_tracking_config(req: UpdateConfigRequest):
    """Update auto-disable configuration for a tracked strategy."""
    db = get_db()
    updates = {}
    if req.failure_threshold is not None:
        updates["failure_threshold"] = max(2, min(req.failure_threshold, 10))
    if req.auto_disable is not None:
        updates["auto_disable"] = req.auto_disable
    if not updates:
        return {"message": "No changes"}
    result = await db.live_tracking.update_one(
        {"strategy_id": req.strategy_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tracking not found")
    return {"message": "Config updated", "id": req.strategy_id, **updates}

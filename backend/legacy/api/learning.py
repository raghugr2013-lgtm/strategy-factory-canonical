"""v1.2.0-alpha2 — /api/learning/* endpoints (Phase A + Phase B).

Phase A endpoints (unchanged):
    POST /learning/runs                 — mint a fresh learning_run_id
    POST /learning/events               — write a manual outcome event
    POST /learning/operator-decision    — approve/reject an outcome
    GET  /learning/events               — list stored events
    GET  /learning/runs                 — list rollup of runs
    GET  /learning/lineage/{hash}       — walk a hash's genealogy

Phase B endpoints (new — self-improving learning engine):
    POST /learning/cycles               — kick off a continuous learning cycle
    GET  /learning/cycles/{run_id}      — get status + stage stream
    GET  /learning/cycles               — list active + recent cycles
    GET  /learning/metrics              — supervisor counters + pass rates
    GET  /learning/config               — effective env-driven thresholds
    POST /learning/scheduler/start      — start the periodic scheduler
    POST /learning/scheduler/stop       — stop the periodic scheduler
    GET  /learning/scheduler/status     — scheduler state
    GET  /learning/lineage/detail/{h}   — Phase B enriched lineage
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines.db import get_db
from engines.learning import (
    COLL,
    LearningSeed,
    config as lcfg,
    counters_snapshot,
    emit,
    emit_operator_decision,
    get_lineage,
    get_run,
    new_run_id,
    run_learning_cycle,
    scheduler_status,
    start_scheduler,
    stop_scheduler,
    VALID_STAGES,
)

router = APIRouter(prefix="/learning", tags=["learning"])


# ── Phase A models ───────────────────────────────────────────────
class ManualEventRequest(BaseModel):
    learning_run_id: Optional[str] = None
    stage: str = Field(..., pattern="|".join(VALID_STAGES))
    status: str = Field(..., pattern="pass|fail|partial|skipped")
    strategy_hash: Optional[str] = None
    reason: Optional[str] = ""
    metrics: Optional[dict] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class OperatorDecisionRequest(BaseModel):
    learning_run_id: str
    strategy_hash: str
    approved: bool
    rating: Optional[int] = None
    comment: Optional[str] = ""


class CycleRequest(BaseModel):
    pair: str = "EURUSD"
    timeframe: str = "H1"
    style: str = "trend-following"
    count: int = 1
    max_duration_s: float = 120.0


# ── Phase A endpoints ────────────────────────────────────────────
@router.post("/runs")
async def start_run():
    return {"learning_run_id": new_run_id()}


@router.post("/events")
async def write_event(req: ManualEventRequest):
    run_id = req.learning_run_id or new_run_id()
    inserted_id = await emit(
        req.stage,
        learning_run_id=run_id,
        status=req.status,
        strategy_hash=req.strategy_hash,
        reason=req.reason or "",
        metrics=req.metrics or {},
        provider=req.provider,
        model=req.model,
    )
    return {"ok": inserted_id is not None, "event_id": inserted_id,
            "learning_run_id": run_id}


@router.post("/operator-decision")
async def operator_decision(req: OperatorDecisionRequest):
    inserted_id = await emit_operator_decision(
        req.learning_run_id, req.strategy_hash,
        approved=req.approved, rating=req.rating, comment=req.comment or "",
    )
    return {"ok": inserted_id is not None, "event_id": inserted_id}


@router.get("/events")
async def list_events(
    strategy_hash: Optional[str] = None,
    learning_run_id: Optional[str] = None,
    stage: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    q = {}
    if strategy_hash:     q["strategy_hash"] = strategy_hash
    if learning_run_id:   q["learning_run_id"] = learning_run_id
    if stage:             q["stage"] = stage
    if provider:          q["provider"] = provider
    db = get_db()
    events = []
    async for e in db[COLL].find(q).sort("ts", -1).limit(limit):
        e["_id"] = str(e["_id"])
        events.append(e)
    return {"events": events, "count": len(events), "query": q}


@router.get("/runs")
async def list_runs(limit: int = Query(20, ge=1, le=200)):
    db = get_db()
    pipeline = [
        {"$group": {
            "_id": "$learning_run_id",
            "first_ts": {"$min": "$ts"},
            "last_ts":  {"$max": "$ts"},
            "stages":   {"$addToSet": "$stage"},
            "n":        {"$sum": 1},
            "final_status": {"$last": "$status"},
        }},
        {"$sort": {"last_ts": -1}},
        {"$limit": limit},
    ]
    runs = []
    async for r in db[COLL].aggregate(pipeline):
        runs.append({
            "learning_run_id": r["_id"],
            "first_ts": r["first_ts"], "last_ts": r["last_ts"],
            "n_events": r["n"], "stages": r["stages"],
            "final_status": r["final_status"],
        })
    return {"runs": runs, "count": len(runs)}


@router.get("/lineage/{strategy_hash}")
async def lineage(strategy_hash: str):
    db = get_db()
    chain: List[str] = [strategy_hash]
    ancestor = strategy_hash
    for _ in range(20):
        row = await db[COLL].find_one(
            {"strategy_hash": ancestor, "parent_hash": {"$ne": None}},
            {"parent_hash": 1, "_id": 0},
            sort=[("ts", 1)],
        )
        if not row or not row.get("parent_hash"):
            break
        if row["parent_hash"] in chain:
            break
        chain.append(row["parent_hash"])
        ancestor = row["parent_hash"]
    events = []
    async for e in db[COLL].find({"strategy_hash": {"$in": chain}}).sort("ts", 1):
        e["_id"] = str(e["_id"])
        events.append(e)
    return {"strategy_hash": strategy_hash, "chain": chain, "events": events}


# ── Phase B endpoints ────────────────────────────────────────────
@router.post("/cycles")
async def start_cycle(req: CycleRequest, _u=Depends(require_admin)):
    """Kick off ONE continuous learning cycle. Runs to completion in
    the request context and returns the final LearningRun record.
    """
    seed = LearningSeed(
        pair=req.pair, timeframe=req.timeframe,
        style=req.style, count=req.count,
        max_duration_s=req.max_duration_s,
    )
    run = await run_learning_cycle(seed)
    return run.to_dict()


@router.get("/cycles")
async def list_cycles():
    """List active + recent cycles held in the supervisor's in-process
    buffer. Cheap — no DB read."""
    return counters_snapshot()


@router.get("/cycles/{run_id}")
async def get_cycle(run_id: str):
    row = get_run(run_id)
    if not row:
        raise HTTPException(status_code=404, detail={"code": "cycle_not_found",
                                                     "run_id": run_id})
    return row


@router.get("/metrics")
async def learning_metrics():
    """Supervisor counters + rolled-up pass rates from outcome_events.
    Provides the future dashboard everything it needs in one call.
    """
    snap = counters_snapshot()
    counters = snap.get("counters", {})
    db = get_db()
    pass_rates: dict = {}
    try:
        pipeline = [
            {"$group": {
                "_id": {"stage": "$stage", "status": "$status"},
                "n": {"$sum": 1},
            }},
        ]
        per_stage: dict = {}
        async for row in db[COLL].aggregate(pipeline):
            rid = row["_id"] or {}
            stage = rid.get("stage")
            status = rid.get("status")
            if not stage:
                continue
            rec = per_stage.setdefault(stage, {"pass": 0, "fail": 0,
                                               "partial": 0, "skipped": 0})
            rec[status] = rec.get(status, 0) + int(row.get("n", 0))
        for stage, rec in per_stage.items():
            total = sum(rec.values())
            pass_rates[stage] = {
                **rec,
                "total": total,
                "pass_rate": round(
                    (rec.get("pass", 0) + 0.5 * rec.get("partial", 0)) / total,
                    4,
                ) if total else 0.0,
            }
    except Exception:
        pass_rates = {"_error": "aggregation_failed"}
    return {
        "counters": counters,
        "pass_rates": pass_rates,
        "active_runs": len(snap.get("active_runs") or []),
        "recent_runs": len(snap.get("recent_runs") or []),
    }


@router.get("/config")
async def learning_config():
    """Effective env-driven configuration. Read-only for now."""
    return lcfg.snapshot()


@router.post("/scheduler/start")
async def scheduler_start(_u=Depends(require_admin)):
    return await start_scheduler()


@router.post("/scheduler/stop")
async def scheduler_stop(_u=Depends(require_admin)):
    return await stop_scheduler()


@router.get("/scheduler/status")
async def scheduler_state():
    return scheduler_status()


@router.get("/lineage/detail/{strategy_hash}")
async def lineage_detail(strategy_hash: str):
    """Phase B enriched lineage — reads the `lineage` sub-doc stamped on
    the strategy collections + walks the parent chain."""
    return await get_lineage(strategy_hash)

"""v1.2.0-alpha2 — /api/learning/* endpoints.

Exposes the outcome-event ledger + genealogy walks. Every strategy's
full lineage is reachable via `GET /api/learning/lineage/{hash}`.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines.db import get_db
from engines.learning import (
    COLL,
    new_run_id,
    emit,
    emit_operator_decision,
    VALID_STAGES,
)

router = APIRouter(prefix="/learning", tags=["learning"])


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


@router.post("/runs")
async def start_run():
    """Return a fresh learning_run_id for the caller to propagate."""
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
    return {
        "ok": inserted_id is not None,
        "event_id": inserted_id,
        "learning_run_id": run_id,
    }


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
    """Full genealogy: every outcome_events row for this hash + all
    ancestor hashes reached by walking `parent_hash` links.
    """
    db = get_db()
    chain: List[str] = [strategy_hash]
    ancestor = strategy_hash
    for _ in range(20):  # cap to prevent cycles
        row = await db[COLL].find_one(
            {"strategy_hash": ancestor, "parent_hash": {"$ne": None}},
            {"parent_hash": 1, "_id": 0},
            sort=[("ts", 1)],
        )
        if not row or not row.get("parent_hash"):
            break
        if row["parent_hash"] in chain:
            break  # cycle guard
        chain.append(row["parent_hash"])
        ancestor = row["parent_hash"]
    events = []
    async for e in db[COLL].find({"strategy_hash": {"$in": chain}}).sort("ts", 1):
        e["_id"] = str(e["_id"])
        events.append(e)
    return {"strategy_hash": strategy_hash, "chain": chain, "events": events}

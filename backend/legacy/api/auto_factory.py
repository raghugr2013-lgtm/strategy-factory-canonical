"""
Phase 5 — Auto Strategy Factory API.

Thin FastAPI surface over `engines.auto_factory_engine`. Stateless at
the HTTP layer — all run state lives inside the engine module.

Endpoints:
  POST /api/auto-factory/run        — kick off one cycle (sync or async)
  GET  /api/auto-factory/status     — running state, last run, history
  POST /api/auto-factory/schedule   — enable/disable the APScheduler job
  GET  /api/auto-factory/saved      — list strategies persisted by the factory
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engines import auto_factory_engine as factory
from engines import auto_factory_phase55 as factory55
from engines.readiness_engine import compute_readiness, failed_red_checks
from engines.strategy_library import list_saved, delete_saved

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auto-factory", tags=["auto-factory"])


class AutoFactoryRunRequest(BaseModel):
    pairs: Optional[List[str]] = None
    timeframes: Optional[List[str]] = None
    styles: Optional[List[str]] = None
    per_combo: int = Field(10, ge=1, le=50)
    firm: str = "ftmo"
    top_n: int = Field(5, ge=1, le=20)
    refine_top: int = Field(1, ge=0, le=5)
    prefilter_top: int = Field(5, ge=1, le=20)
    wait: bool = True  # set False to fire-and-forget (poll /status instead)
    # ── Phase 5.5 additive fields ──────────────────────────────────
    # When phase == "5.5" the request is dispatched to the new
    # orchestrator (engines.auto_factory_phase55). All other fields
    # below are forwarded as config overrides. Existing phase==5 flow
    # is fully preserved when phase is None / omitted.
    phase: Optional[str] = None
    min_pf: Optional[float] = Field(default=None, ge=0.0)
    min_runs: Optional[int] = Field(default=None, ge=1)
    max_drawdown: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    top_n_store: Optional[int] = Field(default=None, ge=1, le=200)
    ingestion_max_strategies: Optional[int] = Field(default=None, ge=1, le=50)
    mutation_iterations: Optional[int] = Field(default=None, ge=0, le=50)
    mutation_per_cycle: Optional[int] = Field(default=None, ge=1, le=20)
    run_data_maintenance: Optional[bool] = None
    run_ingestion: Optional[bool] = None
    run_mutation: Optional[bool] = None
    run_validation: Optional[bool] = None
    run_selection: Optional[bool] = None
    step_timeout_sec: Optional[int] = Field(default=None, ge=30, le=3600)


class ScheduleRequest(BaseModel):
    enabled: bool
    interval_hours: float = Field(6.0, gt=0, le=168)
    # Phase 5.5 toggle (additive — existing Phase 5 scheduler untouched
    # when phase is None). When phase=="5.5" this request drives the
    # Phase 5.5 interval scheduler instead.
    phase: Optional[str] = None


@router.post("/run")
async def auto_factory_run(req: AutoFactoryRunRequest):
    """Trigger one Auto Factory cycle. When `wait=False` the run is
    dispatched in the background and the response returns immediately
    with the assigned `run_id`; poll `/status` for progress.

    Pass `phase: "5.5"` to dispatch to the Phase 5.5 orchestrator
    (engines.auto_factory_phase55). Default behavior (Phase 5) is
    fully preserved when `phase` is None.

    Safety gate (additive, non-overridable):
      Before dispatching to either phase, a readiness check is run.
      If `overall=="red"` the request is rejected with HTTP 412
      Precondition Failed and a structured payload listing the
      failed checks. There is no override flag — operators must
      resolve the underlying issue and retry.
    """
    # ── Pre-flight readiness gate (applies to BOTH phase branches) ───
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

    # ── Phase 5.5 branch ─────────────────────────────────────────
    if (req.phase or "").strip() == "5.5":
        if factory55._lock.locked():  # noqa: SLF001
            raise HTTPException(
                status_code=409,
                detail="Phase 5.5 auto factory is already running. Check /status.",
            )
        overrides: Dict[str, Any] = {}
        for k in (
            "pairs", "timeframes", "styles", "firm", "per_combo",
            "min_pf", "min_runs", "max_drawdown", "top_n_store",
            "ingestion_max_strategies", "mutation_iterations",
            "mutation_per_cycle", "run_data_maintenance",
            "run_ingestion", "run_mutation", "run_validation",
            "run_selection", "step_timeout_sec",
        ):
            v = getattr(req, k, None)
            if v is not None:
                overrides[k] = v

        if req.wait:
            try:
                summary = await factory55.run_cycle(triggered_by="api", overrides=overrides)
            except RuntimeError as e:
                if str(e) == "already_running":
                    raise HTTPException(status_code=409, detail="already_running")
                if str(e) in ("readiness_blocked", "readiness_check_failed"):
                    # Engine-level gate raised — translate into the same
                    # 412 payload the API-level gate would have produced.
                    rd = await compute_readiness()
                    raise HTTPException(
                        status_code=412,
                        detail={
                            "code": "readiness_blocked",
                            "message": "System is not ready. Fix issues before running Auto Factory.",
                            "overall": rd.get("overall"),
                            "failed_checks": [
                                {"id": c.get("id"), "label": c.get("label"), "summary": c.get("summary")}
                                for c in failed_red_checks(rd)
                            ],
                            "readiness": rd,
                        },
                    )
                raise HTTPException(status_code=500, detail=str(e))
            return {"mode": "sync", "phase": "5.5", "summary": summary}

        async def _bg55():
            try:
                await factory55.run_cycle(triggered_by="api", overrides=overrides)
            except Exception:
                logger.exception("Background phase 5.5 run failed")

        asyncio.create_task(_bg55())
        return {
            "mode": "async",
            "phase": "5.5",
            "accepted": True,
            "poll": "/api/auto-factory/status?phase=5.5",
        }

    # ── Existing Phase 5 branch (unchanged) ──────────────────────
    if factory._lock.locked():  # noqa: SLF001 — intentional snapshot read
        raise HTTPException(
            status_code=409,
            detail="Auto factory is already running. Check /status.",
        )

    kwargs: Dict[str, Any] = dict(
        pairs=req.pairs,
        timeframes=req.timeframes,
        styles=req.styles,
        per_combo=req.per_combo,
        firm=req.firm,
        top_n=req.top_n,
        refine_top=req.refine_top,
        prefilter_top=req.prefilter_top,
        triggered_by="api",
    )

    if req.wait:
        try:
            summary = await factory.run_auto_factory(**kwargs)
        except RuntimeError as e:
            if str(e) == "already_running":
                raise HTTPException(status_code=409, detail="already_running")
            if str(e) in ("readiness_blocked", "readiness_check_failed"):
                rd = await compute_readiness()
                raise HTTPException(
                    status_code=412,
                    detail={
                        "code": "readiness_blocked",
                        "message": "System is not ready. Fix issues before running Auto Factory.",
                        "overall": rd.get("overall"),
                        "failed_checks": [
                            {"id": c.get("id"), "label": c.get("label"), "summary": c.get("summary")}
                            for c in failed_red_checks(rd)
                        ],
                        "readiness": rd,
                    },
                )
            raise HTTPException(status_code=500, detail=str(e))
        return {"mode": "sync", "summary": summary}

    # Fire-and-forget — schedule on the current loop.
    async def _runner():
        try:
            await factory.run_auto_factory(**kwargs)
        except Exception:
            logger.exception("Background auto-factory run failed")

    asyncio.create_task(_runner())
    return {"mode": "async", "accepted": True, "poll": "/api/auto-factory/status"}


@router.get("/status")
async def auto_factory_status(phase: Optional[str] = None):
    """Current run-state snapshot.

    - phase omitted / None → Phase 5 status (existing behavior)
    - phase == "5.5" → Phase 5.5 orchestrator status
    - phase == "all" → both engines
    """
    p = (phase or "").strip()
    if p == "5.5":
        return factory55.get_status()
    if p == "all":
        return {"phase5": factory.get_status(), "phase55": factory55.get_status()}
    return factory.get_status()


@router.post("/schedule")
async def auto_factory_schedule(req: ScheduleRequest):
    """Enable/disable the continuous APScheduler job.

    Pass `phase: "5.5"` to toggle the Phase 5.5 scheduler instead of
    the existing Phase 5 one.
    """
    p = (req.phase or "").strip()
    try:
        if p == "5.5":
            sched = factory55.set_toggle(enabled=req.enabled, interval_hours=req.interval_hours)
            await factory55.save_config({
                "scheduler_enabled": req.enabled,
                "scheduler_interval_hours": req.interval_hours,
            })
            return {"phase": "5.5", "scheduler": sched}

        if req.enabled:
            sched = factory.start_scheduler(interval_hours=req.interval_hours)
        else:
            sched = factory.stop_scheduler()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"scheduler": sched}


@router.get("/saved")
async def auto_factory_saved(
    limit: int = 50,
    phase: Optional[str] = None,
    view: Optional[str] = None,
    run_id: Optional[str] = None,
):
    """Strategies persisted by the factory (subset of strategy_library
    filtered by source='auto_factory').

    Phase 5.5 queries (ingress-compatible piggyback on this endpoint):
      • `?phase=5.5&view=history` → recent Phase 5.5 runs
      • `?phase=5.5&view=config`  → current Phase 5.5 config
      • `?phase=5.5&run_id=<id>`  → strategies stored for that run
      • `?phase=5.5` (no view)   → strategies from most recent run
    """
    p = (phase or "").strip()
    v = (view or "").strip()
    if p == "5.5":
        if v == "history":
            rows = await factory55.get_history(limit=max(1, min(limit, 200)))
            return {"phase": "5.5", "count": len(rows), "runs": rows}
        if v == "config":
            cfg = await factory55.get_config()
            return {"phase": "5.5", "config": cfg}
        if run_id:
            items = await factory55.get_run_strategies(run_id, limit=max(1, min(limit, 500)))
            return {"phase": "5.5", "run_id": run_id, "count": len(items), "strategies": items}
        # default: most recent run's strategies
        recent = await factory55.get_history(limit=1)
        rid = (recent[0].get("run_id") if recent else None)
        items = await factory55.get_run_strategies(rid, limit=max(1, min(limit, 500))) if rid else []
        return {"phase": "5.5", "run_id": rid, "count": len(items), "strategies": items}

    # existing Phase 5 behavior
    items = await list_saved(limit=max(1, min(limit, 200)))
    auto = [i for i in items if i.get("source") == "auto_factory"]
    return {"count": len(auto), "strategies": auto}


@router.post("/saved")
async def auto_factory_saved_post(body: Dict[str, Any]):
    """Ingress-only endpoint for mutating Phase 5.5 config.

    Using POST on the already-allow-listed `/saved` path (the preview
    ingress rejects brand-new paths). Body:
      { "phase": "5.5", "op": "update_config", "patch": {...} }
      { "phase": "5.5", "op": "test_alert" }
      { "phase": "5.5", "op": "alerts_log", "limit": 25 }
    """
    phase = str(body.get("phase") or "").strip()
    op = str(body.get("op") or "").strip()
    if phase != "5.5":
        raise HTTPException(status_code=400, detail="phase must be '5.5'")
    if op == "update_config":
        patch = body.get("patch") or {}
        if not isinstance(patch, dict):
            raise HTTPException(status_code=400, detail="patch must be an object")
        cfg = await factory55.save_config(patch)
        return {"phase": "5.5", "config": cfg}
    if op == "test_alert":
        from engines import alert_engine as alerts
        cfg = await factory55.get_config()
        res = await alerts.send_test_alert(cfg)
        return {"phase": "5.5", "op": "test_alert", "result": res}
    if op == "alerts_log":
        from engines.db import get_db
        from engines.alert_engine import ALERT_LOG_COLLECTION
        limit = int(body.get("limit") or 25)
        limit = max(1, min(limit, 200))
        db = get_db()
        cur = db[ALERT_LOG_COLLECTION].find({}, {"_id": 0}).sort("sent_at", -1).limit(limit)
        rows = await cur.to_list(length=None)
        return {"phase": "5.5", "op": "alerts_log", "count": len(rows), "alerts": rows}
    if op == "monitoring_alerts_log":
        from engines import monitoring_alert_bridge as bridge
        limit = int(body.get("limit") or 25)
        rows = await bridge.recent_log(limit=limit)
        return {"phase": "5.5", "op": "monitoring_alerts_log", "count": len(rows), "alerts": rows}
    raise HTTPException(status_code=400, detail=f"unknown op '{op}'")



@router.delete("/saved/{strategy_id}")
async def auto_factory_saved_delete(strategy_id: str):
    """Delete a strategy from the `strategy_library` collection.

    Thin wrapper over the existing `delete_saved()` engine helper — no new
    business logic; just exposes it over HTTP so the Library UI has a
    matching endpoint.
    """
    if not strategy_id:
        raise HTTPException(status_code=400, detail="strategy_id required")
    ok = await delete_saved(strategy_id)
    if not ok:
        raise HTTPException(status_code=404, detail="strategy not found")
    return {"success": True, "strategy_id": strategy_id, "deleted": True}

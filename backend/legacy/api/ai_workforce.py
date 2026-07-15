"""v1.2.0-alpha2 — /api/ai-workforce/* endpoints (Phase A + Phase B).

Phase A endpoints (unchanged):
    GET  /ai-workforce/health          — per-provider CB + telemetry
    GET  /ai-workforce/recent          — recent LLM call ring buffer
    GET  /ai-workforce/scores          — provider quality (raw ledger)
    POST /ai-workforce/circuit/{p}/reset — admin manual reset

Phase B endpoints (Router + Scorer + Metrics):
    GET  /ai-workforce/router-config   — per-task provider chain
    GET  /ai-workforce/metrics         — router counters + recent
    POST /ai-workforce/route-test      — issue a single route-call
    GET  /ai-workforce/quality         — cached scored snapshot (rich)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth_utils import require_admin
from engines.ai_workforce import (
    effective_chain,
    get_breaker,
    get_telemetry,
    is_router_enabled,
    metrics_snapshot,
    route_call,
    router_config,
    score_snapshot,
)
from engines.db import get_db

router = APIRouter(prefix="/ai-workforce", tags=["ai-workforce"])


@router.get("/health")
async def health(window_s: int = Query(3600, ge=60, le=86400)):
    breaker = get_breaker().snapshot()
    tele = get_telemetry().snapshot(window_s=window_s)
    providers = {}
    for p in set(list(breaker.keys()) + list(tele.keys())):
        b = breaker.get(p, {})
        t = tele.get(p, {})
        providers[p] = {
            "state": b.get("state", "closed"),
            "window_size": b.get("window_size", 0),
            "error_rate": b.get("error_rate", 0.0),
            "last_success_ts": b.get("last_success_ts"),
            "last_error": b.get("last_error"),
            "last_error_ts": b.get("last_error_ts"),
            "model": t.get("model"),
            "calls": t.get("calls", 0),
            "ok": t.get("ok", 0),
            "fail": t.get("fail", 0),
            "latency_p50_ms": t.get("latency_p50_ms"),
            "latency_p95_ms": t.get("latency_p95_ms"),
            "tokens_prompt": t.get("tokens_prompt", 0),
            "tokens_completion": t.get("tokens_completion", 0),
            "cost_usd": t.get("cost_usd", 0.0),
        }
    return {"providers": providers, "window_s": window_s,
            "router_enabled": is_router_enabled()}


@router.get("/recent")
async def recent(limit: int = Query(50, ge=1, le=500)):
    return {"calls": get_telemetry().recent(limit=limit)}


@router.get("/scores")
async def scores():
    db = get_db()
    pipeline = [
        {"$match": {"provider": {"$ne": None}}},
        {"$group": {
            "_id": {"provider": "$provider", "stage": "$stage", "status": "$status"},
            "n": {"$sum": 1},
        }},
    ]
    out: dict = {}
    async for row in db["outcome_events"].aggregate(pipeline):
        prov = row["_id"]["provider"]
        stage = row["_id"]["stage"]
        status = row["_id"]["status"]
        rec = out.setdefault(prov, {})
        rec.setdefault(stage, {"pass": 0, "fail": 0, "partial": 0, "skipped": 0})
        rec[stage][status] = rec[stage].get(status, 0) + row["n"]
    scores_out = []
    for prov, per_stage in out.items():
        total_pass = sum(s.get("pass", 0) for s in per_stage.values())
        total = sum(sum(s.values()) for s in per_stage.values())
        scores_out.append({
            "provider": prov,
            "quality_score": (total_pass / total) if total else 0.0,
            "total_events": total,
            "per_stage": per_stage,
        })
    scores_out.sort(key=lambda x: x["quality_score"], reverse=True)
    return {"scores": scores_out}


@router.post("/circuit/{provider}/reset")
async def reset_circuit(provider: str, _u=Depends(require_admin)):
    get_breaker().reset(provider)
    return {"ok": True, "provider": provider, "state": "closed"}


# ── Phase B endpoints ────────────────────────────────────────────
@router.get("/router-config")
async def workforce_router_config():
    return router_config()


@router.get("/metrics")
async def workforce_metrics():
    """Router counters + recent decisions + effective per-task chain
    (after outcome-driven reordering)."""
    scores = await score_snapshot()
    quality = {row["provider"]: row["quality_score"]
               for row in scores.get("scores", [])}
    conf = router_config()
    effective = {t: effective_chain(t, quality) for t in conf["chains"].keys()}
    return {
        **metrics_snapshot(),
        "effective_chains": effective,
        "quality_scores": quality,
    }


@router.get("/quality")
async def workforce_quality():
    """Rich provider quality snapshot (cached, per-stage components)."""
    return await score_snapshot()


class RouteTestRequest(BaseModel):
    task: str = "generic"
    prompt: str
    system_message: str = ""
    prefer_provider: str | None = None


@router.post("/route-test")
async def workforce_route_test(req: RouteTestRequest, _u=Depends(require_admin)):
    """Issue a single call through the workforce router. Useful for
    admins verifying failover behaviour in production."""
    text, provider, model, attempts = await route_call(
        req.task, req.prompt,
        system_message=req.system_message,
        prefer_provider=req.prefer_provider,
    )
    return {
        "ok": text is not None,
        "provider_used": provider,
        "model_used": model,
        "attempts": attempts,
        "text_preview": (text or "")[:400],
        "router_enabled": is_router_enabled(),
    }

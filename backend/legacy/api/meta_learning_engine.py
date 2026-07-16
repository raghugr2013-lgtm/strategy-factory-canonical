"""v1.2.0-alpha2 Phase I9 — /api/meta-learning/* endpoints.

12 endpoints (read-only in OBSERVE mode). Approve/reject/revert
endpoints return 409 when META_LEARNING_MODE=observe|disabled.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from auth_utils import require_admin
from engines.meta_learning import (
    config as mlcfg, ledger,
)
from engines.meta_learning.applier import (
    ApplierGuardBlocked, apply_recommendation, revert_override,
)
from engines.meta_learning.engine import run_meta_learning_cycle
from engines.meta_learning.types import MetaMode, MetaRecStatus

router = APIRouter(prefix="/meta-learning", tags=["meta-learning-engine"])


def _observe_mode_block(mode: str) -> Optional[Dict[str, Any]]:
    """Return an HTTP-409 payload if apply is not permitted in current mode."""
    if not MetaMode.can_apply(mode):
        raise HTTPException(status_code=409, detail={
            "error": f"meta_learning is in {mode} mode; approval blocked",
            "mode": mode,
        })
    return None


# ── Read endpoints ────────────────────────────────────────
@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return {"config": mlcfg.config_snapshot()}


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    from datetime import datetime, timezone
    recs = await ledger.read_recommendations(limit=1)
    evals = await ledger.read_evaluations(limit=1)
    apps = await ledger.read_applications(limit=1)
    return {
        "mode": mlcfg.mode(),
        "last_evaluation_at": evals[0].computed_at if evals else None,
        "last_recommendation_at": recs[0].created_at if recs else None,
        "last_application_at": apps[0].applied_at if apps else None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/evaluations")
async def list_evaluations(
    surface: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_evaluations(
        surface=surface, target=target, limit=limit)
    return {"count": len(rows),
            "evaluations": [r.to_dict() for r in rows]}


@router.get("/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str) -> Dict[str, Any]:
    row = await ledger.read_evaluation(evaluation_id)
    if row is None:
        raise HTTPException(404, "evaluation not found")
    return {"evaluation": row.to_dict()}


@router.get("/recommendations")
async def list_recommendations(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    surface: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_recommendations(
        status=status, severity=severity, surface=surface, limit=limit)
    return {"count": len(rows),
            "recommendations": [r.to_dict() for r in rows]}


@router.get("/pending")
async def list_pending(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    rows = await ledger.read_pending_recommendations(limit=limit)
    return {"count": len(rows),
            "pending": [r.to_dict() for r in rows]}


@router.get("/recommendations/{recommendation_id}")
async def get_recommendation(recommendation_id: str) -> Dict[str, Any]:
    row = await ledger.read_recommendation(recommendation_id)
    if row is None:
        raise HTTPException(404, "recommendation not found")
    return {"recommendation": row.to_dict()}


@router.get("/applications")
async def list_applications(
    target: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_applications(target=target, limit=limit)
    return {"count": len(rows),
            "applications": [r.to_dict() for r in rows]}


@router.get("/overrides")
async def list_overrides(
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_overrides(limit=limit)
    return {"count": len(rows), "overrides": rows}


@router.get("/mode-history")
async def mode_history(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    rows = await ledger.read_mode_history(limit=limit)
    return {"count": len(rows), "history": rows}


# ── Write endpoints (all admin-gated) ─────────────────────
@router.post("/refresh", dependencies=[Depends(require_admin)])
async def refresh_now(force: bool = Query(False)) -> Dict[str, Any]:
    """Force a meta-learning cycle. Still writes nothing to
    overrides in OBSERVE/DISABLED — safe to call at any time."""
    summary = await run_meta_learning_cycle(force=force)
    return {"cycle": summary}


@router.post("/recommendations/{recommendation_id}/approve",
              dependencies=[Depends(require_admin)])
async def approve(recommendation_id: str,
                    applied_by: str = Query("operator")) -> Dict[str, Any]:
    """Approve → apply. Blocked with 409 in OBSERVE/DISABLED."""
    cur = mlcfg.mode()
    _observe_mode_block(cur)
    r = await ledger.read_recommendation(recommendation_id)
    if r is None:
        raise HTTPException(404, "recommendation not found")
    if r.status != MetaRecStatus.PENDING:
        raise HTTPException(400, f"recommendation status={r.status} not pending")
    try:
        app = await apply_recommendation(r, applied_by=applied_by)
        return {"applied": True,
                "application": app.to_dict() if app else None}
    except ApplierGuardBlocked as e:
        raise HTTPException(422, f"guardrail blocked: {str(e)}")


@router.post("/recommendations/{recommendation_id}/reject",
              dependencies=[Depends(require_admin)])
async def reject(recommendation_id: str,
                   reason: str = Query("operator_rejected")) -> Dict[str, Any]:
    """Reject a pending recommendation. Allowed in all modes."""
    r = await ledger.read_recommendation(recommendation_id)
    if r is None:
        raise HTTPException(404, "recommendation not found")
    ok = await ledger.update_recommendation_status(
        recommendation_id, MetaRecStatus.REJECTED, reason=reason)
    return {"rejected": bool(ok)}


@router.post("/overrides/{target}/revert",
              dependencies=[Depends(require_admin)])
async def revert(target: str,
                   reason: str = Query("operator_revert")) -> Dict[str, Any]:
    """Delete an override + journal the reversion. Allowed in all modes
    (revert is always safe — it restores original code behaviour)."""
    ok = await revert_override(target, reason=reason)
    if not ok:
        raise HTTPException(404, "override not found")
    return {"reverted": True, "target": target}

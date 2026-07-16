"""v1.2.0-alpha2 Phase J9 — /api/factory-eval/* endpoints (26 routes)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_utils import require_admin
from engines.factory_eval import config as fecfg, ledger
from engines.factory_eval.engine import (
    apply_recommendation, ApplierGuardBlocked,
    run_factory_evaluation_cycle, revert_override,
)
from engines.factory_eval.types import FEMode, FERecStatus

router = APIRouter(prefix="/factory-eval", tags=["factory-eval-engine"])


def _observe_block(mode: str) -> None:
    if not FEMode.can_apply(mode):
        raise HTTPException(409, {
            "error": f"factory_eval is in {mode} mode; approval blocked",
            "mode": mode,
        })


# ── Reads ─────────────────────────────────────────────────
@router.get("/config")
async def get_config() -> Dict[str, Any]:
    return {"config": fecfg.config_snapshot()}


@router.get("/status")
async def get_status() -> Dict[str, Any]:
    from datetime import datetime, timezone
    latest = await ledger.read_latest_report()
    recs = await ledger.read_recommendations(limit=1)
    apps = await ledger.read_applications(limit=1)
    return {
        "mode": fecfg.mode(),
        "last_report_id": latest.report_id if latest else None,
        "last_cycle_ts": latest.cycle_ts if latest else None,
        "last_recommendation_at": recs[0].created_at if recs else None,
        "last_application_at": apps[0].applied_at if apps else None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/reports")
async def list_reports(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    rows = await ledger.read_reports(limit=limit)
    return {"count": len(rows), "reports": [r.to_dict() for r in rows]}


@router.get("/reports/latest")
async def get_latest_report() -> Dict[str, Any]:
    r = await ledger.read_latest_report()
    if r is None:
        raise HTTPException(404, "no report yet — try /refresh")
    return {"report": r.to_dict()}


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> Dict[str, Any]:
    r = await ledger.read_report(report_id)
    if r is None:
        raise HTTPException(404, "report not found")
    return {"report": r.to_dict()}


@router.get("/kpis")
async def kpis() -> Dict[str, Any]:
    r = await ledger.read_latest_report()
    return {"kpis": r.kpis if r else {},
            "report_id": r.report_id if r else None}


@router.get("/insights")
async def list_insights(
    surface: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_insights(surface=surface, severity=severity, limit=limit)
    return {"count": len(rows), "insights": [r.to_dict() for r in rows]}


@router.get("/insights/{insight_id}")
async def get_insight(insight_id: str) -> Dict[str, Any]:
    r = await ledger.read_insight(insight_id)
    if r is None:
        raise HTTPException(404, "insight not found")
    return {"insight": r.to_dict()}


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
async def pending(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    rows = await ledger.read_pending_recommendations(limit=limit)
    return {"count": len(rows), "pending": [r.to_dict() for r in rows]}


@router.get("/recommendations/{recommendation_id}")
async def get_recommendation(recommendation_id: str) -> Dict[str, Any]:
    r = await ledger.read_recommendation(recommendation_id)
    if r is None:
        raise HTTPException(404, "recommendation not found")
    return {"recommendation": r.to_dict()}


@router.get("/applications")
async def list_applications(
    target: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    rows = await ledger.read_applications(target=target, limit=limit)
    return {"count": len(rows),
            "applications": [r.to_dict() for r in rows]}


@router.get("/overrides")
async def list_overrides(limit: int = Query(100, ge=1, le=1000)) -> Dict[str, Any]:
    rows = await ledger.read_overrides(limit=limit)
    return {"count": len(rows), "overrides": rows}


@router.get("/mode-history")
async def mode_history(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    rows = await ledger.read_mode_history(limit=limit)
    return {"count": len(rows), "history": rows}


# ── Convenience read-outs ─────────────────────────────────
@router.get("/providers/leaderboard")
async def providers_leaderboard() -> Dict[str, Any]:
    r = await ledger.read_latest_report()
    return {"providers": (r.provider_summary if r else {}),
            "report_id": r.report_id if r else None}


@router.get("/strategies/top-contributors")
async def top_contributors(limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
    rows = await ledger.read_insights(
        surface="strategy_contribution", limit=limit * 2)
    top = [r.to_dict() for r in rows
           if r.target.startswith("top:")][:limit]
    return {"count": len(top), "top": top}


@router.get("/strategies/pruning-candidates")
async def pruning_candidates(limit: int = Query(30, ge=1, le=200)) -> Dict[str, Any]:
    rows = await ledger.read_recommendations(
        surface="strategy_pruning", limit=limit)
    return {"count": len(rows), "candidates": [r.to_dict() for r in rows]}


@router.get("/portfolios/health-trends")
async def portfolio_health_trends() -> Dict[str, Any]:
    rows = await ledger.read_insights(surface="portfolio_health", limit=100)
    return {"count": len(rows), "trends": [r.to_dict() for r in rows]}


@router.get("/execution/path-rankings")
async def execution_path_rankings() -> Dict[str, Any]:
    rows = await ledger.read_insights(surface="execution_quality", limit=100)
    return {"count": len(rows), "paths": [r.to_dict() for r in rows]}


@router.get("/regimes/effectiveness")
async def regimes_effectiveness() -> Dict[str, Any]:
    rows = await ledger.read_insights(surface="regime_effectiveness", limit=20)
    return {"count": len(rows), "regimes": [r.to_dict() for r in rows]}


@router.get("/bottlenecks")
async def bottlenecks() -> Dict[str, Any]:
    rows = await ledger.read_insights(surface="bottleneck", limit=20)
    return {"count": len(rows), "bottlenecks": [r.to_dict() for r in rows]}


@router.get("/coverage-gaps")
async def coverage_gaps() -> Dict[str, Any]:
    rows = await ledger.read_insights(surface="coverage_gap", limit=20)
    return {"count": len(rows), "gaps": [r.to_dict() for r in rows]}


# ── Writes (all admin) ────────────────────────────────────
@router.post("/refresh", dependencies=[Depends(require_admin)])
async def refresh(force: bool = Query(False)) -> Dict[str, Any]:
    return {"cycle": await run_factory_evaluation_cycle(force=force)}


@router.post("/daily-report", dependencies=[Depends(require_admin)])
async def daily_report(force: bool = Query(True)) -> Dict[str, Any]:
    return {"cycle": await run_factory_evaluation_cycle(
        force=force, daily=True)}


@router.post("/recommendations/{recommendation_id}/approve",
              dependencies=[Depends(require_admin)])
async def approve(recommendation_id: str,
                    applied_by: str = Query("operator")) -> Dict[str, Any]:
    _observe_block(fecfg.mode())
    r = await ledger.read_recommendation(recommendation_id)
    if r is None:
        raise HTTPException(404, "recommendation not found")
    if r.status != FERecStatus.PENDING:
        raise HTTPException(400, f"status={r.status} not pending")
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
    r = await ledger.read_recommendation(recommendation_id)
    if r is None:
        raise HTTPException(404, "recommendation not found")
    ok = await ledger.update_recommendation_status(
        recommendation_id, FERecStatus.REJECTED, reason=reason)
    return {"rejected": bool(ok)}


@router.post("/overrides/{target}/revert",
              dependencies=[Depends(require_admin)])
async def revert(target: str,
                   reason: str = Query("operator_revert")) -> Dict[str, Any]:
    ok = await revert_override(target, reason=reason)
    if not ok:
        raise HTTPException(404, "override not found")
    return {"reverted": True, "target": target}

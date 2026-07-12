"""Phase 30 — Deployment Registry (read-only).

Surfaces ONLY strategies at lifecycle stage = "deployment_ready". These
are the strategies that have passed every gate: candidate, validated,
stable, prop_safe, elite, portfolio_worthy, deployment_ready (incl.
BI5 realism + cBot compilation). Authoritative source for cTrader
deployment eligibility.

Mounts:
    GET  /api/deployment/registry
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Query

from engines.db import get_db
from engines.survivor_registry import PHASE_VERSION, _deploy_score_of, _now_iso

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.get("/registry")
async def deployment_registry(
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    """Read-only. The authoritative cTrader-eligible universe."""
    db = get_db()
    docs: List[Dict[str, Any]] = []
    async for d in db["strategy_lifecycle"].find(
        {"current_stage": "deployment_ready"},
        {"_id": 0},
    ):
        docs.append(d)
    docs.sort(key=lambda x: (-_deploy_score_of(x), x.get("strategy_hash") or ""))
    docs = docs[: int(limit)]

    bi5_verified = sum(
        1 for d in docs
        if "BI5_FAIL" not in (d.get("flags") or [])
        and "BI5_DATA_MISSING" not in (d.get("flags") or [])
    )
    return {
        "deployment_ready": [
            {
                "strategy_hash":        d.get("strategy_hash"),
                "deploy_score":         _deploy_score_of(d) if _deploy_score_of(d) > float("-inf") else None,
                "stage_rank":           d.get("stage_rank"),
                "current_stage_since":  d.get("current_stage_since"),
                "flags":                d.get("flags") or [],
                "evidence":             d.get("evidence") or {},
            }
            for d in docs
        ],
        "count":              len(docs),
        "bi5_verified":       bi5_verified,
        "transpiler_version": "1.0.0",
        "phase":              PHASE_VERSION,
        "computed_at":        _now_iso(),
    }

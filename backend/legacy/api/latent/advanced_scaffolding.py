"""Latent read-only endpoints — Phase 2 advanced scaffolding.

* GET /api/latent/soak-stability           — recent samples + summary
* GET /api/latent/rotational-proposal      — what rotation WOULD propose
* GET /api/latent/agent-advisor            — prompt the future agent would see
* GET /api/latent/flag-overrides           — current override map (NON-AUTHORITY)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_utils import get_current_user
from engines import (
    agent_advisor,
    flag_overrides,
    rotational_orchestrator,
    soak_stability,
)

router = APIRouter()


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"invalid ISO-8601: {e}")


@router.get("/latent/soak-stability")
async def get_soak_stability(
    _user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(default=200, ge=1, le=2000),
    since: Optional[str] = Query(default=None),
    window_hours: int = Query(default=24, ge=1, le=168),
) -> Dict[str, Any]:
    samples = await soak_stability.list_samples(
        limit=limit, since=_parse_iso(since),
    )
    summary = await soak_stability.summary(window_hours=window_hours)
    return {
        "read_only":          True,
        "governance_authority": False,
        "operator_authority": "final",
        "enabled":            soak_stability.is_enabled(),
        "summary":            summary,
        "samples":            samples,
    }


@router.get("/latent/rotational-proposal")
async def get_rotational_proposal(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await rotational_orchestrator.propose_rotation()


@router.get("/latent/agent-advisor")
async def get_agent_advisor(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await agent_advisor.build_prompt()


@router.get("/latent/flag-overrides")
async def get_flag_overrides_public(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Read-only public view of the override map.

    The full admin surface (set/delete/history) is under /api/admin/flag/*.
    """
    rows = await flag_overrides.list_overrides()
    return {
        "read_only":          True,
        "governance_authority": False,
        "operator_authority": "final",
        "count":              len(rows),
        "overrides":          rows,
        "note": (
            "Engines do not yet consult this map at runtime. Listing it "
            "here is for observability and forensic correlation only."
        ),
    }

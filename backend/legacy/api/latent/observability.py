"""Observability endpoints (read-only) — institutional ecosystem surfaces.

All endpoints under `/api/latent/*` are auth-gated, observational, and
payload-stamped as non-authority:
  `read_only=true, governance_authority=false, operator_authority="final"`.

Endpoints
---------
GET /api/latent/orchestration-health   — scheduler + cooldown + cycle health
GET /api/latent/replay-allocation       — replay queue current vs prioritized
GET /api/latent/mutation-saturation     — throughput + variant exhaustion
GET /api/latent/ecosystem-allocation    — universe × env_priority × survivors
GET /api/latent/activation-journal      — append-only operator-event log
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_utils import get_current_user
from engines import activation_journal as _journal
from engines import ecosystem_observability as _eo

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
        raise HTTPException(
            status_code=400, detail=f"invalid ISO-8601 ({value!r}): {e}",
        )


@router.get("/latent/orchestration-health")
async def get_orchestration_health(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await _eo.orchestration_health()


@router.get("/latent/replay-allocation")
async def get_replay_allocation(
    _user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(default=20, ge=1, le=200),
) -> Dict[str, Any]:
    return await _eo.replay_allocation(limit=limit)


@router.get("/latent/mutation-saturation")
async def get_mutation_saturation(
    _user: Dict[str, Any] = Depends(get_current_user),
    window_hours: int = Query(default=24, ge=1, le=168),
) -> Dict[str, Any]:
    return await _eo.mutation_saturation(window_hours=window_hours)


@router.get("/latent/ecosystem-allocation")
async def get_ecosystem_allocation(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await _eo.ecosystem_allocation()


@router.get("/latent/activation-journal")
async def get_activation_journal(
    _user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(default=_journal.DEFAULT_LIMIT, ge=1,
                       le=_journal.MAX_LIMIT),
    since: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None, max_length=80),
    actor: Optional[str] = Query(default=None, max_length=120),
    include_snapshots: bool = Query(
        default=False,
        description=(
            "Include the bulky safe-to-widen + governance snapshots "
            "captured at write-time. Off by default to keep responses small."
        ),
    ),
) -> Dict[str, Any]:
    return await _journal.list_events(
        limit=limit,
        since=_parse_iso(since),
        event_type=event_type,
        actor=actor,
        include_snapshots=include_snapshots,
    )

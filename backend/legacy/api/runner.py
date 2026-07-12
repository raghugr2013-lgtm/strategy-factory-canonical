"""Master Bot V1 — Runner-facing API (MB-9 Phase 1).

Endpoints consumed by the Windows VPS runner agent. Authentication
is `X-Runner-Id` + `X-Runner-Token` header pair — **NOT** the JWT
used by operator UI. Tokens are minted at runner registration and
hashed-at-rest in `master_bot_runners`.

Routes (all `/api/runner/*`):
    POST /api/runner/heartbeat              — runner POSTs snapshot
    GET  /api/runner/poll                   — runner pulls queue
    POST /api/runner/ack                    — runner ACKs an action
    GET  /api/runner/artifact/{pack_id}     — runner downloads .cbotpack

Discipline:
    * Runner cannot create / promote / rollback. Only ACKs.
    * Pack download verifies pack belongs to a deployment ASSIGNED
      to this runner. No drive-by artifact fetches.
    * All errors return 401/403/404 — no internal trace leakage.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from fastapi.responses import Response
from pydantic import BaseModel, Field

from engines import runner_registry as runners
from engines import master_bot_deployment as mbdep
from engines import master_bot_pack as mbpack
# ── MB-9 Phase 2.C — consumer wiring of Phase 2.A engines into the
#    runner-facing API. Grace-window auth + multi-account fan-out.
#    Both gates default-OFF; flag-OFF byte-identical to Phase 1.
from engines import runner_token_rotator as rtr
from engines import multi_account_envelope as mae
from engines.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runner", tags=["runner"])


# ── Token dep ───────────────────────────────────────────────────────

async def _require_runner(
    x_runner_id:    Optional[str] = Header(None, alias="X-Runner-Id"),
    x_runner_token: Optional[str] = Header(None, alias="X-Runner-Token"),
) -> Dict[str, Any]:
    if not x_runner_id or not x_runner_token:
        raise HTTPException(
            status_code=401,
            detail="X-Runner-Id and X-Runner-Token headers required",
        )
    # Phase 1 fast path — single Mongo read, byte-identical to pre-2.C.
    row = await runners.validate_token(x_runner_id, x_runner_token)
    if row:
        return row
    # ── MB-9 Phase 2.C — grace-window fallback.
    #
    # If the legacy active-token check refused but the runner has an
    # active rotation, the *pending* token is also valid during the
    # configured grace window. validate_with_grace() returns False
    # under every Phase 1 scenario (no rotation row → no pending
    # token), so this code path is invisible to Phase 1 deployments.
    accepted = await rtr.validate_with_grace(x_runner_id, x_runner_token)
    if accepted:
        # Fetch the runner row (without exposing token_hash material).
        full = await runners.get_runner_status(x_runner_id)
        if full and full.get("status") != "disabled":
            return full
    raise HTTPException(status_code=401, detail="invalid runner credentials")


# ── Request models ──────────────────────────────────────────────────

class HeartbeatBody(BaseModel):
    """Mirrors `compute_probe.snapshot()` plus optional runner-side
    fields (active deployments, cTrader Desktop status)."""
    cpu_count:        Optional[int]   = None
    cpu_percent:      Optional[float] = None
    load_avg:         Optional[List[float]] = None
    mem_total_gb:     Optional[float] = None
    mem_available_gb: Optional[float] = None
    mem_percent:      Optional[float] = None
    open_fds:         Optional[int]   = None
    process_rss_mb:   Optional[float] = None
    active_deployments: Optional[List[str]] = None
    ctrader_desktop_state: Optional[str] = Field(
        None, description="running | stopped | unknown",
    )
    runner_agent_version: Optional[str] = None


class AckBody(BaseModel):
    deployment_id:    str   = Field(..., min_length=8, max_length=64)
    state:            str   = Field(..., description="staged | live | crashed | refused")
    sha256_verified:  bool  = False
    message:          Optional[str] = None


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatBody,
    runner: Dict[str, Any] = Depends(_require_runner),
) -> Dict[str, Any]:
    snapshot = body.model_dump(exclude_none=True)
    return await runners.record_heartbeat(
        runner.get("runner_id"), snapshot=snapshot,
    )


@router.get("/poll")
async def poll(
    runner: Dict[str, Any] = Depends(_require_runner),
) -> Dict[str, Any]:
    queue = await mbdep.runner_poll_queue(runner.get("runner_id"))
    assignments: List[Dict[str, Any]] = [
        {
            "deployment_id":  q.get("deployment_id"),
            "master_bot_id":  q.get("master_bot_id"),
            "pack_id":        q.get("pack_id"),
            "filename":       q.get("filename"),
            "sha256":         q.get("sha256"),
            "size_bytes":     q.get("size_bytes"),
            "state":          q.get("state"),
            "rev":            q.get("rev"),
            "promoted_at":    q.get("promoted_at"),
        }
        for q in queue
    ]
    # ── MB-9 Phase 2.C — multi-account fan-out.
    #
    # When RUNNER_MULTI_ACCOUNT_ENABLED=True, surface the runner's
    # account envelopes to the agent so it can fan out the trade
    # across every account. Flag-OFF (default): the response is
    # byte-identical to Phase 1 — NO ``accounts`` field added.
    response: Dict[str, Any] = {
        "runner_id":   runner.get("runner_id"),
        "queue_size":  len(assignments),
        "assignments": assignments,
    }
    if mae._flag_enabled():
        try:
            accounts = await mae.list_accounts(runner.get("runner_id"))
        except Exception:                                       # pragma: no cover
            logger.exception("multi-account fan-out failed; returning legacy shape")
            accounts = []
        # Surface only the fields the runner agent needs — strip
        # operational metadata (created_by, notes, _synthesized).
        response["accounts"] = [
            {
                "account_id":                a.get("account_id"),
                "broker":                    a.get("broker"),
                "credentials_envelope_hash": a.get("credentials_envelope_hash"),
                "active":                    a.get("active", True),
            }
            for a in accounts
            if a.get("active", True)
        ]
    return response


@router.post("/ack")
async def ack(
    body: AckBody,
    runner: Dict[str, Any] = Depends(_require_runner),
) -> Dict[str, Any]:
    try:
        return await mbdep.record_runner_ack(
            body.deployment_id,
            runner_id=runner.get("runner_id"),
            state=body.state,
            sha256_verified=body.sha256_verified,
            message=body.message,
        )
    except mbdep.DeploymentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/artifact/{pack_id}")
async def artifact(
    pack_id: str = Path(..., min_length=8, max_length=64),
    runner: Dict[str, Any] = Depends(_require_runner),
):
    """Download the `.cbotpack` bytes. Authorised only if the pack is
    referenced by a deployment whose `runner_id == this runner`."""
    db = get_db()
    dep = await db[mbdep.DEPLOYMENTS_COLL].find_one(
        {"pack_id": pack_id, "runner_id": runner.get("runner_id")},
        {"_id": 0, "deployment_id": 1},
    )
    if not dep:
        raise HTTPException(
            status_code=404,
            detail="pack not assigned to this runner",
        )
    try:
        filename, blob = await mbpack.read_pack(pack_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

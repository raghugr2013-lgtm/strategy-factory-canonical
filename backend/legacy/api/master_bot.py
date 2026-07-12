"""Master Bot V1 — API router (MB-1 + MB-2 + MB-3).

Mounted at `/api/master-bot/*`. Auth model matches the rest of the
platform (`AuthMiddleware`): bearer JWT required; mutations require
admin role via `require_admin`.

Routes:
    GET    /api/master-bot                        — list bots
    POST   /api/master-bot                        — create (admin)
    GET    /api/master-bot/candidates             — Candidate Pool top-N
    GET    /api/master-bot/candidates/refresh     — recompute (admin)
    GET    /api/master-bot/ranker/config          — ranker weights
    POST   /api/master-bot/ranker/config          — update weights (admin)
    GET    /api/master-bot/{id}                   — read one bot
    PUT    /api/master-bot/{id}                   — rename / describe (admin)
    DELETE /api/master-bot/{id}                   — soft delete (admin)
    POST   /api/master-bot/{id}/members           — add strategy (admin)
    DELETE /api/master-bot/{id}/members/{hash}    — remove (admin)
    POST   /api/master-bot/{id}/members/{hash}/enable    (admin)
    POST   /api/master-bot/{id}/members/{hash}/disable   (admin)
    POST   /api/master-bot/{id}/members/{hash}/promote   (admin)
    POST   /api/master-bot/{id}/members/{hash}/demote    (admin)
    POST   /api/master-bot/{id}/members/{hash}/move-to   (admin)
    POST   /api/master-bot/{id}/tiers/{tier}/reorder     (admin)
    POST   /api/master-bot/{id}/tiers/{tier}             (admin)
    POST   /api/master-bot/{id}/auto-fill                (admin)

Auto-fill ingests the top N from the Candidate Pool and slots them into
tiers 1/2/3 based on configurable per-tier capacity caps + rank order.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import get_current_user, require_admin
from engines import master_bot_engine as mbe
from engines import master_bot_ranker as ranker
from engines import master_bot_definition as mbd
from engines import master_bot_export as mbx
from engines import master_bot_pack as mbpack
from engines import master_bot_diff as mbdiff
from engines import strategy_ir_backfill as mb_ir_backfill
from engines import runner_registry as runners
from engines import master_bot_deployment as mbdep
# ── MB-9 Phase 2.B — Multi-runner routing + token rotation + drift
#    dashboard + multi-account fan-out. Engines are present from
#    Phase 2.A; routes are wired in here (additive, admin-gated).
from engines import runner_router as rr
from engines import runner_token_rotator as rtr
from engines import parity_drift_view as pdv
from engines import multi_account_envelope as mae
from engines import runner_account_migration as rmig
# MB-9 Phase 2.D — operator visibility for the auto-route gate.
from engines import feature_flags as _ff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/master-bot", tags=["master-bot"])


# ── Pydantic request bodies ─────────────────────────────────────────

class CreateMasterBotRequest(BaseModel):
    name:        str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None


class RenameMasterBotRequest(BaseModel):
    name:        Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None


class AddMemberRequest(BaseModel):
    strategy_hash: str = Field(..., min_length=8, max_length=128)
    tier:          str = Field("tier3")
    weight:        Optional[float] = None
    notes:         Optional[str] = None
    snapshot:      Optional[Dict[str, Any]] = None


class MoveToTierRequest(BaseModel):
    tier: str = Field(..., min_length=1, max_length=16)


class ReorderTierRequest(BaseModel):
    ordered_hashes: List[str] = Field(default_factory=list)


class UpdateTierRequest(BaseModel):
    label:            Optional[str] = None
    allocation_share: Optional[float] = None
    max_members:      Optional[int] = None


class RankerWeightsRequest(BaseModel):
    deploy_score:     Optional[float] = None
    pass_probability: Optional[float] = None
    risk_of_ruin:     Optional[float] = None
    calibration:      Optional[float] = None
    regime_fitness:   Optional[float] = None


class AutoFillRequest(BaseModel):
    tier1_count: int = Field(3,  ge=0, le=20)
    tier2_count: int = Field(7,  ge=0, le=30)
    tier3_count: int = Field(15, ge=0, le=50)
    clear_existing: bool = False


class CompileRequest(BaseModel):
    runtime_mode:   Optional[str] = Field(None, description="single_active | multi_strategy | regime_aware")
    runtime_policy: Optional[Dict[str, Any]] = None


class ExportRequest(BaseModel):
    revision_id:         Optional[str] = None
    compile_if_missing:  bool = True
    force_parity:        bool = False           # MB-10 admin bypass


class PackRequest(BaseModel):
    export_id:   Optional[str] = None
    revision_id: Optional[str] = None


# ── MB-9 Phase 1: deployment + runner request bodies ────────────────

class RegisterRunnerRequest(BaseModel):
    name:              str  = Field(..., min_length=1, max_length=120)
    hostname:          Optional[str] = None
    platform:          str  = Field("windows", description="windows | linux")
    pair_filters:      Optional[List[str]] = None
    timeframe_filters: Optional[List[str]] = None
    notes:             Optional[str] = None


class RegisterDeploymentRequest(BaseModel):
    pack_id:    str  = Field(..., min_length=8, max_length=64)
    runner_id:  Optional[str] = Field(None, min_length=8, max_length=64)


# ── MB-9 Phase 2.B: account-envelope request body ──────────────────

class AddRunnerAccountRequest(BaseModel):
    account_id:           str  = Field(..., min_length=1, max_length=120)
    broker:               Optional[str] = Field("ctrader", max_length=64)
    credentials_envelope: Optional[str] = Field(
        None,
        description=(
            "Raw envelope material — hashed sha256:hex before persist; "
            "never stored verbatim."
        ),
    )
    notes:                Optional[str] = Field("", max_length=500)


# ── Convenience helpers ─────────────────────────────────────────────

def _err400(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)


def _err404(msg: str = "not found") -> HTTPException:
    return HTTPException(status_code=404, detail=msg)


# ── Read endpoints (any authed user) ───────────────────────────────

@router.get("")
async def list_master_bots(
    owner:  Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    limit:  int  = Query(100, ge=1, le=500),
    user:   Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await mbe.list_master_bots(
        owner=owner, include_deleted=include_deleted, limit=limit,
    )
    return {"count": len(rows), "master_bots": rows}


@router.get("/candidates")
async def candidates(
    limit: int = Query(30, ge=1, le=100),
    user:  Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await ranker.fetch_candidate_pool(limit=limit)


@router.post("/candidates/refresh")
async def refresh_candidates(
    limit: int = Query(30, ge=1, le=100),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Force a fresh computation (no DB-level caching in V1; this is
    a no-op alias of GET /candidates today, kept for forward-compat
    when MB-2 introduces a persisted pool snapshot)."""
    return await ranker.fetch_candidate_pool(limit=limit)


@router.get("/ranker/config")
async def ranker_config(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await ranker.get_weights()


@router.post("/ranker/config")
async def update_ranker_config(
    req: RankerWeightsRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await ranker.set_weights(
            {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None},
            admin_email=admin.get("email") or "admin",
        )
    except ValueError as e:
        raise _err400(str(e))


# ─────────────────────────────────────────────────────────────────
# MB-9 Phase 1 — Runner registry + deployment control plane.
# Declared BEFORE /{master_bot_id} so literal segments ("runners",
# "deployments") are matched without being shadowed by the
# parametric master_bot_id route.
# ─────────────────────────────────────────────────────────────────

def _deploy_err(e: "mbdep.DeploymentError") -> HTTPException:
    """Map DeploymentError → HTTP. ParitySignoffExpired → 409 to
    match the MB-10 parity-blocked pattern; other errors → 400."""
    if isinstance(e, mbdep.ParitySignoffExpired):
        return HTTPException(status_code=409, detail={
            "error":   "parity_signoff_expired",
            "message": str(e),
            "remedy":  "re-issue parity sign-off for stale members, then retry",
        })
    return HTTPException(status_code=400, detail=str(e))


@router.post("/runners")
async def register_runner_endpoint(
    req: RegisterRunnerRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Register a new Windows VPS runner. Returns the auth token
    ONCE — store it immediately on the runner agent."""
    try:
        return await runners.register_runner(
            name=req.name,
            hostname=req.hostname,
            platform=req.platform,
            pair_filters=req.pair_filters or [],
            timeframe_filters=req.timeframe_filters or [],
            notes=req.notes,
            actor=admin.get("email") or "admin",
        )
    except ValueError as e:
        raise _err400(str(e))


@router.get("/runners")
async def list_runners_endpoint(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await runners.list_runners()
    return {"count": len(rows), "runners": rows}


# ─────────────────────────────────────────────────────────────────
# MB-9 Phase 2.B — literal-segment routes under /runners
#
# These declarations MUST live BEFORE @router.get("/runners/{runner_id}")
# so FastAPI matches the literal segments ("route-preview", "fleet",
# "accounts") without falling into the parametric runner-id route.
# ─────────────────────────────────────────────────────────────────

@router.get("/runners/route-preview")
async def runners_route_preview(
    pair:      str = Query(..., min_length=1, max_length=32),
    timeframe: str = Query(..., min_length=1, max_length=16),
    policy:    Optional[str] = Query(
        None,
        description=(
            "Override RUNNER_AFFINITY_POLICY for this preview only. "
            "Valid: sticky_pair_tf / least_busy / round_robin / "
            "local_only. Unknown values fall back to the default."
        ),
    ),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Preview the router's decision for a (pair, timeframe) workload.

    Read-only — neither mutates Mongo nor advances the round-robin
    cursor at module level beyond what a normal route call would do.
    Admin-gated to match the operator-final-authority invariant on
    routing-policy diagnostics.
    """
    decision = await rr.route(pair, timeframe, policy=policy)
    return {
        "pair":           pair.strip().upper(),
        "timeframe":      timeframe.strip().upper(),
        "policy_override": policy,
        "decision":       decision,
    }


@router.get("/runners/fleet")
async def runners_fleet(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Fleet snapshot: per-runner verdict / heartbeat / queue depth
    + active routing policy + account row counts.

    Admin-gated because the snapshot includes operational state that
    surfaces only to operators per AR §2.2.
    """
    fleet = await runners.list_runners()
    enriched: List[Dict[str, Any]] = []
    for row in fleet:
        rid = row.get("runner_id")
        snap = dict(row)
        if rid:
            try:
                snap["account_count"] = await mae.count_accounts(rid)
            except Exception:                                       # pragma: no cover
                snap["account_count"] = None
            try:
                state = await rtr.get_rotation_state(rid)
                snap["token_rotation_state"]      = state.get("token_rotation_state")
                snap["rotation_grace_expires_at"] = state.get("rotation_grace_expires_at")
                snap["grace_window_active"]      = state.get("grace_window_active")
            except rtr.TokenRotationError:
                snap["token_rotation_state"] = None
        enriched.append(snap)
    return {
        "count":                    len(enriched),
        "active_policy":            rr._resolved_policy(),
        "valid_policies":           list(rr.VALID_POLICIES),
        "multi_account_enabled":    mae._flag_enabled(),
        # MB-9 Phase 2.D — operator visibility for the auto-route gate
        # already consumed by master_bot_deployment.register_deployment.
        # Read-only echo; no behaviour change.
        "auto_route_at_register_enabled": bool(
            _ff.flag("RUNNER_AUTO_ROUTE_AT_REGISTER")
        ),
        "runners":                  enriched,
    }


# ── MB-9 Phase 2.B — admin: legacy-account migration helper ───────

@router.post("/runners/accounts/migrate-legacy")
async def runners_accounts_migrate_legacy(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Idempotent one-shot — create one legacy `runner_accounts` row
    for every active runner that lacks one. Safe to re-run any time."""
    return await rmig.bootstrap_legacy_accounts(
        actor=admin.get("email") or "admin",
    )


@router.get("/runners/accounts/migration-status")
async def runners_accounts_migration_status(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Read-only progress snapshot of the legacy bootstrap."""
    return await rmig.migration_status()


@router.get("/runners/{runner_id}")
async def get_runner_endpoint(
    runner_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    r = await runners.get_runner_status(runner_id)
    if not r:
        raise _err404("runner not found")
    return r


@router.post("/runners/{runner_id}/disable")
async def disable_runner_endpoint(
    runner_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await runners.disable_runner(
            runner_id, actor=admin.get("email") or "admin",
        )
    except ValueError as e:
        raise _err404(str(e))


# ─────────────────────────────────────────────────────────────────
# MB-9 Phase 2.B — token-rotation + multi-account routes
# (parametric, declared AFTER the literal-segment Phase 2.B block)
# ─────────────────────────────────────────────────────────────────

@router.post("/runners/{runner_id}/rotate-token")
async def runner_rotate_token(
    runner_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Mint a new token for the runner. The OLD token continues to
    authenticate for ``RUNNER_TOKEN_GRACE_SEC`` (default 300s). The
    raw ``new_token`` is shown ONLY in this response."""
    try:
        return await rtr.start_rotation(
            runner_id, actor=admin.get("email") or "admin",
        )
    except rtr.TokenRotationError as e:
        # 409 conflict for double-start / disabled / missing runner.
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/runners/{runner_id}/rotate-token/expire-old")
async def runner_rotate_token_expire_old(
    runner_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Promote the pending token to be the only valid one (ends the
    grace window early). Refuses when no rotation is active."""
    try:
        return await rtr.expire_old(
            runner_id, actor=admin.get("email") or "admin",
        )
    except rtr.TokenRotationError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/runners/{runner_id}/rotate-token")
async def runner_rotate_token_state(
    runner_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Inspector — read-only rotation-state snapshot."""
    try:
        return await rtr.get_rotation_state(runner_id)
    except rtr.TokenRotationError as e:
        raise _err404(str(e))


# ── MB-9 Phase 2.B — multi-account fan-out endpoints ──────────────

@router.get("/runners/{runner_id}/accounts")
async def list_runner_accounts(
    runner_id: str,
    raw: bool = Query(
        False,
        description=(
            "When true (admin-only diagnostic), bypass the "
            "RUNNER_MULTI_ACCOUNT_ENABLED flag-OFF synthesized "
            "legacy row and return the raw collection contents."
        ),
    ),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """List all accounts for a runner.

    With ``raw=true`` the flag-OFF synthetic legacy row is bypassed
    and the operator sees the collection's actual contents. Default
    (``raw=false``) preserves the Phase 1 byte-identical behaviour
    when ``RUNNER_MULTI_ACCOUNT_ENABLED=false``.
    """
    if raw:
        db = mae.get_db()
        rows = [
            r async for r in db[mae.ACCOUNTS_COLL].find(
                {"runner_id": runner_id}, {"_id": 0},
            )
        ]
    else:
        rows = await mae.list_accounts(runner_id)
    return {
        "runner_id":             runner_id,
        "count":                 len(rows),
        "multi_account_enabled": mae._flag_enabled(),
        "raw":                   bool(raw),
        "accounts":              rows,
    }


@router.post("/runners/{runner_id}/accounts")
async def add_runner_account(
    runner_id: str,
    req: AddRunnerAccountRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Attach a new account envelope to the runner. The raw envelope
    is sha256-hashed before persist; only the hash is stored."""
    try:
        return await mae.add_account(
            runner_id=runner_id,
            account_id=req.account_id,
            broker=req.broker or "ctrader",
            credentials_envelope=req.credentials_envelope,
            notes=req.notes or "",
            actor=admin.get("email") or "admin",
        )
    except mae.MultiAccountError as e:
        # 409 for duplicate / disabled-runner; 404 for missing.
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        if "already exists" in msg or "disabled" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise _err400(msg)


@router.delete("/runners/{runner_id}/accounts/{account_id}")
async def remove_runner_account(
    runner_id: str,
    account_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Hard-delete one account envelope. Refuses if not found."""
    try:
        return await mae.remove_account(
            runner_id=runner_id, account_id=account_id,
            actor=admin.get("email") or "admin",
        )
    except mae.MultiAccountError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.post("/deployments/{deployment_id}/stage")
async def deploy_stage(
    deployment_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbdep.stage_deployment(
            deployment_id, actor=admin.get("email") or "admin",
        )
    except mbdep.DeploymentError as e:
        raise _deploy_err(e)


@router.post("/deployments/{deployment_id}/promote")
async def deploy_promote(
    deployment_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbdep.promote_to_live(
            deployment_id, actor=admin.get("email") or "admin",
        )
    except mbdep.DeploymentError as e:
        raise _deploy_err(e)


# ─────────────────────────────────────────────────────────────────
# MB-9 Phase 2.B — parity-drift dashboard endpoints
#
# Declared BEFORE @router.get("/deployments/{deployment_id}") so the
# literal "parity-drift" segment matches without being shadowed by
# the parametric deployment-id route. Read-only — any authed user.
# ─────────────────────────────────────────────────────────────────

@router.get("/deployments/parity-drift")
async def deployments_parity_drift_all(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Drift verdict across every `live` deployment. Honest-refusal
    semantics — deployments with < 2 sign-offs in the window return
    decision=insufficient_data and never block."""
    return await pdv.compute_drift_for_all_live()


@router.get("/deployments/parity-drift/{deployment_id}")
async def deployments_parity_drift_one(
    deployment_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Drift verdict for one deployment_id."""
    return await pdv.compute_drift_for_deployment(deployment_id)


@router.post("/deployments/parity-drift/scan-and-alert")
async def deployments_parity_drift_scan_and_alert(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """MB-9 Phase 2.C — operator-triggered drift surveillance sweep.

    Computes drift across every ``live`` deployment and, for each
    deployment whose verdict is non-OK, emits one institutional
    event of type ``PARITY_DRIFT_DETECTED`` via the existing
    alert_engine pipeline (audit-log → dedupe → webhook fan-out).

    Operator-triggered ONLY — never runs on a schedule. The
    flag-OFF byte-identical guarantee is preserved by *not invoking
    this endpoint*. When invoked it never raises: a per-deployment
    failure is captured under ``errors`` and the sweep continues.
    """
    from engines import alert_engine as ae
    rollup = await pdv.compute_drift_for_all_live()
    emitted:    List[Dict[str, Any]] = []
    skipped_ok: List[str] = []
    errors:     List[Dict[str, Any]] = []
    deployments = rollup.get("deployments") or []
    for d in deployments:
        verdict = d.get("decision") or d.get("verdict")
        # Honest-refusal verdicts are NOT drift — skip silently.
        if verdict in (None, "ok", "passed", "insufficient_data",
                       "no_signoffs", "not_found",
                       "deployment_not_found"):
            skipped_ok.append(d.get("deployment_id") or "")
            continue
        try:
            payload = {
                "deployment_id": d.get("deployment_id"),
                "master_bot_id": d.get("master_bot_id"),
                "verdict":       verdict,
                "window_days":   rollup.get("window_days"),
                "metrics":       d.get("metrics") or {},
                "scanned_by":    admin.get("email") or "admin",
            }
            await ae.emit_event(
                event_type="PARITY_DRIFT_DETECTED",
                payload=payload,
                run_id=f"drift_scan::{d.get('deployment_id')}",
            )
            emitted.append({
                "deployment_id": d.get("deployment_id"),
                "verdict":       verdict,
            })
        except Exception as exc:                            # pragma: no cover
            errors.append({
                "deployment_id": d.get("deployment_id"),
                "error":         str(exc),
            })
    return {
        "scanned":        len(deployments),
        "emitted":        emitted,
        "skipped_ok":     skipped_ok,
        "errors":         errors,
        "window_days":    rollup.get("window_days"),
    }


@router.get("/deployments/{deployment_id}")
async def deploy_get(
    deployment_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    row = await mbdep.get_deployment(deployment_id)
    if not row:
        raise _err404("deployment not found")
    return row


@router.get("/{master_bot_id}")
async def get_master_bot(
    master_bot_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    doc = await mbe.get_master_bot(master_bot_id)
    if not doc:
        raise _err404("master bot not found")
    return doc


# ── Master Bot mutations (admin) ───────────────────────────────────

@router.post("")
async def create_master_bot(
    req: CreateMasterBotRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.create_master_bot(
            name=req.name,
            owner=admin.get("email") or "admin",
            description=req.description,
        )
    except ValueError as e:
        raise _err400(str(e))


@router.put("/{master_bot_id}")
async def rename_master_bot(
    master_bot_id: str,
    req: RenameMasterBotRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.rename_master_bot(
            master_bot_id,
            name=req.name,
            description=req.description,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.delete("/{master_bot_id}")
async def delete_master_bot(
    master_bot_id: str,
    hard: bool = Query(False),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.delete_master_bot(master_bot_id, hard=hard)
    except ValueError as e:
        raise _err404(str(e))


# ── Member endpoints (admin) ───────────────────────────────────────

@router.post("/{master_bot_id}/members")
async def add_member(
    master_bot_id: str,
    req: AddMemberRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.add_member(
            master_bot_id,
            strategy_hash=req.strategy_hash,
            tier=req.tier,
            weight=req.weight,
            notes=req.notes,
            snapshot=req.snapshot,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.delete("/{master_bot_id}/members/{strategy_hash}")
async def remove_member(
    master_bot_id: str, strategy_hash: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.remove_member(master_bot_id, strategy_hash)
    except ValueError as e:
        raise _err404(str(e))


@router.post("/{master_bot_id}/members/{strategy_hash}/enable")
async def enable_member(
    master_bot_id: str, strategy_hash: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.set_member_enabled(master_bot_id, strategy_hash, True)
    except ValueError as e:
        raise _err404(str(e))


@router.post("/{master_bot_id}/members/{strategy_hash}/disable")
async def disable_member(
    master_bot_id: str, strategy_hash: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.set_member_enabled(master_bot_id, strategy_hash, False)
    except ValueError as e:
        raise _err404(str(e))


@router.post("/{master_bot_id}/members/{strategy_hash}/promote")
async def promote_member(
    master_bot_id: str, strategy_hash: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.promote_member(master_bot_id, strategy_hash)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.post("/{master_bot_id}/members/{strategy_hash}/demote")
async def demote_member(
    master_bot_id: str, strategy_hash: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.demote_member(master_bot_id, strategy_hash)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.post("/{master_bot_id}/members/{strategy_hash}/move-to")
async def move_member_to_tier(
    master_bot_id: str, strategy_hash: str,
    req: MoveToTierRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.move_to_tier(master_bot_id, strategy_hash, req.tier)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.post("/{master_bot_id}/tiers/{tier}/reorder")
async def reorder_tier(
    master_bot_id: str, tier: str,
    req: ReorderTierRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        rows = await mbe.reorder_members(master_bot_id, tier, req.ordered_hashes)
        return {"tier": tier, "members": rows}
    except ValueError as e:
        raise _err400(str(e))


@router.post("/{master_bot_id}/tiers/{tier}")
async def update_tier(
    master_bot_id: str, tier: str,
    req: UpdateTierRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbe.set_tier_metadata(
            master_bot_id, tier,
            label=req.label,
            allocation_share=req.allocation_share,
            max_members=req.max_members,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.post("/{master_bot_id}/auto-fill")
async def auto_fill(
    master_bot_id: str,
    req: AutoFillRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Greedy fill from the Candidate Pool top-N.

    Order: tier1 takes first `tier1_count` candidates, tier2 next
    `tier2_count`, tier3 next `tier3_count`. Skips duplicates that are
    already members of this Master Bot. Optionally clears all existing
    members before filling.
    """
    parent = await mbe.get_master_bot(master_bot_id)
    if not parent:
        raise _err404("master bot not found")

    pool = await ranker.fetch_candidate_pool(limit=200)
    candidates = pool.get("candidates") or []

    if req.clear_existing:
        for m in (await mbe.list_members(master_bot_id)):
            try:
                await mbe.remove_member(master_bot_id, m["strategy_hash"])
            except Exception:                                  # pragma: no cover
                pass

    plan = [
        ("tier1", req.tier1_count),
        ("tier2", req.tier2_count),
        ("tier3", req.tier3_count),
    ]
    added: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    idx = 0
    for tier, n in plan:
        taken = 0
        while taken < n and idx < len(candidates):
            cand = candidates[idx]
            idx += 1
            sh = cand.get("strategy_hash")
            if not sh:
                continue
            try:
                snap = {
                    "pair":             cand.get("pair"),
                    "timeframe":        cand.get("timeframe"),
                    "style":            cand.get("style"),
                    "profit_factor":    cand.get("profit_factor"),
                    "win_rate":         cand.get("win_rate"),
                    "pass_probability": cand.get("pass_probability"),
                    "deploy_score":     cand.get("deploy_score"),
                    "lifecycle_stage":  cand.get("lifecycle_stage"),
                    "candidate_score":  cand.get("candidate_score"),
                    "captured_at":      pool.get("computed_at"),
                    # MB-7.2 — freeze IR at add-time so the immutable
                    # definition is self-sufficient for cBot export.
                    "strategy_ir":      cand.get("strategy_ir"),
                    "ir_status":        cand.get("ir_status"),
                    "ir_version":       cand.get("ir_version"),
                }
                row = await mbe.add_member(
                    master_bot_id,
                    strategy_hash=sh, tier=tier, snapshot=snap,
                )
                added.append(row)
                taken += 1
            except ValueError as e:
                skipped.append({
                    "strategy_hash": sh, "tier": tier, "reason": str(e),
                })

    return {
        "added":   added,
        "skipped": skipped,
        "added_count":   len(added),
        "skipped_count": len(skipped),
        "candidate_pool_size": len(candidates),
    }


# ─────────────────────────────────────────────────────────────────
# MB-4 — Definition compile / read
# ─────────────────────────────────────────────────────────────────

@router.post("/{master_bot_id}/compile")
async def compile_definition(
    master_bot_id: str,
    req: CompileRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbd.compile_definition(
            master_bot_id,
            runtime_mode=req.runtime_mode or mbd.DEFAULT_RUNTIME_MODE,
            runtime_policy=req.runtime_policy,
            actor=admin.get("email") or "admin",
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.get("/{master_bot_id}/definitions")
async def list_definitions(
    master_bot_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await mbd.list_definitions(master_bot_id, limit=limit)
    return {"count": len(rows), "definitions": rows}


@router.get("/{master_bot_id}/definitions/latest")
async def get_definition_latest(
    master_bot_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    doc = await mbd.get_definition(master_bot_id=master_bot_id)
    if not doc:
        raise _err404("no definition compiled yet")
    return doc


@router.get("/{master_bot_id}/definitions/{rev}")
async def get_definition_by_rev(
    master_bot_id: str, rev: int,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    doc = await mbd.get_definition(master_bot_id=master_bot_id, rev=rev)
    if not doc:
        raise _err404("definition not found")
    return doc


# ─────────────────────────────────────────────────────────────────
# MB-7 — cBot export
# ─────────────────────────────────────────────────────────────────

@router.post("/{master_bot_id}/export")
async def export_master_bot(
    master_bot_id: str,
    req: ExportRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    from engines.parity_certification import ParityGateError
    try:
        return await mbx.export_master_bot(
            master_bot_id,
            revision_id=req.revision_id,
            compile_if_missing=bool(req.compile_if_missing),
            force_parity=bool(req.force_parity),
            actor=admin.get("email") or "admin",
        )
    except ParityGateError as e:
        raise HTTPException(status_code=409, detail={
            "error":   "parity_gate_blocked",
            "message": str(e),
            "verdict": e.verdict,
        })
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.get("/{master_bot_id}/exports")
async def list_exports(
    master_bot_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await mbx.list_exports(master_bot_id, limit=limit)
    return {"count": len(rows), "exports": rows}


@router.get("/exports/{export_id}/download/{kind}")
async def download_export_artifact(
    export_id: str, kind: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from fastapi.responses import Response
    if kind not in ("cs", "meta"):
        raise _err400("kind must be 'cs' or 'meta'")
    try:
        filename, blob = await mbx.read_export_artifact(export_id, kind=kind)
    except ValueError as e:
        raise _err404(str(e))
    media_type = "text/plain; charset=utf-8" if kind == "cs" else "application/json"
    return Response(
        content=blob,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



# ─────────────────────────────────────────────────────────────────
# MB-8 — .cbotpack builder
# ─────────────────────────────────────────────────────────────────

@router.post("/{master_bot_id}/pack")
async def build_cbot_pack(
    master_bot_id: str,
    req: PackRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbpack.build_pack(
            master_bot_id,
            export_id=req.export_id,
            revision_id=req.revision_id,
            actor=admin.get("email") or "admin",
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise _err404(msg)
        raise _err400(msg)


@router.get("/{master_bot_id}/packs")
async def list_cbot_packs(
    master_bot_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await mbpack.list_packs(master_bot_id, limit=limit)
    return {"count": len(rows), "packs": rows}


@router.get("/packs/{pack_id}/download")
async def download_cbot_pack(
    pack_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from fastapi.responses import Response
    try:
        filename, blob = await mbpack.read_pack(pack_id)
    except ValueError as e:
        raise _err404(str(e))
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────
# Revision Diff Viewer
# ─────────────────────────────────────────────────────────────────

@router.get("/{master_bot_id}/diff")
async def diff_revisions(
    master_bot_id: str,
    from_rev: Optional[int] = Query(None, ge=1),
    to_rev:   Optional[int] = Query(None, ge=1),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        return await mbdiff.diff_revisions(
            master_bot_id, from_rev=from_rev, to_rev=to_rev,
        )
    except ValueError as e:
        raise _err404(str(e))



# ─────────────────────────────────────────────────────────────────
# MB-7.2 — Strategy IR back-fill + coverage
# ─────────────────────────────────────────────────────────────────

@router.get("/ir/coverage")
async def ir_coverage(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return await mb_ir_backfill.coverage_stats()


@router.post("/ir/backfill")
async def ir_backfill(
    force: bool = Query(False),
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    return await mb_ir_backfill.backfill_library(
        force=bool(force),
        actor=admin.get("email") or "admin",
    )



# ─────────────────────────────────────────────────────────────────
# MB-10 — Export-time parity gate (preview + status)
# ─────────────────────────────────────────────────────────────────

@router.get("/{master_bot_id}/parity/preview")
async def parity_preview(
    master_bot_id: str,
    revision_id: Optional[str] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Compute the parity verdict for a definition revision WITHOUT
    exporting. Useful for the UI to badge a "Parity Ready / Blocked"
    state before the operator clicks Export."""
    from engines import parity_certification as parity
    from engines import master_bot_definition as _mbd
    rev_doc = (await _mbd.get_definition(revision_id=revision_id)
               if revision_id
               else await _mbd.get_definition(master_bot_id=master_bot_id))
    if not rev_doc:
        raise _err404("revision not found")
    if rev_doc.get("master_bot_id") != master_bot_id:
        raise _err400("revision does not belong to this master bot")
    try:
        verdict = await parity.assert_pass(
            rev_doc.get("revision_id"), enforce=False,
        )
    except ValueError as e:
        raise _err404(str(e))
    return verdict


@router.get("/parity/gate-status")
async def parity_gate_status(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from engines import parity_certification as parity
    return {
        "enabled":      parity.is_parity_gate_enabled(),
        "env_var":      parity.PARITY_GATE_ENV,
        "override_via": "POST /api/master-bot/{id}/export with body.force_parity=true (admin)",
    }




# ─────────────────────────────────────────────────────────────────
# MB-9 Phase 1 — Per-bot deployment endpoints (parametric)
# Safe to declare here — 3-segment paths under /{master_bot_id}/
# do not collide with other routes.
# ─────────────────────────────────────────────────────────────────

@router.post("/{master_bot_id}/deploy/register")
async def deploy_register(
    master_bot_id: str,
    req: RegisterDeploymentRequest,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbdep.register_deployment(
            master_bot_id,
            pack_id=req.pack_id,
            runner_id=req.runner_id,
            actor=admin.get("email") or "admin",
        )
    except mbdep.DeploymentError as e:
        raise _deploy_err(e)


@router.post("/{master_bot_id}/deploy/rollback")
async def deploy_rollback(
    master_bot_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        return await mbdep.rollback(
            master_bot_id, actor=admin.get("email") or "admin",
        )
    except mbdep.DeploymentError as e:
        raise _deploy_err(e)


@router.get("/{master_bot_id}/deployments")
async def deploy_list(
    master_bot_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await mbdep.list_deployments(master_bot_id, limit=limit)
    return {"count": len(rows), "deployments": rows}


@router.get("/{master_bot_id}/deploy/status")
async def deploy_status(
    master_bot_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    live = await mbdep.get_live_deployment(master_bot_id)
    return {
        "master_bot_id": master_bot_id,
        "live":          live,
        "has_live":      bool(live),
    }

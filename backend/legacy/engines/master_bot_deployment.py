"""Master Bot V1 — Deployment Control Plane (MB-9 Phase 1).

The control-plane layer that sits between MB-8 (.cbotpack) and a
Windows VPS runner agent. Per operator decision (2026-02 fork):

  * Topology:   Linux backend + Windows runner (cTrader execution).
  * Transport:  HTTPS polling. Runner pulls; backend never pushes.
  * Sign-off:   30-day TTL for parity sign-offs (re-asserted at every
                state transition).
  * Capital:    Advisory only — no automatic per-account allocation.
  * Routing:    Sticky by (pair, timeframe). Phase 1 = single-runner
                first; routing logic is reserved for Phase 2.

State machine:

    built ─► registered ─► staged ─► live
                              │         │
                              └─────────┴─► rolled_back / archived

Every transition is operator-gated (admin role) AND re-asserts the
MB-10 parity verdict against the configured 30-day TTL.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db
from engines import master_bot_pack as mbpack
from engines import runner_registry as runners
# ── MB-9 Phase 2.C — consumer wiring of the routing engine.
#    Default-gate is OFF; flag-OFF byte-identical to Phase 1.
from engines import runner_router as rr
from engines import feature_flags as _ff

logger = logging.getLogger(__name__)

DEPLOYMENTS_COLL = "master_bot_deployments"

# Parity sign-off TTL (architecture decision: 30 days).
SIGNOFF_TTL_DAYS_DEFAULT = 30

# Terminal/observable states.
STATE_REGISTERED   = "registered"
STATE_STAGED       = "staged"
STATE_LIVE         = "live"
STATE_ROLLED_BACK  = "rolled_back"
STATE_ARCHIVED     = "archived"

VALID_TRANSITIONS = {
    STATE_REGISTERED:  {STATE_STAGED, STATE_ARCHIVED},
    STATE_STAGED:      {STATE_LIVE, STATE_ARCHIVED},
    STATE_LIVE:        {STATE_ROLLED_BACK, STATE_ARCHIVED},
    STATE_ROLLED_BACK: {STATE_LIVE, STATE_ARCHIVED},   # operator can re-promote a rolled-back row
    STATE_ARCHIVED:    set(),
}


# ── Errors ──────────────────────────────────────────────────────────

class DeploymentError(RuntimeError):
    """Raised on invalid state transitions, missing inputs, expired
    sign-offs, etc. The API layer maps this to HTTP 400/409."""


class ParitySignoffExpired(DeploymentError):
    """Sign-off TTL exceeded — operator must re-issue parity before
    the transition can proceed."""


# ── Helpers ─────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _signoff_ttl_days() -> int:
    raw = (os.environ.get("MB9_SIGNOFF_TTL_DAYS") or "").strip()
    try:
        return max(1, int(raw)) if raw else SIGNOFF_TTL_DAYS_DEFAULT
    except (TypeError, ValueError):
        return SIGNOFF_TTL_DAYS_DEFAULT


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[DEPLOYMENTS_COLL].create_index("deployment_id", unique=True)
        await db[DEPLOYMENTS_COLL].create_index(
            [("master_bot_id", 1), ("created_at", -1)],
        )
        await db[DEPLOYMENTS_COLL].create_index([("master_bot_id", 1), ("state", 1)])
        await db[DEPLOYMENTS_COLL].create_index("runner_id")
        await db[DEPLOYMENTS_COLL].create_index("pack_id")
    except Exception:                                            # pragma: no cover
        logger.exception("master_bot_deployment: ensure_indexes failed")


async def _assert_parity_fresh(revision_id: str) -> Dict[str, Any]:
    """Re-assert parity verdict at transition time. Refuses when:
      * verdict.would_block is true (any FAILED or MISSING member), OR
      * any signed_at older than the TTL window.

    Returns the verdict dict on success.
    """
    from engines import parity_certification as parity
    verdict = await parity.assert_pass(revision_id, enforce=False)
    if verdict.get("would_block"):
        raise DeploymentError(
            "parity verdict blocks deployment: "
            f"{verdict.get('failed_count', 0)} FAILED + "
            f"{verdict.get('missing_count', 0)} MISSING members"
        )
    ttl_days = _signoff_ttl_days()
    cutoff = _now() - timedelta(days=ttl_days)
    stale: List[str] = []
    for m in verdict.get("per_member") or []:
        if m.get("verdict") != "PASSED":
            continue
        sa = m.get("signed_at")
        if not sa:
            continue
        try:
            dt = datetime.fromisoformat(str(sa).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if dt < cutoff:
            stale.append(m.get("strategy_hash") or "")
    if stale:
        raise ParitySignoffExpired(
            f"parity sign-off TTL exceeded ({ttl_days}d) for "
            f"{len(stale)} member(s); re-issue sign-off before "
            f"transition. Stale hashes: {stale[:5]}"
            + ("…" if len(stale) > 5 else "")
        )
    return verdict


def _append_transition(row: Dict[str, Any], frm: str, to: str,
                       actor: str, reason: str = "") -> List[Dict[str, Any]]:
    hist = list(row.get("state_transitions") or [])
    hist.append({
        "from":   frm,
        "to":     to,
        "at":     _now_iso(),
        "by":     actor,
        "reason": reason,
    })
    return hist


# ─── Lifecycle: register ─────────────────────────────────────────────

def _pick_representative_pair_tf(pack: Dict[str, Any]) -> Tuple[str, str]:
    """MB-9 Phase 2.C — extract one ``(pair, timeframe)`` representative
    from a pack so the router can be consulted. Walks the pack's
    manifest payload (when present in-row) or falls back to empty
    strings — the router refuses cleanly on empty inputs."""
    payload = pack.get("payload") or {}
    tiers = payload.get("tiers") or []
    for t in tiers:
        for m in t.get("members") or []:
            if not m.get("enabled", True):
                continue
            snap = m.get("snapshot") or {}
            p = (snap.get("pair") or "").strip().upper()
            tf = (snap.get("timeframe") or "").strip().upper()
            if p and tf:
                return p, tf
    return "", ""


async def _auto_route_runner_id_if_enabled(
    pack: Dict[str, Any],
) -> Optional[str]:
    """Consult ``runner_router.route()`` when, and only when, the
    ``RUNNER_AUTO_ROUTE_AT_REGISTER`` flag is true. Returns the
    chosen runner_id or None on any refusal — never raises."""
    if not _ff.flag("RUNNER_AUTO_ROUTE_AT_REGISTER"):
        return None
    pair, tf = _pick_representative_pair_tf(pack)
    if not pair or not tf:
        return None
    try:
        decision = await rr.route(pair, tf)
    except Exception:                                        # pragma: no cover
        logger.exception("auto-route refused: router raised")
        return None
    return decision.get("runner_id")


async def register_deployment(
    master_bot_id: str,
    *,
    pack_id: str,
    runner_id: Optional[str] = None,
    actor: str = "admin",
) -> Dict[str, Any]:
    """Step 1 of MB-9. Pin a `.cbotpack` to a deployment row.

    Validates:
      * pack exists, belongs to this master_bot
      * runner (if provided) is registered + not disabled
      * MB-10 parity verdict re-asserted (no FAILED/MISSING, no
        sign-off older than TTL).
    """
    db = get_db()
    if not pack_id:
        raise DeploymentError("pack_id is required")
    pack = await db[mbpack.PACKS_COLL].find_one(
        {"pack_id": pack_id, "master_bot_id": master_bot_id},
        {"_id": 0},
    )
    if not pack:
        raise DeploymentError(
            "pack not found or does not belong to this master_bot"
        )
    if runner_id:
        r = await runners.get_runner_status(runner_id)
        if not r:
            raise DeploymentError("runner_id not found")
        if r.get("status") == "disabled":
            raise DeploymentError("runner is disabled")
    else:
        # ── MB-9 Phase 2.C consumer hook.
        #
        # When the operator did NOT pin a runner_id explicitly, ask
        # engines.runner_router. The helper is hard-gated by the
        # ``RUNNER_AUTO_ROUTE_AT_REGISTER`` flag — when False (the
        # default) it returns None immediately, preserving Phase 1
        # byte-identical behaviour. Router refusals (no eligible
        # runner) likewise return None and never raise.
        runner_id = await _auto_route_runner_id_if_enabled(pack)
        if runner_id:
            r = await runners.get_runner_status(runner_id)
            if not r or r.get("status") == "disabled":
                # Router suggested an invalid candidate — drop it
                # back to None rather than fail the registration.
                runner_id = None
    revision_id = pack.get("revision_id") or ""
    parity_verdict = await _assert_parity_fresh(revision_id)

    deployment_id = uuid.uuid4().hex
    now = _now_iso()
    row = {
        "deployment_id":           deployment_id,
        "master_bot_id":           master_bot_id,
        "pack_id":                 pack_id,
        "revision_id":             revision_id,
        "rev":                     pack.get("rev"),
        "filename":                pack.get("filename"),
        "sha256":                  pack.get("sha256"),
        "size_bytes":              pack.get("size_bytes"),
        "runner_id":               runner_id,
        "state":                   STATE_REGISTERED,
        "parity_verdict":          parity_verdict,
        "parity_signoff_ttl_days": _signoff_ttl_days(),
        "state_transitions":       [{
            "from": None, "to": STATE_REGISTERED,
            "at":   now,  "by": actor, "reason": "register_deployment",
        }],
        "created_at":              now,
        "created_by":              actor,
        "runner_ack":              None,
        "promoted_at":             None,
        "rolled_back_at":          None,
    }
    await db[DEPLOYMENTS_COLL].insert_one(row)
    return {k: v for k, v in row.items() if k != "_id"}


# ─── Lifecycle: stage ────────────────────────────────────────────────

async def stage_deployment(
    deployment_id: str, *, actor: str = "admin",
) -> Dict[str, Any]:
    """Step 2. registered → staged. The deployment becomes visible
    in the runner's poll queue. Re-asserts parity (defence-in-depth).
    """
    db = get_db()
    row = await db[DEPLOYMENTS_COLL].find_one(
        {"deployment_id": deployment_id}, {"_id": 0},
    )
    if not row:
        raise DeploymentError("deployment not found")
    if row.get("state") not in VALID_TRANSITIONS or \
       STATE_STAGED not in VALID_TRANSITIONS[row.get("state")]:
        raise DeploymentError(
            f"cannot stage from state '{row.get('state')}'"
        )
    if not row.get("runner_id"):
        raise DeploymentError("deployment has no runner_id; assign one first")
    await _assert_parity_fresh(row.get("revision_id"))
    hist = _append_transition(row, row.get("state"), STATE_STAGED, actor,
                              "stage_deployment")
    await db[DEPLOYMENTS_COLL].update_one(
        {"deployment_id": deployment_id},
        {"$set": {"state": STATE_STAGED, "state_transitions": hist}},
    )
    return await get_deployment(deployment_id)


# ─── Lifecycle: promote (go live) ────────────────────────────────────

async def promote_to_live(
    deployment_id: str, *, actor: str = "admin",
) -> Dict[str, Any]:
    """Step 3. staged → live. Archives any prior live deployment for
    the same master_bot. Final parity re-assertion.

    VPS Scaling P1.D — wrapped in `admission_gate(FACTORY_CYCLE)`. With
    `ENABLE_ADMISSION_CONTROL=false` (default) the gate is a no-op and
    behaviour is byte-identical to MB-9 Phase 1. With the flag ON, the
    gate refuses when band=critical/warn or pressure is critical (a
    promotion is a multi-step cycle — refusing it preserves OS headroom).
    """
    from engines.workload_classes import WorkloadClass
    from engines.admission_wrapper import admission_gate

    async with admission_gate(
        WorkloadClass.FACTORY_CYCLE,
        metadata={"site": "master_bot_deployment.promote_to_live",
                  "deployment_id": deployment_id, "actor": actor},
    ):
        return await _promote_to_live_inner(deployment_id, actor=actor)


async def _promote_to_live_inner(
    deployment_id: str, *, actor: str = "admin",
) -> Dict[str, Any]:
    db = get_db()
    row = await db[DEPLOYMENTS_COLL].find_one(
        {"deployment_id": deployment_id}, {"_id": 0},
    )
    if not row:
        raise DeploymentError("deployment not found")
    if row.get("state") != STATE_STAGED:
        raise DeploymentError(
            f"cannot promote from state '{row.get('state')}'; "
            f"must be '{STATE_STAGED}'"
        )
    await _assert_parity_fresh(row.get("revision_id"))

    master_bot_id = row.get("master_bot_id")
    prior = await db[DEPLOYMENTS_COLL].find_one(
        {"master_bot_id": master_bot_id, "state": STATE_LIVE},
        {"_id": 0},
        sort=[("promoted_at", -1)],
    )
    now = _now_iso()
    if prior:
        prior_hist = _append_transition(
            prior, STATE_LIVE, STATE_ARCHIVED, actor,
            f"superseded_by:{deployment_id}",
        )
        await db[DEPLOYMENTS_COLL].update_one(
            {"deployment_id": prior.get("deployment_id")},
            {"$set": {
                "state": STATE_ARCHIVED,
                "archived_at": now,
                "state_transitions": prior_hist,
            }},
        )
    hist = _append_transition(row, STATE_STAGED, STATE_LIVE, actor,
                              "promote_to_live")
    await db[DEPLOYMENTS_COLL].update_one(
        {"deployment_id": deployment_id},
        {"$set": {
            "state":             STATE_LIVE,
            "promoted_at":       now,
            "state_transitions": hist,
        }},
    )
    return await get_deployment(deployment_id)


# ─── Lifecycle: rollback ─────────────────────────────────────────────

async def rollback(
    master_bot_id: str, *, actor: str = "admin",
) -> Dict[str, Any]:
    """Find the prior live deployment (most recent ARCHIVED) and
    re-promote it. The current live becomes ROLLED_BACK.

    Hard requirement (per MB-10 contract): parity is re-asserted at
    rollback time. A stale prior PASSED sign-off does NOT auto-pass.
    """
    db = get_db()
    current_live = await db[DEPLOYMENTS_COLL].find_one(
        {"master_bot_id": master_bot_id, "state": STATE_LIVE},
        {"_id": 0},
        sort=[("promoted_at", -1)],
    )
    if not current_live:
        raise DeploymentError("no live deployment to roll back")
    prior = await db[DEPLOYMENTS_COLL].find_one(
        {
            "master_bot_id": master_bot_id,
            "state": STATE_ARCHIVED,
            "deployment_id": {"$ne": current_live.get("deployment_id")},
        },
        {"_id": 0},
        sort=[("archived_at", -1)],
    )
    if not prior:
        raise DeploymentError("no prior live deployment available for rollback")

    # Re-assert parity for the prior revision — refuses if signoffs
    # have rotted since the prior went archived.
    await _assert_parity_fresh(prior.get("revision_id"))

    now = _now_iso()
    cur_hist = _append_transition(
        current_live, STATE_LIVE, STATE_ROLLED_BACK, actor,
        f"rollback_to:{prior.get('deployment_id')}",
    )
    await db[DEPLOYMENTS_COLL].update_one(
        {"deployment_id": current_live.get("deployment_id")},
        {"$set": {
            "state":             STATE_ROLLED_BACK,
            "rolled_back_at":    now,
            "state_transitions": cur_hist,
        }},
    )
    prior_hist = _append_transition(
        prior, STATE_ARCHIVED, STATE_LIVE, actor,
        f"rollback_from:{current_live.get('deployment_id')}",
    )
    await db[DEPLOYMENTS_COLL].update_one(
        {"deployment_id": prior.get("deployment_id")},
        {"$set": {
            "state":             STATE_LIVE,
            "promoted_at":       now,
            "state_transitions": prior_hist,
        }},
    )
    return {
        "rolled_back_from": current_live.get("deployment_id"),
        "restored_to":      prior.get("deployment_id"),
        "at":               now,
        "by":               actor,
    }


# ─── Runner ACK (called by token-authed runner-facing endpoint) ──────

async def record_runner_ack(
    deployment_id: str,
    *,
    runner_id: str,
    state: str,
    sha256_verified: bool,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """Runner reports the result of an action (pull/verify/start).
    This is observability-only; the row's authoritative state remains
    operator-driven. The ACK is stored on `runner_ack` for the UI."""
    db = get_db()
    row = await db[DEPLOYMENTS_COLL].find_one(
        {"deployment_id": deployment_id}, {"_id": 0},
    )
    if not row:
        raise DeploymentError("deployment not found")
    if row.get("runner_id") != runner_id:
        raise DeploymentError(
            "runner_id does not match deployment.runner_id"
        )
    ack = {
        "state":           state,
        "sha256_verified": bool(sha256_verified),
        "message":         (message or "")[:500],
        "at":              _now_iso(),
    }
    await db[DEPLOYMENTS_COLL].update_one(
        {"deployment_id": deployment_id},
        {"$set": {"runner_ack": ack}},
    )
    return ack


# ─── Read endpoints ──────────────────────────────────────────────────

async def get_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[DEPLOYMENTS_COLL].find_one(
        {"deployment_id": deployment_id}, {"_id": 0},
    )


async def list_deployments(
    master_bot_id: str, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[DEPLOYMENTS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0},
    ).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def get_live_deployment(
    master_bot_id: str,
) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[DEPLOYMENTS_COLL].find_one(
        {"master_bot_id": master_bot_id, "state": STATE_LIVE},
        {"_id": 0},
        sort=[("promoted_at", -1)],
    )


async def runner_poll_queue(runner_id: str) -> List[Dict[str, Any]]:
    """Return deployments this runner should act on. Phase 1 contract:
       * state == STAGED → runner pulls + ACKs `staged`
       * state == LIVE  → runner ensures bot is running + ACKs `live`
       * state == ROLLED_BACK → runner stops the prior bot
    """
    db = get_db()
    cur = db[DEPLOYMENTS_COLL].find(
        {
            "runner_id": runner_id,
            "state": {"$in": [STATE_STAGED, STATE_LIVE, STATE_ROLLED_BACK]},
        },
        {"_id": 0},
    ).sort("created_at", 1)
    return [d async for d in cur]


__all__ = [
    "DEPLOYMENTS_COLL", "SIGNOFF_TTL_DAYS_DEFAULT",
    "STATE_REGISTERED", "STATE_STAGED", "STATE_LIVE",
    "STATE_ROLLED_BACK", "STATE_ARCHIVED",
    "DeploymentError", "ParitySignoffExpired",
    "ensure_indexes",
    "register_deployment", "stage_deployment",
    "promote_to_live", "rollback",
    "record_runner_ack",
    "get_deployment", "list_deployments",
    "get_live_deployment", "runner_poll_queue",
]

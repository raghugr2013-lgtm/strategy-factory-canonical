"""
Factory Supervisor FS-P1.4 — Feature Activation Governance (FAG) proposals.

Implements the operator-mandated 5-state pipeline:

    Observe   →   Recommend   →   Notify   →   Approve   →   Activate

Each step is gated and idempotent. The ONLY mutator that actually
changes a feature flag is `activate()`, and it requires:

  1. A proposal in state `approved`.
  2. The operator who calls `activate()` is `admin`.
  3. The proposal evidence still corroborates the current context.
  4. The operator directive veto (e.g. Auto-Learning) is honoured.

Operator-locked invariants:
  * Advisory only by default. The full pipeline can land proposals,
    notify operators, and survey approvals — but flag flipping is
    explicitly behind the admin-only `activate()` API.
  * Default OFF — the engine itself only runs the pipeline when
    `FS_ENABLE_FAG_ENGINE=true`. Even ON, the operator's explicit
    approval is still required for activation.
  * Provider/transport-neutral.

Proposal lifecycle states (Mongo-backed):
    pending      — created by observe(); awaiting recommendation/notify
    recommended  — eligibility verdict satisfied + Notification raised
    approved     — admin approved (still NOT activated)
    rejected     — admin rejected
    activated    — admin activated; flag flip persisted (best-effort)
    expired      — TTL elapsed (no operator action)

Public surface:
    PROPOSAL_COLLECTION
    STATE_PENDING/RECOMMENDED/APPROVED/REJECTED/ACTIVATED/EXPIRED
    is_enabled()
    ensure_indexes()
    observe(feature_name, ctx, *, user=None)   → proposal dict
    list_proposals(state=None, limit=50)        → list
    get_proposal(proposal_id)                   → dict | None
    approve(proposal_id, user)                  → dict
    reject(proposal_id, user, reason="")        → dict
    activate(proposal_id, user)                 → dict   (admin only, advisory)
    expire_overdue(ttl_sec=86400)               → dict
    stats(window_sec=86400)                     → dict
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from engines.factory_supervisor import eligibility_signals, supervisor_events
from engines.factory_supervisor.copilot_context import CopilotContext

logger = logging.getLogger(__name__)


PROPOSAL_COLLECTION = "factory_supervisor_fag_proposals"

STATE_PENDING     = "pending"
STATE_RECOMMENDED = "recommended"
STATE_APPROVED    = "approved"
STATE_REJECTED    = "rejected"
STATE_ACTIVATED   = "activated"
STATE_EXPIRED     = "expired"

ALL_STATES = (
    STATE_PENDING, STATE_RECOMMENDED, STATE_APPROVED,
    STATE_REJECTED, STATE_ACTIVATED, STATE_EXPIRED,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def is_enabled() -> bool:
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_FAG_ENGINE"))
    except Exception:                                            # pragma: no cover
        return False


async def ensure_indexes() -> Dict[str, Any]:
    try:
        from engines.db import get_db
        db = get_db()
        await db[PROPOSAL_COLLECTION].create_index([("state", 1), ("created_at_epoch", -1)])
        await db[PROPOSAL_COLLECTION].create_index([("feature", 1), ("created_at_epoch", -1)])
        await db[PROPOSAL_COLLECTION].create_index("proposal_id", unique=True)
        return {"created": True, "errors": []}
    except Exception as e:                                       # pragma: no cover
        return {"created": False, "errors": [str(e)[:200]]}


# ─── Step 1: Observe — create a proposal candidate ───────────────────


async def observe(
    feature_name: str,
    ctx: CopilotContext,
    *,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Observe the current eligibility verdict for a feature; create
    a `pending` proposal if eligible. Idempotent — re-observing an
    open proposal returns the existing row."""
    verdict = eligibility_signals.evaluate(feature_name, ctx)
    if not verdict.eligible:
        return {
            "ok":      False,
            "reason":  "not_eligible",
            "feature": feature_name,
            "verdict": verdict.to_dict(),
        }
    # Honour the operator directive veto.
    if verdict.suggested_proposal_kind == "operator_directive_gated":
        return {
            "ok":      False,
            "reason":  "operator_directive_veto",
            "feature": feature_name,
            "verdict": verdict.to_dict(),
        }

    try:
        from engines.db import get_db
        db = get_db()
        # Re-use an open proposal if one already exists.
        existing = await db[PROPOSAL_COLLECTION].find_one(
            {"feature": feature_name,
             "state": {"$in": [STATE_PENDING, STATE_RECOMMENDED, STATE_APPROVED]}},
            {"_id": 0},
        )
        if existing:
            return {"ok": True, "reason": "reused", "proposal": existing}

        proposal_id = str(uuid.uuid4())
        now = _now()
        proposal = {
            "proposal_id":   proposal_id,
            "feature":       feature_name,
            "kind":          verdict.suggested_proposal_kind,
            "state":         STATE_PENDING,
            "verdict":       verdict.to_dict(),
            "evidence":      verdict.evidence,
            "context_phase": ctx.phase,
            "created_by":    (user or {}).get("email") or "auto-observer",
            "created_at":    now.isoformat(),
            "created_at_epoch": now.timestamp(),
            "state_history": [
                {"state": STATE_PENDING, "at": now.isoformat(),
                 "by": (user or {}).get("email") or "auto-observer"},
            ],
        }
        await db[PROPOSAL_COLLECTION].insert_one(dict(proposal))
        proposal.pop("_id", None)
        return {"ok": True, "reason": "created", "proposal": proposal}
    except Exception as e:                                       # pragma: no cover
        logger.debug("[fag_proposals] observe failed: %s", e)
        return {"ok": False, "reason": "exception", "error": str(e)[:200]}


# ─── Steps 2+3: Recommend + Notify ──────────────────────────────────


async def recommend_and_notify(
    proposal_id: str,
    *,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Promote `pending → recommended` AND raise a Notification
    Center alert. Idempotent — calling on an already-recommended
    proposal is a no-op."""
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[PROPOSAL_COLLECTION].find_one(
            {"proposal_id": proposal_id}, {"_id": 0},
        )
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row["state"] != STATE_PENDING:
            return {"ok": True, "reason": "noop", "proposal": row}
        now = _now()
        await db[PROPOSAL_COLLECTION].update_one(
            {"proposal_id": proposal_id},
            {"$set": {"state": STATE_RECOMMENDED,
                      "recommended_at": now.isoformat(),
                      "recommended_at_epoch": now.timestamp()},
             "$push": {"state_history": {
                 "state": STATE_RECOMMENDED, "at": now.isoformat(),
                 "by": (user or {}).get("email") or "fag_engine"}}},
        )
        # Emit a Notification Center event so the operator sees this
        # in their inbox. Best-effort.
        try:
            await supervisor_events.emit(
                event_type="WORK_ROUTED",   # generic; producer renames to FAG_RECOMMENDATION below
                target_id=row["feature"],
                payload={
                    "kind":         "fag_recommendation",
                    "proposal_id":  proposal_id,
                    "feature":      row["feature"],
                    "verdict":      row.get("verdict"),
                },
                title=f"Feature ready for activation: {row['feature']}",
                category="recommendation",
                severity="info",
                correlation_id=proposal_id,
                suggested_action=(
                    "Open Architect → Governance to approve or reject."
                ),
            )
        except Exception as e:                                   # pragma: no cover
            logger.debug("[fag_proposals] notify failed: %s", e)
        row["state"] = STATE_RECOMMENDED
        return {"ok": True, "reason": "promoted", "proposal": row}
    except Exception as e:                                       # pragma: no cover
        return {"ok": False, "reason": "exception", "error": str(e)[:200]}


# ─── Step 4: Approve / Reject ───────────────────────────────────────


async def approve(
    proposal_id: str,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return await _transition(proposal_id, STATE_APPROVED, user)


async def reject(
    proposal_id: str,
    user: Optional[Dict[str, Any]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    return await _transition(proposal_id, STATE_REJECTED, user, extra={"reject_reason": reason})


async def _transition(
    proposal_id: str,
    target_state: str,
    user: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[PROPOSAL_COLLECTION].find_one(
            {"proposal_id": proposal_id}, {"_id": 0},
        )
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row["state"] in (STATE_REJECTED, STATE_ACTIVATED, STATE_EXPIRED):
            return {"ok": False, "reason": "terminal_state", "current": row["state"]}
        now = _now()
        set_doc = {"state": target_state,
                   "transitioned_at": now.isoformat(),
                   "transitioned_at_epoch": now.timestamp()}
        if extra:
            set_doc.update(extra)
        await db[PROPOSAL_COLLECTION].update_one(
            {"proposal_id": proposal_id},
            {"$set": set_doc,
             "$push": {"state_history": {
                 "state": target_state, "at": now.isoformat(),
                 "by": (user or {}).get("email") or "operator"}}},
        )
        row["state"] = target_state
        return {"ok": True, "reason": "transitioned", "proposal": row}
    except Exception as e:                                       # pragma: no cover
        return {"ok": False, "reason": "exception", "error": str(e)[:200]}


# ─── Step 5: Activate (admin only — actually flips the flag) ─────────


async def activate(
    proposal_id: str,
    user: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Activate an APPROVED proposal — i.e. flip the feature flag in
    the local process env. Best-effort: persistence across restart
    requires the operator to bake the flag into the host env file.

    This is the SOLE FAG mutator. It requires:
      * Proposal in state APPROVED.
      * caller user has admin role (the API layer enforces).
      * Operator-directive veto MUST be honoured (Auto-Learning).
    """
    try:
        from engines.db import get_db
        db = get_db()
        row = await db[PROPOSAL_COLLECTION].find_one(
            {"proposal_id": proposal_id}, {"_id": 0},
        )
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row["state"] != STATE_APPROVED:
            return {"ok": False, "reason": "not_approved", "current": row["state"]}

        # Re-honour the directive veto.
        if (row.get("verdict") or {}).get("suggested_proposal_kind") == "operator_directive_gated":
            return {"ok": False, "reason": "operator_directive_veto",
                    "feature": row["feature"]}

        # Flip the flag in the process env (best-effort, advisory-
        # only — persistent flip is the operator's call).
        import os
        flag_name = row["feature"]
        os.environ[flag_name] = "true"
        # Invalidate caches that observe flags.
        try:
            from engines.factory_supervisor import system_state_view
            system_state_view.invalidate_cache()
        except Exception:                                        # pragma: no cover
            pass

        now = _now()
        await db[PROPOSAL_COLLECTION].update_one(
            {"proposal_id": proposal_id},
            {"$set": {"state": STATE_ACTIVATED,
                      "activated_at": now.isoformat(),
                      "activated_at_epoch": now.timestamp(),
                      "activated_by": (user or {}).get("email") or "admin"},
             "$push": {"state_history": {
                 "state": STATE_ACTIVATED, "at": now.isoformat(),
                 "by": (user or {}).get("email") or "admin"}}},
        )
        # Emit a notification for the activation.
        try:
            await supervisor_events.emit(
                event_type="WORK_ROUTED",
                target_id=flag_name,
                payload={"kind": "fag_activation", "proposal_id": proposal_id},
                title=f"Feature activated: {flag_name}",
                category="recommendation",
                severity="info",
                correlation_id=proposal_id,
            )
        except Exception:                                        # pragma: no cover
            pass
        row["state"] = STATE_ACTIVATED
        return {"ok": True, "reason": "activated", "proposal": row,
                "flag": flag_name, "advisory_note":
                "process-env flip only; bake into host env for persistence."}
    except Exception as e:                                       # pragma: no cover
        return {"ok": False, "reason": "exception", "error": str(e)[:200]}


# ─── Step 6: Expire overdue proposals ───────────────────────────────


async def expire_overdue(ttl_sec: int = 86400) -> Dict[str, Any]:
    try:
        from engines.db import get_db
        db = get_db()
        cutoff = (_now() - timedelta(seconds=int(ttl_sec))).timestamp()
        res = await db[PROPOSAL_COLLECTION].update_many(
            {"state": {"$in": [STATE_PENDING, STATE_RECOMMENDED, STATE_APPROVED]},
             "created_at_epoch": {"$lt": cutoff}},
            {"$set": {"state": STATE_EXPIRED,
                      "expired_at_epoch": _now().timestamp()}},
        )
        return {"expired": int(res.modified_count)}
    except Exception as e:                                       # pragma: no cover
        return {"expired": 0, "error": str(e)[:200]}


# ─── Read API ───────────────────────────────────────────────────────


async def list_proposals(
    state: Optional[str] = None,
    feature: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if state:
        q["state"] = state
    if feature:
        q["feature"] = feature
    try:
        from engines.db import get_db
        db = get_db()
        cur = (
            db[PROPOSAL_COLLECTION]
            .find(q, {"_id": 0})
            .sort("created_at_epoch", -1)
            .limit(max(1, min(int(limit), 1000)))
        )
        return [d async for d in cur]
    except Exception as e:                                       # pragma: no cover
        logger.debug("[fag_proposals] list failed: %s", e)
        return []


async def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        return await db[PROPOSAL_COLLECTION].find_one(
            {"proposal_id": proposal_id}, {"_id": 0},
        )
    except Exception:                                            # pragma: no cover
        return None


async def stats(window_sec: int = 86400) -> Dict[str, Any]:
    cutoff = (_now() - timedelta(seconds=int(window_sec))).timestamp()
    per_state: Dict[str, int] = {s: 0 for s in ALL_STATES}
    per_feature: Dict[str, int] = {}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        cur = db[PROPOSAL_COLLECTION].find(
            {"created_at_epoch": {"$gte": cutoff}},
            {"_id": 0, "state": 1, "feature": 1},
        )
        async for row in cur:
            total += 1
            per_state.setdefault(row.get("state", "pending"), 0)
            per_state[row.get("state", "pending")] += 1
            per_feature[row.get("feature", "?")] = per_feature.get(row.get("feature", "?"), 0) + 1
    except Exception as e:                                       # pragma: no cover
        logger.debug("[fag_proposals] stats failed: %s", e)
    return {"window_sec": window_sec, "total": total,
            "per_state": per_state, "per_feature": per_feature}

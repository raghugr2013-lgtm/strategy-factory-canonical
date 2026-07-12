"""
Phase 2 scaffolding — Widening proposal channel (DORMANT, manual approval).

A dedicated write-only collection (``widening_proposals``) that lets
future agents (or operators) submit a STRUCTURED proposal to advance
the activation roadmap. Proposals do NOT execute automatically — they
require an explicit ``approve_proposal()`` call from an admin-
authenticated operator, AND even after approval no flag is flipped
implicitly. Execution is a separate manual `POST /api/admin/flag`.

State machine
-------------
    PENDING  ── approve_proposal() ──►  APPROVED   (record-of-intent only)
       │
       └────── reject_proposal()  ──►  REJECTED

Approval flow is recorded in ``activation_journal`` so the forensic
trail captures both the proposal and the operator decision.

Discipline:
  * No auto-execution under any circumstance.
  * Proposals are append-only; status transitions touch the same row
    but the original payload is preserved.
  * Best-effort persistence — failures never raise out.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "widening_proposals"

STATUS_PENDING  = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXECUTED = "executed"     # marked by a future flag-flip endpoint
STATUS_EXPIRED  = "expired"      # operator-decided

DEFAULT_LIMIT = 50
MAX_LIMIT = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def submit_proposal(
    *,
    proposed_flag: str,
    proposed_value: Any,
    submitted_by: str,
    rationale: str = "",
    target_stage: Optional[str] = None,
    success_criteria: Optional[List[str]] = None,
    advisor_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one PENDING proposal. Returns the proposal_id on success."""
    try:
        now = _now()
        pid = uuid.uuid4().hex[:16]
        doc = {
            "proposal_id":  pid,
            "ts":           now.isoformat(),
            "ts_dt":        now,
            "status":       STATUS_PENDING,
            "proposed_flag": str(proposed_flag)[:80],
            "proposed_value": proposed_value,
            "target_stage": str(target_stage)[:8] if target_stage else None,
            "submitted_by": str(submitted_by)[:120],
            "rationale":    str(rationale)[:2000],
            "success_criteria": list(success_criteria or [])[:20],
            "advisor_payload":  advisor_payload or {},
            "decision":     None,
            "decided_at":   None,
            "decided_at_dt": None,
            "decided_by":   None,
            "decision_rationale": None,
            "phase":        "scaffolding-1",
        }
        await get_db()[COLLECTION].insert_one(doc)
        # Forensic stamp.
        try:
            from engines import activation_journal
            await activation_journal.journal_event(
                "widening_proposal_submitted",
                actor=submitted_by,
                summary=(
                    f"Proposal {pid}: set {proposed_flag} = {proposed_value!r} "
                    f"({rationale[:200]})"
                ),
                payload={"proposal_id": pid, "proposed_flag": proposed_flag,
                         "proposed_value": proposed_value,
                         "target_stage": target_stage},
                include_safe_to_widen=True,
                include_governance=False,
            )
        except Exception:                                   # pragma: no cover
            pass
        return {"ok": True, "proposal_id": pid, "status": STATUS_PENDING}
    except Exception as e:                                  # pragma: no cover
        logger.debug("[widening_proposal] submit failed: %s", e)
        return {"ok": False, "reason": f"persistence_error: {str(e)[:200]}"}


async def _decide(
    proposal_id: str,
    *,
    decision: str,
    decided_by: str,
    rationale: str = "",
) -> Dict[str, Any]:
    """Internal state-transition helper."""
    if decision not in (STATUS_APPROVED, STATUS_REJECTED, STATUS_EXPIRED):
        return {"ok": False, "reason": "invalid_decision"}
    try:
        now = _now()
        doc = await get_db()[COLLECTION].find_one_and_update(
            {"proposal_id": proposal_id, "status": STATUS_PENDING},
            {"$set": {
                "status":              decision,
                "decision":            decision,
                "decided_at":          now.isoformat(),
                "decided_at_dt":       now,
                "decided_by":          str(decided_by)[:120],
                "decision_rationale":  str(rationale)[:2000],
            }},
            projection={"_id": 0},
            return_document=True,
        )
        if doc is None:
            return {"ok": False, "reason": "not_found_or_not_pending"}
        try:
            from engines import activation_journal
            await activation_journal.journal_event(
                f"widening_proposal_{decision}",
                actor=decided_by,
                summary=(
                    f"Proposal {proposal_id} {decision} by {decided_by} "
                    f"(flag={doc.get('proposed_flag')})"
                ),
                payload={"proposal_id": proposal_id, "decision": decision},
                include_safe_to_widen=False,
                include_governance=False,
            )
        except Exception:                                   # pragma: no cover
            pass
        return {"ok": True, "proposal_id": proposal_id, "status": decision}
    except Exception as e:                                  # pragma: no cover
        logger.debug("[widening_proposal] decide failed: %s", e)
        return {"ok": False, "reason": f"persistence_error: {str(e)[:200]}"}


async def approve_proposal(
    proposal_id: str, *, decided_by: str, rationale: str = "",
) -> Dict[str, Any]:
    return await _decide(proposal_id, decision=STATUS_APPROVED,
                         decided_by=decided_by, rationale=rationale)


async def reject_proposal(
    proposal_id: str, *, decided_by: str, rationale: str = "",
) -> Dict[str, Any]:
    return await _decide(proposal_id, decision=STATUS_REJECTED,
                         decided_by=decided_by, rationale=rationale)


async def list_proposals(
    *,
    status: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """Read-only chronological listing of proposals (newest first)."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    query: Dict[str, Any] = {}
    if status:
        query["status"] = str(status)[:20]
    rows: List[Dict[str, Any]] = []
    try:
        cur = get_db()[COLLECTION].find(query, {"_id": 0}).sort("ts_dt", -1).limit(limit)
        async for d in cur:
            rows.append(d)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[widening_proposal] list failed: %s", e)
    return {
        "ts":            _now().isoformat(),
        "read_only":     True,
        "operator_authority": "final",
        "filter_status": status,
        "limit":         limit,
        "count":         len(rows),
        "proposals":     rows,
    }

"""Phase I — Applier.

DORMANT in OBSERVE mode. Only invoked in RECOMMEND (via explicit
operator approval) or AUTONOMOUS (via whitelist + confidence gate).

Application writes to `meta_learning_overrides`. Downstream engines
consume overrides only when their respective `*_USE_META_OVERRIDES`
env flag is true.

Every application:
  1. Records `previous_value` (from override table if present, else
     the current-value snapshot passed in by the caller).
  2. Enforces `max_delta_per_tick` and per-surface `class_caps` per
     rolling 24h.
  3. Emits `meta_learning_application` outcome event.
  4. Is fully reversible via `revert_override()`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from . import config as mlcfg
from . import ledger, explainability
from .types import (
    MetaApplication, MetaMode, MetaRecStatus, MetaRecommendation,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ApplierGuardBlocked(Exception):
    """Raised when a guardrail refuses the application."""


async def apply_recommendation(
    r: MetaRecommendation, *, applied_by: str,
) -> Optional[MetaApplication]:
    """Apply one recommendation. Returns the MetaApplication row
    written, or None if blocked by guard.

    Structural safety: this function is ONLY called from paths that
    have already checked mode ≠ OBSERVE (API approve + orchestrator
    autonomous branch). Even so, we re-check here as belt-and-suspenders.
    """
    cur_mode = mlcfg.mode()
    if not MetaMode.can_apply(cur_mode):
        raise ApplierGuardBlocked(
            f"mode={cur_mode} — apply blocked (OBSERVE/DISABLED)")

    # Autonomous mode additional gates
    if cur_mode == MetaMode.AUTONOMOUS:
        if not mlcfg.autonomous_confirm():
            raise ApplierGuardBlocked(
                "META_LEARNING_AUTONOMOUS_CONFIRM=YES not set")
        if r.surface not in mlcfg.autonomous_whitelist():
            raise ApplierGuardBlocked(
                f"surface {r.surface} not in autonomous_whitelist")

    # Enforce max_delta_per_tick
    if abs(r.proposed_delta) > mlcfg.max_delta_per_tick() + 1e-9:
        raise ApplierGuardBlocked(
            f"|delta|={abs(r.proposed_delta)} > max_delta_per_tick")

    # Enforce per-surface class cap (rolling 24h cumulative)
    cap = mlcfg.class_caps().get(r.surface, 0.05)
    recent = await ledger.read_applications(target=r.target, limit=1000)
    cutoff = datetime.now(timezone.utc).timestamp() - 86400
    cum = 0.0
    for a in recent:
        try:
            ts = datetime.fromisoformat(a.applied_at.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            cum += abs(a.new_value - a.previous_value)
    if cum + abs(r.proposed_delta) > cap + 1e-9:
        raise ApplierGuardBlocked(
            f"class cap {cap} exceeded (cum={cum})")

    # Look up previous value from override table (fallback: r.current_value)
    prev_row = await ledger.read_override(r.target)
    previous = float(prev_row["value"]) if prev_row else float(r.current_value)

    # Write override
    await ledger.upsert_override(r.target, r.proposed_value, source=applied_by)

    # Journal the application
    app = MetaApplication(
        application_id="ml_app_" + uuid.uuid4().hex[:12],
        recommendation_id=r.recommendation_id,
        target=r.target,
        previous_value=previous,
        new_value=float(r.proposed_value),
        applied_at=_now_iso(),
        applied_by=applied_by,
        mode=cur_mode,
        reversible=True,
    )
    await ledger.upsert_application(app)
    await ledger.update_recommendation_status(
        r.recommendation_id, MetaRecStatus.APPLIED,
        reason=f"applied by {applied_by}")

    await explainability.emit(
        "meta_learning_application",
        reason=f"applied {r.target}: {previous} → {r.proposed_value}",
        metrics={"recommendation_id": r.recommendation_id,
                  "target": r.target,
                  "previous_value": previous,
                  "new_value": float(r.proposed_value),
                  "mode": cur_mode},
        evidence={"application_id": app.application_id,
                   "applied_by": applied_by},
    )
    return app


async def revert_override(target: str, *, reason: str = "") -> bool:
    """Delete an override row and journal the reversion."""
    prev_row = await ledger.read_override(target)
    if not prev_row:
        return False
    deleted = await ledger.delete_override(target)
    if not deleted:
        return False
    await explainability.emit(
        "meta_learning_revert",
        reason=f"reverted override on {target}: {reason}",
        metrics={"target": target,
                  "previous_value": prev_row.get("value")},
        evidence={"source": prev_row.get("source"),
                   "reason": reason},
    )
    return True

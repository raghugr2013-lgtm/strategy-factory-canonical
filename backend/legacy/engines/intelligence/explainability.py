"""Phase C — Explainability helper.

Every intelligence decision (classification, scoring, bundle build, regime
detection, activation) emits an `outcome_events` row so the operator can
audit any recommendation end-to-end. Reuses the Phase A/B emitter contract
without adding new collections.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def emit_decision(
    decision_type: str,
    *,
    strategy_hash: Optional[str] = None,
    learning_run_id: Optional[str] = None,
    reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Emit an `outcome_events` row tagged as an intelligence decision.

    stage = "approve" (existing schema — advisory-only decisions never
    persist mutations; they surface via metrics + evidence blocks).
    """
    try:
        from engines.learning import emit, new_run_id
        run_id = learning_run_id or new_run_id()
        payload = {
            "decision_type": decision_type,
            "evidence": evidence or {},
        }
        payload.update(metrics or {})
        return await emit(
            "approve",
            learning_run_id=run_id,
            status="pass",
            strategy_hash=strategy_hash,
            reason=(reason or f"intelligence:{decision_type}")[:512],
            metrics=payload,
            provider="intelligence_engine",
        )
    except Exception:  # noqa: BLE001
        logger.exception("[intelligence] emit_decision failed (non-fatal)")
        return None

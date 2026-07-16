"""Phase I — Explainability helper.

Emits `outcome_events` rows tagged with the Phase I decision-type
markers (§22 of design doc). Zero side effects on any other engine's
state. Non-fatal on failure.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def emit(
    decision_type: str,
    *,
    reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    strategy_hash: Optional[str] = None,
) -> Optional[str]:
    """Emit a meta-learning outcome_events row.

    decision_type ∈ {
      meta_learning_cycle_start, meta_learning_evaluation,
      meta_learning_recommendation, meta_learning_cycle_end,
      meta_learning_mode_change, meta_learning_application,
      meta_learning_revert
    }
    """
    try:
        from engines.learning import emit as _emit, new_run_id
        payload: Dict[str, Any] = {
            "decision_type": decision_type,
            "evidence": evidence or {},
        }
        payload.update(metrics or {})
        return await _emit(
            "approve",
            learning_run_id=new_run_id(),
            status="pass",
            strategy_hash=strategy_hash,
            reason=(reason or f"meta_learning:{decision_type}")[:512],
            metrics=payload,
            provider="meta_learning_engine",
        )
    except Exception:  # noqa: BLE001
        logger.exception("[meta_learning] emit failed (non-fatal)")
        return None

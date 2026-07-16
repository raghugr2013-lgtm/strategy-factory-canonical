"""Phase J — Explainability helper."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def emit(
    decision_type: str, *, reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    evidence: Optional[Dict[str, Any]] = None,
    strategy_hash: Optional[str] = None,
) -> Optional[str]:
    """Emit a factory_eval outcome_event.

    decision_type ∈ {factory_eval_cycle_start, factory_report,
                      factory_eval_insight, factory_eval_recommendation,
                      factory_eval_cycle_end, factory_eval_mode_change,
                      factory_eval_application, factory_eval_revert}
    """
    try:
        from engines.learning import emit as _emit, new_run_id
        payload = {"decision_type": decision_type, "evidence": evidence or {}}
        payload.update(metrics or {})
        return await _emit(
            "approve", learning_run_id=new_run_id(), status="pass",
            strategy_hash=strategy_hash,
            reason=(reason or f"factory_eval:{decision_type}")[:512],
            metrics=payload, provider="factory_eval_engine",
        )
    except Exception:  # noqa: BLE001
        logger.exception("[factory_eval] emit failed (non-fatal)")
        return None

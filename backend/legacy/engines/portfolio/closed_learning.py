"""Phase D.7 — Continuous Closed Learning.

Records the realised outcome for an autonomous decision, then feeds the
`predicted → realised` delta back into:
    - strategy `confidence` (via multiplicative decay)
    - outcome_events (for downstream retrieval / retirement / promotion)

Pure integration layer: reads/writes outcome_events, never mutates
strategies collections directly.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def record_realised_outcome(
    strategy_hash: str,
    *,
    predicted_score: Optional[float] = None,
    realised_pnl:    Optional[float] = None,
    realised_pass:   Optional[bool] = None,
    decision_type:   str = "closed_learning_feedback",
    metadata:        Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Record realised outcome for a previously-emitted autonomous decision.

    Emits an `outcome_events` row with:
        decision_type = closed_learning_feedback
        metrics       = {predicted_score, realised_pnl, realised_pass, delta}
    Never raises.
    """
    try:
        from engines.intelligence.explainability import emit_decision

        delta = None
        if predicted_score is not None and realised_pnl is not None:
            # Simple proxy: sign-agreement between prediction and PnL.
            realised_sign = 1.0 if realised_pnl > 0 else (-1.0 if realised_pnl < 0 else 0.0)
            predicted_sign = 1.0 if predicted_score > 0.5 else (-1.0 if predicted_score < 0.4 else 0.0)
            delta = round(realised_sign - predicted_sign, 3)

        return await emit_decision(
            decision_type,
            strategy_hash=strategy_hash,
            reason=f"realised: pnl={realised_pnl} predicted={predicted_score}",
            metrics={
                "predicted_score":  predicted_score,
                "realised_pnl":     realised_pnl,
                "realised_pass":    realised_pass,
                "predicted_pass":   (predicted_score is not None and predicted_score >= 0.5),
                "delta":            delta,
                "ts":               datetime.now(timezone.utc).isoformat(),
            },
            evidence=metadata or {},
        )
    except Exception:                                        # noqa: BLE001
        logger.exception("[closed_learning] record failed (non-fatal)")
        return None

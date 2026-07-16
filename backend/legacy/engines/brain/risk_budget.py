"""Phase F — Risk Budget."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from . import config as bcfg


@dataclass
class RiskBudgetSnapshot:
    headroom:              float          # 0..1
    open_positions:        int
    theoretical_max:       int
    correlation_penalty:   float
    hard_block_below:      float
    is_blocking_increase:  bool
    evidence:              Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_risk_budget(
    open_positions: int = 0,
    avg_correlation: Optional[float] = None,
) -> RiskBudgetSnapshot:
    theoretical_max = bcfg.risk_max_concurrent_trades()
    open_positions = max(0, int(open_positions))
    corr_penalty = 0.0
    if avg_correlation is not None:
        # High correlation eats budget: 0.7 corr → 30% budget haircut
        corr_penalty = max(0.0, min(0.5, (avg_correlation - 0.3) * 1.0))
    effective_used = open_positions + (theoretical_max * corr_penalty)
    headroom = max(0.0, min(1.0, 1.0 - (effective_used / max(1, theoretical_max))))
    hard_block = bcfg.risk_headroom_hard_block()
    return RiskBudgetSnapshot(
        headroom=round(headroom, 4),
        open_positions=open_positions,
        theoretical_max=theoretical_max,
        correlation_penalty=round(corr_penalty, 4),
        hard_block_below=hard_block,
        is_blocking_increase=(headroom < hard_block),
        evidence={"avg_correlation": avg_correlation,
                  "effective_used": round(effective_used, 3)},
    )

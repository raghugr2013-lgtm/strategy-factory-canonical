"""Phase D — Adaptive Autonomous Portfolio & Master Bot Engine.

Public API:
    from engines.portfolio import (
        # Types
        PortfolioMember, PortfolioAction, PortfolioState,
        # 1) Allocation
        allocation_decisions,
        # 2) Capital
        capital_reweight,
        # 3) Health
        portfolio_health, HealthReport,
        # 4) Promotion
        promotion_candidates, PromotionDecision,
        # 5) Retirement
        retirement_candidates, RetirementDecision,
        # 6) Self-rebuilding master bot
        rebuild_master_bot, RebuildReport,
        # 7) Closed learning
        record_realised_outcome,
    )
"""
from __future__ import annotations

from .types import (              # noqa: F401
    PortfolioAction,
    PortfolioMember,
    PortfolioState,
)
from .allocation import allocation_decisions  # noqa: F401
from .capital import capital_reweight         # noqa: F401
from .health import portfolio_health, HealthReport  # noqa: F401
from .promotion import promotion_candidates, PromotionDecision  # noqa: F401
from .retirement import retirement_candidates, RetirementDecision  # noqa: F401
from .rebuilder import rebuild_master_bot, RebuildReport  # noqa: F401
from .closed_learning import record_realised_outcome  # noqa: F401

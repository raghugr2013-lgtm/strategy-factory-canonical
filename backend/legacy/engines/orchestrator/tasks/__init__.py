"""Phase B.2 — Task adapter registry.

Importing this package auto-registers all 11 task types via `@registry.register`.
Import order is defined here; downstream code should import
`engines.orchestrator.tasks` (this package) exactly once at startup.

Each adapter is a thin wrapper over an existing engine — no new business
logic. Failures degrade to `Readiness(eligible=False)` rather than raising.
"""
from __future__ import annotations

from . import (              # noqa: F401 — side-effect: registration
    market_data_topup,
    bi5_realism_sweep,
    knowledge_index_refresh,
    strategy_generate,
    backtest,
    validation,
    mutation,
    optimization,
    learning_cycle,
    ranking,
    master_bot_bundle_refresh,
    self_rebuild,
    market_intelligence_refresh,
    broker_health_check,
    execution_attribution,
    meta_learning_evaluation,
)

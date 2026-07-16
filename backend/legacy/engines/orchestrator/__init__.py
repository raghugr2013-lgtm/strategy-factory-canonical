"""Phase B.2 — Unified Autonomous Orchestration Engine (package root).

Public API (used by `api/orchestrator_engine.py` + tests):

    from engines.orchestrator import (
        # Core
        Orchestrator, get_orchestrator, is_active,
        # Types
        Task, TaskResult, Readiness, OrchestratorContext,
        # Registry
        registry,
        # Budget
        BudgetTracker, get_budget_tracker,
    )
"""
from __future__ import annotations

from .types import (       # noqa: F401
    OrchestratorContext,
    Readiness,
    Task,
    TaskResult,
    WorkloadClass,
)
from .registry import registry     # noqa: F401
from .budget_tracker import (      # noqa: F401
    BudgetTracker,
    BudgetWeights,
    get_budget_tracker,
)
from .core import (                # noqa: F401
    Orchestrator,
    get_orchestrator,
    is_active,
    orchestrator_enabled,
)

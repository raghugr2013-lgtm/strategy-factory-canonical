"""Phase C — Autonomous Quant Intelligence.

Five modules that together convert learned strategies into adaptive Master
Bots. Additive over the existing engines (regime_classifier,
portfolio_engine, master_bot_engine, strategy_ranking_engine).

Public API:
    from engines.intelligence import (
        # 1) Strategy Intelligence
        classify_strategy, StrategyClassification,
        # 2) Portfolio Intelligence
        portfolio_contribution_score, PortfolioScore,
        # 3) Master Bot Builder
        build_tiered_bundles, BundleReport,
        # 4) Market Regime Engine
        current_regime, RegimeSnapshot,
        # 5) Dynamic Strategy Selector
        select_active_strategy, ActivationDecision,
    )

Every decision is stamped into `outcome_events` via `explainability.emit_decision`
so the operator can audit any recommendation end-to-end.
"""
from __future__ import annotations

from .strategy_intelligence import StrategyClassification, classify_strategy  # noqa: F401
from .portfolio_intelligence import PortfolioScore, portfolio_contribution_score  # noqa: F401
from .master_bot_builder import BundleReport, build_tiered_bundles  # noqa: F401
from .market_regime import RegimeSnapshot, current_regime  # noqa: F401
from .dynamic_selector import ActivationDecision, select_active_strategy  # noqa: F401
from .explainability import emit_decision  # noqa: F401

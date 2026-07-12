"""Inject an IngestedStrategy into the existing mutation pipeline.

This is the ONE bridge between the ingestion layer and the rest of the
system. It does NOT modify mutation, scoring, evolution, or save logic —
it just hands a well-formed `base_strategy` dict to the existing
`run_mutation_pipeline(..., auto_save=True)`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from engines.mutation_engine import run_mutation_pipeline

from .schema import IngestedStrategy

logger = logging.getLogger(__name__)


async def inject_strategy(
    strategy: IngestedStrategy,
    *,
    max_variants: int = 10,
    auto_save: bool = True,
    firm: str = "ftmo",
) -> Dict[str, Any]:
    """Push `strategy` through the mutation pipeline. Returns the raw
    pipeline response verbatim (including `best_variant`,
    `auto_save_result`, etc.).

    NOTE: the pipeline's own `_is_eligible` gate governs persistence.
    Ingested strategies get NO special treatment.
    """
    base = {
        "strategy_text": strategy.to_strategy_text(),
        "pair": strategy.pair,
        "timeframe": strategy.timeframe,
        "style": strategy.type,
    }
    logger.info(
        "injecting ingested strategy name=%r type=%s source=%s pair=%s tf=%s",
        strategy.name, strategy.type, strategy.source,
        strategy.pair, strategy.timeframe,
    )
    return await run_mutation_pipeline(
        base,
        max_variants=max_variants,
        prices=None,                   # reuse real BID candles
        triggered_by=f"ingestion:{strategy.source}",
        auto_save=auto_save,
        firm=firm,
    )

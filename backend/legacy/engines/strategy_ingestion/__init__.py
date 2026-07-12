"""Strategy Ingestion Pipeline — input layer only.

Collects external strategy code (GitHub / TradingView / local queue),
parses it into a structured form via AI, validates + normalises the
result, and hands the normalised strategy to the EXISTING mutation
pipeline with auto_save=True. The existing `_is_eligible` gate,
`save_strategy`, scoring and evolution logic are NEVER modified.

Public surface:
  from engines.strategy_ingestion import (
      IngestedStrategy, run_ingestion_once, get_ingestion_state,
      set_scheduler_enabled, add_local_strategy,
  )
"""
from .schema import IngestedStrategy  # noqa: F401
from .ingestion_runner import (  # noqa: F401
    run_ingestion_once,
    get_ingestion_state,
    set_scheduler_enabled,
    add_local_strategy,
    list_ingested_strategies,
    list_ingestion_runs,
)

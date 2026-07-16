"""v1.2.0-alpha2 Phase G — Market Intelligence engine.

Learns FROM the market (trend duration, volatility dynamics, breakout
quality, correlation, session behaviour, liquidity, style performance)
rather than from strategy performance alone. Emits `MarketState`
rollups and `StructuralChange` signals so the Adaptive Trading Brain
can adapt BEFORE strategies begin failing.

Master switch: `MI_ENABLED` (default true — passive; harmless when
brain weights are 0.0).
Brain-integration switch: `BRAIN_USES_MARKET_INTELLIGENCE` (default
false — two-step operator opt-in per operator refinement).

Backward compatible: with `MI_ENABLED=false` OR
`BRAIN_USES_MARKET_INTELLIGENCE=false` the brain behaves byte-identically
to Phase F. With `BRAIN_USES_MARKET_INTELLIGENCE=true` and market weights
> 0, the brain begins to consume market intelligence.
"""
from __future__ import annotations

from .types import (            # noqa: F401
    MarketSnapshot, MarketState, StructuralChange, MarketIntelligence,
    ObserverResult,
)
from .config import (           # noqa: F401
    mi_enabled, mi_universe, mi_timeframes, mi_state_windows,
    observer_min_snapshots, change_severity_min, snapshot_ttl_days,
    refresh_task_passive, brain_uses_market_intelligence,
    brain_market_risk_pause_enabled,
    w_market_confidence, w_style_confidence, w_opportunity,
    market_risk_pause_threshold, market_style_min_confidence,
)
from .ledger import (           # noqa: F401
    ensure_indexes, append_snapshot, upsert_state, insert_change,
    upsert_intelligence, read_latest_state, read_state_history,
    read_recent_changes, read_latest_intelligence, read_recent_snapshots,
    read_intelligence_by_id,
)
from .intelligence import (     # noqa: F401
    compute_market_intelligence, refresh_market_intelligence,
    reset_snapshot_cache,
)
from .change_detection import detect_structural_changes  # noqa: F401
from .brain_bridge import load_market_intelligence  # noqa: F401

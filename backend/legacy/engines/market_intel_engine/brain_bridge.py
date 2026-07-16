"""Phase G — Brain bridge.

Thin adapter that pulls the latest `MarketIntelligence` payload for a
(pair, timeframe) and exposes it in the shape the Adaptive Trading
Brain understands. Respects the two-step opt-in:
  * MI_ENABLED must be true
  * BRAIN_USES_MARKET_INTELLIGENCE must be true
When either is false, `load_market_intelligence` returns None and the
brain behaves byte-identically to Phase F.

An in-memory cache (populated by `intelligence.compute_market_intelligence`)
prevents hammering Mongo on every brain tick.
"""
from __future__ import annotations

import logging
from typing import Optional

from . import config as mcfg
from . import intelligence as _intel
from . import ledger
from .types import MarketIntelligence

logger = logging.getLogger(__name__)


async def load_market_intelligence(
    pair: str, timeframe: str,
) -> Optional[MarketIntelligence]:
    """Return the freshest MarketIntelligence for (pair, timeframe) or
    None if the switches are off / no data exists."""
    if not mcfg.mi_enabled():
        return None
    if not mcfg.brain_uses_market_intelligence():
        return None
    # In-memory cache first
    cached = _intel._cache_get(pair, timeframe)  # noqa: SLF001
    if cached is not None:
        return cached
    # Mongo fallback
    try:
        mi = await ledger.read_latest_intelligence(pair, timeframe)
        if mi is not None:
            _intel._cache_put(pair, timeframe, mi)  # noqa: SLF001
        return mi
    except Exception:  # noqa: BLE001
        logger.exception("load_market_intelligence failed (non-fatal)")
        return None

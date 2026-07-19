"""Canonical Timeframe Service (CTS) — Phase 2 Stage 2.ε / 2.ζ.

The single authoritative gateway for all historical candle access.
Every consumer — strategy generation, backtesting, portfolio, AI,
knowledge domains, future modules — obtains historical candles
through CTS rather than reading `market_data` directly.

Design principles baked in from line 1:
  * M1 canonical (source of truth); HTF derived on read
  * On-demand materialised cache (Option D from BID_CANDLE_STORAGE_REVIEW.md)
  * Event-driven invalidation (§10.1); time-based safety only
  * 3-axis sharding (symbol × timeframe × yyyy-mm) per §10.2
  * Traceability invariant (§10.5b, added 2026-02-19): every
    returned dataset MUST carry provenance metadata
  * Distribution-ready — Protocol + LocalCTS driver; γ+ swaps
    the storage backend

Public API (import from this package):
  Candle              — traceable single-candle dataclass
  CandleWindow        — full response envelope with provenance metadata
  Provenance          — traceability record attached to every window
  CanonicalTimeframeService — Protocol
  get_cts()           — singleton factory (respects `CTS_DRIVER`)
"""
from .types import (
    Candle,
    CandleWindow,
    DataQualityState,
    Provenance,
    RebuildReport,
    ResampleReport,
    VerificationReport,
)
from .service import CanonicalTimeframeService, get_cts, reset_cts_for_tests

__all__ = [
    "Candle",
    "CandleWindow",
    "CanonicalTimeframeService",
    "DataQualityState",
    "Provenance",
    "RebuildReport",
    "ResampleReport",
    "VerificationReport",
    "get_cts",
    "reset_cts_for_tests",
]

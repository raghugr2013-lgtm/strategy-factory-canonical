"""CTS type surface — Candle, CandleWindow, Provenance.

Traceability invariant (operator directive, 2026-02-19):
  Every dataset returned by CTS MUST identify:
    - canonical_source     (which storage produced the M1 rows)
    - aggregation_path     ("m1_native" | "m1_resampled_to_H1" | ...)
    - cache_generated_at   (when the HTF cache row was materialised)
    - cache_version        (schema version for future migrations)
    - repair_status        (was any gap-repair applied to this window?)
    - data_quality_state   (ok | degraded | reconstructed | stale)

This is the ONE shape every CTS consumer sees. No consumer reads
`market_data` directly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DataQualityState(str, Enum):
    OK             = "ok"                # every expected bar present + fresh
    DEGRADED       = "degraded"          # gaps present but ≤ tolerance
    RECONSTRUCTED  = "reconstructed"     # gaps repaired via provider back-fill
    STALE          = "stale"             # cache older than freshness bound
    UNKNOWN        = "unknown"           # no telemetry available (fresh boot)


CACHE_SCHEMA_VERSION = 1  # bump on breaking changes to cache row shape


@dataclass
class Provenance:
    """Traceability record for a CandleWindow.

    Every CTS response carries exactly one of these. Callers can log,
    persist, or forward it — it's the single source of truth for
    "where did this data come from and what happened to it?".
    """

    canonical_source:   str                     # e.g. "market_data.bid_1m"
    aggregation_path:   str                     # e.g. "m1_native" | "m1_resampled_to_H1"
    cache_generated_at: Optional[str] = None    # UTC ISO — None if not cached
    cache_version:      int = CACHE_SCHEMA_VERSION
    cache_bucket_key:   Optional[str] = None    # e.g. "EURUSD|H1|2026-02"
    repair_status:      str = "none"            # none | gaps_backfilled | manual_override
    data_quality_state: str = DataQualityState.UNKNOWN.value
    gap_count:          int = 0
    generated_at:       str = ""                # UTC ISO of THIS response
    cts_version:        str = "0.1.0"           # CTS module version

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat() + "+00:00"


@dataclass
class Candle:
    """One OHLCV bar. Simple and lightweight — provenance lives on the window."""

    timestamp: str          # UTC ISO
    open:      float
    high:      float
    low:       float
    close:     float
    volume:    float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open":      self.open,
            "high":      self.high,
            "low":       self.low,
            "close":     self.close,
            "volume":    self.volume,
        }


@dataclass
class CandleWindow:
    """The one shape every CTS caller receives.

    Traceability: every window carries a `Provenance` record. Callers
    that log the window MUST log the provenance too — otherwise the
    audit trail is broken.
    """

    symbol:     str
    timeframe:  str
    candles:    List[Candle]
    provenance: Provenance

    def is_empty(self) -> bool:
        return not self.candles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol":     self.symbol,
            "timeframe":  self.timeframe,
            "candles":    [c.to_dict() for c in self.candles],
            "count":      len(self.candles),
            "provenance": asdict(self.provenance),
        }


@dataclass
class ResampleReport:
    """Returned by CTS._resample() (internal diagnostic)."""

    input_rows:    int
    output_rows:   int
    duration_ms:   float
    from_tf:       str
    to_tf:         str


@dataclass
class RebuildReport:
    """Returned by CTS.rebuild_bucket() and force-rebuild admin calls."""

    symbol:            str
    timeframe:         str
    bucket_key:        str
    ok:                bool
    reason:            str
    input_rows:        int = 0
    output_rows:       int = 0
    duration_ms:       float = 0.0


@dataclass
class VerificationReport:
    """Returned by CTS.verify_against_provider() — advisory only, never
    triggers automatic corrections per §10.3 BID review."""

    symbol:                str
    timeframe:             str
    window_days:           int
    provider_bars_sampled: int
    ctsderived_bars:       int
    max_deviation_bps:     float
    tier:                  str    # informational | warning | governance_review
    ok:                    bool
    generated_at:          str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.utcnow().isoformat() + "+00:00"

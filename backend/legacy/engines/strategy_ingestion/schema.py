"""Unified ingested-strategy schema."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


ALLOWED_SOURCES = ("github", "tradingview", "mt5", "local")
ALLOWED_TYPES = (
    "trend_following",
    "mean_reversion",
    "breakout",
    "session_based",
    "volatility_based",
    "unknown",
)


class IngestedStrategy(BaseModel):
    """Canonical internal form produced by the ingestion pipeline."""

    name: str = Field(..., min_length=1, max_length=160)
    type: str = "unknown"
    indicators: List[str] = Field(default_factory=list)
    entry_logic: str = ""
    exit_logic: str = ""
    risk_model: str = ""
    timeframe: str = "H1"
    pair: str = "EURUSD"
    source: str = "local"
    raw_code: str = ""
    confidence: float = 0.0

    # Additive diagnostics (not in the user's base schema but useful):
    quality_score: Optional[float] = None
    rejection_reason: Optional[str] = None
    raw_source_url: Optional[str] = None

    def to_strategy_text(self) -> str:
        """Render in the format our existing strategy_engine emits so the
        mutation engine's text-wrap templates behave identically."""
        indicators_line = ", ".join(self.indicators) if self.indicators else "(none specified)"
        return (
            f"STRATEGY: {self.name}\n"
            f"TYPE: {self.type}\n"
            f"INDICATORS: {indicators_line}\n"
            f"ENTRY LONG: {self.entry_logic}\n"
            f"ENTRY SHORT: (mirror of long)\n"
            f"EXIT: {self.exit_logic}\n"
            f"RISK MODEL: {self.risk_model}\n"
            f"SOURCE: {self.source}"
        ).strip()

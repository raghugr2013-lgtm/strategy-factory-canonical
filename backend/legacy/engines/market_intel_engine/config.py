"""Phase G — env-driven configuration.

Every setting is read at call-time so operators can flip a switch and
have the running process pick it up on the next tick. No import-time
env captures except constants.
"""
from __future__ import annotations

import os
from typing import List, Tuple


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


def _bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on", "y"):
        return True
    if raw in ("0", "false", "no", "off", "n"):
        return False
    return bool(default)


def _csv(name: str, default: str) -> List[str]:
    raw = (os.environ.get(name) or default).strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


# ── Master switches ────────────────────────────────────────────────
def mi_enabled() -> bool:
    """Master switch — when False the ledger + observers + task all
    remain dormant. Defaults True (passive: harmless with weights=0)."""
    return _bool("MI_ENABLED", True)


def refresh_task_passive() -> bool:
    return _bool("MI_REFRESH_TASK_PASSIVE", False)


# ── Universe ───────────────────────────────────────────────────────
def mi_universe() -> List[str]:
    """Comma-separated list of pairs to observe. Fully dynamic — no
    hardcoding. Operator can point at Forex, Metals, Indices, Crypto,
    CFDs, etc."""
    return _csv("MI_UNIVERSE", "EURUSD,GBPUSD,USDJPY,XAUUSD")


def mi_timeframes() -> List[str]:
    return _csv("MI_TIMEFRAMES", "H1,H4,D1")


def mi_state_windows() -> List[str]:
    """Rolling windows tracked per (pair, timeframe)."""
    return _csv("MI_STATE_WINDOWS", "24h,7d,30d")


# ── Observer knobs ─────────────────────────────────────────────────
def observer_min_snapshots() -> int:
    return _int("MI_OBSERVER_MIN_SNAPSHOTS", 30)


def change_severity_min() -> float:
    return _float("MI_CHANGE_SEVERITY_MIN", 0.4)


def snapshot_ttl_days() -> int:
    return _int("MI_SNAPSHOT_TTL_DAYS", 30)


def snapshot_cache_ttl_seconds() -> int:
    """MarketIntelligence in-memory cache TTL — prevents hammering
    Mongo when the brain fires many ticks per minute (operator req)."""
    return _int("MI_INTELLIGENCE_CACHE_TTL_S", 60)


# ── Brain integration (two-step opt-in per operator refinement) ──
def brain_uses_market_intelligence() -> bool:
    """Second switch — brain does NOT read MI until this is true."""
    return _bool("BRAIN_USES_MARKET_INTELLIGENCE", False)


def w_market_confidence() -> float:
    return _float("BRAIN_W_MARKET_CONFIDENCE", 0.0)


def w_style_confidence() -> float:
    return _float("BRAIN_W_STYLE_CONFIDENCE", 0.0)


def w_opportunity() -> float:
    return _float("BRAIN_W_OPPORTUNITY", 0.0)


# ── Risk-first pause hook (OFF by default per Q5 operator ruling) ──
def brain_market_risk_pause_enabled() -> bool:
    """Even when the master switch is on, the market-driven force-pause
    remains OFF by default. Operator must explicitly opt in AFTER
    production validation."""
    return _bool("BRAIN_MARKET_RISK_PAUSE_ENABLED", False)


def market_risk_pause_threshold() -> float:
    return _float("BRAIN_MARKET_RISK_PAUSE_THRESHOLD", 0.20)


def market_style_min_confidence() -> float:
    return _float("BRAIN_MARKET_STYLE_MIN_CONFIDENCE", 0.25)


# ── Window durations in seconds (for TTL / freshness maths) ────────
_WINDOW_SECONDS = {
    "1h":  3600, "6h": 21600, "12h": 43200,
    "24h": 86400, "48h": 172800,
    "7d":  604800, "14d": 1209600, "30d": 2592000,
}


def window_seconds(window: str) -> int:
    return int(_WINDOW_SECONDS.get(window, 86400))


def config_snapshot() -> dict:
    """Debug helper — resolves every knob to its current value."""
    return {
        "MI_ENABLED":            mi_enabled(),
        "MI_UNIVERSE":           mi_universe(),
        "MI_TIMEFRAMES":         mi_timeframes(),
        "MI_STATE_WINDOWS":      mi_state_windows(),
        "MI_OBSERVER_MIN_SNAPSHOTS": observer_min_snapshots(),
        "MI_CHANGE_SEVERITY_MIN":    change_severity_min(),
        "MI_SNAPSHOT_TTL_DAYS":      snapshot_ttl_days(),
        "MI_INTELLIGENCE_CACHE_TTL_S": snapshot_cache_ttl_seconds(),
        "MI_REFRESH_TASK_PASSIVE":  refresh_task_passive(),
        "BRAIN_USES_MARKET_INTELLIGENCE": brain_uses_market_intelligence(),
        "BRAIN_W_MARKET_CONFIDENCE":  w_market_confidence(),
        "BRAIN_W_STYLE_CONFIDENCE":   w_style_confidence(),
        "BRAIN_W_OPPORTUNITY":        w_opportunity(),
        "BRAIN_MARKET_RISK_PAUSE_ENABLED": brain_market_risk_pause_enabled(),
        "BRAIN_MARKET_RISK_PAUSE_THRESHOLD": market_risk_pause_threshold(),
        "BRAIN_MARKET_STYLE_MIN_CONFIDENCE": market_style_min_confidence(),
    }

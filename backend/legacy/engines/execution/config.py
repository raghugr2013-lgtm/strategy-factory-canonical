"""Phase H — env-driven configuration.

Every setting is read at call-time so operators can flip a switch and
have the running process pick it up on the next tick. No import-time
env captures.

All defaults chosen so that a fresh boot with no `EXEC_*` env produces
byte-identical Phase G behaviour except that the execution engine is
now present as a passive observer (Paper broker default; brain does
NOT consume live execution measurements until explicitly enabled).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional


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


def _str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if (v is not None and v != "") else default


# ── Master switches ────────────────────────────────────────────────
def exec_enabled() -> bool:
    return _bool("EXEC_ENABLED", True)


def broker_name() -> str:
    """Q1: paper by default — live venue is always an explicit operator flip."""
    return _str("BROKER", "paper").strip().lower()


def broker_kill_switch() -> bool:
    return _bool("BROKER_KILL_SWITCH", False)


def default_account_id() -> str:
    """Q8: architected for multi-account; single-account impl for Phase H."""
    return _str("EXEC_DEFAULT_ACCOUNT_ID", "default")


# ── Two-step opt-in for brain integration ─────────────────────────
def live_measurement_enabled() -> bool:
    """Step 1: ledger measures live execution quality."""
    return _bool("EXEC_LIVE_MEASUREMENT", False)


def brain_uses_live_execution() -> bool:
    """Step 2: brain consumes measured-live execution quality."""
    return _bool("BRAIN_USES_LIVE_EXECUTION", False)


# ── Timeouts, cadences ────────────────────────────────────────────
def market_ack_timeout_ms() -> int:
    return _int("EXEC_MARKET_ACK_TIMEOUT_MS", 2000)


def attribution_interval_s() -> int:
    return _int("EXEC_ATTRIBUTION_INTERVAL_S", 300)


def health_interval_s() -> int:
    return _int("EXEC_HEALTH_INTERVAL_S", 60)


# ── Q4: rolling weighted broker-health windows ────────────────────
def health_windows() -> Dict[str, int]:
    """Short-term drives execution decisions; medium/long retained
    for historical context."""
    return {
        "short_s":  _int("EXEC_HEALTH_WINDOW_SHORT_S",  300),    # 5m
        "medium_s": _int("EXEC_HEALTH_WINDOW_MEDIUM_S", 3600),   # 1h
        "long_s":   _int("EXEC_HEALTH_WINDOW_LONG_S",   86400),  # 24h
    }


# ── Q3: risk thresholds — RECOMMEND only, never auto-liquidate ────
def risk_thresholds() -> Dict[str, float]:
    return {
        "max_positions":         float(_int("RISK_MAX_POSITIONS", 10)),
        "max_exposure_pair":     _float("RISK_MAX_EXPOSURE_PAIR", 100000.0),
        "max_exposure_total":    _float("RISK_MAX_EXPOSURE_TOTAL", 500000.0),
        "daily_loss_pct":        _float("RISK_DAILY_LOSS_PCT", 3.0),
        "loss_24h_pct":          _float("RISK_24H_LOSS_PCT", 5.0),
        "broker_health_min":     _float("RISK_BROKER_HEALTH_MIN", 0.30),
        "clock_drift_ms":        _float("RISK_CLOCK_DRIFT_MS", 200.0),
    }


# ── cTrader credentials (only used when BROKER=ctrader) ───────────
def broker_credentials() -> Dict[str, str]:
    return {
        "client_id":     _str("CTRADER_CLIENT_ID", ""),
        "client_secret": _str("CTRADER_CLIENT_SECRET", ""),
        "account_id":    _str("CTRADER_ACCOUNT_ID", ""),
        "host":          _str("CTRADER_HOST", "demo.ctraderapi.com"),
        "port":          _str("CTRADER_PORT", "5035"),
    }


# ── Paper broker knobs (deterministic replay for CI / dev) ────────
def paper_config() -> Dict[str, float]:
    return {
        "slippage_pips":    _float("PAPER_SLIPPAGE_PIPS", 0.2),
        "reject_rate":      _float("PAPER_REJECT_RATE", 0.0),
        "partial_rate":     _float("PAPER_PARTIAL_RATE", 0.0),
        "latency_ms":       _float("PAPER_LATENCY_MS", 20.0),
    }


# ── Live-spread bridge to Phase G ─────────────────────────────────
def live_spread_override_enabled() -> bool:
    return _bool("EXEC_LIVE_SPREAD_OVERRIDE", False)


# ── Debug helper ──────────────────────────────────────────────────
def exec_config_snapshot() -> Dict[str, Any]:
    return {
        "EXEC_ENABLED":                 exec_enabled(),
        "BROKER":                       broker_name(),
        "BROKER_KILL_SWITCH":           broker_kill_switch(),
        "EXEC_DEFAULT_ACCOUNT_ID":      default_account_id(),
        "EXEC_LIVE_MEASUREMENT":        live_measurement_enabled(),
        "BRAIN_USES_LIVE_EXECUTION":    brain_uses_live_execution(),
        "EXEC_MARKET_ACK_TIMEOUT_MS":   market_ack_timeout_ms(),
        "EXEC_ATTRIBUTION_INTERVAL_S":  attribution_interval_s(),
        "EXEC_HEALTH_INTERVAL_S":       health_interval_s(),
        "health_windows":               health_windows(),
        "risk_thresholds":              risk_thresholds(),
        "paper_config":                 paper_config(),
        "EXEC_LIVE_SPREAD_OVERRIDE":    live_spread_override_enabled(),
        "ctrader_configured": bool(broker_credentials().get("client_id")
                                    and broker_credentials().get("client_secret")),
    }

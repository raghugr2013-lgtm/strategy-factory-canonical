"""Production Validation Suite — configuration.

All settings read at call-time; overridable via env or CLI flags.
"""
from __future__ import annotations

import os
from pathlib import Path


def _s(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


BASE_URL = _s(
    "VALIDATION_BASE_URL",
    _s("REACT_APP_BACKEND_URL", "http://localhost:8001"),
).rstrip("/")

ADMIN_EMAIL     = _s("VALIDATION_ADMIN_EMAIL", "admin@strategy-factory.local")
ADMIN_PASSWORD  = _s("VALIDATION_ADMIN_PASSWORD", "admin123")

TIMEOUT_S       = _i("VALIDATION_TIMEOUT_S", 30)
SLOW_MS_WARN    = _i("VALIDATION_SLOW_MS_WARN", 2500)

REPORTS_DIR     = Path(_s("VALIDATION_REPORTS_DIR",
                          str(Path(__file__).parent / "reports")))

# Tier 5 defaults
TIER5_DURATION_HOURS   = _i("TIER5_DURATION_HOURS", 24)
TIER5_INTERVAL_SECONDS = _i("TIER5_INTERVAL_SECONDS", 300)  # 5 min


def config_snapshot() -> dict:
    return {
        "BASE_URL": BASE_URL,
        "ADMIN_EMAIL": ADMIN_EMAIL,
        "TIMEOUT_S": TIMEOUT_S,
        "SLOW_MS_WARN": SLOW_MS_WARN,
        "REPORTS_DIR": str(REPORTS_DIR),
        "TIER5_DURATION_HOURS": TIER5_DURATION_HOURS,
        "TIER5_INTERVAL_SECONDS": TIER5_INTERVAL_SECONDS,
    }

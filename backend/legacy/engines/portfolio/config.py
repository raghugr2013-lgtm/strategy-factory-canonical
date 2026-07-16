"""Phase D — shared env helpers + constants."""
from __future__ import annotations

import os


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


def max_style_share() -> float:
    return _float("PORTFOLIO_MAX_STYLE_SHARE", 0.35)


def correlation_max() -> float:
    return _float("PORTFOLIO_CORRELATION_MAX", 0.7)


def min_cash_reserve() -> float:
    return _float("PORTFOLIO_MIN_CASH_RESERVE", 0.10)


def drawdown_pause_pct() -> float:
    return _float("PORTFOLIO_DRAWDOWN_PAUSE_PCT", 12.0)


def drawdown_retire_pct() -> float:
    return _float("PORTFOLIO_DRAWDOWN_RETIRE_PCT", 25.0)


def confidence_min_active() -> float:
    return _float("PORTFOLIO_CONFIDENCE_MIN_ACTIVE", 0.4)


def pf_trend_window() -> int:
    return _int("PORTFOLIO_PF_TREND_WINDOW", 10)


def promotion_min_outcomes() -> int:
    return _int("PORTFOLIO_PROMOTION_MIN_OUTCOMES", 10)


def retirement_archive_after_days() -> int:
    return _int("PORTFOLIO_RETIREMENT_ARCHIVE_AFTER_DAYS", 30)


def rebuild_max_changes() -> int:
    return _int("PORTFOLIO_REBUILD_MAX_CHANGES", 5)

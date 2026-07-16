"""Phase J — env-driven configuration. Live-reload at call-time."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from .types import FEMode


def _f(name, default):
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _i(name, default):
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


def _b(name, default):
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on", "y"): return True
    if raw in ("0", "false", "no", "off", "n"): return False
    return bool(default)


def _s(name, default=""):
    v = os.environ.get(name)
    return v if (v is not None and v != "") else default


def mode() -> str:
    m = _s("FACTORY_EVAL_MODE", FEMode.OBSERVE).strip().lower()
    return m if FEMode.is_valid(m) else FEMode.OBSERVE


def cadence_sec() -> int:              return _i("FACTORY_EVAL_CADENCE_SEC", 3600)
def daily_report_hour() -> int:        return _i("FACTORY_EVAL_DAILY_REPORT_HOUR", 3)
def window_hours_short() -> int:       return _i("FACTORY_EVAL_WINDOW_HOURS_SHORT", 24)
def window_hours_long() -> int:        return _i("FACTORY_EVAL_WINDOW_HOURS_LONG", 2160)
def min_samples() -> int:              return _i("FACTORY_EVAL_MIN_SAMPLES", 30)
def sig_threshold() -> float:          return _f("FACTORY_EVAL_SIG_THRESHOLD", 0.20)
def max_delta_per_tick() -> float:     return _f("FACTORY_EVAL_MAX_DELTA_PER_TICK", 0.05)
def rec_ttl_days() -> int:             return _i("FACTORY_EVAL_REC_TTL_DAYS", 14)
def rank_floor() -> float:             return _f("FACTORY_EVAL_RANK_FLOOR", 0.01)


def autonomous_confirm() -> bool:
    return _s("FACTORY_EVAL_AUTONOMOUS_CONFIRM", "").strip().upper() == "YES"


def autonomous_whitelist() -> List[str]:
    raw = _s("FACTORY_EVAL_AUTONOMOUS_WHITELIST",
             "compute_reallocation,execution_path_pref").strip()
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def class_caps() -> Dict[str, float]:
    return {
        "compute_reallocation":     _f("FACTORY_EVAL_CAP_COMPUTE", 0.10),
        "budget_reallocation":      _f("FACTORY_EVAL_CAP_BUDGET", 0.10),
        "research_investment":      _f("FACTORY_EVAL_CAP_RESEARCH", 0.10),
        "strategy_pruning":         _f("FACTORY_EVAL_CAP_PRUNING", 0.10),
        "portfolio_rebalance_hint": _f("FACTORY_EVAL_CAP_PORTFOLIO_HINT", 0.10),
        "execution_path_pref":      _f("FACTORY_EVAL_CAP_EXEC_PATH", 0.10),
    }


# ── Downstream opt-in (all default false) ──────────────────────────
def use_overrides_orch() -> bool:      return _b("ORCH_USE_FACTORY_EVAL_OVERRIDES", False)
def use_overrides_exec() -> bool:      return _b("EXEC_USE_FACTORY_EVAL_OVERRIDES", False)
def use_overrides_learning() -> bool:  return _b("LEARNING_USE_FACTORY_EVAL_OVERRIDES", False)


def config_snapshot() -> Dict[str, Any]:
    return {
        "FACTORY_EVAL_MODE": mode(),
        "FACTORY_EVAL_CADENCE_SEC": cadence_sec(),
        "FACTORY_EVAL_DAILY_REPORT_HOUR": daily_report_hour(),
        "FACTORY_EVAL_WINDOW_HOURS_SHORT": window_hours_short(),
        "FACTORY_EVAL_WINDOW_HOURS_LONG": window_hours_long(),
        "FACTORY_EVAL_MIN_SAMPLES": min_samples(),
        "FACTORY_EVAL_SIG_THRESHOLD": sig_threshold(),
        "FACTORY_EVAL_MAX_DELTA_PER_TICK": max_delta_per_tick(),
        "FACTORY_EVAL_REC_TTL_DAYS": rec_ttl_days(),
        "FACTORY_EVAL_RANK_FLOOR": rank_floor(),
        "FACTORY_EVAL_AUTONOMOUS_CONFIRM": autonomous_confirm(),
        "FACTORY_EVAL_AUTONOMOUS_WHITELIST": autonomous_whitelist(),
        "FACTORY_EVAL_CLASS_CAPS": class_caps(),
        "ORCH_USE_FACTORY_EVAL_OVERRIDES": use_overrides_orch(),
        "EXEC_USE_FACTORY_EVAL_OVERRIDES": use_overrides_exec(),
        "LEARNING_USE_FACTORY_EVAL_OVERRIDES": use_overrides_learning(),
    }

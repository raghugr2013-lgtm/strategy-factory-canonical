"""Phase 2 Stage 4 P4B.7 — Budget hard-cap enforcement.

When the daily USD budget is exhausted, refuse all AGENT + LLM tasks
with HTTP 429 `budget_hard_cap_reached`. Soft-cap remains the
pre-existing warning surface (see `orchestrator/budget_tracker`).

Feature flag: `COE_BUDGET_HARD_CAP_ENABLED` (default OFF). When off,
`decide()` always returns `admit=True` — Stage-1..3 behaviour preserved.

Pure decision function. Compose with the admission gate via a single
call and honour the returned `admit=False`.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_budget_hard_cap_enabled() -> bool:
    return _flag("COE_BUDGET_HARD_CAP_ENABLED", False)


_LLM_GATED_CLASSES = frozenset({"agent", "backtest"})


@dataclass
class BudgetHardCapDecision:
    admit:            bool
    reason:           str
    workload_class:   str
    today_used_usd:   float                 = 0.0
    today_hard_cap:   float                 = 0.0
    headroom_usd:     float                 = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BudgetHardCap:
    """Composable hard-cap gate.

    Args:
        get_today_used_usd: `() → float` — current spent this day.
        get_today_hard_cap: `() → float` — daily budget ceiling.
    """

    def __init__(
        self,
        *,
        get_today_used_usd: Callable[[], float],
        get_today_hard_cap: Callable[[], float],
    ) -> None:
        self._used = get_today_used_usd
        self._cap = get_today_hard_cap

    def decide(self, *, workload_class: str) -> BudgetHardCapDecision:
        cls = (workload_class or "").lower()
        if not is_budget_hard_cap_enabled():
            return BudgetHardCapDecision(
                admit=True, reason="flag_off_pass_through",
                workload_class=cls,
            )
        if cls not in _LLM_GATED_CLASSES:
            return BudgetHardCapDecision(
                admit=True, reason="class_not_gated",
                workload_class=cls,
            )
        try:
            used = float(self._used())
            cap  = float(self._cap())
        except Exception:                                       # noqa: BLE001
            return BudgetHardCapDecision(
                admit=True, reason="lookup_failed_fail_open",
                workload_class=cls,
            )
        headroom = max(0.0, cap - used)
        if cap > 0 and used >= cap:
            return BudgetHardCapDecision(
                admit=False, reason="budget_hard_cap_reached",
                workload_class=cls,
                today_used_usd=used, today_hard_cap=cap, headroom_usd=0.0,
            )
        return BudgetHardCapDecision(
            admit=True, reason="ok",
            workload_class=cls,
            today_used_usd=used, today_hard_cap=cap, headroom_usd=headroom,
        )

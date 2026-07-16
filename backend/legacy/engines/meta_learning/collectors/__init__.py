"""Phase I — Collectors package.

Read-only helpers that pull specific outcome_event categories from the
Phase A ledger + Phase H attribution rows. Every collector returns a
list of plain dicts sorted newest-first — no side effects, no writes.
"""
from __future__ import annotations

from .brain_decisions import collect_brain_decisions   # noqa: F401
from .execution_realised import collect_execution_realised  # noqa: F401
from .market_intelligence import collect_market_intelligence  # noqa: F401
from .portfolio import collect_portfolio_events  # noqa: F401

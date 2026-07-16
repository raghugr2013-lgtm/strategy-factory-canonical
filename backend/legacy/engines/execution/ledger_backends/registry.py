"""Backend selection registry.

Precedence:
  1. Explicit `set_backend(backend)`
  2. `EXEC_LEDGER_BACKEND=memory|mongo` env
  3. Default: mongo
"""
from __future__ import annotations

import os
from typing import Optional

from .base import LedgerBackend
from .memory import MemoryLedgerBackend
from .mongo import MongoLedgerBackend


_ACTIVE: Optional[LedgerBackend] = None


def _from_env() -> LedgerBackend:
    name = (os.environ.get("EXEC_LEDGER_BACKEND") or "mongo").strip().lower()
    if name == "memory":
        return MemoryLedgerBackend()
    return MongoLedgerBackend()


def get_backend() -> LedgerBackend:
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = _from_env()
    return _ACTIVE


def set_backend(backend: LedgerBackend) -> None:
    """Explicit override. Used by the drill harness."""
    global _ACTIVE
    _ACTIVE = backend


def reset_backend() -> None:
    """Test hook — clears the cached selection so the next
    `get_backend()` re-reads env."""
    global _ACTIVE
    _ACTIVE = None


def active_backend_name() -> str:
    return getattr(get_backend(), "NAME", "unknown")

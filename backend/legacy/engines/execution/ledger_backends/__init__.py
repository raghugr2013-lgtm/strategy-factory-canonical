"""Phase H — Pluggable LedgerBackend interface.

Supports:

  * `MongoLedgerBackend`     — default, wraps `ledger.py` free functions
  * `MemoryLedgerBackend`    — in-memory dict, no I/O, deterministic
  * `ReplayLedgerBackend`    — (future, H11) read-only journal replay

Selection precedence:
  1. Explicit `set_backend(...)` in code
  2. `EXEC_LEDGER_BACKEND=memory|mongo` env
  3. Default: mongo
"""
from __future__ import annotations

from .base import LedgerBackend
from .memory import MemoryLedgerBackend
from .mongo import MongoLedgerBackend
from .registry import (
    get_backend, set_backend, reset_backend, active_backend_name,
)

__all__ = [
    "LedgerBackend", "MemoryLedgerBackend", "MongoLedgerBackend",
    "get_backend", "set_backend", "reset_backend", "active_backend_name",
]

"""Phase B.2 — Task registry.

Module-level singleton mapping `NAME → Task instance`. Tasks self-register at
import time via `registry.register(cls)`. Import order is enforced by
`engines.orchestrator.tasks.__init__`, which imports every task module.
"""
from __future__ import annotations

import logging
import os
from threading import RLock
from typing import Dict, List, Optional

from .types import Task

logger = logging.getLogger(__name__)


class _Registry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: Dict[str, Task] = {}

    def register(self, cls: type) -> type:
        """Class decorator — instantiates once, stores by `NAME`.

        Duplicate names log a warning and overwrite (last-import wins).
        """
        try:
            inst = cls()  # type: ignore[call-arg]
        except Exception as e:                                   # pragma: no cover
            logger.exception("orchestrator: task %s failed to instantiate: %s",
                             getattr(cls, "NAME", cls.__name__), e)
            return cls
        name = getattr(inst, "NAME", None)
        if not name or not isinstance(name, str):
            logger.error("orchestrator: task %s missing NAME — skipped", cls.__name__)
            return cls
        with self._lock:
            if name in self._tasks:
                logger.warning("orchestrator: task %s already registered — overwriting", name)
            self._tasks[name] = inst
        return cls

    def get(self, name: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(name)

    def all(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def names(self) -> List[str]:
        with self._lock:
            return sorted(self._tasks.keys())

    def clear(self) -> None:
        """Test-only — reset the registry between tests."""
        with self._lock:
            self._tasks.clear()

    # ── Env-driven per-task overrides ──────────────────────────────
    @staticmethod
    def is_passive_via_env(name: str, code_default: bool) -> bool:
        """Return True iff the task should be passive right now.

        Precedence:
          1. `ORCH_TASK_<NAME>_PASSIVE=true|false` (operator override)
          2. `code_default` (adapter's `PASSIVE` class attribute)
        """
        env_key = f"ORCH_TASK_{name.upper()}_PASSIVE"
        raw = (os.environ.get(env_key) or "").strip().lower()
        if raw in ("1", "true", "yes", "y", "on"):
            return True
        if raw in ("0", "false", "no", "n", "off"):
            return False
        return bool(code_default)

    @staticmethod
    def priority_base_via_env(name: str, code_default: float) -> float:
        env_key = f"ORCH_TASK_{name.upper()}_PRIORITY_BASE"
        raw = (os.environ.get(env_key) or "").strip()
        if not raw:
            return float(code_default)
        try:
            return float(raw)
        except ValueError:
            return float(code_default)


registry = _Registry()

"""Legacy code compatibility shim.

The v01 codebase used top-level imports like `from engines.strategy_engine
import ...`. After consolidation those files live under
`backend/legacy/engines/`. To keep the ~180 preserved import statements
working WITHOUT rewriting them, this shim aliases each legacy sub-package
into the top-level `sys.modules` namespace. Combined with the sys.path
insert in `backend/server.py`, both `import engines.X` and
`import legacy.engines.X` resolve to the same module object.

This aliasing is idempotent and safe to import multiple times.
"""

from __future__ import annotations

import importlib
import sys

_SUBPACKAGES = ("engines", "api", "cbot_engine", "data_engine", "scripts", "auth_utils", "config", "startup_validator")

for _sub in _SUBPACKAGES:
    try:
        _mod = importlib.import_module(f"legacy.{_sub}")
        sys.modules.setdefault(_sub, _mod)
    except ImportError:
        # sub-package may not exist yet in a slimmed-down bundle — ignore
        pass

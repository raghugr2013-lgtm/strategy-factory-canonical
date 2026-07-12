"""Preview/production entrypoint. Delegates to app.main which contains the
FastAPI application factory. Supervisor runs uvicorn against `server:app`.

This shim also installs the sys.path shim needed to make v01 legacy engines
importable under both `legacy.engines.X` and `engines.X` namespaces. The shim
is a no-op if legacy code is never referenced (Phase 0 disables the legacy
routers by default via ENABLE_LEGACY_ROUTERS=false).
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env")

# Make backend/legacy importable as both `legacy.X` (via package on disk) and
# top-level `X` (v01 style: `from engines.foo import bar`). This is required
# because the preserved legacy code was written when engines/ was top-level.
_LEGACY = _HERE / "legacy"
if _LEGACY.is_dir():
    p = str(_LEGACY)
    if p not in sys.path:
        sys.path.insert(0, p)

from app.main import app  # noqa: E402,F401

"""pytest shared fixtures for Phase 2 Stage 1 tests.

Provides a session-wide env-var scaffold so tests that import
`app.core.config` (which validates MONGO_URL/DB_NAME/JWT_SECRET at
Settings-load time) can run in isolation.

The .env file at /app/backend/.env is loaded automatically by uvicorn
at boot but not by pytest — hence this shim.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv_once() -> None:
    """Best-effort read of /app/backend/.env — never raises."""
    env_file = Path("/app/backend/.env")
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        # Do not overwrite anything already set by the test runner
        os.environ.setdefault(k, v)


_load_dotenv_once()

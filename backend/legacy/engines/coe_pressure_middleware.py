"""X-COE-Pressure response-header middleware.

Emits the current queue pressure band on every /api/* response when
`X_COE_PRESSURE_HEADER_ENABLED=true`. Consumers (frontend, external
callers) can throttle before hitting the admission gate.

Zero-cost when the flag is off — middleware detects and skips.
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


class CoePressureMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not _flag("X_COE_PRESSURE_HEADER_ENABLED", False):
            return response
        # Only stamp API responses
        if not request.url.path.startswith("/api/"):
            return response
        try:
            from engines import queue_pressure as _qp
            snap = _qp.snapshot() or {}
            band = str(snap.get("pressure_band") or "idle")
        except Exception:                                    # noqa: BLE001
            band = "unknown"
        response.headers["X-COE-Pressure"] = band
        return response

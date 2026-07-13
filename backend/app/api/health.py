from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.versioning import version_info
from app.db.mongo import get_db
from app.vie.client import VIEUnavailable, get_vie

router = APIRouter(prefix="/api", tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat(), **version_info()}


@router.get("/health/config")
async def health_config():
    """Secret-free configuration diagnostics (A-1). Presence/booleans only."""
    return get_settings().status()


async def _check_redis() -> dict:
    """Optional Redis check — configured via REDIS_URL env; if unset, skipped."""
    url = (os.environ.get("REDIS_URL") or "").strip()
    if not url:
        return {"status": "skipped", "detail": "REDIS_URL not configured"}
    try:
        # Import lazily so redis is not a hard requirement of the base image.
        import redis.asyncio as aioredis  # type: ignore
    except Exception:  # noqa: BLE001
        return {"status": "yellow", "detail": "redis client not installed"}
    try:
        client = aioredis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        pong = await client.ping()
        await client.aclose()
        return {"status": "green" if pong else "red", "detail": None}
    except Exception as e:  # noqa: BLE001
        return {"status": "red", "detail": str(e)[:200]}


@router.get("/readiness")
async def readiness():
    checks: dict = {}
    # Mongo
    try:
        db = get_db()
        await db.command("ping")
        checks["mongo"] = {"status": "green"}
    except Exception as e:  # noqa: BLE001
        checks["mongo"] = {"status": "red", "detail": str(e)[:200]}

    # VIE
    try:
        v = await get_vie().health()
        checks["vie"] = {"status": "green", "providers_available": v.get("providers_available", 0)}
    except VIEUnavailable as e:
        checks["vie"] = {"status": "yellow", "detail": f"vie unreachable: {e}"[:200]}
    except Exception as e:  # noqa: BLE001
        checks["vie"] = {"status": "red", "detail": str(e)[:200]}

    # Redis (optional)
    checks["redis"] = await _check_redis()

    # Aggregate — "skipped" is treated as green for the overall status.
    def _norm(s: str) -> str:
        return "green" if s == "skipped" else s

    statuses = [_norm(c["status"]) for c in checks.values()]
    overall = "green" if all(s == "green" for s in statuses) else (
        "red" if any(s == "red" for s in statuses) else "yellow"
    )
    return {"status": overall, "checks": checks, **version_info()}


@router.get("/version")
async def version():
    return version_info()

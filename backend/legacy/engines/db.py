"""Mongo connection helper.

Phase A.3 — connection pool tuning (env-driven, defaults conservative).

Reads:
  MONGO_URL         (required)
  DB_NAME           (required)
  MONGO_MAX_POOL    (default 200)
  MONGO_MIN_POOL    (default 20)
  MONGO_WAIT_MS     (default 2500)
  MONGO_SOCKET_MS   (default 30000)

The defaults are sized for the 12 vCPU / 32 GB target with one
FastAPI worker + one factory_runner sibling. Operators can tune
without code changes by setting the env vars.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient

_client = None
_db = None


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def get_db():
    global _client, _db
    if _db is None:
        mongo_url = os.environ.get("MONGO_URL")
        db_name = os.environ.get("DB_NAME")
        _client = AsyncIOMotorClient(
            mongo_url,
            maxPoolSize=_int_env("MONGO_MAX_POOL", 200),
            minPoolSize=_int_env("MONGO_MIN_POOL", 20),
            waitQueueTimeoutMS=_int_env("MONGO_WAIT_MS", 2500),
            socketTimeoutMS=_int_env("MONGO_SOCKET_MS", 30000),
            serverSelectionTimeoutMS=_int_env("MONGO_SRV_SEL_MS", 5000),
            retryWrites=True,
        )
        _db = _client[db_name]
    return _db

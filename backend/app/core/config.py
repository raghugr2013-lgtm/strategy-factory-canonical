"""Application configuration — all values from environment.

No defaults for security-sensitive fields; missing config fails fast.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


class Settings:
    def __init__(self) -> None:
        self.mongo_url: str = _required("MONGO_URL")
        self.db_name: str = _required("DB_NAME")
        self.jwt_secret: str = _required("JWT_SECRET")
        self.jwt_access_ttl_min: int = int(os.environ.get("JWT_ACCESS_TTL_MIN", "60"))
        self.jwt_refresh_ttl_days: int = int(os.environ.get("JWT_REFRESH_TTL_DAYS", "7"))
        self.admin_email: str = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        self.admin_password: str = os.environ.get("ADMIN_PASSWORD", "")
        self.cors_origins: List[str] = _parse_csv(os.environ.get("CORS_ORIGINS", "*"))
        self.vie_url: str = os.environ.get("VIE_URL", "http://127.0.0.1:8100").rstrip("/")
        self.vie_timeout_s: int = int(os.environ.get("VIE_TIMEOUT_S", "60"))
        self.build_version: str = os.environ.get("BUILD_VERSION", "0.0.0")
        self.build_commit: str = os.environ.get("BUILD_COMMIT", "unknown")
        self.build_date: str = os.environ.get("BUILD_DATE", "unknown")

        # Feature flags — Phase 0 defaults keep legacy dormant.
        self.enable_legacy_routers: bool = _bool_env("ENABLE_LEGACY_ROUTERS", False)
        self.enable_factory_runner: bool = _bool_env("ENABLE_FACTORY_RUNNER", False)
        self.enable_dynamic_market_universe: bool = _bool_env("ENABLE_DYNAMIC_MARKET_UNIVERSE", False)


def _required(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"required env var missing: {name}")
    return v


def _parse_csv(raw: str) -> List[str]:
    if not raw or raw.strip() == "*":
        return ["*"]
    return [s.strip() for s in raw.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Application configuration — all values from environment.

Single source of truth for the unified configuration contract (A-1).
Required variables fail fast at startup with one aggregated diagnostic;
`Settings.status()` exposes secret-free diagnostics for /api/health/config.
Full contract: docs/CONFIGURATION.md
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Dict, List

logger = logging.getLogger(__name__)

CONFIG_VERSION_DEFAULT = "1"

# Variables the backend refuses to start without.
REQUIRED_VARS = ("MONGO_URL", "DB_NAME", "JWT_SECRET")

# Recognized-but-optional variables (documented in docs/CONFIGURATION.md).
OPTIONAL_VARS = (
    "CONFIG_VERSION",
    "REDIS_URL",
    "JWT_ACCESS_TTL_MIN",
    "JWT_REFRESH_TTL_DAYS",
    "ADMIN_EMAIL",
    "ADMIN_PASSWORD",
    "CORS_ORIGINS",
    "VIE_URL",
    "VIE_TIMEOUT_S",
    "BUILD_VERSION",
    "BUILD_COMMIT",
    "BUILD_DATE",
    "ENABLE_LEGACY_ROUTERS",
    "ENABLE_FACTORY_RUNNER",
    "ENABLE_DYNAMIC_MARKET_UNIVERSE",
)

_JWT_MIN_LENGTH = 32
_KNOWN_DEV_JWT_SECRETS = frozenset(
    {
        "dev-only-insecure-jwt-secret-change-in-production",
        "dev-only-please-rotate-64-hex-string",
        "CHANGE_ME_TO_64_CHAR_HEX",
    }
)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


class Settings:
    def __init__(self) -> None:
        _validate_required()

        self.config_version: str = os.environ.get("CONFIG_VERSION", CONFIG_VERSION_DEFAULT).strip() or CONFIG_VERSION_DEFAULT
        self.mongo_url: str = os.environ["MONGO_URL"]
        self.db_name: str = os.environ["DB_NAME"]
        self.redis_url: str = (os.environ.get("REDIS_URL") or "").strip()
        self.jwt_secret: str = os.environ["JWT_SECRET"]
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

        self._warn_weak_jwt_secret()

    def _warn_weak_jwt_secret(self) -> None:
        if self.jwt_secret in _KNOWN_DEV_JWT_SECRETS:
            logger.warning(
                "JWT_SECRET is a known development default — rotate to a 64-char hex value before production use"
            )
        elif len(self.jwt_secret) < _JWT_MIN_LENGTH:
            logger.warning(
                "JWT_SECRET is shorter than %d characters — use a 64-char hex value in production",
                _JWT_MIN_LENGTH,
            )

    def status(self) -> Dict:
        """Secret-free configuration diagnostics (never returns secret values)."""
        return {
            "config_version": self.config_version,
            "required": {name: bool((os.environ.get(name) or "").strip()) for name in REQUIRED_VARS},
            "mongo": {"configured": bool(self.mongo_url), "db_name": self.db_name},
            "redis": {"configured": bool(self.redis_url)},
            "jwt": {
                "secret_set": bool(self.jwt_secret),
                "secret_is_dev_default": self.jwt_secret in _KNOWN_DEV_JWT_SECRETS,
                "secret_length_ok": len(self.jwt_secret) >= _JWT_MIN_LENGTH,
                "access_ttl_min": self.jwt_access_ttl_min,
                "refresh_ttl_days": self.jwt_refresh_ttl_days,
            },
            "admin": {"email_set": bool(self.admin_email), "password_set": bool(self.admin_password)},
            "cors": {"origins": self.cors_origins},
            "vie": {"url": self.vie_url, "timeout_s": self.vie_timeout_s},
            "build": {
                "version": self.build_version,
                "commit": self.build_commit,
                "date": self.build_date,
            },
            "flags": {
                "enable_legacy_routers": self.enable_legacy_routers,
                "enable_factory_runner": self.enable_factory_runner,
                "enable_dynamic_market_universe": self.enable_dynamic_market_universe,
            },
        }


def _validate_required() -> None:
    missing = [n for n in REQUIRED_VARS if not (os.environ.get(n) or "").strip()]
    if missing:
        raise RuntimeError(
            "missing required configuration: "
            + ", ".join(missing)
            + " — copy .env.example to .env (see docs/CONFIGURATION.md)"
        )


def _parse_csv(raw: str) -> List[str]:
    if not raw or raw.strip() == "*":
        return ["*"]
    return [s.strip() for s in raw.split(",") if s.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Build/version metadata surface."""
from __future__ import annotations

from typing import Dict

from app.core.config import get_settings


def version_info() -> Dict[str, str]:
    s = get_settings()
    return {
        "version": s.build_version,
        "commit": s.build_commit,
        "build_date": s.build_date,
        "service": "strategy-factory-backend",
    }

"""Phase 2 Stage 4 P4D.8 — Subsystem HealthSnapshot retrofits.

Additive `/api/<subsystem>/health` endpoints for the five subsystems
that don't yet have one. Every endpoint follows the same shape:

    {"subsystem": "<name>", "status": "opted_in" | "dormant" | "healthy",
     "flag_enabled": bool, "flag_name": "<flag>", "checked_at": iso,
     "notes": [...]}

Each is FLAG-GATED (HTTP 503 when off) so wiring is per-subsystem
opt-in during Coherent UKIE Activation. Existing subsystem diagnostic
endpoints are NEVER modified — this router is additive only.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SUBSYSTEMS: List[Dict[str, str]] = [
    {"name": "meta-learning", "flag": "META_LEARNING_HEALTH_PROVIDER_ENABLED"},
    {"name": "mi",            "flag": "MI_HEALTH_PROVIDER_ENABLED"},
    {"name": "execution",     "flag": "EXECUTION_HEALTH_PROVIDER_ENABLED"},
    {"name": "portfolio",     "flag": "PORTFOLIO_HEALTH_PROVIDER_ENABLED"},
    {"name": "factory-eval",  "flag": "FACTORY_EVAL_HEALTH_PROVIDER_ENABLED"},
]


router = APIRouter(tags=["health"])


def _make_snapshot(name: str, flag: str) -> Dict[str, Any]:
    enabled = _flag(flag, False)
    return {
        "subsystem":    name,
        "status":       "opted_in" if enabled else "dormant",
        "flag_enabled": enabled,
        "flag_name":    flag,
        "checked_at":   _now_iso(),
        "notes":        [
            "Stage-4 P4D scaffold — deeper subsystem checks wired at "
            "Coherent UKIE Activation time.",
        ],
    }


# Register one endpoint per subsystem
for _spec in SUBSYSTEMS:
    _name = _spec["name"]
    _flag_name = _spec["flag"]

    def _make_endpoint(name: str, flag_name: str):
        async def _endpoint() -> Dict[str, Any]:
            if not _flag(flag_name, False):
                raise HTTPException(status_code=503, detail=f"{flag_name} is off")
            return _make_snapshot(name, flag_name)
        _endpoint.__name__ = f"get_{name.replace('-', '_')}_health"
        return _endpoint

    router.add_api_route(
        f"/api/{_name}/health",
        _make_endpoint(_name, _flag_name),
        methods=["GET"],
        name=f"get_{_name.replace('-', '_')}_health",
    )

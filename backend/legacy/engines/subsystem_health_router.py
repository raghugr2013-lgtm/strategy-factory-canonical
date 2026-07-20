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


# ─────────────────────────────────────────────────────────────────────
# Phase 4 / Coherent UKIE Activation — aggregator wiring (W2).
#
# Each retrofit registers a HealthSnapshot provider with the central
# `/api/health/system` aggregator so an operator flipping
# `<SUB>_HEALTH_PROVIDER_ENABLED=true` sees the subsystem appear
# without any code change. When the flag is off the provider returns
# an `empty_snapshot()` marked `dormant` — health_score=100, state=OK.
# This preserves the "no data yet ≠ unhealthy" doctrine documented in
# engines/health/contract.py::empty_snapshot.
#
# Registration is best-effort. If the health-contract module is
# missing (e.g. Phase 2 Stage 1 not deployed) we simply skip
# registration; nothing else in this module changes.
# ─────────────────────────────────────────────────────────────────────
def _register_aggregator_providers() -> None:
    try:
        from engines.health.providers import register_provider
        from engines.health.contract import (
            ActionRequired,
            HealthSnapshot,
            RecoveryState,
            RecoveryStatus,
            empty_snapshot,
        )
    except Exception:                                          # pragma: no cover
        return

    def _make_provider(name: str, flag_name: str):
        def _provider() -> HealthSnapshot:
            enabled = _flag(flag_name, False)
            if not enabled:
                snap = empty_snapshot(name)
                snap.recovery_status = RecoveryStatus(
                    state=RecoveryState.OK,
                    reason="dormant",
                    action_required=ActionRequired.NONE,
                )
                return snap
            # Opted-in but no deeper telemetry yet — return a
            # baseline healthy snapshot. Real subsystem probes are
            # wired at Coherent UKIE Activation time.
            snap = empty_snapshot(name)
            snap.recovery_status = RecoveryStatus(
                state=RecoveryState.OK,
                reason="opted_in",
                action_required=ActionRequired.NONE,
            )
            return snap
        _provider.__name__ = f"{name.replace('-', '_')}_snapshot"
        return _provider

    for _spec in SUBSYSTEMS:
        register_provider(_spec["name"], _make_provider(_spec["name"], _spec["flag"]))


_register_aggregator_providers()

"""GET /api/latent/deployment-readiness — VPS commissioning health check.

Auth-gated. Read-only. Pure inspection — never writes, never mutates env.

Single endpoint the VPS operator can hit immediately after a fresh
install to verify the backend is correctly commissioned:

  * required env vars present
  * Mongo reachable
  * required collections accessible
  * P0 institutional invariants intact (all_dormant, legacy generator
    retired, structured error contract live)
  * Python version + supervisor process state

Returns an overall ``status: "ready" | "degraded" | "blocked"`` plus
per-check detail so the operator can decide whether to flip the
``ENABLE_AUTONOMOUS_FACTORY`` flag.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines.db import get_db
from startup_validator import REQUIRED_VARS, RECOMMENDED_VARS

router = APIRouter()


def _python_check() -> Dict[str, Any]:
    """Verify Python version is in the supported band."""
    py = platform.python_version_tuple()
    major, minor = int(py[0]), int(py[1])
    # 3.11+ required (we rely on PEP 654 exception groups + asyncio
    # behaviour that landed in 3.11).
    ok = (major, minor) >= (3, 11)
    return {
        "name":   "python_version",
        "ok":     ok,
        "value":  platform.python_version(),
        "required": ">=3.11",
        "detail": (
            "OK" if ok
            else "Python 3.11+ required — please upgrade the venv."
        ),
    }


def _env_check() -> Dict[str, Any]:
    """Verify required env vars are present (delegates to startup_validator)."""
    missing = [n for n in REQUIRED_VARS if not (os.environ.get(n) or "").strip()]
    missing_recommended = [
        n for n in RECOMMENDED_VARS if not (os.environ.get(n) or "").strip()
    ]
    return {
        "name":   "required_env_vars",
        "ok":     not missing,
        "missing_required":    missing,
        "missing_recommended": missing_recommended,
        "required_count":      len(REQUIRED_VARS),
        "detail": (
            "All required env vars present."
            if not missing
            else f"Missing required env vars: {', '.join(missing)}. "
                 "Backend cannot serve auth/LLM traffic until these are set."
        ),
    }


async def _mongo_check() -> Dict[str, Any]:
    """Verify Mongo is reachable + the configured DB exists."""
    db_name = os.environ.get("DB_NAME") or "<unset>"
    try:
        db = get_db()
        # Use a deterministic, lightweight admin command.
        ping = await db.command({"ping": 1})
        collections = await db.list_collection_names()
        ok = bool(ping.get("ok"))
        return {
            "name":              "mongo",
            "ok":                ok,
            "db_name":           db_name,
            "collection_count":  len(collections),
            "detail":            "Mongo reachable." if ok else "Mongo ping returned non-OK.",
        }
    except Exception as e:                                  # noqa: BLE001
        return {
            "name":   "mongo",
            "ok":     False,
            "db_name": db_name,
            "detail": f"Mongo unreachable: {str(e)[:300]}",
        }


def _supervisor_check() -> Dict[str, Any]:
    """Verify supervisor sees the backend in RUNNING state."""
    # Foreground-only; ~50ms budget.
    if not shutil.which("supervisorctl"):
        return {
            "name":   "supervisor",
            "ok":     False,
            "detail": "supervisorctl not in PATH",
        }
    try:
        out = subprocess.run(
            ["supervisorctl", "status", "backend"],
            capture_output=True, text=True, timeout=5,
        )
        line = (out.stdout or "").strip()
        running = "RUNNING" in line
        return {
            "name":   "supervisor",
            "ok":     running,
            "raw":    line,
            "detail": (
                "Supervisor reports backend RUNNING." if running
                else f"Supervisor backend state is not RUNNING: {line!r}"
            ),
        }
    except Exception as e:                                  # noqa: BLE001
        return {
            "name":   "supervisor",
            "ok":     False,
            "detail": f"supervisorctl probe failed: {str(e)[:200]}",
        }


async def _factory_runner_heartbeat_check() -> Dict[str, Any]:
    """Pass 16 — Non-blocking liveness check for the sibling factory_runner.

    Surfaces the silent-failure mode identified by the 2026-01 audit:
    when ``FACTORY_RUNNER_OWNS_SCHEDULERS=true`` the uvicorn backend
    defers all scheduler restoration to a sibling process. If that
    sibling is not running, schedulers are SILENTLY DORMANT — the
    previous readiness probe returned ``ready`` regardless.

    Mapping to readiness bands (intentionally NON-blocking — the
    readiness verdict moves to ``degraded`` but never ``blocked``,
    preserving rollback safety while breaking the silence):

      * verdict=alive          → ok=True
      * verdict=not_expected   → ok=True   (operator chose uvicorn-
                                             owned schedulers)
      * verdict=stale          → ok=False  (degraded)
      * verdict=dead           → ok=False  (degraded)
      * verdict=never_seen     → ok=False  (degraded — most common
                                             commissioning trap)
      * verdict=unknown        → ok=True   (Mongo blip; don't flip
                                             readiness on transient
                                             infra noise)
    """
    try:
        from engines.factory_runner_heartbeat import get_heartbeat_status
        payload = await get_heartbeat_status()
        verdict = payload.get("verdict")
        # ``ok`` follows the band above. ``unknown`` keeps ok=True so
        # transient Mongo errors don't oscillate the readiness verdict.
        ok = verdict in ("alive", "not_expected", "unknown")
        return {
            "name":               "factory_runner_heartbeat",
            "ok":                 ok,
            "verdict":            verdict,
            "owner_flag_active":  payload.get("owner_flag_active"),
            "age_seconds":        payload.get("age_seconds"),
            "cadence_sec":        payload.get("cadence_sec"),
            "last_heartbeat_at":  payload.get("last_heartbeat_at"),
            "detail":             payload.get("detail", ""),
        }
    except Exception as e:                                  # noqa: BLE001
        # Best-effort: if the heartbeat module itself fails, surface
        # an honest "could not be determined" without blocking.
        return {
            "name":   "factory_runner_heartbeat",
            "ok":     True,
            "verdict": "unknown",
            "detail": f"heartbeat probe error: {str(e)[:200]}",
        }


async def _p0_invariants_check() -> Dict[str, Any]:
    """Verify the P0 institutional invariants are intact."""
    # P0.1 — legacy generator must raise. We check the import surface
    # rather than the live HTTP route (this endpoint is server-internal).
    try:
        from cbot_engine.generator import (
            LegacyGeneratorRetiredError, generate_cbot_code,
        )
        try:
            await generate_cbot_code(_caller="deployment_readiness_probe")
            generator_loud = False
        except LegacyGeneratorRetiredError:
            generator_loud = True
    except Exception as e:                                  # noqa: BLE001
        return {
            "name":   "p0_invariants",
            "ok":     False,
            "detail": f"P0.1 import surface broken: {str(e)[:200]}",
        }
    # P0.2/P0.3 — scaffold helpers must be importable.
    try:
        from cbot_engine.ir_transpiler import transpile_ir_to_csharp  # noqa: F401
        scaffold_ok = True
    except Exception:                                       # noqa: BLE001
        scaffold_ok = False

    # Flag manifest — all_dormant must be True.
    try:
        from engines.feature_flags import all_flags
        flags = all_flags()
        any_overridden = any(
            f.get("value") != f.get("default") for f in flags.values()
        )
        all_dormant = not any_overridden
    except Exception:                                       # noqa: BLE001
        all_dormant = False

    ok = generator_loud and scaffold_ok and all_dormant
    return {
        "name":   "p0_invariants",
        "ok":     ok,
        "p0_1_legacy_generator_retired": generator_loud,
        "p0_2_3_scaffold_importable":    scaffold_ok,
        "all_dormant":                   all_dormant,
        "detail": (
            "P0 invariants intact." if ok
            else "One or more P0 invariants are violated."
        ),
    }


def _overall(checks: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Aggregate per-check verdicts into a single readiness band."""
    blocking_checks = ("required_env_vars", "mongo", "python_version", "p0_invariants")
    blocking_failures = [
        c["name"] for c in checks
        if c["name"] in blocking_checks and not c["ok"]
    ]
    if blocking_failures:
        return "blocked", (
            "Cannot proceed with deployment activation. Failing "
            f"blocking checks: {', '.join(blocking_failures)}."
        )
    any_failure = [c["name"] for c in checks if not c["ok"]]
    if any_failure:
        return "degraded", (
            "Backend serves traffic but at least one non-blocking "
            f"check is failing: {', '.join(any_failure)}."
        )
    return "ready", (
        "All readiness checks pass. Backend is institutionally cleared "
        "for VPS production operation. Flag activation remains the "
        "operator's authority."
    )


@router.get("/latent/deployment-readiness")
async def get_deployment_readiness(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = [
        _python_check(),
        _env_check(),
        await _mongo_check(),
        _supervisor_check(),
        await _factory_runner_heartbeat_check(),
        await _p0_invariants_check(),
    ]
    status, summary = _overall(checks)
    return {
        "endpoint":             "/api/latent/deployment-readiness",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "status":               status,    # "ready" | "degraded" | "blocked"
        "summary":              summary,
        "checks":               checks,
    }

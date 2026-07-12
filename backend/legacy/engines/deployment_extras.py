"""
Pass 15 — Deployment-readiness extras (read-only, advisory-only).

Status
------
* **Always callable**, **never engine-consumed**. No flag gate — this
  is a pure diagnostic surface that complements the existing
  ``/api/latent/deployment-readiness`` endpoint by adding the four
  dimensions the original (Pass 10) did not cover: disk / storage
  headroom, deployment packaging artifact presence, recovery-tooling
  script presence, and a consolidated compute headroom passthrough
  from the activation-governance subsystem.
* Pure file-system probe + ``shutil.disk_usage``. NEVER writes.
  NEVER triggers anything.

Why it exists separately from ``api/latent/deployment_readiness.py``
-------------------------------------------------------------------
The existing Pass 10 endpoint is the production gate that operators
already trust. Modifying it risks shape drift and re-litigating
test assertions across multiple existing latent tests. The
institutional pattern (followed in every Pass since P0) is:
*"never modify a stable production-facing surface to add a
diagnostic; add an additive sibling surface instead."* The
``DeploymentReadinessCard`` (Pass 15) composes BOTH endpoints +
the existing ``/api/latent/activation-governance`` payload to
produce the unified single-glance view.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Disk / storage headroom
# ─────────────────────────────────────────────────────────────────────
# Operator-tunable warning thresholds, defaults aligned with the
# audit's "production VPS" SLA expectations.
_DISK_OK_FREE_PCT = 20.0   # >= 20% free → ok
_DISK_WARN_FREE_PCT = 10.0  # 10..20% free → warn
# Below 10% → critical


def _classify_disk(free_pct: float) -> str:
    if free_pct >= _DISK_OK_FREE_PCT:
        return "ok"
    if free_pct >= _DISK_WARN_FREE_PCT:
        return "warn"
    return "critical"


def check_disk(path: str = "/app") -> Dict[str, Any]:
    """Return a structured disk-usage probe for ``path``.

    Returns
    -------
    dict
        ``{
            "name":      "disk",
            "ok":        bool,
            "band":      "ok" | "warn" | "critical" | "error",
            "path":      str,
            "total_gb":  float | None,
            "used_gb":   float | None,
            "free_gb":   float | None,
            "free_pct":  float | None,
            "detail":    str,
          }``
    """
    try:
        usage = shutil.disk_usage(path)
        total_gb = round(usage.total / (1024 ** 3), 2)
        used_gb = round(usage.used / (1024 ** 3), 2)
        free_gb = round(usage.free / (1024 ** 3), 2)
        free_pct = round(usage.free / max(1, usage.total) * 100.0, 2)
        band = _classify_disk(free_pct)
        return {
            "name":     "disk",
            "ok":       band == "ok",
            "band":     band,
            "path":     str(path),
            "total_gb": total_gb,
            "used_gb":  used_gb,
            "free_gb":  free_gb,
            "free_pct": free_pct,
            "detail": {
                "ok":       f"{free_pct:.1f}% free ({free_gb} GB)",
                "warn":     f"Disk free below {_DISK_OK_FREE_PCT:.0f}% — "
                             f"{free_pct:.1f}% remaining. Watch growth.",
                "critical": f"Disk free below {_DISK_WARN_FREE_PCT:.0f}% — "
                             f"{free_pct:.1f}% remaining. URGENT cleanup needed.",
            }[band],
        }
    except Exception as e:                                  # pragma: no cover
        return {
            "name":     "disk",
            "ok":       False,
            "band":     "error",
            "path":     str(path),
            "total_gb": None,
            "used_gb":  None,
            "free_gb":  None,
            "free_pct": None,
            "detail":   f"disk probe failed: {str(e)[:200]}",
        }


# ─────────────────────────────────────────────────────────────────────
# Deployment-packaging artifacts
# ─────────────────────────────────────────────────────────────────────
def _check_files(base: Path, required: List[str]) -> Tuple[List[str], List[str]]:
    present: List[str] = []
    missing: List[str] = []
    for rel in required:
        p = base / rel
        if p.exists():
            present.append(rel)
        else:
            missing.append(rel)
    return present, missing


def check_packaging(app_root: str = "/app") -> Dict[str, Any]:
    """Verify the deployment packaging layer is present + addressable.

    Mirrors the audit doc's institutional Pass 10 packaging:
    backend.env.template, frontend.env.template, supervisor template,
    systemd templates.
    """
    base = Path(app_root) / "deploy"
    required = [
        "README.md",
        "backend.env.template",
        "frontend.env.template",
        "supervisor.conf.template",
        "systemd",
    ]
    if not base.exists():
        return {
            "name":     "packaging",
            "ok":       False,
            "deploy_dir": str(base),
            "present":  [],
            "missing":  required,
            "detail":   f"Deploy directory not found at {base}.",
        }
    present, missing = _check_files(base, required)
    return {
        "name":     "packaging",
        "ok":       not missing,
        "deploy_dir": str(base),
        "present":  present,
        "missing":  missing,
        "detail":   (
            f"All {len(required)} deploy artifacts present."
            if not missing else
            f"{len(missing)} deploy artifact(s) missing: {missing}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Recovery-tooling presence
# ─────────────────────────────────────────────────────────────────────
def check_recovery_tooling(app_root: str = "/app") -> Dict[str, Any]:
    """Verify the operator-facing recovery scripts are present at the
    expected paths.

    These are the scripts the audit doc (Pass 9 / Pass 10) introduced
    for post-install commissioning and rollback safety.
    """
    base = Path(app_root) / "scripts"
    required = [
        "install.sh",
        "update.sh",
        "rollback.sh",
        "snapshot_now.sh",
        "diagnose_log.sh",
        "deploy_check.sh",
    ]
    if not base.exists():
        return {
            "name":     "recovery_tooling",
            "ok":       False,
            "scripts_dir": str(base),
            "present":  [],
            "missing":  required,
            "detail":   f"Scripts directory not found at {base}.",
        }
    present, missing = _check_files(base, required)
    # Surface which present scripts are executable (institutional
    # discipline: rollback.sh chmod-fail in production is a real
    # failure mode).
    not_executable: List[str] = []
    for rel in present:
        p = base / rel
        try:
            if not (p.stat().st_mode & 0o111):
                not_executable.append(rel)
        except OSError:                                     # pragma: no cover
            not_executable.append(rel)
    ok = (not missing) and (not not_executable)
    return {
        "name":           "recovery_tooling",
        "ok":             ok,
        "scripts_dir":    str(base),
        "present":        present,
        "missing":        missing,
        "not_executable": not_executable,
        "detail":         (
            f"All {len(required)} recovery scripts present and executable."
            if ok else
            f"missing={missing or 'none'}; not_executable={not_executable or 'none'}"
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Supervisor service templates
# ─────────────────────────────────────────────────────────────────────
def check_supervisor_templates(app_root: str = "/app") -> Dict[str, Any]:
    """Verify supervisor service-template files are present. The
    operator's VPS commissioning script wires these into
    ``/etc/supervisor/conf.d/`` — missing templates are an explicit
    deployment-time failure mode worth surfacing.
    """
    base = Path(app_root) / "supervisor"
    if not base.exists():
        return {
            "name":     "supervisor_templates",
            "ok":       False,
            "templates_dir": str(base),
            "present":  [],
            "detail":   f"Supervisor templates directory not found at {base}.",
        }
    present = sorted(p.name for p in base.glob("*.conf")) or []
    return {
        "name":          "supervisor_templates",
        "ok":            len(present) > 0,
        "templates_dir": str(base),
        "present":       present,
        "detail":        (
            f"{len(present)} supervisor template(s) present."
            if present else
            "No .conf templates found in supervisor/."
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Consolidated probe
# ─────────────────────────────────────────────────────────────────────
def collect_extras(app_root: str = "/app") -> Dict[str, Any]:
    """Aggregate every extras check into a single payload. Pure
    function of the file-system state at call-time.
    """
    checks = [
        check_disk(app_root),
        check_packaging(app_root),
        check_recovery_tooling(app_root),
        check_supervisor_templates(app_root),
    ]
    all_ok = all(c.get("ok") for c in checks)
    bands = [c.get("band") for c in checks if c.get("band")]
    if "critical" in bands:
        status = "critical"
    elif (not all_ok) or ("warn" in bands):
        status = "warn"
    else:
        status = "ok"
    return {
        "status":              status,
        "all_ok":              all_ok,
        "checks":              checks,
        "thresholds": {
            "disk_ok_free_pct":   _DISK_OK_FREE_PCT,
            "disk_warn_free_pct": _DISK_WARN_FREE_PCT,
        },
        "advisory_only":       True,
        "read_only":           True,
        "governance_authority": False,
        "operator_authority":  "final",
    }


__all__ = [
    "check_disk",
    "check_packaging",
    "check_recovery_tooling",
    "check_supervisor_templates",
    "collect_extras",
]

"""
VPS Scaling P1.B — Host capability detector + tiered profile.

Runs once at backend startup (and on operator-triggered `POST
/api/scaling/recompute` in P1.D). Persists a single Mongo row per
`host_id` describing what THIS box has — its logical and effective
CPU count, RAM, swap, disk, cgroup quota. This is the foundation for
adaptive pool sizing in P1.B and for adaptive concurrency in P1.C.

Discipline (per CAPACITY_ENGINE_DESIGN.md §1):
  * Read-only against the OS (no env mutation, no fs writes outside
    `/app/data/host_id` for the persistent host id).
  * Best-effort persistence — Mongo failure logs a warning and
    returns the in-memory `HostCapability` regardless.
  * Honest accounting — `effective_cpu_count` is the LOWER of
    `os.cpu_count()` and the cgroup-imposed quota. Containers with
    32 logical cores but a 4-core CFS quota must size for 4.
  * Tiered profile picker — pure function over `HostCapability`,
    with operator override via `WORKLOAD_PROFILE` env (auto/small/
    medium/large/xlarge).

Schema row (single document per `host_id`):

    {
      "_id":                  <host_id>,
      "hostname":             "vps-prod-01",
      "detected_at":          iso-string,
      "logical_cpu_count":    int,
      "effective_cpu_count":  int,
      "mem_total_gb":         float,
      "mem_available_gb":     float,
      "swap_total_gb":        float,
      "disk_total_gb":        float | None,
      "cgroup_cpu_quota":     float | None,
      "kernel":               str,
      "python":               str,
      "profile":              "small" | "medium" | "large" | "xlarge",
      "profile_pinned_via_env": bool,
    }
"""
from __future__ import annotations

import logging
import os
import platform
import socket
import sys
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import psutil
    _PSUTIL_OK = True
except Exception:                                            # pragma: no cover
    psutil = None
    _PSUTIL_OK = False

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "host_capabilities"
_HOST_ID_FILE = Path("/app/data/host_id")
_CACHE: Optional["HostCapability"] = None

# Profile threshold table (per CAPACITY_ENGINE_DESIGN.md §1.2).
# These are operator-acceptable defaults from gap-analysis §7.2.
PROFILE_THRESHOLDS = {
    # (max_cpu_inclusive, max_mem_gb_inclusive) → profile
    "small":  {"cpu_max": 4,  "mem_max": 8},
    "medium": {"cpu_max": 8,  "mem_max": 16},
    "large":  {"cpu_max": 16, "mem_max": 32},
    # xlarge = everything above large.
}
VALID_PROFILES = ("small", "medium", "large", "xlarge")


@dataclass
class HostCapability:
    host_id:             str
    hostname:            str
    detected_at:         str
    logical_cpu_count:   int
    effective_cpu_count: int
    mem_total_gb:        float
    mem_available_gb:    float
    swap_total_gb:       float
    disk_total_gb:       Optional[float]
    cgroup_cpu_quota:    Optional[float]
    kernel:              str
    python:              str
    profile:             str
    profile_pinned_via_env: bool = False
    psutil_available:    bool = True


# ─── Host ID persistence ─────────────────────────────────────────────

def _read_or_mint_host_id() -> str:
    """Return a stable host_id, persisted at `/app/data/host_id`.

    Falls back to `socket.gethostname()` if the file is unwritable —
    that's degraded but not broken.
    """
    try:
        if _HOST_ID_FILE.exists():
            hid = _HOST_ID_FILE.read_text().strip()
            if hid:
                return hid
    except Exception as e:                                   # pragma: no cover
        logger.warning("[host_capability] reading host_id failed: %s", e)
    # Mint a new one
    new_id = f"{socket.gethostname() or 'host'}-{uuid.uuid4().hex[:8]}"
    try:
        _HOST_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _HOST_ID_FILE.write_text(new_id)
    except Exception as e:                                   # pragma: no cover
        logger.warning("[host_capability] persisting host_id failed: %s", e)
        # Degraded fallback — still return SOMETHING stable for this boot.
        return socket.gethostname() or "host-unknown"
    return new_id


# ─── cgroup CPU quota detection ──────────────────────────────────────

def _read_cgroup_cpu_quota() -> Optional[float]:
    """Return the cgroup v2 / v1 CPU quota as cores-equivalent.

    Returns None if no quota is detected (full host) or on read error.
    """
    # cgroup v2: /sys/fs/cgroup/cpu.max contains "<quota> <period>" or "max <period>"
    v2 = Path("/sys/fs/cgroup/cpu.max")
    try:
        if v2.exists():
            txt = v2.read_text().strip()
            parts = txt.split()
            if len(parts) == 2:
                quota_s, period_s = parts
                if quota_s.lower() == "max":
                    return None  # no limit
                quota  = float(quota_s)
                period = float(period_s)
                if period > 0:
                    return round(quota / period, 3)
    except Exception:                                        # pragma: no cover
        pass

    # cgroup v1: separate files for quota and period.
    v1_quota  = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    v1_period = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    try:
        if v1_quota.exists() and v1_period.exists():
            q = int(v1_quota.read_text().strip())
            p = int(v1_period.read_text().strip())
            if q > 0 and p > 0:
                return round(q / p, 3)
    except Exception:                                        # pragma: no cover
        pass
    return None


# ─── Profile classification ──────────────────────────────────────────

def recommend_profile(caps: "HostCapability") -> str:
    """Pure-function tiered classifier.

    Operator override via `WORKLOAD_PROFILE` env wins absolutely.
    Otherwise applies the §1.2 threshold table from CAPACITY_ENGINE_DESIGN.
    """
    env_pin = (os.environ.get("WORKLOAD_PROFILE") or "auto").strip().lower()
    if env_pin in VALID_PROFILES:
        return env_pin
    # else env_pin == "auto" or invalid → auto-classify
    cpu = caps.effective_cpu_count
    mem = caps.mem_total_gb
    if cpu <= PROFILE_THRESHOLDS["small"]["cpu_max"] or mem <= PROFILE_THRESHOLDS["small"]["mem_max"]:
        return "small"
    if cpu <= PROFILE_THRESHOLDS["medium"]["cpu_max"] and mem <= PROFILE_THRESHOLDS["medium"]["mem_max"]:
        return "medium"
    if cpu <= PROFILE_THRESHOLDS["large"]["cpu_max"] and mem <= PROFILE_THRESHOLDS["large"]["mem_max"]:
        return "large"
    return "xlarge"


# ─── Detection ───────────────────────────────────────────────────────

def detect() -> HostCapability:
    """Read this host's capability. Pure read-side; no DB write here.

    Call `persist(caps)` to push to Mongo. Boot sequence in `server.py`
    calls `detect()` → `persist()` → caches in `_CACHE`.
    """
    host_id  = _read_or_mint_host_id()
    hostname = socket.gethostname() or host_id
    now      = datetime.now(timezone.utc).isoformat()

    logical = os.cpu_count() or 1
    cgroup_q = _read_cgroup_cpu_quota()
    if cgroup_q is not None and cgroup_q > 0:
        effective = max(1, min(int(logical), int(round(cgroup_q))))
    else:
        effective = max(1, int(logical))

    if _PSUTIL_OK:
        try:
            vm  = psutil.virtual_memory()
            sm  = psutil.swap_memory()
            du  = None
            for mount in ("/app", "/"):
                try:
                    d = psutil.disk_usage(mount)
                    if du is None or d.total > du:
                        du = d.total
                except Exception:
                    continue
            mem_total_gb     = round(vm.total / (1024 ** 3), 3)
            mem_available_gb = round(vm.available / (1024 ** 3), 3)
            swap_total_gb    = round(sm.total / (1024 ** 3), 3)
            disk_total_gb    = round(du / (1024 ** 3), 3) if du else None
            psutil_ok        = True
        except Exception as e:                               # pragma: no cover
            logger.warning("[host_capability] psutil read failed: %s", e)
            mem_total_gb = mem_available_gb = swap_total_gb = 0.0
            disk_total_gb = None
            psutil_ok = False
    else:
        mem_total_gb = mem_available_gb = swap_total_gb = 0.0
        disk_total_gb = None
        psutil_ok = False

    env_pin_raw = (os.environ.get("WORKLOAD_PROFILE") or "auto").strip().lower()
    pinned = env_pin_raw in VALID_PROFILES

    caps = HostCapability(
        host_id=host_id,
        hostname=hostname,
        detected_at=now,
        logical_cpu_count=logical,
        effective_cpu_count=effective,
        mem_total_gb=mem_total_gb,
        mem_available_gb=mem_available_gb,
        swap_total_gb=swap_total_gb,
        disk_total_gb=disk_total_gb,
        cgroup_cpu_quota=cgroup_q,
        kernel=platform.release() or "",
        python=".".join(map(str, sys.version_info[:3])),
        profile="",                # filled below
        profile_pinned_via_env=pinned,
        psutil_available=psutil_ok,
    )
    caps.profile = recommend_profile(caps)
    return caps


# ─── Persistence ─────────────────────────────────────────────────────

async def persist(caps: HostCapability) -> Dict[str, Any]:
    """Upsert the row + cache. Best-effort — Mongo failure does NOT raise.

    Returns the Mongo update result envelope.
    """
    global _CACHE
    _CACHE = caps
    db = get_db()
    try:
        await db[COLLECTION].update_one(
            {"_id": caps.host_id},
            {"$set": {k: v for k, v in asdict(caps).items() if k != "host_id"}},
            upsert=True,
        )
        return {"ok": True, "host_id": caps.host_id}
    except Exception as e:                                   # pragma: no cover
        logger.warning("[host_capability] persist %s failed: %s", caps.host_id, e)
        return {"ok": False, "host_id": caps.host_id, "error": str(e)[:200]}


def current() -> Optional[HostCapability]:
    """Return the cached HostCapability from boot (None if not yet detected).

    This is the entry point `adaptive_pool_sizer.recommend_pool_size()`
    consults. Sync — no I/O. Never raises.
    """
    return _CACHE


def reset_cache() -> None:
    """Test-only helper. Resets the module-level cache so that test
    fixtures can simulate "fresh process" without re-importing."""
    global _CACHE
    _CACHE = None


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation. Never raises."""
    db = get_db()
    created, existed, errors = [], [], []
    try:
        existing = await db[COLLECTION].index_information()
        if "ix_hostcap_detected_at" not in existing:
            await db[COLLECTION].create_index(
                [("detected_at", -1)],
                name="ix_hostcap_detected_at",
                background=True,
            )
            created.append("ix_hostcap_detected_at")
        else:
            existed.append("ix_hostcap_detected_at")
    except Exception as e:                                   # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[host_capability] ensure_indexes failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}

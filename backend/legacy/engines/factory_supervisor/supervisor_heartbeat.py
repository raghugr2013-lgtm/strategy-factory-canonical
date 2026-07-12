"""
Factory Supervisor FS-P1.0 — Heartbeat + verdict bands.

Persists `factory_supervisor_heartbeats` rows so the operator can ask
"is the Supervisor alive?" without leaving the system. Verdict bands
**reuse the `factory_runner_heartbeat` vocabulary verbatim** so operators
learn ONE band language across the platform.

Verdict bands (mirrors engines.factory_runner_heartbeat.VERDICT_*):
    * alive       — heartbeat fresher than 2× cadence
    * stale       — between 2× and 4× cadence
    * dead        — older than 4× cadence OR never seen with flag ON
    * never_seen  — collection empty + flag ON
    * not_expected— flag OFF (Supervisor not running here)
    * unknown     — Mongo blip / cannot read

Schema (`factory_supervisor_heartbeats` — append-only, one row per emit):
    {
        "_id":               ObjectId,
        "host_id":           "<host>",
        "hostname":          "<vps-build-01>",
        "ts":                iso,
        "ts_epoch":          float,
        "is_leader":         bool,
        "process_pid":       int,
        "payload":           {<free-form: queue depths, routed counts, ...>},
        "supervisor_version":"FS-P1.0",
    }

Discipline:
  * Best-effort writes. Mongo blip → False, never raises.
  * Append-only by design — the verdict aggregator looks at the most
    recent row per host_id.
  * DORMANT until `ENABLE_FACTORY_SUPERVISOR=true`. `is_enabled()`
    short-circuits emit when the master flag is OFF.

Public surface:
    SUPERVISOR_VERSION
    VERDICT_ALIVE / VERDICT_STALE / VERDICT_DEAD
    VERDICT_NEVER_SEEN / VERDICT_NOT_EXPECTED / VERDICT_UNKNOWN
    DEFAULT_CADENCE_SEC
    ensure_indexes()
    is_enabled()
    emit(host_id, payload=None, is_leader=False)  → bool
    latest(host_id)                                → dict|None
    verdict_band(host_id, cadence_sec=None)        → str
    list_recent(limit=50)                          → List[dict]
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION = "factory_supervisor_heartbeats"
SUPERVISOR_VERSION = "FS-P1.0"

# Reuse the band vocabulary verbatim from factory_runner_heartbeat.
VERDICT_ALIVE        = "alive"
VERDICT_STALE        = "stale"
VERDICT_DEAD         = "dead"
VERDICT_NEVER_SEEN   = "never_seen"
VERDICT_NOT_EXPECTED = "not_expected"
VERDICT_UNKNOWN      = "unknown"

DEFAULT_CADENCE_SEC = 30
_HISTORY_KEEP_DAYS  = 7  # TTL hint; not enforced by index in FS-P1.0


def _now() -> Dict[str, Any]:
    dt = datetime.now(timezone.utc)
    return {"iso": dt.isoformat(), "epoch": dt.timestamp()}


def is_enabled() -> bool:
    """Mirror of the master Factory Supervisor flag."""
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_FACTORY_SUPERVISOR"))
    except KeyError:
        return False
    except Exception:                                          # pragma: no cover
        return False


def _resolve_cadence(cadence_sec: Optional[int]) -> int:
    if cadence_sec is not None:
        try:
            return max(5, min(int(cadence_sec), 600))
        except (TypeError, ValueError):
            pass
    raw = (os.environ.get("FS_HEARTBEAT_CADENCE_SEC") or "").strip()
    if raw:
        try:
            return max(5, min(int(raw), 600))
        except ValueError:
            pass
    return DEFAULT_CADENCE_SEC


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation. Never raises."""
    created, existed, errors = [], [], []
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[COLLECTION].index_information()
        specs = [
            ("ix_fs_heartbeat_host_ts",
             [("host_id", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_fs_heartbeat_ts",
             [("ts_epoch", DESCENDING)]),
        ]
        for name, keys in specs:
            if name in existing:
                existed.append(name)
                continue
            await db[COLLECTION].create_index(keys, name=name, background=True)
            created.append(name)
    except Exception as e:                                     # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[supervisor_heartbeat] ensure_indexes failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}


def _local_host_meta() -> Dict[str, str]:
    try:
        from engines import host_capability
        caps = host_capability.current()
        if caps is not None:
            return {"host_id": caps.host_id, "hostname": caps.hostname}
    except Exception:                                          # pragma: no cover
        pass
    hn = os.environ.get("HOSTNAME") or "unknown"
    return {"host_id": hn, "hostname": hn}


async def emit(
    host_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    is_leader: bool = False,
) -> bool:
    """Append one heartbeat row. No-op when ENABLE_FACTORY_SUPERVISOR is OFF.

    Returns True iff the write reached Mongo.
    """
    if not is_enabled():
        return False
    meta = _local_host_meta()
    if not host_id:
        host_id = meta["host_id"]
    times = _now()
    doc: Dict[str, Any] = {
        "host_id":            host_id,
        "hostname":           meta["hostname"],
        "ts":                 times["iso"],
        "ts_epoch":           times["epoch"],
        "is_leader":          bool(is_leader),
        "process_pid":        os.getpid(),
        "payload":            dict(payload or {}),
        "supervisor_version": SUPERVISOR_VERSION,
    }
    try:
        from engines.db import get_db
        db = get_db()
        await db[COLLECTION].insert_one(doc)
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_heartbeat] emit failed: %s", e)
        return False


async def latest(host_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the most recent heartbeat row for `host_id`. None if none."""
    if not host_id:
        host_id = _local_host_meta()["host_id"]
    try:
        from engines.db import get_db
        from pymongo import DESCENDING
        db = get_db()
        doc = await db[COLLECTION].find_one(
            {"host_id": host_id},
            {"_id": 0},
            sort=[("ts_epoch", DESCENDING)],
        )
        return doc
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_heartbeat] latest failed: %s", e)
        return None


async def list_recent(limit: int = 50) -> List[Dict[str, Any]]:
    """Diagnostic list. Returns [] on Mongo blip."""
    limit = max(1, min(int(limit), 500))
    try:
        from engines.db import get_db
        from pymongo import DESCENDING
        db = get_db()
        cur = db[COLLECTION].find({}, {"_id": 0}).sort("ts_epoch", DESCENDING).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                     # pragma: no cover
        logger.debug("[supervisor_heartbeat] list_recent failed: %s", e)
        return []


def _classify(age_sec: Optional[float], cadence_sec: int, enabled: bool) -> str:
    if not enabled:
        return VERDICT_NOT_EXPECTED
    if age_sec is None:
        return VERDICT_NEVER_SEEN
    if age_sec < 0:
        # Clock skew — treat as unknown rather than coerce to alive.
        return VERDICT_UNKNOWN
    if age_sec <= 2 * cadence_sec:
        return VERDICT_ALIVE
    if age_sec <= 4 * cadence_sec:
        return VERDICT_STALE
    return VERDICT_DEAD


async def verdict_band(
    host_id: Optional[str] = None,
    cadence_sec: Optional[int] = None,
) -> Dict[str, Any]:
    """Classify the Supervisor's liveness for `host_id`.

    Returns
    -------
    {
      "host_id":         str,
      "band":            "alive"|"stale"|"dead"|"never_seen"|"not_expected"|"unknown",
      "age_sec":         float | None,
      "cadence_sec":     int,
      "enabled":         bool,
      "last_seen":       iso | None,
      "is_leader":       bool | None,
      "supervisor_version": str | None,
      "error":           str | None,
    }
    """
    cadence = _resolve_cadence(cadence_sec)
    enabled = is_enabled()
    target  = host_id or _local_host_meta()["host_id"]
    out: Dict[str, Any] = {
        "host_id":            target,
        "band":               VERDICT_UNKNOWN,
        "age_sec":            None,
        "cadence_sec":        cadence,
        "enabled":            enabled,
        "last_seen":          None,
        "is_leader":          None,
        "supervisor_version": None,
        "error":              None,
    }
    try:
        doc = await latest(target)
        if doc is None:
            out["band"] = _classify(None, cadence, enabled)
            return out
        last_epoch  = float(doc.get("ts_epoch") or 0.0)
        now_epoch   = datetime.now(timezone.utc).timestamp()
        age_sec     = round(now_epoch - last_epoch, 3)
        out["age_sec"]    = age_sec
        out["last_seen"]  = doc.get("ts")
        out["is_leader"]  = bool(doc.get("is_leader"))
        out["supervisor_version"] = doc.get("supervisor_version")
        out["band"] = _classify(age_sec, cadence, enabled)
        return out
    except Exception as e:                                     # pragma: no cover
        out["error"] = str(e)[:200]
        return out

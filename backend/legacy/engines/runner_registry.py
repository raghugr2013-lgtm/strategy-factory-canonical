"""Master Bot V1 — Runner Registry (MB-9 Phase 1).

Manages the lifecycle of Windows VPS runner agents that pull
`.cbotpack` artifacts and run cTrader instances. This module is the
control-plane authority for:

  * **Registration** — admin creates a runner row + one-time token.
  * **Token validation** — each runner-facing request carries a
    bearer token verified against `token_hash` (sha256).
  * **Heartbeat ingestion** — runners POST a `compute_probe`-shaped
    snapshot every `MB9_HEARTBEAT_SEC` (default 300 s).
  * **Liveness verdict** — band classifier mirrors
    `factory_runner_heartbeat.py`: alive / stale / dead / never_seen
    / unknown.

Discipline (institutional posture):
  * Tokens are stored ONLY as sha256 hashes. Raw token shown ONCE at
    registration time. No retrieval-after-create endpoint.
  * Read-only diagnostics: heartbeat freshness does NOT trigger any
    action — it informs the operator and the deployment router.
  * Operator-final authority on register / disable. No auto-spawn.
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

RUNNERS_COLL = "master_bot_runners"

# Heartbeat cadence (s). Matches the architecture decision: 5 min.
HEARTBEAT_DEFAULT_SEC = 300

# Verdict band labels — reused verbatim across MB-9 + future scaling work.
VERDICT_ALIVE = "alive"
VERDICT_STALE = "stale"
VERDICT_DEAD = "dead"
VERDICT_NEVER_SEEN = "never_seen"
VERDICT_DISABLED = "disabled"
VERDICT_UNKNOWN = "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _heartbeat_cadence_sec() -> int:
    raw = (os.environ.get("MB9_HEARTBEAT_SEC") or "").strip()
    try:
        return max(60, int(raw)) if raw else HEARTBEAT_DEFAULT_SEC
    except (TypeError, ValueError):
        return HEARTBEAT_DEFAULT_SEC


def _hash_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def _mint_token() -> str:
    # 256 bits of entropy, URL-safe. Operator copies this into the
    # runner agent's local config ONCE.
    return "mbr_" + secrets.token_urlsafe(32)


def _classify(age_seconds: Optional[float], cadence_sec: int, status: str) -> str:
    if status == "disabled":
        return VERDICT_DISABLED
    if age_seconds is None:
        return VERDICT_NEVER_SEEN
    if age_seconds < 0:
        return VERDICT_UNKNOWN
    if age_seconds < 2 * cadence_sec:
        return VERDICT_ALIVE
    if age_seconds < 4 * cadence_sec:
        return VERDICT_STALE
    return VERDICT_DEAD


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[RUNNERS_COLL].create_index("runner_id", unique=True)
        await db[RUNNERS_COLL].create_index("name", unique=True)
        await db[RUNNERS_COLL].create_index("status")
    except Exception:                                            # pragma: no cover
        logger.exception("runner_registry: ensure_indexes failed")


# ─── Registration ────────────────────────────────────────────────────

async def register_runner(
    *,
    name: str,
    hostname: Optional[str] = None,
    platform: str = "windows",
    pair_filters: Optional[List[str]] = None,
    timeframe_filters: Optional[List[str]] = None,
    notes: Optional[str] = None,
    actor: str = "admin",
) -> Dict[str, Any]:
    """Create a runner row + one-time token.

    Returns ``{runner_id, token, ...}``. The raw ``token`` is shown
    ONLY here — store the response immediately. Token is hashed at
    rest; we cannot recover it later.
    """
    db = get_db()
    if not name or len(name) > 120:
        raise ValueError("invalid runner name")
    if platform not in ("windows", "linux"):
        raise ValueError("platform must be 'windows' or 'linux'")
    if await db[RUNNERS_COLL].find_one({"name": name}):
        raise ValueError(f"runner with name '{name}' already exists")

    raw_token = _mint_token()
    runner_id = uuid.uuid4().hex
    row = {
        "runner_id":          runner_id,
        "name":               name,
        "hostname":           hostname or "",
        "platform":           platform,
        "token_hash":         _hash_token(raw_token),
        "pair_filters":       [p.strip().upper() for p in (pair_filters or []) if p.strip()],
        "timeframe_filters":  [t.strip().upper() for t in (timeframe_filters or []) if t.strip()],
        "status":             "registered",
        "last_heartbeat_at":  None,
        "last_snapshot":      None,
        "created_at":         _now_iso(),
        "created_by":         actor,
        "notes":              notes or "",
    }
    await db[RUNNERS_COLL].insert_one(row)
    out = {k: v for k, v in row.items() if k not in ("_id", "token_hash")}
    out["token"] = raw_token   # one-time
    out["token_storage"] = "show-once; sha256-hashed at rest"
    return out


async def validate_token(runner_id: str, token: str) -> Optional[Dict[str, Any]]:
    """Return the runner row if (runner_id, token) is valid. Else None.
    Constant-time comparison on the hash.
    """
    if not runner_id or not token:
        return None
    db = get_db()
    row = await db[RUNNERS_COLL].find_one({"runner_id": runner_id}, {"_id": 0})
    if not row:
        return None
    if row.get("status") == "disabled":
        return None
    expected = row.get("token_hash") or ""
    candidate = _hash_token(token)
    if not secrets.compare_digest(expected, candidate):
        return None
    return row


async def record_heartbeat(
    runner_id: str, snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Update the runner's last_heartbeat_at + last_snapshot. Pure
    write; no verdict reasoning here (the verdict is computed at read
    time via `get_runner_status`)."""
    db = get_db()
    now = _now_iso()
    await db[RUNNERS_COLL].update_one(
        {"runner_id": runner_id},
        {"$set": {
            "last_heartbeat_at": now,
            "last_snapshot":     snapshot or {},
            "status":            "active",  # first heartbeat promotes registered→active
        }},
    )
    return {"runner_id": runner_id, "recorded_at": now}


async def disable_runner(runner_id: str, *, actor: str = "admin") -> Dict[str, Any]:
    db = get_db()
    row = await db[RUNNERS_COLL].find_one({"runner_id": runner_id}, {"_id": 0})
    if not row:
        raise ValueError("runner not found")
    await db[RUNNERS_COLL].update_one(
        {"runner_id": runner_id},
        {"$set": {"status": "disabled", "disabled_at": _now_iso(), "disabled_by": actor}},
    )
    return {"runner_id": runner_id, "status": "disabled"}


async def list_runners() -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[RUNNERS_COLL].find({}, {"_id": 0, "token_hash": 0}).sort("created_at", -1)
    rows: List[Dict[str, Any]] = []
    cadence = _heartbeat_cadence_sec()
    now = datetime.now(timezone.utc)
    async for r in cur:
        last = r.get("last_heartbeat_at")
        age = None
        if last:
            try:
                last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age = (now - last_dt).total_seconds()
            except ValueError:
                age = None
        r["verdict"] = _classify(age, cadence, r.get("status") or "registered")
        r["age_seconds"] = int(age) if age is not None else None
        r["cadence_sec"] = cadence
        rows.append(r)
    return rows


async def get_runner_status(runner_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    r = await db[RUNNERS_COLL].find_one(
        {"runner_id": runner_id}, {"_id": 0, "token_hash": 0},
    )
    if not r:
        return None
    cadence = _heartbeat_cadence_sec()
    last = r.get("last_heartbeat_at")
    age = None
    if last:
        try:
            last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last_dt).total_seconds()
        except ValueError:
            age = None
    r["verdict"] = _classify(age, cadence, r.get("status") or "registered")
    r["age_seconds"] = int(age) if age is not None else None
    r["cadence_sec"] = cadence
    return r


__all__ = [
    "RUNNERS_COLL", "HEARTBEAT_DEFAULT_SEC",
    "VERDICT_ALIVE", "VERDICT_STALE", "VERDICT_DEAD",
    "VERDICT_NEVER_SEEN", "VERDICT_DISABLED", "VERDICT_UNKNOWN",
    "ensure_indexes", "register_runner", "validate_token",
    "record_heartbeat", "disable_runner",
    "list_runners", "get_runner_status",
]

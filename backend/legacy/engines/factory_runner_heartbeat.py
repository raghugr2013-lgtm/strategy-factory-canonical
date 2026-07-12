"""
Pass 16 — Factory-runner heartbeat freshness aggregator.

Read-only diagnostic. Pure function of:
  * the most recent ``factory_runner:heartbeat`` row in ``audit_log``;
  * the operator-decreed ``FACTORY_RUNNER_OWNS_SCHEDULERS`` env flag;
  * the current wall-clock UTC time.

Closes the silent-failure mode identified by the 2026-01 audit:
``deployment-readiness`` previously returned ``ready`` even when
the factory_runner sibling process had never been started — because
the orchestrator scheduler restoration short-circuits when the env
flag delegates ownership to a sibling that does not exist. Operators
saw "READY" with no actual scheduler running.

This module is the institutional answer to "is the autonomous research
runner actually alive?" — without any new authority surface, without
any flag flips, without consulting any dormant capability.

Discipline (consistent with every prior latent module):
  * READ-ONLY. No writes, no mutations, no flag flips.
  * Pure aggregator + pure verdict band. No engine consumer.
  * Statically enforced by
    ``tests/test_factory_runner_heartbeat.py::test_no_engine_consumer``.
  * Best-effort: a Mongo blip yields verdict ``unknown`` with the
    underlying error captured, NEVER raises.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Verdict thresholds — operator-tunable via env without code change.
# Defaults: heartbeat cadence in factory_runner.py is
# ``FACTORY_RUNNER_HEARTBEAT_SEC`` (default 300 s = 5 min). A row
# fresher than 2× cadence is "alive"; 2-4× is "stale"; older or
# absent (with ownership flag ON) is "dead".
# ─────────────────────────────────────────────────────────────────────
_DEFAULT_HEARTBEAT_SEC = 300

# Verdict band labels — used by the extended deployment-readiness check
# and the dedicated latent endpoint. Centralised so the test suite
# can assert the vocabulary stays stable.
VERDICT_ALIVE = "alive"
VERDICT_STALE = "stale"
VERDICT_DEAD = "dead"
VERDICT_NEVER_SEEN = "never_seen"
VERDICT_NOT_EXPECTED = "not_expected"
VERDICT_UNKNOWN = "unknown"


def _heartbeat_interval_sec() -> int:
    """Resolve the runner's configured heartbeat cadence (best-effort)."""
    raw = (os.environ.get("FACTORY_RUNNER_HEARTBEAT_SEC") or "").strip()
    try:
        return max(60, int(raw)) if raw else _DEFAULT_HEARTBEAT_SEC
    except (TypeError, ValueError):
        return _DEFAULT_HEARTBEAT_SEC


def _owner_flag_active() -> bool:
    """True when ``FACTORY_RUNNER_OWNS_SCHEDULERS`` is enabled.

    Pass 16: this is the SINGLE source of truth for "is the operator
    expecting the sibling runner to own the scheduler authority?".
    Engines must keep reading ``os.environ`` directly (the
    institutional dormant-flag rule) — this helper exists only for
    the heartbeat aggregator's narrative output.
    """
    raw = (os.environ.get("FACTORY_RUNNER_OWNS_SCHEDULERS") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _classify(
    age_seconds: Optional[float],
    owner_active: bool,
    cadence_sec: int,
) -> str:
    """Pure band classifier.

    Bands:
      * ``alive``        — age < 2× cadence
      * ``stale``        — 2× cadence ≤ age < 4× cadence
      * ``dead``         — age ≥ 4× cadence  (process likely crashed)
      * ``never_seen``   — no heartbeat row exists; owner expected
      * ``not_expected`` — no heartbeat row, owner flag OFF (legitimate
                            posture when uvicorn owns the schedulers)
      * ``unknown``      — Mongo error or unresolvable state
    """
    if age_seconds is None:
        return VERDICT_NEVER_SEEN if owner_active else VERDICT_NOT_EXPECTED
    if age_seconds < 0:
        # Clock skew or a row in the future — treat as unknown rather
        # than silently coercing to alive.
        return VERDICT_UNKNOWN
    if age_seconds < 2 * cadence_sec:
        return VERDICT_ALIVE
    if age_seconds < 4 * cadence_sec:
        return VERDICT_STALE
    return VERDICT_DEAD


def _verdict_detail(
    verdict: str,
    age_seconds: Optional[float],
    owner_active: bool,
    cadence_sec: int,
) -> str:
    """Operator-readable single-line explanation per band."""
    if verdict == VERDICT_ALIVE:
        return (
            f"Factory-runner heartbeat fresh ({int(age_seconds or 0)}s old; "
            f"cadence {cadence_sec}s). Sibling scheduler authority is active."
        )
    if verdict == VERDICT_STALE:
        return (
            f"Factory-runner heartbeat stale ({int(age_seconds or 0)}s old; "
            f"cadence {cadence_sec}s). Runner may be paused or in a slow "
            f"shutdown — investigate before relying on autonomous research."
        )
    if verdict == VERDICT_DEAD:
        return (
            f"Factory-runner heartbeat older than 4× cadence "
            f"({int(age_seconds or 0)}s; cadence {cadence_sec}s). "
            f"The sibling runner is almost certainly dead. Schedulers "
            f"that were delegated to it (orchestrator, auto-discovery, "
            f"auto-maintenance) are NOT running. "
            f"Recovery: `sudo supervisorctl restart factory-runner`."
        )
    if verdict == VERDICT_NEVER_SEEN:
        return (
            "FACTORY_RUNNER_OWNS_SCHEDULERS=true but no heartbeat row has "
            "ever been written to audit_log. The sibling factory_runner "
            "is NOT running. The uvicorn backend has deferred scheduler "
            "restoration to a process that does not exist — autonomous "
            "research is silently dormant. "
            "Recovery: `sudo supervisorctl start factory-runner`."
        )
    if verdict == VERDICT_NOT_EXPECTED:
        return (
            "FACTORY_RUNNER_OWNS_SCHEDULERS is OFF — schedulers are "
            "owned by the uvicorn backend. No factory-runner heartbeat "
            "is expected in this posture."
        )
    return (
        "Heartbeat freshness could not be determined "
        "(audit_log unreachable or row malformed)."
    )


async def get_heartbeat_status() -> Dict[str, Any]:
    """Return a structured heartbeat-freshness snapshot.

    NEVER raises. Returns a plain dict suitable for direct JSON
    serialization — used by both the dedicated latent endpoint and
    the extended deployment-readiness check.

    Shape::

        {
          "verdict":            "alive" | "stale" | "dead" | "never_seen"
                                  | "not_expected" | "unknown",
          "owner_flag_active":  bool,
          "cadence_sec":        int,
          "stale_threshold_sec":  int,    # 2 × cadence
          "dead_threshold_sec":   int,    # 4 × cadence
          "last_heartbeat_at":  str | None,   # ISO timestamp
          "last_heartbeat_pid": int | None,
          "age_seconds":        int | None,
          "detail":             str,
          "advisory_only":      True,
          "read_only":          True,
          "governance_authority": False,
          "operator_authority": "final",
        }
    """
    cadence = _heartbeat_interval_sec()
    owner = _owner_flag_active()
    out: Dict[str, Any] = {
        "verdict":              VERDICT_UNKNOWN,
        "owner_flag_active":    owner,
        "cadence_sec":          cadence,
        "stale_threshold_sec":  2 * cadence,
        "dead_threshold_sec":   4 * cadence,
        "last_heartbeat_at":    None,
        "last_heartbeat_pid":   None,
        "age_seconds":          None,
        "detail":               "",
        "advisory_only":        True,
        "read_only":            True,
        "governance_authority": False,
        "operator_authority":   "final",
    }
    try:
        from engines.db import get_db
        db = get_db()
        row = await db["audit_log"].find_one(
            {"event": "factory_runner:heartbeat"},
            sort=[("ts_dt", -1)],
            projection={"_id": 0, "ts": 1, "ts_dt": 1, "pid": 1},
        )
        if not row:
            out["verdict"] = _classify(None, owner, cadence)
            out["detail"] = _verdict_detail(out["verdict"], None, owner, cadence)
            return out
        # Resolve age. Prefer the BSON Date companion (ts_dt) — it's
        # authoritative and timezone-stable. Fall back to ISO ts.
        ts_dt = row.get("ts_dt")
        if ts_dt is None and row.get("ts"):
            try:
                ts_dt = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00"))
            except ValueError:
                ts_dt = None
        if ts_dt is not None and ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - ts_dt).total_seconds() if ts_dt else None
        verdict = _classify(age, owner, cadence)
        out.update({
            "verdict":            verdict,
            "last_heartbeat_at":  row.get("ts") or (ts_dt.isoformat() if ts_dt else None),
            "last_heartbeat_pid": row.get("pid"),
            "age_seconds":        int(age) if age is not None else None,
            "detail":             _verdict_detail(verdict, age, owner, cadence),
        })
        return out
    except Exception as e:                                  # noqa: BLE001
        logger.debug("[factory_runner_heartbeat] probe failed: %s", e)
        out["verdict"] = VERDICT_UNKNOWN
        out["detail"] = (
            "Heartbeat freshness could not be determined: "
            f"{str(e)[:200]}"
        )
        return out


__all__ = [
    "get_heartbeat_status",
    "VERDICT_ALIVE",
    "VERDICT_STALE",
    "VERDICT_DEAD",
    "VERDICT_NEVER_SEEN",
    "VERDICT_NOT_EXPECTED",
    "VERDICT_UNKNOWN",
]

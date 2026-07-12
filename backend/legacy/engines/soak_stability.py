"""
Phase 2 scaffolding — Soak stability emitter (DORMANT).

Per-tick stability sample writer + reader. When
``ENABLE_SOAK_STABILITY_EMITTER=true`` AND a caller (typically the
orchestrator tick) invokes ``capture()``, one compact row is appended
to the ``soak_stability_samples`` collection carrying:

  * the live ``safe_to_widen`` verdict
  * compute headroom snapshot
  * orchestration health pulse
  * advisory-lock count
  * 24h cycle error rate

These samples are the historical evidence base every future widening
verdict depends on (the "stable orchestration samples must exist
before activation" criterion).

Discipline:
  * Dormant: ``capture()`` is a no-op while the flag is OFF.
  * Best-effort: never raises. The orchestrator tick cannot crash
    on a stability-sample write failure.
  * Bounded: collection grows by at most ~96 rows/day at a 15-min
    cadence; a TTL index (declared on first activation by the index
    sweep, default 365 days) caps growth.
  * Pure-observer: NO mutation of any other subsystem.
  * No call-site wires this yet — adoption is operator-driven.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "soak_stability_samples"

DEFAULT_LIMIT = 200
MAX_LIMIT = 2000


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_SOAK_STABILITY_EMITTER") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def capture(*, source: str = "orchestrator_tick") -> Optional[str]:
    """Capture one stability sample. No-op while the flag is OFF.

    Returns the new sample_id on success, None when the flag is off
    or on any persistence error. NEVER raises.
    """
    if not is_enabled():
        return None
    try:
        # Lazy imports so this module stays leaf-loadable.
        from engines import compute_probe
        snap = compute_probe.snapshot()
        head = compute_probe.headroom_summary(snap)

        verdict: Optional[str] = None
        current_stage: Optional[str] = None
        try:
            from engines import safe_to_widen
            sw = await safe_to_widen.evaluate()
            verdict = sw.get("verdict")
            current_stage = sw.get("current_stage")
        except Exception:                                   # pragma: no cover
            pass

        held_locks: Optional[int] = None
        try:
            held_locks = await get_db()["advisory_locks"].count_documents({})
        except Exception:                                   # pragma: no cover
            pass

        cycle_error_rate: Optional[float] = None
        try:
            db = get_db()
            n_total = 0
            n_err = 0
            async for row in db["auto_run_cycles"].find(
                {}, {"_id": 0, "status": 1},
            ).sort("finished_at", -1).limit(50):
                n_total += 1
                st = (row.get("status") or "").lower()
                if st in ("error", "timeout"):
                    n_err += 1
            if n_total > 0:
                cycle_error_rate = round(n_err / n_total, 3)
        except Exception:                                   # pragma: no cover
            pass

        now = _now()
        sample_id = uuid.uuid4().hex[:16]
        doc = {
            "sample_id":         sample_id,
            "ts":                now.isoformat(),
            "ts_dt":             now,
            "source":            str(source)[:60],
            "process_pid":       os.getpid(),
            "safe_to_widen_verdict": verdict,
            "current_stage":     current_stage,
            "cpu_percent":       snap.get("cpu_percent"),
            "mem_percent":       snap.get("mem_percent"),
            "load_per_core":     head.get("load_per_core"),
            "host_headroom_ok":  head.get("ok"),
            "advisory_locks_held": held_locks,
            "recent_cycle_error_rate": cycle_error_rate,
            "phase":             "scaffolding-1",
        }
        await get_db()[COLLECTION].insert_one(doc)
        return sample_id
    except Exception as e:                                   # pragma: no cover
        logger.debug("[soak_stability] capture failed: %s", e)
        return None


async def list_samples(
    *,
    limit: int = DEFAULT_LIMIT,
    since: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read-only listing of recent stability samples (newest first)."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    query: Dict[str, Any] = {}
    if since is not None:
        query["ts_dt"] = {"$gte": since}
    rows: List[Dict[str, Any]] = []
    try:
        cur = (
            get_db()[COLLECTION]
            .find(query, {"_id": 0})
            .sort("ts_dt", -1)
            .limit(limit)
        )
        async for d in cur:
            rows.append(d)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[soak_stability] list_samples failed: %s", e)
    return {
        "enabled":          is_enabled(),
        "samples_count":    len(rows),
        "limit":            limit,
        "since":            since.isoformat() if since else None,
        "samples":          rows,
    }


async def summary(window_hours: int = 24) -> Dict[str, Any]:
    """Aggregate statistics over the recent window — useful as a
    one-glance "is the system soaking cleanly?" surface."""
    from datetime import timedelta
    window_hours = max(1, min(int(window_hours), 168))
    cutoff = _now() - timedelta(hours=window_hours)
    rows = (await list_samples(limit=MAX_LIMIT, since=cutoff))["samples"]

    if not rows:
        return {
            "enabled":      is_enabled(),
            "window_hours": window_hours,
            "samples":      0,
            "verdict_histogram": {},
            "stage_histogram":   {},
            "median_cpu_percent": None,
            "median_mem_percent": None,
            "median_load_per_core": None,
            "median_cycle_error_rate": None,
            "host_headroom_pct_ok": None,
        }

    def _median(values):
        v = sorted(x for x in values if isinstance(x, (int, float)))
        return v[len(v) // 2] if v else None

    verdict_hist: Dict[str, int] = {}
    stage_hist: Dict[str, int] = {}
    ok_count = 0
    ok_total = 0
    for r in rows:
        v = r.get("safe_to_widen_verdict") or "UNKNOWN"
        verdict_hist[v] = verdict_hist.get(v, 0) + 1
        s = r.get("current_stage") or "UNKNOWN"
        stage_hist[s] = stage_hist.get(s, 0) + 1
        ok = r.get("host_headroom_ok")
        if isinstance(ok, bool):
            ok_total += 1
            if ok:
                ok_count += 1

    return {
        "enabled":             is_enabled(),
        "window_hours":        window_hours,
        "samples":             len(rows),
        "verdict_histogram":   verdict_hist,
        "stage_histogram":     stage_hist,
        "median_cpu_percent":  _median(r.get("cpu_percent") for r in rows),
        "median_mem_percent":  _median(r.get("mem_percent") for r in rows),
        "median_load_per_core": _median(r.get("load_per_core") for r in rows),
        "median_cycle_error_rate": _median(r.get("recent_cycle_error_rate") for r in rows),
        "host_headroom_pct_ok": (
            round(100.0 * ok_count / ok_total, 1) if ok_total > 0 else None
        ),
    }

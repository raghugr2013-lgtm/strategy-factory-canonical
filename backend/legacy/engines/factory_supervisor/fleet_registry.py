"""
Factory Supervisor FS-P1.0 — Fleet registry (read-only multi-host view).

Composes a single canonical snapshot of every host the Supervisor knows
about by reading EXISTING dormant primitives. **Pure projection.** No
new collection, no writes, no scheduler authority. Read-mostly, cached
for 5 seconds in-process.

The snapshot powers:
  * `/api/factory-supervisor/fleet` (operator dashboard input)
  * `system_state_view.snapshot()` (FS-P1.3 — unified state, Principle P-5)
  * the future `routing_policy.choose_host()` (FS-P1.1)

Sources (all best-effort; each can degrade independently):
  * scaling_registry.list_nodes()          — multi-host heartbeats (P1.A)
  * scaling_registry.get_node(host_id)     — current host record
  * host_capability.current()              — local capability detector
  * queue_pressure.snapshot()              — local per-class pressure
  * compute_probe.headroom_summary()       — local headroom band
  * architect_scaling_view.get_admission_journal_stats(window_sec)

Discipline:
  * READ-ONLY. No mutations.
  * Best-effort. A failed source yields a structured `error` field but
    does NOT break the snapshot.
  * Dormant. The 5-s cache means the fleet view costs ~one Mongo
    aggregate per 5 s no matter how many callers it has.

Public surface:
    snapshot(refresh=False, window_sec=3600)  → dict
    fleet_band(snapshot_dict) → "ok"|"warn"|"critical"|"unknown"
    invalidate_cache()  — for tests
"""
from __future__ import annotations

import logging
import socket
import time
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

CACHE_TTL_SEC = 5.0
_CACHE: Dict[str, Any] = {"ts": 0.0, "value": None}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def invalidate_cache() -> None:
    """Tests + admin force-refresh hook."""
    _CACHE["ts"] = 0.0
    _CACHE["value"] = None


async def _read_remote_hosts() -> Dict[str, Any]:
    try:
        from engines import scaling_registry
        rows = await scaling_registry.list_nodes(limit=200)
        return {"available": True, "hosts": rows}
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200], "hosts": []}


def _read_local_capability() -> Dict[str, Any]:
    try:
        from engines import host_capability
        caps = host_capability.current()
        if caps is None:
            return {"available": False, "error": "not_detected"}
        return {
            "available":            True,
            "host_id":              caps.host_id,
            "hostname":             caps.hostname,
            "logical_cpu_count":    caps.logical_cpu_count,
            "effective_cpu_count":  caps.effective_cpu_count,
            "mem_total_gb":         caps.mem_total_gb,
            "mem_available_gb":     caps.mem_available_gb,
            "cgroup_cpu_quota":     caps.cgroup_cpu_quota,
            "profile":              caps.profile,
        }
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


def _read_local_pressure() -> Dict[str, Any]:
    try:
        from engines import queue_pressure
        return queue_pressure.snapshot()
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


def _read_local_headroom() -> Dict[str, Any]:
    try:
        from engines import compute_probe
        h = compute_probe.headroom_summary()
        return {
            "available":        True,
            "ok":               bool(h.get("ok")),
            "band":             h.get("band") or "unknown",
            "cpu_headroom_pct": h.get("cpu_headroom_pct"),
            "mem_headroom_pct": h.get("mem_headroom_pct"),
        }
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "band": "unknown", "error": str(e)[:200]}


async def _read_admission_stats(window_sec: int) -> Dict[str, Any]:
    try:
        from engines import architect_scaling_view
        return await architect_scaling_view.get_admission_journal_stats(window_sec)
    except Exception as e:                                     # pragma: no cover
        return {"window_sec": window_sec, "total": 0, "error": str(e)[:200]}


def _local_host_id() -> str:
    try:
        from engines import host_capability
        caps = host_capability.current()
        if caps is not None:
            return caps.host_id
    except Exception:                                          # pragma: no cover
        pass
    return socket.gethostname() or "unknown"


def fleet_band(snap: Dict[str, Any]) -> str:
    """Worst-of band across known hosts (advisory). 'unknown' if no data."""
    hosts = snap.get("hosts") or []
    if not hosts:
        local = snap.get("local") or {}
        return (local.get("headroom") or {}).get("band") or "unknown"
    worst_rank = 0
    rank = {"ok": 1, "unknown": 2, "warn": 3, "critical": 4}
    chosen = "unknown"
    for h in hosts:
        b = ((h.get("last_headroom") or {}).get("band")) or "unknown"
        r = rank.get(b, 2)
        if r > worst_rank:
            worst_rank = r
            chosen = b
    return chosen


async def snapshot(refresh: bool = False, window_sec: int = 3600) -> Dict[str, Any]:
    """Build a multi-host snapshot. Cached 5 s.

    Returns:
        {
          "evaluated_at": iso,
          "local_host_id": "<host>",
          "hosts": [<scaling_nodes rows>],
          "local": {
              "host_capability": {...},
              "queue_pressure":  {...},
              "headroom":        {...},
              "admission_stats": {...},
          },
          "fleet_band": "ok" | "warn" | "critical" | "unknown",
          "sources":  {<source>: "ok"|"error"|"unavailable", ...},
        }
    """
    now = time.monotonic()
    if not refresh and _CACHE["value"] is not None and (now - _CACHE["ts"]) < CACHE_TTL_SEC:
        return _CACHE["value"]

    remote        = await _read_remote_hosts()
    cap           = _read_local_capability()
    pressure      = _read_local_pressure()
    headroom      = _read_local_headroom()
    adm_stats     = await _read_admission_stats(window_sec)

    sources = {
        "remote_hosts":        "ok" if remote.get("available") else "error",
        "host_capability":     "ok" if cap.get("available") else "error",
        "queue_pressure":      "ok" if pressure.get("worker_utilization") is not None else "error",
        "headroom":            "ok" if headroom.get("available") else "error",
        "admission_stats":     "ok" if "error" not in adm_stats else "error",
    }

    snap: Dict[str, Any] = {
        "evaluated_at":  _now_iso(),
        "local_host_id": _local_host_id(),
        "hosts":         remote.get("hosts") or [],
        "local": {
            "host_capability": cap,
            "queue_pressure":  pressure,
            "headroom":        headroom,
            "admission_stats": adm_stats,
        },
        "sources":       sources,
    }
    snap["fleet_band"] = fleet_band(snap)

    _CACHE["ts"] = now
    _CACHE["value"] = snap
    return snap

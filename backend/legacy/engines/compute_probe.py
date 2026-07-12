"""
Phase 2 scaffolding — Compute probe (READ-ONLY, always safe to call).

Pure observation: CPU%, load average, memory, open-file-descriptor count.
Never mutates anything; never raises (returns conservative defaults on
error). Other dormant Phase 2 primitives consume this snapshot when their
gating flags activate — but until then NO call-site reads from this module.

Discipline:
  * Read-only: no DB writes, no env mutation, no scheduler interaction.
  * Best-effort: missing `psutil` returns ``available=False`` payload
    rather than crashing.
  * Reversible: deleting this module breaks zero existing imports.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import psutil  # type: ignore
    _PSUTIL_OK = True
except Exception:                                            # pragma: no cover
    psutil = None                                            # type: ignore
    _PSUTIL_OK = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_available() -> bool:
    """True iff psutil import succeeded."""
    return bool(_PSUTIL_OK)


def snapshot() -> Dict[str, Any]:
    """One read of the host's compute state. Never raises.

    Shape (all fields nullable when psutil unavailable):
        {
          "ts":          iso-string,
          "available":   bool,            # psutil importable?
          "cpu_count":   int | None,      # logical CPUs
          "cpu_percent": float | None,    # last-sampled 1s average
          "load_avg":    [1m,5m,15m] | None,
          "mem_total_gb":      float | None,
          "mem_available_gb":  float | None,
          "mem_percent":       float | None,
          "open_fds":          int | None,
          "process_rss_mb":    float | None,
        }
    """
    out: Dict[str, Any] = {
        "ts":                _now_iso(),
        "available":         _PSUTIL_OK,
        "cpu_count":         None,
        "cpu_percent":       None,
        "load_avg":          None,
        "mem_total_gb":      None,
        "mem_available_gb":  None,
        "mem_percent":       None,
        "open_fds":          None,
        "process_rss_mb":    None,
    }
    if not _PSUTIL_OK:
        return out
    try:
        out["cpu_count"]   = psutil.cpu_count(logical=True)
        # interval=None returns the average since last call (cheap on hot path).
        out["cpu_percent"] = float(psutil.cpu_percent(interval=None))
        try:
            la = os.getloadavg()
            out["load_avg"] = [round(la[0], 3), round(la[1], 3), round(la[2], 3)]
        except (OSError, AttributeError):                    # pragma: no cover
            out["load_avg"] = None
        vm = psutil.virtual_memory()
        out["mem_total_gb"]     = round(vm.total / (1024 ** 3), 3)
        out["mem_available_gb"] = round(vm.available / (1024 ** 3), 3)
        out["mem_percent"]      = float(vm.percent)
        proc = psutil.Process()
        try:
            out["open_fds"] = proc.num_fds()
        except (AttributeError, psutil.AccessDenied):        # pragma: no cover
            out["open_fds"] = None
        try:
            out["process_rss_mb"] = round(proc.memory_info().rss / (1024 ** 2), 2)
        except psutil.AccessDenied:                          # pragma: no cover
            out["process_rss_mb"] = None
    except Exception as e:                                   # pragma: no cover
        logger.debug("[compute_probe] snapshot failed: %s", e)
    return out


def headroom_summary(snap: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Derive a simple "is this host healthy enough to widen?" answer.

    Pure arithmetic over a snapshot — NO thresholds with operator-facing
    meaning. The caller (an activation-governance UI) decides what to do
    with the numbers.

    Returns:
        {
          "ok":                 bool,    # crude bool: cpu<85% and mem<85%
          "cpu_headroom_pct":   float | None,
          "mem_headroom_pct":   float | None,
          "load_per_core":      float | None,
          "band":               "ok" | "warn" | "critical" | "unknown",
        }

    The `band` field was added in VPS Scaling P1.A. It is the categorical
    summary the `scaling_router` consumes. Pure derivation from the same
    inputs — never changes the `ok` bool, never raises. Thresholds
    (per CAPACITY_ENGINE_DESIGN.md §5.2):
        unknown  : cpu_percent or mem_percent is None
        critical : cpu >= 95 OR mem >= 95
        warn     : cpu >= 80 OR mem >= 85
        ok       : otherwise
    """
    s = snap if snap is not None else snapshot()
    cpu_p = s.get("cpu_percent")
    mem_p = s.get("mem_percent")
    cpu_head = (100.0 - float(cpu_p)) if isinstance(cpu_p, (int, float)) else None
    mem_head = (100.0 - float(mem_p)) if isinstance(mem_p, (int, float)) else None
    load_per_core = None
    la = s.get("load_avg")
    n  = s.get("cpu_count")
    if isinstance(la, list) and la and isinstance(n, int) and n > 0:
        load_per_core = round(float(la[0]) / float(n), 3)
    ok = (
        isinstance(cpu_head, float) and cpu_head > 15.0
        and isinstance(mem_head, float) and mem_head > 15.0
    )
    # Band classification (additive; existing consumers ignore unknown keys).
    if not isinstance(cpu_p, (int, float)) or not isinstance(mem_p, (int, float)):
        band = "unknown"
    elif cpu_p >= 95.0 or mem_p >= 95.0:
        band = "critical"
    elif cpu_p >= 80.0 or mem_p >= 85.0:
        band = "warn"
    else:
        band = "ok"
    return {
        "ok":               bool(ok),
        "cpu_headroom_pct": round(cpu_head, 2) if cpu_head is not None else None,
        "mem_headroom_pct": round(mem_head, 2) if mem_head is not None else None,
        "load_per_core":    load_per_core,
        "band":             band,
    }

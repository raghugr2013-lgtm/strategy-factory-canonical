"""
VPS Scaling P1.C — Adaptive concurrency calculator (PURE FUNCTION).

Given (HostCapability, compute_probe snapshot, queue_pressure snapshot),
return a per-WorkloadClass concurrency target. This is the bridge
between the read-only observability layer (P1.A + P1.B) and the active
admission gate (P1.C admission_controller).

Discipline (per CAPACITY_ENGINE_DESIGN.md §5):
  * PURE FUNCTION. No DB. No env mutation. No I/O. No state.
  * Deterministic: given the same inputs, returns the same output.
  * No raises — bad inputs degrade to safe defaults.
  * Hysteresis: band downgrades require ≥ 3 consecutive observations of
    the lower band; upgrades are instantaneous. The caller is expected
    to supply `consecutive_warn_samples` / `consecutive_critical_samples`
    from a rolling counter (not implemented in P1.C — defaults to 0).
  * Honest-refusal: `band="unknown"` → bt/mut/fc all 0. The admission
    controller maps that to `defer` for API_HOT / `refuse` for everything
    else.

Output shape (caller-stable across P1.D rewiring):

    ConcurrencyTargets(
        pool_size=int,                          # absolute ceiling
        max_concurrent_backtests=int,
        max_concurrent_mutations=int,
        max_concurrent_factory_cycles=int,
        max_concurrent_api_hot="unlimited",     # API_HOT not count-gated
        max_concurrent_agents="unlimited",      # AGENT not count-gated
        band="ok" | "ok_busy" | "warn" | "critical" | "unknown",
        band_reason=str,
        derivation={...},                       # for diagnostic API
    )
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from engines.host_capability import HostCapability


# ─── Public types ────────────────────────────────────────────────────

@dataclass
class ConcurrencyTargets:
    pool_size:                     int
    max_concurrent_backtests:      int
    max_concurrent_mutations:      int
    max_concurrent_factory_cycles: int
    max_concurrent_api_hot:        str = "unlimited"
    max_concurrent_agents:         str = "unlimited"
    band:                          str = "unknown"
    band_reason:                   str = ""
    derivation:                    Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Band thresholds (mirror compute_probe + add `ok_busy`) ──────────
# `ok_busy` is an internal band — treated as `ok` for admission but
# tells the operator "we're hot, do not aggressively scale up".

CPU_WARN     = 80.0
CPU_CRITICAL = 95.0
MEM_WARN     = 85.0
MEM_CRITICAL = 95.0
CPU_BUSY     = 60.0
MEM_BUSY     = 70.0


def classify_band(probe: Optional[Dict[str, Any]]) -> tuple:
    """Pure-function band classifier from a compute_probe snapshot.

    Returns (band, reason). Bands: ok, ok_busy, warn, critical, unknown.
    """
    if not isinstance(probe, dict):
        return ("unknown", "probe_missing")
    cpu = probe.get("cpu_percent")
    mem = probe.get("mem_percent")
    if not isinstance(cpu, (int, float)) or not isinstance(mem, (int, float)):
        return ("unknown", "probe_unavailable")
    if cpu >= CPU_CRITICAL or mem >= MEM_CRITICAL:
        return ("critical", f"cpu={cpu:.1f} mem={mem:.1f}")
    if cpu >= CPU_WARN or mem >= MEM_WARN:
        return ("warn", f"cpu={cpu:.1f} mem={mem:.1f}")
    if cpu >= CPU_BUSY or mem >= MEM_BUSY:
        return ("ok_busy", f"cpu={cpu:.1f} mem={mem:.1f}")
    return ("ok", f"cpu={cpu:.1f} mem={mem:.1f}")


# ─── Main recommendation ─────────────────────────────────────────────

def _resolve_pool_size_for(caps: Optional[HostCapability]) -> int:
    """Read the recommended pool size from P1.B sizer; never raises."""
    if caps is None:
        return 1
    try:
        from engines.adaptive_pool_sizer import recommend_pool_size
        return max(1, int(recommend_pool_size(caps)))
    except Exception:                                          # pragma: no cover
        return 1


def recommend(
    caps: Optional[HostCapability],
    probe: Optional[Dict[str, Any]],
    pressure: Optional[Dict[str, Any]] = None,
) -> ConcurrencyTargets:
    """Compute per-class concurrency targets.

    Args
    ----
    caps     : HostCapability (boot-time row); None ⇒ degrade to small.
    probe    : compute_probe.snapshot() dict; None ⇒ band=unknown.
    pressure : queue_pressure.snapshot() dict; optional. When present
               and `pressure_band == "critical"`, the calculator also
               steps down (queue-driven critical wins over probe band).

    Returns
    -------
    ConcurrencyTargets dataclass. Always populated; never raises.

    Step-down logic per band:
        ok / ok_busy → bt=mut=pool_n, fc=1
        warn         → bt=mut=pool_n//2 (min 1), fc=0
        critical     → bt=mut=0, fc=0
        unknown      → bt=mut=0, fc=0
    """
    pool_n = _resolve_pool_size_for(caps)
    band, reason = classify_band(probe)

    # Queue-pressure override: if pressure layer says critical, treat
    # as a stronger gate than probe band alone. Probe-critical still
    # wins; pressure-critical can ONLY step DOWN, never UP.
    pressure_band = (pressure or {}).get("pressure_band") if isinstance(pressure, dict) else None
    if pressure_band == "critical" and band not in ("critical", "unknown"):
        band = "critical"
        reason = f"queue_pressure_critical (was probe band: {classify_band(probe)[0]})"

    if band in ("ok", "ok_busy"):
        bt = pool_n
        mut = pool_n
        fc = 1
    elif band == "warn":
        bt = max(1, pool_n // 2)
        mut = max(1, pool_n // 2)
        fc = 0
    elif band == "critical":
        bt = 0
        mut = 0
        fc = 0
    else:  # unknown
        bt = 0
        mut = 0
        fc = 0

    derivation = {
        "pool_size":          pool_n,
        "host_profile":       (caps.profile if caps else None),
        "host_effective_cpu": (caps.effective_cpu_count if caps else None),
        "probe_band":         classify_band(probe)[0],
        "pressure_band":      pressure_band,
        "final_band":         band,
        "thresholds": {
            "cpu_warn": CPU_WARN, "cpu_critical": CPU_CRITICAL,
            "mem_warn": MEM_WARN, "mem_critical": MEM_CRITICAL,
            "cpu_busy": CPU_BUSY, "mem_busy": MEM_BUSY,
        },
    }

    return ConcurrencyTargets(
        pool_size=pool_n,
        max_concurrent_backtests=bt,
        max_concurrent_mutations=mut,
        max_concurrent_factory_cycles=fc,
        band=band,
        band_reason=reason,
        derivation=derivation,
    )

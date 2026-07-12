"""
VPS Scaling P1.B — Adaptive pool sizer (PURE FUNCTION).

Translates a `HostCapability` into a recommended `cpu_pool` worker
count. Pure; no I/O; deterministic. Consumed by `cpu_pool.pool_size()`
when (a) `CPU_POOL_SIZE` env is unset AND (b) `ENABLE_ADAPTIVE_POOL_SIZING`
flag is ON.

Discipline (per CAPACITY_ENGINE_DESIGN.md §3):
  * Pure function. No env mutation, no DB, no side-effects.
  * Operator override `CPU_POOL_SIZE` env wins absolutely (handled
    in `cpu_pool.pool_size()`, not here).
  * Floor at 1 worker on every branch (clamp protects tiny containers).
  * Ceiling at 32 workers (matches existing `cpu_pool` cap — preserved
    as a safety net regardless of `recommend_pool_size` output).

Recommendation table (per CAPACITY_ENGINE_DESIGN §3.1):
    small  : max(1, min(cpu - 1, 2))   # leave 1 core for API + OS
    medium : max(2, cpu - 2)           # leave 2 cores: API + Mongo + OS
    large  : max(4, cpu - 3)           # leave 3 cores
    xlarge : max(8, cpu - 4)           # leave 4 cores
    (fallback) : 4
"""
from __future__ import annotations

from typing import Optional

from engines.feature_flags import flag
from engines.host_capability import HostCapability, current as current_caps


CPU_POOL_HARD_CEIL = 32   # mirrors existing cpu_pool.pool_size() cap.


def recommend_pool_size(caps: HostCapability, profile: Optional[str] = None) -> int:
    """Pure recommendation from host capability + profile.

    Args
    ----
    caps    : detected host capability (boot-time row)
    profile : explicit profile override; defaults to `caps.profile`

    Returns
    -------
    Integer recommended `max_workers` for the cpu_pool. Always in
    `[1, CPU_POOL_HARD_CEIL]`.
    """
    eff_cpu = max(1, int(caps.effective_cpu_count))
    chosen_profile = (profile or caps.profile or "small").lower()

    if chosen_profile == "small":
        n = max(1, min(eff_cpu - 1, 2))
    elif chosen_profile == "medium":
        n = max(2, eff_cpu - 2)
    elif chosen_profile == "large":
        n = max(4, eff_cpu - 3)
    elif chosen_profile == "xlarge":
        n = max(8, eff_cpu - 4)
    else:
        # Unknown profile → safe legacy default.
        n = 4

    return max(1, min(n, CPU_POOL_HARD_CEIL))


def would_override() -> bool:
    """Diagnostic: would the adaptive sizer be consulted RIGHT NOW?

    True iff (a) `ENABLE_ADAPTIVE_POOL_SIZING` is ON AND (b) the host
    capability has been detected.  False otherwise.
    """
    import os
    if not bool(flag("ENABLE_ADAPTIVE_POOL_SIZING")):
        return False
    if (os.environ.get("CPU_POOL_SIZE") or "").strip() != "":
        return False  # explicit env pin wins
    return current_caps() is not None


def current_recommendation() -> Optional[int]:
    """Diagnostic: what would the sizer recommend RIGHT NOW for this host?

    Returns None when the host capability is not yet detected.
    """
    caps = current_caps()
    if caps is None:
        return None
    return recommend_pool_size(caps)

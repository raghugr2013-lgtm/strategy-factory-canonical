"""
VPS Scaling P1.A — Skeleton router (PURE FUNCTION, default `accept_all`).

This module is the *advisory* routing decision layer. In P1.A it is a
skeleton that always returns `accept_all` regardless of input band.
Subsequent sub-phases (P1.B–P1.D) will compose additional engines around
it — but the API surface and default policy land here, in P1.A, so
operators can soak the observability layer (heartbeats + bands) without
any behaviour change to existing call sites.

Discipline (per `VPS_SCALING_P1_IMPLEMENTATION_PLAN.md` §1.1 + §1.5):
  * Pure function — no DB writes, no env mutation, no side-effects.
  * Default policy `accept_all` — every call returns `decision="accept"`.
  * `ENABLE_BAND_BASED_ROUTING=false` by default — only when an operator
    explicitly flips it to `true` does the router consult the band.
  * Honest-refusal — `band="unknown"` does NOT silently coerce to `ok`.
    Under band-based policy, `unknown` returns `decision="defer"` with
    `reason="band_unknown"`.
  * The verdict is *advisory*. No engine consults this router in P1.A.
    Wiring into `cpu_pool.submit_cpu` / `auto_factory.run_auto_factory_cycle`
    / `master_bot_deployment.promote_to_live` lands in P1.D.

Verdict shape (caller-stable across sub-phases):

    {
      "decision":    "accept" | "defer" | "refuse",
      "policy":      "accept_all" | "band_based",
      "reason":      <human-readable string>,
      "band":        "ok" | "warn" | "critical" | "unknown" | None,
      "class_":      caller-supplied workload class id (free-string in P1.A),
      "evaluated_at": iso-string,
    }
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engines.feature_flags import flag


POLICY_ACCEPT_ALL = "accept_all"
POLICY_BAND_BASED = "band_based"

DECISION_ACCEPT = "accept"
DECISION_DEFER  = "defer"
DECISION_REFUSE = "refuse"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_policy() -> str:
    """Return the policy this router would apply *right now*.

    Pure function; reads `ENABLE_BAND_BASED_ROUTING` via the centralised
    feature_flags registry. Default policy is `accept_all`.
    """
    return POLICY_BAND_BASED if bool(flag("ENABLE_BAND_BASED_ROUTING")) else POLICY_ACCEPT_ALL


def route(
    *,
    class_: Optional[str] = None,
    band: Optional[str] = None,
    headroom: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return an advisory verdict for the caller. Pure; no I/O.

    Args
    ----
    class_   : caller-supplied workload class id (free-string in P1.A —
               structured enum lands in P1.B `workload_classes.py`).
    band     : explicit band string. When omitted, `headroom["band"]`
               is consulted.
    headroom : a `compute_probe.headroom_summary()` dict; only consulted
               for its `band` field when `band` arg is None.

    Behaviour
    ---------
    Policy = `accept_all` (DEFAULT):
        Always returns DECISION_ACCEPT, regardless of band. This is the
        deliberate P1.A skeleton — no behaviour change for any caller.

    Policy = `band_based` (operator-opt-in via ENABLE_BAND_BASED_ROUTING):
        - band="ok"        → DECISION_ACCEPT
        - band="warn"      → DECISION_DEFER  (advisory; caller may proceed)
        - band="critical"  → DECISION_REFUSE
        - band="unknown"   → DECISION_DEFER  (honest-refusal: never coerce to OK)
        - band missing     → DECISION_DEFER  (treated as "unknown")
    """
    policy = current_policy()
    effective_band = band
    if effective_band is None and isinstance(headroom, dict):
        effective_band = headroom.get("band")

    verdict: Dict[str, Any] = {
        "policy":       policy,
        "band":         effective_band,
        "class_":       class_,
        "evaluated_at": _now_iso(),
    }

    if policy == POLICY_ACCEPT_ALL:
        verdict["decision"] = DECISION_ACCEPT
        verdict["reason"]   = "policy_accept_all"
        return verdict

    # Band-based policy
    if effective_band == "ok":
        verdict["decision"] = DECISION_ACCEPT
        verdict["reason"]   = "band_ok"
    elif effective_band == "warn":
        verdict["decision"] = DECISION_DEFER
        verdict["reason"]   = "band_warn"
    elif effective_band == "critical":
        verdict["decision"] = DECISION_REFUSE
        verdict["reason"]   = "band_critical"
    else:
        # Honest-refusal: unknown / missing band → defer, not accept.
        verdict["decision"] = DECISION_DEFER
        verdict["reason"]   = "band_unknown"
    return verdict

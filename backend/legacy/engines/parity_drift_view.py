"""Master Bot V1 — Parity Drift Aggregator (MB-9 Phase 2.A).

Read-only aggregator that surfaces parity-verdict regressions over a
rolling window.

Data sources (read-only):

  * ``cbot_parity_audit``  — per-event log (multiple rows per
    strategy_hash). This is the **primary timeline source**.
  * ``cbot_parity_signoff`` — latest-verdict snapshot (UNIQUE per
    strategy_hash). Used as a fallback "single anchor" when the
    audit log carries < 2 events for the strategy in question.
  * ``master_bot_deployments`` — per-deployment metadata + state.

Per architecture review §1, MB-9 Phase 2 reads historical sign-offs;
under the institutional schema, the audit collection is the
historical surface while ``cbot_parity_signoff`` carries one current
row per strategy. This module respects that schema verbatim — it
does not mutate either collection.

Discipline:

  * **Read-only.** No writes to any collection. The advisory
    ``parity_drift_status`` field on ``master_bot_deployments`` is
    populated by a future Phase 2.B scheduler — this module computes
    it but does NOT persist it.

  * **Honest refusal.** A deployment with fewer than 2 sign-offs in
    the window is reported with ``decision="insufficient_data"`` —
    never coerced into a green/red verdict.

  * **Window**: env ``RUNNER_PARITY_DRIFT_WINDOW_DAYS`` (default 7).
    Phase-2.B will formalise the flag.

Drift definition:

  Given a deployment's sign-off timeline within the window, drift is
  declared when the most-recent sign-off's verdict is a REGRESSION
  versus the deployment's anchor (the last verdict labelled approved
  / WITHIN_TOLERANCE / passed at deployment promotion time).

  Verdict severity ladder (best → worst):
    WITHIN_TOLERANCE  >  NOT_APPLICABLE  >  ADVISORY_DIVERGED  >  DIVERGED  >  UNKNOWN

  Trade parity:  passed=True is best; passed=False is regression.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)


SIGNOFF_COLL    = "cbot_parity_signoff"
AUDIT_COLL      = "cbot_parity_audit"
DEPLOYMENTS_COLL = "master_bot_deployments"

DEFAULT_WINDOW_DAYS = 7

# Honest verdict labels surfaced by this module.
DECISION_STABLE          = "stable"
DECISION_DRIFTING        = "drifting"
DECISION_RECOVERED       = "recovered"
DECISION_INSUFFICIENT    = "insufficient_data"
DECISION_NO_DEPLOYMENT   = "deployment_not_found"

# HTF verdict severity (best → worst).
_HTF_SEVERITY = {
    "WITHIN_TOLERANCE":   0,
    "NOT_APPLICABLE":     1,
    "ADVISORY_DIVERGED":  2,
    "DIVERGED":           3,
    None:                 4,
    "UNKNOWN":            4,
}


def _window_days() -> int:
    raw = (os.environ.get("RUNNER_PARITY_DRIFT_WINDOW_DAYS") or "").strip()
    try:
        return max(1, int(raw)) if raw else DEFAULT_WINDOW_DAYS
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_DAYS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _htf_severity(verdict: Any) -> int:
    return _HTF_SEVERITY.get(verdict if verdict is None else str(verdict), 4)


def _trade_severity(passed: Any) -> int:
    # True (passed) → 0; anything else → 3 (regression).
    return 0 if passed is True else 3


def _is_regression(prev: Dict[str, Any], curr: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (is_regression, reason)."""
    p_htf = _htf_severity(prev.get("htf_parity_verdict"))
    c_htf = _htf_severity(curr.get("htf_parity_verdict"))
    if c_htf > p_htf:
        return True, f"htf_severity {p_htf}→{c_htf}"
    p_tr = _trade_severity(prev.get("trade_parity_passed"))
    c_tr = _trade_severity(curr.get("trade_parity_passed"))
    if c_tr > p_tr:
        return True, f"trade_severity {p_tr}→{c_tr}"
    return False, ""


def _is_recovery(prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
    p_htf = _htf_severity(prev.get("htf_parity_verdict"))
    c_htf = _htf_severity(curr.get("htf_parity_verdict"))
    p_tr  = _trade_severity(prev.get("trade_parity_passed"))
    c_tr  = _trade_severity(curr.get("trade_parity_passed"))
    return (c_htf < p_htf) or (c_tr < p_tr)


def _summarise_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "signed_at":              row.get("signed_at"),
        "strategy_hash":          row.get("strategy_hash"),
        "status":                 row.get("status"),
        "htf_parity_verdict":     row.get("htf_parity_verdict"),
        "trade_parity_passed":    row.get("trade_parity_passed"),
        "htf_divergence_pct":     row.get("htf_divergence_pct"),
    }


# ── Pure decision function (testable without Mongo) ───────────────────
def decide_drift_from_timeline(
    timeline: List[Dict[str, Any]],
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> Dict[str, Any]:
    """Pure function: given a sorted-asc-by-signed_at timeline of
    sign-off rows for ONE deployment, return the drift decision.
    """
    cutoff = _now() - timedelta(days=max(1, int(window_days)))
    in_window = [
        r for r in timeline
        if (_parse_dt(r.get("signed_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff
    ]
    if len(in_window) < 2:
        return {
            "decision":         DECISION_INSUFFICIENT,
            "window_days":      window_days,
            "rows_in_window":   len(in_window),
            "timeline":         [_summarise_row(r) for r in in_window],
            "reason":           "fewer than 2 sign-offs in window",
        }

    # Anchor = oldest in-window row; current = newest.
    anchor = in_window[0]
    current = in_window[-1]
    regressed, reason = _is_regression(anchor, current)
    if regressed:
        decision = DECISION_DRIFTING
    elif _is_recovery(anchor, current):
        decision = DECISION_RECOVERED
    else:
        decision = DECISION_STABLE
    return {
        "decision":          decision,
        "window_days":       window_days,
        "rows_in_window":    len(in_window),
        "anchor":            _summarise_row(anchor),
        "current":           _summarise_row(current),
        "regression_reason": reason if regressed else None,
        "timeline":          [_summarise_row(r) for r in in_window],
    }


# ── Mongo-backed wrappers (async) ────────────────────────────────────
async def compute_drift_for_deployment(deployment_id: str) -> Dict[str, Any]:
    """Read sign-offs for the deployment's bound strategy across the
    window, then call ``decide_drift_from_timeline``.

    A deployment is keyed to a ``.cbotpack`` whose underlying
    ``strategy_hash`` is the join key against ``cbot_parity_signoff``.
    If the deployment is missing or carries no strategy_hash, return a
    honest-refusal verdict.
    """
    db = get_db()
    dep = await db[DEPLOYMENTS_COLL].find_one(
        {"deployment_id": deployment_id}, {"_id": 0},
    )
    if not dep:
        return {
            "decision":     DECISION_NO_DEPLOYMENT,
            "deployment_id": deployment_id,
            "reason":       "deployment row not found",
        }
    strategy_hash = (
        dep.get("strategy_hash")
        or (dep.get("parity_verdict") or {}).get("strategy_hash")
    )
    if not strategy_hash:
        return {
            "decision":     DECISION_INSUFFICIENT,
            "deployment_id": deployment_id,
            "rows_in_window": 0,
            "reason":        "deployment has no strategy_hash to join",
        }

    window = _window_days()
    cutoff = _now() - timedelta(days=window)
    timeline: List[Dict[str, Any]] = []

    # Primary timeline source: the per-event audit log.
    cursor = db[AUDIT_COLL].find(
        {"strategy_hash": strategy_hash},
        {"_id": 0},
    ).sort("signed_at", 1)
    async for row in cursor:
        dt = _parse_dt(row.get("signed_at"))
        if dt and dt >= cutoff:
            timeline.append(row)

    # Fallback: the latest-verdict snapshot (single anchor) — only if
    # the audit log carries fewer than 2 events for this strategy.
    if len(timeline) < 2:
        signoff = await db[SIGNOFF_COLL].find_one(
            {"strategy_hash": strategy_hash}, {"_id": 0},
        )
        if signoff:
            dt = _parse_dt(signoff.get("signed_at"))
            if dt and dt >= cutoff:
                # Avoid duplicating a row already present in the audit list.
                if not any(
                    r.get("signed_at") == signoff.get("signed_at") for r in timeline
                ):
                    timeline.append(signoff)
            timeline.sort(key=lambda r: _parse_dt(r.get("signed_at"))
                          or datetime.min.replace(tzinfo=timezone.utc))

    verdict = decide_drift_from_timeline(timeline, window_days=window)
    verdict["deployment_id"] = deployment_id
    verdict["strategy_hash"] = strategy_hash
    return verdict


async def compute_drift_for_all_live() -> Dict[str, Any]:
    """Aggregator — drift verdict for every deployment currently
    flagged ``live``. Returns one row per deployment + a roll-up."""
    db = get_db()
    rolls = {"stable": 0, "drifting": 0, "recovered": 0, "insufficient_data": 0,
             "deployment_not_found": 0}
    rows: List[Dict[str, Any]] = []
    async for dep in db[DEPLOYMENTS_COLL].find(
        {"state": "live"}, {"_id": 0, "deployment_id": 1},
    ):
        dep_id = dep.get("deployment_id")
        if not dep_id:
            continue
        d = await compute_drift_for_deployment(dep_id)
        rolls[d.get("decision", "insufficient_data")] = rolls.get(
            d.get("decision", "insufficient_data"), 0
        ) + 1
        rows.append(d)
    return {
        "computed_at": _now().isoformat(),
        "window_days": _window_days(),
        "live_deployments_considered": len(rows),
        "rollup":      rolls,
        "rows":        rows,
    }


__all__ = [
    "SIGNOFF_COLL", "AUDIT_COLL", "DEPLOYMENTS_COLL", "DEFAULT_WINDOW_DAYS",
    "DECISION_STABLE", "DECISION_DRIFTING", "DECISION_RECOVERED",
    "DECISION_INSUFFICIENT", "DECISION_NO_DEPLOYMENT",
    "decide_drift_from_timeline",
    "compute_drift_for_deployment",
    "compute_drift_for_all_live",
]

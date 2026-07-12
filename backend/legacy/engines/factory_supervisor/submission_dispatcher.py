"""
Factory Supervisor FS-P1.1 — Submission dispatcher.

The single entry point for every NEW submission flowing through the
Supervisor. Composes:

    routing_policy.choose_host(workload, fleet_snapshot)
    admission_controller.gate(workload_class)
    supervisor_events.emit(WORK_ROUTED | WORK_DEFERRED | WORK_REFUSED | WORK_REROUTED)

Discipline (operator-locked):
  * DORMANT by default. ENABLE_FACTORY_SUPERVISOR=false ⇒ dispatch()
    returns a bypass verdict (`mode="bypass"`). No persistence; no
    events; no behaviour change for legacy callers.
  * NO refactor of admission_controller / cpu_pool / auto_factory /
    mutation_engine / master_bot_deployment / MB-1..MB-10 wrap sites.
    Those continue to run unchanged through the P1.D admission_wrapper
    path. This dispatcher is *additive* — it is invoked ONLY by
    callers that explicitly opt in (the new `POST /submit` endpoint and
    future Auto-Learning / cTrader telemetry producers).
  * Local short-circuit: when routing_decision==local AND
    admission_controller verdict admits, the dispatch is "accepted"
    and the caller proceeds to run the work locally itself. The
    dispatcher does NOT submit to cpu_pool here — that wiring will
    arrive in FS-P1.2 (defer_queue + worker runtime). For FS-P1.1
    the dispatcher is the *intent layer*: it records the verdict,
    emits the event, and returns the decision to the caller.
  * Multi-node short-circuit: only meaningful when a future policy
    returns assigned_host != local. FS-P1.1 ships only local_only as
    active, so multi-node dispatch records a `mode="remote_stub"`
    outcome — the actual HTTP-RPC submit lands in FS-P1.2.

Persistence:
  * Every dispatch call persists ONE row to
    `factory_supervisor_submissions` (when ENABLE_FACTORY_SUPERVISOR
    is ON) capturing the full envelope + verdict. Read by Copilot to
    answer the six questions in the operator's directive.

Public surface:
    OUTCOME_ACCEPTED / OUTCOME_DEFERRED / OUTCOME_REFUSED / OUTCOME_REROUTED
    SUBMISSIONS_COLLECTION
    is_enabled()
    ensure_indexes() → dict
    dispatch(workload, *, force=False, fleet_snapshot=None) → DispatchVerdict
    list_recent(limit=100, ...) → list[dict]
    stats(window_sec=3600) → dict
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from engines.factory_supervisor import routing_policy, supervisor_events
from engines.factory_supervisor.workload import Workload

logger = logging.getLogger(__name__)

SUBMISSIONS_COLLECTION = "factory_supervisor_submissions"

OUTCOME_ACCEPTED = "accepted"
OUTCOME_DEFERRED = "deferred"
OUTCOME_REFUSED  = "refused"
OUTCOME_REROUTED = "rerouted"

ALL_OUTCOMES = (OUTCOME_ACCEPTED, OUTCOME_DEFERRED, OUTCOME_REFUSED, OUTCOME_REROUTED)


@dataclass
class DispatchVerdict:
    """Result of one dispatch call. Frozen contract."""
    workload_id:       str
    workload_class:    str
    source_module:     str
    correlation_id:    str
    created_at:        str
    priority:          int
    outcome:           str
    mode:              str            # "bypass" | "local" | "remote_stub"
    routing_decision:  Optional[str]  # policy name OR fallback chain
    assigned_host:     Optional[str]
    reason:            str
    retry_after_sec:   Optional[int]
    admission_decision: Optional[str] = None
    admission_reason:   Optional[str] = None
    pressure_band:      Optional[str] = None
    band:               Optional[str] = None
    fallback_from_policy: Optional[str] = None
    persisted:         bool = False
    event_emitted:     bool = False
    rationale:         Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def is_enabled() -> bool:
    """Mirrors ENABLE_FACTORY_SUPERVISOR."""
    try:
        from engines.feature_flags import flag
        return bool(flag("ENABLE_FACTORY_SUPERVISOR"))
    except Exception:                                          # pragma: no cover
        return False


# ─── Indexes ─────────────────────────────────────────────────────────

async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent indexes for `factory_supervisor_submissions`."""
    created, existed, errors = [], [], []
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[SUBMISSIONS_COLLECTION].index_information()
        specs = [
            ("ix_fs_subs_ts",
             [("ts_epoch", DESCENDING)]),
            ("ix_fs_subs_outcome_ts",
             [("outcome", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_fs_subs_class_ts",
             [("workload_class", ASCENDING), ("ts_epoch", DESCENDING)]),
            ("ix_fs_subs_correlation",
             [("correlation_id", ASCENDING)]),
            ("ix_fs_subs_assigned_host_ts",
             [("assigned_host", ASCENDING), ("ts_epoch", DESCENDING)]),
        ]
        for name, keys in specs:
            if name in existing:
                existed.append(name)
                continue
            await db[SUBMISSIONS_COLLECTION].create_index(keys, name=name, background=True)
            created.append(name)
    except Exception as e:                                     # pragma: no cover
        errors.append({"error": str(e)[:200]})
        logger.warning("[submission_dispatcher] ensure_indexes failed: %s", e)
    return {"created": created, "existed": existed, "errors": errors}


# ─── Core dispatch ───────────────────────────────────────────────────

def _outcome_to_event(outcome: str) -> Optional[str]:
    return {
        OUTCOME_ACCEPTED: supervisor_events.EVENT_WORK_ROUTED,
        OUTCOME_DEFERRED: supervisor_events.EVENT_WORK_DEFERRED,
        OUTCOME_REFUSED:  supervisor_events.EVENT_WORK_REFUSED,
        OUTCOME_REROUTED: getattr(supervisor_events, "EVENT_WORK_REROUTED", None),
    }.get(outcome)


async def _run_admission(workload_class: str, force: bool) -> Dict[str, Any]:
    """Call admission_controller.gate(); return verdict dict or
    None if class is unknown. Pure best-effort — admission errors
    fall back to admit=flag_off shape."""
    try:
        from engines import admission_controller
        from engines.workload_classes import WorkloadClass
    except Exception as e:                                     # pragma: no cover
        return {"decision": "admit", "reason": "admission_unavailable", "error": str(e)[:200]}
    # Map workload_class string to enum
    try:
        cls = WorkloadClass(workload_class)
    except Exception:
        return {
            "decision": "admit",
            "reason":   f"class_unmapped:{workload_class}",
        }
    try:
        verdict = admission_controller.gate(cls, force=force)
        return verdict.to_dict()
    except Exception as e:                                     # pragma: no cover
        return {"decision": "admit", "reason": f"gate_error:{e}"[:200]}


async def _persist_submission(
    workload: Workload,
    verdict: DispatchVerdict,
) -> bool:
    """Best-effort write of one row to factory_supervisor_submissions."""
    try:
        from engines.db import get_db
        from engines import host_capability
        db = get_db()
        now = datetime.now(timezone.utc)
        host_id = None
        try:
            caps = host_capability.current()
            if caps is not None:
                host_id = caps.host_id
        except Exception:                                      # pragma: no cover
            host_id = None
        doc: Dict[str, Any] = {
            "workload_id":         workload.workload_id,
            "workload_class":      workload.workload_class,
            "source_module":       workload.source_module,
            "correlation_id":      workload.correlation_id,
            "priority":            workload.priority,
            "target_id":           workload.target_id,
            "pair":                workload.pair,
            "strategy_id":         workload.strategy_id,
            "deployment_id":       workload.deployment_id,
            "deadline_epoch":      workload.deadline_epoch,
            "capabilities_required": list(workload.capabilities_required or []),
            "created_at":          workload.created_at,
            "outcome":             verdict.outcome,
            "mode":                verdict.mode,
            "routing_decision":    verdict.routing_decision,
            "assigned_host":       verdict.assigned_host,
            "fallback_from_policy": verdict.fallback_from_policy,
            "reason":              verdict.reason,
            "retry_after_sec":     verdict.retry_after_sec,
            "admission_decision":  verdict.admission_decision,
            "admission_reason":    verdict.admission_reason,
            "pressure_band":       verdict.pressure_band,
            "band":                verdict.band,
            "rationale":           verdict.rationale,
            "supervisor_host_id":  host_id,
            "ts":                  now.isoformat(),
            "ts_epoch":            now.timestamp(),
            "supervisor_version":  "FS-P1.1",
        }
        await db[SUBMISSIONS_COLLECTION].insert_one(doc)
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[submission_dispatcher] persist failed: %s", e)
        return False


def _fmt_routing_label(rd) -> str:
    """Pretty 'policy[:host]' label for the routing_decision field."""
    if rd is None:
        return "unknown"
    base = rd.policy
    if rd.fallback_from and rd.fallback_from != rd.policy:
        base = f"{rd.fallback_from}->local_only"
    if rd.assigned_host:
        return f"{base}:{rd.assigned_host}"
    return base


async def dispatch(
    workload: Workload,
    *,
    force: bool = False,
    fleet_snapshot: Optional[Dict[str, Any]] = None,
) -> DispatchVerdict:
    """Run the full Supervisor dispatch pipeline.

    Returns a DispatchVerdict; never raises. Persists one row to the
    submissions collection and emits one supervisor_event (both
    best-effort, both gated by ENABLE_FACTORY_SUPERVISOR).
    """
    # Base verdict skeleton (filled progressively).
    base = DispatchVerdict(
        workload_id     = workload.workload_id,
        workload_class  = workload.workload_class,
        source_module   = workload.source_module,
        correlation_id  = workload.correlation_id,
        created_at      = workload.created_at,
        priority        = workload.priority,
        outcome         = OUTCOME_ACCEPTED,
        mode            = "bypass",
        routing_decision = None,
        assigned_host   = None,
        reason          = "",
        retry_after_sec = None,
    )

    # ─ 0. DORMANT short-circuit ───────────────────────────────────
    if not is_enabled():
        base.outcome  = OUTCOME_ACCEPTED
        base.mode     = "bypass"
        base.reason   = "flag_off"
        base.rationale["bypass_reason"] = "ENABLE_FACTORY_SUPERVISOR=false"
        base.rationale["caller_responsibility"] = (
            "legacy admission_wrapper path remains authoritative"
        )
        return base

    # ─ 1. Routing policy ──────────────────────────────────────────
    try:
        rd = routing_policy.choose_host(workload, fleet_snapshot)
    except Exception as e:                                     # pragma: no cover
        rd = None
        logger.debug("[submission_dispatcher] routing_policy raised: %s", e)
    base.routing_decision     = _fmt_routing_label(rd) if rd else "local_only:fallback"
    base.assigned_host        = rd.assigned_host if rd else None
    base.fallback_from_policy = rd.fallback_from if rd else None
    base.rationale["routing"] = rd.to_dict() if rd else {"policy": "local_only", "note": "rd_unavailable"}

    # Annotate workload (advisory; downstream/diagnostics consumers
    # may inspect the envelope).
    workload.routing_decision = base.routing_decision
    workload.assigned_host    = base.assigned_host

    # ─ 2. Admission gate ──────────────────────────────────────────
    adm = await _run_admission(workload.workload_class, force=force)
    base.admission_decision = adm.get("decision")
    base.admission_reason   = adm.get("reason")
    base.pressure_band      = adm.get("pressure_band")
    base.band               = adm.get("band")
    base.rationale["admission"] = adm

    # ─ 3. Mode + outcome reconciliation ───────────────────────────
    # Remote-host stub (multi-node) handling: in FS-P1.1 only local_only
    # is active, so this branch fires ONLY if a future policy bypasses
    # the active check (defensive — we still produce a clean record).
    if rd is not None and rd.assigned_host and _is_remote_assignment(rd):
        base.mode = "remote_stub"
        base.outcome = OUTCOME_REROUTED
        base.reason  = (
            f"routed to {rd.assigned_host}; HTTP-RPC submit stubbed in FS-P1.1"
        )
    else:
        base.mode = "local"
        # Map admission verdict → outcome
        decision = (adm.get("decision") or "admit").lower()
        if decision == "admit":
            base.outcome = OUTCOME_ACCEPTED
            base.reason  = adm.get("reason") or "admitted"
        elif decision == "defer":
            base.outcome = OUTCOME_DEFERRED
            base.reason  = adm.get("reason") or "deferred"
            base.retry_after_sec = adm.get("retry_after_sec") or 30
        elif decision == "refuse":
            base.outcome = OUTCOME_REFUSED
            base.reason  = adm.get("reason") or "refused"
        else:
            base.outcome = OUTCOME_ACCEPTED
            base.reason  = f"unknown_admission_decision:{decision}"

    # ─ 4. Persistence (best-effort) ───────────────────────────────
    base.persisted = await _persist_submission(workload, base)

    # ─ 4b. Defer-queue enqueue (FS-P1.2; flag-gated) ──────────────
    if base.outcome == OUTCOME_DEFERRED:
        try:
            from engines.factory_supervisor import defer_queue
            enq = await defer_queue.enqueue(workload.to_dict(), base.to_dict())
            base.rationale["defer_queue"] = {
                "enqueued": bool(enq.get("enqueued")),
                "row_id":   enq.get("row_id"),
                "skipped":  enq.get("skipped"),
            }
        except Exception as e:                                 # pragma: no cover
            base.rationale["defer_queue"] = {"enqueued": False, "error": str(e)[:200]}

    # ─ 5. Supervisor event emission ───────────────────────────────
    event_type = _outcome_to_event(base.outcome)
    if event_type is not None:
        try:
            emit_out = await supervisor_events.emit(
                event_type,
                payload={
                    "workload_id":    workload.workload_id,
                    "workload_class": workload.workload_class,
                    "source_module":  workload.source_module,
                    "priority":       workload.priority,
                    "assigned_host":  base.assigned_host,
                    "routing_decision": base.routing_decision,
                    "fallback_from_policy": base.fallback_from_policy,
                    "admission_decision":   base.admission_decision,
                    "admission_reason":     base.admission_reason,
                    "pressure_band":        base.pressure_band,
                    "band":                 base.band,
                    "reason":               base.reason,
                    "retry_after_sec":      base.retry_after_sec,
                },
                target_id=workload.target_id,
                correlation_id=workload.correlation_id,
            )
            base.event_emitted = bool(emit_out.get("emitted"))
        except Exception as e:                                 # pragma: no cover
            logger.debug("[submission_dispatcher] emit failed: %s", e)

    return base


def _is_remote_assignment(rd) -> bool:
    """A routing decision is 'remote' if it explicitly chose a non-local
    host AND the active policy returned decision='remote' (FS-P1.1 has
    no such active policy — defensive check)."""
    if rd is None:
        return False
    if rd.decision == "remote":
        return True
    return False


# ─── Read endpoints ──────────────────────────────────────────────────

async def list_recent(
    limit:           int           = 100,
    outcome:         Optional[str] = None,
    workload_class:  Optional[str] = None,
    correlation_id:  Optional[str] = None,
    since_epoch:     Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Read recent submissions. Best-effort; returns [] on Mongo blip."""
    limit = max(1, min(int(limit), 1000))
    q: Dict[str, Any] = {}
    if outcome:
        q["outcome"] = outcome
    if workload_class:
        q["workload_class"] = workload_class
    if correlation_id:
        q["correlation_id"] = correlation_id
    if since_epoch is not None:
        q["ts_epoch"] = {"$gte": float(since_epoch)}
    try:
        from engines.db import get_db
        db = get_db()
        cur = db[SUBMISSIONS_COLLECTION].find(q, {"_id": 0}).sort("ts_epoch", -1).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                     # pragma: no cover
        logger.debug("[submission_dispatcher] list_recent failed: %s", e)
        return []


async def stats(window_sec: int = 3600) -> Dict[str, Any]:
    """Aggregate counts per outcome in the rolling window."""
    window_sec = max(1, min(int(window_sec), 86400 * 30))
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).timestamp()
    per_outcome = {o: 0 for o in ALL_OUTCOMES}
    per_class: Dict[str, int] = {}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        pipeline = [
            {"$match": {"ts_epoch": {"$gte": cutoff}}},
            {"$group": {
                "_id":   {"outcome": "$outcome", "class": "$workload_class"},
                "n":     {"$sum": 1},
            }},
        ]
        async for row in db[SUBMISSIONS_COLLECTION].aggregate(pipeline):
            outcome = (row["_id"] or {}).get("outcome") or "unknown"
            cls = (row["_id"] or {}).get("class") or "unknown"
            n = int(row["n"])
            per_outcome.setdefault(outcome, 0)
            per_outcome[outcome] += n
            per_class.setdefault(cls, 0)
            per_class[cls] += n
            total += n
    except Exception as e:                                     # pragma: no cover
        logger.debug("[submission_dispatcher] stats failed: %s", e)
    return {
        "window_sec":  window_sec,
        "total":       total,
        "per_outcome": per_outcome,
        "per_class":   per_class,
    }

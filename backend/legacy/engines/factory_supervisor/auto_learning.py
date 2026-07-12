"""
Factory Supervisor FS-P1.4 (Auto-Learning Infrastructure) — additive layer.

Connects the four dormant learning components into a single read-only
aggregator that produces RECOMMENDATIONS AND LEARNING INSIGHTS ONLY:

    * engines.risk_of_ruin                — RoR per strategy
    * engines.lifecycle_decay             — aging penalty distribution
    * engines.calibration_framework       — predicted vs realised PP
    * engines.execution_realism_defaults  — operator-decreed cost rows

Operator-locked invariants (per operator directive):
  * Additive only.
  * Default OFF — every consumption gate defaults False.
  * Rollback safe — no migration, no schema change, no auto-bootstrapping.
  * Provider-agnostic — no LLM, no transport, no SDK import.
  * NO execution authority. NO automatic strategy mutation.
  * NO automatic feature activation. NO automatic deployment.
  * NO learning loop. Insights are produced on demand only.
  * Honours the existing operator-directive veto on ENABLE_AUTONOMOUS_DISCOVERY.

The aggregator NEVER writes; it composes a `LearningInsightsReport`
that downstream consumers (Recommendation Engine, Eligibility Signals,
Notification Center fan-out, Architect Dashboard, Copilot Context) may
read. The Notification Center fan-out is the ONLY non-read path and it
is MANUAL: an admin must explicitly POST to /auto-learning/notify; the
module itself never emits.

Public surface:
    LearningInsight                   — frozen-like dataclass
    LearningInsightsReport            — aggregator output (dataclass)
    SEVERITY_*                        — constants
    is_enabled()                      — consumption gate
    is_loop_enabled()                 — auto-loop gate (always False today)
    flag_manifest()                   — flag snapshot for /status
    build_report(ctx=None)            — async, pure aggregator
    generate_insights(report)         — pure converter from report → insights
    to_recommendations(insights)      — pure converter to Recommendation dataclasses
    fan_out_to_notifications(...)     — MANUAL fan-out (admin-triggered only)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Severity constants (mirror architect_advisor severities) ───────

SEVERITY_INFO       = "info"
SEVERITY_SUGGESTION = "suggestion"
SEVERITY_WARN       = "warn"
SEVERITY_CRITICAL   = "critical"


# ─── Public dataclasses ─────────────────────────────────────────────


@dataclass
class LearningInsight:
    """A single read-only learning insight produced by the aggregator.

    Insights NEVER carry execution authority. The `suggested_action`
    field is operator-facing prose only; the activation pathway (if
    any) still has to traverse Feature Activation Governance.
    """
    kind:             str
    severity:         str
    title:            str
    detail:           str
    suggested_action: str = ""
    evidence:         Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LearningInsightsReport:
    """Aggregated read-only snapshot of the four dormant learning
    components. Includes raw component snapshots PLUS a derived
    `insights` list. NEVER cached on disk — recomputed per request."""
    evaluated_at:    str
    advisory_only:   bool
    is_loop_enabled: bool
    components: Dict[str, Any] = field(default_factory=dict)
    insights:    List[Dict[str, Any]] = field(default_factory=list)
    flags:       Dict[str, Any] = field(default_factory=dict)
    sources:     Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Consumption gating ─────────────────────────────────────────────


def is_enabled() -> bool:
    """Consumption gate for the Auto-Learning Insights aggregator.

    Aggregation itself ALWAYS runs (read-only / safe) but downstream
    consumers (Copilot, FAG, Recommendation Engine) MUST honour the
    returned advisory flag.
    """
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_AUTO_LEARNING"))
    except Exception:                                                # pragma: no cover
        return False


def is_loop_enabled() -> bool:
    """Auto-loop gate — operator directive keeps this OFF forever (today).

    Even if someone later flips FS_ENABLE_AUTO_LEARNING_LOOP to True,
    the operator's `ENABLE_AUTONOMOUS_DISCOVERY` veto still wins.
    Returns True iff BOTH the loop flag AND the autonomous-discovery
    gate are ON — and the loop flag itself defaults False.
    """
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        if not bool(flag("FS_ENABLE_AUTO_LEARNING_LOOP")):
            return False
        # Operator directive veto — must be honoured.
        if not bool(flag("ENABLE_AUTONOMOUS_DISCOVERY")):
            return False
        return True
    except Exception:                                                # pragma: no cover
        return False


def flag_manifest() -> Dict[str, Any]:
    """Snapshot of the Auto-Learning-related flags (for /status)."""
    try:
        from engines.feature_flags import flag
        return {
            "FS_ENABLE_AUTO_LEARNING":          bool(flag("FS_ENABLE_AUTO_LEARNING")),
            "FS_ENABLE_AUTO_LEARNING_LOOP":     bool(flag("FS_ENABLE_AUTO_LEARNING_LOOP")),
            "FS_AUTO_LEARNING_ROR_THRESHOLD":   float(flag("FS_AUTO_LEARNING_ROR_THRESHOLD")),
            "FS_AUTO_LEARNING_AGING_THRESHOLD": float(flag("FS_AUTO_LEARNING_AGING_THRESHOLD")),
            "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES": int(
                flag("FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES")
            ),
            # Read-only echo of the four dormant components' own gates.
            "ENABLE_RISK_OF_RUIN":                   bool(flag("ENABLE_RISK_OF_RUIN")),
            "RISK_OF_RUIN_WEIGHT":                   float(flag("RISK_OF_RUIN_WEIGHT")),
            "ENABLE_AGING_PENALTY":                  bool(flag("ENABLE_AGING_PENALTY")),
            "ENABLE_AGING_AUTO_DEMOTION":            bool(flag("ENABLE_AGING_AUTO_DEMOTION")),
            "ENABLE_CALIBRATION":                    bool(flag("ENABLE_CALIBRATION")),
            "ENABLE_EXECUTION_REALISM_DEFAULTS":     bool(flag("ENABLE_EXECUTION_REALISM_DEFAULTS")),
            # The operator's hard veto on the loop.
            "ENABLE_AUTONOMOUS_DISCOVERY":           bool(flag("ENABLE_AUTONOMOUS_DISCOVERY")),
        }
    except Exception as e:                                           # pragma: no cover
        return {"error": str(e)[:200]}


# ─── Best-effort component readers ──────────────────────────────────


async def _read_risk_of_ruin(limit: int = 50) -> Dict[str, Any]:
    """List recent RoR evaluations + summary stats. Never raises."""
    out: Dict[str, Any] = {
        "available":   False,
        "rows":        [],
        "summary":     {},
        "weight":      0.0,
        "is_active":   False,
    }
    try:
        from engines import risk_of_ruin
        rows = await risk_of_ruin.list_evaluations(limit=limit)
        out["rows"] = rows
        out["weight"] = risk_of_ruin.deploy_score_weight()
        out["is_active"] = out["weight"] > 0.0
        out["available"] = True
        # Lightweight summary — count + worst RoR observed.
        worst = None
        for r in rows:
            cf = r.get("closed_form_ror")
            mc = (r.get("monte_carlo") or {}).get("ror")
            for v in (cf, mc):
                if isinstance(v, (int, float)) and (worst is None or v > worst):
                    worst = float(v)
        out["summary"] = {
            "count":           len(rows),
            "worst_ror":       worst,
            "weight_in_deploy_score": out["weight"],
        }
    except Exception as e:                                           # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_lifecycle_decay() -> Dict[str, Any]:
    """Read-only aging distribution. Never raises."""
    out: Dict[str, Any] = {"available": False, "distribution": {}, "is_active": False}
    try:
        from engines import lifecycle_decay
        out["is_active"] = lifecycle_decay.is_active()
        dist = await lifecycle_decay.get_distribution()
        out["distribution"] = dist
        out["available"] = True
    except Exception as e:                                           # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_calibration() -> Dict[str, Any]:
    """Read-only calibration diagnostics. Never raises."""
    out: Dict[str, Any] = {"available": False, "diagnostics": {}, "is_active": False}
    try:
        from engines import calibration_framework
        diag = await calibration_framework.diagnostics()
        out["diagnostics"] = diag
        out["is_active"] = bool(diag.get("is_active"))
        out["available"] = True
    except Exception as e:                                           # pragma: no cover
        out["error"] = str(e)[:200]
    return out


async def _read_execution_realism(limit: int = 50) -> Dict[str, Any]:
    """Read-only operator-decreed realism rows + count. Never raises."""
    out: Dict[str, Any] = {"available": False, "rows": [], "count": 0, "is_active": False}
    try:
        from engines import execution_realism_defaults
        out["is_active"] = execution_realism_defaults.is_enabled()
        out["count"] = await execution_realism_defaults.count_defaults()
        out["rows"] = await execution_realism_defaults.list_defaults(limit=limit)
        out["available"] = True
    except Exception as e:                                           # pragma: no cover
        out["error"] = str(e)[:200]
    return out


# ─── Aggregate report builder ───────────────────────────────────────


async def build_report(
    *,
    ror_limit: int = 50,
    realism_limit: int = 50,
) -> LearningInsightsReport:
    """Compose the read-only Auto-Learning report.

    Pure aggregator: composes existing dormant component readers; never
    mutates anything. Safe to call regardless of flag state — the report
    carries `advisory_only=true` when consumption is gated OFF.
    """
    from datetime import datetime, timezone

    ror      = await _read_risk_of_ruin(limit=ror_limit)
    lifecyc  = await _read_lifecycle_decay()
    calib    = await _read_calibration()
    realism  = await _read_execution_realism(limit=realism_limit)
    sources = {
        "risk_of_ruin":               "ok" if not ror.get("error") else "error",
        "lifecycle_decay":            "ok" if not lifecyc.get("error") else "error",
        "calibration_framework":      "ok" if not calib.get("error") else "error",
        "execution_realism_defaults": "ok" if not realism.get("error") else "error",
    }

    report = LearningInsightsReport(
        evaluated_at    = datetime.now(timezone.utc).isoformat(),
        advisory_only   = not is_enabled(),
        is_loop_enabled = is_loop_enabled(),
        components      = {
            "risk_of_ruin":               ror,
            "lifecycle_decay":            lifecyc,
            "calibration_framework":      calib,
            "execution_realism_defaults": realism,
        },
        flags    = flag_manifest(),
        sources  = sources,
    )
    report.insights = [i.to_dict() for i in generate_insights(report)]
    return report


# ─── Insight generators (one per learning component) ────────────────


def _ror_insight(report: LearningInsightsReport) -> Optional[LearningInsight]:
    ror = report.components.get("risk_of_ruin") or {}
    if not ror.get("available"):
        return None
    worst = (ror.get("summary") or {}).get("worst_ror")
    count = int((ror.get("summary") or {}).get("count") or 0)
    if count == 0:
        return LearningInsight(
            kind="ROR_NO_EVALUATIONS",
            severity=SEVERITY_INFO,
            title="Risk-of-Ruin: no evaluations recorded",
            detail=(
                "The Risk-of-Ruin engine has not persisted any "
                "evaluations. Diagnostic-only signal; no action required."
            ),
            suggested_action=(
                "Trigger evaluations via the latent API or wait for "
                "auto-population by the survivor pipeline once activated."
            ),
            evidence={"weight_in_deploy_score": ror.get("weight")},
        )
    try:
        from engines.feature_flags import flag
        threshold = float(flag("FS_AUTO_LEARNING_ROR_THRESHOLD"))
    except Exception:                                                # pragma: no cover
        threshold = 0.10
    if worst is not None and worst >= threshold:
        return LearningInsight(
            kind="ROR_THRESHOLD_BREACH",
            severity=SEVERITY_WARN,
            title=f"Risk-of-Ruin worst value {worst:.3f} ≥ {threshold:.3f}",
            detail=(
                "At least one recently-evaluated strategy carries a "
                "RoR above the operator-defined threshold. This is "
                "advisory only — RoR weight in deploy_score is "
                f"{ror.get('weight')}; no automatic action will be taken."
            ),
            suggested_action=(
                "Review recent RoR evaluations in /api/latent/risk_of_ruin; "
                "operator may file a FAG proposal to raise RISK_OF_RUIN_WEIGHT."
            ),
            evidence={"worst_ror": worst, "threshold": threshold,
                      "count": count, "weight": ror.get("weight")},
        )
    return LearningInsight(
        kind="ROR_WITHIN_BAND",
        severity=SEVERITY_INFO,
        title=f"Risk-of-Ruin within operator band ({count} samples)",
        detail="RoR samples remain below the configured threshold.",
        suggested_action="",
        evidence={"worst_ror": worst, "threshold": threshold, "count": count},
    )


def _lifecycle_insight(report: LearningInsightsReport) -> Optional[LearningInsight]:
    lc = report.components.get("lifecycle_decay") or {}
    if not lc.get("available"):
        return None
    dist = lc.get("distribution") or {}
    rows = dist.get("rows") or []
    if not rows:
        return LearningInsight(
            kind="LIFECYCLE_NO_ROWS",
            severity=SEVERITY_INFO,
            title="Lifecycle decay: no strategies tracked",
            detail="The lifecycle decay surface has no rows to inspect.",
            evidence={"count": 0},
        )
    try:
        from engines.feature_flags import flag
        threshold = float(flag("FS_AUTO_LEARNING_AGING_THRESHOLD"))
    except Exception:                                                # pragma: no cover
        threshold = 0.6
    stale = [r for r in rows if (r.get("aging_penalty") or 0.0) >= threshold]
    if stale:
        return LearningInsight(
            kind="LIFECYCLE_STALE_CANDIDATES",
            severity=SEVERITY_SUGGESTION,
            title=f"{len(stale)} strategies past aging threshold ({threshold:.2f})",
            detail=(
                "Strategies with aging_penalty above the threshold may "
                "warrant revalidation. The aging_penalty signal is "
                "diagnostic-only unless ENABLE_AGING_PENALTY is flipped ON."
            ),
            suggested_action=(
                "Open the lifecycle dashboard; operator may schedule a "
                "revalidation pass. No automatic demotion will be taken."
            ),
            evidence={"stale_count": len(stale), "threshold": threshold,
                      "is_active": lc.get("is_active")},
        )
    return LearningInsight(
        kind="LIFECYCLE_OK",
        severity=SEVERITY_INFO,
        title=f"Lifecycle decay nominal ({len(rows)} rows scanned)",
        detail="No strategies exceed the configured aging threshold.",
        evidence={"count": len(rows), "threshold": threshold,
                  "is_active": lc.get("is_active")},
    )


def _calibration_insight(report: LearningInsightsReport) -> Optional[LearningInsight]:
    cal = report.components.get("calibration_framework") or {}
    if not cal.get("available"):
        return None
    diag = cal.get("diagnostics") or {}
    total = int(diag.get("outcomes_total") or 0)
    resolved = int(diag.get("outcomes_resolved") or 0)
    try:
        from engines.feature_flags import flag
        min_outcomes = int(flag("FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES"))
    except Exception:                                                # pragma: no cover
        min_outcomes = 30
    if total == 0:
        return LearningInsight(
            kind="CALIBRATION_NO_DATA",
            severity=SEVERITY_INFO,
            title="Calibration framework: no predictions recorded",
            detail="No predictions persisted yet — calibration is still latent.",
            suggested_action=(
                "Pass_probability emitters may persist predictions once "
                "the survivor pipeline runs."
            ),
            evidence={"outcomes_total": total},
        )
    if resolved < min_outcomes:
        return LearningInsight(
            kind="CALIBRATION_INSUFFICIENT_OUTCOMES",
            severity=SEVERITY_INFO,
            title=f"Calibration evidence still thin ({resolved}/{min_outcomes})",
            detail=(
                "Insufficient resolved outcomes — the calibration table "
                "returns identity for sparse bins."
            ),
            evidence={"resolved": resolved, "required": min_outcomes,
                      "is_active": cal.get("is_active")},
        )
    return LearningInsight(
        kind="CALIBRATION_READY",
        severity=SEVERITY_SUGGESTION,
        title=f"Calibration table ready ({resolved} outcomes)",
        detail=(
            "Sufficient outcomes are available to consult the calibration "
            "table. ENABLE_CALIBRATION remains operator-gated."
        ),
        suggested_action=(
            "Operator may file a FAG proposal to flip ENABLE_CALIBRATION."
        ),
        evidence={"resolved": resolved, "is_active": cal.get("is_active")},
    )


def _realism_insight(report: LearningInsightsReport) -> Optional[LearningInsight]:
    r = report.components.get("execution_realism_defaults") or {}
    if not r.get("available"):
        return None
    count = int(r.get("count") or 0)
    if count == 0:
        return LearningInsight(
            kind="REALISM_NO_OVERRIDES",
            severity=SEVERITY_INFO,
            title="Execution realism: no per-pair overrides",
            detail=(
                "The execution-realism registry has no operator-decreed "
                "rows. The engine falls back to the zero-cost default."
            ),
            suggested_action=(
                "Upsert per-(pair, broker_class) realism defaults via "
                "the admin endpoint when broker quotes are available."
            ),
            evidence={"count": count, "is_active": r.get("is_active")},
        )
    return LearningInsight(
        kind="REALISM_OVERRIDES_PRESENT",
        severity=SEVERITY_INFO,
        title=f"Execution realism: {count} per-pair override(s) registered",
        detail=(
            "Operator-decreed realism rows are present. The registry "
            "remains DORMANT — no engine consults it until "
            "ENABLE_EXECUTION_REALISM_DEFAULTS is flipped ON."
        ),
        evidence={"count": count, "is_active": r.get("is_active")},
    )


def _directive_insight(report: LearningInsightsReport) -> LearningInsight:
    """Always include the operator-directive echo so any consumer that
    walks the report sees the hard veto explicitly."""
    return LearningInsight(
        kind="AUTO_LEARNING_LOOP_GATED",
        severity=SEVERITY_INFO,
        title="Auto-Learning loop is GATED OFF (operator directive)",
        detail=(
            "The Auto-Learning Infrastructure is built and consumable as "
            "insights, but the execution loop is strictly OFF per operator "
            "policy. No automatic strategy mutation, deployment, or "
            "feature activation can occur."
        ),
        suggested_action=(
            "Insights are advisory. Any activation pathway still requires "
            "an operator-approved FAG proposal."
        ),
        evidence={"is_loop_enabled": report.is_loop_enabled,
                  "operator_directive": "off",
                  "flag_snapshot": report.flags},
    )


def generate_insights(report: LearningInsightsReport) -> List[LearningInsight]:
    """Convert the aggregated report into a deterministic insight list.

    Pure function. No DB reads. No mutation. Skips component-level
    insights when the corresponding component reader is unavailable.
    Always includes the operator-directive echo at the end so any
    downstream walker sees the hard veto.
    """
    out: List[LearningInsight] = []
    for builder in (_ror_insight, _lifecycle_insight, _calibration_insight, _realism_insight):
        try:
            insight = builder(report)
        except Exception as e:                                       # pragma: no cover
            logger.debug("[auto_learning] %s failed: %s", builder.__name__, e)
            insight = None
        if insight is not None:
            out.append(insight)
    out.append(_directive_insight(report))
    return out


# ─── Conversion to Recommendation dataclasses ───────────────────────


def to_recommendations(insights: List[LearningInsight]) -> List[Dict[str, Any]]:
    """Convert insights into Recommendation-shaped dicts (no Recommendation
    import required at call-site)."""
    out: List[Dict[str, Any]] = []
    for ins in insights or []:
        out.append({
            "code":          f"AUTO_LEARNING:{ins.kind}",
            "severity":      ins.severity,
            "title":         ins.title,
            "detail":        ins.detail,
            "suggested_fix": ins.suggested_action,
            "evidence":      dict(ins.evidence or {}),
        })
    return out


# ─── Manual fan-out to Notification Center (admin-triggered only) ───


async def fan_out_to_notifications(
    insights: List[LearningInsight],
    *,
    user: Optional[Dict[str, Any]] = None,
    severity_floor: str = SEVERITY_SUGGESTION,
) -> Dict[str, Any]:
    """Manually emit insights as Notification Center events.

    *** ADMIN-TRIGGERED ONLY. ***  The aggregator NEVER calls this
    automatically. The API endpoint that calls this requires admin
    auth + an explicit POST. Best-effort emit; never raises.
    """
    if not insights:
        return {"emitted": 0, "skipped": 0, "reason": "no_insights"}
    floor_rank = {"info": 0, "suggestion": 1, "warn": 2, "critical": 3}.get(
        severity_floor, 1,
    )
    emitted = 0
    skipped = 0
    try:
        from engines.factory_supervisor import supervisor_events
    except Exception as e:                                           # pragma: no cover
        return {"emitted": 0, "skipped": len(insights),
                "reason": f"events_unavailable: {e}"[:200]}
    actor = (user or {}).get("email") or "operator"
    for ins in insights:
        rank = {"info": 0, "suggestion": 1, "warn": 2, "critical": 3}.get(
            ins.severity, 0,
        )
        if rank < floor_rank:
            skipped += 1
            continue
        # supervisor_events.emit() does not accept a freeform severity
        # vocabulary; map "suggestion" → "info" for the event severity.
        sev_for_event = ins.severity if ins.severity in ("info", "warn", "critical") else "info"
        try:
            await supervisor_events.emit(
                event_type="WORK_ROUTED",   # generic; payload kind is the discriminator
                target_id=f"auto_learning:{ins.kind}",
                payload={
                    "kind":             "auto_learning_insight",
                    "title":            ins.title,
                    "detail":           ins.detail,
                    "insight_kind":     ins.kind,
                    "severity":         ins.severity,
                    "evidence":         ins.evidence,
                    "suggested_action": ins.suggested_action,
                    "triggered_by":     actor,
                },
                severity=sev_for_event,
                category="recommendation",
            )
            emitted += 1
        except Exception as e:                                       # pragma: no cover
            logger.debug("[auto_learning] fan_out emit failed: %s", e)
            skipped += 1
    return {"emitted": emitted, "skipped": skipped, "triggered_by": actor}


__all__ = [
    "LearningInsight",
    "LearningInsightsReport",
    "SEVERITY_INFO",
    "SEVERITY_SUGGESTION",
    "SEVERITY_WARN",
    "SEVERITY_CRITICAL",
    "is_enabled",
    "is_loop_enabled",
    "flag_manifest",
    "build_report",
    "generate_insights",
    "to_recommendations",
    "fan_out_to_notifications",
]

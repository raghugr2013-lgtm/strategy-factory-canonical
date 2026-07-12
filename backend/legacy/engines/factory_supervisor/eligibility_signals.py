"""
Factory Supervisor FS-P1.4 — Eligibility Signals registry.

Per-feature activation readiness signals. Each signal is a pure
function `CopilotContext → EligibilityVerdict` that answers:

    "Are the prerequisites for activating this feature satisfied?"

The engine NEVER activates anything; it only reports the verdict.
Feature Activation Governance (`fag_proposals`) translates a
satisfied verdict into a proposal — which itself still requires
operator approval before activation.

Operator-locked invariants:
  * READ-ONLY signals. Pure functions of the context. No DB writes.
  * Default OFF — eligibility verdicts are advisory only when
    `FS_ENABLE_FAG_ENGINE=false`.
  * Provider-agnostic — no transport / LLM call.

Registry shape:
    SIGNAL_REGISTRY: Dict[feature_name, SignalSpec]

    SignalSpec.evaluator(ctx) -> EligibilityVerdict
    EligibilityVerdict {feature, eligible, reasons, evidence, suggested_proposal_kind}

Public surface:
    EligibilityVerdict, SignalSpec, SIGNAL_REGISTRY
    is_enabled()
    evaluate(feature_name, ctx)        → EligibilityVerdict
    evaluate_all(ctx)                  → List[EligibilityVerdict]
    list_features()                    → List[str]
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List

from engines.factory_supervisor.copilot_context import CopilotContext

logger = logging.getLogger(__name__)


@dataclass
class EligibilityVerdict:
    feature:    str
    eligible:   bool
    reasons:    List[str] = field(default_factory=list)
    evidence:   Dict[str, Any] = field(default_factory=dict)
    suggested_proposal_kind: str = "feature_flag_flip"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SignalSpec:
    feature:        str
    flag_name:      str
    intent:         str
    evaluator:      Callable[[CopilotContext], EligibilityVerdict]


def is_enabled() -> bool:
    """Consumption gate for the FAG eligibility engine."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_FAG_ENGINE"))
    except Exception:                                            # pragma: no cover
        return False


# ─── Per-feature evaluators ─────────────────────────────────────────


def _ev_band_based_routing(ctx: CopilotContext) -> EligibilityVerdict:
    fleet_band = (ctx.fleet or {}).get("fleet_band") or "unknown"
    fag_flags  = (ctx.feature_flags or {}).get("fag_flags") or {}
    already_on = bool(fag_flags.get("ENABLE_BAND_BASED_ROUTING"))
    reasons: List[str] = []
    if already_on:
        reasons.append("already_active")
    if fleet_band == "critical":
        reasons.append("fleet_band_critical")
    eligible = (not already_on) and fleet_band in ("ok", "warn")
    return EligibilityVerdict(
        feature="ENABLE_BAND_BASED_ROUTING",
        eligible=eligible,
        reasons=reasons or (["ok"] if eligible else []),
        evidence={"fleet_band": fleet_band, "already_active": already_on},
    )


def _ev_admission_control(ctx: CopilotContext) -> EligibilityVerdict:
    fag_flags  = (ctx.feature_flags or {}).get("fag_flags") or {}
    already_on = bool(fag_flags.get("ENABLE_ADMISSION_CONTROL"))
    adm_total  = int((ctx.admission or {}).get("stats", {}).get("total", 0))
    enough     = adm_total >= 50   # require some admission history
    reasons: List[str] = []
    if already_on:
        reasons.append("already_active")
    if not enough:
        reasons.append(f"admission_journal_too_thin ({adm_total} < 50)")
    eligible = (not already_on) and enough
    return EligibilityVerdict(
        feature="ENABLE_ADMISSION_CONTROL",
        eligible=eligible,
        reasons=reasons or (["ok"] if eligible else []),
        evidence={"admission_total": adm_total, "already_active": already_on},
    )


def _ev_adaptive_pool_sizing(ctx: CopilotContext) -> EligibilityVerdict:
    fag_flags  = (ctx.feature_flags or {}).get("fag_flags") or {}
    already_on = bool(fag_flags.get("ENABLE_ADAPTIVE_POOL_SIZING"))
    fleet_band = (ctx.fleet or {}).get("fleet_band") or "unknown"
    has_window = (ctx.fleet or {}).get("hosts")  # any fleet at all
    reasons: List[str] = []
    if already_on:
        reasons.append("already_active")
    if not has_window:
        reasons.append("no_hosts_registered")
    if fleet_band == "critical":
        reasons.append("fleet_band_critical")
    eligible = (not already_on) and bool(has_window) and fleet_band in ("ok", "warn", "unknown")
    return EligibilityVerdict(
        feature="ENABLE_ADAPTIVE_POOL_SIZING",
        eligible=eligible,
        reasons=reasons or (["ok"] if eligible else []),
        evidence={"fleet_band": fleet_band, "has_hosts": bool(has_window),
                  "already_active": already_on},
    )


def _ev_autonomous_discovery(ctx: CopilotContext) -> EligibilityVerdict:
    """Auto-Learning — the operator's strict policy keeps this OFF.

    The signal STILL evaluates honestly so the dashboard can show
    "auto-learning eligible but disabled" — but the verdict's
    `evidence` carries an operator_directive override that FAG MUST
    treat as a hard veto in any auto-observe loop.
    """
    al_flags   = (ctx.feature_flags or {}).get("auto_learning_flags") or {}
    already_on = bool(al_flags.get("ENABLE_AUTONOMOUS_DISCOVERY"))
    fleet_band = (ctx.fleet or {}).get("fleet_band") or "unknown"
    dq_pending = int((ctx.blocked or {}).get("defer_queue_pending", 0))
    reasons: List[str] = ["operator_directive_off"]
    if already_on:
        reasons.append("already_active")
    if fleet_band == "critical":
        reasons.append("fleet_band_critical")
    if dq_pending >= 50:
        reasons.append(f"queue_backlog_too_high ({dq_pending})")
    # `eligible=True` reflects the technical readiness; FAG must still
    # honour the directive_off veto.
    technically_eligible = (
        (not already_on)
        and fleet_band in ("ok", "warn", "unknown")
        and dq_pending < 50
    )
    return EligibilityVerdict(
        feature="ENABLE_AUTONOMOUS_DISCOVERY",
        eligible=technically_eligible,
        reasons=reasons,
        evidence={"operator_directive": "off",
                  "queue_backlog": dq_pending,
                  "fleet_band": fleet_band,
                  "already_active": already_on},
        suggested_proposal_kind="operator_directive_gated",
    )


def _ev_copilot_advanced(ctx: CopilotContext) -> EligibilityVerdict:
    """Advanced Intelligence Copilot layer — built but OFF."""
    fs_flags    = (ctx.feature_flags or {}).get("fs_flags") or {}
    already_on  = bool(fs_flags.get("FS_ENABLE_COPILOT_ADVANCED"))
    op_layer_on = bool(fs_flags.get("FS_ENABLE_COPILOT"))
    provider    = fs_flags.get("FS_COPILOT_PROVIDER") or "none"
    reasons: List[str] = []
    if already_on:
        reasons.append("already_active")
    if not op_layer_on:
        reasons.append("operational_copilot_off")
    if provider in (None, "", "none"):
        reasons.append("no_provider_registered")
    eligible = (not already_on) and op_layer_on and provider not in (None, "", "none")
    return EligibilityVerdict(
        feature="FS_ENABLE_COPILOT_ADVANCED",
        eligible=eligible,
        reasons=reasons or (["ok"] if eligible else []),
        evidence={"provider": provider, "operational_layer_on": op_layer_on,
                  "already_active": already_on},
    )


def _ev_auto_learning_loop(ctx: CopilotContext) -> EligibilityVerdict:
    """Auto-Learning loop — strictly OFF per operator directive.

    Mirrors `_ev_autonomous_discovery` for the dedicated Auto-Learning
    loop gate. The signal honestly evaluates technical readiness so the
    dashboard can show 'auto-learning eligible but disabled', but the
    `evidence.operator_directive` veto is a HARD STOP for FAG.
    """
    fs_flags    = (ctx.feature_flags or {}).get("fs_flags") or {}
    al_flags    = (ctx.feature_flags or {}).get("auto_learning_flags") or {}
    already_on  = bool(fs_flags.get("FS_ENABLE_AUTO_LEARNING_LOOP"))
    aggregator  = bool(fs_flags.get("FS_ENABLE_AUTO_LEARNING"))
    directive   = bool(al_flags.get("ENABLE_AUTONOMOUS_DISCOVERY"))
    fleet_band  = (ctx.fleet or {}).get("fleet_band") or "unknown"
    reasons: List[str] = ["operator_directive_off"]
    if already_on:
        reasons.append("already_active")
    if not aggregator:
        reasons.append("aggregator_off")
    if fleet_band == "critical":
        reasons.append("fleet_band_critical")
    technically_eligible = (
        (not already_on)
        and aggregator
        and directive
        and fleet_band in ("ok", "warn", "unknown")
    )
    return EligibilityVerdict(
        feature="FS_ENABLE_AUTO_LEARNING_LOOP",
        eligible=technically_eligible,
        reasons=reasons,
        evidence={"operator_directive": "off",
                  "aggregator_on": aggregator,
                  "fleet_band": fleet_band,
                  "already_active": already_on},
        suggested_proposal_kind="operator_directive_gated",
    )


# ─── Registry ───────────────────────────────────────────────────────


SIGNAL_REGISTRY: Dict[str, SignalSpec] = {
    "ENABLE_BAND_BASED_ROUTING": SignalSpec(
        feature="ENABLE_BAND_BASED_ROUTING",
        flag_name="ENABLE_BAND_BASED_ROUTING",
        intent="Activate band-based routing once fleet stabilises.",
        evaluator=_ev_band_based_routing,
    ),
    "ENABLE_ADMISSION_CONTROL": SignalSpec(
        feature="ENABLE_ADMISSION_CONTROL",
        flag_name="ENABLE_ADMISSION_CONTROL",
        intent="Activate admission control once a sample journal exists.",
        evaluator=_ev_admission_control,
    ),
    "ENABLE_ADAPTIVE_POOL_SIZING": SignalSpec(
        feature="ENABLE_ADAPTIVE_POOL_SIZING",
        flag_name="ENABLE_ADAPTIVE_POOL_SIZING",
        intent="Activate adaptive pool sizing when fleet has telemetry.",
        evaluator=_ev_adaptive_pool_sizing,
    ),
    "ENABLE_AUTONOMOUS_DISCOVERY": SignalSpec(
        feature="ENABLE_AUTONOMOUS_DISCOVERY",
        flag_name="ENABLE_AUTONOMOUS_DISCOVERY",
        intent=(
            "Auto-Learning queue drain — built but strictly OFF per "
            "operator decree. FAG MUST treat the directive veto as hard."
        ),
        evaluator=_ev_autonomous_discovery,
    ),
    "FS_ENABLE_COPILOT_ADVANCED": SignalSpec(
        feature="FS_ENABLE_COPILOT_ADVANCED",
        flag_name="FS_ENABLE_COPILOT_ADVANCED",
        intent="Advanced Intelligence Copilot layer — built but OFF.",
        evaluator=_ev_copilot_advanced,
    ),
    "FS_ENABLE_AUTO_LEARNING_LOOP": SignalSpec(
        feature="FS_ENABLE_AUTO_LEARNING_LOOP",
        flag_name="FS_ENABLE_AUTO_LEARNING_LOOP",
        intent=(
            "Auto-Learning Infrastructure loop — built (insights only) "
            "but strictly OFF per operator decree. FAG MUST treat the "
            "directive veto as a hard stop."
        ),
        evaluator=_ev_auto_learning_loop,
    ),
}


def list_features() -> List[str]:
    return list(SIGNAL_REGISTRY.keys())


def evaluate(feature_name: str, ctx: CopilotContext) -> EligibilityVerdict:
    spec = SIGNAL_REGISTRY.get(feature_name)
    if spec is None:
        return EligibilityVerdict(
            feature=feature_name,
            eligible=False,
            reasons=["unknown_feature"],
            evidence={},
        )
    try:
        return spec.evaluator(ctx)
    except Exception as e:                                       # pragma: no cover
        logger.debug("[eligibility_signals] %s evaluator failed: %s", feature_name, e)
        return EligibilityVerdict(
            feature=feature_name,
            eligible=False,
            reasons=[f"evaluator_failed: {e}"[:200]],
            evidence={},
        )


def evaluate_all(ctx: CopilotContext) -> List[EligibilityVerdict]:
    return [evaluate(name, ctx) for name in SIGNAL_REGISTRY.keys()]

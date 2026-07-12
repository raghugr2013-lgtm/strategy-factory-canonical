"""
Factory Supervisor FS-P1.4 — Recommendation engine.

A deeper rule-based engine that complements `architect_advisor` (which
covers operational health). This engine derives recommendations that
require cross-collection insight (strongest strategy / master bot /
pair / activation-ready feature). Output is always a list of
`Recommendation` dataclass instances; ranking is deterministic
(severity-desc, then code-asc).

Operator-locked invariants:
  * READ-ONLY. The engine consumes the immutable `CopilotContext`
    (built from `system_state_view`) plus best-effort optional Mongo
    reads (with safe fallbacks). NEVER mutates state. NEVER emits.
  * Default OFF — when `FS_ENABLE_COPILOT=false`, the engine still
    runs (read-only is safe) but downstream consumers MUST honour
    the `advisory_only` flag carried by the context.
  * Provider/transport-neutral. No LLM call. No transport call.
  * Feature Activation Governance compatible — recommendations may
    carry an `activation_candidate` payload that FAG translates into
    a proposal (Observe → Recommend → Notify → Approve → Activate).

Rule families (additive to architect_advisor's 9 families):
    R-1  STRONGEST_STRATEGY_FOUND
    R-2  STRONGEST_MASTER_BOT_FOUND
    R-3  STRONGEST_PAIR_BY_OUTCOME
    R-4  ACTIVATION_READY_FEATURE
    R-5  COPILOT_LAYER_AVAILABLE  (advisory: advanced layer built but OFF)
    R-6  AUTO_LEARNING_STILL_GATED  (echoes the operator's directive)
    R-7  AUTO_LEARNING:*             (insights surfaced from the
                                       Auto-Learning Infrastructure
                                       aggregator; only when
                                       FS_ENABLE_AUTO_LEARNING=true)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from engines.factory_supervisor.architect_advisor import (
    Recommendation,
    REC_SEVERITY_INFO,
    REC_SEVERITY_SUGGESTION,
    REC_SEVERITY_WARN,
    _SEV_RANK,
)
from engines.factory_supervisor.copilot_context import CopilotContext

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    """Consumption gate. The engine itself always runs (read-only)."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_COPILOT"))
    except Exception:                                            # pragma: no cover
        return False


# ─── Best-effort Mongo readers (each is safe, never raises) ──────────


async def _read_top_strategies(limit: int = 3) -> List[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        cur = (
            db["strategy_library"]
            .find({}, {"_id": 0,
                       "fingerprint": 1, "pair": 1, "timeframe": 1,
                       "style": 1, "stability": 1, "rank": 1,
                       "saved_at": 1, "name": 1})
            .sort([("stability", -1), ("saved_at", -1)])
            .limit(limit)
        )
        return [d async for d in cur]
    except Exception as e:                                       # pragma: no cover
        logger.debug("[recommendation_engine] _read_top_strategies: %s", e)
        return []


async def _read_top_master_bots(limit: int = 3) -> List[Dict[str, Any]]:
    try:
        from engines.db import get_db
        db = get_db()
        cur = (
            db["master_bot_deployments"]
            .find({"state": "live"}, {"_id": 0,
                       "deployment_id": 1, "bot_id": 1, "name": 1,
                       "state": 1, "parity_verdict": 1, "promoted_at": 1})
            .sort([("promoted_at", -1)])
            .limit(limit)
        )
        return [d async for d in cur]
    except Exception as e:                                       # pragma: no cover
        logger.debug("[recommendation_engine] _read_top_master_bots: %s", e)
        return []


async def _read_top_pairs_by_submissions(ctx: CopilotContext, limit: int = 3) -> List[Dict[str, Any]]:
    """Use submissions stats (per_class) to surface the busiest pair-
    proxy. Submissions are not strictly per-pair, but `per_class`
    keys carry workload-class breakdown — the closest legitimate
    signal available pre-FS-P1.5."""
    per_class = (ctx.submissions or {}).get("stats", {}).get("per_class") or {}
    rows = sorted(per_class.items(), key=lambda kv: -int(kv[1].get("total", 0) if isinstance(kv[1], dict) else 0))
    out: List[Dict[str, Any]] = []
    for k, v in rows[:limit]:
        total = int(v.get("total", 0)) if isinstance(v, dict) else int(v)
        out.append({"workload_class": k, "total": total})
    return out


# ─── Rule families ──────────────────────────────────────────────────


async def _r1_strongest_strategy(ctx: CopilotContext) -> Optional[Recommendation]:
    rows = await _read_top_strategies(limit=3)
    if not rows:
        return None
    top = rows[0]
    name = top.get("name") or top.get("fingerprint") or "(unnamed)"
    return Recommendation(
        code="STRONGEST_STRATEGY_FOUND",
        severity=REC_SEVERITY_SUGGESTION,
        title=f"Strongest strategy: {name}",
        detail=(
            f"Top strategy by stability/rank — {top.get('pair') or 'pair?'} "
            f"{top.get('timeframe') or ''} · style={top.get('style') or '—'}."
        ),
        suggested_fix=(
            "Review in the Library tab; promote if parity sign-off holds."
        ),
        evidence={"top_3": rows},
    )


async def _r2_strongest_master_bot(ctx: CopilotContext) -> Optional[Recommendation]:
    rows = await _read_top_master_bots(limit=3)
    if not rows:
        return None
    top = rows[0]
    return Recommendation(
        code="STRONGEST_MASTER_BOT_FOUND",
        severity=REC_SEVERITY_SUGGESTION,
        title=f"Strongest live Master Bot: {top.get('name') or top.get('deployment_id') or '?'}",
        detail=(
            f"Currently-live Master Bot with most recent promotion — "
            f"parity={(top.get('parity_verdict') or {}).get('verdict')}."
        ),
        suggested_fix=(
            "Open the Master Bot tab; re-assert parity if older than 30 days."
        ),
        evidence={"top_3": rows},
    )


async def _r3_top_pair(ctx: CopilotContext) -> Optional[Recommendation]:
    rows = await _read_top_pairs_by_submissions(ctx, limit=3)
    if not rows or rows[0]["total"] == 0:
        return None
    top = rows[0]
    return Recommendation(
        code="STRONGEST_PAIR_BY_OUTCOME",
        severity=REC_SEVERITY_INFO,
        title=f"Busiest workload class: {top['workload_class']} ({top['total']})",
        detail=(
            "Submission throughput leader. Pre-FS-P1.5, per-pair "
            "telemetry rides under workload_class — a true pair "
            "ranker lands when execution bodies activate."
        ),
        suggested_fix="",
        evidence={"top_3": rows},
    )


def _r4_activation_ready(ctx: CopilotContext) -> List[Recommendation]:
    """One Recommendation per activation-ready feature."""
    out: List[Recommendation] = []
    for name in ctx.activation_ready or []:
        out.append(Recommendation(
            code="ACTIVATION_READY_FEATURE",
            severity=REC_SEVERITY_SUGGESTION,
            title=f"Feature ready for activation: {name}",
            detail=(
                "Eligibility signals are satisfied. Per Feature "
                "Activation Governance, activation requires operator "
                "approval — this engine never auto-activates."
            ),
            suggested_fix=(
                "Use Architect → Governance → Approve to file a proposal."
            ),
            evidence={"feature": name},
        ))
    return out


def _r5_advanced_layer_available(ctx: CopilotContext) -> Optional[Recommendation]:
    flags = (ctx.feature_flags or {}).get("fs_flags") or {}
    if flags.get("FS_ENABLE_COPILOT_ADVANCED") in (True, 1, "true"):
        return None
    # Only suggest when the Operational layer is itself ON.
    if not flags.get("FS_ENABLE_COPILOT"):
        return None
    return Recommendation(
        code="COPILOT_ADVANCED_LAYER_AVAILABLE",
        severity=REC_SEVERITY_INFO,
        title="Advanced Intelligence Copilot built but OFF",
        detail=(
            "The Advanced Intelligence Copilot layer is fully built "
            "and provider-agnostic. It remains gated OFF (operator "
            "policy). Enabling requires a concrete LLM provider "
            "registration plus the FS_ENABLE_COPILOT_ADVANCED flag."
        ),
        suggested_fix=(
            "When ready: register a provider in copilot_advanced.PROVIDER_REGISTRY "
            "and flip FS_ENABLE_COPILOT_ADVANCED=true."
        ),
        evidence={"current_provider": flags.get("FS_COPILOT_PROVIDER", "none")},
    )


def _r6_auto_learning_still_gated(ctx: CopilotContext) -> Optional[Recommendation]:
    al_flags = (ctx.feature_flags or {}).get("auto_learning_flags") or {}
    if al_flags.get("ENABLE_AUTONOMOUS_DISCOVERY") in (True, 1, "true"):
        return None
    return Recommendation(
        code="AUTO_LEARNING_GATED_BY_DIRECTIVE",
        severity=REC_SEVERITY_INFO,
        title="Auto-Learning remains gated OFF (operator directive)",
        detail=(
            "Auto-Learning infrastructure is fully built per FS-P1 "
            "roadmap; the activation gate stays OFF until explicit "
            "operator authorization."
        ),
        suggested_fix="",
        evidence={"directive": "operator-strict-off"},
    )


async def _r7_auto_learning_insights(ctx: CopilotContext) -> List[Recommendation]:
    """Surface read-only Auto-Learning insights as recommendations.

    Only contributes when `FS_ENABLE_AUTO_LEARNING` consumption gate
    is ON. Even when ON, NO insight here can trigger execution —
    every conversion drops to advisory severity at most.
    """
    try:
        from engines.factory_supervisor import auto_learning
    except Exception:                                                # pragma: no cover
        return []
    if not auto_learning.is_enabled():
        return []
    try:
        report = await auto_learning.build_report()
    except Exception as e:                                           # pragma: no cover
        logger.debug("[recommendation_engine] auto_learning failed: %s", e)
        return []
    insights = auto_learning.generate_insights(report)
    out: List[Recommendation] = []
    for ins in insights:
        # Cap severity at WARN — Auto-Learning never raises a CRITICAL.
        sev = ins.severity if ins.severity in (
            REC_SEVERITY_INFO, REC_SEVERITY_SUGGESTION, REC_SEVERITY_WARN,
        ) else REC_SEVERITY_INFO
        out.append(Recommendation(
            code=f"AUTO_LEARNING:{ins.kind}",
            severity=sev,
            title=ins.title,
            detail=ins.detail,
            suggested_fix=ins.suggested_action,
            evidence=dict(ins.evidence or {}),
        ))
    return out


# ─── Public surface ─────────────────────────────────────────────────


async def evaluate(ctx: CopilotContext) -> List[Recommendation]:
    """Run all rule families. Best-effort; per-rule failures are
    logged but never propagate. Sorted by severity-desc / code-asc."""
    out: List[Recommendation] = []
    # Architect's recommendations are already in ctx.recommendations —
    # include them in the engine output so consumers get a single list.
    for r in (ctx.recommendations or []):
        try:
            out.append(Recommendation(
                code=str(r.get("code") or "UNKNOWN"),
                severity=str(r.get("severity") or "info"),
                title=str(r.get("title") or ""),
                detail=str(r.get("detail") or ""),
                suggested_fix=str(r.get("suggested_fix") or ""),
                evidence=r.get("evidence") or {},
            ))
        except Exception:                                        # pragma: no cover
            continue

    for async_rule in (_r1_strongest_strategy, _r2_strongest_master_bot, _r3_top_pair):
        try:
            rec = await async_rule(ctx)
            if rec is not None:
                out.append(rec)
        except Exception as e:                                   # pragma: no cover
            logger.debug("[recommendation_engine] %s: %s", async_rule.__name__, e)

    out.extend(_r4_activation_ready(ctx))
    for sync_rule in (_r5_advanced_layer_available, _r6_auto_learning_still_gated):
        try:
            rec = sync_rule(ctx)
            if rec is not None:
                out.append(rec)
        except Exception as e:                                   # pragma: no cover
            logger.debug("[recommendation_engine] %s: %s", sync_rule.__name__, e)

    # R-7: Auto-Learning insights (only when its consumption gate is ON).
    try:
        out.extend(await _r7_auto_learning_insights(ctx))
    except Exception as e:                                       # pragma: no cover
        logger.debug("[recommendation_engine] _r7_auto_learning_insights: %s", e)

    # Dedupe by code (architect recs may overlap with engine recs).
    seen = set()
    unique: List[Recommendation] = []
    for r in out:
        if r.code in seen:
            continue
        seen.add(r.code)
        unique.append(r)

    unique.sort(key=lambda r: (-_SEV_RANK.get(r.severity, 0), r.code))
    return unique


async def top_recommendation(ctx: CopilotContext) -> Recommendation:
    """The most-pressing item across all rule families."""
    recs = await evaluate(ctx)
    return recs[0] if recs else Recommendation(
        code="NO_ACTION_REQUIRED",
        severity=REC_SEVERITY_INFO,
        title="No action required",
        detail="All monitored signals are within nominal bands.",
    )

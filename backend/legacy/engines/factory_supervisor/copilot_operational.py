"""
Factory Supervisor FS-P1.4 — Operational Copilot layer.

The Operational Copilot is a deterministic, read-only QA layer that
answers operator questions from the `CopilotContext` alone. It NEVER
calls an LLM. The full Advanced Intelligence layer (LLM-backed) lives
in `copilot_advanced.py` and is gated separately.

Operator-locked invariants:
  * READ-ONLY. No DB writes. No mutation. No emit().
  * Default OFF — when `FS_ENABLE_COPILOT=false`, every answer carries
    `advisory_only=true` and downstream consumers MUST honour that.
  * Provider-agnostic. No LLM import, no SDK touched.
  * Operator's 8 questions are the canonical contract.

Operator's 8 canonical questions (mapped to dedicated answerers):

    Q1  "What requires attention?"
    Q2  "What is blocked?"
    Q3  "What should I do next?"
    Q4  "Which systems are healthy?"
    Q5  "Which systems are inactive?"
    Q6  "Which features are ready for activation?"
    Q7  "What is the strongest strategy / master bot / pair right now?"
    Q8  "Is Auto-Learning ready, and if not, why?"
    Q9  "What are the current learning insights?"  (Auto-Learning Infra)

Public surface:
    is_enabled()
    answer(ctx, question_id) → dict       # one of the 8 above
    answer_all(ctx)            → dict     # all 8
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from engines.factory_supervisor.copilot_context import CopilotContext

logger = logging.getLogger(__name__)


CANONICAL_QUESTIONS = (
    "what_requires_attention",        # Q1
    "what_is_blocked",                # Q2
    "what_should_i_do_next",          # Q3
    "which_systems_are_healthy",      # Q4
    "which_systems_are_inactive",     # Q5
    "which_features_ready_to_activate",  # Q6
    "what_is_strongest",              # Q7
    "is_auto_learning_ready",         # Q8
    "what_are_learning_insights",     # Q9 (FS-P1.4 Auto-Learning Infra)
)


def is_enabled() -> bool:
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_COPILOT"))
    except Exception:                                            # pragma: no cover
        return False


# ─── Question answerers ──────────────────────────────────────────────


def _q1_what_requires_attention(ctx: CopilotContext) -> Dict[str, Any]:
    recs = ctx.recommendations or []
    # Only severities >= suggestion count as "requires attention".
    relevant = [r for r in recs if r.get("severity") in
                ("suggestion", "warn", "critical", "fatal")]
    return {
        "answer":          f"{len(relevant)} item(s) flagged for attention.",
        "items":           relevant,
        "top":             ctx.recommended_action,
        "system_health":   ctx.system_health,
    }


def _q2_what_is_blocked(ctx: CopilotContext) -> Dict[str, Any]:
    blocked = ctx.blocked or {}
    rows_preview = blocked.get("rows_preview") or []
    return {
        "answer": (
            f"defer_queue_pending={blocked.get('defer_queue_pending', 0)}, "
            f"submissions_refused={blocked.get('submissions_refused', 0)}, "
            f"defer_queue_failed={blocked.get('defer_queue_failed', 0)}."
        ),
        "blocked":       blocked,
        "rows_preview":  rows_preview[:10],
    }


def _q3_what_should_i_do_next(ctx: CopilotContext) -> Dict[str, Any]:
    return {
        "answer":             ctx.recommended_action.get("title") or "No action required.",
        "recommended_action": ctx.recommended_action,
    }


def _q4_which_systems_are_healthy(ctx: CopilotContext) -> Dict[str, Any]:
    return {
        "answer": (
            f"{len(ctx.healthy_systems)} healthy / "
            f"{len(ctx.unhealthy_systems)} unhealthy."
        ),
        "healthy":    list(ctx.healthy_systems),
        "unhealthy":  list(ctx.unhealthy_systems),
        "system_health": ctx.system_health,
    }


def _q5_which_systems_are_inactive(ctx: CopilotContext) -> Dict[str, Any]:
    return {
        "answer": (
            f"{len(ctx.inactive_workers)} inactive worker(s), "
            f"{len(ctx.inactive_flags or {})} dormant flag(s)."
        ),
        "inactive_workers": list(ctx.inactive_workers),
        "active_workers":   list(ctx.active_workers),
        "inactive_flags":   dict(ctx.inactive_flags or {}),
    }


def _q6_which_features_ready_to_activate(ctx: CopilotContext) -> Dict[str, Any]:
    # Run the eligibility engine here; it's pure + read-only.
    try:
        from engines.factory_supervisor import eligibility_signals
        verdicts = eligibility_signals.evaluate_all(ctx)
        ready = [v.to_dict() for v in verdicts if v.eligible]
        all_v = [v.to_dict() for v in verdicts]
    except Exception as e:                                       # pragma: no cover
        logger.debug("[copilot_operational] q6 failed: %s", e)
        ready, all_v = [], []
    return {
        "answer":     f"{len(ready)} feature(s) eligible for activation.",
        "ready":      ready,
        "verdicts":   all_v,
    }


def _q7_what_is_strongest(ctx: CopilotContext) -> Dict[str, Any]:
    # Borrow the recommendations carrying the codes we know.
    recs = ctx.recommendations or []
    by_code = {r.get("code"): r for r in recs if isinstance(r, dict)}
    return {
        "answer": "See per-section evidence.",
        "strongest_strategy":   by_code.get("STRONGEST_STRATEGY_FOUND"),
        "strongest_master_bot": by_code.get("STRONGEST_MASTER_BOT_FOUND"),
        "strongest_pair":       by_code.get("STRONGEST_PAIR_BY_OUTCOME"),
    }


def _q8_is_auto_learning_ready(ctx: CopilotContext) -> Dict[str, Any]:
    al_flags = (ctx.feature_flags or {}).get("auto_learning_flags") or {}
    enabled  = bool(al_flags.get("ENABLE_AUTONOMOUS_DISCOVERY"))
    try:
        from engines.factory_supervisor import eligibility_signals
        verdict = eligibility_signals.evaluate("ENABLE_AUTONOMOUS_DISCOVERY", ctx)
        verdict_d = verdict.to_dict()
    except Exception:                                            # pragma: no cover
        verdict_d = None
    return {
        "answer": (
            "Auto-Learning is ENABLED."
            if enabled else
            "Auto-Learning is GATED OFF by operator directive."
        ),
        "enabled":           enabled,
        "verdict":           verdict_d,
        "operator_directive": "off",  # frozen for FS-P1.4
    }


def _q9_what_are_learning_insights(ctx: CopilotContext) -> Dict[str, Any]:
    """Return the FS-P1.4 Auto-Learning Infrastructure insight set.

    Read-only. Reads from `ctx.auto_learning` (hydrated by
    `copilot_context.build_from_snapshot` ONLY when
    FS_ENABLE_AUTO_LEARNING is ON). When dormant, returns an empty
    insight list with `advisory_only=true`. NEVER triggers a loop.
    """
    al = ctx.auto_learning or {}
    insights = al.get("insights") or []
    summary  = {
        "total": len(insights),
        "by_severity": {},
    }
    for i in insights:
        sev = i.get("severity") or "info"
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
    try:
        from engines.factory_supervisor import auto_learning
        loop_on = auto_learning.is_loop_enabled()
    except Exception:                                            # pragma: no cover
        loop_on = False
    return {
        "answer": (
            f"{len(insights)} learning insight(s) available."
            if insights else
            "Auto-Learning aggregator dormant (no insights surfaced)."
        ),
        "insights":         insights,
        "summary":          summary,
        "is_loop_enabled":  loop_on,
        "operator_directive": "off",
        "components_sources": al.get("sources") or {},
        "flags":            al.get("flags") or {},
    }


_ANSWERERS = {
    "what_requires_attention":            _q1_what_requires_attention,
    "what_is_blocked":                    _q2_what_is_blocked,
    "what_should_i_do_next":              _q3_what_should_i_do_next,
    "which_systems_are_healthy":          _q4_which_systems_are_healthy,
    "which_systems_are_inactive":         _q5_which_systems_are_inactive,
    "which_features_ready_to_activate":   _q6_which_features_ready_to_activate,
    "what_is_strongest":                  _q7_what_is_strongest,
    "is_auto_learning_ready":             _q8_is_auto_learning_ready,
    "what_are_learning_insights":         _q9_what_are_learning_insights,
}


# ─── Public surface ──────────────────────────────────────────────────


def answer(ctx: CopilotContext, question_id: str) -> Dict[str, Any]:
    """Answer one of the 8 canonical questions deterministically.

    Unknown question_id → {error: 'unknown_question'} with the
    canonical question list for discovery. Never raises.
    """
    qid = (question_id or "").strip().lower()
    fn = _ANSWERERS.get(qid)
    if fn is None:
        return {
            "question_id":     qid,
            "advisory_only":   not is_enabled(),
            "error":           "unknown_question",
            "canonical":       list(CANONICAL_QUESTIONS),
        }
    try:
        body = fn(ctx)
    except Exception as e:                                       # pragma: no cover
        logger.debug("[copilot_operational] %s failed: %s", qid, e)
        body = {"error": f"answerer_failed: {e}"[:200]}
    return {
        "question_id":   qid,
        "advisory_only": not is_enabled(),
        "evaluated_at":  ctx.evaluated_at,
        "system_health": ctx.system_health,
        **body,
    }


def answer_all(ctx: CopilotContext) -> Dict[str, Any]:
    """Answer every canonical question. Useful for the dashboard /
    Copilot integration tests."""
    out = {
        "advisory_only":   not is_enabled(),
        "evaluated_at":    ctx.evaluated_at,
        "system_health":   ctx.system_health,
        "answers":         {},
    }
    for qid in CANONICAL_QUESTIONS:
        try:
            out["answers"][qid] = _ANSWERERS[qid](ctx)
        except Exception as e:                                   # pragma: no cover
            out["answers"][qid] = {"error": str(e)[:200]}
    return out

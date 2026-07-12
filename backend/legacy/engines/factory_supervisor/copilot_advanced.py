"""
Factory Supervisor FS-P1.4 — Advanced Intelligence Copilot layer.

The Advanced Intelligence Copilot is the (currently DORMANT) bridge
between the deterministic Operational Copilot and a real LLM
provider. It is built fully so the platform is deployment-ready
later, but it is gated strictly OFF and provider-agnostic.

Operator-locked invariants:
  * Default OFF — when `FS_ENABLE_COPILOT_ADVANCED=false`, every call
    returns `{provider: 'none', advisory_only: True, ...}` without
    touching any provider.
  * Provider-agnostic — no LLM SDK is imported at this module's load
    time. Adapters are pulled via `llm_adapter_base.PROVIDER_REGISTRY`
    when (and only when) a request is honoured.
  * The Copilot context (`CopilotContext`) is the SOLE substrate the
    layer ever sees. No direct DB / engine access from prompt
    construction.
  * No execution authority — even with FS_ENABLE_COPILOT_ADVANCED=true
    AND a registered provider, the layer is advisory_only. Any
    feature activation must still flow through `fag_proposals`.

Public surface:
    ALL_INTENTS                              # canonical intent ids
    is_enabled() -> bool
    provider_manifest() -> dict
    build_prompt(ctx, intent, *, user_input=None) -> LLMRequest
    async invoke(ctx, intent, *, user_input=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from engines.factory_supervisor.copilot_context import CopilotContext
from engines.factory_supervisor import llm_adapter_base as _llm
from engines.factory_supervisor.llm_adapter_base import LLMRequest

logger = logging.getLogger(__name__)


# Canonical Copilot intents — additive only.
INTENT_EXPLAIN_RECOMMENDATION = "explain_recommendation"
INTENT_SUMMARISE_STATE        = "summarise_state"
INTENT_COMPARE_OPTIONS        = "compare_options"
INTENT_DRAFT_OPERATOR_NOTE    = "draft_operator_note"
INTENT_FREEFORM               = "freeform"

ALL_INTENTS = (
    INTENT_EXPLAIN_RECOMMENDATION,
    INTENT_SUMMARISE_STATE,
    INTENT_COMPARE_OPTIONS,
    INTENT_DRAFT_OPERATOR_NOTE,
    INTENT_FREEFORM,
)


def is_enabled() -> bool:
    """Master gate. When False, `invoke()` never calls a provider."""
    try:
        from engines.feature_flags import flag
        if not bool(flag("ENABLE_FACTORY_SUPERVISOR")):
            return False
        return bool(flag("FS_ENABLE_COPILOT_ADVANCED"))
    except Exception:                                            # pragma: no cover
        return False


def provider_manifest() -> Dict[str, Any]:
    """Snapshot of the resolved adapter + the full registry."""
    name, adapter = _llm.resolve_active_adapter()
    return {
        "enabled":           is_enabled(),
        "active_provider":   name,
        "registered":        _llm.list_providers(),
        "advisory_only":     not is_enabled() or name == "none",
    }


# ─── Prompt construction (provider-agnostic) ─────────────────────────


_SYSTEM_PROMPT_BASE = (
    "You are the Factory Supervisor Copilot. You are READ-ONLY and "
    "ADVISORY-ONLY. You NEVER execute changes; you only explain, "
    "summarise, and compare. Honour the operator's directive that "
    "Auto-Learning stays gated OFF unless explicitly enabled. Quote "
    "the system_state_view snapshot when relevant; do not invent fields."
)


def _summarise_ctx(ctx: CopilotContext) -> Dict[str, Any]:
    """Compact, deterministic context summary for prompt embedding."""
    return {
        "phase":              ctx.phase,
        "evaluated_at":       ctx.evaluated_at,
        "advisory_only":      ctx.advisory_only,
        "system_health":      ctx.system_health,
        "top_recommendation": ctx.recommended_action,
        "blocked":            ctx.blocked,
        "healthy_systems":    ctx.healthy_systems,
        "unhealthy_systems":  ctx.unhealthy_systems,
        "activation_ready":   ctx.activation_ready,
        "inactive_flags":     list((ctx.inactive_flags or {}).keys())[:25],
    }


def build_prompt(
    ctx: CopilotContext,
    intent: str,
    *,
    user_input: Optional[str] = None,
) -> LLMRequest:
    """Construct the LLMRequest for a given intent + context.

    Pure function — no DB / engine access. The result is suitable for
    static inspection and dry-running prompt construction in tests
    without ever calling a provider.
    """
    intent_key = (intent or INTENT_FREEFORM).strip().lower()
    if intent_key not in ALL_INTENTS:
        intent_key = INTENT_FREEFORM
    ctx_summary = _summarise_ctx(ctx)

    if intent_key == INTENT_EXPLAIN_RECOMMENDATION:
        prompt = (
            "Explain the operator's TOP recommendation in plain English. "
            "Quote the suggested_fix verbatim. Do not invent steps. "
            "Context (top_recommendation):\n"
            f"{ctx_summary['top_recommendation']}\n"
        )
    elif intent_key == INTENT_SUMMARISE_STATE:
        prompt = (
            "Summarise the current Factory Supervisor state in 4-6 "
            "bullet points. Highlight: system_health, blocked, "
            "activation-ready, and the top recommendation. Do not "
            "invent fields outside the provided context."
        )
    elif intent_key == INTENT_COMPARE_OPTIONS:
        prompt = (
            "Compare the listed activation-ready features. For each, "
            "state the eligibility verdict and the operator-facing "
            "trade-off. End with a recommendation matrix; do NOT "
            "auto-activate anything — that is FAG's job and requires "
            "operator approval."
        )
    elif intent_key == INTENT_DRAFT_OPERATOR_NOTE:
        prompt = (
            "Draft a 3-paragraph operator note summarising the current "
            "system health, blockers, and the top recommendation. Keep "
            "it factual; avoid speculation."
        )
    else:  # FREEFORM
        prompt = (user_input or "").strip() or (
            "Provide a short status update from the current context."
        )

    return LLMRequest(
        prompt=prompt,
        system_prompt=_SYSTEM_PROMPT_BASE,
        context=ctx_summary,
        extra={"intent": intent_key, "ctx_phase": ctx.phase},
    )


# ─── Invocation (gated) ──────────────────────────────────────────────


async def invoke(
    ctx: CopilotContext,
    intent: str,
    *,
    user_input: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a Copilot invocation.

    Behaviour:
      * If `FS_ENABLE_COPILOT_ADVANCED=false` → returns advisory_only
        response WITHOUT touching any provider (even null).
      * If enabled AND the resolved provider is `none` → returns the
        NullLLMAdapter response (advisory_only=true).
      * If enabled AND a real provider is registered → routes the
        LLMRequest through `LLMAdapter.invoke()`; the adapter is
        responsible for never raising.

    The returned dict carries the response shape plus the prompt
    inputs so consumers can trace what was sent.
    """
    req = build_prompt(ctx, intent, user_input=user_input)

    if not is_enabled():
        return {
            "advisory_only": True,
            "intent":        req.extra.get("intent"),
            "provider":      "none",
            "request":       req.to_dict(),
            "response":      {
                "provider":       "none",
                "advisory_only":  True,
                "text":           "[advisory-only — FS_ENABLE_COPILOT_ADVANCED is OFF]",
                "finish_reason":  "gated_off",
            },
        }

    name, adapter = _llm.resolve_active_adapter()
    try:
        resp = await adapter.invoke(req)
    except Exception as e:                                       # pragma: no cover
        logger.debug("[copilot_advanced] adapter raised: %s", e)
        return {
            "advisory_only": True,
            "intent":        req.extra.get("intent"),
            "provider":      name,
            "request":       req.to_dict(),
            "response":      {"provider": name, "advisory_only": True,
                              "text": "", "error": str(e)[:200]},
        }

    return {
        "advisory_only": resp.advisory_only or name == "none",
        "intent":        req.extra.get("intent"),
        "provider":      name,
        "request":       req.to_dict(),
        "response":      resp.to_dict(),
    }

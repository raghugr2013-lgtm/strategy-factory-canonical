"""
Phase 2 scaffolding — Agentic governance advisor (DORMANT, no-LLM).

A scaffold for future agent-driven orchestration recommendations. Today
this module produces ONLY the prompt template that WOULD be sent to an
LLM if ``ENABLE_AGENT_ADVISOR=true`` — it does NOT actually call any
LLM, does NOT require any API key, and emits no recommendations.

The intent is to let the operator inspect, ahead of activation:
  * what context the future agent would see,
  * what question it would be asked, and
  * what response format would be expected.

Discipline:
  * Dormant: even when the flag is ON, the only effect is that the
    response carries ``would_call_llm=true`` and the prompt is
    materialised. NO actual LLM call is made from this module.
  * No keys required.
  * Read-only across every input source.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """\
You are the AI Strategy Factory's institutional widening advisor.
You have NO authority to flip flags, alter schedulers, or change
governance. Your output is a RECOMMENDATION; the human operator
remains the only entity that may act.

Current activation state
------------------------
- current_stage:       {current_stage}
- next_stage:          {next_stage}
- live verdict:        {verdict}
- blocking reasons:    {blocking_reasons}
- warning reasons:     {warning_reasons}

Host posture
------------
- cpu_headroom_pct:    {cpu_headroom_pct}
- mem_headroom_pct:    {mem_headroom_pct}
- load_per_core:       {load_per_core}

Ecosystem
---------
- universe pairs:      {pairs}
- universe timeframes: {timeframes}
- survivor active:     {survivor_active}
- survivor cap:        {survivor_cap}

Soak posture
------------
- last widening at:    {last_widening_at}
- days since:          {soak_days_since}

Question
--------
Given the above, recommend ONE of:
  (a) "HOLD"      — soak longer; no widening today.
  (b) "PROPOSE"   — propose the next stage flag flip with explicit
                    confidence and concrete success criteria.
  (c) "ESCALATE"  — there is an institutional anomaly the operator
                    should review BEFORE any widening.

Reply as JSON: {{"recommendation": "HOLD"|"PROPOSE"|"ESCALATE",
                 "confidence_pct": 0..100,
                 "rationale": "...",
                 "success_criteria": ["...", "..."]}}
"""


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_AGENT_ADVISOR") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def build_prompt() -> Dict[str, Any]:
    """Materialise the prompt the future agent would see. Pure read.

    Returns
    -------
    {
      "ts":              iso,
      "enabled":         bool,
      "would_call_llm":  bool,
      "advisory_only":   true,
      "operator_authority": "final",
      "context_inputs":  {...full structured context the agent would see},
      "prompt_text":     str,       # the templated prompt
      "expected_response_schema": {...},
      "note":            "Even when enabled, this scaffold does NOT call any LLM."
    }
    """
    enabled = is_enabled()
    # ── Gather inputs (best-effort, read-only). ───────────────────
    inputs: Dict[str, Any] = {}
    try:
        from engines import safe_to_widen
        sw = await safe_to_widen.evaluate()
        inputs["safe_to_widen"] = sw
    except Exception:                                       # pragma: no cover
        inputs["safe_to_widen"] = {}

    try:
        from engines import compute_probe
        snap = compute_probe.snapshot()
        inputs["compute"] = {
            "snapshot": snap,
            "headroom": compute_probe.headroom_summary(snap),
        }
    except Exception:                                       # pragma: no cover
        inputs["compute"] = {}

    try:
        from engines import governance_universe as gu
        inputs["universe"] = await gu.get_universe()
    except Exception:                                       # pragma: no cover
        inputs["universe"] = {}

    try:
        from engines import survivor_registry
        inputs["survivor_universe"] = await survivor_registry.fetch_survivor_universe()
    except Exception:                                       # pragma: no cover
        inputs["survivor_universe"] = {}

    try:
        from engines import widening_history
        wh = await widening_history.build_history(
            limit=1, include_context=False, include_universe=False,
        )
        inputs["last_widening"] = (wh.get("events") or [None])[0]
    except Exception:                                       # pragma: no cover
        inputs["last_widening"] = None

    # ── Build prompt text. ────────────────────────────────────────
    sw  = inputs.get("safe_to_widen") or {}
    cp  = inputs.get("compute") or {}
    uni = inputs.get("universe") or {}
    sur = inputs.get("survivor_universe") or {}
    lw  = inputs.get("last_widening") or {}
    head = cp.get("headroom") or {}

    prompt_text = PROMPT_TEMPLATE.format(
        current_stage=     sw.get("current_stage", "?"),
        next_stage=        sw.get("next_stage", "?"),
        verdict=           sw.get("verdict", "?"),
        blocking_reasons=  sw.get("blocking_reasons") or [],
        warning_reasons=   sw.get("warning_reasons") or [],
        cpu_headroom_pct=  head.get("cpu_headroom_pct"),
        mem_headroom_pct=  head.get("mem_headroom_pct"),
        load_per_core=     head.get("load_per_core"),
        pairs=             uni.get("pairs") or [],
        timeframes=        uni.get("timeframes") or [],
        survivor_active=   sur.get("active_count"),
        survivor_cap=      sur.get("cap"),
        last_widening_at=  lw.get("ts"),
        soak_days_since=   _soak_days_from_event(lw),
    )

    return {
        "ts":               _now_iso(),
        "enabled":          enabled,
        "would_call_llm":   enabled,
        "advisory_only":    True,
        "operator_authority": "final",
        "phase":            "scaffolding-1",
        "context_inputs":   inputs,
        "prompt_text":      prompt_text,
        "expected_response_schema": {
            "recommendation":     'HOLD | PROPOSE | ESCALATE',
            "confidence_pct":     "0..100",
            "rationale":          "string",
            "success_criteria":   "string[]",
        },
        "note": (
            "Even when ENABLE_AGENT_ADVISOR=true, this module does NOT "
            "call any LLM. It only materialises the prompt. A future "
            "adoption pass would wire an LLM call AND an admin-approval "
            "gate before any recommendation reaches an operator decision."
        ),
    }


def _soak_days_from_event(event: Optional[Dict[str, Any]]) -> Optional[float]:
    if not event or not isinstance(event, dict):
        return None
    ts = event.get("ts")
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - dt).total_seconds() / 86400.0, 2)
    except (TypeError, ValueError):                         # pragma: no cover
        return None

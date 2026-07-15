"""Compact LLM prompt block from a `KnowledgeContext`.

Rendered as a Markdown-fenced block the strategy_engine's LLM system
prompt can prepend under `## Prior knowledge`. Keeps under ~2 KB so it
never dominates the token budget.

If the context is empty, returns a stable single-line placeholder so
the prompt shape is byte-identical whether or not the index is
populated.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .retriever import KnowledgeContext


_EMPTY = "(no prior knowledge yet — generate from scratch)"

_MAX_ITEMS_PER_COHORT = 5
_MAX_INDICATOR_TOKENS = 8
_SUMMARY_CHAR_LIMIT = 200


def _condense(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "hash": (row.get("strategy_hash") or "")[:12],
        "type": row.get("strategy_type"),
        "pair": row.get("pair"),
        "tf":   row.get("timeframe"),
        "indicators": (row.get("indicators") or [])[:_MAX_INDICATOR_TOKENS],
        "risk":  (row.get("risk_model") or [])[:4],
        "verdict": row.get("verdict"),
        "pf": row.get("best_pf"),
        "dd": row.get("best_dd"),
        "gist": (row.get("knowledge_summary_text") or "")[:_SUMMARY_CHAR_LIMIT],
    }


def build_block(ctx: KnowledgeContext) -> str:
    if not ctx.winners and not ctx.losers and not ctx.neutral:
        return _EMPTY

    winners = [_condense(r) for r in ctx.winners[:_MAX_ITEMS_PER_COHORT]]
    losers  = [_condense(r) for r in ctx.losers[:_MAX_ITEMS_PER_COHORT]]

    parts: List[str] = []
    parts.append(
        f"Prior knowledge from {ctx.total_scanned} historical strategies "
        f"in scope pair={ctx.query.get('pair') or '?'} "
        f"tf={ctx.query.get('timeframe') or '?'} "
        f"style={ctx.query.get('style') or '?'}:"
    )
    if winners:
        parts.append("Historical WINNERS to draw from (inherit indicators/risk shapes):")
        parts.append(json.dumps(winners, ensure_ascii=False))
    if losers:
        parts.append("Historical LOSERS to AVOID (do NOT replicate these shapes):")
        parts.append(json.dumps(losers, ensure_ascii=False))
    if ctx.mutation_paths:
        parts.append("Mutation families with the highest historical yield: " +
                     ", ".join(f"{k}×{n}" for k, n in ctx.mutation_paths[:5]))
    if ctx.lifecycle_paths:
        parts.append("Terminal lifecycle distribution: " + json.dumps(ctx.lifecycle_paths))

    return "\n".join(parts)


def format_lookup_summary(ctx: KnowledgeContext) -> Dict[str, Any]:
    """Machine-friendly rendering for `GET /api/knowledge/lookup`."""
    return {
        "query": ctx.query,
        "total_scanned": ctx.total_scanned,
        "winners": [_condense(r) for r in ctx.winners],
        "losers":  [_condense(r) for r in ctx.losers],
        "neutral": [_condense(r) for r in ctx.neutral],
        "mutation_paths": [{"family": f, "count": n} for f, n in ctx.mutation_paths],
        "lifecycle_paths": ctx.lifecycle_paths,
        "prompt_block": build_block(ctx),
    }

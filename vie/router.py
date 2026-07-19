"""Task → provider preference routing with failover.

Static defaults; can be overridden by env `VIE_TASK_MAP` (JSON string).

Phase 2 Stage 1 (2026-02-19) — extended default task map with the 6
UKIE-parser tasks. The extension is behind
`VIE_TASK_MAP_EXTENDED=true` at the backend layer (the VIE service
itself always accepts the extended vocabulary; backend-side gating
controls whether the new tasks are actually referenced). Zero behaviour
change until a caller passes one of the new task names.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

# Ordered lists — first available provider in the list wins.
DEFAULT_TASK_MAP: Dict[str, List[str]] = {
    # Historical tasks (unchanged).
    "research": ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "generation": ["openai", "anthropic", "deepseek", "gemini", "groq", "kimi"],
    "validation": ["deepseek", "openai", "anthropic", "gemini", "groq", "kimi"],
    "explanation": ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "fast": ["groq", "gemini", "deepseek", "openai", "anthropic", "kimi"],
    "default": ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"],

    # Phase 2 Stage 1 (2026-02-19) — UKIE parser tasks per PHASE_2_CONSOLIDATED §4.5.
    # These names line up with the six Knowledge Domains defined in PHASE_2C §1.0.
    "parse_strategy_code":       ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"],
    "parse_paper_abstract":      ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "parse_indicator_definition":["openai", "gemini", "deepseek", "anthropic", "groq", "kimi"],
    "parse_market_note":         ["gemini", "openai", "anthropic", "deepseek", "groq", "kimi"],
    "parse_execution_rule":      ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    # parse_internal_history bypasses LLM (internal Mongo read) — no chain.
}


def load_task_map() -> Dict[str, List[str]]:
    raw = os.environ.get("VIE_TASK_MAP")
    if not raw:
        return DEFAULT_TASK_MAP
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {**DEFAULT_TASK_MAP, **parsed}
    except json.JSONDecodeError:
        pass
    return DEFAULT_TASK_MAP


def route(task: str, available_names: List[str]) -> List[str]:
    """Return ordered list of provider names to try for `task`."""
    tmap = load_task_map()
    order = tmap.get(task) or tmap.get("default") or []
    return [n for n in order if n in available_names]

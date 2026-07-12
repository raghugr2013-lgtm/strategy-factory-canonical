"""Task → provider preference routing with failover.

Static defaults; can be overridden by env `VIE_TASK_MAP` (JSON string).
"""
from __future__ import annotations

import json
import os
from typing import Dict, List

# Ordered lists — first available provider in the list wins.
DEFAULT_TASK_MAP: Dict[str, List[str]] = {
    "research": ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "generation": ["openai", "anthropic", "deepseek", "gemini", "groq", "kimi"],
    "validation": ["deepseek", "openai", "anthropic", "gemini", "groq", "kimi"],
    "explanation": ["anthropic", "openai", "gemini", "deepseek", "groq", "kimi"],
    "fast": ["groq", "gemini", "deepseek", "openai", "anthropic", "kimi"],
    "default": ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"],
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

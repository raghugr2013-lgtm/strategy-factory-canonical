"""Provider registry — reads env, instantiates every provider (available or not).

A provider is `available` when its API key env var is present and non-empty.
Missing key does NOT crash the service — the provider is simply marked
unavailable and skipped by the router.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from .providers.anthropic_p import AnthropicProvider
from .providers.base import BaseProvider
from .providers.deepseek_p import DeepSeekProvider
from .providers.gemini_p import GeminiProvider
from .providers.groq_p import GroqProvider
from .providers.kimi_p import KimiProvider
from .providers.openai_p import OpenAIProvider

_ORDER = ["openai", "anthropic", "gemini", "deepseek", "groq", "kimi"]

_CLASSES = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
    "groq": GroqProvider,
    "kimi": KimiProvider,
}

_MODEL_ENV = {
    "openai": "OPENAI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "gemini": "GEMINI_MODEL",
    "deepseek": "DEEPSEEK_MODEL",
    "groq": "GROQ_MODEL",
    "kimi": "KIMI_MODEL",
}


class Registry:
    def __init__(self) -> None:
        self._providers: Dict[str, BaseProvider] = {}
        for name in _ORDER:
            cls = _CLASSES[name]
            api_key = os.environ.get(cls.api_key_env, "").strip()
            model_override = os.environ.get(_MODEL_ENV[name], "").strip() or None
            self._providers[name] = cls(api_key=api_key or None, default_model=model_override)

    def get(self, name: str) -> Optional[BaseProvider]:
        return self._providers.get(name.lower())

    def all(self) -> List[BaseProvider]:
        return [self._providers[n] for n in _ORDER]

    def available(self) -> List[BaseProvider]:
        return [p for p in self.all() if p.available]

    def status(self) -> List[dict]:
        return [
            {
                "name": p.name,
                "available": p.available,
                "default_model": p.default_model,
                "api_key_env": p.api_key_env,
            }
            for p in self.all()
        ]


_registry: Registry | None = None


def get_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry

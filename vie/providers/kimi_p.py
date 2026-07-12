"""Kimi / Moonshot (OpenAI-compatible)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .base import BaseProvider


class KimiProvider(BaseProvider):
    name = "kimi"
    api_key_env = "KIMI_API_KEY"
    default_model = "kimi-k2"
    url = "https://api.moonshot.ai/v1/chat/completions"

    def generate(self, *, prompt, system_message="", model=None, temperature=0.3, max_tokens=None) -> Dict[str, Any]:
        chosen = model or self.default_model
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        body = {"model": chosen, "messages": messages, "temperature": temperature}
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        r = requests.post(
            self.url,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return {
            "output": data["choices"][0]["message"]["content"],
            "model": data.get("model", chosen),
            "usage": data.get("usage"),
        }

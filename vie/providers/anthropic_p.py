"""Anthropic Messages API."""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    api_key_env = "ANTHROPIC_API_KEY"
    default_model = "claude-sonnet-4-5-20250929"
    url = "https://api.anthropic.com/v1/messages"

    def generate(self, *, prompt, system_message="", model=None, temperature=0.3, max_tokens=None) -> Dict[str, Any]:
        chosen = model or self.default_model
        body = {
            "model": chosen,
            "max_tokens": max_tokens or 2048,
            "system": system_message,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        r = requests.post(
            self.url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return {"output": text, "model": data.get("model", chosen), "usage": data.get("usage")}

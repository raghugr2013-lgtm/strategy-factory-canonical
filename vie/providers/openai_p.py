"""OpenAI Chat Completions."""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .base import BaseProvider


class OpenAIProvider(BaseProvider):
    name = "openai"
    api_key_env = "OPENAI_API_KEY"
    default_model = "gpt-4o-mini"
    url = "https://api.openai.com/v1/chat/completions"

    def generate(self, *, prompt, system_message="", model=None, temperature=0.3, max_tokens=None) -> Dict[str, Any]:
        messages = []
        if system_message:
            messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": prompt})
        chosen_model = model or self.default_model
        body: dict = {"model": chosen_model, "messages": messages}
        # gpt-5 family only supports default temperature
        if not chosen_model.startswith("gpt-5"):
            body["temperature"] = temperature
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
            "model": data.get("model", chosen_model),
            "usage": data.get("usage"),
        }

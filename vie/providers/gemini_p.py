"""Google Gemini (v1beta generateContent)."""
from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .base import BaseProvider


class GeminiProvider(BaseProvider):
    name = "gemini"
    api_key_env = "GEMINI_API_KEY"
    default_model = "gemini-2.5-flash"

    def generate(self, *, prompt, system_message="", model=None, temperature=0.3, max_tokens=None) -> Dict[str, Any]:
        chosen = model or self.default_model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{chosen}:generateContent?key={self.api_key}"
        full = f"{system_message}\n\n{prompt}" if system_message else prompt
        body: dict = {"contents": [{"parts": [{"text": full}]}], "generationConfig": {"temperature": temperature}}
        if max_tokens is not None:
            body["generationConfig"]["maxOutputTokens"] = max_tokens
        r = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
        text = parts[0].get("text", "") if parts else ""
        return {"output": text, "model": chosen, "usage": data.get("usageMetadata")}

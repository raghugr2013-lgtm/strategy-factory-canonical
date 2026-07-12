"""Base provider — subclasses adapt the shared HTTP request/response shape."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseProvider(ABC):
    name: str = "base"
    api_key_env: str = ""
    default_model: str = ""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None) -> None:
        self.api_key = api_key
        if default_model:
            self.default_model = default_model

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        system_message: str = "",
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return dict with keys: output(str), model(str), usage(dict|None)."""
        raise NotImplementedError

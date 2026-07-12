"""VIE HTTP client — the ONLY way the backend talks to LLM providers.

No direct provider SDKs are imported in business logic. All calls flow
through this async client to the VIE service on `VIE_URL`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class VIEError(Exception):
    pass


class VIEUnavailable(VIEError):
    pass


class VIEClient:
    def __init__(self, base_url: Optional[str] = None, timeout_s: Optional[int] = None) -> None:
        s = get_settings()
        self.base_url = (base_url or s.vie_url).rstrip("/")
        self.timeout_s = timeout_s or s.vie_timeout_s

    async def _get(self, path: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.get(f"{self.base_url}{path}")
                r.raise_for_status()
                return r.json()
        except httpx.HTTPError as e:
            logger.warning("VIE GET %s failed: %s", path, e)
            raise VIEUnavailable(str(e)) from e

    async def _post(self, path: str, body: Dict[str, Any]) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as c:
                r = await c.post(f"{self.base_url}{path}", json=body)
                if r.status_code == 503:
                    raise VIEUnavailable(f"VIE 503: {r.text[:400]}")
                if r.status_code >= 400:
                    raise VIEError(f"VIE {r.status_code}: {r.text[:400]}")
                return r.json()
        except httpx.HTTPError as e:
            logger.warning("VIE POST %s failed: %s", path, e)
            raise VIEUnavailable(str(e)) from e

    async def health(self) -> Dict[str, Any]:
        return await self._get("/health")

    async def providers(self) -> List[Dict[str, Any]]:
        data = await self._get("/providers")
        return data.get("providers", [])

    async def probe(self, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        body: Dict[str, Any] = {}
        if provider:
            body["provider"] = provider
        # probe can take up to N * timeout_s across all providers; allow generous ceiling
        try:
            async with httpx.AsyncClient(timeout=120.0) as c:
                r = await c.post(f"{self.base_url}/probe", json=body)
                if r.status_code == 503:
                    raise VIEUnavailable(f"VIE 503: {r.text[:400]}")
                if r.status_code >= 400:
                    raise VIEError(f"VIE {r.status_code}: {r.text[:400]}")
                data = r.json()
        except httpx.HTTPError as e:
            logger.warning("VIE probe failed: %s", e)
            raise VIEUnavailable(str(e)) from e
        return data.get("results", [])

    async def generate(
        self,
        *,
        prompt: str,
        task: Optional[str] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        system_message: str = "",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "prompt": prompt,
            "system_message": system_message,
            "temperature": temperature,
        }
        if task:
            body["task"] = task
        if provider:
            body["provider"] = provider
        if model:
            body["model"] = model
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return await self._post("/generate", body)


_client: VIEClient | None = None


def get_vie() -> VIEClient:
    global _client
    if _client is None:
        _client = VIEClient()
    return _client

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
        provider_hint: Optional[str] = None,
        model: Optional[str] = None,
        system_message: str = "",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a generation request to the VIE service.

        Phase 2 Stage 1 additions (2026-02-19):
          * `provider_hint` — advisory routing preference. Honoured when
            `VIE_PROVIDER_HINT_RESPECT=true`. If `provider` is set
            explicitly, `provider` wins (backwards compatible).
          * Every successful completion is recorded in the shared
            `BudgetTracker` when `VIE_BUDGET_PERSIST=true` (single
            source of truth per PHASE_2_CONSOLIDATED §4.2).
        """
        # Provider hint honouring — flag-gated so pre-flag behaviour is
        # byte-identical.
        import os as _os
        if provider is None and provider_hint is not None:
            hint_flag = (_os.environ.get("VIE_PROVIDER_HINT_RESPECT") or "").strip().lower()
            if hint_flag in ("1", "true", "yes", "y", "on"):
                provider = provider_hint

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
        result = await self._post("/generate", body)

        # Budget recording — best-effort, never raises. Central tracker
        # is the single source of truth for USD accounting.
        try:
            self._record_budget(result)
        except Exception as e:  # noqa: BLE001
            logger.debug("VIE budget record failed (non-fatal): %s", e)
        return result

    def _record_budget(self, result: Dict[str, Any]) -> None:
        """Best-effort cost accounting via the shared BudgetTracker.

        VIE responses carry `usage` in a provider-specific shape. When
        the response includes `usage.cost_usd` and `usage.tokens`, they
        are recorded verbatim. Otherwise a zero-cost row is written so
        the RPM window still advances.
        """
        import os as _os
        raw = (_os.environ.get("VIE_BUDGET_PERSIST") or _os.environ.get("BUDGET_PERSIST") or "").strip().lower()
        if raw not in ("1", "true", "yes", "y", "on"):
            return
        provider = str(result.get("provider") or "").strip() or "unknown"
        usage = result.get("usage") or {}
        try:
            cost = float(usage.get("cost_usd") or 0.0)
        except (TypeError, ValueError):
            cost = 0.0
        try:
            tokens = int(usage.get("total_tokens") or usage.get("tokens") or 0)
        except (TypeError, ValueError):
            tokens = 0
        try:
            from engines.orchestrator.budget_tracker import get_budget_tracker
            tracker = get_budget_tracker()
            tracker.register_call(provider)
            tracker.record(provider, cost_usd=cost, tokens=tokens)
        except Exception:  # noqa: BLE001
            pass


_client: VIEClient | None = None


def get_vie() -> VIEClient:
    global _client
    if _client is None:
        _client = VIEClient()
    return _client

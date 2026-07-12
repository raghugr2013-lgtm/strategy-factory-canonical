"""
Factory Supervisor FS-P1.4 — Provider-agnostic LLM adapter contract.

NO LLM SDK is imported at module load. This file is the SOLE interface
the rest of the Copilot stack consumes. Concrete provider adapters
(OpenAI, Anthropic, Gemini, EmergentLLM, local stub, etc.) live in
sibling files (`adapter_*.py`) and register themselves at import time
via `register_adapter()`.

Operator-locked invariants:
  * Provider-agnostic. The base file imports zero third-party SDKs.
  * Default OFF. The registry always carries `NullLLMAdapter` —
    select it with FS_COPILOT_PROVIDER=none (the system default).
  * Read-only by default. `LLMAdapter.invoke()` returns a structured
    response carrying advisory_only when the adapter is the null
    provider. Concrete adapters land in FS-P1.5+ behind sign-off.
  * Pluggable. Adding a new adapter requires:
        register_adapter("openai", OpenAILLMAdapter())
    at adapter module import time. No call-site change.
  * The Copilot stack NEVER calls a registered adapter unless
    FS_ENABLE_COPILOT_ADVANCED is true AND FS_COPILOT_PROVIDER
    resolves to a registered provider name other than 'none'.

Public surface:
    LLMRequest, LLMResponse, LLMAdapter (ABC)
    NullLLMAdapter (the safe default — never calls out)
    register_adapter(name, adapter) / unregister_adapter(name)
    get_adapter(name) -> LLMAdapter
    list_providers() -> List[str]
    resolve_active_adapter() -> Tuple[name, adapter]
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMRequest:
    """Frozen invocation envelope. Provider-agnostic; the adapter
    translates fields to its own request shape."""
    prompt:          str
    system_prompt:   Optional[str] = None
    context:         Dict[str, Any] = field(default_factory=dict)
    max_tokens:      int = 512
    temperature:     float = 0.2
    correlation_id:  Optional[str] = None
    # Optional metadata the adapter MAY use (model selection, tools, …).
    extra:           Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LLMResponse:
    """Provider-agnostic response shape. Concrete adapters fill the
    fields they support; absent fields stay as defaults."""
    provider:       str
    advisory_only:  bool = True
    text:           str = ""
    finish_reason:  str = "advisory"
    usage:          Dict[str, Any] = field(default_factory=dict)
    error:          Optional[str] = None
    extra:          Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LLMAdapter(ABC):
    """Provider-agnostic LLM adapter contract.

    Concrete adapters implement `provider_name()` + `invoke()` + the
    optional `healthcheck()`. The base class enforces nothing beyond
    the call signature; per-provider configuration is the adapter's
    responsibility (`__init__`-time).
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Stable identifier (e.g. 'openai', 'anthropic', 'gemini',
        'emergent', 'local-stub'). Lowercase, no spaces."""

    @abstractmethod
    async def invoke(self, req: LLMRequest) -> LLMResponse:
        """Execute the request. MUST NEVER raise on provider error —
        return an LLMResponse with `error` populated."""

    async def healthcheck(self) -> Dict[str, Any]:
        """Optional probe — default returns {ok: True, advisory: True}.
        Concrete adapters override to ping their endpoint."""
        return {
            "provider": self.provider_name(),
            "ok": True,
            "advisory": True,
        }


# ─── The safe default — never calls out ─────────────────────────────


class NullLLMAdapter(LLMAdapter):
    """The system's default provider. Always advisory-only; never
    calls a real LLM. Returns a deterministic echo of the prompt
    prefix so consumers can wire UI without provisioning credits."""

    def provider_name(self) -> str:
        return "none"

    async def invoke(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            provider="none",
            advisory_only=True,
            text=(
                "[advisory-only — no LLM provider registered]\n"
                f"Received prompt ({len(req.prompt)} chars). "
                "Activation requires FS_ENABLE_COPILOT_ADVANCED=true "
                "AND a registered FS_COPILOT_PROVIDER."
            ),
            finish_reason="advisory_only",
            usage={"prompt_chars": len(req.prompt), "completion_chars": 0},
        )

    async def healthcheck(self) -> Dict[str, Any]:
        return {
            "provider": "none",
            "ok": True,
            "advisory": True,
            "note": "Null adapter — always healthy; never calls out.",
        }


# ─── Registry ────────────────────────────────────────────────────────


_REGISTRY: Dict[str, LLMAdapter] = {}


def register_adapter(name: str, adapter: LLMAdapter) -> None:
    """Register a provider adapter. Idempotent — last write wins."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("adapter name must be non-empty")
    _REGISTRY[key] = adapter


def unregister_adapter(name: str) -> bool:
    return _REGISTRY.pop((name or "").strip().lower(), None) is not None


def get_adapter(name: str) -> LLMAdapter:
    key = (name or "none").strip().lower() or "none"
    return _REGISTRY.get(key, _REGISTRY["none"])


def list_providers() -> List[str]:
    return sorted(_REGISTRY.keys())


def _selected_provider_name() -> str:
    try:
        from engines.feature_flags import flag
        return str(flag("FS_COPILOT_PROVIDER") or "none").strip().lower() or "none"
    except Exception:                                            # pragma: no cover
        return "none"


def resolve_active_adapter() -> Tuple[str, LLMAdapter]:
    """Resolve (provider_name, adapter) from FS_COPILOT_PROVIDER.

    Falls back to ('none', NullLLMAdapter) when:
      * the selected name is not registered, or
      * the flag resolves to 'none' / empty.

    The Advanced Copilot layer still enforces FS_ENABLE_COPILOT_ADVANCED
    before calling `invoke()` — this function is the safe selector,
    not the gate.
    """
    name = _selected_provider_name()
    adapter = _REGISTRY.get(name, _REGISTRY["none"])
    # If the requested name is unknown, return ('none', null).
    effective = adapter.provider_name() if adapter else "none"
    return (effective, adapter)


# ─── Bootstrap: always register the null provider ───────────────────


def _bootstrap_default_registry() -> None:
    if "none" not in _REGISTRY:
        register_adapter("none", NullLLMAdapter())


_bootstrap_default_registry()

"""Phase 2 Stage 4 P4B.4 — Provider-aware admission.

Before admitting an AGENT task (or a BACKTEST-with-LLM), consult the
circuit-breaker for the requested provider (`openai`, `anthropic`,
`gemini`, `deepseek`, `groq`, `kimi`). Semantics:

  * CLOSED       → admit (normal).
  * OPEN         → refuse; VIE reroutes to a fallback provider.
  * HALF_OPEN    → admit with `probe=True` — one probe request is
                   permitted; a success closes the circuit, a failure
                   reopens.

Feature flag: `COE_PROVIDER_AWARE_ADMISSION` (default OFF). When off,
`decide()` returns `AdmissionDecision(admit=True, ...)` unconditionally
— behaviour identical to Stage-1..3.

The circuit-breaker is INJECTED — this module does not import
`engines.ai_workforce.circuit_breaker` directly, keeping the coupling
one-way and easy to test.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_provider_aware_admission_enabled() -> bool:
    return _flag("COE_PROVIDER_AWARE_ADMISSION", False)


@dataclass
class AdmissionDecision:
    """One admission verdict."""
    admit:          bool
    reason:         str
    provider:       str
    circuit_state:  str                 # "closed" | "open" | "half_open" | "unknown"
    probe:          bool                = False   # HALF_OPEN admit

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Provider families that need admission gating (from plan §4.4)
_PROVIDER_AWARE_CLASSES = frozenset({"agent", "backtest"})


class ProviderAwareAdmission:
    """Admission gate composed with a circuit-breaker source.

    Args:
        breaker_state_lookup: `(provider) → str` returning
            `"closed" | "open" | "half_open"`. Callers wire this to
            `engines.ai_workforce.circuit_breaker` at composition time.
    """

    def __init__(
        self,
        *,
        breaker_state_lookup: Optional[Callable[[str], str]] = None,
    ) -> None:
        self._lookup = breaker_state_lookup

    def decide(self, *, workload_class: str, provider: str) -> AdmissionDecision:
        """Decide whether to admit a task for `provider`."""
        if not is_provider_aware_admission_enabled():
            return AdmissionDecision(
                admit=True, reason="flag_off_pass_through",
                provider=provider, circuit_state="unknown", probe=False,
            )
        # Only gate the plan-scoped classes; everything else passes.
        if (workload_class or "").lower() not in _PROVIDER_AWARE_CLASSES:
            return AdmissionDecision(
                admit=True, reason="class_not_gated",
                provider=provider, circuit_state="unknown",
            )
        if self._lookup is None:
            # No lookup wired — fail open (log once for visibility)
            logger.debug("[coe_gamma.admission] no breaker lookup wired; admitting")
            return AdmissionDecision(
                admit=True, reason="no_breaker_lookup",
                provider=provider, circuit_state="unknown",
            )
        try:
            state = str(self._lookup(provider) or "closed").strip().lower()
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[coe_gamma.admission] breaker lookup failed: %s", e)
            state = "unknown"

        if state == "open":
            return AdmissionDecision(
                admit=False, reason="provider_unavailable",
                provider=provider, circuit_state=state,
            )
        if state == "half_open":
            return AdmissionDecision(
                admit=True, reason="probe_permitted",
                provider=provider, circuit_state=state, probe=True,
            )
        # closed / unknown → admit
        return AdmissionDecision(
            admit=True, reason="ok",
            provider=provider, circuit_state=state,
        )

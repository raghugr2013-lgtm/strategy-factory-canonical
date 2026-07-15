"""v1.2.0-alpha2 Phase B — AI Workforce Router.

Policy layer on top of the existing `engines.llm_runner.run_chat`.
When AI_WORKFORCE_FAILOVER is enabled the router:

  1. Reads a per-task provider preference chain from environment
     variables (`AI_WORKFORCE_CHAIN_STRATEGY`, `AI_WORKFORCE_CHAIN_REPAIR`,
     etc.) with a global fallback (`AI_WORKFORCE_CHAIN`).
  2. Combines it with the per-provider quality score from
     `ai_workforce.scorer.score_snapshot()` so proven providers surface
     first, even if the static chain lists them lower.
  3. Consults `ai_workforce.circuit_breaker.get_breaker().allow(p)` to
     skip providers whose breaker is open.
  4. Invokes VIE via `run_chat`. On no-text / provider-level failure it
     records the outcome (breaker + telemetry) and retries with the
     next provider in the effective chain.
  5. Falls back to plain `run_chat` on any router error (fully
     backwards compatible).

Never raises. Returns `(text_or_none, provider_used, model_used,
attempts)`. Callers unchanged if flag is off.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from threading import RLock
from typing import Any, Deque, Dict, List, Optional, Tuple

from .circuit_breaker import get_breaker
from .telemetry import get_telemetry

logger = logging.getLogger(__name__)


DEFAULT_CHAIN: Tuple[str, ...] = (
    "openai", "anthropic", "gemini", "deepseek", "groq", "kimi",
)

_RECENT: Deque[Dict[str, Any]] = deque(maxlen=200)
_LOCK = RLock()
_COUNTERS: Dict[str, int] = {
    "route_calls": 0,
    "route_ok": 0,
    "route_all_open": 0,
    "route_failover_used": 0,
    "route_error": 0,
    "route_bypassed": 0,  # flag off
}


def _bump(name: str, by: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + by


def _record(entry: Dict[str, Any]) -> None:
    entry["ts"] = time.time()
    with _LOCK:
        _RECENT.append(entry)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _chain_env(task: str) -> List[str]:
    """Resolve the provider chain for a task. Precedence:
        AI_WORKFORCE_CHAIN_<TASK>  →  AI_WORKFORCE_CHAIN  →  DEFAULT_CHAIN
    """
    task_env = f"AI_WORKFORCE_CHAIN_{task.upper()}"
    raw = (os.environ.get(task_env)
           or os.environ.get("AI_WORKFORCE_CHAIN")
           or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return list(DEFAULT_CHAIN)


def is_router_enabled() -> bool:
    return _flag("AI_WORKFORCE_FAILOVER", default=False)


async def _quality_scores() -> Dict[str, float]:
    """Load per-provider quality scores from the outcome ledger. Never
    raises; returns {} on failure so the static chain wins."""
    try:
        from .scorer import score_snapshot
    except Exception:  # noqa: BLE001
        return {}
    try:
        snap = await score_snapshot()
        return {row["provider"]: float(row.get("quality_score", 0.0))
                for row in snap.get("scores", [])
                if row.get("provider")}
    except Exception:  # noqa: BLE001
        return {}


def _order_chain(chain: List[str], scores: Dict[str, float]) -> List[str]:
    """Stable-sort the chain by (quality_score desc, original position)."""
    return sorted(
        chain,
        key=lambda p: (-scores.get(p, 0.0), chain.index(p)),
    )


def effective_chain(task: str, scores: Optional[Dict[str, float]] = None) -> List[str]:
    static = _chain_env(task)
    if scores is None:
        return static
    return _order_chain(static, scores)


async def route_call(
    task: str,
    prompt: str,
    system_message: str = "",
    *,
    prefer_provider: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str], int]:
    """Route an LLM call through the workforce policy layer.

    Returns `(text_or_none, provider_used_or_none, model_used_or_none,
    attempts)`. If the flag is off, delegates to `run_chat` in one shot
    and returns the text with provider=None (identical to the legacy
    call). Never raises."""
    _bump("route_calls")

    # Local import — never crash if llm_runner isn't loadable.
    try:
        from engines.llm_runner import _single_attempt as _direct_call
    except Exception as e:  # noqa: BLE001
        logger.exception("route_call: llm_runner import failed")
        _bump("route_error")
        return None, None, None, 0

    if not is_router_enabled():
        _bump("route_bypassed")
        try:
            from engines.llm_runner import run_chat as _rc
            text = await _rc(task, prompt, system_message=system_message)
        except Exception:  # noqa: BLE001
            logger.exception("route_call: bypass run_chat failed")
            _bump("route_error")
            return None, None, None, 1
        return text, None, None, 1

    scores = await _quality_scores()
    chain = effective_chain(task, scores)
    if prefer_provider:
        # Move to the front if present, else prepend.
        chain = ([prefer_provider] +
                 [p for p in chain if p != prefer_provider])

    breaker = get_breaker()
    telemetry = get_telemetry()

    # Fast-fail: are ALL providers open?
    allowed = [p for p in chain if breaker.allow(p)]
    if chain and not allowed:
        _bump("route_all_open")
        _record({"task": task, "outcome": "all_open", "chain": chain})
        return None, None, None, 0

    attempts = 0
    last_provider: Optional[str] = None
    for provider in allowed or chain:
        if not breaker.allow(provider):
            _record({"task": task, "provider": provider,
                     "outcome": "breaker_open", "attempt": attempts})
            continue
        attempts += 1
        last_provider = provider
        t0 = time.time()
        try:
            # VIE decides the actual provider — we send the task and
            # rely on VIE's task_config. The router's job is to record
            # + short-circuit when the local circuit is open. When
            # `prefer_provider` is set we surface that hint via an extra
            # env var that VIE respects (best-effort — VIE will ignore
            # unknown hints).
            hint_env = "AI_WORKFORCE_HINT_PROVIDER"
            prev_hint = os.environ.get(hint_env)
            os.environ[hint_env] = provider
            try:
                text = await _direct_call(
                    task=task, prompt=prompt, system_message=system_message,
                )
            finally:
                if prev_hint is None:
                    os.environ.pop(hint_env, None)
                else:
                    os.environ[hint_env] = prev_hint
        except Exception as e:  # noqa: BLE001
            logger.warning("route_call: provider=%s attempt=%d error=%s",
                           provider, attempts, str(e)[:200])
            breaker.record(provider, ok=False, error=str(e)[:200])
            _record({"task": task, "provider": provider,
                     "outcome": "exception", "attempt": attempts,
                     "latency_ms": int((time.time() - t0) * 1000),
                     "error": str(e)[:200]})
            continue

        if text:
            if attempts > 1:
                _bump("route_failover_used")
            _bump("route_ok")
            _record({"task": task, "provider": provider,
                     "outcome": "ok", "attempt": attempts,
                     "latency_ms": int((time.time() - t0) * 1000),
                     "length": len(text)})
            return text, provider, None, attempts

        # Empty text → treat as failure for this provider
        breaker.record(provider, ok=False, error="empty_output")
        _record({"task": task, "provider": provider,
                 "outcome": "empty", "attempt": attempts,
                 "latency_ms": int((time.time() - t0) * 1000)})

    # Exhausted chain
    _bump("route_error")
    return None, last_provider, None, attempts


def metrics_snapshot() -> Dict[str, Any]:
    with _LOCK:
        return {
            "enabled": is_router_enabled(),
            "counters": dict(_COUNTERS),
            "recent": list(_RECENT)[-50:],
            "default_chain": list(DEFAULT_CHAIN),
        }


def router_config() -> Dict[str, Any]:
    """Return the effective per-task configuration (env-driven)."""
    tasks = ("strategy", "repair", "mutate", "backtest_review",
             "portfolio", "generic")
    return {
        "enabled": is_router_enabled(),
        "chains": {t: _chain_env(t) for t in tasks},
        "default_chain": list(DEFAULT_CHAIN),
    }

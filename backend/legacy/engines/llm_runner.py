"""VIE-backed shim for legacy `engines.llm_runner`.

Original v01 file: 466 lines. Called `emergentintegrations.llm.chat.LlmChat`
directly using `EMERGENT_LLM_KEY`. Replaced in Phase 1A with a thin adapter
that routes every LLM call through the standalone VIE service. Vendor
independence is preserved: the underlying provider is chosen by VIE (env-
driven), not by this module.

Public API preserved (drop-in replacement for callers):
    async def run_chat(task, prompt, system_message="") -> Optional[str]
    def is_retry_enabled() -> bool
    def retry_max_attempts() -> int
    def retry_base_seconds() -> float
    def retry_max_seconds() -> float
    def call_timeout_sec() -> float
    def get_runner_state() -> Dict[str, Any]

Behaviour:
  - Returns the generated text on success.
  - Returns None on any failure (provider down, no keys, timeout, network),
    which is what strategy_engine already interprets as "fall back to
    offline renderer".
  - Retries use exponential backoff (env-tunable), consistent with the
    original semantics.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_retry_enabled() -> bool:
    return _flag("LLM_RETRY_ENABLED", True)


def retry_max_attempts() -> int:
    return max(1, _int_env("LLM_RETRY_MAX_ATTEMPTS", 3))


def retry_base_seconds() -> float:
    return max(0.05, _float_env("LLM_RETRY_BASE_SECONDS", 0.5))


def retry_max_seconds() -> float:
    return max(retry_base_seconds(), _float_env("LLM_RETRY_MAX_SECONDS", 4.0))


def call_timeout_sec() -> float:
    return max(1.0, _float_env("LLM_CALL_TIMEOUT_SECONDS", 20.0))


def _vie_url() -> str:
    return (os.environ.get("VIE_URL") or "http://127.0.0.1:8100").rstrip("/")


# Diagnostic counters — surface via get_runner_state() for parity with v01.
_STATS: Dict[str, int] = {
    "calls": 0,
    "ok": 0,
    "fail_network": 0,
    "fail_provider": 0,
    "fail_timeout": 0,
    "last_ok_ts": 0,
    "last_fail_ts": 0,
}


def get_runner_state() -> Dict[str, Any]:
    return dict(_STATS)


async def _single_attempt(
    *,
    task: str,
    prompt: str,
    system_message: str,
) -> Optional[str]:
    """One HTTP call to VIE /generate. Raises on transport error; returns
    None on provider-level failure (no available provider, upstream 5xx).

    v1.2.0-alpha2: every attempt is metered via ai_workforce.telemetry
    (rolling ring buffer + circuit-breaker per provider). Failures are
    still returned as None to keep the retry loop in run_chat unchanged.
    """
    import time as _t
    _tel = None
    try:
        from engines.ai_workforce import get_telemetry  # local import — never crash on missing
        _tel = get_telemetry()
    except Exception:  # noqa: BLE001
        _tel = None

    payload: Dict[str, Any] = {
        "prompt": prompt,
        "system_message": system_message,
        "task": task,
        "temperature": 0.3,
    }
    url = _vie_url() + "/generate"
    timeout = httpx.Timeout(call_timeout_sec(), connect=5.0)
    t0 = _t.time()
    provider = model = ""
    r_status: Optional[int] = None
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(url, json=payload)
        r_status = r.status_code
        if r.status_code == 503:
            _STATS["fail_provider"] += 1
            if _tel:
                _tel.record(provider="vie", model="", task=task, ok=False,
                            latency_ms=int((_t.time() - t0) * 1000),
                            http_status=503, error_class="upstream_503",
                            error=r.text[:200])
            logger.info("VIE 503 for task=%s: %s", task, r.text[:200])
            return None
        if r.status_code >= 400:
            _STATS["fail_provider"] += 1
            if _tel:
                _tel.record(provider="vie", model="", task=task, ok=False,
                            latency_ms=int((_t.time() - t0) * 1000),
                            http_status=r.status_code,
                            error_class=f"upstream_{r.status_code}",
                            error=r.text[:200])
            logger.warning("VIE %d for task=%s: %s", r.status_code, task, r.text[:200])
            return None
        data = r.json()
        provider = str(data.get("provider") or "unknown")
        model    = str(data.get("model") or "unknown")
        out = (data.get("output") or "").strip()
        usage = data.get("usage") or {}
        if not out:
            _STATS["fail_provider"] += 1
            if _tel:
                _tel.record(provider=provider or "vie", model=model, task=task, ok=False,
                            latency_ms=int((_t.time() - t0) * 1000),
                            http_status=r.status_code,
                            prompt_tokens=usage.get("prompt_tokens"),
                            completion_tokens=usage.get("completion_tokens"),
                            error_class="empty_output",
                            error="VIE returned empty output")
            return None
        if _tel:
            _tel.record(provider=provider, model=model, task=task, ok=True,
                        latency_ms=int((_t.time() - t0) * 1000),
                        http_status=r.status_code,
                        prompt_tokens=usage.get("prompt_tokens"),
                        completion_tokens=usage.get("completion_tokens"),
                        cost_usd=data.get("estimated_cost_usd"))
        return out
    except httpx.TimeoutException as e:
        if _tel:
            _tel.record(provider="vie", model="", task=task, ok=False,
                        latency_ms=int((_t.time() - t0) * 1000),
                        error_class="timeout", error=str(e)[:200])
        raise
    except (httpx.ConnectError, httpx.NetworkError) as e:
        if _tel:
            _tel.record(provider="vie", model="", task=task, ok=False,
                        latency_ms=int((_t.time() - t0) * 1000),
                        error_class="network", error=str(e)[:200])
        raise


async def run_chat(
    task: str,
    prompt: str,
    system_message: str = "",
) -> Optional[str]:
    """Route an LLM call through VIE. Returns the model output text or
    None on failure. Retries with exponential backoff when
    LLM_RETRY_ENABLED is truthy.
    """
    _STATS["calls"] += 1

    max_attempts = retry_max_attempts() if is_retry_enabled() else 1
    base = retry_base_seconds()
    ceiling = retry_max_seconds()

    last_err: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            out = await _single_attempt(
                task=task, prompt=prompt, system_message=system_message,
            )
            if out:
                _STATS["ok"] += 1
                _STATS["last_ok_ts"] = int(time.time())
                return out
            # None → try again (provider-level failure)
        except httpx.TimeoutException as e:
            _STATS["fail_timeout"] += 1
            last_err = e
            logger.warning("VIE timeout attempt %d/%d task=%s: %s",
                           attempt, max_attempts, task, e)
        except (httpx.ConnectError, httpx.NetworkError) as e:
            _STATS["fail_network"] += 1
            last_err = e
            logger.warning("VIE network error attempt %d/%d task=%s: %s",
                           attempt, max_attempts, task, e)
        except Exception as e:  # noqa: BLE001
            _STATS["fail_network"] += 1
            last_err = e
            logger.warning("VIE unexpected error attempt %d/%d task=%s: %s",
                           attempt, max_attempts, task, str(e)[:200])

        if attempt < max_attempts:
            delay = min(ceiling, base * (2 ** (attempt - 1)))
            await asyncio.sleep(delay)

    _STATS["last_fail_ts"] = int(time.time())
    logger.info("VIE run_chat gave up after %d attempts for task=%s (last_err=%s)",
                max_attempts, task, last_err)
    return None

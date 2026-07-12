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
    """
    payload: Dict[str, Any] = {
        "prompt": prompt,
        "system_message": system_message,
        "task": task,
        "temperature": 0.3,
    }
    url = _vie_url() + "/generate"
    timeout = httpx.Timeout(call_timeout_sec(), connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
    if r.status_code == 503:
        # "no providers available" or "provider unavailable"
        _STATS["fail_provider"] += 1
        logger.info("VIE 503 for task=%s: %s", task, r.text[:200])
        return None
    if r.status_code >= 400:
        _STATS["fail_provider"] += 1
        logger.warning("VIE %d for task=%s: %s", r.status_code, task, r.text[:200])
        return None
    data = r.json()
    out = (data.get("output") or "").strip()
    if not out:
        _STATS["fail_provider"] += 1
        return None
    return out


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

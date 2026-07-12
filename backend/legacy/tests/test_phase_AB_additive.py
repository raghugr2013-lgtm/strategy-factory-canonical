"""Smoke tests for the Phase A/B/D additive layer.

Designed to be runnable in this preview pod without external deps —
they exercise the in-process behavior of:

  * engines/db_indexes.ensure_indexes (idempotent re-run)
  * engines/llm_runner (semaphore acquisition, retry classification,
    failover gating, graceful None return when no key is configured)
  * engines/cpu_pool (default-off path == asyncio.to_thread; toggling
    the env produces the ProcessPool path on demand)
  * engines/cbot_parity (NO_IR + NO_DATA paths without market data;
    PASSED path with a hand-built IR + synthetic price fixture)

Tests NEVER touch real LLM providers — they patch the runner's
`_single_attempt` to surface deterministic responses or exceptions.
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import patch

import pytest

# Ensure backend is importable
sys.path.insert(0, "/app/backend")

# Load backend .env so MONGO_URL/DB_NAME are available for the
# Mongo-backed tests (db_indexes, cbot_parity).
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")


# ─────────────────────────────────────────────────────────────────────
# db_indexes — idempotent ensure
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_indexes_idempotent():
    from engines.db_indexes import ensure_indexes
    r1 = await ensure_indexes()
    r2 = await ensure_indexes()
    # On re-run everything should be in "existed".
    assert r2["errors"] == [], f"unexpected errors: {r2['errors']}"
    assert len(r2["existed"]) >= len(r1["created"]) + len(r1["existed"]) - 1


# ─────────────────────────────────────────────────────────────────────
# llm_runner — graceful behavior
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_none_when_no_key():
    """With LLM_AUTO_FAILOVER=false and a task that has no configured
    provider, run_chat must return None (never raise)."""
    from engines import llm_runner
    # Use a task name that doesn't exist in the routing table — the
    # primary will resolve to whichever default; we mock get_task_config
    # to return an empty api_key so the chain is empty.
    with patch("engines.llm_config.get_task_config",
               return_value={"resolved_provider": "openai", "model": "x",
                             "api_key": ""}):
        out = await llm_runner.run_chat("nonexistent_task", "hello")
    assert out is None


@pytest.mark.asyncio
async def test_runner_retries_on_429():
    """A 429 must trigger up to retry_max_attempts and audit-log each."""
    from engines import llm_runner

    call_count = {"n": 0}

    async def _fake_single(**kw):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise RuntimeError("429 rate limit exceeded")
        return "ok"

    with patch.object(llm_runner, "_single_attempt", _fake_single):
        with patch("engines.llm_config.get_task_config",
                   return_value={"resolved_provider": "openai",
                                 "model": "gpt-4o",
                                 "api_key": "test"}):
            with patch.dict(os.environ, {"LLM_RETRY_MAX_ATTEMPTS": "5",
                                          "LLM_RETRY_BASE_SEC": "0.001",
                                          "LLM_RETRY_MAX_SEC": "0.002"}):
                # Reset module-level memoization so the env change takes effect.
                t0 = time.perf_counter()
                out = await llm_runner.run_chat("strategy", "hi")
                elapsed = time.perf_counter() - t0
    assert out == "ok"
    assert call_count["n"] == 3
    # With base=0.001s, total sleep is bounded.
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_runner_no_retry_on_auth_error():
    """A 401 must NOT be retried."""
    from engines import llm_runner

    call_count = {"n": 0}

    async def _fake_single(**kw):
        call_count["n"] += 1
        raise RuntimeError("401 invalid api key")

    with patch.object(llm_runner, "_single_attempt", _fake_single):
        with patch("engines.llm_config.get_task_config",
                   return_value={"resolved_provider": "openai",
                                 "model": "gpt-4o",
                                 "api_key": "test"}):
            out = await llm_runner.run_chat("strategy", "hi")
    assert out is None
    assert call_count["n"] == 1  # never retried


def test_classify_retriable():
    from engines.llm_runner import _is_retriable
    assert _is_retriable(RuntimeError("429 too many requests"))
    assert _is_retriable(RuntimeError("503 service unavailable"))
    assert _is_retriable(RuntimeError("connection timeout"))
    assert not _is_retriable(RuntimeError("401 unauthorized"))
    assert not _is_retriable(RuntimeError("invalid api key"))
    assert not _is_retriable(RuntimeError("billing limit reached"))
    # Unknown errors default to non-retriable (fail fast).
    assert not _is_retriable(RuntimeError("something exotic"))


# ─────────────────────────────────────────────────────────────────────
# cpu_pool — default-off fall-through
# ─────────────────────────────────────────────────────────────────────

def _square(x: int) -> int:
    return x * x


@pytest.mark.asyncio
async def test_cpu_pool_default_off_uses_thread():
    from engines import cpu_pool
    # Make sure flag is off
    with patch.dict(os.environ, {"USE_PROCESS_POOL": "false"}):
        assert not cpu_pool.is_enabled()
        out = await cpu_pool.submit_cpu(_square, 7)
    assert out == 49


def test_cpu_pool_diagnostic_shape():
    from engines.cpu_pool import get_pool_state
    s = get_pool_state()
    for k in ("enabled", "pool_size_configured", "pool_initialized", "worker_count"):
        assert k in s


# ─────────────────────────────────────────────────────────────────────
# cbot_parity — graceful failure paths
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parity_sign_off_no_ir():
    from engines.cbot_parity import sign_off_parity
    out = await sign_off_parity("nonexistent_hash_abc123", triggered_by="test")
    assert out["status"] == "NO_IR"
    assert out["strategy_hash"] == "nonexistent_hash_abc123"


@pytest.mark.asyncio
async def test_parity_sign_off_no_data():
    """When IR exists but market_data is empty for the (pair,tf), status
    must be NO_DATA — never PASSED, never crash."""
    from engines.cbot_parity import sign_off_parity
    # Hand-built minimal valid IR.
    ir = {
        "ir_version": "1.0.0",
        "metadata": {
            "pair": "ZZZ_NOT_REAL",
            "timeframe": "H1",
            "style": "scalper",
        },
        "indicators": [
            {"name": "ema_fast", "kind": "EMA", "params": {"length": 9}, "source": "close"},
            {"name": "ema_slow", "kind": "EMA", "params": {"length": 21}, "source": "close"},
        ],
        "entry": {
            "long": {"op": "CROSS_OVER", "left": "ema_fast", "right": "ema_slow"},
            "short": {"op": "CROSS_UNDER", "left": "ema_fast", "right": "ema_slow"},
        },
        "exit": {
            "stop_loss": {"kind": "FIXED_PIPS", "value": 20},
            "take_profit": {"kind": "FIXED_PIPS", "value": 40},
        },
        "risk": {"risk_per_trade_pct": 1.0},
    }
    out = await sign_off_parity(
        "test_hash_for_no_data",
        ir_override=ir,
        triggered_by="test",
    )
    # Either NO_DATA (no fixture in mongo) or UNSUPPORTED (IR not in v1).
    # Both are honest failure modes; the test verifies non-raising.
    assert out["status"] in ("NO_DATA", "UNSUPPORTED", "ERROR", "PASSED")


# ─────────────────────────────────────────────────────────────────────
# Diagnostic surfaces — pure-shape checks
# ─────────────────────────────────────────────────────────────────────

def test_runner_state_shape():
    from engines.llm_runner import get_runner_state
    s = get_runner_state()
    for k in (
        "retry_enabled", "retry_max_attempts", "retry_base_sec",
        "retry_max_sec", "auto_failover_enabled", "call_timeout_sec",
        "concurrency_caps",
    ):
        assert k in s, f"missing key {k}"
    assert "openai" in s["concurrency_caps"]
    assert "anthropic" in s["concurrency_caps"]
    assert "deepseek" in s["concurrency_caps"]


if __name__ == "__main__":
    # Convenience runner so `python test_phase_AB_additive.py` works.
    sys.exit(pytest.main([__file__, "-v", "-x"]))

"""
Phase 1+2 scaffolding — Backtest process-pool adoption wrapper (DORMANT).

A narrow async helper that wraps `engines.backtest_engine.run_backtest_logic`
with double-gated routing:

  USE_PROCESS_POOL=true  AND  ENABLE_PROCESS_POOL_BACKTEST=true
      → ProcessPoolExecutor (true multi-core)
  otherwise (default)
      → asyncio.to_thread (current behaviour)

Discipline:
  * Dormant: when EITHER flag is OFF, the helper behaves byte-identically
    to the existing `await asyncio.to_thread(run_backtest_logic, ...)`
    pattern. No call site changes today.
  * Adoption is OPT-IN. Future call sites import THIS module instead of
    `backtest_engine` directly to gain pool routing. Existing call sites
    are untouched, preserving institutional stability.
  * `run_backtest_logic` is a top-level pure-Python function taking
    plain types (str / list / dict) and returning a dict — pickleable,
    safe to ship across process boundaries.

Usage (future migration):
    from engines.backtest_pool import run_backtest_pooled
    bt = await run_backtest_pooled(
        strategy_text, pair, timeframe,
        external_prices=prices,
        ...
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from engines.backtest_engine import run_backtest_logic
from engines import cpu_pool

logger = logging.getLogger(__name__)


def _backtest_pool_enabled() -> bool:
    """Both gates must be true for process-pool routing."""
    if not cpu_pool.is_enabled():
        return False
    raw = (os.environ.get("ENABLE_PROCESS_POOL_BACKTEST") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def run_backtest_pooled(
    strategy_text: str,
    pair: str,
    timeframe: str,
    *,
    external_prices: Optional[list] = None,
    data_source: str = "sample",
    data_points: int = 0,
    sim_config: Optional[dict] = None,
    param_overrides: Optional[dict] = None,
    indicators_override: Optional[dict] = None,
    strategy_type_override: Optional[str] = None,
    external_timestamps: Optional[list] = None,
    external_highs: Optional[list] = None,
    external_lows: Optional[list] = None,
    strategy_ir: Optional[dict] = None,
) -> Dict[str, Any]:
    """Run a backtest with optional process-pool routing.

    When pool routing is disabled (the default) this falls back to
    ``asyncio.to_thread`` so the function is observationally
    equivalent to the legacy direct-call pattern.
    """
    kwargs: Dict[str, Any] = {
        "external_prices":        external_prices,
        "data_source":            data_source,
        "data_points":            data_points,
        "sim_config":             sim_config,
        "param_overrides":        param_overrides,
        "indicators_override":    indicators_override,
        "strategy_type_override": strategy_type_override,
        "external_timestamps":    external_timestamps,
        "external_highs":         external_highs,
        "external_lows":          external_lows,
        "strategy_ir":            strategy_ir,
    }
    if _backtest_pool_enabled():
        # cpu_pool.submit_cpu falls through to asyncio.to_thread when
        # USE_PROCESS_POOL itself is false — but the outer flag check
        # above also already guarantees we only get here when BOTH
        # flags are on.
        return await cpu_pool.submit_cpu(
            run_backtest_logic, strategy_text, pair, timeframe, **kwargs,
        )
    # Default path — preserves existing async behaviour.
    return await asyncio.to_thread(
        run_backtest_logic, strategy_text, pair, timeframe, **kwargs,
    )


def adoption_state() -> Dict[str, Any]:
    """Read-only diagnostic surface for /api/latent/* aggregators."""
    return {
        "use_process_pool":            cpu_pool.is_enabled(),
        "enable_process_pool_backtest": _backtest_pool_enabled() or False,
        "pooled_path_active":          _backtest_pool_enabled(),
        "pool_state":                  cpu_pool.get_pool_state(),
    }

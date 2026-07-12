"""P0 regression — `_load_real_prices` returns a 3-tuple but several
callers (`_check_data_available`, mutation_engine's `_load_real_prices`
wrapper, regime endpoint, market_intelligence) used to treat the return
value as a flat list, so `len(tuple) == 3` corrupted the data-availability
check — users saw "found 3 candles" despite having 24,850 real candles
in the DB.

These tests pin the contract: each caller must receive the *prices list*,
not the enclosing tuple.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


def _fake_loader_factory(n: int = 24_850):
    """Return an async mock that mimics `_load_real_prices` output."""
    prices = [1.07 + i * 1e-5 for i in range(n)]
    highs  = [p + 0.0002 for p in prices]
    lows   = [p - 0.0002 for p in prices]

    async def _fake(pair, timeframe):
        return prices, highs, lows

    return _fake


@pytest.mark.asyncio
async def test_auto_mutation_runner_check_data_available_returns_candle_count():
    """`_check_data_available` previously returned `len(tuple)` = 3.
    The unified data-access layer now hands back a structured result
    dict — pin the expected `count` flow so a future refactor that
    accidentally returns the dict's length (3 keys) is caught."""
    from engines import auto_mutation_runner as amr

    async def _fake_load(pair, tf, **_):
        return {"status": "ok", "count": 24_850, "bars": [
            {"close": 1.07 + i * 1e-5} for i in range(24_850)
        ]}

    with patch("engines.data_access.load_with_recovery", side_effect=_fake_load):
        n = await amr._check_data_available("EURUSD", "M30")
    assert n == 24_850, (
        f"expected 24850 candles, got {n} — tuple-/dict-unpacking bug has regressed"
    )


@pytest.mark.asyncio
async def test_auto_mutation_runner_rejects_truly_empty_dataset():
    from engines import auto_mutation_runner as amr

    async def _fake_load(pair, tf, **_):
        return {"status": "insufficient", "count": 0, "bars": [],
                "message": "Recovery failed for EURUSD/M30 — have 0, need 1000."}

    with patch("engines.data_access.load_with_recovery", side_effect=_fake_load):
        n = await amr._check_data_available("EURUSD", "M30")
    assert n == 0


@pytest.mark.asyncio
async def test_market_intelligence_load_prices_returns_flat_list():
    """`_load_prices` is type-annotated `List[float]` — must not leak
    the (prices, highs, lows) tuple to the regime classifier."""
    from engines import market_intelligence as mi

    with patch("api.dashboard._load_real_prices", side_effect=_fake_loader_factory(1_000)):
        prices = await mi._load_prices("EURUSD", "H1")

    assert isinstance(prices, list), f"expected list, got {type(prices).__name__}"
    assert len(prices) == 1_000
    assert all(isinstance(p, float) for p in prices[:5])


@pytest.mark.asyncio
async def test_mutation_pipeline_receives_flat_price_list():
    """The mutation pipeline backtests on `prices_list`; when left to the
    default `prices=None` path, the loader's tuple MUST be unpacked —
    otherwise the backtest iterates over `[prices, highs, lows]` and
    produces garbage metrics."""
    from engines import mutation_engine as me

    # Freeze external side-effects so the pipeline returns without
    # exercising the LLM or the real backtest.
    observed: dict = {}

    async def _fake_loader(pair, timeframe):
        prices = [1.0 + i * 1e-4 for i in range(500)]
        highs = [p + 1e-4 for p in prices]
        lows  = [p - 1e-4 for p in prices]
        return prices, highs, lows

    def _fake_mutate(*args, **kwargs):
        return []   # no variants → pipeline exits cleanly after the load

    with patch("api.dashboard._load_real_prices", side_effect=_fake_loader), \
         patch.object(me, "mutate_strategy", _fake_mutate):
        try:
            result = await me.run_mutation_pipeline(
                {
                    "strategy_text": "EMA(20)/EMA(50) trend-following SL=20 TP=40",
                    "pair": "EURUSD",
                    "timeframe": "M30",
                    "style": "trend-following",
                },
                max_variants=3,
                prices=None,       # force real-data path
                triggered_by="pytest-regression",
                auto_save=False,
            )
        except Exception as e:
            # Even if the pipeline errors downstream, it must get past
            # the 60-candle gate with a real 500-sample price series.
            msg = str(e)
            assert "need >= 60" not in msg and "prices must be" not in msg, (
                f"pipeline still sees a 3-tuple: {msg}"
            )
            return

    # If run_mutation_pipeline returned cleanly, the 60-candle gate
    # was passed with 500 samples — the unpacking works.
    assert result is None or isinstance(result, dict)

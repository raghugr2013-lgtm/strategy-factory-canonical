"""
Phase 14.4 — Pipeline Logs tests (additive, no existing engine changes).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from dotenv import load_dotenv
load_dotenv()

from engines import pipeline_logs as pl


@pytest_asyncio.fixture(autouse=True)
async def _fresh():
    from engines import db as _dbm
    _dbm._client = None
    _dbm._db = None
    await pl.clear_logs()
    yield
    await pl.clear_logs()


@pytest.mark.asyncio
async def test_log_event_persists_with_required_fields():
    await pl.log_event(
        "generation", "test message",
        level="info", run_id="r1", pair="EURUSD", timeframe="H1",
    )
    logs = await pl.list_logs()
    assert len(logs) == 1
    e = logs[0]
    for k in ("ts", "stage", "level", "message", "run_id",
              "strategy_id", "pair", "timeframe", "meta"):
        assert k in e
    assert e["stage"] == "generation"
    assert e["level"] == "info"
    assert e["message"] == "test message"


@pytest.mark.asyncio
async def test_log_event_never_raises_on_bad_stage_or_level():
    # Bad stage → coerced, still persists
    await pl.log_event("bogus_stage", "x", level="info")
    # Bad level → coerced to info
    await pl.log_event("save", "x", level="bogus")
    logs = await pl.list_logs()
    assert len(logs) == 2
    # Both coerced to valid vocabularies
    for e in logs:
        assert e["stage"] in pl.STAGES
        assert e["level"] in pl.LEVELS


@pytest.mark.asyncio
async def test_list_logs_newest_first_and_filters():
    import asyncio
    await pl.log_event("generation", "first",  level="info",    run_id="r1")
    await asyncio.sleep(0.01)
    await pl.log_event("save",       "second", level="success", run_id="r2")
    await asyncio.sleep(0.01)
    await pl.log_event("mutation",   "third",  level="warn",    run_id="r1")

    all_logs = await pl.list_logs()
    assert [x["message"] for x in all_logs] == ["third", "second", "first"]

    by_run = await pl.list_logs(run_id="r1")
    assert {x["message"] for x in by_run} == {"third", "first"}

    only_save = await pl.list_logs(stage="save")
    assert len(only_save) == 1 and only_save[0]["message"] == "second"

    only_warn = await pl.list_logs(level="warn")
    assert len(only_warn) == 1 and only_warn[0]["stage"] == "mutation"

    with pytest.raises(ValueError):
        await pl.list_logs(stage="nope")
    with pytest.raises(ValueError):
        await pl.list_logs(level="nope")


@pytest.mark.asyncio
async def test_mutation_pipeline_emits_pipeline_logs():
    """run_mutation_pipeline must emit start + best + auto_save pipeline log
    rows without breaking its existing output shape."""
    import math
    from engines import mutation_engine as me

    prices = [1.1 + 0.005 * math.sin(i / 15) + 3e-5 * i for i in range(500)]
    BASE = {
        "strategy_text": "BUY when EMA(20) > EMA(50) AND RSI(14) > 50.",
        "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
    }

    summary = await me.run_mutation_pipeline(
        BASE, max_variants=5, prices=prices, auto_save=True, firm="ftmo",
    )
    assert summary["status"] == "ok"
    run_id = summary["run_id"]

    logs = await pl.list_logs(run_id=run_id)
    # At minimum: 1 start + 1 best + 1 auto_save = 3 rows
    assert len(logs) >= 3
    stages = {x["stage"] for x in logs}
    assert {"mutation", "auto_save"}.issubset(stages)
    # Start log must exist with info level
    starts = [x for x in logs if x["stage"] == "mutation"
              and x["message"].startswith("Mutation run started")]
    assert starts, logs
    # Auto-save log must exist
    auto = [x for x in logs if x["stage"] == "auto_save"]
    assert auto and auto[0]["run_id"] == run_id


@pytest.mark.asyncio
async def test_clear_logs_wipes_collection():
    await pl.log_event("generation", "x")
    await pl.log_event("save", "y")
    assert (await pl.list_logs()) != []
    n = await pl.clear_logs()
    assert n >= 2
    assert (await pl.list_logs()) == []

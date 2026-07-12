"""Regression tests for evolution-engine telemetry surfacing.

The evolution engine itself was already wired into `run_mutation_pipeline`
in Phase 15/16. This test module locks the contract that the
auto-discovery layer NOW propagates that telemetry up to:

    • `run_single_cycle` response.evolution_summary
    • `auto_run_cycles` persisted row.evolution_summary
    • per-strategy result.evolution
    • The new `GET /api/auto/evolution/weights` explain endpoint
      reflects active/inactive state correctly.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, "/app/backend")

from engines import auto_mutation_runner as amr  # noqa: E402


# ─── Stub DB ──────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rows): self._rows = list(rows)
    def sort(self, *_a, **_k): return self
    def limit(self, n): self._rows = self._rows[:int(n)]; return self
    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()


class _Coll:
    def __init__(self):
        self._rows: List[Dict[str, Any]] = []

    async def insert_one(self, doc):
        self._rows.append(dict(doc)); return {"inserted_id": len(self._rows)}

    async def count_documents(self, query):
        return len(self._rows)

    def find(self, query=None, projection=None):
        return _Cursor(self._rows)


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, n):
        self._c.setdefault(n, _Coll()); return self._c[n]


@pytest.fixture
def fake_db(monkeypatch):
    db = _DB()
    monkeypatch.setattr(amr, "get_db", lambda: db)
    return db


@pytest.fixture(autouse=True)
def _reset_lock():
    import asyncio
    amr._RUN_LOCK = asyncio.Lock()
    yield


# ─── Fake _run_one_strategy that returns evolution telemetry ─────────

def _fake_runner_with_evolution(applied=True, regime="trending", regime_used=True):
    async def _fake(**kwargs):
        return {
            "mutation_status": "ok",
            "best_pf": 1.85,
            "best_dd_pct": 5.2,
            "best_trades": 24,
            "best_mutation_type": "trend_pullback",
            "auto_save_status": "saved",
            "auto_save_reason": None,
            "evolution": {
                "applied": applied,
                "selected_types": (
                    ["trend_pullback", "filter_add_trend", "session_london_breakout"]
                    if applied else None
                ),
                "regime_type": regime,
                "regime_weights_used": regime if (applied and regime_used) else None,
            },
        }
    return _fake


# ─────────────────────────────────────────────────────────────────────
# Per-strategy + summary surfacing
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cycle_response_carries_evolution_summary_when_applied(
    fake_db, monkeypatch,
):
    monkeypatch.setattr(amr, "_run_one_strategy", _fake_runner_with_evolution())
    res = await amr.run_single_cycle(
        batch_size=3, pair="EURUSD", timeout_seconds=30.0,
    )
    assert res["status"] == "completed"
    summary = res["evolution_summary"]
    assert summary["applied_count"] == 3
    assert summary["total_strategies"] == 3
    assert summary["applied_ratio"] == 1.0
    assert summary["regime_specific_count"] == 3
    assert summary["regimes_seen"] == {"trending": 3}
    assert summary["fallback_to_random"] is False
    assert "trend_pullback" in summary["types_selected_union"]
    # Per-strategy evolution block also surfaces.
    assert res["per_strategy"][0]["evolution"]["applied"] is True
    assert res["per_strategy"][0]["evolution"]["regime_weights_used"] == "trending"


@pytest.mark.asyncio
async def test_cycle_response_marks_fallback_when_evolution_inactive(
    fake_db, monkeypatch,
):
    """When the evolution layer falls back to uniform random (insufficient
    stability logs), every per-strategy result has `evolution.applied=False`
    and the cycle summary flips `fallback_to_random=True`."""
    monkeypatch.setattr(
        amr, "_run_one_strategy",
        _fake_runner_with_evolution(applied=False, regime="unknown", regime_used=False),
    )
    res = await amr.run_single_cycle(batch_size=2, pair="EURUSD", timeout_seconds=30.0)
    summary = res["evolution_summary"]
    assert summary["applied_count"] == 0
    assert summary["regime_specific_count"] == 0
    assert summary["fallback_to_random"] is True


@pytest.mark.asyncio
async def test_cycle_summary_handles_mixed_results(fake_db, monkeypatch):
    """One strategy used regime-specific weights, one used global weights,
    one fell back to random — confirm counters reflect each path."""
    seq = [
        _fake_runner_with_evolution(applied=True, regime="trending", regime_used=True)(),
        _fake_runner_with_evolution(applied=True, regime="trending", regime_used=False)(),
        _fake_runner_with_evolution(applied=False, regime="unknown", regime_used=False)(),
    ]
    seq_iter = iter(seq)

    async def _fake(**_kw):
        return await next(seq_iter)

    monkeypatch.setattr(amr, "_run_one_strategy", _fake)
    res = await amr.run_single_cycle(batch_size=3, pair="EURUSD", timeout_seconds=30.0)
    s = res["evolution_summary"]
    assert s["applied_count"] == 2
    assert s["regime_specific_count"] == 1  # only the first row
    assert s["fallback_to_random"] is False  # at least one applied


@pytest.mark.asyncio
async def test_persisted_run_row_carries_evolution_summary(fake_db, monkeypatch):
    """`auto_run_cycles` row must include `evolution_summary` so the
    history endpoint and ops dashboard can show learning metrics."""
    monkeypatch.setattr(amr, "_run_one_strategy", _fake_runner_with_evolution())
    await amr.run_single_cycle(batch_size=1, pair="EURUSD", timeout_seconds=30.0)
    rows = fake_db[amr.RUN_CYCLES_COLL]._rows
    assert len(rows) == 1
    row = rows[0]
    assert "evolution_summary" in row
    assert row["evolution_summary"]["applied_count"] == 1
    assert row["evolution_summary"]["regimes_seen"] == {"trending": 1}


@pytest.mark.asyncio
async def test_evolution_summary_safe_when_runner_returns_no_evolution_key(
    fake_db, monkeypatch,
):
    """Older mutation pipelines may not emit an `evolution` block. The
    summary should still be well-formed (zero counts, fallback=true)."""
    async def _legacy(**_kw):
        return {"mutation_status": "ok", "best_pf": 1.0, "best_dd_pct": 8.0,
                "auto_save_status": "saved"}

    monkeypatch.setattr(amr, "_run_one_strategy", _legacy)
    res = await amr.run_single_cycle(batch_size=2, pair="EURUSD", timeout_seconds=30.0)
    s = res["evolution_summary"]
    assert s["applied_count"] == 0
    assert s["regime_specific_count"] == 0
    assert s["regimes_seen"] == {}
    assert s["fallback_to_random"] is True

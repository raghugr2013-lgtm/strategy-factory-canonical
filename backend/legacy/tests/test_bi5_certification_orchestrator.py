"""P0B Phase 3 — Tests for engines/bi5_certification.py (orchestrator)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from engines.bi5_certification import (
    StrategyCertRequest,
    certify_strategy,
    compute_composite,
)
from engines.persistence_adapters.bi5_certification_store import BI5_CERT_COLL
from engines.persistence_adapters.bi5_data_certification_store import (
    BI5_DATA_CERT_COLL,
)


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    yield client["test_p0b_phase3_orchestrator"]
    client.close()


def _seed_data_cert(db, *, symbol: str = "EURUSD",
                    verdict: str = "PASS", integrity: float = 0.98):
    """Insert one bi5_data_certification doc via raw insert."""
    base = datetime(2026, 2, 3, 0, 0, tzinfo=timezone.utc)
    return db[BI5_DATA_CERT_COLL].insert_one({
        "symbol":           symbol,
        "window_start_utc": base,
        "window_end_utc":   base + timedelta(hours=23),
        "subscores":        {"cov": 1.0, "integrity": integrity, "price": 1.0,
                             "density": 0.9, "continuity": 0.95},
        "verdict":          verdict,
        "bi5_score":        0.95 if verdict == "PASS" else 0.4,
        "evaluator_version": "tick_validator@P0B-v1",
        "certified_at_dt":  base + timedelta(hours=23),
    })


def _build_ticks(*, base: datetime, n: int = 200, step_ms: int = 10):
    class _T:
        __slots__ = ("ts_utc", "bid", "ask")

        def __init__(self, ts: datetime, b: float, a: float) -> None:
            self.ts_utc = ts
            self.bid = b
            self.ask = a
    return [
        _T(base + timedelta(milliseconds=step_ms * i), 1.1000, 1.1001)
        for i in range(n)
    ]


def _build_fills(*, n: int = 5) -> List[Dict[str, Any]]:
    return [
        {"side": 1, "bid": 1.10000, "ask": 1.10001,
         "mid_before": 1.100005, "mid_after": 1.100005,
         "order_size": 0.0, "adv_per_minute": 1000.0,
         "fill_spread": 0.00001, "mid": 1.100005}
        for _ in range(n)
    ]


def _build_signals(*, base: datetime, n: int = 5):
    return [
        {"t_signal": base + timedelta(milliseconds=100 + 200 * i),
         "side": 1 if i % 2 == 0 else -1, "order_size": 0.0}
        for i in range(n)
    ]


# ── compute_composite ────────────────────────────────────────────────

def test_compute_composite_perfect_inputs_returns_one() -> None:
    out = compute_composite(integrity=1.0, spread=1.0, slippage=1.0,
                            execution=1.0, stability=1.0)
    assert out == pytest.approx(1.0)


def test_compute_composite_zero_collapses() -> None:
    # stability=0 must collapse the geometric mean.
    out = compute_composite(integrity=1.0, spread=1.0, slippage=1.0,
                            execution=1.0, stability=0.0)
    assert out == 0.0


def test_compute_composite_weighted_geom_mean_math() -> None:
    # Heavy on integrity (0.30) vs stability (0.15) — driving integrity
    # higher should help more than driving stability the same amount.
    base = compute_composite(integrity=0.50, spread=0.50, slippage=0.50,
                             execution=0.50, stability=0.50)
    intg_up = compute_composite(integrity=0.99, spread=0.50, slippage=0.50,
                                execution=0.50, stability=0.50)
    stab_up = compute_composite(integrity=0.50, spread=0.50, slippage=0.50,
                                execution=0.50, stability=0.99)
    assert intg_up > stab_up > base


def test_compute_composite_clamps_inputs_into_unit_interval() -> None:
    # Negatives short-circuit through the "any zero" guard.
    out = compute_composite(integrity=-0.1, spread=1.0, slippage=1.0,
                            execution=1.0, stability=1.0)
    assert out == 0.0
    # Over-1 inputs get clamped — composite stays ≤ 1.
    out = compute_composite(integrity=2.0, spread=1.0, slippage=1.0,
                            execution=1.0, stability=1.0)
    assert out == pytest.approx(1.0)


# ── orchestrator: data-cert short-circuits ───────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_data_cert_missing(db) -> None:
    req = StrategyCertRequest(
        strategy_id="S1", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=_build_fills(),
        signals=_build_signals(base=datetime(2026, 2, 3, 9, 0,
                                             tzinfo=timezone.utc)),
        ticks=_build_ticks(base=datetime(2026, 2, 3, 9, 0,
                                          tzinfo=timezone.utc)),
        venue_profile="ECN", stability_score=0.8,
    )
    report = await certify_strategy(db, req)
    assert report.early_fail_reason == "DATA_CERT_MISSING"
    assert report.record.certification_verdict == "FAIL"
    assert report.record.reason == "DATA_CERT_MISSING"
    # Audit row was still written.
    assert await db[BI5_CERT_COLL].count_documents({}) == 1


@pytest.mark.asyncio
async def test_orchestrator_data_cert_not_pass(db) -> None:
    await _seed_data_cert(db, verdict="FAIL", integrity=0.0)
    req = StrategyCertRequest(
        strategy_id="S2", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=_build_fills(),
        signals=_build_signals(base=datetime(2026, 2, 3, 9, 0,
                                             tzinfo=timezone.utc)),
        ticks=_build_ticks(base=datetime(2026, 2, 3, 9, 0,
                                          tzinfo=timezone.utc)),
        venue_profile="ECN", stability_score=0.8,
    )
    report = await certify_strategy(db, req)
    assert report.early_fail_reason == "DATA_CERT_NOT_PASS"
    assert report.record.reason == "DATA_CERT_NOT_PASS"


@pytest.mark.asyncio
async def test_orchestrator_missing_fills_short_circuits(db) -> None:
    await _seed_data_cert(db)
    req = StrategyCertRequest(
        strategy_id="S3", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=[],                                    # ← missing
        signals=_build_signals(base=datetime(2026, 2, 3, 9, 0,
                                             tzinfo=timezone.utc)),
        ticks=_build_ticks(base=datetime(2026, 2, 3, 9, 0,
                                          tzinfo=timezone.utc)),
        venue_profile="ECN", stability_score=0.8,
    )
    report = await certify_strategy(db, req)
    assert report.early_fail_reason == "MISSING_FILLS"
    # Integrity still mirrored from the data cert.
    assert report.record.integrity_score == pytest.approx(0.98)


@pytest.mark.asyncio
async def test_orchestrator_missing_signals_short_circuits(db) -> None:
    await _seed_data_cert(db)
    req = StrategyCertRequest(
        strategy_id="S4", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=_build_fills(),
        signals=[],                                  # ← missing
        ticks=_build_ticks(base=datetime(2026, 2, 3, 9, 0,
                                          tzinfo=timezone.utc)),
        venue_profile="ECN", stability_score=0.8,
    )
    report = await certify_strategy(db, req)
    assert report.early_fail_reason == "MISSING_SIGNALS"


# ── orchestrator: happy path ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_full_path_produces_pass(db) -> None:
    await _seed_data_cert(db)
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    req = StrategyCertRequest(
        strategy_id="S5", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=_build_fills(n=10),
        signals=_build_signals(base=base, n=6),
        ticks=_build_ticks(base=base, n=6000, step_ms=10),
        venue_profile="ECN",
        stability_score=0.99,
        # Realised half-spread ≈ 0.0455 bps; assumed values matched so
        # spread / slippage scores land near 1.0.
        assumed_cost_bps=0.0455, assumed_slippage_bps=0.0455,
        tolerance_bps=1.0,
        adv_per_minute=1000.0,
        mutation_family="trend.ema_cross.v2",
        parent_strategy_id="EM-parent",
    )
    report = await certify_strategy(db, req)
    assert report.early_fail_reason is None
    rec = report.record
    assert rec.certification_verdict in ("PASS", "WARN")
    assert rec.integrity_score == pytest.approx(0.98)
    assert rec.stability_score == pytest.approx(0.99)
    # All sub-scores clamped into [0, 1].
    for v in (rec.spread_score, rec.slippage_score, rec.execution_score,
              rec.composite_score):
        assert 0.0 <= v <= 1.0
    assert rec.data_cert_ref is not None
    assert rec.mutation_family == "trend.ema_cross.v2"


@pytest.mark.asyncio
async def test_orchestrator_records_low_composite_reason_on_fail(db) -> None:
    await _seed_data_cert(db)
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    # stability=0 forces composite to collapse → FAIL.
    req = StrategyCertRequest(
        strategy_id="S6", pair="EURUSD", timeframe="M5", style="trend",
        data_cert_window=None,
        fills=_build_fills(n=3),
        signals=_build_signals(base=base, n=3),
        ticks=_build_ticks(base=base, n=2000, step_ms=10),
        venue_profile="ECN", stability_score=0.0,
        adv_per_minute=1000.0,
    )
    report = await certify_strategy(db, req)
    assert report.record.certification_verdict == "FAIL"
    assert report.record.reason == "LOW_COMPOSITE"
    assert report.record.composite_score == 0.0

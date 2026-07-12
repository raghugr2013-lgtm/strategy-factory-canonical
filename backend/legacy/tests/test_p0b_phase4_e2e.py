"""P0B Phase 4 — End-to-End validation of the full BI5 pipeline.

Drives the canonical lifecycle path:

    BI5 Ingestion
        ↓
    BI5 Data Certification        (Phase-2 data-cert write)
        ↓
    Strategy Certification        (Phase-3 orchestrator)
        ↓
    Derived Flag                  (is_bi5_certified read)
        ↓
    Deployable Check              (= derived flag PASS within freshness)

Both PASS and FAIL paths are exercised end-to-end through the actual
FastAPI router (mounted in the production server) using TestClient
and a mongomock-backed Mongo handle.

The ingestion stub is deterministic — we don't hit Dukascopy. The
goal is to prove the seams between stages, not to exercise real BI5
network IO (covered by P0A regression tests already in the suite).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from api.bi5_certification import router as bi5_cert_router
from auth_utils import require_admin
from engines.persistence_adapters.bi5_certification_store import BI5_CERT_COLL
from engines.persistence_adapters.bi5_data_certification_store import (
    BI5_DATA_CERT_COLL,
    upsert_data_certification,
)
from engines.persistence_adapters.market_spread_store import (
    MARKET_SPREAD_COLL,
    upsert_spread_bars,
)
from engines.spread_analyzer import SpreadBar
from engines.tick_validator import BI5ScoreReport


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_app(mock_db) -> FastAPI:
    app = FastAPI()
    app.include_router(bi5_cert_router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: {
        "id": "e2e-admin", "role": "admin", "email": "admin@e2e.local",
    }
    return app


@pytest.fixture
def mock_db(monkeypatch):
    client = AsyncMongoMockClient()
    db = client["p0b_phase4_e2e"]
    monkeypatch.setattr("api.bi5_certification.get_db", lambda: db)
    return db


# ── E2E helpers (the "stages") ──────────────────────────────────────

def _stage1_ingest(db) -> Dict[str, Any]:
    """Simulate a successful BI5 ingestion for EURUSD over an hour.

    A real ingest would write 1m bars to ``market_data`` and per-minute
    spread bars to ``market_spread``. For the E2E we focus on the
    seam between ingest and data-cert, so we write a representative
    `market_spread` row here directly.
    """
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    bar = SpreadBar(
        symbol="EURUSD", ts=base,
        spread_open=0.00010, spread_high=0.00012, spread_low=0.00008,
        spread_close=0.00010, spread_mean=0.00010, tick_count=400,
    )
    return _run(upsert_spread_bars(db, [bar]))


def _stage2_data_cert(db, *, verdict: str = "PASS",
                      integrity: float = 0.98) -> Dict[str, Any]:
    """Write a data-feed cert for the EURUSD 24h window."""
    base = datetime(2026, 2, 3, 0, 0, tzinfo=timezone.utc)
    rpt = BI5ScoreReport(
        symbol="EURUSD",
        window_start=base, window_end=base + timedelta(hours=23),
        hours_expected=24, hours_present=24, hours_missing=0,
        hours_expected_empty=0, hours_decode_fail=0,
        ticks_total=540_000,
        non_monotonic_ticks=0, price_outlier_ticks=2, zero_vol_ticks=0,
        sparse_hours=0, low_density_hours=0, max_silent_gap_s=12.0,
        subscores={"cov": 1.0, "integrity": integrity, "price": 1.0,
                   "density": 0.95, "continuity": 0.96},
        bi5_score=integrity * 0.95, verdict=verdict,
    )
    return _run(upsert_data_certification(db, rpt))


def _stage3_certify_strategy(
    client: TestClient, *,
    strategy_id: str, stability: float = 0.99,
) -> Dict[str, Any]:
    """POST /api/admin/bi5/certify-strategy via the real FastAPI seam."""
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = [
        {"ts_utc": (base + timedelta(milliseconds=10 * i)).isoformat(),
         "bid": 1.10000, "ask": 1.10001}
        for i in range(2000)
    ]
    fills = [{"side": 1, "bid": 1.10000, "ask": 1.10001,
              "mid_before": 1.100005, "mid_after": 1.100005,
              "fill_spread": 0.00001, "mid": 1.100005,
              "order_size": 0.0, "adv_per_minute": 1000.0}] * 6
    signals = [{"t_signal": (base + timedelta(milliseconds=100 + 200 * i)).isoformat(),
                "side": 1 if i % 2 == 0 else -1, "order_size": 0.0}
               for i in range(5)]
    resp = client.post("/api/admin/bi5/certify-strategy", json={
        "strategy_id": strategy_id, "pair": "EURUSD",
        "timeframe": "M5", "style": "trend",
        "venue_profile": "ECN",
        "stability_score": stability,
        "assumed_cost_bps": 0.0455, "assumed_slippage_bps": 0.0455,
        "tolerance_bps": 1.0, "adv_per_minute": 1000.0,
        "mutation_family": "trend.ema_cross.v2",
        "parent_strategy_id": "EM-parent",
        "fills": fills, "signals": signals, "ticks": ticks,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stage4_derived_flag(
    client: TestClient, *, strategy_id: str,
    freshness_days: int = None,
) -> Dict[str, Any]:
    path = f"/api/admin/bi5/certified/{strategy_id}"
    if freshness_days is not None:
        path += f"?freshness_days={freshness_days}"
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ─── E2E: PASS path ─────────────────────────────────────────────────

def test_e2e_pass_path_full_lifecycle(mock_db) -> None:
    """The happy path: ingest → data-cert PASS → certify-strategy → flag = certified."""
    client = TestClient(_build_app(mock_db))

    # Stage 1: ingest.
    ingest_res = _stage1_ingest(mock_db)
    assert ingest_res["upserted"] == 1

    # Stage 2: data-cert.
    data_cert_res = _stage2_data_cert(mock_db, verdict="PASS")
    assert data_cert_res["upserted"] == 1

    # Stage 3: strategy cert via the real API seam.
    body = _stage3_certify_strategy(client, strategy_id="E2E-PASS",
                                    stability=0.99)
    assert body["early_fail_reason"] is None
    assert body["verdict"] in ("PASS", "WARN")
    # The audit doc carries data_cert_ref → traceable provenance.
    assert body["record"]["data_cert_ref"]["symbol"] == "EURUSD"

    # Stage 4: derived flag is honoured (only if Stage 3 was PASS;
    # WARN doesn't certify).
    flag = _stage4_derived_flag(client, strategy_id="E2E-PASS")
    if body["verdict"] == "PASS":
        assert flag["certified"] is True
        # Stage 5: deployable check = the derived flag itself.
        assert flag["freshness_days"] == 30
        assert "expires_at" in flag
    else:
        # WARN is acceptable (sub-scores landed between warn & pass
        # thresholds). Even then, the flag must NOT be true because
        # only PASS certifies.
        assert flag["certified"] is False


# ─── E2E: FAIL path — data-cert missing ─────────────────────────────

def test_e2e_fail_path_data_cert_missing(mock_db) -> None:
    """No data-cert exists → orchestrator short-circuits with
    DATA_CERT_MISSING; derived flag = NOT certified."""
    client = TestClient(_build_app(mock_db))

    # Skip Stage 2 — no data-cert.
    body = _stage3_certify_strategy(client, strategy_id="E2E-FAIL-NODC")
    assert body["verdict"] == "FAIL"
    assert body["early_fail_reason"] == "DATA_CERT_MISSING"
    assert body["record"]["reason"] == "DATA_CERT_MISSING"

    flag = _stage4_derived_flag(client, strategy_id="E2E-FAIL-NODC")
    assert flag["certified"] is False


# ─── E2E: FAIL path — data-cert NOT_PASS ────────────────────────────

def test_e2e_fail_path_data_cert_not_pass(mock_db) -> None:
    """Data-cert exists but verdict=FAIL → strategy cert short-circuits."""
    client = TestClient(_build_app(mock_db))

    _stage2_data_cert(mock_db, verdict="FAIL", integrity=0.0)

    body = _stage3_certify_strategy(client, strategy_id="E2E-FAIL-DCFAIL")
    assert body["verdict"] == "FAIL"
    assert body["early_fail_reason"] == "DATA_CERT_NOT_PASS"

    flag = _stage4_derived_flag(client, strategy_id="E2E-FAIL-DCFAIL")
    assert flag["certified"] is False


# ─── E2E: FAIL path — stability=0 collapses composite ───────────────

def test_e2e_fail_path_low_composite(mock_db) -> None:
    """Data-cert PASS, all Phase-1 inputs provided, but stability=0
    collapses the composite → verdict=FAIL with reason=LOW_COMPOSITE."""
    client = TestClient(_build_app(mock_db))

    _stage2_data_cert(mock_db, verdict="PASS")
    body = _stage3_certify_strategy(client, strategy_id="E2E-FAIL-LOW",
                                    stability=0.0)
    assert body["verdict"] == "FAIL"
    assert body["record"]["reason"] == "LOW_COMPOSITE"
    assert body["record"]["composite_score"] == 0.0

    flag = _stage4_derived_flag(client, strategy_id="E2E-FAIL-LOW")
    assert flag["certified"] is False


# ─── E2E: separator — ingest writes don't pollute cert collection ───

def test_e2e_collections_are_independent(mock_db) -> None:
    """A passing ingest must not leak into bi5_certification."""
    _stage1_ingest(mock_db)
    _stage2_data_cert(mock_db, verdict="PASS")

    n_spread = _run(mock_db[MARKET_SPREAD_COLL].count_documents({}))
    n_data   = _run(mock_db[BI5_DATA_CERT_COLL].count_documents({}))
    n_strat  = _run(mock_db[BI5_CERT_COLL].count_documents({}))
    assert n_spread == 1
    assert n_data == 1
    assert n_strat == 0    # nothing is written until certify-strategy runs

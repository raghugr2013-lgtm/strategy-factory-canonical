"""P0B Phase 3 — Tests for api/bi5_certification.py (FastAPI TestClient).

Auth is bypassed via ``app.dependency_overrides[require_admin]``.
Mongo is mocked via mongomock_motor; the seam reads it through
``engines.db.get_db`` which we monkey-patch onto the mock client.
"""
from __future__ import annotations

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
)


def _build_test_app(mock_db) -> FastAPI:
    app = FastAPI()
    app.include_router(bi5_cert_router, prefix="/api")
    app.dependency_overrides[require_admin] = lambda: {
        "id": "test-admin", "role": "admin", "email": "admin@test.local",
    }
    return app


@pytest.fixture
def patched_db(monkeypatch):
    client = AsyncMongoMockClient()
    db = client["test_p0b_phase3_api"]
    # The seam reads the db handle via engines.db.get_db at request time;
    # patch the symbol *as imported by the seam* (api.bi5_certification).
    monkeypatch.setattr("api.bi5_certification.get_db", lambda: db)
    return db


def _run(coro):
    """Run an async coroutine on a fresh event loop.

    Using ``asyncio.get_event_loop()`` is brittle when tests interleave
    with other ``pytest-asyncio`` cases — the loop can be closed or
    bound to a different thread by the time these sync helpers run.
    A fresh loop per call keeps this fixture suite-order-independent.
    """
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _seed_data_cert(db, *, symbol: str = "EURUSD",
                    verdict: str = "PASS", integrity: float = 0.98):
    base = datetime(2026, 2, 3, 0, 0, tzinfo=timezone.utc)
    return _run(db[BI5_DATA_CERT_COLL].insert_one({
        "symbol": symbol,
        "window_start_utc": base,
        "window_end_utc": base + timedelta(hours=23),
        "subscores": {"cov": 1.0, "integrity": integrity, "price": 1.0,
                      "density": 0.9, "continuity": 0.95},
        "verdict": verdict,
        "bi5_score": 0.95 if verdict == "PASS" else 0.4,
        "evaluator_version": "tick_validator@P0B-v1",
        "certified_at_dt": base + timedelta(hours=23),
    }))


def _seed_cert(db, **overrides) -> Dict[str, Any]:
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    doc = {
        "strategy_id":             overrides.get("strategy_id", "EM-A"),
        "pair":                    overrides.get("pair", "EURUSD"),
        "timeframe":               overrides.get("timeframe", "M5"),
        "style":                   overrides.get("style", "trend"),
        "certification_timestamp": overrides.get("ts", base),
        "certification_verdict":   overrides.get("verdict", "PASS"),
        "certification_version":   "bi5_cert@P0B-v1",
        "integrity_score": 0.98, "spread_score": 0.95, "slippage_score": 0.91,
        "execution_score": 0.93, "stability_score": 0.88,
        "composite_score":         overrides.get("composite", 0.93),
        "weights_used": {"integrity": 0.30, "spread": 0.20, "slippage": 0.20,
                         "execution": 0.15, "stability": 0.15},
        "thresholds_used": {"pass": 0.90, "warn": 0.70},
        "mutation_family":         overrides.get("family", "trend.v2"),
    }
    _run(db[BI5_CERT_COLL].insert_one(doc))
    return doc


# ── POST /admin/bi5/certify-strategy ─────────────────────────────────

def test_certify_strategy_endpoint_no_data_cert_returns_fail(patched_db):
    client = TestClient(_build_test_app(patched_db))
    resp = client.post("/api/admin/bi5/certify-strategy", json={
        "strategy_id": "S-X", "pair": "EURUSD",
        "timeframe": "M5", "style": "trend",
        "venue_profile": "ECN", "stability_score": 0.8,
        "fills": [{"side": 1, "bid": 1.1, "ask": 1.1001,
                   "mid_before": 1.10005, "mid_after": 1.10005,
                   "fill_spread": 0.00005, "mid": 1.10005}],
        "signals": [{"t_signal": "2026-02-03T09:00:00Z", "side": 1}],
        "ticks": [],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "FAIL"
    assert body["early_fail_reason"] == "DATA_CERT_MISSING"
    assert body["record"]["reason"] == "DATA_CERT_MISSING"


def test_certify_strategy_endpoint_happy_path(patched_db):
    _seed_data_cert(patched_db)
    client = TestClient(_build_test_app(patched_db))
    # Build a tick stream + fills + signals consistent with the
    # orchestrator's happy-path test.
    base = datetime(2026, 2, 3, 9, 0, tzinfo=timezone.utc)
    ticks = [
        {"ts_utc": (base + timedelta(milliseconds=10 * i)).isoformat(),
         "bid": 1.10000, "ask": 1.10001}
        for i in range(2000)
    ]
    fills = [{"side": 1, "bid": 1.10000, "ask": 1.10001,
              "mid_before": 1.100005, "mid_after": 1.100005,
              "fill_spread": 0.00001, "mid": 1.100005}] * 5
    signals = [{"t_signal": (base + timedelta(milliseconds=100 + 200 * i)).isoformat(),
                "side": 1 if i % 2 == 0 else -1}
               for i in range(4)]

    resp = client.post("/api/admin/bi5/certify-strategy", json={
        "strategy_id": "S-Happy", "pair": "EURUSD",
        "timeframe": "M5", "style": "trend",
        "venue_profile": "ECN", "stability_score": 0.99,
        "assumed_cost_bps": 0.0455, "assumed_slippage_bps": 0.0455,
        "tolerance_bps": 1.0,
        "adv_per_minute": 1000.0,
        "mutation_family": "trend.ema_cross.v2",
        "fills": fills, "signals": signals, "ticks": ticks,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verdict"] in ("PASS", "WARN")
    assert body["early_fail_reason"] is None
    assert body["record"]["mutation_family"] == "trend.ema_cross.v2"


# ── GET /admin/bi5/certifications ────────────────────────────────────

def test_list_certifications_filters_by_pair(patched_db):
    _seed_cert(patched_db, strategy_id="A", pair="EURUSD")
    _seed_cert(patched_db, strategy_id="B", pair="GBPUSD",
               ts=datetime(2026, 2, 3, 13, 0, tzinfo=timezone.utc))
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications?pair=EURUSD")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["strategy_id"] == "A"


def test_list_certifications_filters_by_verdict(patched_db):
    _seed_cert(patched_db, strategy_id="A", verdict="PASS")
    _seed_cert(patched_db, strategy_id="B", verdict="FAIL",
               composite=0.2,
               ts=datetime(2026, 2, 3, 13, 0, tzinfo=timezone.utc))
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications?verdict=FAIL")
    assert resp.status_code == 200
    body = resp.json()
    assert [r["strategy_id"] for r in body["items"]] == ["B"]


# ── GET /admin/bi5/certifications/{strategy_id}{,/latest} ────────────

def test_get_certifications_for_strategy(patched_db):
    _seed_cert(patched_db, strategy_id="X",
               ts=datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc),
               composite=0.80)
    _seed_cert(patched_db, strategy_id="X",
               ts=datetime(2026, 2, 5, 12, 0, tzinfo=timezone.utc),
               composite=0.95)
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications/X")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # newest first
    assert body["items"][0]["composite_score"] == pytest.approx(0.95)


def test_get_latest_certification_for_strategy(patched_db):
    _seed_cert(patched_db, strategy_id="X",
               ts=datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc),
               composite=0.80)
    _seed_cert(patched_db, strategy_id="X",
               ts=datetime(2026, 2, 5, 12, 0, tzinfo=timezone.utc),
               composite=0.95)
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications/X/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["composite_score"] == pytest.approx(0.95)


# ── GET /admin/bi5/certified/{strategy_id} (derived flag) ────────────

def test_certified_flag_reflects_freshness(patched_db):
    _seed_cert(patched_db, strategy_id="Z",
               ts=datetime.now(timezone.utc) - timedelta(days=5),
               verdict="PASS")
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certified/Z")
    assert resp.status_code == 200
    body = resp.json()
    assert body["certified"] is True
    assert body["freshness_days"] == 30
    # A tighter freshness window kicks it out.
    resp2 = client.get("/api/admin/bi5/certified/Z?freshness_days=2")
    assert resp2.status_code == 200
    assert resp2.json()["certified"] is False


def test_certified_flag_unknown_strategy(patched_db):
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certified/does-not-exist")
    assert resp.status_code == 200
    assert resp.json()["certified"] is False


# ── GET /admin/bi5/certifications/stats ──────────────────────────────

def test_stats_endpoint_group_by_style(patched_db):
    base = datetime(2026, 2, 3, 12, 0, tzinfo=timezone.utc)
    for i in range(3):
        _seed_cert(patched_db, strategy_id=f"T{i}", style="trend",
                   ts=base + timedelta(minutes=i), verdict="PASS")
    for i in range(2):
        _seed_cert(patched_db, strategy_id=f"M{i}", style="meanrev",
                   ts=base + timedelta(minutes=10 + i), verdict="FAIL",
                   composite=0.2)
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications/stats?group_by=style")
    assert resp.status_code == 200
    body = resp.json()
    rows = {r["key"]: r for r in body["rows"]}
    assert rows["trend"]["total"] == 3
    assert rows["trend"]["pass"] == 3
    assert rows["meanrev"]["total"] == 2
    assert rows["meanrev"]["fail"] == 2


def test_stats_endpoint_rejects_bad_group_by(patched_db):
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/certifications/stats?group_by=strategy_id")
    assert resp.status_code == 422   # FastAPI validation rejects unknown literal


# ── GET /admin/bi5/data-certifications ───────────────────────────────

def test_data_certifications_latest(patched_db):
    _seed_data_cert(patched_db, symbol="EURUSD", verdict="PASS")
    client = TestClient(_build_test_app(patched_db))
    resp = client.get("/api/admin/bi5/data-certifications/latest?symbol=EURUSD")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"] is not None
    assert body["item"]["symbol"] == "EURUSD"
    assert body["item"]["verdict"] == "PASS"

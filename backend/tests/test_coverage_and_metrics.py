"""Phase 2, Stage 2.θ + 2.ι — Coverage API + Prometheus exporter tests.

Uses TestClient to exercise the FastAPI routers directly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))


def _make_app_with(*, coverage=False, metrics=False, pressure=False):
    """Assemble a minimal FastAPI app with just the Phase-2 routers."""
    app = FastAPI()
    from engines.coverage_router import router as cov_router
    from engines.coe_metrics_router import router as met_router
    from engines.coe_pressure_middleware import CoePressureMiddleware
    app.include_router(cov_router)
    app.include_router(met_router)
    app.add_middleware(CoePressureMiddleware)
    return app


def _set(monkeypatch, **flags):
    for k, v in flags.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)


# ── Coverage API ─────────────────────────────────────────────────────

def test_coverage_503_when_flag_off(monkeypatch):
    _set(monkeypatch, COE_COVERAGE_REPORT_ENABLED=None)
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage")
        assert r.status_code == 503


def test_coverage_returns_locked_contract_shape(monkeypatch):
    _set(monkeypatch, COE_COVERAGE_REPORT_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage")
        assert r.status_code == 200
        d = r.json()
        for k in ("ts", "canonical_mode", "summary", "symbols", "gaps", "cache", "provider", "health"):
            assert k in d, f"missing top-level key: {k}"
        s = d["summary"]
        for k in ("symbol_count", "m1_row_count_total", "cache_bucket_count",
                  "coverage_completeness_pct", "gap_count", "cts_health_score"):
            assert k in s, f"missing summary key: {k}"
        c_ = d["cache"]
        for k in ("bucket_count", "bucket_fresh_count", "bucket_stale_count",
                  "hit_ratio_last_hour", "aggregation_ms_p50"):
            assert k in c_, f"missing cache key: {k}"
        assert d["health"]["subsystem"] == "cts"


def test_coverage_include_filter(monkeypatch):
    _set(monkeypatch, COE_COVERAGE_REPORT_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage?include=summary,health")
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d
        assert "health" in d
        assert "symbols" not in d
        assert "gaps" not in d
        assert "cache" not in d


def test_coverage_symbol_endpoint(monkeypatch):
    _set(monkeypatch, COE_COVERAGE_REPORT_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage/EURUSD")
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d and "symbols" in d


# ── Prometheus exporter ─────────────────────────────────────────────

def test_metrics_503_when_flag_off(monkeypatch):
    _set(monkeypatch, COE_METRICS_ENABLED=None)
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/coe/metrics")
        assert r.status_code == 503


def test_metrics_prometheus_text_format(monkeypatch):
    _set(monkeypatch, COE_METRICS_ENABLED="true")
    # Seed a counter + histogram
    from engines.metrics import get_metrics
    get_metrics().reset()
    get_metrics().inc("test_counter", 5, class_="backtest")
    get_metrics().observe("test_ms", 10.0)
    get_metrics().observe("test_ms", 20.0)
    get_metrics().observe("test_ms", 30.0)
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/coe/metrics")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")
        body = r.text
        assert "# TYPE test_counter counter" in body
        assert "test_counter" in body and "backtest" in body
        assert "# TYPE test_ms summary" in body
        assert 'quantile="0.5"' in body
        assert 'quantile="0.95"' in body


def test_metrics_state_endpoint(monkeypatch):
    _set(monkeypatch, COE_METRICS_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/coe/state")
        assert r.status_code == 200
        d = r.json()
        assert "metrics" in d


# ── X-COE-Pressure middleware ────────────────────────────────────────

def test_pressure_header_absent_when_flag_off(monkeypatch):
    _set(monkeypatch, X_COE_PRESSURE_HEADER_ENABLED=None,
         COE_COVERAGE_REPORT_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage")
        assert "x-coe-pressure" not in {k.lower() for k in r.headers.keys()}


def test_pressure_header_present_when_flag_on(monkeypatch):
    _set(monkeypatch, X_COE_PRESSURE_HEADER_ENABLED="true",
         COE_COVERAGE_REPORT_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/api/data/coverage")
        band = r.headers.get("x-coe-pressure")
        assert band in ("idle", "normal", "high", "critical", "unknown")


def test_pressure_header_not_on_non_api_routes(monkeypatch):
    _set(monkeypatch, X_COE_PRESSURE_HEADER_ENABLED="true")
    with TestClient(_make_app_with()) as c:
        r = c.get("/nonexistent")
        # 404 but no X-COE-Pressure since path is /nonexistent (not /api/*)
        assert "x-coe-pressure" not in {k.lower() for k in r.headers.keys()}

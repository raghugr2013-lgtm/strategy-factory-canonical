"""Phase 22.1 — regression for the auto-maintenance → data_coverage fix.

Validates:
  * POST /api/auto-maintenance/run-now now upserts data_coverage for every
    (symbol, bid_1m, tf) + (symbol, bi5, 1m) tuple.
  * Every symbol present in market_data ends up in data_coverage (no gaps).
  * WARNING log lines are emitted (checked in backend.err.log).
  * /api/data/maintenance/coverage returns the enriched rows.
  * Regression: /api/dashboard/datasets still returns 7 pairs and
    market_data row counts are unchanged (additive fix).
"""
from __future__ import annotations

import os
import time
from typing import Dict, List

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
# Direct internal fallback — auth middleware bypasses localhost, spec allows it
INTERNAL_URL = "http://localhost:8001"

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"]
BID_TFS = ["1m", "5m", "15m", "30m", "1h"]


def _url(path: str, internal: bool = False) -> str:
    base = INTERNAL_URL if internal else (BASE_URL or INTERNAL_URL)
    return f"{base}{path}"


@pytest.fixture(scope="module")
def client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def market_data_before(client: requests.Session) -> Dict[str, int]:
    """Row counts per symbol BEFORE triggering run-now — used to confirm
    the fix is additive (no inserts/deletes to market_data)."""
    r = client.get(_url("/api/dashboard/datasets"), timeout=30)
    assert r.status_code == 200, f"datasets endpoint failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    rows = data.get("datasets") or data.get("pairs") or data
    if isinstance(rows, dict):
        rows = rows.get("datasets", [])
    counts: Dict[str, int] = {}
    for item in rows or []:
        sym = item.get("symbol") or item.get("pair")
        # try a few possible field names for candle count
        cnt = (
            item.get("candles")
            or item.get("candle_count")
            or item.get("rows")
            or item.get("total_candles")
            or 0
        )
        if sym:
            counts[sym] = int(cnt or 0)
    return counts


# ── 1. Regression: dashboard/datasets still works ───────────────────────
def test_dashboard_datasets_returns_pairs(market_data_before):
    assert len(market_data_before) >= 7, (
        f"expected at least 7 pairs in /api/dashboard/datasets, got {len(market_data_before)}: {market_data_before}"
    )
    # All 7 configured symbols should be present
    missing = [s for s in SYMBOLS if s not in market_data_before]
    assert not missing, f"symbols missing from datasets: {missing}"


# ── 2. Trigger run-now and verify coverage count grows ──────────────────
@pytest.fixture(scope="module")
def coverage_before(client: requests.Session) -> List[dict]:
    r = client.get(_url("/api/data/maintenance/coverage"), timeout=30)
    assert r.status_code == 200, f"coverage GET failed: {r.status_code} {r.text[:200]}"
    return r.json().get("coverage", [])


@pytest.fixture(scope="module")
def run_now_result(client: requests.Session, coverage_before):
    # Truncate backend.err.log so we can assert the WARNING lines came
    # from THIS run (the file is shared across the test session)
    log_path = "/var/log/supervisor/backend.err.log"
    marker = f"[PYTEST_MARKER_{int(time.time())}]"
    try:
        with open(log_path, "a") as f:
            f.write(f"\n{marker}\n")
    except Exception:
        pass

    r = client.post(_url("/api/auto-maintenance/run-now"), timeout=300)
    assert r.status_code == 200, f"run-now failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("success") is True
    # Should have processed 7 symbols × 2 tracks = 14 results
    assert body.get("count", 0) >= 14, f"expected >=14 results, got {body.get('count')}"
    return {"body": body, "marker": marker, "log_path": log_path}


def test_run_now_triggers_coverage_update(client, coverage_before, run_now_result):
    # Post-run coverage should have MORE or EQUAL entries vs before
    r = client.get(_url("/api/data/maintenance/coverage"), timeout=30)
    assert r.status_code == 200
    after = r.json().get("coverage", [])
    assert len(after) >= len(coverage_before), (
        f"coverage shrank: before={len(coverage_before)} after={len(after)}"
    )
    # Stash for subsequent tests
    pytest._coverage_after = after


def test_every_market_symbol_has_coverage_entry(run_now_result, market_data_before):
    after = getattr(pytest, "_coverage_after", [])
    syms_in_cov = {row.get("symbol") for row in after}
    syms_in_market = {s for s, c in market_data_before.items() if c > 0}
    missing = syms_in_market - syms_in_cov
    assert not missing, (
        f"symbols in market_data but absent from data_coverage: {missing}. "
        f"This is the exact bug the fix targets."
    )


def test_coverage_contains_expected_tuple_count(run_now_result):
    """7 symbols × 5 bid_1m timeframes + 7 × bi5 = up to 42 entries.
    The fix should register ALL of them even if some have rows=0."""
    after = getattr(pytest, "_coverage_after", [])
    bid_entries = [r for r in after if r.get("source") == "bid_1m"]
    bi5_entries = [r for r in after if r.get("source") == "bi5"]
    assert len(bid_entries) >= 7, f"expected >=7 bid_1m coverage entries, got {len(bid_entries)}"
    assert len(bi5_entries) >= 7, f"expected >=7 bi5 coverage entries, got {len(bi5_entries)}"
    # Total should be in the 35-42 sweet spot per main-agent notes
    assert len(after) >= 35, f"expected >=35 total coverage rows, got {len(after)}"


def test_btcusd_ethusd_coverage_present(run_now_result, market_data_before):
    """Main agent specifically called out BTCUSD/ETHUSD as previously
    missing. If either has market_data rows, they MUST now appear in
    data_coverage (the core symptom of the bug)."""
    after = getattr(pytest, "_coverage_after", [])
    for sym in ("BTCUSD", "ETHUSD"):
        if market_data_before.get(sym, 0) == 0:
            continue  # skip if there's no real data to register
        rows = [r for r in after if r.get("symbol") == sym]
        assert rows, f"{sym} missing from data_coverage despite market_data rows"
        # At least one non-empty row expected
        non_empty = [r for r in rows if (r.get("rows") or 0) > 0]
        assert non_empty, f"{sym} in data_coverage but every row has rows=0"


def test_coverage_row_shape(run_now_result):
    after = getattr(pytest, "_coverage_after", [])
    assert after, "coverage is empty"
    sample = after[0]
    required = {"symbol", "source", "timeframe", "rows", "completeness", "last_updated"}
    missing = required - set(sample.keys())
    assert not missing, f"coverage row missing fields: {missing}; sample={sample}"
    assert "_id" not in sample, "mongo _id leaked into coverage response"


# ── 3. Backend log trace ────────────────────────────────────────────────
def test_warning_log_lines_emitted(run_now_result):
    """Scan backend.err.log for the three WARNING lines the fix emits."""
    log_path = run_now_result["log_path"]
    marker = run_now_result["marker"]
    if not os.path.exists(log_path):
        pytest.skip(f"backend log not readable at {log_path}")
    # Read only content AFTER the marker we wrote pre-run
    try:
        with open(log_path, "r", errors="ignore") as f:
            full = f.read()
    except Exception as e:
        pytest.skip(f"could not read log: {e}")
    idx = full.rfind(marker)
    tail = full[idx:] if idx >= 0 else full[-200_000:]

    assert "[auto-maintenance] BID" in tail and "range_count=" in tail, (
        "missing BID range_count WARNING line in backend.err.log"
    )
    assert "coverage registered for" in tail, (
        "missing BID 'coverage registered for X/5 timeframes' WARNING line"
    )
    assert "BI5" in tail and "coverage registered" in tail, (
        "missing BI5 coverage registered WARNING line"
    )


# ── 4. Regression: market_data row counts unchanged ─────────────────────
def test_market_data_counts_unchanged(client, market_data_before, run_now_result):
    r = client.get(_url("/api/dashboard/datasets"), timeout=30)
    assert r.status_code == 200
    data = r.json()
    rows = data.get("datasets") or data.get("pairs") or data
    if isinstance(rows, dict):
        rows = rows.get("datasets", [])
    after_counts: Dict[str, int] = {}
    for item in rows or []:
        sym = item.get("symbol") or item.get("pair")
        cnt = (
            item.get("candles")
            or item.get("candle_count")
            or item.get("rows")
            or item.get("total_candles")
            or 0
        )
        if sym:
            after_counts[sym] = int(cnt or 0)

    for sym, before in market_data_before.items():
        after = after_counts.get(sym, 0)
        # Fix is additive — counts can only grow (if Dukascopy reachable)
        # or stay equal. Never decrease.
        assert after >= before, (
            f"{sym} row count DECREASED: {before} → {after}. The fix should be additive."
        )


# ── 5. Regression: manual full pipeline still works ─────────────────────
def test_manual_full_pipeline_still_works(client):
    r = client.post(_url("/api/data/maintenance/run"), json={"enforce": False}, timeout=300)
    assert r.status_code == 200, f"/api/data/maintenance/run failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body.get("success") is True
    assert "coverage_count" in body
    assert body.get("coverage_count", 0) > 0, "coverage_count should be > 0"

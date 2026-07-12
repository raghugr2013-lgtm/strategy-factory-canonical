"""P1 — Live HTTP tests for /api/dashboard/portfolios/{save,list,{id}}.

Covers:
  * POST save — happy path (grade=A, ≥2 pairs)
  * POST save — rejection for grade=C (grade_below_threshold)
  * POST save — rejection for <2 pairs_passed (fewer_than_2_pairs_passed)
  * POST save — rejection for empty/whitespace name (name_required)
  * GET list — sorted newest-first, no `_id` / `strategies` in items
  * GET {id} — full doc returned, no `_id`
  * GET unknown_id — `{success:false,error:'not_found'}`
  * DELETE {id} — `{success:true, deleted:1}`
  * DELETE unknown_id — `{success:false,error:'not_found'}`
"""
from __future__ import annotations

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")


ADMIN_EMAIL = "admin@local.test"
ADMIN_PASSWORD = "Admin@1234567890"

SAVE_URL = f"{BASE_URL}/api/dashboard/portfolios/save"
LIST_URL = f"{BASE_URL}/api/dashboard/portfolios/list"
ONE_URL = lambda pid: f"{BASE_URL}/api/dashboard/portfolios/{pid}"  # noqa


def _pr(grade: str = "A", pairs_passed=("EURUSD", "XAUUSD"), num_strategies: int = 3):
    """Build a portfolio_result that mirrors /dashboard/generate-portfolio."""
    return {
        "success": True,
        "pairs_requested": list(pairs_passed) + ["GBPUSD"],
        "pairs_passed": list(pairs_passed),
        "pairs_rejected": [{"pair": "GBPUSD", "reason": "pf_median_below_threshold"}],
        "per_pair": [
            {
                "pair": p, "timeframe": "H1", "passed": True, "candles": 1000,
                "elapsed_seconds": 1.0, "error": None,
                "gate": {"passed": True, "median_oos_pf": 1.3, "max_oos_dd": 8.0},
                "top_strategies": [
                    {
                        "strategy_id": f"cand_{p}_1", "pair": p, "timeframe": "H1",
                        "style": "trend-following", "strategy_text": f"EMA strat {p}",
                        "verdict": "TRADE", "score": 80.0,
                        "backtest": {
                            "profit_factor": 1.35, "max_drawdown_pct": 6.0,
                            "net_profit": 400.0, "total_return_pct": 4.0,
                            "total_trades": 30, "win_rate": 55.0,
                        },
                        "equity_curve": [10000.0, 10200.0, 10400.0],
                        "initial_balance": 10000.0,
                        "phase4": {"quality_filter_enabled": True},
                        "phase5": {"atr_stops_enabled": True},
                    },
                ],
            } for p in pairs_passed
        ],
        "portfolio": {
            "num_strategies": num_strategies,
            "combined_metrics": {"total_return_pct": 4.0, "max_drawdown_pct": 7.2, "volatility": 0.1},
            "diversification_grade": grade,
            "avg_correlation": 0.09,
            "portfolio_risk_score": 0.4,
            "asset_contributions_pct": {p: 100.0 / len(pairs_passed) for p in pairs_passed},
        },
    }


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Login admin (even though endpoints are public, to match system expectations)
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    if r.status_code == 200:
        tok = r.json().get("token")
        if tok:
            s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def cleanup_ids():
    ids: list[str] = []
    yield ids
    # best-effort teardown
    for pid in ids:
        try:
            requests.delete(ONE_URL(pid), timeout=10)
        except Exception:
            pass


# ── validation gates ────────────────────────────────────────────────

def test_save_requires_name(session, cleanup_ids):
    r = session.post(SAVE_URL, json={"name": "   ", "portfolio_result": _pr("A")}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "name_required"


def test_save_rejects_grade_c(session):
    r = session.post(SAVE_URL, json={"name": "TEST_reject_c", "portfolio_result": _pr("C")}, timeout=15)
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "validation_failed"
    assert "grade_below_threshold" in body.get("reason", "")


def test_save_rejects_single_passing_pair(session):
    r = session.post(SAVE_URL, json={
        "name": "TEST_one_pair", "portfolio_result": _pr("A", pairs_passed=("EURUSD",))
    }, timeout=15)
    body = r.json()
    assert body["success"] is False
    assert "fewer_than_2_pairs_passed" in body.get("reason", "")


# ── happy path: save → list → load → delete ─────────────────────────

def test_save_list_load_delete_roundtrip(session, cleanup_ids):
    name = f"TEST_roundtrip_{uuid.uuid4().hex[:8]}"
    echo = {
        "pairs": ["EURUSD", "XAUUSD"], "timeframe": "H1",
        "style": "trend-following", "firm": "ftmo",
        "gate_config": {"threshold": 1.10, "seeds": [7, 42, 101]},
    }
    r = session.post(SAVE_URL, json={"name": name, "portfolio_result": _pr("A"), "request_echo": echo}, timeout=20)
    assert r.status_code == 200, r.text
    save = r.json()
    assert save["success"] is True
    pid = save["portfolio_id"]
    assert isinstance(pid, str) and len(pid) == 32
    assert save["grade"] == "A"
    assert save["name"] == name
    assert save["num_strategies"] >= 2
    assert "created_at" in save
    cleanup_ids.append(pid)

    # LIST — must include this portfolio and NOT leak _id / strategies
    r = session.get(f"{LIST_URL}?limit=50", timeout=15)
    assert r.status_code == 200
    lst = r.json()
    assert lst["success"] is True
    assert lst["count"] >= 1
    found = next((i for i in lst["items"] if i["portfolio_id"] == pid), None)
    assert found is not None, "saved portfolio missing from list"
    assert "_id" not in found
    assert "strategies" not in found, "list should strip heavy strategies field"
    assert found["name"] == name
    assert found["diversification_grade"] == "A"

    # List must be sorted newest-first
    created_ats = [i.get("created_at") for i in lst["items"] if i.get("created_at")]
    assert created_ats == sorted(created_ats, reverse=True)

    # LOAD full doc
    r = session.get(ONE_URL(pid), timeout=15)
    assert r.status_code == 200
    loaded = r.json()
    assert loaded["success"] is True
    doc = loaded["portfolio"]
    assert "_id" not in doc
    assert doc["portfolio_id"] == pid
    assert doc["diversification_grade"] == "A"
    assert isinstance(doc["strategies"], list) and len(doc["strategies"]) >= 2
    assert doc["gate_config"]["threshold"] == 1.10
    assert "equity_curve" in doc["strategies"][0]
    assert "phase4" in doc["strategies"][0]
    assert "phase5" in doc["strategies"][0]
    assert "asset_contributions_pct" in doc

    # DELETE
    r = session.delete(ONE_URL(pid), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["success"] is True
    assert d["deleted"] == 1

    # LOAD after delete → not_found
    r = session.get(ONE_URL(pid), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "not_found"

    cleanup_ids.remove(pid)


def test_load_unknown_returns_not_found(session):
    r = session.get(ONE_URL("deadbeef" * 4), timeout=10)
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "not_found"


def test_delete_unknown_returns_not_found(session):
    r = session.delete(ONE_URL("deadbeef" * 4), timeout=10)
    body = r.json()
    assert body["success"] is False
    assert body["error"] == "not_found"

"""P2 Signal Quality — API integration tests against live backend."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://strategy-factory-v1.preview.emergentagent.com").rstrip("/")
EMAIL = "admin@local.test"
PASSWORD = "Admin@1234567890"


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


def _gen(headers, **extra):
    body = {"pair": "GBPUSD", "timeframe": "H1", "count": 2, **extra}
    r = requests.post(f"{BASE_URL}/api/dashboard/generate",
                      json=body, headers=headers, timeout=240)
    return r


def test_filter_off_default(headers):
    r = _gen(headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("success") is True
    strategies = data.get("top_strategies") or []
    assert len(strategies) > 0
    for s in strategies:
        p4 = s.get("phase4")
        assert p4 is not None, f"phase4 missing on strategy: {s.get('strategy_name')}"
        assert p4["quality_filter_enabled"] is False
        assert p4["quality_threshold"] == 60.0
        assert p4["is_quality_evaluated"] >= 0
        assert p4["is_quality_blocked"] == 0
        assert p4["oos_quality_blocked"] == 0
        assert "is_avg_score" in p4
        assert "oos_avg_score" in p4
        assert "is_quality_filter_pct" in p4
        assert "oos_quality_filter_pct" in p4
    plog = " ".join(data.get("pipeline_log") or [])
    assert "signal-quality filter OFF" in plog


def test_filter_on_threshold_60(headers):
    r = _gen(headers, quality_filter=True, quality_threshold=60)
    assert r.status_code == 200, r.text
    data = r.json()
    strategies = data.get("top_strategies") or []
    assert len(strategies) > 0
    s = strategies[0]
    p4 = s["phase4"]
    assert p4["quality_filter_enabled"] is True
    assert p4["quality_threshold"] == 60.0
    # filter on with threshold 60: blocks > 0 OR all evaluated equals all blocked
    assert p4["is_quality_blocked"] > 0 or p4["is_quality_evaluated"] == p4["is_quality_blocked"]
    if p4["is_quality_evaluated"] > 0:
        expected = round(100.0 * p4["is_quality_blocked"] / p4["is_quality_evaluated"], 2)
        assert abs(p4["is_quality_filter_pct"] - expected) < 0.01
    plog = " ".join(data.get("pipeline_log") or [])
    assert "signal-quality filter ON" in plog
    assert "threshold=60" in plog


def test_filter_on_threshold_zero(headers):
    r = _gen(headers, quality_filter=True, quality_threshold=0)
    assert r.status_code == 200, r.text
    data = r.json()
    strategies = data.get("top_strategies") or []
    assert len(strategies) > 0
    for s in strategies:
        p4 = s["phase4"]
        assert p4["quality_filter_enabled"] is True
        assert p4["quality_threshold"] == 0.0
        assert p4["is_quality_blocked"] == 0
        assert p4["oos_quality_blocked"] == 0

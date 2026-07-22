"""Live-API integration tests for P2 Quality-Aware Optimization.

Hits POST /api/dashboard/generate on the public preview URL and verifies
`top_strategies[0].optimized.signal_quality` is populated for both
random_search and ga optimizers when quality_filter=True, and shows
filter_enabled=false (or is absent) when filter is off.
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://sprint3-phase2.preview.emergentagent.com").rstrip("/")
LOGIN = f"{BASE_URL}/api/auth/login"
GEN = f"{BASE_URL}/api/dashboard/generate"

CREDS = {"email": "admin@local.test", "password": "Admin@1234567890"}


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(LOGIN, json=CREDS, timeout=30)
    assert r.status_code == 200, r.text
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _payload(optimizer, quality_filter, **extras):
    p = {
        "pair": "GBPUSD",
        "timeframe": "H1",
        "count": 1,
        "quality_filter": quality_filter,
        "quality_threshold": 50,
        "optimize_top": 1,
        "optimizer": optimizer,
    }
    p.update(extras)
    return p


def test_random_search_with_quality_filter_on(auth_headers):
    r = requests.post(GEN, json=_payload("random_search", True),
                      headers=auth_headers, timeout=600)
    assert r.status_code == 200, r.text
    data = r.json()
    tops = data.get("top_strategies") or []
    assert tops, "No strategies returned"
    optimized = tops[0].get("optimized") or {}
    sq = optimized.get("signal_quality")
    assert sq is not None, f"signal_quality missing, optimized keys: {list(optimized.keys())}"
    assert sq.get("filter_enabled") is True
    assert sq.get("threshold") == 50
    assert isinstance(sq.get("is_avg_score"), (int, float))
    assert isinstance(sq.get("is_filter_pct"), (int, float))
    assert sq["is_filter_pct"] > 0, f"Expected IS filter_pct > 0, got {sq['is_filter_pct']}"
    assert isinstance(sq.get("oos_avg_score"), (int, float))
    assert isinstance(sq.get("oos_filter_pct"), (int, float))


def test_ga_with_quality_filter_on(auth_headers):
    r = requests.post(GEN, json=_payload("ga", True, ga_population=8, ga_generations=2, refine_top=1),
                      headers=auth_headers, timeout=900)
    assert r.status_code == 200, r.text
    data = r.json()
    tops = data.get("top_strategies") or []
    assert tops, "No strategies returned"
    optimized = tops[0].get("optimized") or {}
    sq = optimized.get("signal_quality")
    assert sq is not None, f"signal_quality missing, optimized keys: {list(optimized.keys())}"
    assert sq.get("filter_enabled") is True


def test_default_quality_filter_off(auth_headers):
    r = requests.post(GEN, json=_payload("random_search", False),
                      headers=auth_headers, timeout=600)
    assert r.status_code == 200, r.text
    data = r.json()
    tops = data.get("top_strategies") or []
    assert tops, "No strategies returned"
    optimized = tops[0].get("optimized") or {}
    sq = optimized.get("signal_quality") or {}
    # Either absent or filter_enabled false; is_filter_pct should be 0/None
    assert sq.get("filter_enabled") in (False, None)
    pct = sq.get("is_filter_pct")
    assert pct in (None, 0, 0.0)

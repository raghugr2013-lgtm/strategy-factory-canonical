"""P1 Multi-Asset Rollout — endpoint integration tests.

Verifies POST /api/dashboard/generate-portfolio:
  * 400 guard for <2 unique pairs (raw and case-insensitive duplicates)
  * Successful 3-pair run returns expected response shape
  * per_pair[].gate fields and asset_contributions_pct sum
"""
from __future__ import annotations

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://portfolio-builder-874.preview.emergentagent.com").rstrip("/")
ENDPOINT = f"{BASE_URL}/api/dashboard/generate-portfolio"
TIMEOUT = 180


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@local.test", "password": "Admin@1234567890"},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ---------- 400 guards ----------

def test_400_when_single_pair(auth_headers):
    r = requests.post(ENDPOINT, json={"pairs": ["EURUSD"], "timeframe": "H1"},
                      headers=auth_headers, timeout=TIMEOUT)
    assert r.status_code == 400, r.text
    body = r.json()
    detail = body.get("detail", body)
    assert detail.get("error") == "need_at_least_two_pairs"


def test_400_when_case_insensitive_duplicates(auth_headers):
    r = requests.post(
        ENDPOINT,
        json={"pairs": ["EURUSD", "eurusd"], "timeframe": "H1"},
        headers=auth_headers, timeout=TIMEOUT,
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", {})
    assert detail.get("error") == "need_at_least_two_pairs"
    # Endpoint should normalise to 1 unique pair
    assert detail.get("pairs_requested") == ["EURUSD"]


# ---------- Happy path: 3-pair run ----------

@pytest.fixture(scope="module")
def three_pair_response(auth_headers):
    payload = {
        "pairs": ["EURUSD", "GBPUSD", "XAUUSD"],
        "timeframe": "H1",
        "style": "trend-following",
        "gate_enabled": True,
        "gate_seeds": [7, 42, 101],
        "gate_population": 8,
        "gate_generations": 2,
    }
    r = requests.post(ENDPOINT, json=payload, headers=auth_headers, timeout=TIMEOUT)
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:1000]}"
    return r.json()


def test_response_top_level_shape(three_pair_response):
    body = three_pair_response
    for key in ("success", "pairs_requested", "pairs_passed",
                "pairs_rejected", "per_pair", "pipeline_log"):
        assert key in body, f"missing key {key} in response: {list(body.keys())}"
    assert body["success"] is True
    assert sorted(body["pairs_requested"]) == ["EURUSD", "GBPUSD", "XAUUSD"]
    # passed + rejected + (errors) should cover all requested
    assert isinstance(body["pairs_passed"], list)
    assert isinstance(body["pairs_rejected"], list)
    assert isinstance(body["per_pair"], list)
    assert len(body["per_pair"]) == 3


def test_per_pair_gate_shape(three_pair_response):
    for entry in three_pair_response["per_pair"]:
        assert "pair" in entry
        gate = entry.get("gate")
        # entries with insufficient_data still include a gate dict
        assert gate is not None, f"missing gate for {entry.get('pair')}"
        # required fields
        assert "passed" in gate
        assert "reason" in gate or gate.get("passed") is True
        # numeric fields may be None when insufficient_data, but key exists
        assert "median_oos_pf" in gate
        assert "max_oos_dd" in gate


def test_portfolio_contributions_sum_when_present(three_pair_response):
    portfolio = three_pair_response.get("portfolio")
    if not portfolio or not portfolio.get("success"):
        pytest.skip(f"portfolio not built (only {len(three_pair_response.get('pairs_passed', []))} pairs passed)")
    contribs = portfolio.get("asset_contributions_pct") or {}
    assert contribs, "portfolio built but asset_contributions_pct is empty"
    total = sum(contribs.values())
    assert abs(total - 100.0) < 1.0, f"contribs sum={total}, contribs={contribs}"

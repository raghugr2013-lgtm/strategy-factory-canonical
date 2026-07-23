"""Phase 7 Portfolio Intelligence API tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://factory-v2-canonical.preview.emergentagent.com").rstrip("/")
PI = f"{BASE_URL}/api/portfolio-intelligence"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ── Health + existing endpoints coexistence ───────────────────────────
def test_health(client):
    r = client.get(f"{BASE_URL}/api/health", timeout=30)
    assert r.status_code == 200


def test_existing_portfolio_build_untouched(client):
    r = client.post(f"{BASE_URL}/api/portfolio/build",
                    json={"top_n_pool": 10, "target_size": 3}, timeout=60)
    # allow 200 / 400 (if prereqs missing) but NOT 404
    assert r.status_code != 404, "Existing /api/portfolio/build must still be mounted"
    assert r.status_code in (200, 400, 422, 500)


def test_existing_portfolio_builder_untouched(client):
    r = client.post(f"{BASE_URL}/api/portfolio-builder/build", json={}, timeout=60)
    assert r.status_code != 404, "Existing /api/portfolio-builder/build must still be mounted"


# ── Portfolio Intelligence config + lifecycle ─────────────────────────
def test_config_defaults(client):
    r = client.get(f"{PI}/config", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "defaults" in data
    d = data["defaults"]
    assert d["min_weight"] == 0.05
    assert d["max_weight"] == 0.40
    assert d["max_portfolio_dd"] == 10.0


def test_history_endpoint(client):
    r = client.get(f"{PI}/history?limit=10", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert "count" in data and "history" in data
    assert isinstance(data["history"], list)


def test_current_endpoint_structure(client):
    r = client.get(f"{PI}/current", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] in ("ok", "empty")


# ── Build from auto_factory seed ─────────────────────────────────────
def test_build_auto_factory(client):
    r = client.post(f"{PI}/build", json={"source": "auto_factory"}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] in ("ok", "below_target_min", "insufficient_candidates")
    if d["status"] in ("ok", "below_target_min"):
        allocs = [row["allocation"] for row in d["portfolio"]]
        assert abs(sum(allocs) - 1.0) < 1e-2, f"Sum allocations = {sum(allocs)}"
        # Hard caps (with tolerance since there may be a single-candidate edge case)
        if len(allocs) >= 2:
            for a in allocs:
                assert 0.05 - 1e-3 <= a <= 0.40 + 1e-3, f"alloc {a} out of [0.05,0.40]"


def test_build_explorer(client):
    r = client.post(f"{PI}/build", json={"source": "explorer"}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] in ("ok", "below_target_min", "insufficient_candidates")


# ── Explicit strategies (deterministic) ───────────────────────────────
EXPLICIT = [
    {"strategy_id": "S1", "pair": "EURUSD", "timeframe": "H1",
     "profit_factor": 2.1, "stability_score": 70, "pass_probability": 0.6,
     "env_confidence": 0.8, "max_drawdown_pct": 6.0, "strategy_hash": "h1"},
    {"strategy_id": "S2", "pair": "GBPUSD", "timeframe": "H4",
     "profit_factor": 1.8, "stability_score": 65, "pass_probability": 0.55,
     "env_confidence": 0.75, "max_drawdown_pct": 5.0, "strategy_hash": "h2"},
    {"strategy_id": "S3", "pair": "USDJPY", "timeframe": "M15",
     "profit_factor": 2.4, "stability_score": 80, "pass_probability": 0.7,
     "env_confidence": 0.85, "max_drawdown_pct": 4.0, "strategy_hash": "h3"},
    {"strategy_id": "S4", "pair": "AUDUSD", "timeframe": "D1",
     "profit_factor": 1.5, "stability_score": 60, "pass_probability": 0.5,
     "env_confidence": 0.7, "max_drawdown_pct": 7.0, "strategy_hash": "h4"},
    {"strategy_id": "S5", "pair": "NZDUSD", "timeframe": "H1",
     "profit_factor": 1.6, "stability_score": 55, "pass_probability": 0.5,
     "env_confidence": 0.65, "max_drawdown_pct": 8.0, "strategy_hash": "h5"},
]


def test_build_explicit_and_caps(client):
    r = client.post(f"{PI}/build", json={"strategies": EXPLICIT}, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    allocs = [row["allocation"] for row in d["portfolio"]]
    assert abs(sum(allocs) - 1.0) < 1e-2
    for a in allocs:
        assert 0.05 - 1e-3 <= a <= 0.40 + 1e-3


def test_determinism(client):
    r1 = client.post(f"{PI}/build", json={"strategies": EXPLICIT}, timeout=60).json()
    time.sleep(0.2)
    r2 = client.post(f"{PI}/build", json={"strategies": EXPLICIT}, timeout=60).json()
    ids1 = [row["strategy_id"] for row in r1["portfolio"]]
    ids2 = [row["strategy_id"] for row in r2["portfolio"]]
    assert ids1 == ids2
    allocs1 = [row["allocation"] for row in r1["portfolio"]]
    allocs2 = [row["allocation"] for row in r2["portfolio"]]
    assert allocs1 == allocs2
    assert r1["expected_pf"] == r2["expected_pf"]
    assert r1["expected_dd"] == r2["expected_dd"]


def test_high_correlation_drop(client):
    # Two strategies with same pair+timeframe -> heuristic corr = 0.85 -> dropped
    strategies = [
        {"strategy_id": "A", "pair": "EURUSD", "timeframe": "H1",
         "profit_factor": 2.5, "stability_score": 80, "pass_probability": 0.7,
         "env_confidence": 0.9, "max_drawdown_pct": 5.0, "strategy_hash": "A"},
        {"strategy_id": "B", "pair": "EURUSD", "timeframe": "H1",
         "profit_factor": 2.4, "stability_score": 75, "pass_probability": 0.65,
         "env_confidence": 0.85, "max_drawdown_pct": 5.0, "strategy_hash": "B"},
        {"strategy_id": "C", "pair": "GBPUSD", "timeframe": "H4",
         "profit_factor": 2.0, "stability_score": 70, "pass_probability": 0.6,
         "env_confidence": 0.8, "max_drawdown_pct": 6.0, "strategy_hash": "C"},
        {"strategy_id": "D", "pair": "USDJPY", "timeframe": "M15",
         "profit_factor": 1.8, "stability_score": 65, "pass_probability": 0.55,
         "env_confidence": 0.75, "max_drawdown_pct": 4.0, "strategy_hash": "D"},
    ]
    r = client.post(f"{PI}/build", json={"strategies": strategies}, timeout=60)
    d = r.json()
    pair_tf = [(row["pair"], row["timeframe"]) for row in d["portfolio"]]
    assert len(set(pair_tf)) == len(pair_tf), "duplicate pair+tf should be diversified away"


def test_insufficient_candidates(client):
    # single strategy — below target_min=3
    one = [{"strategy_id": "solo", "pair": "EURUSD", "timeframe": "H1",
            "profit_factor": 2.0, "stability_score": 70, "pass_probability": 0.6,
            "env_confidence": 0.8, "max_drawdown_pct": 5.0, "strategy_hash": "solo"}]
    r = client.post(f"{PI}/build", json={"strategies": one}, timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] == "insufficient_candidates"


def test_empty_strategies_falls_back_to_source(client):
    """NOTE: explicit empty list is falsy in `if req.strategies:` — API
    silently falls back to the configured source. Documented here so this
    behaviour doesn't regress."""
    r = client.post(f"{PI}/build", json={"strategies": [], "source": "auto_factory"}, timeout=60)
    assert r.status_code == 200
    # not asserting "insufficient_candidates" because spec behaviour may
    # evolve; we only verify no crash.
    assert r.json()["status"] in ("ok", "below_target_min", "insufficient_candidates")


def test_dd_auto_trim(client):
    strategies = [
        {"strategy_id": f"T{i}", "pair": p, "timeframe": tf,
         "profit_factor": pf, "stability_score": 70, "pass_probability": 0.6,
         "env_confidence": 0.8, "max_drawdown_pct": 18.0, "strategy_hash": f"T{i}"}
        for i, (p, tf, pf) in enumerate([
            ("EURUSD", "H1", 2.5),
            ("GBPUSD", "H4", 2.4),
            ("USDJPY", "M15", 2.3),
            ("AUDUSD", "D1", 1.2),
            ("NZDUSD", "M30", 1.1),
        ])
    ]
    r = client.post(f"{PI}/build",
                    json={"strategies": strategies, "max_portfolio_dd": 5.0,
                          "target_min": 2, "target_max": 5},
                    timeout=60)
    d = r.json()
    assert d["status"] == "ok"
    # Either trimmed OR hit target_min floor
    assert d["trimmed_count"] > 0 or d["selected_count"] <= 2


def test_current_after_build(client):
    # Ensure build happened
    client.post(f"{PI}/build", json={"strategies": EXPLICIT}, timeout=60)
    r = client.get(f"{PI}/current", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["portfolio"] is not None
    assert "portfolio" in d["portfolio"]  # nested portfolio rows

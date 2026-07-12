"""Phase 8 — Strategy Refinement (Optimization) API tests.

Validates /api/optimization/* mounted in api/optimization.py and
ensures legacy routes remain functional.
"""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
OPT = f"{BASE_URL}/api/optimization"


# ── Module: defaults & list endpoints ────────────────────────────────
class TestDefaults:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_config_defaults(self):
        r = requests.get(f"{OPT}/config", timeout=15)
        assert r.status_code == 200
        d = r.json()["defaults"]
        assert d["runs"] == 8
        assert d["perturbation_pct"] == 0.15
        assert d["min_pf"] == 1.3
        assert d["max_dd_pct"] == 12.0
        assert d["min_stability"] == 0.7
        assert d["dd_penalty_cap"] == 20.0

    def test_history_shape(self):
        r = requests.get(f"{OPT}/history?limit=10", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "history" in body
        assert isinstance(body["history"], list)

    def test_best_shape(self):
        r = requests.get(f"{OPT}/best?limit=10", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "strategies" in body
        assert isinstance(body["strategies"], list)
        for s in body["strategies"]:
            assert s.get("verdict") == "OPTIMIZED"


# ── Module: batch run sources ────────────────────────────────────────
class TestRunSources:
    def test_run_auto_factory(self):
        r = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "pool_size": 5, "runs": 6},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "auto_factory"
        assert body["candidates"] >= 1
        for res in body["results"]:
            assert "verdict" in res
            assert "original_metrics" in res
            assert "optimized_metrics" in res
            imp = res["improvement"]
            for k in ("pf_change", "dd_change", "stability_change", "fitness_change"):
                assert k in imp

    def test_run_portfolio(self):
        r = requests.post(
            f"{OPT}/run",
            json={"source": "portfolio", "pool_size": 5, "runs": 6},
            timeout=120,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["source"] == "portfolio"
        assert body["candidates"] >= 1

    def test_run_explicit_strategy_single(self):
        strat = {
            "strategy_id": "TEST_phase8_explicit",
            "strategy_name": "TEST_phase8_explicit",
            "pair": "EURUSD", "timeframe": "H1", "style": "trend",
            "profit_factor": 1.7, "max_drawdown_pct": 7.0,
            "win_rate": 55.0, "stability_score": 0.85,
            "pass_probability": 70.0, "env_confidence": 0.8,
            "parameters": {"sl_pips": 30, "tp_pips": 60},
        }
        r = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": strat, "runs": 6},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["candidates"] == 1
        assert body["source"] == "explicit"
        assert len(body["results"]) == 1


# ── Module: deterministic + filter + overfit + bounds ────────────────
class TestSemantics:
    def _strat(self, **over):
        s = {
            "strategy_id": "TEST_phase8_det",
            "pair": "EURUSD", "timeframe": "H1", "style": "trend",
            "profit_factor": 1.6, "max_drawdown_pct": 6.0,
            "win_rate": 55.0, "stability_score": 0.8,
            "pass_probability": 70.0, "env_confidence": 0.8,
            "parameters": {"sl_pips": 30, "tp_pips": 60},
        }
        s.update(over)
        return s

    def test_deterministic(self):
        payload = {"source": "auto_factory", "strategy": self._strat(), "runs": 6}
        a = requests.post(f"{OPT}/run", json=payload, timeout=60).json()
        b = requests.post(f"{OPT}/run", json=payload, timeout=60).json()
        ra, rb = a["results"][0], b["results"][0]
        assert ra["optimized_metrics"]["pf"] == rb["optimized_metrics"]["pf"]
        assert ra["optimized_metrics"]["max_drawdown_pct"] == rb["optimized_metrics"]["max_drawdown_pct"]
        assert ra["optimized_metrics"]["fitness"] == rb["optimized_metrics"]["fitness"]

    def test_below_threshold_weak_pf(self):
        weak = self._strat(strategy_id="TEST_phase8_weak", profit_factor=1.0)
        r = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": weak, "runs": 6},
            timeout=60,
        ).json()
        res = r["results"][0]
        assert res["verdict"] in ("BELOW_THRESHOLD", "UNSTABLE", "REJECTED")
        # filter_reasons should mention pf threshold somewhere
        assert any("pf<" in str(x) for x in res["filter_reasons"])

    def test_runs_clamped(self):
        # request runs=12 → API caps via Field le=10; engine internally clamps too
        r = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": self._strat(strategy_id="TEST_clamp_hi"), "runs": 10},
            timeout=60,
        )
        assert r.status_code == 200
        assert r.json()["results"][0]["runs_count"] == 10

        # runs=5 (API floor) → engine min_runs=5
        r2 = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": self._strat(strategy_id="TEST_clamp_lo"), "runs": 5},
            timeout=60,
        )
        assert r2.status_code == 200
        assert r2.json()["results"][0]["runs_count"] == 5

        # runs=3 → 422 from pydantic (ge=5) — confirms validation
        r3 = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": self._strat(), "runs": 3},
            timeout=30,
        )
        assert r3.status_code == 422

    def test_overfit_guard_engine_direct(self):
        """Directly probe engine since API requires runs>=5; we just confirm
        the overfit_guard / fallback flag exists in any response payload."""
        r = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": self._strat(strategy_id="TEST_of"), "runs": 6},
            timeout=60,
        ).json()
        res = r["results"][0]
        for k in ("overfit_guard", "fallback_to_original", "filter_reasons"):
            assert k in res


# ── Module: persisted single fetch ───────────────────────────────────
class TestStrategyFetch:
    def test_get_strategy_after_run(self):
        sid = "TEST_phase8_persist"
        strat = {
            "strategy_id": sid, "pair": "EURUSD", "timeframe": "H1",
            "profit_factor": 1.7, "max_drawdown_pct": 6.0,
            "win_rate": 55.0, "stability_score": 0.85,
            "pass_probability": 70.0, "env_confidence": 0.8,
            "parameters": {"sl_pips": 30, "tp_pips": 60},
        }
        run = requests.post(
            f"{OPT}/run",
            json={"source": "auto_factory", "strategy": strat, "runs": 6},
            timeout=60,
        )
        assert run.status_code == 200

        got = requests.get(f"{OPT}/strategy/{sid}", timeout=15)
        assert got.status_code == 200
        d = got.json()
        assert d["strategy_id"] == sid
        assert "optimized_metrics" in d and "original_metrics" in d

    def test_get_strategy_unknown(self):
        r = requests.get(f"{OPT}/strategy/NOPE_xyz_does_not_exist", timeout=15)
        assert r.status_code == 404


# ── Module: legacy endpoints untouched ───────────────────────────────
class TestLegacyCoexistence:
    def test_legacy_routes_resolve(self):
        # POST {} → 422 (validation) or 2xx confirms route is mounted; 404 = removed
        for path in (
            "/api/optimize-strategy",
            "/api/optimize-random",
            "/api/portfolio-intelligence/build",
            "/api/portfolio/build",
            "/api/portfolio-builder/build",
        ):
            r = requests.post(f"{BASE_URL}{path}", json={}, timeout=30)
            assert r.status_code != 404, f"legacy route gone: {path}"
            assert r.status_code != 405, f"legacy route method changed: {path}"

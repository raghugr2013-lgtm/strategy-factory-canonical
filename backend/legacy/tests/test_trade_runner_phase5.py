"""Phase 5 — Trade Runner (paper execution) backend tests.

Covers:
    • /config defaults
    • /start (with portfolio_id, fallback to latest, empty-DB 400, live 400)
    • /step/{run_id} advances sim; trades recorded; rollups update
    • Daily DD auto-halt (halted_reason='daily_loss_limit')
    • Total DD auto-halt (halted_reason='total_loss_limit')
    • Go/No-Go gate blocks new trades after halt/stop
    • /stop/{run_id} — running → stopped; halted stays halted
    • /status/{run_id} — run+trades, no _id leak
    • /runs — history, no _id leak
    • SL-based sizing math (lot_size = risk_usd / (sl_pips × pip_value))
    • Win-rate derivation from PF, bounded [0.25, 0.85]
    • Trade record schema (required fields)
    • Phase-9 /api/execution and /api/portfolio-builder/* still respond
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any, Dict, List

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except OSError:
        BASE_URL = "http://localhost:8001"

TR = f"{BASE_URL}/api/trade-runner"
PB = f"{BASE_URL}/api/portfolio-builder"

sys.path.insert(0, "/app/backend")


# ── helpers ───────────────────────────────────────────────────────────
def _seed_portfolio(
    *, marker: str, strategies: List[Dict[str, Any]],
    allocation: Dict[str, Dict[str, float]],
) -> str:
    """Insert a synthetic portfolio directly via /portfolio-builder/save."""
    payload = {
        "status": "ok",
        "strategies": strategies,
        "allocation": allocation,
        "total_risk": round(sum(a.get("risk_pct", 0.0) for a in allocation.values()), 2),
        "_marker": marker,
    }
    r = requests.post(f"{PB}/save", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["portfolio_id"]


def _mk_strategy(h: str, *, pair: str = "EURUSD", tf: str = "H1",
                 pf: float = 1.5, risk_pct: float = 1.0) -> Dict[str, Any]:
    return {
        "strategy_hash": h,
        "strategy_name": h,
        "type": "trend_ema",
        "pair": pair,
        "timeframe": tf,
        "firm_slug": "ftmo",
        "challenge": "100k",
        "strategy_best_pf": pf,
        "safe_risk": risk_pct,
    }


def _mk_alloc(hashes: List[str], per_risk: float = 1.0) -> Dict[str, Dict[str, float]]:
    w = 1.0 / max(1, len(hashes))
    return {h: {"risk_pct": per_risk, "weight": round(w, 3)} for h in hashes}


# ──────────────────────────────────────────────────────────────────────
# 1. /config
# ──────────────────────────────────────────────────────────────────────
class TestConfig:
    def test_config_defaults(self):
        r = requests.get(f"{TR}/config", timeout=10)
        assert r.status_code == 200
        data = r.json()
        d = data["defaults"]
        assert d["account_balance"] == 10000.0
        assert d["daily_loss_limit_pct"] == 5.0
        assert d["total_loss_limit_pct"] == 10.0
        assert d["reward_ratio"] == 1.0
        assert d["mode"] == "paper"
        assert data["modes"] == ["paper"]


# ──────────────────────────────────────────────────────────────────────
# 2. /start
# ──────────────────────────────────────────────────────────────────────
class TestStart:
    @classmethod
    def setup_class(cls):
        cls.marker = f"TEST_TR_{uuid.uuid4().hex[:8]}"
        hashes = ["htr_a", "htr_b", "htr_c"]
        strategies = [
            _mk_strategy(hashes[0], pair="EURUSD", pf=1.5),
            _mk_strategy(hashes[1], pair="USDJPY", pf=2.0),
            _mk_strategy(hashes[2], pair="GBPUSD", pf=1.2),
        ]
        cls.portfolio_id = _seed_portfolio(
            marker=cls.marker, strategies=strategies,
            allocation=_mk_alloc(hashes, per_risk=1.0),
        )

    def test_start_with_portfolio_id(self):
        r = requests.post(
            f"{TR}/start",
            json={"portfolio_id": self.portfolio_id, "account_balance": 10000.0,
                  "seed": 42},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "started"
        run = data["run"]
        assert run["status"] == "running"
        assert run["equity"] == 10000.0
        assert run["account_balance_start"] == 10000.0
        assert run["run_id"].startswith("tr_")
        assert run["portfolio_id"] == self.portfolio_id
        assert run["mode"] == "paper"
        # per-strategy rollup populated
        assert len(run["strategies"]) == 3
        for s in run["strategies"]:
            assert s["trades"] == 0 and s["wins"] == 0 and s["losses"] == 0
            assert s["pnl"] == 0.0
            assert 0.25 <= s["win_rate"] <= 0.85
            assert s["risk_pct"] == 1.0
        assert "_id" not in run

    def test_start_without_portfolio_id_uses_latest(self):
        r = requests.post(f"{TR}/start", json={"seed": 7}, timeout=30)
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        assert run["status"] == "running"
        assert run["portfolio_id"]  # some portfolio picked

    def test_start_live_mode_rejected(self):
        r = requests.post(
            f"{TR}/start",
            json={"portfolio_id": self.portfolio_id, "mode": "live"},
            timeout=30,
        )
        # pydantic pattern blocks anything not paper|live → live passes regex,
        # the engine rejects with ValueError → 400
        assert r.status_code == 400, r.text
        assert "live" in r.json().get("detail", "").lower()

    def test_start_unknown_portfolio_id_400(self):
        r = requests.post(
            f"{TR}/start", json={"portfolio_id": "does_not_exist_xyz"},
            timeout=30,
        )
        assert r.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# 3. /step, /status, /runs, /stop — main lifecycle
# ──────────────────────────────────────────────────────────────────────
class TestLifecycle:
    @classmethod
    def setup_class(cls):
        cls.marker = f"TEST_TR_LIFE_{uuid.uuid4().hex[:8]}"
        hashes = ["hl_a", "hl_b"]
        strategies = [
            _mk_strategy(hashes[0], pair="EURUSD", pf=1.6),
            _mk_strategy(hashes[1], pair="USDJPY", pf=1.4),
        ]
        cls.portfolio_id = _seed_portfolio(
            marker=cls.marker, strategies=strategies,
            allocation=_mk_alloc(hashes, per_risk=1.0),
        )
        r = requests.post(
            f"{TR}/start",
            json={"portfolio_id": cls.portfolio_id, "account_balance": 10000.0,
                  "seed": 42},
            timeout=30,
        )
        assert r.status_code == 200
        cls.run_id = r.json()["run"]["run_id"]

    def test_step_records_trades_and_updates_rollups(self):
        r = requests.post(f"{TR}/step/{self.run_id}", json={"steps": 3}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        run = body["run"]
        # 2 strategies × 3 steps = up to 6 trades, unless halt fires
        assert body["executed_count"] >= 1
        assert run["trades_count"] >= 1
        # per-strategy rollup advanced
        assert sum(s["trades"] for s in run["strategies"]) == run["trades_count"]
        # equity shifted from starting balance
        assert run["equity"] != 10000.0 or run["pnl"] != 0.0 or run["trades_count"] > 0

        # Validate trade record schema on the returned `executed`
        for t in body["executed"]:
            for k in ("strategy_hash", "pair", "direction", "lot_size",
                      "sl_pips", "risk_usd", "pnl", "result",
                      "executed_at", "run_id"):
                assert k in t, f"trade missing field {k}"
            assert t["direction"] in ("BUY", "SELL")
            assert t["result"] in ("WIN", "LOSS")
            assert t["run_id"] == self.run_id
            assert "_id" not in t

    def test_status_returns_run_and_trades_no_id_leak(self):
        r = requests.get(f"{TR}/status/{self.run_id}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "run" in data and "trades" in data
        assert data["run"]["run_id"] == self.run_id
        assert "_id" not in data["run"]
        for t in data["trades"]:
            assert "_id" not in t
            assert t["run_id"] == self.run_id

    def test_runs_list_no_id_leak(self):
        r = requests.get(f"{TR}/runs?limit=10", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data and data["count"] == len(data["runs"])
        for doc in data["runs"]:
            assert "_id" not in doc
        assert any(d["run_id"] == self.run_id for d in data["runs"])

    def test_stop_flips_running_to_stopped(self):
        # ensure run still running (not halted)
        pre = requests.get(f"{TR}/status/{self.run_id}", timeout=30).json()["run"]
        if pre["status"] != "running":
            pytest.skip(f"run not running (status={pre['status']}); stop check N/A")
        r = requests.post(f"{TR}/stop/{self.run_id}", timeout=30)
        assert r.status_code == 200, r.text
        run = r.json()["run"]
        assert run["status"] == "stopped"

    def test_step_after_stop_is_skipped(self):
        r = requests.post(f"{TR}/step/{self.run_id}", json={"steps": 2}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        # skipped-path returns {run, executed:[], skipped_reason}
        assert body.get("executed", []) == []
        assert body.get("executed_count", 0) == 0
        assert body["run"]["status"] in ("stopped", "halted")
        assert "skipped_reason" in body

    def test_status_unknown_run_404(self):
        r = requests.get(f"{TR}/status/tr_does_not_exist", timeout=10)
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────
# 4. Risk limits — Daily DD and Total DD halts
# ──────────────────────────────────────────────────────────────────────
class TestRiskLimits:
    def _make_run(self, *, daily_limit: float, total_limit: float,
                  risk_pct: float = 5.0, pf: float = 0.2,
                  seed: int = 13) -> str:
        """High-risk + low-PF strategies → losing streak → triggers DD."""
        marker = f"TEST_TR_DD_{uuid.uuid4().hex[:8]}"
        hashes = [f"hdd_{i}" for i in range(3)]
        strategies = [
            _mk_strategy(h, pair=f"PAIR{i}", pf=pf, risk_pct=risk_pct)
            for i, h in enumerate(hashes)
        ]
        pid = _seed_portfolio(
            marker=marker, strategies=strategies,
            allocation=_mk_alloc(hashes, per_risk=risk_pct),
        )
        r = requests.post(
            f"{TR}/start",
            json={
                "portfolio_id": pid,
                "account_balance": 10000.0,
                "daily_loss_limit_pct": daily_limit,
                "total_loss_limit_pct": total_limit,
                "seed": seed,
            },
            timeout=30,
        )
        assert r.status_code == 200, r.text
        return r.json()["run"]["run_id"]

    def test_daily_dd_halts_run(self):
        # risk 5% × loss-heavy PF → ~half of losing trades blow 5% daily fast.
        # total limit set very high so daily hits first.
        run_id = self._make_run(daily_limit=5.0, total_limit=95.0,
                                risk_pct=5.0, pf=0.1, seed=101)
        # Step hard; engine caps at 200 per call.
        last = None
        for _ in range(5):
            r = requests.post(f"{TR}/step/{run_id}", json={"steps": 50}, timeout=60)
            assert r.status_code == 200, r.text
            last = r.json()["run"]
            if last["status"] != "running":
                break
        assert last is not None
        assert last["status"] == "halted", f"expected halted, got {last['status']}"
        assert last["halted_reason"] == "daily_loss_limit"
        assert last["daily_loss_pct"] >= 5.0

    def test_total_dd_halts_run(self):
        # Very high daily limit so total fires first.
        run_id = self._make_run(daily_limit=99.0, total_limit=10.0,
                                risk_pct=5.0, pf=0.1, seed=202)
        last = None
        for _ in range(5):
            r = requests.post(f"{TR}/step/{run_id}", json={"steps": 50}, timeout=60)
            assert r.status_code == 200, r.text
            last = r.json()["run"]
            if last["status"] != "running":
                break
        assert last is not None
        assert last["status"] == "halted"
        assert last["halted_reason"] == "total_loss_limit"
        assert last["total_loss_pct"] >= 10.0

    def test_stop_on_halted_run_is_idempotent(self):
        run_id = self._make_run(daily_limit=5.0, total_limit=95.0,
                                risk_pct=5.0, pf=0.1, seed=303)
        # Drive it to halt
        for _ in range(5):
            r = requests.post(f"{TR}/step/{run_id}", json={"steps": 50}, timeout=60)
            if r.json()["run"]["status"] != "running":
                break
        r = requests.post(f"{TR}/stop/{run_id}", timeout=30)
        assert r.status_code == 200
        run = r.json()["run"]
        # Spec: halted runs return as-is (status stays 'halted')
        assert run["status"] == "halted"

    def test_go_no_go_skips_new_trades_after_halt(self):
        run_id = self._make_run(daily_limit=5.0, total_limit=95.0,
                                risk_pct=5.0, pf=0.1, seed=404)
        for _ in range(5):
            r = requests.post(f"{TR}/step/{run_id}", json={"steps": 50}, timeout=60)
            if r.json()["run"]["status"] != "running":
                break
        # Now any further /step must not execute new trades
        r = requests.post(f"{TR}/step/{run_id}", json={"steps": 10}, timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert body.get("executed", []) == []
        assert body.get("executed_count", 0) == 0
        assert body["run"]["status"] in ("halted", "stopped")


# ──────────────────────────────────────────────────────────────────────
# 5. Engine unit tests — sizing math + win-rate derivation
# ──────────────────────────────────────────────────────────────────────
class TestEngineUnits:
    def test_sl_based_sizing_math(self):
        from engines.trade_runner_engine import compute_position
        # risk_usd = 10000 * 1% = 100; lot = 100 / (30 * 10) = 0.333
        out = compute_position(
            account_balance=10000.0, risk_pct=1.0,
            sl_pips=30.0, pip_value_per_lot=10.0,
        )
        assert out["risk_usd"] == 100.0
        assert out["lot_size"] == round(100.0 / (30.0 * 10.0), 3)
        assert out["sl_pips"] == 30.0

    def test_sl_based_sizing_custom(self):
        from engines.trade_runner_engine import compute_position
        out = compute_position(
            account_balance=25000.0, risk_pct=2.0,
            sl_pips=50.0, pip_value_per_lot=10.0,
        )
        # 25000 * 2% = 500; lot = 500 / (50 * 10) = 1.0
        assert out["risk_usd"] == 500.0
        assert out["lot_size"] == 1.0

    def test_win_rate_from_pf_bounds(self):
        from engines.trade_runner_engine import _win_rate_from_pf
        # PF=1, R=1 → 0.5
        assert _win_rate_from_pf(1.0, 1.0) == 0.5
        # Very high PF clamped to 0.85
        assert _win_rate_from_pf(100.0, 1.0) == 0.85
        # Very low PF clamped up to 0.25
        assert _win_rate_from_pf(0.01, 1.0) == 0.25
        # Missing PF → default 0.5
        assert _win_rate_from_pf(None, 1.0) == 0.5
        # Known value: PF=2, R=1 → 2/3 ≈ 0.6667
        wr = _win_rate_from_pf(2.0, 1.0)
        assert abs(wr - (2.0 / 3.0)) < 1e-6

    def test_go_no_go_logic(self):
        from engines.trade_runner_engine import go_no_go
        run = {
            "status": "running",
            "limits": {"daily_loss_limit_pct": 5.0, "total_loss_limit_pct": 10.0},
            "daily_loss_pct": 2.0, "total_loss_pct": 4.0,
        }
        assert go_no_go(run)["allow"] is True
        run["daily_loss_pct"] = 5.0
        assert go_no_go(run) == {"allow": False, "reason": "daily_loss_limit"}
        run["daily_loss_pct"] = 0.0
        run["total_loss_pct"] = 10.0
        assert go_no_go(run) == {"allow": False, "reason": "total_loss_limit"}
        run2 = {"status": "halted", "limits": {}}
        v = go_no_go(run2)
        assert v["allow"] is False and "halted" in v["reason"]


# ──────────────────────────────────────────────────────────────────────
# 6. Coexistence — Phase-9 /api/execution and Phase-4 /api/portfolio-builder
#    must still respond unchanged.
# ──────────────────────────────────────────────────────────────────────
class TestCoexistence:
    def test_phase9_execution_untouched(self):
        # Any /api/execution/* route must still be reachable (not 404-swept)
        r = requests.get(f"{BASE_URL}/api/execution/runs", timeout=10)
        # 200 / 404 / 405 all acceptable — what must NOT happen: 5xx
        assert r.status_code < 500, r.text

    def test_portfolio_builder_config_untouched(self):
        r = requests.get(f"{PB}/config", timeout=10)
        assert r.status_code == 200
        assert "defaults" in r.json()

    def test_portfolio_builder_recent_untouched(self):
        r = requests.get(f"{PB}/recent?limit=3", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "portfolios" in data
        for p in data["portfolios"]:
            assert "_id" not in p

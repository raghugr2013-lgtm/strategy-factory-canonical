"""P1 — Multi-Asset Portfolio persistence tests.

Uses an in-memory fake Mongo collection (same tactic as
`test_dashboard_datasets.py`) so tests are hermetic — no dependency on
a live MongoDB or event-loop wiring.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


# ── In-memory fake collection that mimics the Motor API we use ───────

class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction):
        rev = direction < 0
        self._docs.sort(key=lambda d: d.get(key, ""), reverse=rev)
        return self

    def limit(self, n):
        self._docs = self._docs[: int(n)]
        return self

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._i]
        self._i += 1
        return doc


class _FakeCollection:
    def __init__(self):
        self._docs: list[dict] = []

    async def insert_one(self, doc):
        # Match Mongo's behaviour of adding `_id` to the input dict.
        doc = dict(doc)
        doc["_id"] = "fake-oid-{}".format(len(self._docs))
        self._docs.append(doc)
        return type("Res", (), {"inserted_id": doc["_id"]})()

    def find(self, flt=None, projection=None):
        items = list(self._docs)
        if projection:
            out = []
            for d in items:
                copy = dict(d)
                for k, v in (projection or {}).items():
                    if v == 0 and k in copy:
                        del copy[k]
                out.append(copy)
            items = out
        return _FakeCursor(items)

    async def find_one(self, flt, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in (flt or {}).items()):
                copy = dict(d)
                if projection:
                    for k, v in projection.items():
                        if v == 0 and k in copy:
                            del copy[k]
                return copy
        return None

    async def delete_one(self, flt):
        for i, d in enumerate(self._docs):
            if all(d.get(k) == v for k, v in (flt or {}).items()):
                del self._docs[i]
                return type("Res", (), {"deleted_count": 1})()
        return type("Res", (), {"deleted_count": 0})()

    async def delete_many(self, _flt):
        n = len(self._docs)
        self._docs.clear()
        return type("Res", (), {"deleted_count": n})()

    async def count_documents(self, _flt):
        return len(self._docs)


class _FakeDB:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = _FakeCollection()
        return self._collections[name]


@pytest.fixture
def fake_db():
    db = _FakeDB()
    with patch("engines.portfolio_store.get_db", return_value=db):
        yield db


# ── sample portfolio result builder ──────────────────────────────────

def _fake_portfolio_result(*, grade: str = "A", pairs_passed=("EURUSD", "XAUUSD"),
                           num_strategies: int = 3) -> dict:
    return {
        "success": True,
        "pairs_requested": list(pairs_passed) + ["GBPUSD"],
        "pairs_passed":    list(pairs_passed),
        "pairs_rejected":  [{"pair": "GBPUSD", "reason": "pf_median_below_threshold"}],
        "per_pair": [
            {
                "pair": "EURUSD", "timeframe": "H1", "passed": True, "candles": 12569,
                "elapsed_seconds": 1.5, "error": None,
                "gate": {"passed": True, "median_oos_pf": 1.42, "max_oos_dd": 6.75},
                "top_strategies": [
                    {
                        "strategy_id": "cand_1", "pair": "EURUSD", "timeframe": "H1",
                        "style": "trend-following", "strategy_text": "EMA strategy A",
                        "verdict": "TRADE", "score": 82.5,
                        "backtest": {
                            "profit_factor": 1.42, "max_drawdown_pct": 5.6,
                            "net_profit": 520.1, "total_return_pct": 5.2,
                            "total_trades": 47, "win_rate": 57.4,
                        },
                        "equity_curve": [10000.0, 10260.0, 10520.1],
                        "initial_balance": 10000.0,
                        "phase4": {"quality_filter_enabled": False},
                        "phase5": {"atr_stops_enabled": False},
                    },
                ],
            },
            {
                "pair": "XAUUSD", "timeframe": "H1", "passed": True, "candles": 5888,
                "elapsed_seconds": 0.9, "error": None,
                "gate": {"passed": True, "median_oos_pf": 1.11, "max_oos_dd": 11.12},
                "top_strategies": [
                    {
                        "strategy_id": "cand_1", "pair": "XAUUSD", "timeframe": "H1",
                        "style": "trend-following", "strategy_text": "EMA X",
                        "verdict": "RISKY", "score": 68.1,
                        "backtest": {
                            "profit_factor": 1.21, "max_drawdown_pct": 9.2,
                            "net_profit": 210.5, "total_return_pct": 2.1,
                            "total_trades": 33, "win_rate": 54.0,
                        },
                        "equity_curve": [10000.0, 10105.0, 10210.5],
                        "initial_balance": 10000.0,
                    },
                    {
                        "strategy_id": "cand_2", "pair": "XAUUSD", "timeframe": "H1",
                        "style": "trend-following", "strategy_text": "EMA Y",
                        "verdict": "TRADE", "score": 71.0,
                        "backtest": {
                            "profit_factor": 1.33, "max_drawdown_pct": 7.8,
                            "net_profit": 400.0, "total_return_pct": 4.0,
                            "total_trades": 29, "win_rate": 55.0,
                        },
                        "equity_curve": [10000.0, 10200.0, 10400.0],
                        "initial_balance": 10000.0,
                    },
                ],
            },
        ],
        "portfolio": {
            "num_strategies": num_strategies,
            "combined_metrics": {
                "total_return_pct": 3.5, "max_drawdown_pct": 9.24, "volatility": 0.11,
            },
            "diversification_grade": grade,
            "avg_correlation": 0.089,
            "portfolio_risk_score": 0.42,
            "asset_contributions_pct": {"EURUSD": 60.0, "XAUUSD": 40.0},
            "suggested_allocations": [0.5, 0.3, 0.2],
        },
    }


# ── validation gates ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_rejects_grade_below_b(fake_db):
    from engines.portfolio_store import save_portfolio
    res = await save_portfolio(
        name="low", portfolio_result=_fake_portfolio_result(grade="C"),
    )
    assert res["success"] is False
    assert res["error"] == "validation_failed"
    assert "grade_below_threshold" in res["reason"]


@pytest.mark.asyncio
async def test_save_rejects_single_passing_pair(fake_db):
    from engines.portfolio_store import save_portfolio
    res = await save_portfolio(
        name="one-asset",
        portfolio_result=_fake_portfolio_result(pairs_passed=("EURUSD",)),
    )
    assert res["success"] is False
    assert "fewer_than_2_pairs_passed" in res["reason"]


@pytest.mark.asyncio
async def test_save_requires_name(fake_db):
    from engines.portfolio_store import save_portfolio
    res = await save_portfolio(
        name="   ", portfolio_result=_fake_portfolio_result(),
    )
    assert res["success"] is False
    assert res["error"] == "name_required"


@pytest.mark.asyncio
async def test_save_rejects_empty_portfolio_block(fake_db):
    from engines.portfolio_store import save_portfolio
    res = await save_portfolio(name="x", portfolio_result={"portfolio": None})
    assert res["success"] is False
    assert "no_portfolio_block" in res["reason"]


# ── happy path ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_list_load_delete_roundtrip(fake_db):
    from engines.portfolio_store import (
        save_portfolio, list_portfolios, load_portfolio, delete_portfolio,
    )
    save = await save_portfolio(
        name="Gold + FX balanced",
        portfolio_result=_fake_portfolio_result(grade="A"),
        request_echo={
            "pairs": ["EURUSD", "XAUUSD"], "timeframe": "H1",
            "style": "trend-following", "firm": "ftmo",
            "gate_config": {"threshold": 1.10, "seeds": [7, 42, 101]},
        },
    )
    assert save["success"] is True
    pid = save["portfolio_id"]
    assert isinstance(pid, str) and len(pid) == 32
    assert save["grade"] == "A"

    listing = await list_portfolios()
    assert listing["success"] is True
    assert listing["count"] == 1
    item = listing["items"][0]
    assert item["portfolio_id"] == pid
    assert item["name"] == "Gold + FX balanced"
    assert "strategies" not in item
    assert "_id" not in item

    loaded = await load_portfolio(pid)
    assert loaded["success"] is True
    doc = loaded["portfolio"]
    assert doc["portfolio_id"] == pid
    assert "_id" not in doc
    assert doc["diversification_grade"] == "A"
    assert len(doc["strategies"]) == 3
    assert doc["strategies"][0]["strategy_text"] == "EMA strategy A"
    assert doc["strategies"][0]["equity_curve"] == [10000.0, 10260.0, 10520.1]
    assert doc["combined_metrics"]["max_drawdown_pct"] == 9.24
    assert doc["asset_contributions_pct"] == {"EURUSD": 60.0, "XAUUSD": 40.0}
    assert doc["gate_config"]["threshold"] == 1.10
    assert doc["source"] == "multi_asset_rollout"

    d = await delete_portfolio(pid)
    assert d["success"] is True
    assert d["deleted"] == 1

    missing = await load_portfolio(pid)
    assert missing["success"] is False
    assert missing["error"] == "not_found"

    listing_after = await list_portfolios()
    assert listing_after["count"] == 0


@pytest.mark.asyncio
async def test_multiple_saves_have_unique_ids(fake_db):
    from engines.portfolio_store import save_portfolio, count_portfolios
    s1 = await save_portfolio(name="p1", portfolio_result=_fake_portfolio_result())
    s2 = await save_portfolio(name="p2", portfolio_result=_fake_portfolio_result(grade="B"))
    assert s1["success"] and s2["success"]
    assert s1["portfolio_id"] != s2["portfolio_id"]
    assert await count_portfolios() == 2


@pytest.mark.asyncio
async def test_list_sorts_newest_first(fake_db):
    import asyncio
    from engines.portfolio_store import save_portfolio, list_portfolios
    for n in ("alpha", "beta", "gamma"):
        await save_portfolio(name=n, portfolio_result=_fake_portfolio_result(grade="A"))
        await asyncio.sleep(0.01)
    listing = await list_portfolios()
    names = [i["name"] for i in listing["items"]]
    assert names == ["gamma", "beta", "alpha"]


@pytest.mark.asyncio
async def test_delete_unknown_id(fake_db):
    from engines.portfolio_store import delete_portfolio
    res = await delete_portfolio("nonexistent123")
    assert res["success"] is False
    assert res["error"] == "not_found"


@pytest.mark.asyncio
async def test_load_empty_id(fake_db):
    from engines.portfolio_store import load_portfolio
    assert (await load_portfolio(""))["error"] == "portfolio_id_required"


@pytest.mark.asyncio
async def test_persisted_strategy_captures_phase_telemetry(fake_db):
    from engines.portfolio_store import save_portfolio, load_portfolio
    s = await save_portfolio(name="phase_check", portfolio_result=_fake_portfolio_result(grade="A"))
    loaded = await load_portfolio(s["portfolio_id"])
    strats = loaded["portfolio"]["strategies"]
    assert strats[0]["phase4"] == {"quality_filter_enabled": False}
    assert strats[0]["phase5"] == {"atr_stops_enabled": False}

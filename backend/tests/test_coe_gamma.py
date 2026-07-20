"""Phase 2 Stage 4 P4B — COE γ tests.

Covers every P4B component:
  * Retry executor (pass-through, retries, exhaustion)
  * Dead-letter repository (record, requeue, discard, depth, flag-off)
  * Work recovery sweep
  * Provider-aware admission (open/closed/half-open, flag-off pass-through)
  * Age boost (below/above threshold, cap, flag-off)
  * Elastic bands (below high water, active loan, donor busy, flag-off)
  * Budget hard-cap (headroom, cap reached, flag-off)
  * Operator controls (circuit reset, queue pause/resume, audit)
  * Router — 503 when flag off; 200 when on
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.coe_gamma import (  # noqa: E402
    AgeBoost, BudgetHardCap, ElasticBandRedistributor,
    OperatorControls, ProviderAwareAdmission, RetryExecutor,
    compute_age_boost,
)
from engines.coe_gamma import dead_letter as dl  # noqa: E402
from engines.coe_gamma import operator_controls as opctl  # noqa: E402
from engines.coe_gamma import work_recovery as wr  # noqa: E402
from engines.coe_gamma.dead_letter import DeadLetterRepository  # noqa: E402
from engines.coe_gamma.retry_executor import (  # noqa: E402
    CLASS_RETRY_POLICIES, retry_policy_for_class,
)


# ── Fake Mongo ───────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._skip = 0
        self._limit = None
    def skip(self, n):
        self._skip = n
        return self
    def limit(self, n):
        self._limit = n
        return self
    def __aiter__(self):
        docs = self._rows[self._skip:]
        if self._limit is not None:
            docs = docs[:self._limit]
        self._it = iter(docs)
        return self
    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self, name):
        self.name = name
        self._docs: List[Dict[str, Any]] = []
        self._i = 0

    async def insert_one(self, doc):
        self._i += 1
        stored = {**doc, "_id": f"{self.name}-{self._i}"}
        self._docs.append(stored)
        class _R:
            def __init__(self, _id): self.inserted_id = _id
        return _R(stored["_id"])

    async def update_one(self, q, update, upsert=False):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {}))
                class _R: matched_count = 1
                return _R()
        class _R: matched_count = 0
        return _R()

    async def find_one(self, q):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    def find(self, q):
        def _match(d):
            for k, v in q.items():
                if isinstance(v, dict):
                    # Support $lt / $gte / $ne for the tests that need it
                    for op, val in v.items():
                        got = d.get(k)
                        if op == "$lt"  and not (got is not None and got < val):  return False
                        if op == "$gte" and not (got is not None and got >= val): return False
                        if op == "$ne"  and got == val:                            return False
                elif d.get(k) != v:
                    return False
            return True
        matches = [d for d in self._docs if _match(d)]
        return _Cursor(matches)

    async def count_documents(self, q):
        return sum(
            1 for d in self._docs
            if all(d.get(k) == v for k, v in q.items())
        )


class _FakeDB:
    def __init__(self):
        self._c: Dict[str, _Coll] = {}
    def __getitem__(self, name):
        if name not in self._c:
            self._c[name] = _Coll(name)
        return self._c[name]


# ── Retry executor ───────────────────────────────────────────────────

class TestRetryExecutor:
    @pytest.mark.asyncio
    async def test_pass_through_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("COE_RETRY_ENABLED", raising=False)
        calls = {"n": 0}
        async def _fn():
            calls["n"] += 1
            return "ok"
        r = RetryExecutor()
        out = await r.execute(_fn, workload_class="agent")
        assert out.ok is True and out.attempts == 1 and calls["n"] == 1

    @pytest.mark.asyncio
    async def test_retries_and_succeeds(self, monkeypatch):
        monkeypatch.setenv("COE_RETRY_ENABLED", "true")
        calls = {"n": 0}
        async def _fn():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("boom")
            return "ok"
        async def _sleep(_s): return None
        r = RetryExecutor(sleep=_sleep)
        out = await r.execute(_fn, workload_class="knowledge")
        assert out.ok is True
        assert out.attempts == 3
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_retries_exhaust(self, monkeypatch):
        monkeypatch.setenv("COE_RETRY_ENABLED", "true")
        async def _fn():
            raise RuntimeError("persistent")
        async def _sleep(_s): return None
        r = RetryExecutor(sleep=_sleep)
        out = await r.execute(_fn, workload_class="knowledge")
        assert out.ok is False
        assert out.attempts == CLASS_RETRY_POLICIES["knowledge"].max_attempts
        assert "persistent" in out.error

    @pytest.mark.asyncio
    async def test_non_retryable_stops_early(self, monkeypatch):
        monkeypatch.setenv("COE_RETRY_ENABLED", "true")
        async def _fn():
            raise ValueError("nope")
        async def _sleep(_s): return None
        r = RetryExecutor(sleep=_sleep)
        out = await r.execute(_fn, workload_class="knowledge",
                              is_retryable=lambda exc: False)
        assert out.ok is False and out.attempts == 1

    def test_policy_lookup_falls_back(self):
        p = retry_policy_for_class("something-unknown")
        assert p.max_attempts >= 1


# ── Dead-letter ──────────────────────────────────────────────────────

class TestDeadLetter:
    @pytest.mark.asyncio
    async def test_flag_off_returns_marker(self, monkeypatch):
        monkeypatch.delenv("COE_DEAD_LETTER_ENABLED", raising=False)
        repo = DeadLetterRepository(db_getter=lambda: _FakeDB())
        out = await repo.record(
            workload_class="agent", task_kind="llm", task_id="t1",
            error_class="X", error_message="e", attempts=3,
        )
        assert out["status"] == "flag_off"
        # list_rows / depth also short-circuit
        assert await repo.list_rows() == []
        assert await repo.depth() == 0

    @pytest.mark.asyncio
    async def test_record_and_list(self, monkeypatch):
        monkeypatch.setenv("COE_DEAD_LETTER_ENABLED", "true")
        db = _FakeDB()
        repo = DeadLetterRepository(db_getter=lambda: db)
        out = await repo.record(
            workload_class="agent", task_kind="llm", task_id="t1",
            error_class="TimeoutError", error_message="oops", attempts=3,
            provider="openai",
        )
        assert out["status"] == "recorded"
        rows = await repo.list_rows()
        assert len(rows) == 1
        assert rows[0]["task_id"] == "t1"
        assert rows[0]["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_requeue_marks_row(self, monkeypatch):
        monkeypatch.setenv("COE_DEAD_LETTER_ENABLED", "true")
        db = _FakeDB()
        repo = DeadLetterRepository(db_getter=lambda: db)
        r = await repo.record(workload_class="agent", task_kind="k", task_id="t",
                              error_class="E", error_message="m", attempts=3)
        rid = r["row_id"]
        rq = await repo.requeue(rid, requested_by="op")
        assert rq["status"] == "requeued"
        got = await repo.get(rid)
        assert got["requeued_at"] is not None
        assert got["requeued_by"] == "op"

    @pytest.mark.asyncio
    async def test_discard_soft_deletes(self, monkeypatch):
        monkeypatch.setenv("COE_DEAD_LETTER_ENABLED", "true")
        db = _FakeDB()
        repo = DeadLetterRepository(db_getter=lambda: db)
        r = await repo.record(workload_class="agent", task_kind="k", task_id="t",
                              error_class="E", error_message="m", attempts=3)
        d = await repo.discard(r["row_id"], requested_by="op", reason="not needed")
        assert d["status"] == "discarded"
        # By default `list_rows` excludes discarded
        assert (await repo.list_rows()) == []
        # With include_discarded=True they appear
        assert len(await repo.list_rows(include_discarded=True)) == 1

    @pytest.mark.asyncio
    async def test_depth_excludes_requeued_and_discarded(self, monkeypatch):
        monkeypatch.setenv("COE_DEAD_LETTER_ENABLED", "true")
        db = _FakeDB()
        repo = DeadLetterRepository(db_getter=lambda: db)
        a = await repo.record(workload_class="agent", task_kind="k", task_id="a",
                              error_class="E", error_message="m", attempts=3)
        b = await repo.record(workload_class="agent", task_kind="k", task_id="b",
                              error_class="E", error_message="m", attempts=3)
        c = await repo.record(workload_class="backtest", task_kind="k", task_id="c",
                              error_class="E", error_message="m", attempts=3)
        assert await repo.depth() == 3
        await repo.requeue(a["row_id"], requested_by="op")
        await repo.discard(b["row_id"], requested_by="op", reason="x")
        assert await repo.depth() == 1
        assert await repo.depth(workload_class="agent") == 0
        assert await repo.depth(workload_class="backtest") == 1


# ── Work recovery ────────────────────────────────────────────────────

class TestWorkRecovery:
    @pytest.mark.asyncio
    async def test_flag_off_returns_marker(self, monkeypatch):
        monkeypatch.delenv("COE_WORK_RECOVERY_ENABLED", raising=False)
        r = wr.WorkRecovery(db_getter=lambda: _FakeDB())
        assert (await r.sweep())["status"] == "flag_off"

    @pytest.mark.asyncio
    async def test_sweep_handles_stale_rows(self, monkeypatch):
        monkeypatch.setenv("COE_WORK_RECOVERY_ENABLED", "true")
        db = _FakeDB()
        stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
        fresh_ts = datetime.now(timezone.utc).isoformat()
        # Note: the fake coll's `find` matches only equality — the $lt
        # filter is ignored, so we simulate by only seeding stale rows.
        db["workload_events"]._docs.extend([
            {"status": "in_flight", "started_at": stale_ts, "task_id": "s1"},
            {"status": "in_flight", "started_at": stale_ts, "task_id": "s2"},
        ])
        results: Dict[str, int] = {"requeue": 0, "dead_letter": 0}
        async def _requeue(row):
            results["requeue"] += 1
            return row["task_id"] == "s1"  # requeue s1, dead-letter s2
        async def _dead(row):
            results["dead_letter"] += 1
        r = wr.WorkRecovery(db_getter=lambda: db,
                            requeue_hook=_requeue, dead_letter_hook=_dead)
        out = await r.sweep(stale_after_s=1)
        assert out["status"] == "swept"
        assert out["found"] == 2
        assert out["requeued"] == 1
        assert out["dead_lettered"] == 1


# ── Provider-aware admission ─────────────────────────────────────────

class TestProviderAdmission:
    def test_flag_off_admits(self, monkeypatch):
        monkeypatch.delenv("COE_PROVIDER_AWARE_ADMISSION", raising=False)
        pa = ProviderAwareAdmission(breaker_state_lookup=lambda p: "open")
        d = pa.decide(workload_class="agent", provider="openai")
        assert d.admit is True and d.reason == "flag_off_pass_through"

    def test_class_not_gated(self, monkeypatch):
        monkeypatch.setenv("COE_PROVIDER_AWARE_ADMISSION", "true")
        pa = ProviderAwareAdmission(breaker_state_lookup=lambda p: "open")
        d = pa.decide(workload_class="market_data", provider="openai")
        assert d.admit is True and d.reason == "class_not_gated"

    def test_open_circuit_refuses(self, monkeypatch):
        monkeypatch.setenv("COE_PROVIDER_AWARE_ADMISSION", "true")
        pa = ProviderAwareAdmission(breaker_state_lookup=lambda p: "open")
        d = pa.decide(workload_class="agent", provider="openai")
        assert d.admit is False
        assert d.reason == "provider_unavailable"

    def test_half_open_admits_probe(self, monkeypatch):
        monkeypatch.setenv("COE_PROVIDER_AWARE_ADMISSION", "true")
        pa = ProviderAwareAdmission(breaker_state_lookup=lambda p: "half_open")
        d = pa.decide(workload_class="agent", provider="openai")
        assert d.admit is True and d.probe is True

    def test_closed_admits(self, monkeypatch):
        monkeypatch.setenv("COE_PROVIDER_AWARE_ADMISSION", "true")
        pa = ProviderAwareAdmission(breaker_state_lookup=lambda p: "closed")
        d = pa.decide(workload_class="agent", provider="anthropic")
        assert d.admit is True and d.reason == "ok"


# ── Age boost ────────────────────────────────────────────────────────

class TestAgeBoost:
    def test_flag_off_returns_zero(self, monkeypatch):
        monkeypatch.delenv("COE_AGE_BOOST_ENABLED", raising=False)
        r = compute_age_boost(queued_at_iso="2020-01-01T00:00:00+00:00")
        assert r.delta == 0.0 and r.reason == "flag_off"

    def test_below_threshold(self, monkeypatch):
        monkeypatch.setenv("COE_AGE_BOOST_ENABLED", "true")
        recent = datetime.now(timezone.utc).isoformat()
        r = compute_age_boost(queued_at_iso=recent)
        assert r.delta == 0.0 and r.reason == "below_threshold"

    def test_above_threshold_delta_grows(self, monkeypatch):
        monkeypatch.setenv("COE_AGE_BOOST_ENABLED", "true")
        # Simulate a task queued 5 minutes ago
        five_min_ago = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        r = compute_age_boost(queued_at_iso=five_min_ago)
        assert r.delta > 0.0
        assert r.intervals >= 5  # crossed 60s + 4 more 30s intervals

    def test_max_cap(self, monkeypatch):
        monkeypatch.setenv("COE_AGE_BOOST_ENABLED", "true")
        ancient = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        r = compute_age_boost(queued_at_iso=ancient, max_delta=5.0)
        assert r.delta == 5.0


# ── Elastic bands ────────────────────────────────────────────────────

class TestElasticBands:
    def test_flag_off(self, monkeypatch):
        monkeypatch.delenv("COE_ELASTIC_BAND_ENABLED", raising=False)
        e = ElasticBandRedistributor(
            get_queue_depth=lambda _c: 100,
            get_reservation=lambda _c: 10,
        )
        assert e.compute_plan().active is False

    def test_below_high_water(self, monkeypatch):
        monkeypatch.setenv("COE_ELASTIC_BAND_ENABLED", "true")
        monkeypatch.setenv("ELASTIC_HIGH_WATER", "50")
        e = ElasticBandRedistributor(
            get_queue_depth=lambda c: {"backtest": 10, "mutation": 0}[c],
            get_reservation=lambda c: 10,
        )
        p = e.compute_plan()
        assert p.active is False and p.reason == "below_high_water"

    def test_active_loan(self, monkeypatch):
        monkeypatch.setenv("COE_ELASTIC_BAND_ENABLED", "true")
        monkeypatch.setenv("ELASTIC_HIGH_WATER", "20")
        e = ElasticBandRedistributor(
            get_queue_depth=lambda c: {"backtest": 100, "mutation": 0}[c],
            get_reservation=lambda c: 10,
        )
        p = e.compute_plan()
        assert p.active is True
        assert p.loan_amount == 5  # 50% of 10
        assert p.donor_reservation_after == 5
        assert p.receiver_reservation_after == 15

    def test_donor_busy_no_loan(self, monkeypatch):
        monkeypatch.setenv("COE_ELASTIC_BAND_ENABLED", "true")
        monkeypatch.setenv("ELASTIC_HIGH_WATER", "20")
        e = ElasticBandRedistributor(
            get_queue_depth=lambda c: {"backtest": 100, "mutation": 5}[c],
            get_reservation=lambda c: 10,
        )
        p = e.compute_plan()
        assert p.active is False and p.reason == "donor_busy"


# ── Budget hard-cap ──────────────────────────────────────────────────

class TestBudgetHardCap:
    def test_flag_off(self, monkeypatch):
        monkeypatch.delenv("COE_BUDGET_HARD_CAP_ENABLED", raising=False)
        b = BudgetHardCap(get_today_used_usd=lambda: 999.0,
                          get_today_hard_cap=lambda: 10.0)
        d = b.decide(workload_class="agent")
        assert d.admit is True and d.reason == "flag_off_pass_through"

    def test_class_not_gated(self, monkeypatch):
        monkeypatch.setenv("COE_BUDGET_HARD_CAP_ENABLED", "true")
        b = BudgetHardCap(get_today_used_usd=lambda: 999.0,
                          get_today_hard_cap=lambda: 10.0)
        d = b.decide(workload_class="market_data")
        assert d.admit is True and d.reason == "class_not_gated"

    def test_cap_reached_refuses(self, monkeypatch):
        monkeypatch.setenv("COE_BUDGET_HARD_CAP_ENABLED", "true")
        b = BudgetHardCap(get_today_used_usd=lambda: 100.0,
                          get_today_hard_cap=lambda: 100.0)
        d = b.decide(workload_class="agent")
        assert d.admit is False
        assert d.reason == "budget_hard_cap_reached"

    def test_headroom_computed(self, monkeypatch):
        monkeypatch.setenv("COE_BUDGET_HARD_CAP_ENABLED", "true")
        b = BudgetHardCap(get_today_used_usd=lambda: 30.0,
                          get_today_hard_cap=lambda: 100.0)
        d = b.decide(workload_class="agent")
        assert d.admit is True and d.headroom_usd == 70.0


# ── Operator controls ────────────────────────────────────────────────

class TestOperatorControls:
    @pytest.mark.asyncio
    async def test_flag_off_returns_marker(self, monkeypatch):
        monkeypatch.delenv("COE_OPERATOR_CONTROLS_ENABLED", raising=False)
        c = OperatorControls()
        r = await c.circuit_reset(provider="openai", requested_by="op", reason="x")
        assert r["status"] == "flag_off"

    @pytest.mark.asyncio
    async def test_circuit_reset_audits(self, monkeypatch):
        monkeypatch.setenv("COE_OPERATOR_CONTROLS_ENABLED", "true")
        events: List[Dict[str, Any]] = []
        async def _reset(p): return True
        async def _sink(d): events.append(d)
        c = OperatorControls(breaker_reset_hook=_reset, audit_sink=_sink)
        r = await c.circuit_reset(provider="openai", requested_by="op", reason="reopen")
        assert r["status"] == "reset"
        assert len(events) == 1
        assert events[0]["kind"] == "circuit_reset"
        assert events[0]["target"] == "openai"

    @pytest.mark.asyncio
    async def test_queue_pause_resume(self, monkeypatch):
        monkeypatch.setenv("COE_OPERATOR_CONTROLS_ENABLED", "true")
        c = OperatorControls()
        p = await c.queue_pause(workload_class="agent", requested_by="op", reason="drain")
        assert p["status"] == "paused"
        assert c.is_paused("agent") is True
        r = await c.queue_resume(workload_class="agent", requested_by="op", reason="ok")
        assert r["status"] == "resumed"
        assert c.is_paused("agent") is False


# ── Router ───────────────────────────────────────────────────────────

def _make_app():
    from engines.coe_gamma.router import router
    app = FastAPI()
    app.include_router(router)
    return app


class TestRouter:
    def test_dead_letter_endpoints_503_when_off(self, monkeypatch):
        monkeypatch.delenv("COE_DEAD_LETTER_ENABLED", raising=False)
        with TestClient(_make_app()) as c:
            assert c.get("/api/coe/dead-letter").status_code == 503
            assert c.get("/api/coe/dead-letter/depth").status_code == 503
            assert c.get("/api/coe/dead-letter/x").status_code == 503
            assert c.post("/api/coe/dead-letter/x/requeue",
                          json={"requested_by": "op"}).status_code == 503
            assert c.post("/api/coe/dead-letter/x/discard",
                          json={"requested_by": "op", "reason": "x"}).status_code == 503

    def test_operator_endpoints_503_when_off(self, monkeypatch):
        monkeypatch.delenv("COE_OPERATOR_CONTROLS_ENABLED", raising=False)
        with TestClient(_make_app()) as c:
            r = c.post("/api/coe/circuit-breaker/openai/reset",
                       json={"requested_by": "op", "reason": "x"})
            assert r.status_code == 503

    def test_dead_letter_flow_when_on(self, monkeypatch):
        monkeypatch.setenv("COE_DEAD_LETTER_ENABLED", "true")
        db = _FakeDB()
        dl._reset_for_tests()
        monkeypatch.setattr(
            "engines.coe_gamma.router.get_dead_letter_repository",
            lambda: DeadLetterRepository(db_getter=lambda: db),
        )
        with TestClient(_make_app()) as c:
            # No rows initially
            r = c.get("/api/coe/dead-letter")
            assert r.status_code == 200
            assert r.json()["count"] == 0
            # Depth also 200
            r = c.get("/api/coe/dead-letter/depth")
            assert r.status_code == 200 and r.json()["depth"] == 0
            # Unknown row 404
            r = c.get("/api/coe/dead-letter/unknown-id")
            assert r.status_code == 404

    def test_operator_flow_when_on(self, monkeypatch):
        monkeypatch.setenv("COE_OPERATOR_CONTROLS_ENABLED", "true")
        opctl._reset_for_tests()
        events: List[Dict[str, Any]] = []
        async def _reset(p): return True
        async def _sink(d): events.append(d)
        monkeypatch.setattr(
            "engines.coe_gamma.router.get_operator_controls",
            lambda: OperatorControls(breaker_reset_hook=_reset, audit_sink=_sink),
        )
        with TestClient(_make_app()) as c:
            r = c.post("/api/coe/circuit-breaker/openai/reset",
                       json={"requested_by": "op", "reason": "reopen"})
            assert r.status_code == 200 and r.json()["status"] == "reset"
            assert len(events) == 1

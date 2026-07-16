"""v1.2.0-alpha2 Phase H — Execution Intelligence regression tests
(milestones H1 + H2 + H3 foundational scope).

Covers:
  * Types, config, master switch dormancy
  * Ledger idempotency (order_requests, fill_events)
  * Immutable journal — monotonic seq under concurrent writes
  * PaperBrokerAdapter determinism (fills, partial, rejects)
  * Order lifecycle state machine (PENDING → SENT → WORKING → FILLED)
  * Position lifecycle (open, opposing-close, realised PnL)
  * Explainability — every state change emits an outcome event
  * Backward-compat — Phase A/B/B.1/B.2/C/D/E/F/G behaviour preserved
  * Router count invariant unchanged (H1-H3 add zero routers; H9 adds one).
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

sys.path.insert(0, "/app/backend/legacy")
sys.path.insert(0, "/app/backend")


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@strategy-factory.local",
                     "password": "admin123"})
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── 1. Types + config ───────────────────────────────────────────
class TestTypes:
    def test_order_state_terminality(self):
        from engines.execution import OrderState
        assert OrderState.is_terminal(OrderState.FILLED)
        assert OrderState.is_terminal(OrderState.REJECTED)
        assert OrderState.is_terminal(OrderState.CANCELLED)
        assert OrderState.is_terminal(OrderState.EXPIRED)
        assert not OrderState.is_terminal(OrderState.WORKING)
        assert not OrderState.is_terminal(OrderState.PENDING)

    def test_order_request_roundtrip(self):
        from engines.execution import OrderRequest
        o = OrderRequest(request_id="r1", account_id="a",
                          pair="EURUSD", side="BUY", type="MARKET",
                          qty=100.0)
        d = o.to_dict()
        o2 = OrderRequest.from_dict(d)
        assert o2.request_id == "r1" and o2.qty == 100.0


class TestConfig:
    def test_defaults_operator_safe(self):
        # Isolate from previous test env pollution
        for k in ("EXEC_LIVE_MEASUREMENT", "BRAIN_USES_LIVE_EXECUTION",
                  "BROKER_KILL_SWITCH"):
            os.environ.pop(k, None)
        from engines.execution import (
            exec_enabled, broker_name, live_measurement_enabled,
            brain_uses_live_execution, exec_config_snapshot,
        )
        assert exec_enabled() is True                # dormant only via env
        assert broker_name() == "paper"              # Q1 — safe default
        assert live_measurement_enabled() is False   # Q2 — opt-in
        assert brain_uses_live_execution() is False  # Q2 — opt-in
        snap = exec_config_snapshot()
        assert snap["BROKER"] == "paper"
        # Q4: three rolling windows must be present
        assert set(snap["health_windows"].keys()) == {"short_s", "medium_s", "long_s"}
        # Q3: risk thresholds all present but non-liquidating
        for k in ("max_positions", "max_exposure_pair",
                  "daily_loss_pct", "loss_24h_pct", "broker_health_min"):
            assert k in snap["risk_thresholds"]


# ── 2. Ledger idempotency ───────────────────────────────────────
class TestLedger:
    def test_order_and_journal_flow(self):
        script = r"""
import asyncio, uuid, sys, os
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.execution import (
    ensure_indexes, OrderRequest, OrderState, JournalEventType,
    append_order_request, update_order_state, read_order,
    append_fill_event, read_fills, FillEvent,
    append_journal, read_journal_range,
)
async def go():
    await ensure_indexes()
    from engines.db import get_db
    db = get_db()
    for c in ('order_requests','fill_events','execution_journal'):
        await db[c].delete_many({'account_id': 'PYTEST_H'})

    rid = 'req_' + uuid.uuid4().hex[:8]
    o = OrderRequest(request_id=rid, account_id='PYTEST_H',
        pair='EURUSD', side='BUY', type='MARKET', qty=1000.0)
    await append_order_request(o)
    await append_order_request(o)         # duplicate — must be a no-op
    n = await db['order_requests'].count_documents({'request_id': rid})
    assert n == 1, f'order dup: {n}'

    await update_order_state(rid, state=OrderState.WORKING, broker_order_id='b1')
    r = await read_order(rid)
    assert r.state == OrderState.WORKING
    assert r.broker_order_id == 'b1'

    fills = [FillEvent(fill_id=f'f_{i}', request_id=rid,
        account_id='PYTEST_H', pair='EURUSD', side='BUY',
        qty_filled=100.0, price=1.08+i*0.0001,
        timestamp='2026-02-16T00:00:00Z') for i in range(3)]
    for f in fills:
        await append_fill_event(f)
    read_back = await read_fills(request_id=rid)
    assert len(read_back) == 3

    # Journal monotonic seq under concurrent writes
    tasks = [append_journal('PYTEST_H', JournalEventType.LATENCY_SAMPLE,
        {'ms': i}) for i in range(20)]
    results = await asyncio.gather(*tasks)
    seqs = [r.seq for r in results if r]
    assert len(seqs) == 20
    assert len(set(seqs)) == 20   # all unique

    # Range read is chronological
    rows = await read_journal_range('PYTEST_H', limit=200)
    prev = 0
    for row in rows:
        assert row.seq > prev, f'seq {row.seq} not > prev {prev}'
        prev = row.seq
    print('LEDGER_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "LEDGER_OK" in r.stdout


# ── 3. PaperBrokerAdapter ───────────────────────────────────────
class TestPaperBroker:
    def test_deterministic_market_fill(self):
        script = r"""
import asyncio, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.execution import (
    OrderRequest, PaperBrokerAdapter,
)
async def go():
    br = PaperBrokerAdapter(seed=42)
    await br.connect()
    r = OrderRequest(request_id='det1', account_id='X', pair='EURUSD',
        side='BUY', type='MARKET', qty=1000.0, price=1.08)
    bid = await br.submit(r)
    assert bid.startswith('paper_')
    fills = await br.drain_fills(timeout=0.1)
    assert len(fills) == 1, f'expected 1 fill, got {len(fills)}'
    # Deterministic: default slippage 0.2 pips, BUY pays higher
    assert abs(fills[0].price - (1.08 + 0.00002)) < 1e-6, f'price={fills[0].price}'
    print('PAPER_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "PAPER_OK" in r.stdout

    def test_idempotent_submit(self):
        script = r"""
import asyncio, sys
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.execution import OrderRequest, PaperBrokerAdapter
async def go():
    br = PaperBrokerAdapter(seed=0)
    await br.connect()
    r = OrderRequest(request_id='same_id', account_id='X', pair='EURUSD',
        side='BUY', type='MARKET', qty=1000.0, price=1.08)
    b1 = await br.submit(r)
    b2 = await br.submit(r)   # same request_id — must return same broker_id
    assert b1 == b2, f'{b1} != {b2}'
    print('IDEMPO_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "IDEMPO_OK" in r.stdout

    def test_kill_switch_blocks_submit(self):
        script = r"""
import asyncio, sys, os
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
os.environ['BROKER_KILL_SWITCH']='true'
from engines.execution import (OrderRequest, PaperBrokerAdapter, BrokerError)
async def go():
    br = PaperBrokerAdapter(seed=0)
    await br.connect()
    r = OrderRequest(request_id='ks1', account_id='X', pair='EURUSD',
        side='BUY', type='MARKET', qty=1000.0, price=1.08)
    try:
        await br.submit(r)
        print('KILL_SWITCH_FAIL')
    except BrokerError as e:
        assert 'KILL_SWITCH' in str(e)
        print('KILL_SWITCH_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "KILL_SWITCH_OK" in r.stdout


# ── 4. End-to-end order + position lifecycle ────────────────────
class TestLifecycle:
    def test_full_roundtrip(self):
        script = r"""
import asyncio, sys, uuid
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.execution import (
    ensure_indexes, OrderRequest, get_paper_adapter, reset_paper_adapter,
    submit_order, process_fill, apply_fill_to_position,
    read_positions, read_closed_positions, read_journal_range,
)
async def go():
    await ensure_indexes()
    from engines.db import get_db
    db = get_db()
    for c in ('order_requests','fill_events','positions','execution_journal'):
        await db[c].delete_many({'account_id': 'H2_TEST'})
    reset_paper_adapter()
    br = get_paper_adapter()
    await br.connect()

    # Open + close in a full round trip
    open_req = OrderRequest(request_id='ro'+uuid.uuid4().hex[:6],
        account_id='H2_TEST', pair='EURUSD', side='BUY', type='MARKET',
        qty=10000.0, price=1.08, strategy_hash='s', brain_decision_id='bd')
    boid, term = await submit_order(open_req, br)
    assert boid and term == 'WORKING', f'{boid} {term}'
    for f in await br.drain_fills(timeout=0.15):
        await process_fill(f)
        await apply_fill_to_position(f, strategy_hash='s', brain_decision_id='bd')

    open_pos = await read_positions(account_id='H2_TEST', open_only=True)
    assert len(open_pos) == 1
    assert open_pos[0].side == 'BUY' and open_pos[0].qty == 10000.0

    close_req = OrderRequest(request_id='rc'+uuid.uuid4().hex[:6],
        account_id='H2_TEST', pair='EURUSD', side='SELL', type='MARKET',
        qty=10000.0, price=1.09, strategy_hash='s', brain_decision_id='bd')
    await submit_order(close_req, br)
    for f in await br.drain_fills(timeout=0.15):
        await process_fill(f)
        await apply_fill_to_position(f, strategy_hash='s', brain_decision_id='bd')

    closed = await read_closed_positions(account_id='H2_TEST')
    assert len(closed) == 1 and closed[0].state == 'CLOSED'
    assert closed[0].realised_pnl > 0, f'expected positive PnL, got {closed[0].realised_pnl}'

    # Journal chain check — must contain both order_state_change and fill_event.
    j = await read_journal_range('H2_TEST')
    types = {e.event_type for e in j}
    assert 'order_state_change' in types
    assert 'fill_event' in types
    print('E2E_OK realised_pnl=', round(closed[0].realised_pnl, 2))
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "E2E_OK" in r.stdout


# ── 5. Backward compatibility ───────────────────────────────────
class TestBackwardCompatibility:
    """H1-H3 additive milestones: router count unchanged, no /api/execution/*
    endpoints yet (arriving in H9). Phase G behaviour preserved."""

    def test_router_count_unchanged_pre_h9(self):
        # H1-H8 add zero routers; H9 will add one (execution_engine → 98)
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        m = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert m
        # Accept 97 (pre-H9) or 98 (post-H9)
        assert m[-1] in ("97", "98"), f"boot reports {m[-1]}"

    def test_no_execution_api_yet(self, admin):
        # /api/execution/* endpoints are H9 — must currently 404
        r = admin.get(f"{BASE_URL}/api/execution/broker/health")
        assert r.status_code in (404, 405, 501)

    def test_exec_indexes_bootstrapped_on_boot(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        assert "execution engine indexes bootstrapped" in log

    def test_phase_g_endpoints_still_work(self, admin):
        r = admin.get(f"{BASE_URL}/api/market-intelligence/observers/config")
        assert r.status_code == 200

    def test_phase_f_endpoints_still_work(self, admin):
        r = admin.get(f"{BASE_URL}/api/brain/policy/weights")
        assert r.status_code == 200


# ── 6. Explainability — Q5 immutable audit chain ────────────────
class TestExplainability:
    def test_journal_chain_preserves_ids(self):
        script = r"""
import asyncio, sys, uuid
sys.path.insert(0,'/app/backend'); sys.path.insert(0,'/app/backend/legacy')
from engines.execution import (
    ensure_indexes, OrderRequest, get_paper_adapter, reset_paper_adapter,
    submit_order, process_fill, read_journal_range,
)
async def go():
    await ensure_indexes()
    from engines.db import get_db
    db = get_db()
    for c in ('order_requests','fill_events','execution_journal'):
        await db[c].delete_many({'account_id': 'AUDIT'})
    reset_paper_adapter()
    br = get_paper_adapter()
    await br.connect()
    req = OrderRequest(request_id='audit1', account_id='AUDIT',
        pair='EURUSD', side='BUY', type='MARKET', qty=1000.0,
        price=1.08, strategy_hash='SH_X', brain_decision_id='BD_Y')
    await submit_order(req, br)
    for f in await br.drain_fills(timeout=0.1):
        await process_fill(f)

    j = await read_journal_range('AUDIT')
    # Every event must carry the request_id correlation
    for e in j:
        assert e.correlation.get('request_id') == 'audit1' or \
               e.correlation.get('fill_id')
    # First event carries brain_decision_id + strategy_hash
    first = j[0]
    assert first.correlation.get('brain_decision_id') == 'BD_Y'
    assert first.correlation.get('strategy_hash') == 'SH_X'
    print('AUDIT_OK')
asyncio.run(go())
"""
        r = subprocess.run(["python3", "-c", script], capture_output=True,
                           text=True, env={**os.environ,
                            "PYTHONPATH": "/app/backend:/app/backend/legacy"})
        assert r.returncode == 0, r.stderr
        assert "AUDIT_OK" in r.stdout

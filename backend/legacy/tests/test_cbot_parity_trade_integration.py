"""
P1.3 — Tests for the flag-gated trade-parity integration in
``engines.cbot_parity.sign_off_parity``.

Scope:

    1. **OFF identity** — when ``ENABLE_CBOT_TRADE_PARITY=False`` (the
       institutional default), the sign-off document and audit row
       carry NO ``trade_*`` keys. Byte-for-byte identical to pre-P1.3.

    2. **ON additive** — when the flag is ON, the sign-off document
       gains a ``trade_summary`` block, a ``trade_parity_passed`` bool,
       ``trade_parity_inputs`` echo, ``trade_parity_self_check``
       verdict, and ``trade_parity_advisory_only=True``. The audit row
       also carries ``trade_parity_passed`` / ``trade_parity_self_check``
       / count fields.

    3. **Status invariance** — the OVERALL ``status`` is driven ONLY
       by signal parity in both modes. P1.3 never promotes
       trade-parity to a hard gate (that belongs to a future,
       separately-reviewed pass).

    4. **Error containment** — if the trade-parity step itself raises,
       ``trade_parity_passed=False`` is recorded, but the signal-parity
       ``status="PASSED"`` is preserved (advisory-only discipline).

The tests use an in-memory monkeypatch of `engines.cbot_parity`'s I/O
seam (`get_db`, `_find_ir_for_strategy`, `_load_price_fixture`,
`_persist_signoff`, `_audit`) so we never touch a real Mongo.
"""
from __future__ import annotations

import asyncio
import math
import random
import sys
from datetime import datetime, timedelta, timezone

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines import cbot_parity as P                          # noqa: E402
from engines.mutation_engine import _derive_base_ir           # noqa: E402


_TREND_TEXT = (
    "STRATEGY: Base Trend (EURUSD H1)\n"
    "ENTRY LONG:  EMA(20) crosses above EMA(50)\n"
    "ENTRY SHORT: EMA(20) crosses below EMA(50)\n"
    "EXIT: SL = 20 pips  |  TP = 40 pips\n"
)


def _ir():
    return _derive_base_ir({
        "strategy_text": _TREND_TEXT,
        "pair":          "EURUSD",
        "timeframe":     "H1",
    })


def _series(n: int = 240, seed: int = 42):
    rng = random.Random(seed)
    closes, highs, lows, ts = [], [], [], []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        c = 1.10 + 0.005 * math.sin(2 * math.pi * i / 50) + (rng.random() - 0.5) * 0.001
        closes.append(c)
        highs.append(c + 0.0005 + rng.random() * 0.0003)
        lows.append(c - 0.0005 - rng.random() * 0.0003)
        ts.append(start + timedelta(hours=i))
    return closes, highs, lows, ts


@pytest.fixture
def patched_signoff(monkeypatch):
    """Patch the I/O seam so sign_off_parity can be exercised without
    Mongo. Records calls to `_persist_signoff` and `_audit` for
    assertions.
    """
    state = {
        "signoff_docs": [],
        "audit_rows":  [],
    }

    ir = _ir()
    closes, highs, lows, ts = _series()

    class _DummyDB:
        pass

    monkeypatch.setattr(P, "get_db", lambda: _DummyDB())

    async def fake_find_ir(strategy_hash):  # noqa: ARG001
        return ir

    async def fake_load_fixture(pair, timeframe, n_bars=240):  # noqa: ARG001
        return closes, highs, lows, ts

    async def fake_persist(db, doc):  # noqa: ARG001
        state["signoff_docs"].append(dict(doc))

    async def fake_audit(db, strategy_hash, outcome, *, triggered_by):  # noqa: ARG001
        # Mirror what the real _audit row would carry. We re-build it
        # here using the same logic the production function does so
        # the tests assert the public contract.
        row = {
            "ts": P._now_iso(),
            "event": "cbot_parity_signoff",
            "strategy_hash": strategy_hash,
            "status": outcome.get("status"),
            "triggered_by": triggered_by,
            "fixture": outcome.get("fixture"),
            "parity_mode": outcome.get("parity_mode"),
            "fixtures_passed": outcome.get("fixtures_passed"),
            "details": outcome.get("details"),
            "phase": "B.1",
        }
        if "trade_parity_passed" in outcome:
            row["trade_parity_passed"] = outcome.get("trade_parity_passed")
            row["trade_parity_self_check"] = outcome.get("trade_parity_self_check")
            if outcome.get("trade_summary"):
                ts_sum = outcome["trade_summary"]
                row["trade_parity_total_trades"] = ts_sum.get("total_trades")
                row["trade_parity_sl_hits"] = ts_sum.get("sl_hits")
                row["trade_parity_tp_hits"] = ts_sum.get("tp_hits")
        state["audit_rows"].append(row)

    monkeypatch.setattr(P, "_find_ir_for_strategy", fake_find_ir)
    monkeypatch.setattr(P, "_load_price_fixture", fake_load_fixture)
    monkeypatch.setattr(P, "_persist_signoff", fake_persist)
    monkeypatch.setattr(P, "_audit", fake_audit)

    return state


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — OFF identity
# ─────────────────────────────────────────────────────────────────────
class TestFlagOffIdentity:

    def test_signoff_passed_status_unchanged(self, patched_signoff, monkeypatch):
        monkeypatch.delenv("ENABLE_CBOT_TRADE_PARITY", raising=False)
        out = asyncio.run(P.sign_off_parity("hash-off-1", triggered_by="test"))
        assert out["status"] == "PASSED"
        assert out["signal_summary"]["total"] > 0

    def test_no_trade_keys_when_flag_off(self, patched_signoff, monkeypatch):
        monkeypatch.delenv("ENABLE_CBOT_TRADE_PARITY", raising=False)
        out = asyncio.run(P.sign_off_parity("hash-off-2", triggered_by="test"))
        for key in (
            "trade_summary",
            "trade_parity_passed",
            "trade_parity_inputs",
            "trade_parity_self_check",
            "trade_parity_advisory_only",
        ):
            assert key not in out, (
                f"P1.3 OFF-identity invariant violated: {key} present "
                "in sign-off doc when ENABLE_CBOT_TRADE_PARITY is OFF"
            )
        # Audit row also has no trade_* keys
        assert patched_signoff["audit_rows"], "expected an audit row"
        last_audit = patched_signoff["audit_rows"][-1]
        for key in last_audit:
            assert not key.startswith("trade_parity"), (
                f"P1.3 OFF-identity violated: audit row carries {key}"
            )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — ON additive
# ─────────────────────────────────────────────────────────────────────
class TestFlagOnAdditive:

    def test_trade_summary_attached_when_on(self, patched_signoff, monkeypatch):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        out = asyncio.run(P.sign_off_parity("hash-on-1", triggered_by="test"))
        # OVERALL status must still be PASSED (signal-parity-driven).
        assert out["status"] == "PASSED"
        # Trade-parity additive metadata MUST be present.
        assert "trade_summary" in out
        assert "trade_parity_passed" in out
        assert "trade_parity_self_check" in out
        assert "trade_parity_inputs" in out
        assert out.get("trade_parity_advisory_only") is True

    def test_trade_parity_self_check_verdict(self, patched_signoff, monkeypatch):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        out = asyncio.run(P.sign_off_parity("hash-on-2", triggered_by="test"))
        assert out["trade_parity_self_check"] in ("PASSED", "EMPTY")
        assert out["trade_parity_passed"] is True

    def test_trade_summary_counts_consistent(self, patched_signoff, monkeypatch):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        out = asyncio.run(P.sign_off_parity("hash-on-3", triggered_by="test"))
        s = out["trade_summary"]
        assert s["total_trades"] == s["buy_count"] + s["sell_count"]
        assert (
            s["sl_hits"] + s["tp_hits"] + s["open_at_end"] == s["total_trades"]
        )

    def test_audit_row_carries_trade_parity_when_on(
        self, patched_signoff, monkeypatch,
    ):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        asyncio.run(P.sign_off_parity("hash-on-4", triggered_by="test"))
        last_audit = patched_signoff["audit_rows"][-1]
        assert "trade_parity_passed" in last_audit
        assert "trade_parity_self_check" in last_audit


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — status invariance
# ─────────────────────────────────────────────────────────────────────
class TestStatusInvariance:

    def test_status_is_passed_regardless_of_flag(
        self, patched_signoff, monkeypatch,
    ):
        # OFF
        monkeypatch.delenv("ENABLE_CBOT_TRADE_PARITY", raising=False)
        a = asyncio.run(P.sign_off_parity("hash-inv-1", triggered_by="test"))
        # ON
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")
        b = asyncio.run(P.sign_off_parity("hash-inv-2", triggered_by="test"))
        # Same core PASSED verdict; same signal_summary content.
        assert a["status"] == b["status"] == "PASSED"
        assert a["signal_summary"] == b["signal_summary"]
        assert a["operators_used"] == b["operators_used"]
        assert a["indicator_kinds_used"] == b["indicator_kinds_used"]


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — error containment
# ─────────────────────────────────────────────────────────────────────
class TestErrorContainment:

    def test_trade_parity_exception_does_not_overwrite_status(
        self, patched_signoff, monkeypatch,
    ):
        monkeypatch.setenv("ENABLE_CBOT_TRADE_PARITY", "true")

        # Monkey-patch simulate_trades to blow up so we can verify
        # the containment branch is reached.
        from engines import cbot_trade_parity as TP

        def boom(*args, **kwargs):  # noqa: ARG001
            raise RuntimeError("synthetic trade-parity failure")

        monkeypatch.setattr(TP, "simulate_trades", boom)

        out = asyncio.run(P.sign_off_parity("hash-err-1", triggered_by="test"))
        # Signal-parity verdict preserved.
        assert out["status"] == "PASSED"
        # Trade-parity recorded as failed BUT advisory-only.
        assert out["trade_parity_passed"] is False
        assert "trade_parity_error" in out
        assert out["trade_parity_advisory_only"] is True

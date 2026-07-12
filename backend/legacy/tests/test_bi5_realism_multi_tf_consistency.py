"""Phase 27.4 — BI5 multi-TF realism consistency tests.

End-to-end consistency: two strategy hashes for the same pair at
different timeframes must derive their realism reading from the same
1m base stream. Verifies that ``bi5_realism.evaluate()`` now routes
through ``_load_and_resample_bi5`` (the canonical Phase 27.4 path) and
that the persisted block carries the ``resample`` provenance.

Pure-mock tests — no Mongo, no HTTP, no fixtures.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch


_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines import bi5_realism                              # noqa: E402


def _arun(coro):
    return asyncio.run(coro)


def _make_1m_stream(start: datetime, n_minutes: int) -> list:
    """Synthetic 1m stream — deterministic, ascending closes."""
    out = []
    for i in range(n_minutes):
        ts = start + timedelta(minutes=i)
        c = 1.1000 + (i / 100000.0)
        out.append({
            "timestamp": ts.isoformat(),
            "open":   c - 0.0001,
            "high":   c + 0.0002,
            "low":    c - 0.0002,
            "close":  c,
            "volume": 1.0,
        })
    return out


def _lib(timeframe: str, *, pf: float = 1.5) -> dict:
    return {
        "library_id":    f"lib_test_27_4_{timeframe}",
        "strategy_text": "RSI > 50",
        "pair":          "EURUSD",
        "timeframe":     timeframe,
        "profit_factor": pf,
    }


# ── Tests ──────────────────────────────────────────────────────────


class TestRealismRoutesThroughResample:
    """`evaluate()` must obtain bars exclusively via the new
    `_load_and_resample_bi5` path. Verified by patching the canonical
    1m loader and confirming the resample block lands on the persisted
    payload."""

    def test_h1_evaluate_uses_resample_path(self):
        """H1 strategy → resampled-from-1m → ok band → persisted block
        carries `resample.applied=True, from='1m', to='H1'`."""
        # 30 days of 1m bars — way over the 200-H1-bar floor.
        stream = _make_1m_stream(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            n_minutes=60 * 24 * 30,
        )
        captured_block = {}

        async def _capture(strategy_hash, *, library_id, block):
            captured_block.update(block)

        async def _go():
            with patch("engines.data_access.load_bi5_1m_bars",
                       new=AsyncMock(return_value=stream)), \
                 patch.object(bi5_realism, "_resolve_library_doc",
                              new=AsyncMock(return_value=_lib("H1"))), \
                 patch("engines.bi5_realism.run_backtest_logic",
                       return_value={
                           "profit_factor": 1.30,    # ratio 1.30/1.5 = 0.866 → ok
                           "total_trades":  60,
                       }), \
                 patch.object(bi5_realism, "_persist_realism", new=_capture):
                return await bi5_realism.evaluate(
                    "TEST_BI5_27_4_h1",
                    persist=True, force_refresh=True,
                )

        out = _arun(_go())
        assert out["status"] == "ok", f"got {out}"
        assert out["flag"] is None
        assert captured_block.get("resample") is not None
        assert captured_block["resample"]["applied"] is True
        assert captured_block["resample"]["from"] == "1m"
        assert captured_block["resample"]["to"] == "H1"
        assert captured_block["resample"]["boundary"] == "left"
        assert captured_block["resample"]["label"] == "left"

    def test_m15_evaluate_uses_resample_path(self):
        """M15 strategy reading the SAME 1m base produces an
        independent realism block with `resample.to='M15'`."""
        stream = _make_1m_stream(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            n_minutes=60 * 24 * 10,
        )
        captured_block = {}

        async def _capture(strategy_hash, *, library_id, block):
            captured_block.update(block)

        async def _go():
            with patch("engines.data_access.load_bi5_1m_bars",
                       new=AsyncMock(return_value=stream)), \
                 patch.object(bi5_realism, "_resolve_library_doc",
                              new=AsyncMock(return_value=_lib("M15"))), \
                 patch("engines.bi5_realism.run_backtest_logic",
                       return_value={
                           "profit_factor": 1.20,
                           "total_trades":  120,
                       }), \
                 patch.object(bi5_realism, "_persist_realism", new=_capture):
                return await bi5_realism.evaluate(
                    "TEST_BI5_27_4_m15",
                    persist=True, force_refresh=True,
                )

        out = _arun(_go())
        assert out["status"] == "ok"
        assert captured_block["resample"]["to"] == "M15"
        assert captured_block["resample"]["from"] == "1m"

    def test_data_missing_path_still_carries_resample_metadata(self):
        """When the 1m base is empty, the persisted data_missing block
        must still carry the resample provenance so operators can see
        that the path was attempted."""
        captured_block = {}

        async def _capture(strategy_hash, *, library_id, block):
            captured_block.update(block)

        async def _go():
            with patch("engines.data_access.load_bi5_1m_bars",
                       new=AsyncMock(return_value=[])), \
                 patch.object(bi5_realism, "_resolve_library_doc",
                              new=AsyncMock(return_value=_lib("H1"))), \
                 patch.object(bi5_realism, "_persist_realism", new=_capture):
                return await bi5_realism.evaluate(
                    "TEST_BI5_27_4_missing",
                    persist=True, force_refresh=True,
                )

        out = _arun(_go())
        assert out["status"] == "data_missing"
        assert out["flag"] == "BI5_DATA_MISSING"
        # The persisted block must carry the resample envelope so an
        # operator can see what was attempted.
        assert "resample" in captured_block
        assert captured_block["resample"]["from"] == "1m"
        assert captured_block["resample"]["to"] == "H1"


class TestSingleStreamArchitecturalInvariant:
    """The realism evaluator must NEVER call
    ``data_access.load_with_recovery`` with ``source='bi5'`` — the
    Phase 27.4 contract is that ``load_bi5_1m_bars`` is the SOLE BI5
    read point."""

    def test_evaluate_does_not_use_load_with_recovery_for_bi5(self):
        """If anything inside `evaluate()` reaches for
        `load_with_recovery(source='bi5', ...)` we want to know."""
        stream = _make_1m_stream(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            n_minutes=60 * 24 * 30,
        )
        load_with_recovery_calls: list = []

        async def _spy_lwr(*args, **kwargs):
            load_with_recovery_calls.append(kwargs)
            return {"status": "insufficient", "bars": [], "count": 0}

        async def _go():
            with patch("engines.data_access.load_bi5_1m_bars",
                       new=AsyncMock(return_value=stream)), \
                 patch("engines.data_access.load_with_recovery",
                       new=_spy_lwr), \
                 patch.object(bi5_realism, "_resolve_library_doc",
                              new=AsyncMock(return_value=_lib("H1"))), \
                 patch("engines.bi5_realism.run_backtest_logic",
                       return_value={
                           "profit_factor": 1.30, "total_trades": 60,
                       }), \
                 patch.object(bi5_realism, "_persist_realism",
                              new=AsyncMock(return_value=None)):
                return await bi5_realism.evaluate(
                    "TEST_BI5_27_4_invariant",
                    persist=True, force_refresh=True,
                )

        out = _arun(_go())
        assert out["status"] == "ok"
        # Phase 27.4 invariant: realism evaluator never reaches for
        # the legacy `load_with_recovery(source='bi5')` path.
        bi5_lwr_calls = [
            c for c in load_with_recovery_calls
            if c.get("source") == "bi5"
        ]
        assert bi5_lwr_calls == [], (
            f"realism evaluator called load_with_recovery(source='bi5') "
            f"{len(bi5_lwr_calls)}× — Phase 27.4 contract violation"
        )

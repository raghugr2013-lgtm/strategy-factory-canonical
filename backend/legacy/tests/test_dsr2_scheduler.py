"""DSR-2 — Scheduler consumes the dynamic Market Universe registry.

Validates ``_ingestion_symbols()`` in ``data_engine.auto_data_maintainer``:

  * **Flag OFF (legacy default)** → returns ``list(SYMBOL_CONFIG.keys())``
    byte-identically. Zero behavioural drift on the 7 legacy symbols.
  * **Flag ON** → consults ``market_universe.list_symbols(enabled=True)``
    and yields only symbols whose ``eligibility.ingestion_enabled`` is
    truthy.
  * **Registry empty / error** → falls back to ``SYMBOL_CONFIG`` so the
    scheduler never starves.

These are pure unit tests — no Mongo, no APScheduler. We monkeypatch
``is_flag_on`` and ``list_symbols`` to exercise each branch.
"""
from __future__ import annotations

import asyncio

from data_engine import auto_data_maintainer as ADM
from config.symbols import SYMBOL_CONFIG


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────
# Flag OFF — legacy parity
# ─────────────────────────────────────────────────────────────────────
class TestDsr2FlagOff:
    def test_returns_legacy_symbol_config(self, monkeypatch):
        # Force the flag OFF regardless of env.
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: False,
        )
        out = _run(ADM._ingestion_symbols())
        assert out == list(SYMBOL_CONFIG.keys())

    def test_does_not_call_registry_when_flag_off(self, monkeypatch):
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: False,
        )
        called = {"n": 0}

        async def boom(*a, **kw):
            called["n"] += 1
            raise RuntimeError("registry must not be touched when flag OFF")

        monkeypatch.setattr("engines.market_universe.list_symbols", boom)
        _run(ADM._ingestion_symbols())
        assert called["n"] == 0


# ─────────────────────────────────────────────────────────────────────
# Flag ON — registry-driven
# ─────────────────────────────────────────────────────────────────────
class TestDsr2FlagOn:
    def _make_rows(self):
        # 3 ingestion-eligible · 1 ingestion-disabled · 1 enabled=False (already
        # filtered upstream — included here to prove the helper does NOT
        # double-filter, list_symbols(enabled=True) is the upstream filter).
        return [
            {"symbol": "EURUSD", "enabled": True,
             "eligibility": {"ingestion_enabled": True}},
            {"symbol": "BTCUSD", "enabled": True,
             "eligibility": {"ingestion_enabled": True}},
            {"symbol": "NAS100", "enabled": True,
             "eligibility": {"ingestion_enabled": True}},
            {"symbol": "GBPUSD", "enabled": True,
             "eligibility": {"ingestion_enabled": False}},  # filtered by helper
        ]

    def test_returns_only_ingestion_eligible(self, monkeypatch):
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: True,
        )
        rows = self._make_rows()

        async def fake_list(**kwargs):
            assert kwargs.get("enabled") is True
            return rows

        monkeypatch.setattr("engines.market_universe.list_symbols", fake_list)
        out = _run(ADM._ingestion_symbols())
        assert out == ["EURUSD", "BTCUSD", "NAS100"]
        assert "GBPUSD" not in out  # ingestion_enabled=False

    def test_dedupes(self, monkeypatch):
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: True,
        )

        async def fake_list(**kwargs):
            return [
                {"symbol": "EURUSD", "enabled": True,
                 "eligibility": {"ingestion_enabled": True}},
                {"symbol": "EURUSD", "enabled": True,
                 "eligibility": {"ingestion_enabled": True}},
            ]

        monkeypatch.setattr("engines.market_universe.list_symbols", fake_list)
        out = _run(ADM._ingestion_symbols())
        assert out == ["EURUSD"]

    def test_falls_back_when_registry_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: True,
        )

        async def fake_list(**kwargs):
            return []

        monkeypatch.setattr("engines.market_universe.list_symbols", fake_list)
        out = _run(ADM._ingestion_symbols())
        # Empty registry → must NOT starve; fall back to legacy.
        assert out == list(SYMBOL_CONFIG.keys())

    def test_falls_back_when_registry_raises(self, monkeypatch):
        monkeypatch.setattr(
            "engines.market_universe_adapter.is_flag_on",
            lambda: True,
        )

        async def fake_list(**kwargs):
            raise RuntimeError("simulated mongo timeout")

        monkeypatch.setattr("engines.market_universe.list_symbols", fake_list)
        out = _run(ADM._ingestion_symbols())
        assert out == list(SYMBOL_CONFIG.keys())


# ─────────────────────────────────────────────────────────────────────
# Sanity — helper exists and is async
# ─────────────────────────────────────────────────────────────────────
class TestDsr2HelperContract:
    def test_helper_is_async(self):
        import inspect
        assert inspect.iscoroutinefunction(ADM._ingestion_symbols)

    def test_helper_is_consumed_by_three_jobs(self):
        # Grep the file to ensure _bid_track_job, _bi5_track_job,
        # run_auto_maintenance all call _ingestion_symbols().
        import pathlib
        src = pathlib.Path(ADM.__file__).read_text()
        assert "_ingestion_symbols" in src
        assert src.count("_ingestion_symbols(") >= 4  # 1 def + 3 callers

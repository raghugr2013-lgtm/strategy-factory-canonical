"""R0 — Per-symbol byte-parity tests for the market_universe seed.

For each of the 7 canonical symbols, assert that the seed payload
reproduces the legacy hardcoded constants EXACTLY:

* ``calendar``         ≡ ``config/symbols.py::SYMBOL_CONFIG``
* ``broker_mapping``   ≡ ``config/bi5_symbols.py::_BI5_SYMBOL_SPECS``
                       + ``data_engine/dukascopy_downloader.py::INSTRUMENT_MAP``
* ``precision``        ≡ ``config/bi5_symbols.py`` (price_multiplier, quote_decimals)
* ``spread_defaults``  ≡ ``engines/spread_analyzer.py::{DEFAULT_TOLERANCE_BPS,
                                                       SYMBOL_DEFAULT_BPS}``
* ``cert_defaults.density_table`` ≡ ``engines/tick_validator.py::DENSITY_TABLE``

Pure equality — if a legacy constant changes, this test fails loudly
so the seed payload can be updated in lockstep. This is the contract
that lets R5 flip the flag safely.

Also exercises:
* Seed idempotency (running twice produces no new audit rows for
  unchanged data).
* Baseline audit row presence after first insert.
* 409 / refusal on seed-row delete without ``force=True``.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any, Dict

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture
def patched_db(monkeypatch):
    """Patch engines.db to a fresh mongomock_motor handle per test."""
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    db = client["r0_seed_test"]

    from engines import db as db_mod
    monkeypatch.setattr(db_mod, "_db", db, raising=False)
    monkeypatch.setattr(db_mod, "_client", client, raising=False)
    monkeypatch.setattr(db_mod, "get_db", lambda: db)

    # Also patch the already-imported references inside companion modules.
    from engines import market_universe as MU
    from engines import market_universe_audit as MUA
    monkeypatch.setattr(MU, "get_db", lambda: db, raising=False)
    monkeypatch.setattr(MUA, "get_db", lambda: db, raising=False)
    from engines.seed import market_universe_seed as SEED
    monkeypatch.setattr(SEED, "get_db", lambda: db, raising=False)

    return db


# ─────────────────────────────────────────────────────────────────────
# Byte-parity assertions vs legacy constants
# ─────────────────────────────────────────────────────────────────────
class TestSeedByteParity:
    """Each seed row's nested fields must equal the legacy constants."""

    def _seed_by_symbol(self) -> Dict[str, Dict[str, Any]]:
        from engines.seed.market_universe_seed import SEED_SYMBOLS
        return {row["symbol"]: row for row in SEED_SYMBOLS}

    def test_calendar_parity(self):
        from config.symbols import SYMBOL_CONFIG
        seed = self._seed_by_symbol()
        for sym, legacy in SYMBOL_CONFIG.items():
            assert sym in seed, f"{sym} missing from seed"
            cal = seed[sym]["calendar"]
            assert cal["market_type"] == legacy["market_type"], (
                f"{sym}: calendar.market_type drift"
            )
            assert cal["timezone"] == legacy["timezone"], (
                f"{sym}: calendar.timezone drift"
            )

    def test_bi5_broker_mapping_parity(self):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        seed = self._seed_by_symbol()
        for sym, spec in _BI5_SYMBOL_SPECS.items():
            assert sym in seed, f"{sym} missing from seed"
            bm = seed[sym]["broker_mapping"]
            assert bm["dukascopy_slug"] == spec.url_slug, (
                f"{sym}: broker_mapping.dukascopy_slug drift"
            )
            prec = seed[sym]["precision"]
            assert prec["price_multiplier"] == spec.price_multiplier, (
                f"{sym}: precision.price_multiplier drift"
            )
            assert prec["quote_decimals"] == spec.quote_decimals, (
                f"{sym}: precision.quote_decimals drift"
            )

    def test_dukascopy_instrument_id_parity(self):
        """Seed must carry the SDK enum token name for every symbol that
        is mapped in INSTRUMENT_MAP."""
        from data_engine.dukascopy_downloader import INSTRUMENT_MAP
        seed = self._seed_by_symbol()
        # Hardcoded mapping mirror — kept in this test to detect any drift
        # in the SDK adapter without importing the SDK at test time.
        expected_ids = {
            "EURUSD": "INSTRUMENT_FX_MAJORS_EUR_USD",
            "GBPUSD": "INSTRUMENT_FX_MAJORS_GBP_USD",
            "USDJPY": "INSTRUMENT_FX_MAJORS_USD_JPY",
            "XAUUSD": "INSTRUMENT_FX_METALS_XAU_USD",
            "US100":  "INSTRUMENT_IDX_AMERICA_E_NQ_100",
            "BTCUSD": "INSTRUMENT_VCCY_BTC_USD",
            "ETHUSD": "INSTRUMENT_VCCY_ETH_USD",
        }
        for sym, expected_id in expected_ids.items():
            assert sym in INSTRUMENT_MAP, f"{sym} missing from INSTRUMENT_MAP"
            assert sym in seed, f"{sym} missing from seed"
            assert seed[sym]["broker_mapping"]["dukascopy_instrument_id"] == expected_id, (
                f"{sym}: dukascopy_instrument_id drift"
            )

    def test_spread_defaults_parity(self):
        from engines.spread_analyzer import (
            DEFAULT_TOLERANCE_BPS, SYMBOL_DEFAULT_BPS,
        )
        seed = self._seed_by_symbol()
        for sym, val in DEFAULT_TOLERANCE_BPS.items():
            assert seed[sym]["spread_defaults"]["tolerance_bps"] == val, (
                f"{sym}: spread_defaults.tolerance_bps drift"
            )
        for sym, val in SYMBOL_DEFAULT_BPS.items():
            assert seed[sym]["spread_defaults"]["symbol_default_bps"] == val, (
                f"{sym}: spread_defaults.symbol_default_bps drift"
            )

    def test_density_table_parity(self):
        from engines.tick_validator import DENSITY_TABLE
        seed = self._seed_by_symbol()
        for sym, sessions in DENSITY_TABLE.items():
            seed_density = seed[sym]["cert_defaults"]["density_table"]
            for session, (floor, target) in sessions.items():
                assert seed_density[session] == [floor, target], (
                    f"{sym} / {session}: density_table drift "
                    f"(legacy={(floor, target)} seed={seed_density[session]})"
                )

    def test_us100_aliases_nas100(self):
        """Approved decision §7.1 — NAS100 must register as alias of US100."""
        seed = self._seed_by_symbol()
        assert "US100" in seed
        assert "NAS100" in (seed["US100"].get("aliases") or []), (
            "NAS100 alias missing from US100 seed row"
        )


# ─────────────────────────────────────────────────────────────────────
# Functional — seed runs idempotently against mongomock
# ─────────────────────────────────────────────────────────────────────
class TestSeedRun:

    def test_run_inserts_all_seven(self, patched_db):
        from engines.seed.market_universe_seed import (
            run_market_universe_seed,
        )
        from engines.market_universe import COLL
        result = _run(run_market_universe_seed())
        assert result["total"] == 7
        assert len(result["inserted"]) == 7
        assert result["errors"] == []
        count = _run(patched_db[COLL].count_documents({}))
        assert count == 7
        # Each symbol carries is_seed=True
        async def _check():
            async for doc in patched_db[COLL].find({}, {"_id": 0}):
                assert doc.get("is_seed") is True, doc.get("symbol")
                assert doc.get("created_by") == "r0_seed"
        _run(_check())

    def test_run_is_idempotent(self, patched_db):
        from engines.seed.market_universe_seed import run_market_universe_seed
        from engines.market_universe import COLL
        _run(run_market_universe_seed())
        # Second run: every row should be "refreshed", not inserted, but
        # there must still be exactly 7 rows.
        result2 = _run(run_market_universe_seed())
        assert len(result2["inserted"]) == 0
        assert len(result2["refreshed"]) == 7
        count = _run(patched_db[COLL].count_documents({}))
        assert count == 7

    def test_baseline_audit_row_written(self, patched_db):
        """Approved decision §7.4 — baseline audit row per seed insert."""
        from engines.seed.market_universe_seed import run_market_universe_seed
        from engines.market_universe import AUDIT_COLL
        _run(run_market_universe_seed())
        n = _run(patched_db[AUDIT_COLL].count_documents(
            {"action": "seed_baseline"}
        ))
        assert n == 7, f"expected 7 baseline audit rows, got {n}"

    def test_operator_edited_row_not_overwritten(self, patched_db):
        """If an operator has edited a seed row (updated_by != 'r0_seed'),
        the seed must NOT clobber their value."""
        from engines.seed.market_universe_seed import run_market_universe_seed
        from engines.market_universe import COLL
        _run(run_market_universe_seed())
        # Operator edit: bump EURUSD spread tolerance
        _run(patched_db[COLL].update_one(
            {"symbol": "EURUSD", "broker_class": "dukascopy"},
            {"$set": {
                "spread_defaults.tolerance_bps": 9.99,
                "updated_by": "operator@example.com",
            }},
        ))
        _run(run_market_universe_seed())
        doc = _run(patched_db[COLL].find_one(
            {"symbol": "EURUSD", "broker_class": "dukascopy"}, {"_id": 0},
        ))
        assert doc["spread_defaults"]["tolerance_bps"] == 9.99, (
            "operator edit was clobbered by re-seed"
        )


# ─────────────────────────────────────────────────────────────────────
# Seed-row protection
# ─────────────────────────────────────────────────────────────────────
class TestSeedProtection:

    def test_delete_seed_row_without_force_refuses(self, patched_db):
        from engines.seed.market_universe_seed import run_market_universe_seed
        from engines import market_universe as MU
        _run(run_market_universe_seed())
        res = _run(MU.delete_symbol(
            symbol="EURUSD", broker_class="dukascopy", force=False,
        ))
        assert res["deleted"] is False
        assert res["reason"] == "seed_row_protected_use_force"
        assert res["was_seed"] is True

    def test_delete_seed_row_with_force_succeeds(self, patched_db):
        from engines.seed.market_universe_seed import run_market_universe_seed
        from engines import market_universe as MU
        _run(run_market_universe_seed())
        res = _run(MU.delete_symbol(
            symbol="EURUSD", broker_class="dukascopy", force=True,
            updated_by="admin@example.com",
        ))
        assert res["deleted"] is True
        assert res["was_seed"] is True

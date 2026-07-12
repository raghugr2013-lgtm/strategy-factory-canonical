"""R0 — Audit collection tests for engines.market_universe_audit."""
from __future__ import annotations

import asyncio
import sys

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
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    db = client["r0_audit_test"]

    from engines import db as db_mod
    monkeypatch.setattr(db_mod, "_db", db, raising=False)
    monkeypatch.setattr(db_mod, "_client", client, raising=False)
    monkeypatch.setattr(db_mod, "get_db", lambda: db)

    from engines import market_universe as MU
    from engines import market_universe_audit as MUA
    monkeypatch.setattr(MU, "get_db", lambda: db, raising=False)
    monkeypatch.setattr(MUA, "get_db", lambda: db, raising=False)
    from engines.seed import market_universe_seed as SEED
    monkeypatch.setattr(SEED, "get_db", lambda: db, raising=False)

    return db


class TestAuditWrites:

    def test_upsert_writes_one_audit_row(self, patched_db):
        from engines import market_universe as MU
        from engines.market_universe_audit import AUDIT_COLL
        _run(MU.upsert_symbol(
            symbol="EURUSD", broker_class="dukascopy",
            asset_class="fx_major", tier="candidate",
            updated_by="ops@example.com",
        ))
        n = _run(patched_db[AUDIT_COLL].count_documents({"symbol": "EURUSD"}))
        assert n == 1

    def test_two_upserts_write_two_audit_rows(self, patched_db):
        from engines import market_universe as MU
        from engines.market_universe_audit import AUDIT_COLL
        _run(MU.upsert_symbol(
            symbol="EURUSD", broker_class="dukascopy",
            asset_class="fx_major", tier="candidate",
            updated_by="ops@example.com",
        ))
        _run(MU.upsert_symbol(
            symbol="EURUSD", broker_class="dukascopy",
            asset_class="fx_major", tier="active",
            updated_by="ops@example.com",
        ))
        rows = _run(patched_db[AUDIT_COLL]
                    .find({"symbol": "EURUSD"}, {"_id": 0}).to_list(10))
        assert len(rows) == 2
        actions = sorted(r["action"] for r in rows)
        assert actions == ["upsert_insert", "upsert_update"]

    def test_audit_row_has_before_after_diff(self, patched_db):
        from engines import market_universe as MU
        _run(MU.upsert_symbol(
            symbol="XAUUSD", broker_class="dukascopy",
            asset_class="commodity_metal", tier="candidate", pip_size=0.1,
            updated_by="ops@example.com",
        ))
        _run(MU.set_tier(
            symbol="XAUUSD", broker_class="dukascopy",
            tier="active", updated_by="ops@example.com",
        ))
        rows = _run(MU.list_audit_for_symbol(
            symbol="XAUUSD", broker_class="dukascopy",
        ))
        # Locate by action — mongomock ts_dt ordering can be coarse for
        # writes within the same millisecond.
        tier_rows = [r for r in rows if r["action"] == "set_tier"]
        assert tier_rows, "no set_tier audit row found"
        latest = tier_rows[0]
        assert latest["before"]["tier"] == "candidate"
        assert latest["after"]["tier"] == "active"
        assert "tier" in latest["diff"]
        assert latest["diff"]["tier"] == ["candidate", "active"]

    def test_set_eligibility_writes_audit(self, patched_db):
        from engines import market_universe as MU
        _run(MU.upsert_symbol(
            symbol="EURUSD", broker_class="dukascopy",
            asset_class="fx_major", tier="candidate",
            updated_by="ops@example.com",
        ))
        _run(MU.set_eligibility(
            symbol="EURUSD",
            eligibility_patch={"live_trading_enabled": True},
            broker_class="dukascopy",
            updated_by="ops@example.com",
        ))
        rows = _run(MU.list_audit_for_symbol(
            symbol="EURUSD", broker_class="dukascopy",
        ))
        # Both rows share the same ts_dt under mongomock; locate by action.
        elig = [r for r in rows if r["action"] == "set_eligibility"]
        assert elig, "no set_eligibility audit row found"
        assert elig[0]["after"]["eligibility"]["live_trading_enabled"] is True

    def test_set_calendar_rejects_invalid_market_type(self, patched_db):
        from engines import market_universe as MU
        _run(MU.upsert_symbol(
            symbol="EURUSD", broker_class="dukascopy",
            asset_class="fx_major", updated_by="ops@example.com",
        ))
        with pytest.raises(ValueError, match="market_type"):
            _run(MU.set_calendar(
                symbol="EURUSD", broker_class="dukascopy",
                calendar_patch={"market_type": "stocks"},
                updated_by="ops@example.com",
            ))

    def test_bulk_import_returns_per_row_outcome(self, patched_db):
        from engines import market_universe as MU
        result = _run(MU.bulk_import(
            rows=[
                {"symbol": "AUDJPY", "broker_class": "dukascopy",
                 "asset_class": "fx_cross", "tier": "candidate"},
                {"symbol": "",      "broker_class": "dukascopy"},  # invalid
                {"symbol": "USDCAD", "broker_class": "dukascopy",
                 "asset_class": "fx_major", "tier": "candidate"},
            ],
            updated_by="ops@example.com",
        ))
        assert result["total"] == 3
        assert len(result["succeeded"]) == 2
        assert len(result["failed"]) == 1
        succeeded_syms = {r["symbol"] for r in result["succeeded"]}
        assert succeeded_syms == {"AUDJPY", "USDCAD"}


class TestAuditTTLIndexDeclared:
    """Verify that the TTL index spec is declared in db_indexes."""

    def test_audit_ttl_index_present_in_spec(self):
        from engines.db_indexes import TTL_SPECS
        ttl_names = [name for (coll, field, ttl_sec, name) in TTL_SPECS]
        assert "ttl_market_universe_audit" in ttl_names

    def test_audit_ttl_is_ninety_days(self):
        from engines.db_indexes import TTL_SPECS, MARKET_UNIVERSE_AUDIT_TTL_DAYS
        assert MARKET_UNIVERSE_AUDIT_TTL_DAYS == 90
        for coll, field, ttl_sec, name in TTL_SPECS:
            if name == "ttl_market_universe_audit":
                assert coll == "market_universe_audit"
                assert field == "ts_dt"
                assert ttl_sec == 90 * 86400


class TestEligibilityDefaults:

    def test_default_eligibility_shape(self):
        from engines.market_universe import (
            DEFAULT_ELIGIBILITY, ELIGIBILITY_KEYS,
        )
        for k in ELIGIBILITY_KEYS:
            assert k in DEFAULT_ELIGIBILITY
        assert DEFAULT_ELIGIBILITY["ingestion_enabled"] is True
        assert DEFAULT_ELIGIBILITY["live_trading_enabled"] is False

    def test_normalize_eligibility_drops_unknown_keys(self):
        from engines.market_universe import normalize_eligibility
        out = normalize_eligibility(
            {"discovery_enabled": True, "bogus_key": True}
        )
        assert out["discovery_enabled"] is True
        assert "bogus_key" not in out


class TestFlagStillOff:
    """The R0 contract: ENABLE_DYNAMIC_MARKET_UNIVERSE remains OFF
    by default after R0. Consuming engines must still see is_enabled()
    == False."""

    def test_flag_default_off(self, monkeypatch):
        from engines import market_universe as MU
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        assert MU.is_enabled() is False

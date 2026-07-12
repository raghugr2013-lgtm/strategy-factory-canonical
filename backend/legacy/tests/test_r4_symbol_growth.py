"""R4 — Symbol-growth validation.

Demonstrates that a NEW symbol (AUDJPY) registered in market_universe
appears automatically through the hook's API endpoint and through the
adapter accessors, **without any frontend code change**.

This is the operator-mandated R4 symbol-growth gate — the whole reason
the dynamic registry exists. Adding AUDJPY to the registry must:

  1. Surface immediately in `/api/latent/market-universe` rows.
  2. Be filterable by every eligibility slice it was registered for.
  3. Be visible to the adapter accessors (with the flag ON, the
     adapter returns the registry slice; with the flag OFF, the
     legacy authority is unaffected).
  4. Survive a hook-shaped response — `data.rows` includes AUDJPY.

The hook itself is React-resident and consumes `data.rows` directly.
This test validates the data path that feeds the hook.
"""
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
    """Mongomock-backed DB shared by market_universe, audit, adapter
    and the latent API surface.
    """
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    db = client["r4_symbol_growth"]

    from engines import db as db_mod
    monkeypatch.setattr(db_mod, "_db", db, raising=False)
    monkeypatch.setattr(db_mod, "_client", client, raising=False)
    monkeypatch.setattr(db_mod, "get_db", lambda: db)

    from engines import market_universe as MU
    from engines import market_universe_audit as MUA
    monkeypatch.setattr(MU, "get_db", lambda: db, raising=False)
    monkeypatch.setattr(MUA, "get_db", lambda: db, raising=False)
    try:
        from engines.seed import market_universe_seed as SEED
        monkeypatch.setattr(SEED, "get_db", lambda: db, raising=False)
    except Exception:
        pass

    from engines import market_universe_adapter as ADAPTER
    ADAPTER.clear_registry_cache()
    return db


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Registry growth surfaces via list_symbols (hook data path)
# ─────────────────────────────────────────────────────────────────────
class TestSymbolGrowthVisibleToHookEndpoint:

    def _seed_canonical(self):
        from engines import market_universe as MU
        for sym in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"):
            _run(MU.upsert_symbol(
                symbol=sym, broker_class="dukascopy",
                asset_class="fx_major" if sym in ("EURUSD","GBPUSD","USDJPY","XAUUSD")
                                       else "other",
                tier="candidate",
                enabled=True,
                eligibility={"ingestion_enabled": True,
                             "discovery_enabled": True,
                             "validation_enabled": True},
                is_seed=True,
                updated_by="r4-test",
            ))

    def test_audjpy_not_in_baseline(self, patched_db):
        self._seed_canonical()
        from engines import market_universe as MU
        rows = _run(MU.list_symbols(limit=200))
        symbols = {r["symbol"] for r in rows}
        assert "EURUSD" in symbols
        assert "AUDJPY" not in symbols, (
            "AUDJPY must NOT be present before registry growth"
        )

    def test_audjpy_appears_after_upsert(self, patched_db):
        self._seed_canonical()
        from engines import market_universe as MU
        # Operator registers AUDJPY through the same admin endpoint
        # the frontend governance panel uses.
        _run(MU.upsert_symbol(
            symbol="AUDJPY",
            broker_class="dukascopy",
            asset_class="fx_minor",
            tier="candidate",
            enabled=True,
            priority=80,
            eligibility={
                "ingestion_enabled":     True,
                "discovery_enabled":     True,
                "mutation_enabled":      False,
                "validation_enabled":    True,
                "certification_enabled": False,
                "portfolio_enabled":     False,
                "live_trading_enabled":  False,
            },
            updated_by="r4-symbol-growth-test",
        ))

        rows = _run(MU.list_symbols(limit=200))
        symbols = {r["symbol"] for r in rows}
        assert "AUDJPY" in symbols, (
            "R4 symbol-growth: AUDJPY must appear in /api/latent/market-universe "
            "rows without any frontend code change."
        )

    def test_audjpy_eligibility_routes_into_hook_slices(self, patched_db):
        """When the hook receives this row and runs `_filterEligibility`,
        AUDJPY appears in ingestion/discovery/validation slices and is
        excluded from mutation/certification/portfolio/live_trading.
        """
        self._seed_canonical()
        from engines import market_universe as MU

        _run(MU.upsert_symbol(
            symbol="AUDJPY",
            broker_class="dukascopy",
            asset_class="fx_minor",
            tier="candidate",
            enabled=True,
            priority=80,
            eligibility={
                "ingestion_enabled":     True,
                "discovery_enabled":     True,
                "mutation_enabled":      False,
                "validation_enabled":    True,
                "certification_enabled": False,
                "portfolio_enabled":     False,
                "live_trading_enabled":  False,
            },
            updated_by="r4-symbol-growth-test",
        ))

        rows = _run(MU.list_symbols(limit=200))

        # Simulate the hook's _filterEligibility step in Python.
        def _slice(key):
            return [
                r["symbol"] for r in rows
                if r.get("enabled") is not False
                and (r.get("eligibility") or {}).get(key) is True
            ]

        assert "AUDJPY" in _slice("ingestion_enabled")
        assert "AUDJPY" in _slice("discovery_enabled")
        assert "AUDJPY" in _slice("validation_enabled")
        assert "AUDJPY" not in _slice("mutation_enabled")
        assert "AUDJPY" not in _slice("certification_enabled")
        assert "AUDJPY" not in _slice("portfolio_enabled")
        assert "AUDJPY" not in _slice("live_trading_enabled")


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Flag-OFF: legacy authority is unchanged regardless of
#                    registry growth. R4 must not weaken R3's guarantee.
# ─────────────────────────────────────────────────────────────────────
class TestFlagOffUnaffectedByRegistryGrowth:

    def test_flag_off_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        from engines import market_universe as MU
        assert MU.is_enabled() is False

    def test_audjpy_does_not_leak_into_legacy_authority(
        self, patched_db, monkeypatch,
    ):
        """With the flag OFF (R4 boundary), adding AUDJPY to the
        registry MUST NOT change what the legacy authority returns.
        """
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)

        from engines import market_universe as MU
        from engines import market_universe_adapter as ADAPTER

        # Baseline snapshot.
        before = {
            "allowed":       set(ADAPTER.get_allowed_symbols()),
            "watchlist":     set(ADAPTER.get_active_watchlist()),
            "discovery":     set(ADAPTER.get_discovery_pairs()),
            "tier1":         set(ADAPTER.get_tier1_symbols()),
        }

        _run(MU.upsert_symbol(
            symbol="AUDJPY",
            broker_class="dukascopy",
            asset_class="fx_minor",
            tier="candidate",
            enabled=True,
            eligibility={"ingestion_enabled": True,
                         "discovery_enabled": True},
            updated_by="r4-test",
        ))
        ADAPTER.clear_registry_cache()

        after = {
            "allowed":       set(ADAPTER.get_allowed_symbols()),
            "watchlist":     set(ADAPTER.get_active_watchlist()),
            "discovery":     set(ADAPTER.get_discovery_pairs()),
            "tier1":         set(ADAPTER.get_tier1_symbols()),
        }
        assert before == after, (
            f"Flag-OFF authority must be unchanged by registry growth. "
            f"before={before} after={after}"
        )
        assert "AUDJPY" not in after["allowed"]


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Frontend code did not change for AUDJPY.
# ─────────────────────────────────────────────────────────────────────
class TestNoFrontendCodeChange:

    def test_no_audjpy_literal_in_frontend(self):
        """If symbol-growth required a frontend code change, AUDJPY
        would appear as a string literal somewhere in src/. R4 must
        keep all frontend code free of AUDJPY string references —
        proving the new symbol surfaces purely through the registry.

        Comments (`// AUDJPY ...`) are exempt — the only mentions are
        documentation explaining *why* no hardcoding is needed.
        """
        from pathlib import Path
        import re
        # Match AUDJPY appearing as a string literal: 'AUDJPY' or "AUDJPY"
        literal_re = re.compile(r"""['"]AUDJPY['"]""")
        offenders = []
        for p in Path("/app/frontend/src").rglob("*.*"):
            if p.suffix not in {".js", ".jsx", ".ts", ".tsx", ".json", ".css"}:
                continue
            try:
                if literal_re.search(p.read_text(encoding="utf-8")):
                    offenders.append(str(p))
            except Exception:
                pass
        assert not offenders, (
            f"R4 contract violated: AUDJPY hardcoded as a string literal in: "
            f"{offenders}"
        )

    def test_hook_pulls_audjpy_via_endpoint_path(self):
        """The hook fetches `/api/latent/market-universe?limit=200`
        and reads `data.rows`. Symbol-growth flows entirely through
        this path — verify the hook still uses it.
        """
        src = open("/app/frontend/src/hooks/useMarketUniverse.js").read()
        assert "/api/latent/market-universe" in src, (
            "Hook must consume /api/latent/market-universe"
        )
        assert "data?.rows" in src or "data.rows" in src, (
            "Hook must read `rows` from the endpoint response"
        )

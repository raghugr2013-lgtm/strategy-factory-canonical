"""R3 — Eligibility-level parity verification (operator-mandated gate).

For each canonical symbol, verify that the adapter's eligibility-set
accessors and per-symbol predicate produce results identical to the
legacy authority under all three flag states:

    (A) Flag OFF
    (B) Flag ON + empty cache
    (C) Flag ON + R0 seed cache

Eligibility dimensions covered:

    * discovery        (auto_factory / gem_factory default pairs)
    * mutation         (mutation default pair set)
    * validation       (validation default pair set; = readiness watchlist)
    * portfolio        (portfolio builder default pair set)
    * certification    (BI5 cert default pair set; = intelligence pairs)
    * readiness        (watchlist + tier1)
    * data-api allowed (/api/data* validators)
    * data-maintenance (unattended maintenance default)
    * intelligence     (market_intelligence digest default)
"""
from __future__ import annotations

import sys
import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


CANONICAL_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"]


@pytest.fixture(autouse=True)
def _flag_off_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
    from engines import market_universe_adapter as ADAPTER
    ADAPTER.clear_registry_cache()
    yield
    ADAPTER.clear_registry_cache()


# ═════════════════════════════════════════════════════════════════════
# Tier 1 — Flag OFF: adapter == legacy authority
# ═════════════════════════════════════════════════════════════════════
class TestFlagOff_EligibilitySets:

    def test_watchlist_matches_legacy(self):
        from engines.readiness_engine import WATCHLIST
        from engines.market_universe_adapter import get_active_watchlist
        assert get_active_watchlist() == list(WATCHLIST)

    def test_tier1_matches_legacy(self):
        from engines.readiness_engine import TIER1_SYMBOLS
        from engines.market_universe_adapter import get_tier1_symbols
        assert get_tier1_symbols() == list(TIER1_SYMBOLS)

    def test_intelligence_pairs_matches_legacy(self):
        from engines.market_intelligence import DEFAULT_PAIRS
        from engines.market_universe_adapter import get_intelligence_pairs
        assert get_intelligence_pairs() == list(DEFAULT_PAIRS)

    def test_allowed_symbols_matches_legacy(self):
        from api.data import ALLOWED_SYMBOLS
        from engines.market_universe_adapter import get_allowed_symbols
        assert get_allowed_symbols() == list(ALLOWED_SYMBOLS)

    def test_data_maintenance_pairs_matches_legacy(self):
        from data_engine.data_maintenance import DEFAULT_PAIRS
        from engines.market_universe_adapter import get_data_maintenance_pairs
        assert get_data_maintenance_pairs() == list(DEFAULT_PAIRS)

    def test_discovery_pairs_matches_legacy(self):
        from engines.auto_factory_engine import DEFAULT_PAIRS as FACT_PAIRS
        from engines.market_universe_adapter import get_discovery_pairs
        assert get_discovery_pairs() == list(FACT_PAIRS)

    def test_mutation_pairs_matches_legacy(self):
        from engines.auto_factory_engine import DEFAULT_PAIRS as FACT_PAIRS
        from engines.market_universe_adapter import get_mutation_pairs
        assert get_mutation_pairs() == list(FACT_PAIRS)

    def test_validation_pairs_matches_legacy(self):
        from engines.readiness_engine import WATCHLIST
        from engines.market_universe_adapter import get_validation_pairs
        assert get_validation_pairs() == list(WATCHLIST)

    def test_portfolio_pairs_matches_legacy(self):
        from data_engine.data_maintenance import DEFAULT_PAIRS as DM_PAIRS
        from engines.market_universe_adapter import get_portfolio_pairs
        assert get_portfolio_pairs() == list(DM_PAIRS)

    def test_certification_pairs_matches_legacy(self):
        from engines.market_intelligence import DEFAULT_PAIRS as MI_PAIRS
        from engines.market_universe_adapter import get_certification_pairs
        assert get_certification_pairs() == list(MI_PAIRS)


# ═════════════════════════════════════════════════════════════════════
# Tier 2 — Per-symbol predicate parity (flag OFF)
# ═════════════════════════════════════════════════════════════════════
class TestFlagOff_PerSymbolPredicate:
    """is_eligible(symbol, capability=...) under flag OFF should
    answer based on whether the symbol appears in the legacy default
    set for that capability."""

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_ingestion_eligibility(self, symbol):
        from api.data import ALLOWED_SYMBOLS
        from engines.market_universe_adapter import is_eligible
        expected = symbol in ALLOWED_SYMBOLS
        assert is_eligible(symbol, capability="ingestion") == expected
        # Suffix-tolerant form:
        assert is_eligible(symbol, capability="ingestion_enabled") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_validation_eligibility(self, symbol):
        from engines.readiness_engine import WATCHLIST
        from engines.market_universe_adapter import is_eligible
        expected = symbol in WATCHLIST
        assert is_eligible(symbol, capability="validation") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_discovery_eligibility(self, symbol):
        from engines.auto_factory_engine import DEFAULT_PAIRS
        from engines.market_universe_adapter import is_eligible
        expected = symbol in DEFAULT_PAIRS
        assert is_eligible(symbol, capability="discovery") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_mutation_eligibility(self, symbol):
        from engines.auto_factory_engine import DEFAULT_PAIRS
        from engines.market_universe_adapter import is_eligible
        expected = symbol in DEFAULT_PAIRS
        assert is_eligible(symbol, capability="mutation") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_portfolio_eligibility(self, symbol):
        from data_engine.data_maintenance import DEFAULT_PAIRS
        from engines.market_universe_adapter import is_eligible
        expected = symbol in DEFAULT_PAIRS
        assert is_eligible(symbol, capability="portfolio") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_certification_eligibility(self, symbol):
        from engines.market_intelligence import DEFAULT_PAIRS
        from engines.market_universe_adapter import is_eligible
        expected = symbol in DEFAULT_PAIRS
        assert is_eligible(symbol, capability="certification") == expected

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_live_trading_disabled_by_default(self, symbol):
        from engines.market_universe_adapter import is_eligible
        # Legacy has no concept of live_trading_enabled; default False.
        assert is_eligible(symbol, capability="live_trading") is False


# ═════════════════════════════════════════════════════════════════════
# Tier 3 — Flag ON, empty cache: fall-through to legacy
# ═════════════════════════════════════════════════════════════════════
class TestFlagOn_EmptyCache_Eligibility:

    @pytest.fixture
    def flag_on(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "true")
        from engines import market_universe_adapter as ADAPTER
        ADAPTER.clear_registry_cache()
        yield
        ADAPTER.clear_registry_cache()
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)

    def test_watchlist_falls_back(self, flag_on):
        from engines.readiness_engine import WATCHLIST
        from engines.market_universe_adapter import get_active_watchlist
        assert get_active_watchlist() == list(WATCHLIST)

    def test_tier1_falls_back(self, flag_on):
        from engines.readiness_engine import TIER1_SYMBOLS
        from engines.market_universe_adapter import get_tier1_symbols
        assert get_tier1_symbols() == list(TIER1_SYMBOLS)

    def test_intelligence_falls_back(self, flag_on):
        from engines.market_intelligence import DEFAULT_PAIRS
        from engines.market_universe_adapter import get_intelligence_pairs
        assert get_intelligence_pairs() == list(DEFAULT_PAIRS)

    def test_allowed_falls_back(self, flag_on):
        from api.data import ALLOWED_SYMBOLS
        from engines.market_universe_adapter import get_allowed_symbols
        assert get_allowed_symbols() == list(ALLOWED_SYMBOLS)

    def test_data_maintenance_falls_back(self, flag_on):
        from data_engine.data_maintenance import DEFAULT_PAIRS
        from engines.market_universe_adapter import get_data_maintenance_pairs
        assert get_data_maintenance_pairs() == list(DEFAULT_PAIRS)

    def test_discovery_falls_back(self, flag_on):
        from engines.auto_factory_engine import DEFAULT_PAIRS
        from engines.market_universe_adapter import get_discovery_pairs
        assert get_discovery_pairs() == list(DEFAULT_PAIRS)


# ═════════════════════════════════════════════════════════════════════
# Tier 4 — Flag ON, R0 seed cache populated
# ═════════════════════════════════════════════════════════════════════
class TestFlagOn_SeedCache_Eligibility:
    """With the R0 seed cache populated, each adapter accessor returns
    a registry slice. The slice contents must be consistent with the
    seed's per-symbol eligibility flags."""

    @pytest.fixture
    def flag_on_with_seed(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "true")
        from engines import market_universe_adapter as ADAPTER
        from engines.seed.market_universe_seed import SEED_SYMBOLS
        ADAPTER.clear_registry_cache()
        ADAPTER.set_registry_cache(list(SEED_SYMBOLS))
        yield ADAPTER
        ADAPTER.clear_registry_cache()
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)

    def _expected_with_capability(self, capability: str):
        """Independent re-derivation from the seed payload — no
        adapter call. Returns the set sorted by priority DESC."""
        from engines.seed.market_universe_seed import SEED_SYMBOLS
        if not capability.endswith("_enabled"):
            capability = f"{capability}_enabled"
        rows = [r for r in SEED_SYMBOLS
                if bool((r.get("eligibility") or {}).get(capability))
                and bool(r.get("enabled", True))]
        rows.sort(key=lambda r: (-int(r.get("priority", 0)), r.get("symbol", "")))
        return [r["symbol"] for r in rows]

    def test_ingestion_set_matches_seed(self, flag_on_with_seed):
        # All 7 seed rows have ingestion_enabled=True → full set.
        got = flag_on_with_seed.get_active_watchlist()
        assert got == self._expected_with_capability("ingestion")

    def test_validation_set_matches_seed(self, flag_on_with_seed):
        got = flag_on_with_seed.get_validation_pairs()
        assert got == self._expected_with_capability("validation")

    def test_discovery_set_matches_seed(self, flag_on_with_seed):
        # Per R0 seed: EURUSD/GBPUSD/USDJPY/XAUUSD have discovery=True;
        # US100/BTC/ETH have discovery=False.
        got = flag_on_with_seed.get_discovery_pairs()
        assert got == self._expected_with_capability("discovery")
        # Spot-check the contents
        assert "US100" not in got
        assert "BTCUSD" not in got
        assert "EURUSD" in got
        assert "XAUUSD" in got

    def test_mutation_set_matches_seed(self, flag_on_with_seed):
        got = flag_on_with_seed.get_mutation_pairs()
        assert got == self._expected_with_capability("mutation")
        # Per R0: USDJPY has mutation_enabled=False
        assert "USDJPY" not in got
        assert "EURUSD" in got

    def test_portfolio_set_matches_seed(self, flag_on_with_seed):
        got = flag_on_with_seed.get_portfolio_pairs()
        assert got == self._expected_with_capability("portfolio")
        # R5 Phase-2 prep (D5 PRESERVE-LEGACY, 2026-06-04): USDJPY is
        # now portfolio-eligible again (preserves legacy parity with
        # `data_maintenance.DEFAULT_PAIRS`). US100/BTC/ETH remain
        # excluded from the portfolio set per the original R0 seed.
        assert "USDJPY" in got
        assert "US100" not in got
        assert "BTCUSD" not in got
        # EURUSD, GBPUSD, XAUUSD ARE
        assert "EURUSD" in got
        assert "GBPUSD" in got
        assert "XAUUSD" in got

    def test_certification_set_matches_seed(self, flag_on_with_seed):
        got = flag_on_with_seed.get_certification_pairs()
        assert got == self._expected_with_capability("certification")

    def test_tier1_matches_seed(self, flag_on_with_seed):
        """Seed has all rows at tier='candidate' — none at 'active' —
        so the registry slice is empty, and the adapter falls back to
        the legacy TIER1_SYMBOLS tuple."""
        from engines.readiness_engine import TIER1_SYMBOLS
        got = flag_on_with_seed.get_tier1_symbols()
        assert got == list(TIER1_SYMBOLS)

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_is_eligible_predicate_via_cache(
        self, flag_on_with_seed, symbol,
    ):
        """The per-symbol predicate must answer based on the seed row's
        actual eligibility map, not the legacy fall-through."""
        from engines.seed.market_universe_seed import SEED_SYMBOLS
        seed_map = {r["symbol"]: r for r in SEED_SYMBOLS}
        elig = seed_map[symbol]["eligibility"]
        for cap in (
            "ingestion_enabled", "validation_enabled",
            "discovery_enabled", "mutation_enabled",
            "certification_enabled", "portfolio_enabled",
            "live_trading_enabled",
        ):
            assert flag_on_with_seed.is_eligible(
                symbol, capability=cap,
            ) is bool(elig[cap]), (
                f"{symbol}/{cap}: predicate drift from seed"
            )

    def test_nas100_alias_eligibility_via_cache(self, flag_on_with_seed):
        # NAS100 → US100 (alias). Both must report identical eligibility.
        for cap in ("ingestion", "validation", "discovery", "mutation",
                    "certification", "portfolio", "live_trading"):
            us = flag_on_with_seed.is_eligible("US100", capability=cap)
            nas = flag_on_with_seed.is_eligible("NAS100", capability=cap)
            assert us == nas, f"NAS100 vs US100 eligibility mismatch on {cap}"


# ═════════════════════════════════════════════════════════════════════
# Tier 5 — Legacy engine behaviour preserved
# ═════════════════════════════════════════════════════════════════════
class TestLegacyBehaviourPreserved:
    """The 5 engines that R3 routes through the adapter must continue
    to return the same default values under flag OFF."""

    def test_readiness_watchlist_helper_returns_legacy_tuple(self):
        from engines.readiness_engine import _watchlist, WATCHLIST
        assert _watchlist() == WATCHLIST

    def test_readiness_tier1_helper_returns_legacy_tuple(self):
        from engines.readiness_engine import _tier1_symbols, TIER1_SYMBOLS
        assert _tier1_symbols() == TIER1_SYMBOLS

    def test_api_data_allowed_helper_returns_legacy_list(self):
        from api.data import _allowed_symbols, ALLOWED_SYMBOLS
        assert _allowed_symbols() == list(ALLOWED_SYMBOLS)

    def test_legacy_module_constants_unchanged(self):
        """The original module-level constants must STILL exist with
        the original values. Rollback safety."""
        from engines.readiness_engine import WATCHLIST, TIER1_SYMBOLS
        from engines.market_intelligence import DEFAULT_PAIRS as MI_PAIRS
        from engines.auto_factory_engine import DEFAULT_PAIRS as AF_PAIRS
        from data_engine.data_maintenance import DEFAULT_PAIRS as DM_PAIRS
        from api.data import ALLOWED_SYMBOLS
        assert TIER1_SYMBOLS == ("EURUSD", "GBPUSD")
        assert WATCHLIST == ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
                             "US100", "BTCUSD", "ETHUSD")
        assert MI_PAIRS == ["EURUSD", "GBPUSD", "XAUUSD"]
        assert AF_PAIRS == ["EURUSD", "GBPUSD", "XAUUSD"]
        assert DM_PAIRS == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        assert ALLOWED_SYMBOLS == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD",
                                   "US100", "BTCUSD", "ETHUSD"]


# ═════════════════════════════════════════════════════════════════════
# Tier 6 — Flag-state contract
# ═════════════════════════════════════════════════════════════════════
class TestFlagStateContract_R3:

    def test_flag_default_off(self):
        from engines.market_universe_adapter import is_flag_on
        assert is_flag_on() is False

    def test_unknown_capability_returns_false(self):
        from engines.market_universe_adapter import is_eligible
        assert is_eligible("EURUSD", capability="quantum_supremacy_enabled") is False
        assert is_eligible("EURUSD", capability="") is False

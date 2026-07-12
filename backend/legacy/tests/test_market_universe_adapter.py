"""R1 — Adapter parity verification (the operator-mandated gate).

For every canonical symbol, this test asserts:

    legacy_source(symbol)  ≡  adapter(symbol)

for:

    * symbol mapping        (config/symbols.SYMBOL_CONFIG)
    * BI5 mapping           (config/bi5_symbols._BI5_SYMBOL_SPECS)
    * instrument mapping    (data_engine/dukascopy_downloader.INSTRUMENT_MAP)
    * precision              (price_multiplier, quote_decimals)
    * pip size               (derived; from BI5 spec where applicable)
    * alias resolution       (NAS100 → US100, GOLD → XAUUSD)

The adapter must be behaviour-identical while the flag remains OFF.
This is the byte-parity contract that lets R5 flip safely later.

The tests run in both flag states:
    1. Flag OFF → adapter falls back to legacy values everywhere.
    2. Flag ON  → cache empty → adapter still falls back to legacy
                  values everywhere (registry-miss path).
    3. Flag ON  → cache pre-populated with the R0 seed payload →
                  adapter returns registry values; we verify those
                  match legacy.
"""
from __future__ import annotations

import sys

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ─────────────────────────────────────────────────────────────────────
# Canonical symbol set under verification.
# (Same 7 as the R0 seed.)
# ─────────────────────────────────────────────────────────────────────
CANONICAL_SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"]


@pytest.fixture(autouse=True)
def _flag_off_default(monkeypatch):
    """Default contract: flag is OFF. Individual tests may flip it on
    via their own monkeypatch fixture."""
    monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
    # Clear the adapter cache between tests so state doesn't leak.
    from engines import market_universe_adapter as ADAPTER
    ADAPTER.clear_registry_cache()
    yield
    ADAPTER.clear_registry_cache()


# ═════════════════════════════════════════════════════════════════════
# Tier 1 — Flag OFF parity (the day-1 contract)
# ═════════════════════════════════════════════════════════════════════
class TestFlagOff_SymbolMapping:

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_calendar_byte_identical_to_legacy(self, symbol):
        from config.symbols import SYMBOL_CONFIG
        from engines.market_universe_adapter import get_calendar
        legacy = SYMBOL_CONFIG[symbol]
        out = get_calendar(symbol)
        assert out["market_type"] == legacy["market_type"], (
            f"{symbol}: calendar.market_type drift"
        )
        assert out["timezone"] == legacy["timezone"], (
            f"{symbol}: calendar.timezone drift"
        )

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_get_market_type_byte_identical(self, symbol):
        from config.symbols import SYMBOL_CONFIG, get_market_type
        legacy_str = SYMBOL_CONFIG[symbol]["market_type"]
        from_func  = get_market_type(symbol)
        assert from_func == legacy_str

    def test_unknown_symbol_falls_back_to_default(self):
        from engines.market_universe_adapter import get_calendar
        out = get_calendar("XXXYYY")
        assert out == {"market_type": "forex", "timezone": "UTC"}


class TestFlagOff_BI5Mapping:

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_bi5_spec_identical_to_legacy(self, symbol):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        from engines.market_universe_adapter import get_bi5_symbol_spec
        legacy = _BI5_SYMBOL_SPECS[symbol]
        out = get_bi5_symbol_spec(symbol)
        # Identity on the frozen dataclass — same object actually.
        assert out == legacy, f"{symbol}: BI5 spec drift"
        assert out.url_slug == legacy.url_slug
        assert out.price_multiplier == legacy.price_multiplier
        assert out.quote_decimals == legacy.quote_decimals
        assert out.market_type == legacy.market_type

    def test_bi5_spec_unknown_raises_keyerror(self):
        from engines.market_universe_adapter import get_bi5_symbol_spec
        with pytest.raises(KeyError, match="BI5 spec not registered"):
            get_bi5_symbol_spec("XXXYYY")

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_is_bi5_supported(self, symbol):
        from engines.market_universe_adapter import is_bi5_supported
        assert is_bi5_supported(symbol) is True

    def test_list_bi5_symbols_flag_off_equals_legacy(self):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        from engines.market_universe_adapter import list_bi5_symbols
        assert list_bi5_symbols() == sorted(_BI5_SYMBOL_SPECS)


class TestFlagOff_InstrumentMapping:

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_resolve_dukascopy_instrument_identical_to_legacy(self, symbol):
        from data_engine.dukascopy_downloader import INSTRUMENT_MAP
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        legacy = INSTRUMENT_MAP[symbol]
        out = resolve_dukascopy_instrument(symbol)
        # Identity check: must be the SAME SDK enum object.
        assert out is legacy, f"{symbol}: SDK enum identity drift"

    def test_resolve_unknown_returns_none(self):
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        assert resolve_dukascopy_instrument("XXXYYY") is None


class TestFlagOff_Precision:

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_price_multiplier_identical(self, symbol):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        from engines.market_universe_adapter import get_bi5_symbol_spec
        assert get_bi5_symbol_spec(symbol).price_multiplier == \
               _BI5_SYMBOL_SPECS[symbol].price_multiplier

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_quote_decimals_identical(self, symbol):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        from engines.market_universe_adapter import get_bi5_symbol_spec
        assert get_bi5_symbol_spec(symbol).quote_decimals == \
               _BI5_SYMBOL_SPECS[symbol].quote_decimals


class TestFlagOff_PipSize:
    """Pip-size resolution authority today is ``engines.cbot_trade_parity.
    resolve_pip_size`` — a substring matcher: JPY→0.01, XAU→0.1, XAG→0.001,
    everything else→0.0001. R1 does NOT promote this surface to the
    adapter (that is R2 scope), so the parity contract here is simply:
    legacy resolver behaviour MUST NOT drift while R1 is in flight.

    The R0 registry payload stores more accurate pip sizes for indices
    and crypto (0.01) but they are NOT yet consulted at runtime — they
    will be in R2 when the substring resolver is replaced by an
    adapter call.
    """

    LEGACY_PIP_SIZE = {
        # Substring rules: JPY → 0.01, XAU → 0.1
        "EURUSD": 0.0001,
        "GBPUSD": 0.0001,
        "USDJPY": 0.01,
        "XAUUSD": 0.1,
        # Index + crypto fall through to the 0.0001 default in legacy.
        "US100":  0.0001,
        "BTCUSD": 0.0001,
        "ETHUSD": 0.0001,
    }

    @pytest.mark.parametrize("symbol,pip", LEGACY_PIP_SIZE.items())
    def test_legacy_pip_size_unchanged_by_r1(self, symbol, pip):
        """The legacy substring resolver MUST still produce the same
        value at the end of R1 as at the start of R1. This is the
        regression guard that protects P0B until R2 ships."""
        from engines.cbot_trade_parity import resolve_pip_size
        assert resolve_pip_size(symbol) == pip, (
            f"{symbol}: legacy pip-size resolver drifted in R1"
        )


# ═════════════════════════════════════════════════════════════════════
# Tier 2 — Alias resolution (always-on; SAME in both flag states)
# ═════════════════════════════════════════════════════════════════════
class TestAliasResolution:

    def test_nas100_resolves_to_us100(self):
        from engines.market_universe_adapter import resolve_alias
        assert resolve_alias("NAS100") == "US100"
        assert resolve_alias("nas100") == "US100"
        assert resolve_alias("Nas 100") == "US100"

    def test_gold_resolves_to_xauusd(self):
        from engines.market_universe_adapter import resolve_alias
        assert resolve_alias("GOLD") == "XAUUSD"
        assert resolve_alias("Gold") == "XAUUSD"

    def test_canonical_symbol_resolves_to_itself(self):
        from engines.market_universe_adapter import resolve_alias
        for sym in CANONICAL_SYMBOLS:
            assert resolve_alias(sym) == sym

    def test_unknown_passes_through(self):
        from engines.market_universe_adapter import resolve_alias
        assert resolve_alias("EURGBP") == "EURGBP"

    def test_alias_resolution_in_bi5_spec(self):
        """Even with the flag OFF, the adapter resolves aliases BEFORE
        dispatching to the legacy table. NAS100 must therefore behave
        as US100 in the BI5 lookup."""
        from engines.market_universe_adapter import get_bi5_symbol_spec
        # US100 is registered in the legacy BI5 table; NAS100 is not.
        # Resolution lets the adapter answer NAS100 correctly.
        us100 = get_bi5_symbol_spec("US100")
        # NAS100 → US100; the adapter delegates to the US100 spec
        # because alias resolution runs first.
        nas100 = get_bi5_symbol_spec("NAS100")
        assert nas100 == us100

    def test_alias_resolution_in_dukascopy_instrument(self):
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        us100 = resolve_dukascopy_instrument("US100")
        nas100 = resolve_dukascopy_instrument("NAS100")
        assert us100 is not None
        assert nas100 is us100, "NAS100 must resolve to US100's instrument"

    def test_alias_resolution_for_gold(self):
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        xau = resolve_dukascopy_instrument("XAUUSD")
        gold = resolve_dukascopy_instrument("GOLD")
        assert gold is xau


# ═════════════════════════════════════════════════════════════════════
# Tier 3 — Flag ON, empty cache: same fall-through as flag OFF
# ═════════════════════════════════════════════════════════════════════
class TestFlagOn_EmptyCache:

    @pytest.fixture
    def flag_on(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "true")
        from engines import market_universe_adapter as ADAPTER
        ADAPTER.clear_registry_cache()
        yield
        ADAPTER.clear_registry_cache()
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_calendar_falls_back_to_legacy(self, flag_on, symbol):
        from config.symbols import SYMBOL_CONFIG
        from engines.market_universe_adapter import get_calendar
        assert get_calendar(symbol) == SYMBOL_CONFIG[symbol]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_bi5_spec_falls_back_to_legacy(self, flag_on, symbol):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        from engines.market_universe_adapter import get_bi5_symbol_spec
        assert get_bi5_symbol_spec(symbol) == _BI5_SYMBOL_SPECS[symbol]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_instrument_falls_back_to_legacy(self, flag_on, symbol):
        from data_engine.dukascopy_downloader import INSTRUMENT_MAP
        from engines.market_universe_adapter import resolve_dukascopy_instrument
        assert resolve_dukascopy_instrument(symbol) is INSTRUMENT_MAP[symbol]


# ═════════════════════════════════════════════════════════════════════
# Tier 4 — Flag ON, cache populated from R0 seed payload
# ═════════════════════════════════════════════════════════════════════
class TestFlagOn_SeedCache:
    """Mirror R5 behaviour: cache populated from the R0 seed payload.
    Adapter outputs must still equal the legacy values byte-for-byte.
    This is the lock that lets R5 flip safely later."""

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

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_calendar_byte_identical_to_legacy(
        self, flag_on_with_seed, symbol,
    ):
        from config.symbols import SYMBOL_CONFIG
        out = flag_on_with_seed.get_calendar(symbol)
        assert out["market_type"] == SYMBOL_CONFIG[symbol]["market_type"]
        assert out["timezone"] == SYMBOL_CONFIG[symbol]["timezone"]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_bi5_spec_byte_identical_to_legacy(
        self, flag_on_with_seed, symbol,
    ):
        from config.bi5_symbols import _BI5_SYMBOL_SPECS
        legacy = _BI5_SYMBOL_SPECS[symbol]
        out = flag_on_with_seed.get_bi5_symbol_spec(symbol)
        assert out.url_slug == legacy.url_slug, f"{symbol}: url_slug drift"
        assert out.price_multiplier == legacy.price_multiplier, (
            f"{symbol}: price_multiplier drift"
        )
        assert out.quote_decimals == legacy.quote_decimals, (
            f"{symbol}: quote_decimals drift"
        )
        assert out.market_type == legacy.market_type, (
            f"{symbol}: market_type drift"
        )

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_dukascopy_instrument_byte_identical(
        self, flag_on_with_seed, symbol,
    ):
        from data_engine.dukascopy_downloader import INSTRUMENT_MAP
        legacy = INSTRUMENT_MAP[symbol]
        out = flag_on_with_seed.resolve_dukascopy_instrument(symbol)
        # The cache stores the SDK enum *name* — the adapter must
        # resolve it back to the actual enum object via the SDK.
        # The identity must match the legacy import.
        assert out is legacy, (
            f"{symbol}: SDK enum identity drift after registry hit "
            f"(adapter returned {out!r})"
        )

    def test_alias_nas100_via_cache_resolves_to_us100(
        self, flag_on_with_seed,
    ):
        # The seed registers NAS100 as alias of US100. With the flag
        # on and cache populated, NAS100 must produce the SAME row as
        # US100.
        us100 = flag_on_with_seed.get_bi5_symbol_spec("US100")
        nas100 = flag_on_with_seed.get_bi5_symbol_spec("NAS100")
        assert nas100.url_slug == us100.url_slug


# ═════════════════════════════════════════════════════════════════════
# Tier 5 — Public legacy modules unchanged by the integration
# ═════════════════════════════════════════════════════════════════════
class TestLegacyModuleAPIPreserved:
    """The legacy module functions (config.symbols.get_symbol_config,
    config.bi5_symbols.get_bi5_symbol_spec) must continue to honour
    their original signatures and return shapes."""

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_config_symbols_get_symbol_config(self, symbol):
        from config.symbols import get_symbol_config, SYMBOL_CONFIG
        out = get_symbol_config(symbol)
        assert out == SYMBOL_CONFIG[symbol]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_config_symbols_get_market_type(self, symbol):
        from config.symbols import get_market_type, SYMBOL_CONFIG
        assert get_market_type(symbol) == SYMBOL_CONFIG[symbol]["market_type"]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_config_bi5_get_bi5_symbol_spec(self, symbol):
        from config.bi5_symbols import (
            get_bi5_symbol_spec, _BI5_SYMBOL_SPECS,
        )
        out = get_bi5_symbol_spec(symbol)
        assert out == _BI5_SYMBOL_SPECS[symbol]

    @pytest.mark.parametrize("symbol", CANONICAL_SYMBOLS)
    def test_config_bi5_is_supported(self, symbol):
        from config.bi5_symbols import is_bi5_supported
        assert is_bi5_supported(symbol) is True

    def test_config_bi5_is_supported_alias(self):
        from config.bi5_symbols import is_bi5_supported
        # NAS100 → US100; with the adapter integrated, the legacy
        # function reports True for the alias too.
        assert is_bi5_supported("NAS100") is True
        assert is_bi5_supported("GOLD") is True

    def test_config_bi5_list_byte_identical(self):
        from config.bi5_symbols import list_bi5_symbols, _BI5_SYMBOL_SPECS
        assert list_bi5_symbols() == sorted(_BI5_SYMBOL_SPECS)


# ═════════════════════════════════════════════════════════════════════
# Tier 6 — Flag-state verification
# ═════════════════════════════════════════════════════════════════════
class TestFlagStateContract:

    def test_flag_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        from engines.market_universe_adapter import is_flag_on
        assert is_flag_on() is False

    def test_flag_can_be_turned_on(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "true")
        from engines.market_universe_adapter import is_flag_on
        assert is_flag_on() is True

    def test_market_universe_writer_flag_aligned(self, monkeypatch):
        """``engines.market_universe.is_enabled`` and the adapter's
        ``is_flag_on`` must read the same env var."""
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "1")
        from engines import market_universe as MU
        from engines.market_universe_adapter import is_flag_on
        assert MU.is_enabled() is True
        assert is_flag_on() is True
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "0")
        assert MU.is_enabled() is False
        assert is_flag_on() is False

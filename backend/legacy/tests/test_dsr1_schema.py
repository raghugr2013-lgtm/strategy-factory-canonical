"""DSR-1 — Schema extension tests.

Validates the three additive changes made to ``engines.market_universe``
in support of the Dynamic Symbol Registry (operator-onboarded custom
symbols across Forex / Metal / Index / Crypto / CFD / Futures):

  1. ``VALID_ASSET_CLASSES`` now includes ``cfd`` and ``futures``.
  2. ``ELIGIBILITY_KEYS`` + ``DEFAULT_ELIGIBILITY`` now include
     ``marketplace_enabled`` (defaults to ``False``).
  3. New ``VALID_EXECUTION_PLATFORMS`` enum + ``normalize_execution_platforms``
     helper + ``execution_platforms`` field on the upsert.
  4. Five reserved future-phase fields are accepted as opaque dicts
     and stored without validation:
         broker_compatibility · strategy_compatibility ·
         masterbot_compatibility · marketplace_visibility ·
         propfirm_eligibility.

All assertions are pure (no Mongo round-trip). They guard the schema
contract that the frontend Symbol Registry UI relies on.
"""
from __future__ import annotations

import pytest

from engines import market_universe as MU


class TestDsr1AssetClasses:
    def test_cfd_in_enum(self):
        assert "cfd" in MU.VALID_ASSET_CLASSES

    def test_futures_in_enum(self):
        assert "futures" in MU.VALID_ASSET_CLASSES

    def test_legacy_asset_classes_preserved(self):
        for ac in ("fx_major", "fx_cross", "fx_exotic", "crypto", "index",
                   "commodity_metal", "commodity_energy", "stock", "other"):
            assert ac in MU.VALID_ASSET_CLASSES, ac

    @pytest.mark.parametrize("ac", ["cfd", "futures"])
    def test_normalize_accepts_new_class(self, ac):
        assert MU.normalize_asset_class(ac) == ac

    def test_normalize_unknown_falls_back_to_other(self):
        # The contract pre-DSR-1: unknown asset class → "other".
        assert MU.normalize_asset_class("synthetic_index") == "other"


class TestDsr1Eligibility:
    def test_marketplace_in_keys(self):
        assert "marketplace_enabled" in MU.ELIGIBILITY_KEYS

    def test_marketplace_default_off(self):
        assert MU.DEFAULT_ELIGIBILITY.get("marketplace_enabled") is False

    def test_legacy_eligibility_defaults_preserved(self):
        # Ingestion + validation default ON, others default OFF — the
        # pre-DSR-1 contract. Marketplace also defaults OFF.
        assert MU.DEFAULT_ELIGIBILITY["ingestion_enabled"]   is True
        assert MU.DEFAULT_ELIGIBILITY["validation_enabled"]  is True
        assert MU.DEFAULT_ELIGIBILITY["discovery_enabled"]   is False
        assert MU.DEFAULT_ELIGIBILITY["live_trading_enabled"] is False

    def test_normalize_eligibility_accepts_marketplace_flag(self):
        out = MU.normalize_eligibility({"marketplace_enabled": True})
        assert out.get("marketplace_enabled") is True


class TestDsr1ExecutionPlatforms:
    @pytest.mark.parametrize(
        "plat",
        ["ctrader", "mt4", "mt5", "matchtrader", "tradelocker", "dxtrade"],
    )
    def test_all_target_platforms_in_enum(self, plat):
        assert plat in MU.VALID_EXECUTION_PLATFORMS

    def test_normalize_lowercases_and_strips(self):
        out = MU.normalize_execution_platforms(
            ["cTrader", " MT5 ", "Match-Trader", "DxTrade"],
        )
        # Sorted, deduped, normalised. "Match-Trader" → "matchtrader".
        assert out == ["ctrader", "dxtrade", "matchtrader", "mt5"]

    def test_normalize_drops_unknown(self):
        out = MU.normalize_execution_platforms(
            ["ctrader", "binance", "ninjatrader", "mt4"],
        )
        # Only known platforms survive.
        assert out == ["ctrader", "mt4"]

    def test_normalize_none_returns_empty_list(self):
        assert MU.normalize_execution_platforms(None) == []
        assert MU.normalize_execution_platforms([]) == []

    def test_normalize_dedup(self):
        out = MU.normalize_execution_platforms(["mt5", "MT5", "mt5"])
        assert out == ["mt5"]


class TestDsr1ReservedFutureFields:
    def test_reserved_field_names(self):
        # The five names locked in /app/memory/visual_approval_package/
        # 10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md
        expected = {
            "broker_compatibility",
            "strategy_compatibility",
            "masterbot_compatibility",
            "marketplace_visibility",
            "propfirm_eligibility",
        }
        assert set(MU.RESERVED_FUTURE_FIELDS) == expected


class TestDsr1UpsertSignature:
    """``upsert_symbol`` MUST accept the new kwargs as optional. We do
    NOT exercise the Mongo round-trip here — that's covered by the
    integration tests in ``test_market_universe.py``."""

    def test_upsert_signature_has_execution_platforms(self):
        import inspect
        sig = inspect.signature(MU.upsert_symbol)
        params = set(sig.parameters.keys())
        for name in (
            "execution_platforms",
            "broker_compatibility",
            "strategy_compatibility",
            "masterbot_compatibility",
            "marketplace_visibility",
            "propfirm_eligibility",
        ):
            assert name in params, f"upsert_symbol missing kwarg: {name}"

    def test_upsert_signature_is_keyword_only(self):
        import inspect
        sig = inspect.signature(MU.upsert_symbol)
        # All five reserved fields should be keyword-only so callers can
        # adopt them progressively without positional-arg breakage.
        for name in MU.RESERVED_FUTURE_FIELDS:
            assert sig.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY

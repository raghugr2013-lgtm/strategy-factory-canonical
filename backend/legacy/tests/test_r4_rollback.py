"""R4 — Rollback verification.

R4 is additive — every legacy authority must remain importable and
fully functional. Reverting the frontend hook (deleting `useMarketUniverse.js`
and reverting components) would restore exactly the R3 behaviour:

  * The backend legacy module-level constants (WATCHLIST, TIER1_SYMBOLS,
    DEFAULT_PAIRS × 3, ALLOWED_SYMBOLS) are still authoritative and
    untouched.
  * The adapter accessors continue to fall through to those constants
    when the flag is OFF.
  * The hook is the only new frontend artefact; rollback = delete the
    hook + revert `import { useMarketUniverse }`.

This test enumerates the rollback surface and asserts every legacy
constant still exists with the expected shape.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Backend legacy authorities remain importable and unchanged.
# ─────────────────────────────────────────────────────────────────────
class TestBackendLegacyAuthorityIntact:

    def test_api_data_allowed_symbols_present(self):
        from api import data as DATA_API
        assert hasattr(DATA_API, "ALLOWED_SYMBOLS")
        assert tuple(DATA_API.ALLOWED_SYMBOLS) == (
            "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD",
        )

    def test_readiness_watchlist_present(self):
        from engines import readiness_engine as RE
        assert RE.WATCHLIST == (
            "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD",
        )

    def test_readiness_tier1_present(self):
        from engines import readiness_engine as RE
        assert RE.TIER1_SYMBOLS == ("EURUSD", "GBPUSD")

    def test_market_intelligence_default_pairs_present(self):
        from engines import market_intelligence as MI
        assert MI.DEFAULT_PAIRS == ["EURUSD", "GBPUSD", "XAUUSD"]

    def test_data_maintenance_default_pairs_present(self):
        from data_engine import data_maintenance as DM
        assert DM.DEFAULT_PAIRS == ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

    def test_auto_factory_default_pairs_present(self):
        from engines import auto_factory_engine as AFE
        assert AFE.DEFAULT_PAIRS == ["EURUSD", "GBPUSD", "XAUUSD"]


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Frontend component `*_LEGACY` constants remain present so
# rollback is purely additive (delete the hook import / restore the
# old `PAIRS = PAIRS_LEGACY` line).
# ─────────────────────────────────────────────────────────────────────
class TestFrontendLegacyConstantsIntact:

    COMPONENTS_DIR = Path("/app/frontend/src/components")

    LEGACY_CONSTS = [
        ("AutoFactoryPhase55.js",    "PAIRS_LEGACY"),
        ("DataUpload.js",             "SYMBOLS_LEGACY"),
        ("DataMaintenancePanel.js",   "PAIR_OPTIONS_LEGACY"),
    ]

    @pytest.mark.parametrize("filename,const_name", LEGACY_CONSTS)
    def test_legacy_constant_still_defined(self, filename, const_name):
        path = self.COMPONENTS_DIR / filename
        text = path.read_text(encoding="utf-8")
        assert re.search(
            rf"const\s+{const_name}\s*=\s*\[", text,
        ), f"Rollback contract: {filename} must keep {const_name}"

    def test_dataset_master_pairs_still_exported(self):
        text = Path(
            "/app/frontend/src/hooks/useDatasetAvailability.js"
        ).read_text(encoding="utf-8")
        assert "export const DATASET_MASTER_PAIRS" in text
        assert "export const DATASET_MASTER_TIMEFRAMES" in text


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — The hook file itself can be deleted without leaving dangling
# imports that import from anywhere outside React. Verify the only
# external dependency is `react` (so the hook is genuinely free-standing).
# ─────────────────────────────────────────────────────────────────────
class TestHookHasNoEntanglements:

    def test_hook_only_imports_from_react(self):
        text = Path(
            "/app/frontend/src/hooks/useMarketUniverse.js"
        ).read_text(encoding="utf-8")
        imports = re.findall(r"""^import\s+.+?\s+from\s+['"]([^'"]+)['"]""",
                             text, re.MULTILINE)
        assert imports, "Hook must declare at least one import"
        for src in imports:
            assert src == "react", (
                f"Rollback contract: useMarketUniverse must only import "
                f"from 'react'; found '{src}'"
            )


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Adapter rollback: clear_registry_cache() restores legacy
# semantics deterministically.
# ─────────────────────────────────────────────────────────────────────
class TestAdapterRollbackPath:

    def test_clear_cache_restores_legacy(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "1")
        from engines import market_universe_adapter as ADAPTER

        # Force-populate the cache with bogus data to simulate a stale
        # registry snapshot.
        ADAPTER._registry_cache = {  # noqa: SLF001 (test introspection)
            "ts": 1, "rows": [{"symbol": "FAKE", "enabled": True}],
        }
        ADAPTER.clear_registry_cache()

        # With cleared cache, flag ON, no DB → adapter must still
        # serve legacy authority via the try/except guard.
        from api import data as DATA_API
        assert set(ADAPTER.get_allowed_symbols()) == set(DATA_API.ALLOWED_SYMBOLS)

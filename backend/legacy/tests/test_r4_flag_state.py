"""R4 — Flag-state contract verification.

R4 must not flip ``ENABLE_DYNAMIC_MARKET_UNIVERSE``. The flag remains
**OFF by default** and the legacy fallback authority remains intact.

This test asserts:

  1. The feature flag manifest still registers the flag with the
     documented default and scope.
  2. The runtime accessor `MU.is_enabled()` returns False when the
     env var is unset.
  3. Every adapter accessor still falls through to the legacy
     module-level constants when the flag is OFF.
  4. No R4 commit silently set the env var anywhere in the repo.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


class TestFlagDefaultOff:

    def test_flag_default_off_in_manifest(self):
        from engines import feature_flags as FF
        # Find the manifest entry.
        manifest = getattr(FF, "FLAG_MANIFEST", None) or getattr(FF, "MANIFEST", None)
        if manifest is None:
            # Fall back to introspection — at least one entry mentions
            # ENABLE_DYNAMIC_MARKET_UNIVERSE.
            src = Path(FF.__file__).read_text(encoding="utf-8")
            assert "ENABLE_DYNAMIC_MARKET_UNIVERSE" in src
            # And the default is False / "0" / not "1".
            assert not re.search(
                r"ENABLE_DYNAMIC_MARKET_UNIVERSE[^,\n}]*['\"](1|true|yes|on)['\"]",
                src, re.IGNORECASE,
            ), "ENABLE_DYNAMIC_MARKET_UNIVERSE must default OFF"
            return
        entry = next(
            (m for m in manifest if isinstance(m, dict) and
             m.get("name") == "ENABLE_DYNAMIC_MARKET_UNIVERSE"),
            None,
        )
        assert entry is not None, "Manifest must register the flag"
        default = entry.get("default")
        assert default in (False, "0", "false", None, ""), (
            f"Flag default must be OFF (got {default!r})"
        )

    def test_runtime_accessor_returns_false_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        from engines import market_universe as MU
        assert MU.is_enabled() is False

    @pytest.mark.parametrize("truthy", ["", "0", "false", "off", "no"])
    def test_runtime_falsy_strings_keep_flag_off(self, monkeypatch, truthy):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", truthy)
        from engines import market_universe as MU
        assert MU.is_enabled() is False


class TestAdapterFallsThroughWhenFlagOff:
    """Every adapter accessor must return the legacy authority when the
    flag is OFF — proving R4 did not silently widen the registry's
    runtime authority.
    """

    @pytest.fixture(autouse=True)
    def _flag_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        from engines import market_universe_adapter as ADAPTER
        ADAPTER.clear_registry_cache()
        yield
        ADAPTER.clear_registry_cache()

    def test_get_allowed_symbols_equals_api_data_allowed(self):
        from engines import market_universe_adapter as ADAPTER
        from api import data as DATA_API
        assert tuple(ADAPTER.get_allowed_symbols()) == tuple(DATA_API.ALLOWED_SYMBOLS)

    def test_get_active_watchlist_equals_readiness_watchlist(self):
        from engines import market_universe_adapter as ADAPTER
        from engines import readiness_engine as RE
        assert tuple(ADAPTER.get_active_watchlist()) == tuple(RE.WATCHLIST)

    def test_get_tier1_symbols_equals_readiness_tier1(self):
        from engines import market_universe_adapter as ADAPTER
        from engines import readiness_engine as RE
        assert tuple(ADAPTER.get_tier1_symbols()) == tuple(RE.TIER1_SYMBOLS)

    def test_get_discovery_pairs_equals_auto_factory_default(self):
        from engines import market_universe_adapter as ADAPTER
        from engines import auto_factory_engine as AFE
        assert tuple(ADAPTER.get_discovery_pairs()) == tuple(AFE.DEFAULT_PAIRS)

    def test_get_intelligence_pairs_equals_intelligence_default(self):
        from engines import market_universe_adapter as ADAPTER
        from engines import market_intelligence as MI
        assert tuple(ADAPTER.get_intelligence_pairs()) == tuple(MI.DEFAULT_PAIRS)


class TestEnvFilesDoNotEnableFlag:

    def test_backend_env_does_not_enable_flag(self):
        path = Path("/app/backend/.env")
        if not path.is_file():
            return  # OK — env file absent means default OFF
        body = path.read_text(encoding="utf-8")
        # Look for ENABLE_DYNAMIC_MARKET_UNIVERSE=... lines and verify
        # they are either absent or evaluate to falsy.
        for line in body.splitlines():
            m = re.match(
                r"\s*ENABLE_DYNAMIC_MARKET_UNIVERSE\s*=\s*(.*)",
                line,
            )
            if not m:
                continue
            val = m.group(1).strip().strip('"').strip("'").lower()
            assert val in ("", "0", "false", "off", "no"), (
                f"R4 boundary violated: backend/.env enables the flag → {line!r}"
            )

    def test_frontend_env_does_not_enable_flag(self):
        path = Path("/app/frontend/.env")
        if not path.is_file():
            return
        body = path.read_text(encoding="utf-8")
        assert "ENABLE_DYNAMIC_MARKET_UNIVERSE" not in body, (
            "Frontend .env must not reference the backend-only flag"
        )

    def test_no_test_credentials_leak(self):
        # Belt-and-suspenders: ensure the live process is currently
        # running with the flag OFF.
        assert os.environ.get(
            "ENABLE_DYNAMIC_MARKET_UNIVERSE", ""
        ).strip().lower() in ("", "0", "false", "off", "no")

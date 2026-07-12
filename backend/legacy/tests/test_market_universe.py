"""
P1.6 — Tests for the dormant dynamic market-universe registry.

Scope (institutional discipline — no expansion beyond P1.6):

    1. Module imports cleanly.
    2. ``is_enabled()`` honours ``ENABLE_DYNAMIC_MARKET_UNIVERSE``,
       defaults False.
    3. ``default_tier()`` honours ``MARKET_UNIVERSE_DEFAULT_TIER``,
       defaults ``candidate``.
    4. ``normalize_symbol`` produces deterministic canonical form
       across casing, separators, whitespace.
    5. Tier / asset-class / compute-hint validators round-trip.
    6. ``_validate_payload`` honest-refusal coverage.
    7. ``exploration_budget_for`` returns the documented tier defaults.
    8. ``compute_cost_hint_to_weight`` returns the documented weights.
    9. **Engine non-consumption invariant** — no module under
       ``backend/engines/`` imports ``engines.market_universe``.
    10. Feature_flags manifest registers all 3 flags with the
        documented defaults and scopes.

CRUD round-trips against real Mongo are NOT exercised here — the
admin endpoints + live smoke test (curl) cover that path, and the
engine-imports regression test confirms the module loads cleanly.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines import market_universe as MU                       # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — dormancy
# ─────────────────────────────────────────────────────────────────────
class TestDormancy:

    def test_module_imports(self):
        for name in (
            "is_enabled", "default_tier",
            "normalize_symbol", "normalize_broker_class",
            "normalize_tier", "normalize_asset_class",
            "get_symbol", "list_symbols", "count_by_tier",
            "upsert_symbol", "delete_symbol",
            "set_tier", "set_enabled",
            "exploration_budget_for", "compute_cost_hint_to_weight",
        ):
            assert hasattr(MU, name), f"market_universe missing: {name}"

    def test_flag_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", raising=False)
        assert MU.is_enabled() is False

    def test_flag_env_override(self, monkeypatch):
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "true")
        assert MU.is_enabled() is True
        monkeypatch.setenv("ENABLE_DYNAMIC_MARKET_UNIVERSE", "false")
        assert MU.is_enabled() is False

    def test_default_tier_env_override(self, monkeypatch):
        monkeypatch.delenv("MARKET_UNIVERSE_DEFAULT_TIER", raising=False)
        assert MU.default_tier() == "candidate"
        monkeypatch.setenv("MARKET_UNIVERSE_DEFAULT_TIER", "experimental")
        assert MU.default_tier() == "experimental"
        monkeypatch.setenv("MARKET_UNIVERSE_DEFAULT_TIER", "not-a-tier")
        # Falls back to candidate on malformed value (no silent typo).
        assert MU.default_tier() == "candidate"

    def test_no_engine_consumer(self):
        """``backend/engines/*.py`` (other than ``market_universe.py``
        itself and its R0 companion writers ``market_universe_audit``
        / ``seed/market_universe_seed``) MUST NOT import
        ``engines.market_universe`` directly. The registry CRUD module
        is operator-decree-only.

        Importing ``engines.market_universe_adapter`` IS permitted —
        the adapter is the authorised gateway and is consulted by
        ``tick_validator``, ``spread_analyzer``, ``cbot_trade_parity``,
        ``paper_execution_engine`` (R2 promotions).
        """
        backend_root = Path(_BACKEND)
        # Match only the writer module — NOT _adapter / _audit / _seed.
        # Word-boundary at the end (whitespace, dot, end of line).
        cmd = [
            "grep", "-rEln",
            r"^[[:space:]]*(from|import)[[:space:]]+engines\.market_universe([[:space:]]|$)",
            str(backend_root),
            "--include=*.py",
        ]
        out = subprocess.run(cmd, capture_output=True, text=True)
        engines_dir = str(backend_root / "engines") + "/"
        # Companion writers that are ALLOWED to import the registry.
        ALLOWED_COMPANIONS = {
            "market_universe.py",
            "market_universe_audit.py",
            "market_universe_seed.py",
            "market_universe_adapter.py",
        }
        violations = []
        for line in out.stdout.splitlines():
            if not line:
                continue
            path = Path(line.split(":", 1)[0] if ":" in line else line)
            if path.name in ALLOWED_COMPANIONS:
                continue
            if "/tests/" in line or "__pycache__" in line:
                continue
            if line.startswith(engines_dir):
                violations.append(line)
        assert violations == [], (
            "engines.market_universe (the writer module) must not be "
            "consumed by any engine outside the R0 companion set. "
            "Adapter consumption via engines.market_universe_adapter "
            "is allowed. Violations:\n  " + "\n  ".join(violations)
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — normalisation
# ─────────────────────────────────────────────────────────────────────
class TestNormalization:

    @pytest.mark.parametrize("raw,expected", [
        ("eurusd",       "EURUSD"),
        ("EUR/USD",      "EURUSD"),
        ("XRP-USD",      "XRPUSD"),
        ("  NAS 100  ",  "NAS100"),
        ("us30.cash",    "US30CASH"),
        ("xau usd",      "XAUUSD"),
        ("",             ""),
        ("  ",           ""),
    ])
    def test_normalize_symbol(self, raw, expected):
        assert MU.normalize_symbol(raw) == expected

    def test_normalize_broker_class(self):
        assert MU.normalize_broker_class("Tier1_ECN") == "tier1_ecn"
        assert MU.normalize_broker_class("") == "unknown"
        assert MU.normalize_broker_class(None) == "unknown"

    def test_normalize_tier_falls_back(self):
        assert MU.normalize_tier("ACTIVE") == "active"
        assert MU.normalize_tier("bogus") == "candidate"
        assert MU.normalize_tier(None) == "candidate"

    def test_normalize_asset_class_falls_back(self):
        assert MU.normalize_asset_class("crypto") == "crypto"
        assert MU.normalize_asset_class("STOCK") == "stock"
        assert MU.normalize_asset_class("unknown-class") == "other"

    def test_normalize_compute_hint_falls_back(self):
        assert MU.normalize_compute_hint("low") == "low"
        assert MU.normalize_compute_hint("HIGH") == "high"
        assert MU.normalize_compute_hint("foo") == "medium"


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — honest-refusal validation
# ─────────────────────────────────────────────────────────────────────
def _good_kwargs(**overrides):
    base = dict(
        symbol="EURUSD", broker_class="tier1_ecn",
        asset_class="fx_major", tier="candidate",
        priority=100, exploration_budget_pct=25.0,
        compute_cost_hint="medium", pip_size=0.0001,
        volume_min=1000.0, volume_step=1000.0, min_data_bars=500,
    )
    base.update(overrides)
    return base


class TestValidation:

    def test_good_passes(self):
        MU._validate_payload(**_good_kwargs())

    def test_empty_symbol_rejected(self):
        with pytest.raises(ValueError, match=r"symbol"):
            MU._validate_payload(**_good_kwargs(symbol=""))

    def test_invalid_tier_rejected(self):
        with pytest.raises(ValueError, match=r"tier"):
            MU._validate_payload(**_good_kwargs(tier="not-a-tier"))

    def test_invalid_asset_class_rejected(self):
        with pytest.raises(ValueError, match=r"asset_class"):
            MU._validate_payload(**_good_kwargs(asset_class="bogus"))

    def test_invalid_compute_hint_rejected(self):
        with pytest.raises(ValueError, match=r"compute_cost_hint"):
            MU._validate_payload(**_good_kwargs(compute_cost_hint="ultra"))

    def test_priority_out_of_range_rejected(self):
        with pytest.raises(ValueError, match=r"priority"):
            MU._validate_payload(**_good_kwargs(priority=10_000))

    def test_exploration_budget_out_of_range_rejected(self):
        with pytest.raises(ValueError, match=r"exploration_budget_pct"):
            MU._validate_payload(**_good_kwargs(exploration_budget_pct=150.0))

    def test_negative_pip_size_rejected(self):
        with pytest.raises(ValueError, match=r"pip_size"):
            MU._validate_payload(**_good_kwargs(pip_size=-0.0001))

    def test_negative_min_data_bars_rejected(self):
        with pytest.raises(ValueError, match=r"min_data_bars"):
            MU._validate_payload(**_good_kwargs(min_data_bars=-1))


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — pure helper contracts
# ─────────────────────────────────────────────────────────────────────
class TestPureHelpers:

    @pytest.mark.parametrize("tier,expected", [
        ("active",            5.0),
        ("candidate",         25.0),
        ("experimental",      50.0),
        ("regime_activated",  30.0),
        ("dormant",           0.0),
        ("unknown-tier",      25.0),   # falls back to candidate default
    ])
    def test_exploration_budget_for(self, tier, expected):
        assert MU.exploration_budget_for(tier) == expected

    @pytest.mark.parametrize("hint,expected", [
        ("low",     1.0),
        ("medium",  2.0),
        ("high",    4.0),
        ("ultra",   2.0),   # falls back to medium
    ])
    def test_compute_cost_hint_to_weight(self, hint, expected):
        assert MU.compute_cost_hint_to_weight(hint) == expected


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — feature_flags manifest
# ─────────────────────────────────────────────────────────────────────
class TestFeatureFlagManifest:

    def test_flags_registered(self):
        from engines.feature_flags import all_flags
        af = all_flags()
        for name in (
            "ENABLE_DYNAMIC_MARKET_UNIVERSE",
            "MARKET_UNIVERSE_DEFAULT_TIER",
            "MARKET_UNIVERSE_AUTO_INGEST",
        ):
            assert name in af, f"{name} missing from manifest"
            assert af[name]["scope"] == "market_universe"
            assert af[name]["is_dormant"] is True

    def test_defaults_are_dormant(self):
        from engines.feature_flags import all_flags
        af = all_flags()
        assert af["ENABLE_DYNAMIC_MARKET_UNIVERSE"]["default"] is False
        assert af["MARKET_UNIVERSE_AUTO_INGEST"]["default"] is False
        assert af["MARKET_UNIVERSE_DEFAULT_TIER"]["default"] == "candidate"

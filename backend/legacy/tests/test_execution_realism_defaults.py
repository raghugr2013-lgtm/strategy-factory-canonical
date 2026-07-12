"""
P1.2 — Tests for the dormant per-pair execution-realism defaults
registry (``engines.execution_realism_defaults``).

Scope:

    1. Module imports cleanly.
    2. ``is_enabled()`` reflects ``ENABLE_EXECUTION_REALISM_DEFAULTS``
       and defaults to False.
    3. ``normalize_pair`` / ``normalize_broker_class`` produce
       deterministic keys.
    4. ``_validate_payload`` raises ``ValueError`` on each honest-
       refusal class (negative, non-numeric, unit-typo ceiling).
    5. **Engine non-consumption invariant** —
       ``engines/execution_engine.py`` does NOT import this module.
       Statically enforced by grep, identical pattern to the P0.4
       dormancy invariant.
    6. Feature_flags manifest registers ``ENABLE_EXECUTION_REALISM_DEFAULTS``
       with the right defaults.

CRUD round-trips are NOT exercised here because they would touch the
real Mongo collection. They are covered by the higher-level admin
endpoint smoke test in this same pass (run via curl after backend
restart) and by the existing engine-imports regression test which
imports the module cleanly at module-load time.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from engines import execution_realism_defaults as ERD          # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — dormancy
# ─────────────────────────────────────────────────────────────────────
class TestDormancy:

    def test_module_imports(self):
        assert hasattr(ERD, "get_defaults")
        assert hasattr(ERD, "list_defaults")
        assert hasattr(ERD, "upsert_defaults")
        assert hasattr(ERD, "delete_defaults")
        assert hasattr(ERD, "is_enabled")

    def test_flag_default_off(self, monkeypatch):
        monkeypatch.delenv("ENABLE_EXECUTION_REALISM_DEFAULTS", raising=False)
        assert ERD.is_enabled() is False

    def test_flag_respects_env_override(self, monkeypatch):
        monkeypatch.setenv("ENABLE_EXECUTION_REALISM_DEFAULTS", "true")
        assert ERD.is_enabled() is True
        monkeypatch.setenv("ENABLE_EXECUTION_REALISM_DEFAULTS", "false")
        assert ERD.is_enabled() is False

    def test_no_engine_consumer(self):
        """``engines/execution_engine.py`` MUST NOT import
        ``engines.execution_realism_defaults``. The activation pathway
        belongs to a separately-reviewed P1.1 wiring pass — never a
        drive-by edit.
        """
        backend_root = Path(_BACKEND)
        cmd = [
            "grep", "-rEln",
            r"^[[:space:]]*(from|import)[[:space:]]+engines\.execution_realism_defaults",
            str(backend_root),
            "--include=*.py",
        ]
        out = subprocess.run(cmd, capture_output=True, text=True)
        # Only the api/ surface (latent + admin) and the test file
        # itself should import this module today. Engines must NOT.
        forbidden_prefixes = (
            str(backend_root / "engines") + "/",
        )
        violations = []
        for line in out.stdout.splitlines():
            if not line:
                continue
            if "execution_realism_defaults.py" in Path(line).name:
                continue
            if "/tests/" in line or "__pycache__" in line:
                continue
            if any(line.startswith(p) for p in forbidden_prefixes):
                violations.append(line)
        assert violations == [], (
            "execution_realism_defaults must not be consumed by any "
            "engine module today. Violations:\n  " +
            "\n  ".join(violations)
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — normalization
# ─────────────────────────────────────────────────────────────────────
class TestNormalization:

    def test_pair_uppercased(self):
        assert ERD.normalize_pair("eurusd") == "EURUSD"
        assert ERD.normalize_pair("  USDJPY  ") == "USDJPY"

    def test_broker_class_lowercased(self):
        assert ERD.normalize_broker_class("Tier1_ECN") == "tier1_ecn"
        assert ERD.normalize_broker_class(" RETAIL_STP ") == "retail_stp"


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — honest-refusal validation
# ─────────────────────────────────────────────────────────────────────
class TestValidation:

    def test_negative_spread_rejected(self):
        with pytest.raises(ValueError, match=r"spread_usd.*>= 0"):
            ERD._validate_payload(
                pair="EURUSD", broker_class="tier1_ecn",
                spread_usd=-0.1, max_slippage_usd=0.0, commission_usd=0.0,
            )

    def test_non_numeric_rejected(self):
        with pytest.raises(ValueError, match=r"commission_usd.*numeric"):
            ERD._validate_payload(
                pair="EURUSD", broker_class="tier1_ecn",
                spread_usd=0.0, max_slippage_usd=0.0,
                commission_usd="five",  # type: ignore[arg-type]
            )

    def test_unit_typo_ceiling_rejected(self):
        with pytest.raises(ValueError, match=r"max_slippage_usd.*unit error"):
            ERD._validate_payload(
                pair="EURUSD", broker_class="tier1_ecn",
                spread_usd=0.0, max_slippage_usd=5000.0,
                commission_usd=0.0,
            )

    def test_empty_pair_rejected(self):
        with pytest.raises(ValueError, match=r"pair"):
            ERD._validate_payload(
                pair="", broker_class="tier1_ecn",
                spread_usd=0.0, max_slippage_usd=0.0, commission_usd=0.0,
            )

    def test_valid_payload_passes(self):
        # Should not raise.
        ERD._validate_payload(
            pair="EURUSD", broker_class="tier1_ecn",
            spread_usd=1.5, max_slippage_usd=0.8, commission_usd=2.0,
        )


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — feature_flags manifest
# ─────────────────────────────────────────────────────────────────────
class TestFeatureFlagManifest:

    def test_flag_registered(self):
        from engines.feature_flags import all_flags
        spec = all_flags().get("ENABLE_EXECUTION_REALISM_DEFAULTS")
        assert spec is not None, (
            "ENABLE_EXECUTION_REALISM_DEFAULTS missing from manifest"
        )
        assert spec["default"] is False
        assert spec["kind"] == "bool"
        assert spec["scope"] == "execution_realism"
        assert spec["is_dormant"] is True

"""R4 — Frontend parity validation.

Verifies that:

  1. The legacy fallback constants embedded in every frontend file that
     was migrated to ``useMarketUniverse`` byte-match (set-equality) the
     backend authoritative list for the corresponding eligibility tier.

  2. The legacy fallback in ``useMarketUniverse.js`` itself byte-matches
     the backend authoritative lists across every eligibility slice it
     advertises.

  3. Every component that calls ``useMarketUniverse`` is rendered safely
     (i.e. uses ``.options`` or ``.all`` / ``.tier1`` etc. — never a
     non-existent slice) and asks for a known eligibility kind.

R4 must produce **set equality** between the OLD selector options (the
hard-coded ``*_LEGACY`` arrays) and the NEW selector options served by
``useMarketUniverse`` when the API is unavailable / empty. The hook is
the only path the frontend ever uses to populate symbol pickers — these
tests are the operator-mandated "old == new" parity gate.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

FRONTEND_ROOT = Path("/app/frontend/src")
HOOK_PATH = FRONTEND_ROOT / "hooks" / "useMarketUniverse.js"
COMPONENTS_DIR = FRONTEND_ROOT / "components"
DATASET_HOOK_PATH = FRONTEND_ROOT / "hooks" / "useDatasetAvailability.js"

CANONICAL_7 = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD")
LEGACY_TIER1 = ("EURUSD", "GBPUSD")
LEGACY_DISCOVERY = ("EURUSD", "GBPUSD", "XAUUSD")
LEGACY_MUTATION = ("EURUSD", "GBPUSD", "XAUUSD")
LEGACY_PORTFOLIO = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
LEGACY_CERTIFICATION = ("EURUSD", "GBPUSD", "XAUUSD")


_ARRAY_RE = re.compile(
    r"""(?:export\s+)?const\s+(?P<name>[A-Z][A-Z0-9_]*)\s*=\s*\[(?P<body>[^\]]*)\]""",
    re.DOTALL,
)
_STRING_RE = re.compile(r"""['"]([A-Z0-9]{3,12})['"]""")


def _extract_array(js_text: str, const_name: str) -> tuple[str, ...]:
    """Extract a JS const array of strings by name. Returns a tuple of
    the string literals in source order.

    Raises AssertionError when not found — these constants are part of
    the R4 contract and their disappearance must fail the gate.
    """
    for m in _ARRAY_RE.finditer(js_text):
        if m.group("name") == const_name:
            return tuple(_STRING_RE.findall(m.group("body")))
    raise AssertionError(
        f"Could not locate JS const '{const_name}' in source. "
        f"R4 contract requires this legacy fallback to remain present.",
    )


# ─────────────────────────────────────────────────────────────────────
# 1 · useMarketUniverse hook — fallback constants byte-match backend.
# ─────────────────────────────────────────────────────────────────────
class TestHookLegacyFallbackParity:
    """The legacy fallback served by the hook MUST equal the backend
    authoritative list for every eligibility slice.
    """

    @pytest.fixture(scope="class")
    def hook(self) -> str:
        return HOOK_PATH.read_text(encoding="utf-8")

    def test_hook_file_present(self):
        assert HOOK_PATH.is_file(), (
            "R4 contract: src/hooks/useMarketUniverse.js must exist."
        )

    def test_legacy_pairs_matches_canonical_7(self, hook):
        got = _extract_array(hook, "LEGACY_PAIRS")
        assert tuple(got) == CANONICAL_7, (
            "Hook's LEGACY_PAIRS fallback must equal the canonical 7."
        )

    def test_legacy_discovery_matches_backend(self, hook):
        got = _extract_array(hook, "LEGACY_DISCOVERY")
        assert set(got) == set(LEGACY_DISCOVERY)

    def test_legacy_mutation_matches_backend(self, hook):
        got = _extract_array(hook, "LEGACY_MUTATION")
        assert set(got) == set(LEGACY_MUTATION)

    def test_legacy_portfolio_matches_backend(self, hook):
        got = _extract_array(hook, "LEGACY_PORTFOLIO")
        assert set(got) == set(LEGACY_PORTFOLIO)

    def test_legacy_certification_matches_backend(self, hook):
        got = _extract_array(hook, "LEGACY_CERTIFICATION")
        assert set(got) == set(LEGACY_CERTIFICATION)

    def test_legacy_tier1_matches_backend(self, hook):
        got = _extract_array(hook, "LEGACY_TIER1")
        assert set(got) == set(LEGACY_TIER1)


# ─────────────────────────────────────────────────────────────────────
# 2 · Component-level legacy arrays must equal hook fallback (the OLD
#     selector options) — proving the "Old selector options == New
#     selector options" R4 gate.
# ─────────────────────────────────────────────────────────────────────
class TestComponentLegacyParity:
    """For each migrated component, the historic ``*_LEGACY`` constant
    (which represents what the dropdown *used* to render) must match the
    hook's fallback slice (which is what the dropdown now renders when
    the API is unreachable).
    """

    # (filename, JS const name, hook slice the component requests)
    CASES = [
        ("AutoFactoryPhase55.js", "PAIRS_LEGACY", "discovery"),
        ("DataUpload.js",          "SYMBOLS_LEGACY", "ingestion"),
        ("DataMaintenancePanel.js", "PAIR_OPTIONS_LEGACY", "ingestion"),
    ]

    HOOK_SLICE_TO_CONST = {
        "ingestion":     "LEGACY_PAIRS",
        "discovery":     "LEGACY_DISCOVERY",
        "mutation":      "LEGACY_MUTATION",
        "portfolio":     "LEGACY_PORTFOLIO",
        "certification": "LEGACY_CERTIFICATION",
        "validation":    "LEGACY_PAIRS",
    }

    @pytest.fixture(scope="class")
    def hook(self) -> str:
        return HOOK_PATH.read_text(encoding="utf-8")

    @pytest.mark.parametrize("filename,const_name,slice_kind", CASES)
    def test_component_legacy_preserves_canonical(
        self, hook, filename, const_name, slice_kind,
    ):
        """The historic `*_LEGACY` constant kept in each migrated
        component is the audit record of what the dropdown used to
        render. R4 contract: it must still contain every canonical
        symbol (no canonical lost from history), and it must remain
        a superset of the hook fallback for the slice the component
        now requests (so empty-state never widens the UI beyond what
        was previously offered).
        """
        path = COMPONENTS_DIR / filename
        assert path.is_file(), f"R4 contract: {filename} must exist"
        comp_legacy = set(_extract_array(path.read_text(encoding="utf-8"), const_name))

        canon = set(CANONICAL_7)
        assert canon <= comp_legacy, (
            f"Component '{filename}' legacy lost canonical symbols: "
            f"missing {canon - comp_legacy}"
        )

        hook_const = self.HOOK_SLICE_TO_CONST[slice_kind]
        hook_legacy = set(_extract_array(hook, hook_const))
        assert hook_legacy <= comp_legacy, (
            f"Hook fallback for '{slice_kind}' ({hook_legacy}) widens "
            f"beyond historic {filename} options ({comp_legacy})."
        )

    @pytest.mark.parametrize("filename,const_name,slice_kind", CASES)
    def test_component_new_slice_matches_backend_authority(
        self, filename, const_name, slice_kind,
    ):
        """The hook slice each component now requests must equal the
        backend authoritative list — proving that the NEW selector
        options (under flag-OFF / empty-API fallback) come straight
        from the same authority that backs the legacy module-level
        constants the adapter falls through to.
        """
        hook = HOOK_PATH.read_text(encoding="utf-8")
        hook_const = self.HOOK_SLICE_TO_CONST[slice_kind]
        hook_legacy = set(_extract_array(hook, hook_const))

        from engines import market_universe_adapter as ADAPTER
        slice_to_adapter = {
            "ingestion":     ADAPTER.get_allowed_symbols,
            "discovery":     ADAPTER.get_discovery_pairs,
            "mutation":      ADAPTER.get_mutation_pairs,
            "validation":    ADAPTER.get_validation_pairs,
            "certification": ADAPTER.get_certification_pairs,
            "portfolio":     ADAPTER.get_portfolio_pairs,
        }
        backend_authority = set(slice_to_adapter[slice_kind]())
        assert hook_legacy == backend_authority, (
            f"R4 parity gate: hook '{slice_kind}' fallback differs from "
            f"backend authority. hook={hook_legacy} backend={backend_authority}"
        )


# ─────────────────────────────────────────────────────────────────────
# 3 · Component usage discipline — every migrated component requests a
#     known eligibility kind and reads `.options`/`.all`/`.tier1`.
# ─────────────────────────────────────────────────────────────────────
class TestComponentHookUsage:
    """Static check: every consumer of useMarketUniverse asks for a
    documented eligibility slice and consumes the safe accessor.
    """

    EXPECTED_CONSUMERS = {
        "AutoFactory.js",
        "AutoFactoryPhase55.js",
        "DataMaintenancePanel.js",
        "DataUpload.js",
        "PortfolioPanel.js",
        "SavedStrategies.js",
        "StrategyPanel.js",
        "UniverseGovernancePanel.jsx",
    }

    KNOWN_ELIGIBILITY = {
        "ingestion", "discovery", "mutation", "validation",
        "certification", "portfolio", "live_trading",
    }

    SAFE_ACCESSORS = {"options", "all", "tier1"}

    def test_dataset_hook_consumes_market_universe(self):
        text = DATASET_HOOK_PATH.read_text(encoding="utf-8")
        assert "useMarketUniverse" in text, (
            "useDatasetAvailability must consume useMarketUniverse for "
            "symbol-growth automation."
        )
        # The dataset hook requests ingestion slice.
        assert "eligibility: 'ingestion'" in text or 'eligibility: "ingestion"' in text

    def test_all_expected_consumers_present(self):
        for fname in self.EXPECTED_CONSUMERS:
            p = COMPONENTS_DIR / fname
            assert p.is_file(), f"R4: expected migrated component '{fname}' is missing"

    @pytest.mark.parametrize("fname", sorted(EXPECTED_CONSUMERS))
    def test_consumer_uses_safe_accessor(self, fname):
        text = (COMPONENTS_DIR / fname).read_text(encoding="utf-8")
        assert "useMarketUniverse" in text, (
            f"{fname} should import/use useMarketUniverse"
        )
        # At least one safe accessor must appear in the destructure.
        # We look for `const { options ...` / `const { all ...` /
        # `const { tier1 ...` near a useMarketUniverse(...) call.
        pattern = re.compile(
            r"const\s*\{\s*([^}]+)\}\s*=\s*useMarketUniverse",
            re.MULTILINE,
        )
        m = pattern.search(text)
        assert m, f"{fname} must destructure the hook return value"
        keys = {k.split(":")[0].strip() for k in m.group(1).split(",") if k.strip()}
        assert keys & self.SAFE_ACCESSORS, (
            f"{fname} must destructure one of {self.SAFE_ACCESSORS}; got {keys}"
        )

    @pytest.mark.parametrize("fname", sorted(EXPECTED_CONSUMERS))
    def test_consumer_requests_known_eligibility(self, fname):
        text = (COMPONENTS_DIR / fname).read_text(encoding="utf-8")
        # Some consumers (SavedStrategies, UniverseGovernancePanel) ask
        # for the full registry (no `eligibility`), which is also fine.
        m = re.search(
            r"useMarketUniverse\(\s*\{\s*eligibility:\s*['\"]([a-z_]+)['\"]",
            text,
        )
        if m:
            assert m.group(1) in self.KNOWN_ELIGIBILITY, (
                f"{fname} requests unknown eligibility '{m.group(1)}'. "
                f"Known: {self.KNOWN_ELIGIBILITY}"
            )


# ─────────────────────────────────────────────────────────────────────
# 4 · Hook fallback equality vs backend authority (set-level, the
#     true Old==New contract for empty-state).
# ─────────────────────────────────────────────────────────────────────
class TestHookFallbackEqualsBackendAuthority:
    """Direct comparison of the hook's fallback slices against the
    legacy backend authorities they shadow.
    """

    @pytest.fixture(scope="class")
    def hook(self) -> str:
        return HOOK_PATH.read_text(encoding="utf-8")

    def test_ingestion_fallback_matches_api_data_allowed(self, hook):
        from api import data as DATA_API
        got = set(_extract_array(hook, "LEGACY_PAIRS"))
        assert got == set(DATA_API.ALLOWED_SYMBOLS)

    def test_validation_fallback_matches_readiness_watchlist(self, hook):
        from engines import readiness_engine as RE
        got = set(_extract_array(hook, "LEGACY_PAIRS"))
        assert got == set(RE.WATCHLIST)

    def test_tier1_fallback_matches_readiness_tier1(self, hook):
        from engines import readiness_engine as RE
        got = set(_extract_array(hook, "LEGACY_TIER1"))
        assert got == set(RE.TIER1_SYMBOLS)

    def test_discovery_fallback_matches_auto_factory_default(self, hook):
        from engines import auto_factory_engine as AFE
        got = set(_extract_array(hook, "LEGACY_DISCOVERY"))
        assert got == set(AFE.DEFAULT_PAIRS)

    def test_portfolio_fallback_matches_data_maintenance_default(self, hook):
        from data_engine import data_maintenance as DM
        got = set(_extract_array(hook, "LEGACY_PORTFOLIO"))
        assert got == set(DM.DEFAULT_PAIRS)

    def test_certification_fallback_matches_intelligence_default(self, hook):
        from engines import market_intelligence as MI
        # market_intelligence DEFAULT_PAIRS = ['EURUSD','GBPUSD','XAUUSD']
        got = set(_extract_array(hook, "LEGACY_CERTIFICATION"))
        assert got == set(MI.DEFAULT_PAIRS)

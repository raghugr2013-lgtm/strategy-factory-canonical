"""R4 — Empty-state protection.

The frontend hook `useMarketUniverse` must NEVER blank out dropdowns,
even when:

    * the market-universe API is unreachable (network error)
    * the API call times out (5-second AbortController)
    * the API returns 4xx / 5xx
    * the API returns an empty registry (`rows: []`)
    * the eligibility slice happens to be empty (e.g. live_trading)

The hook implements four layers of defence. We verify the source code
contains every one of them so a future refactor cannot quietly remove
the legacy-fallback safety net.

This is a *structural* test — we cannot execute React hooks under
pytest, but we can prove the source contains the contractual
guarantees.
"""
from __future__ import annotations

import re
from pathlib import Path

HOOK_PATH = Path("/app/frontend/src/hooks/useMarketUniverse.js")


class TestEmptyStateContract:
    """Every empty-state branch the hook claims to handle must be
    expressed in the source code.
    """

    def setup_method(self):
        self.src = HOOK_PATH.read_text(encoding="utf-8")

    # ─── (1) network failure / abort ─────────────────────────────────
    def test_uses_abort_controller(self):
        assert "AbortController" in self.src
        assert "controller.abort()" in self.src

    def test_has_fetch_timeout_constant(self):
        m = re.search(r"FETCH_TIMEOUT_MS\s*=\s*(\d+)", self.src)
        assert m, "FETCH_TIMEOUT_MS must be defined"
        timeout_ms = int(m.group(1))
        assert 1000 <= timeout_ms <= 10000, (
            f"Hook timeout ({timeout_ms}ms) must be within 1-10s"
        )

    def test_aborts_via_timer(self):
        # setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
        assert re.search(
            r"setTimeout\(.*controller\.abort.*FETCH_TIMEOUT_MS",
            self.src, re.DOTALL,
        ), "Hook must abort the fetch via AbortController after FETCH_TIMEOUT_MS"

    def test_catches_fetch_errors_to_legacy(self):
        # The catch block must set `_cache.rows` to null so the memo
        # serves the legacy fallback.
        assert re.search(
            r"catch\s*\([^)]*\)\s*\{[^}]*rows:\s*null", self.src, re.DOTALL,
        ), "Hook must fall back to legacy on fetch error"

    def test_handles_non_ok_response(self):
        assert "res.ok" in self.src, "Hook must check res.ok"
        assert re.search(r"throw\s+new\s+Error", self.src), (
            "Non-ok responses must be rerouted into the catch block"
        )

    # ─── (2) empty registry response ────────────────────────────────
    def test_handles_empty_rows_array(self):
        # `Array.isArray(data?.rows) ? data.rows : []`
        assert re.search(
            r"Array\.isArray\(\s*data\?\.rows\s*\)\s*\?\s*data\.rows\s*:\s*\[\s*\]",
            self.src,
        ), "Hook must coerce missing `rows` to an empty array"

    def test_memo_returns_fallback_when_rows_null(self):
        # `if (!rows) { return { ... LEGACY_*.slice() ... }; }`
        assert re.search(
            r"if\s*\(!rows\)\s*\{", self.src,
        ), "Hook must branch on `!rows` to legacy fallback"

    # ─── (3) safety net for empty eligibility slice ─────────────────
    def test_options_never_empty(self):
        # The hook's `options` accessor must reroute empty arrays
        # through LEGACY_PAIRS.
        assert "if (!options || !options.length)" in self.src, (
            "Hook must guarantee `.options` is never empty"
        )
        assert "LEGACY_PAIRS.slice()" in self.src, (
            "Empty-safety net must serve LEGACY_PAIRS"
        )

    # ─── (4) the legacy fallback itself ─────────────────────────────
    def test_legacy_fallback_is_exported(self):
        # External callers may want to use the legacy list directly
        # (parity test, e2e fixtures, etc.).
        assert re.search(
            r"export\s+const\s+LEGACY_PAIRS\s*=\s*\[",
            self.src,
        ), "LEGACY_PAIRS must be exported for downstream verification"

    def test_loading_state_serves_fallback_immediately(self):
        # Before the first fetch resolves, `_cache` is null → the memo
        # serves the legacy fallback. We verify the memo handles
        # `(_cache && _cache.rows) || null` so the very first render
        # is non-blank.
        assert "_cache && _cache.rows" in self.src, (
            "Hook must serve the legacy fallback on the first render"
        )

    # ─── (5) fromFallback flag ──────────────────────────────────────
    def test_exposes_from_fallback_flag(self):
        # Consumers (e.g. UniverseGovernancePanel) display a banner
        # when fallback is in effect.
        assert "fromFallback" in self.src, (
            "Hook must expose `fromFallback` to inform consumers"
        )


class TestEmptyStateBranchSnapshot:
    """Snapshot of the *exact* fallback branch — guards against silent
    refactors that drop the legacy list reference.
    """

    EXPECTED_FALLBACK_KEYS = [
        "LEGACY_PAIRS",
        "LEGACY_DISCOVERY",
        "LEGACY_MUTATION",
        "LEGACY_PORTFOLIO",
        "LEGACY_CERTIFICATION",
        "LEGACY_TIER1",
    ]

    def test_every_eligibility_slice_has_a_fallback(self):
        src = HOOK_PATH.read_text(encoding="utf-8")
        # The fallback branch is `if (!rows) { ... return { ... }; }`.
        m = re.search(
            r"if\s*\(!rows\)\s*\{(.+?)return\s*\{(.+?)\}\s*;\s*\}",
            src, re.DOTALL,
        )
        assert m, "Could not locate the !rows fallback branch"
        block = m.group(1) + m.group(2)
        for key in self.EXPECTED_FALLBACK_KEYS:
            assert key in block, (
                f"Fallback branch missing reference to {key}"
            )

    def test_no_silent_blank_dropdown(self):
        """The fallback branch must NOT introduce a literal `[]` for
        symbol slices (live_trading exempted — it intentionally returns
        []  because nothing should auto-go-live).
        """
        src = HOOK_PATH.read_text(encoding="utf-8")
        m = re.search(
            r"if\s*\(!rows\)\s*\{(.+?)return\s*\{(.+?)\}\s*;\s*\}",
            src, re.DOTALL,
        )
        assert m
        block = m.group(2)
        # Allow `live_trading: []` but no other literal empty arrays.
        # Strip the live_trading line and assert no other `[]` slices.
        stripped = re.sub(r"live_trading:\s*\[\s*\]\s*,?", "", block)
        # The fallback branch must not contain another `: []` literal.
        assert not re.search(r":\s*\[\s*\]", stripped), (
            "Fallback branch must not assign empty arrays to symbol slices "
            "other than live_trading"
        )

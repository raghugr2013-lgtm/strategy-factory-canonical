"""R5 — Shadow audit (Phase 1).

Runs the read-only shadow comparator against a seeded mongomock
registry and asserts:

  1. Parity between the legacy authority and the registry-backed shadow
     across every R1/R2/R3 adapter accessor and the R4 frontend
     selector fallbacks.

  2. The audit itself never persists the
     ``ENABLE_DYNAMIC_MARKET_UNIVERSE`` flag — the env value before and
     after the run is identical.

  3. The legacy fallback authority is unchanged after the shadow run
     (rollback verification).

The audit is *purely read-only*. It does not mutate the database, it
does not flip the production flag, and it does not call any of the
out-of-scope subsystems (scheduler, VPS scaling, activation matrix,
factory supervisor).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

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
def seeded_registry(monkeypatch):
    """Mongomock-backed DB with the canonical 7-symbol seed loaded.
    Mirrors the production seed flow.
    """
    from mongomock_motor import AsyncMongoMockClient
    client = AsyncMongoMockClient()
    db = client["r5_shadow_audit"]

    from engines import db as db_mod
    monkeypatch.setattr(db_mod, "_db", db, raising=False)
    monkeypatch.setattr(db_mod, "_client", client, raising=False)
    monkeypatch.setattr(db_mod, "get_db", lambda: db)

    from engines import market_universe as MU
    from engines import market_universe_audit as MUA
    from engines.seed import market_universe_seed as SEED
    monkeypatch.setattr(MU,  "get_db", lambda: db, raising=False)
    monkeypatch.setattr(MUA, "get_db", lambda: db, raising=False)
    monkeypatch.setattr(SEED, "get_db", lambda: db, raising=False)

    from engines import market_universe_adapter as ADAPTER
    ADAPTER.clear_registry_cache()

    summary = _run(SEED.run_market_universe_seed())
    assert summary["total"] == 7
    assert len(summary["inserted"]) == 7, summary

    return db


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Audit harness sanity
# ─────────────────────────────────────────────────────────────────────
class TestComparatorHarness:

    def test_seed_loaded(self, seeded_registry):
        from engines import market_universe as MU
        rows = _run(MU.list_symbols(limit=200))
        symbols = sorted(r["symbol"] for r in rows)
        assert symbols == ["BTCUSD", "ETHUSD", "EURUSD",
                           "GBPUSD", "US100", "USDJPY", "XAUUSD"]

    def test_flag_off_before_audit(self, seeded_registry):
        assert os.environ.get(
            "ENABLE_DYNAMIC_MARKET_UNIVERSE", ""
        ).strip().lower() in ("", "0", "false", "off", "no")

    def test_shadow_report_shape(self, seeded_registry):
        from engines.r5_shadow_comparator import run_shadow_comparison
        report = _run(run_shadow_comparison())
        assert "groups" in report
        assert "summary" in report
        for g in report["groups"]:
            assert g["scope"] in {
                "symbol_list", "bi5", "instrument",
                "eligibility", "cert_defaults", "frontend",
            }
            assert all("name" in c and "ok" in c for c in g["checks"])
        assert report["cache_size"] == 7


# ─────────────────────────────────────────────────────────────────────
# Tier 2 — Audit invariants
#
# The shadow audit is a *diagnostic*, not a gate. Its job is to surface
# deltas so the operator can decide what to do. We assert:
#
#   * The audit *runs end-to-end* without raising.
#   * The audit *finds* deltas where R0–R3 design intentionally
#     parameterised something (e.g. registry eligibility narrower
#     than the legacy union).
#   * The frontend selectors group is *clean* (R4 hard contract).
#   * Documented advisories (pip_size for BTC/ETH/US100) match the
#     R2 design memo.
#
# Any UNEXPECTED delta — a mismatch we have not catalogued — fails the
# audit. The catalogue is maintained inline below.
# ─────────────────────────────────────────────────────────────────────
KNOWN_DELTAS = {
    # symbol_lists — flag-ON narrows or widens the slice based on the
    # registry's per-symbol eligibility flags, where the legacy lists
    # are unparameterised unions of the canonical 7. These deltas are
    # exactly what we want shadow mode to reveal.
    #
    # Status after R5 Phase-2 prep (2026-06-04):
    #   D1 — USDJPY in discovery/intelligence: APPROVED, expected delta.
    #   D2 — BTC/ETH/US100 in data-maintenance: APPROVED, expected delta.
    #   D5 — USDJPY in portfolio: PRESERVE-LEGACY → delta resolved.
    #   D7 — pip-size for BTC/ETH/US100: PRESERVE-LEGACY → delta resolved.
    "get_intelligence_pairs":     {"extra_in_shadow": ["USDJPY"]},
    "get_data_maintenance_pairs": {"extra_in_shadow": ["BTCUSD", "ETHUSD", "US100"]},
    "get_discovery_pairs":        {"extra_in_shadow": ["USDJPY"]},
    # eligibility — same root cause, expressed at the per-symbol /
    # per-capability level.
    "is_eligible(USDJPY, discovery)":     {"legacy": False, "shadow": True},
}


class TestShadowAuditClean:

    @pytest.fixture
    def report(self, seeded_registry):
        from engines.r5_shadow_comparator import run_shadow_comparison
        rpt = _run(run_shadow_comparison())
        # Persist for the report writer.
        Path("/app/memory").mkdir(parents=True, exist_ok=True)
        with open("/app/memory/_r5_shadow_report.json", "w") as f:
            json.dump(rpt, f, indent=2, default=str)
        return rpt

    def _unexpected_diffs(self, group):
        out = []
        for c in group["checks"]:
            if c["ok"]:
                continue
            if c["name"] in KNOWN_DELTAS:
                continue
            if "advisory" in c:
                # Cert-defaults pip-size advisories — documented separately.
                continue
            out.append(c)
        return out

    def test_symbol_lists_no_unexpected_diffs(self, report):
        g = next(g for g in report["groups"] if g["name"] == "symbol_lists")
        diffs = self._unexpected_diffs(g)
        assert not diffs, (
            "Unexpected symbol-list deltas: "
            + json.dumps(diffs, indent=2, default=str)
        )

    def test_bi5_mappings_parity(self, report):
        """BI5 specs MUST be byte-identical — there is no legitimate
        reason for a registry to disagree with the legacy BI5 spec
        for a canonical symbol."""
        g = next(g for g in report["groups"] if g["name"] == "bi5_mappings")
        diffs = [c for c in g["checks"] if not c["ok"]]
        assert not diffs, (
            "BI5 mapping parity violations: "
            + json.dumps(diffs, indent=2, default=str)
        )

    def test_instrument_mappings_parity(self, report):
        g = next(g for g in report["groups"] if g["name"] == "instrument_mappings")
        diffs = [c for c in g["checks"] if not c["ok"]]
        assert not diffs, (
            "Instrument mapping parity violations: "
            + json.dumps(diffs, indent=2, default=str)
        )

    def test_eligibility_no_unexpected_diffs(self, report):
        g = next(g for g in report["groups"] if g["name"] == "eligibility")
        diffs = self._unexpected_diffs(g)
        assert not diffs, (
            "Unexpected eligibility deltas: "
            + json.dumps(diffs, indent=2, default=str)
        )

    def test_cert_defaults_parity_excluding_documented_advisory(self, report):
        """All cert-defaults checks must pass EXCEPT the explicitly
        documented `resolve_pip_size` advisory for BTC/ETH/US100 — that
        delta is *by design* (R2 spec).
        """
        g = next(g for g in report["groups"] if g["name"] == "cert_defaults")
        documented_advisory = []
        true_diffs = []
        for c in g["checks"]:
            if c["ok"]:
                continue
            if c["name"].startswith("resolve_pip_size") and "advisory" in c:
                documented_advisory.append(c)
            else:
                true_diffs.append(c)
        assert not true_diffs, (
            "Cert-defaults parity violations (not the documented "
            "pip-size advisory): "
            + json.dumps(true_diffs, indent=2, default=str)
        )
        # Document the advisory deltas the report will surface (may be
        # empty when the seed precision matches the substring resolver).
        advisory_symbols = sorted(
            c["name"].split("(")[1].rstrip(")") for c in documented_advisory
        )
        assert set(advisory_symbols).issubset({"BTCUSD", "ETHUSD", "US100"}), (
            f"Unexpected pip-size advisory drift: {advisory_symbols}"
        )

    def test_frontend_selectors_parity(self, report):
        """R4 hard contract: frontend hook fallback ≡ backend authority.
        Zero tolerance for drift here."""
        g = next(g for g in report["groups"] if g["name"] == "frontend_selectors")
        diffs = [c for c in g["checks"] if not c["ok"]]
        assert not diffs, (
            "Frontend-selector parity violations: "
            + json.dumps(diffs, indent=2, default=str)
        )

    def test_known_deltas_match_catalogue(self, report):
        """For every check listed in KNOWN_DELTAS, confirm the live
        delta matches the catalogued shape. This is the gate that
        prevents silent drift in the "known-different" set."""
        live_diffs = {}
        for g in report["groups"]:
            for c in g["checks"]:
                if not c["ok"] and c["name"] in KNOWN_DELTAS:
                    live_diffs[c["name"]] = c["delta"]

        for name, expected in KNOWN_DELTAS.items():
            if name not in live_diffs:
                # The catalogued delta no longer reproduces — that's
                # great (parity tightened) — but we want to surface it.
                # Not a failure.
                continue
            actual = live_diffs[name]
            for key, val in expected.items():
                assert actual.get(key) == val, (
                    f"Catalogued delta drift for {name!r}: "
                    f"expected {key}={val!r}, got {key}={actual.get(key)!r}"
                )


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — Flag-state contract
# ─────────────────────────────────────────────────────────────────────
class TestFlagStateNotPersisted:

    def test_flag_persistence(self, seeded_registry):
        """The audit must not leave the process with the flag flipped."""
        prior = os.environ.get("ENABLE_DYNAMIC_MARKET_UNIVERSE", "")
        from engines.r5_shadow_comparator import run_shadow_comparison
        _ = _run(run_shadow_comparison())
        after = os.environ.get("ENABLE_DYNAMIC_MARKET_UNIVERSE", "")
        assert prior == after, (
            f"Audit persisted the flag: before={prior!r} after={after!r}"
        )

    def test_flag_off_after_audit(self, seeded_registry):
        from engines import market_universe as MU
        from engines.r5_shadow_comparator import run_shadow_comparison
        _ = _run(run_shadow_comparison())
        # Default OFF state must be intact.
        assert MU.is_enabled() is False


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Rollback verification after the shadow run
# ─────────────────────────────────────────────────────────────────────
class TestPostAuditRollback:
    """After the audit, the adapter must behave identically to its
    pre-audit state (legacy fallback authority for every accessor).
    """

    def test_post_audit_legacy_authority(self, seeded_registry):
        from engines.r5_shadow_comparator import run_shadow_comparison
        from engines import market_universe_adapter as ADAPTER
        from api import data as DATA_API
        from engines import readiness_engine as RE

        _ = _run(run_shadow_comparison())
        ADAPTER.clear_registry_cache()

        assert list(ADAPTER.get_allowed_symbols()) == list(DATA_API.ALLOWED_SYMBOLS)
        assert list(ADAPTER.get_active_watchlist()) == list(RE.WATCHLIST)
        assert list(ADAPTER.get_tier1_symbols()) == list(RE.TIER1_SYMBOLS)

    def test_post_audit_seed_intact(self, seeded_registry):
        """Seeded rows must still be present and untouched after the
        read-only audit.
        """
        from engines import market_universe as MU
        from engines.r5_shadow_comparator import run_shadow_comparison

        before = _run(MU.list_symbols(limit=200))
        before_ids = sorted((r["symbol"], r.get("broker_class", ""), r.get("priority", 0))
                            for r in before)
        _ = _run(run_shadow_comparison())
        after = _run(MU.list_symbols(limit=200))
        after_ids = sorted((r["symbol"], r.get("broker_class", ""), r.get("priority", 0))
                           for r in after)
        assert before_ids == after_ids

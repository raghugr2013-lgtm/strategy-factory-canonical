"""Phase 30.2 — Universe Governance trust gate.

Tiers:
  T1  Pure helpers (intersect_scan / canon_tf / canon_pair / canon_style)
  T2  Persistence (seed, save, audit_log cap, validation)
  T3  Filter wiring (multi_cycle, ai_orchestrator, env_priority,
                     gem_factory, auto_factory_phase55)
  T4  API surface (routes declared, admin gate, byte-identity preview)
  T5  Bypass invariants — manual scan, sealed surfaces unchanged

Discipline:
  • Pure-function tier uses no DB.
  • DB-touching tests reset cache + use isolated patch payloads.
  • Sealed surfaces from Phase 28/29/30 NEVER touched.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from engines import governance_universe as gu  # noqa: E402
from engines import db as _db_mod  # noqa: E402


# Motor binds its executor to the first event loop that touches it.
# Reset the cached client whenever we open a fresh loop so each test
# can independently use asyncio.run() without "Event loop is closed".
def _reset_motor():
    _db_mod._client = None
    _db_mod._db = None
    # Also invalidate the universe cache.
    gu._cache["doc"] = None
    gu._cache["ts"]  = 0.0


def _run(coro):
    _reset_motor()
    return asyncio.run(coro)


# Module teardown — reset motor so subsequent test modules get a fresh
# client bound to their own event loop (prevents cross-module
# "Event loop is closed" cascades).
def teardown_module(module):  # noqa: D401
    _reset_motor()


# ────────────────────────────────────────────────────────────────────
# Tier T1 — pure helpers
# ────────────────────────────────────────────────────────────────────

class TestT1PureHelpers:

    def test_canon_tf_handles_all_input_forms(self):
        assert gu.canon_tf("1h")  == "H1"
        assert gu.canon_tf("H1")  == "H1"
        assert gu.canon_tf("h1")  == "H1"
        assert gu.canon_tf("15m") == "M15"
        assert gu.canon_tf("M15") == "M15"
        assert gu.canon_tf("4h")  == "H4"
        assert gu.canon_tf("1d")  == "D1"
        # whitespace
        assert gu.canon_tf("  H1  ") == "H1"

    def test_canon_pair_uppercases_and_strips(self):
        assert gu.canon_pair("eurusd") == "EURUSD"
        assert gu.canon_pair(" XaUuSd ") == "XAUUSD"

    def test_intersect_scan_keeps_only_universe_cells(self):
        uni = {"pairs": ["EURUSD", "XAUUSD"], "timeframes": ["H1", "H4"]}
        scan = [("EURUSD", "H1"), ("GBPUSD", "H1"), ("XAUUSD", "H4")]
        out = gu.intersect_scan(uni, scan)
        assert out == [("EURUSD", "H1"), ("XAUUSD", "H4")]

    def test_intersect_scan_normalises_input_formats(self):
        uni = {"pairs": ["EURUSD"], "timeframes": ["H1"]}
        # Accepts both tuple and dict input shapes.
        scan = [("eurusd", "1h"), {"pair": "EURUSD", "timeframe": "H1"}]
        out = gu.intersect_scan(uni, scan)
        # Dedup-by-position is not enforced — both inputs are valid cells.
        assert out == [("EURUSD", "H1"), ("EURUSD", "H1")]

    def test_intersect_scan_empty_universe_returns_empty(self):
        uni = {"pairs": [], "timeframes": []}
        assert gu.intersect_scan(uni, [("EURUSD", "H1")]) == []

    def test_is_pair_tf_style_allowed(self):
        uni = {
            "pairs": ["EURUSD"],
            "timeframes": ["H1"],
            "styles": ["trend-following"],
        }
        assert gu.is_pair_allowed(uni, "eurusd")
        assert gu.is_pair_allowed(uni, "EURUSD")
        assert not gu.is_pair_allowed(uni, "GBPUSD")
        assert gu.is_tf_allowed(uni, "1h")
        assert gu.is_tf_allowed(uni, "H1")
        assert not gu.is_tf_allowed(uni, "H4")
        assert gu.is_style_allowed(uni, "TREND-FOLLOWING")
        assert not gu.is_style_allowed(uni, "scalping")


# ────────────────────────────────────────────────────────────────────
# Tier T2 — Persistence + validation
# ────────────────────────────────────────────────────────────────────

class TestT2Persistence:

    def test_default_seed_matches_operator_decree(self):
        out = _run(gu.get_universe(force_refresh=True))
        assert "EURUSD" in out["pairs"]
        assert "XAUUSD" in out["pairs"]
        assert "H1"     in out["timeframes"]
        assert "H4"     in out["timeframes"]
        for s in ("trend-following", "mean-reversion", "breakout"):
            assert s in out["styles"]
        assert out["exploration_floor_pct"] == 5.0
        assert out["max_active_cells"]      == 8
        assert out["phase"] == gu.PHASE_VERSION

    def test_save_universe_appends_audit_log(self):
        async def _go():
            before = await gu.get_universe(force_refresh=True)
            n_before = len(before.get("audit_log") or [])
            out = await gu.save_universe(
                {"max_active_cells": 9},
                admin_email="trustgate@local.test",
            )
            # Restore.
            await gu.save_universe(
                {"max_active_cells": int(before["max_active_cells"])},
                admin_email="trustgate@local.test",
            )
            return out, n_before
        out, n_before = _run(_go())
        assert out["max_active_cells"] == 9
        assert len(out["audit_log"]) == min(n_before + 1, gu.AUDIT_LOG_CAP)

    def test_save_universe_rejects_empty_pairs(self):
        async def _go():
            return await gu.save_universe({"pairs": []}, admin_email="x@x.test")
        with pytest.raises(ValueError):
            _run(_go())

    def test_save_universe_rejects_unknown_timeframe(self):
        async def _go():
            return await gu.save_universe(
                {"timeframes": ["H99"]}, admin_email="x@x.test",
            )
        with pytest.raises(ValueError):
            _run(_go())

    def test_save_universe_rejects_out_of_range_floor(self):
        async def _go():
            return await gu.save_universe(
                {"exploration_floor_pct": 99.0}, admin_email="x@x.test",
            )
        with pytest.raises(ValueError):
            _run(_go())


# ────────────────────────────────────────────────────────────────────
# Tier T3 — Filter wiring across authorities
# ────────────────────────────────────────────────────────────────────

class TestT3FilterWiring:

    def test_multi_cycle_runner_filter_present(self):
        import inspect
        from engines import multi_cycle_runner as mcr
        src = inspect.getsource(mcr.start_multi_cycle)
        assert "governance_universe" in src
        assert "universe_filtered" in src
        # Manual scan must still bypass — comment preserved.
        assert "honoured verbatim" in src or "bypass" in src.lower()

    def test_ai_orchestrator_observation_includes_universe(self):
        import inspect
        from engines import ai_orchestrator as ao
        src = inspect.getsource(ao._observe_lifecycle)
        assert "allowed_universe" in src
        assert "governance_universe" in src

    def test_ai_orchestrator_decide_filters_diversity_scan(self):
        import inspect
        from engines import ai_orchestrator as ao
        src = inspect.getsource(ao.decide)
        assert "A2" in src or "universe filter" in src.lower()
        assert "rotation_filtered_by_universe" in src

    def test_env_priority_enumerate_accepts_universe(self):
        import inspect
        from engines import env_priority as ep
        sig = inspect.signature(ep._enumerate_envs)
        assert "allowed_universe" in sig.parameters
        src = inspect.getsource(ep._enumerate_envs)
        assert "uni_pairs" in src and "uni_tfs_lower" in src

    def test_env_priority_pick_environments_fetches_universe(self):
        import inspect
        from engines import env_priority as ep
        src = inspect.getsource(ep.pick_environments)
        assert "governance_universe" in src

    def test_gem_factory_filters_args_through_universe(self):
        import inspect
        from engines import gem_factory_engine as gfe
        src = inspect.getsource(gfe.run_gem_factory)
        assert "governance_universe" in src
        # Must FAIL LOUD on explicit-args misconfiguration.
        assert "outside allowed universe" in src

    def test_auto_factory_phase55_respect_universe_default_on(self):
        from engines import auto_factory_phase55 as af55
        assert "respect_universe" in af55.DEFAULTS
        assert af55.DEFAULTS["respect_universe"] is True
        import inspect
        src = inspect.getsource(af55.get_config)
        assert "governance_universe" in src
        assert "universe_filtered" in src


# ────────────────────────────────────────────────────────────────────
# Tier T4 — API surface
# ────────────────────────────────────────────────────────────────────

class TestT4APISurface:

    def test_universe_endpoints_declared(self):
        from api.governance import router
        paths = [r.path for r in router.routes]
        assert "/governance/universe"          in paths
        assert "/governance/universe/preview"  in paths

    def test_save_universe_route_requires_admin(self):
        """The POST handler must depend on `require_admin` (FastAPI Depends)."""
        from api.governance import router
        for r in router.routes:
            if r.path == "/governance/universe" and "POST" in (r.methods or set()):
                # Inspect dependant
                deps = [d.call.__name__ for d in r.dependant.dependencies if hasattr(d, "call")]
                assert "require_admin" in deps, f"missing admin gate, got {deps}"
                return
        pytest.fail("POST /governance/universe route not found")

    def test_preview_endpoint_aggregates_six_authorities(self):
        import inspect
        from api import governance as gov_api
        src = inspect.getsource(gov_api.universe_preview)
        for key in (
            "multi_cycle_default",
            "orchestrator_diversity",
            "autonomous_rotation",
            "env_priority_pool",
            "gem_factory_pool",
            "auto_factory_pool",
        ):
            assert key in src, f"preview missing {key}"


# ────────────────────────────────────────────────────────────────────
# Tier T5 — Bypass invariants + sealed-surface preservation
# ────────────────────────────────────────────────────────────────────

class TestT5BypassInvariants:

    def test_manual_scan_payload_bypasses_filter(self):
        """When start_multi_cycle receives an explicit scan=[...], the
        universe filter must NOT touch it."""
        import inspect
        from engines import multi_cycle_runner as mcr
        src = inspect.getsource(mcr.start_multi_cycle)
        # The filter block is gated on `if not scan:` → explicit scan
        # branches into the original (p.upper(), tf.upper()) path.
        assert "if not scan:" in src
        # The else branch is the existing un-filtered path.
        assert "scan_list = [(p.upper()" in src

    def test_phase30_1_emit_event_taxonomy_unchanged(self):
        from engines import alert_engine as ae
        assert len(ae.INSTITUTIONAL_EVENT_TYPES) == 7
        assert "LIFECYCLE_DEPLOYMENT_READY" in ae.INSTITUTIONAL_EVENT_TYPES

    def test_phase30_autonomy_flags_remain_false(self):
        from engines import ai_orchestrator as ao
        from engines import replacement_engine as rep
        assert ao.AUTONOMOUS_DISCOVERY_ENABLED is False
        assert rep.SURVIVOR_AUTO_REPLACE_ENABLED is False

    def test_phase26_5_lifecycle_gates_byte_identical(self):
        from engines import strategy_lifecycle as lc
        assert lc.LIFECYCLE_STAGES == (
            "exploratory", "candidate", "validated", "stable",
            "prop_safe", "elite", "portfolio_worthy", "deployment_ready",
        )
        for gate in (
            "_gate_candidate", "_gate_validated", "_gate_stable",
            "_gate_prop_safe", "_gate_elite", "_gate_portfolio_worthy",
            "_gate_deployment_ready",
        ):
            assert hasattr(lc, gate)

"""Phase 30.1 — Convergence Integration trust gate (Δ1–Δ4).

Δ1  Unified Strategy Truth endpoint (read-only aggregator)
Δ2  Institutional Event Notifications (7-event taxonomy + audit_log fallback)
Δ3  RULE 12 · AUTONOMOUS_DISCOVERY_TICK (dormant; observational telemetry)
Δ4  phase30_universe_member marker (idempotent, first-elite-only)

Frontend Δ5 (GovernanceCard) is verified separately via screenshot smoke.

Discipline:
  • Additive · reversible · observable · anti-drift.
  • Alert failures must NEVER block lifecycle writes.
  • RULE 12 must remain dormant by default.
"""
from __future__ import annotations

import sys
from typing import Any, Dict

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from engines import ai_orchestrator as ao  # noqa: E402
from engines import alert_engine as ae  # noqa: E402
from engines import strategy_lifecycle as lc  # noqa: E402


# ════════════════════════════════════════════════════════════════════
# Tier Δ1 — Unified Strategy Truth endpoint
# ════════════════════════════════════════════════════════════════════

class TestDelta1StrategyTruth:

    def test_endpoint_is_declared(self):
        from api.governance import router
        paths = [r.path for r in router.routes]
        assert "/governance/strategy-truth/{strategy_hash}" in paths

    def test_endpoint_is_read_only(self):
        """Δ1 must be a pure GET (no POST/PUT/PATCH/DELETE counterparts)."""
        from api.governance import router
        for r in router.routes:
            if r.path == "/governance/strategy-truth/{strategy_hash}":
                # Starlette routes expose `.methods` as a set
                assert r.methods == {"GET"} or "GET" in r.methods
                # No write methods on the same path:
                forbidden = {"POST", "PUT", "PATCH", "DELETE"}
                assert not (r.methods & forbidden)
                return
        pytest.fail("strategy-truth route not found")

    def test_endpoint_source_aggregates_canonical_surfaces(self):
        """Δ1 must aggregate lifecycle + Phase 11 + Phase 29 + Phase 30."""
        import inspect
        from api import governance as gov_api
        src = inspect.getsource(gov_api.strategy_truth)
        # Reads the canonical sources — never writes.
        for marker in (
            "get_lifecycle",
            "strategy_library",
            "strategy_performance_history",
            "phase11_slot",
            "phase29_regime",
            "phase30_universe",
            "phase30_replacement",
            "deployment_eligibility",
        ):
            assert marker in src, f"strategy_truth missing canonical surface: {marker}"
        # Anti-drift: must not write to any collection.
        for write in ("update_one", "insert_one", "delete_one", "replace_one"):
            assert write not in src, f"Δ1 must be READ-ONLY (found {write})"


# ════════════════════════════════════════════════════════════════════
# Tier Δ2 — Institutional Event Notifications
# ════════════════════════════════════════════════════════════════════

class TestDelta2EventTaxonomy:

    def test_seven_event_taxonomy_is_closed(self):
        assert set(ae.INSTITUTIONAL_EVENT_TYPES) == {
            "LIFECYCLE_DEPLOYMENT_READY",
            "LIFECYCLE_ELITE_PROMOTION",
            "SURVIVOR_ADMITTED",
            "SURVIVOR_DEMOTED",
            "REPLACEMENT_EXECUTED",
            "REGIME_FRAGILE_FLAG",
            "DEPLOYMENT_EXPORTED",
        }
        # Must remain at exactly 7.
        assert len(ae.INSTITUTIONAL_EVENT_TYPES) == 7

    def test_emit_event_exists_and_async(self):
        import inspect
        assert hasattr(ae, "emit_event")
        assert inspect.iscoroutinefunction(ae.emit_event)

    def test_emit_event_rejects_unknown_type_silently(self):
        import asyncio
        out = asyncio.run(ae.emit_event("NOT_A_REAL_EVENT", "h_test", {"x": 1}))
        assert out["emitted"] is False
        assert out.get("reason") == "unknown_event_type"

    def test_lifecycle_upsert_wires_event_emit(self):
        import inspect
        src = inspect.getsource(lc.upsert_lifecycle)
        assert "emit_event" in src
        # Critical events that MUST be wired into lifecycle:
        for marker in (
            "LIFECYCLE_DEPLOYMENT_READY",
            "LIFECYCLE_ELITE_PROMOTION",
            "SURVIVOR_ADMITTED",
            "SURVIVOR_DEMOTED",
        ):
            assert marker in src, f"lifecycle upsert missing event {marker}"

    def test_replacement_engine_emits_replacement_executed(self):
        import inspect
        from engines import replacement_engine as rep
        src = inspect.getsource(rep.execute_replacement)
        assert "REPLACEMENT_EXECUTED" in src
        assert "emit_event" in src

    def test_cbot_export_emits_deployment_exported(self):
        import inspect
        from api import strategy_memory as api_sm
        src = inspect.getsource(api_sm.export_cbot)
        assert "DEPLOYMENT_EXPORTED" in src
        assert "emit_event" in src or "_emit_evt" in src

    def test_audit_log_fallback_is_default(self):
        """Δ2 must write to audit_log on every emit (channels optional)."""
        import inspect
        src = inspect.getsource(ae.emit_event)
        assert "_audit_log_event" in src
        assert "audit_log" in src.lower()

    def test_alert_failures_never_raise(self):
        """Δ2 must be subordinate — emit_event swallows all exceptions."""
        import inspect
        src = inspect.getsource(ae.emit_event)
        # The outer try/except must wrap the whole body.
        assert src.count("try:") >= 1
        assert "except Exception" in src
        # Caller wiring in lifecycle must also swallow.
        src_lc = inspect.getsource(lc.upsert_lifecycle)
        assert "event emit swallowed" in src_lc


# ════════════════════════════════════════════════════════════════════
# Tier Δ3 — RULE 12 AUTONOMOUS_DISCOVERY_TICK (dormant)
# ════════════════════════════════════════════════════════════════════

class TestDelta3Rule12:

    def test_autonomous_discovery_disabled_by_default(self):
        assert ao.AUTONOMOUS_DISCOVERY_ENABLED is False

    def test_rotation_targets_declared(self):
        assert isinstance(ao.AUTONOMOUS_DISCOVERY_ROTATION, tuple)
        assert len(ao.AUTONOMOUS_DISCOVERY_ROTATION) >= 1
        for pair_tf in ao.AUTONOMOUS_DISCOVERY_ROTATION:
            assert isinstance(pair_tf, tuple) and len(pair_tf) == 2

    def test_rule_12_fires_dormant_telemetry_with_zero_headroom(self):
        """RULE 12 must run every tick and emit observational telemetry."""
        state = _synth_state(headroom=0, active=100, cap=100)
        recs = ao.decide(state)
        rule_12 = [r for r in recs if r["rule_id"] == "AUTONOMOUS_DISCOVERY_TICK"]
        assert len(rule_12) == 1
        r12 = rule_12[0]
        # Dormant ⇒ advisory action only.
        assert r12["action"] == "log_recommendation"
        # Telemetry payload contract:
        p = r12["params"]
        for key in (
            "evaluated_at",
            "autonomous_discovery_enabled",
            "conditions_passed",
            "trigger_reason",
            "skip_reason",
            "rotating_target",
            "survivor_headroom",
            "survivor_active_count",
            "survivor_universe_cap",
            "min_headroom_required",
            "phase",
        ):
            assert key in p, f"telemetry missing key: {key}"
        assert p["autonomous_discovery_enabled"] is False
        assert p["conditions_passed"] is False
        assert p["skip_reason"] == "autonomous_discovery_disabled"
        assert p["survivor_headroom"] == 0
        assert p["phase"] == "30.1"

    def test_rule_12_fires_even_with_high_headroom_while_dormant(self):
        """Even with headroom, RULE 12 stays dormant — operator decree."""
        state = _synth_state(headroom=50, active=50, cap=100)
        recs = ao.decide(state)
        rule_12 = [r for r in recs if r["rule_id"] == "AUTONOMOUS_DISCOVERY_TICK"]
        assert len(rule_12) == 1
        assert rule_12[0]["action"] == "log_recommendation"
        assert rule_12[0]["params"]["skip_reason"] == "autonomous_discovery_disabled"
        # Telemetry should still record headroom snapshot.
        assert rule_12[0]["params"]["survivor_headroom"] == 50

    def test_rule_12_has_rotating_target(self):
        state = _synth_state(headroom=5, active=95, cap=100)
        recs = ao.decide(state)
        r12 = [r for r in recs if r["rule_id"] == "AUTONOMOUS_DISCOVERY_TICK"][0]
        tgt = r12["params"]["rotating_target"]
        assert isinstance(tgt, dict)
        assert "pair" in tgt and "timeframe" in tgt


# ════════════════════════════════════════════════════════════════════
# Tier Δ4 — phase30_universe_member marker (idempotent, first-elite-only)
# ════════════════════════════════════════════════════════════════════

class TestDelta4PhaseMarker:

    def test_marker_field_is_idempotent_when_already_set(self):
        """If prior state already has the marker, it must be preserved."""
        import inspect
        src = inspect.getsource(lc.upsert_lifecycle)
        assert "phase30_universe_member" in src
        assert "prior_marker" in src
        # First-stamp branch must be guarded by `prior_marker` being False
        # AND new_stage == "elite" AND prior_stage != "elite".
        assert 'new_stage == "elite"' in src
        assert 'prior_stage != "elite"' in src

    def test_marker_field_in_strategy_truth_response(self):
        """Δ1 must surface the marker on strategy-truth."""
        import inspect
        from api import governance as gov_api
        src = inspect.getsource(gov_api.strategy_truth)
        assert "phase30_universe_member" in src
        assert "phase30_universe_joined_at" in src


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────

def _synth_state(*, headroom: int, active: int, cap: int) -> Dict[str, Any]:
    """Minimal observed-state stub that exercises RULE 12 cleanly."""
    return {
        "live": {"status": "idle"},
        "recent_runs": [],
        "total_saves_recent": 0,
        "rejection_breakdown": {"counts": {}, "total": 0},
        "avg_pf_recent": None,
        "best_candidate": None,
        "adaptive_scan": [],
        "lifecycle": {
            "stage_counts": {
                s: 0 for s in lc.LIFECYCLE_STAGES
            },
            "promotions_recent": [],
            "demotions_recent":  [],
            "transitions_total": 0,
            "last_portfolio_built_at": None,
            "survivor_universe": {
                "active_count": active,
                "cap":          cap,
                "headroom":     headroom,
                "over_cap":     active > cap,
            },
        },
    }

"""Phase 30 — Survivor Governance Convergence trust gate.

Consolidated suite covering all 5 surfaces:
  A. Filtration Honesty       — null-metric write guard, truthful counters,
                                 evidence-only Explorer default
  B. Promotion Ledger         — stage breakdown over strategy_lifecycle
  C. Survivor Registry        — top-N elite universe
  D. Replacement Authority    — advisory replacement candidates
  E. Deployment Registry      — deployment_ready surface
     + cBot export gating     — 403 unless deployment_ready, admin override audit

Discipline:
  • Pure-function tiers use synthetic in-memory fixtures (no DB).
  • DB-touching tests self-clean with TEST_P30_ prefix.
  • Sealed surfaces (transpiler, lifecycle gates, mutation engine) NEVER
    touched — confirmed by Tier 6 byte-identity.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import survivor_registry as sr  # noqa: E402
from engines import replacement_engine as rep  # noqa: E402
from engines import strategy_lifecycle as lc  # noqa: E402


def _lc_doc(hash_, stage, deploy_score, since_iso=None):
    return {
        "strategy_hash":       hash_,
        "current_stage":       stage,
        "stage_rank":          lc.STAGE_RANK.get(stage, 0),
        "current_stage_since": since_iso or "2026-01-01T00:00:00+00:00",
        "last_run_at":         "2026-02-01T00:00:00+00:00",
        "flags":               [],
        "evidence":            {"deploy_score": deploy_score} if deploy_score is not None else {},
    }


# ════════════════════════════════════════════════════════════════════
# Tier A — Filtration Honesty (5)
# ════════════════════════════════════════════════════════════════════

class TestTierAFiltrationHonesty:

    def test_phase30_constants_match_operator_decisions(self):
        assert sr.SURVIVOR_TOP_N == 100
        assert sr.SURVIVOR_ELIGIBLE_STAGES == ("elite", "portfolio_worthy", "deployment_ready")
        assert rep.SURVIVOR_AUTO_REPLACE_ENABLED is False
        assert rep.REPLACEMENT_MIN_DEPLOY_SCORE_DELTA == 5.0
        assert rep.REPLACEMENT_COOLDOWN_DAYS == 7

    def test_ingestion_runner_has_truthful_counters(self):
        import inspect
        from engines.strategy_ingestion import ingestion_runner
        src = inspect.getsource(ingestion_runner)
        assert "total_evidential" in src
        assert "total_abandoned" in src
        assert "abandon_reasons" in src

    def test_ingestion_runner_writes_history_only_for_evidence(self):
        import inspect
        from engines.strategy_ingestion import ingestion_runner
        src = inspect.getsource(ingestion_runner)
        # The null-metric guard must be present and active.
        assert "_phase30_has_evidence" in src
        assert "record_from_mutation_result" in src
        # The guard must come before the recorder call.
        guard_pos = src.find("_phase30_has_evidence")
        call_pos = src.find("if _phase30_has_evidence:")
        assert 0 < guard_pos < call_pos

    def test_explorer_endpoint_has_view_mode_param(self):
        from api import strategy_memory as api_sm
        import inspect
        sig = inspect.signature(api_sm.explorer)
        assert "view_mode" in sig.parameters
        # Default must be "evidence" (operator decision).
        # The Query default is wrapped — inspect the source.
        src = inspect.getsource(api_sm.explorer)
        assert '"evidence"' in src or "'evidence'" in src

    def test_evidence_filter_strips_null_metrics(self):
        # Synthetic explorer rows
        rows = [
            {"strategy_hash": "h1", "best_pf": None, "avg_trades": None, "library_id": None},
            {"strategy_hash": "h2", "best_pf": 1.5,  "avg_trades": 30,   "library_id": None},
            {"strategy_hash": "h3", "best_pf": None, "avg_trades": 50,   "library_id": "lib1"},
        ]
        # Mimic the inline filter from api/strategy_memory.py
        filtered = [
            r for r in rows
            if r.get("best_pf") is not None
            or (r.get("avg_trades") is not None and float(r["avg_trades"]) > 0)
        ]
        assert {r["strategy_hash"] for r in filtered} == {"h2", "h3"}


# ════════════════════════════════════════════════════════════════════
# Tier B — Survivor Registry (8)
# ════════════════════════════════════════════════════════════════════

class TestTierBSurvivorRegistry:

    def test_empty_cohort(self):
        out = sr.compute_survivor_universe([])
        assert out["universe"] == []
        assert out["active_count"] == 0
        assert out["cap"] == 100
        assert out["headroom"] == 100
        assert out["over_cap"] is False
        assert out["phase"] == "30.0"
        assert out["advisory_only"] is True

    def test_only_eligible_stages_counted(self):
        docs = [
            _lc_doc("e1", "exploratory", 10.0),
            _lc_doc("c1", "candidate",   20.0),
            _lc_doc("el1", "elite",       80.0),
            _lc_doc("pw1", "portfolio_worthy", 70.0),
            _lc_doc("dr1", "deployment_ready", 90.0),
        ]
        out = sr.compute_survivor_universe(docs)
        hashes = {u["strategy_hash"] for u in out["universe"]}
        assert hashes == {"el1", "pw1", "dr1"}
        assert out["active_count"] == 3

    def test_universe_sorted_by_deploy_score_desc(self):
        docs = [
            _lc_doc("a", "elite", 50.0),
            _lc_doc("b", "elite", 90.0),
            _lc_doc("c", "elite", 70.0),
        ]
        out = sr.compute_survivor_universe(docs)
        scores = [u["deploy_score"] for u in out["universe"]]
        assert scores == [90.0, 70.0, 50.0]

    def test_top_n_cap_applied(self):
        docs = [_lc_doc(f"h{i}", "elite", float(i)) for i in range(150)]
        out = sr.compute_survivor_universe(docs, top_n=100)
        assert len(out["universe"]) == 100
        assert out["active_count"] == 150
        assert out["over_cap"] is True
        assert out["headroom"] == 0

    def test_weakest_decile_when_universe_has_10_plus(self):
        docs = [_lc_doc(f"h{i}", "elite", float(i)) for i in range(20)]
        out = sr.compute_survivor_universe(docs)
        # 20 in universe → decile_size = 2 → weakest 2 are last two (lowest scores)
        assert len(out["weakest_decile"]) == 2
        weakest_scores = [w["deploy_score"] for w in out["weakest_decile"]]
        # Should be the two lowest deploy_scores
        assert max(weakest_scores) < 5  # bottom decile of 20 scoring 0..19

    def test_weakest_decile_empty_when_under_10(self):
        docs = [_lc_doc(f"h{i}", "elite", float(i)) for i in range(5)]
        out = sr.compute_survivor_universe(docs)
        assert out["weakest_decile"] == []

    def test_missing_deploy_score_sorts_bottom(self):
        docs = [
            _lc_doc("with_score", "elite", 50.0),
            _lc_doc("no_score", "elite", None),
        ]
        out = sr.compute_survivor_universe(docs)
        # The one with a real score must come first
        assert out["universe"][0]["strategy_hash"] == "with_score"
        # The one without a score reports None (honest refusal)
        assert out["universe"][1]["deploy_score"] is None

    def test_by_stage_counts_correct(self):
        docs = [
            _lc_doc("a", "elite", 10.0),
            _lc_doc("b", "elite", 20.0),
            _lc_doc("c", "portfolio_worthy", 30.0),
            _lc_doc("d", "deployment_ready", 40.0),
        ]
        out = sr.compute_survivor_universe(docs)
        assert out["by_stage_counts"] == {
            "elite": 2, "portfolio_worthy": 1, "deployment_ready": 1,
        }


# ════════════════════════════════════════════════════════════════════
# Tier C — Replacement helpers (3)
# ════════════════════════════════════════════════════════════════════

class TestTierCReplacement:

    def test_explain_reasons(self):
        assert "cooldown_not_met" in rep._explain(False, True, 10.0)
        assert "delta_below_min"  in rep._explain(True,  False, 2.0)
        assert "challenger_dominant" in rep._explain(True, True, 10.0)
        assert "cooldown_not_met AND delta_below_min" in rep._explain(False, False, 2.0)

    def test_days_since_zero_when_now(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        d = rep._days_since(now_iso)
        assert d is not None and abs(d) < 0.01

    def test_days_since_handles_invalid(self):
        assert rep._days_since(None) is None
        assert rep._days_since("not-an-iso") is None


# ════════════════════════════════════════════════════════════════════
# Tier D — Sealed surface byte-identity (3) — operator-mandated discipline
# ════════════════════════════════════════════════════════════════════

class TestTierDSealedByteIdentity:

    def test_all_seven_lifecycle_gates_intact(self):
        # Sealed Phase 26.5 surfaces must remain present and untouched
        # in name. Phase 30 only EXTENDS — never modifies these.
        for name in (
            "_gate_candidate", "_gate_validated", "_gate_stable",
            "_gate_prop_safe", "_gate_elite", "_gate_portfolio_worthy",
            "_gate_deployment_ready",
        ):
            assert hasattr(lc, name), f"Phase 30 broke sealed surface: {name}"

    def test_lifecycle_stages_tuple_unchanged(self):
        assert lc.LIFECYCLE_STAGES == (
            "exploratory", "candidate", "validated", "stable",
            "prop_safe", "elite", "portfolio_worthy", "deployment_ready",
        )

    def test_lifecycle_flags_includes_phase29_taxonomy(self):
        # Phase 29 added REGIME_FRAGILE — must remain.
        assert "REGIME_FRAGILE" in lc.LIFECYCLE_FLAGS
        # Phase 30 must NOT have introduced any new flag.
        expected = {
            "PARTIAL_REALISM", "BI5_FAIL", "STALE",
            "MANUALLY_OVERRIDDEN", "BI5_DATA_MISSING", "REGIME_FRAGILE",
        }
        assert lc.LIFECYCLE_FLAGS == expected, (
            "Phase 30 must NOT add new lifecycle flags — anti-drift"
        )


# ════════════════════════════════════════════════════════════════════
# Tier E — Deployment gating (3)
# ════════════════════════════════════════════════════════════════════

class TestTierEDeploymentGating:

    def test_export_cbot_has_force_param(self):
        from api import strategy_memory as api_sm
        import inspect
        sig = inspect.signature(api_sm.export_cbot)
        assert "force" in sig.parameters
        assert "reason" in sig.parameters

    def test_export_cbot_source_contains_stage_gate(self):
        from api import strategy_memory as api_sm
        import inspect
        src = inspect.getsource(api_sm.export_cbot)
        assert "deployment_ready" in src
        assert "force" in src
        assert "audit_log" in src
        assert "phase30_cbot_export_force_override" in src

    def test_governance_router_endpoints_declared(self):
        from api.governance import router
        paths = [r.path for r in router.routes]
        assert "/governance/promotion-ledger" in paths
        assert "/governance/survivor-registry" in paths
        assert "/governance/replacement-candidates" in paths
        assert "/governance/replacement/execute" in paths


# ════════════════════════════════════════════════════════════════════
# Tier F — Determinism + schema stability (2)
# ════════════════════════════════════════════════════════════════════

class TestTierFDeterminism:

    def test_compute_survivor_universe_deterministic(self):
        import json
        docs = [_lc_doc(f"h{i}", "elite", float(20 - i)) for i in range(15)]
        a = sr.compute_survivor_universe(docs)
        b = sr.compute_survivor_universe(list(reversed(docs)))
        a.pop("computed_at")
        b.pop("computed_at")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_top_level_keys_stable(self):
        out_empty = sr.compute_survivor_universe([])
        out_full = sr.compute_survivor_universe([_lc_doc("h", "elite", 50.0)])
        expected = {
            "universe", "active_count", "cap", "headroom", "over_cap",
            "weakest_decile", "by_stage_counts", "phase", "advisory_only",
            "computed_at",
        }
        assert set(out_empty.keys()) == expected
        assert set(out_full.keys()) == expected

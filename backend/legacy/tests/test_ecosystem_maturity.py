"""Ecosystem Exploration Governance — Maturity Detection trust gate."""
from __future__ import annotations

import asyncio
import sys

import pytest

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/app/backend/.env")

from engines import ecosystem_maturity as em  # noqa: E402
from engines import db as _db_mod  # noqa: E402


def _reset_motor():
    _db_mod._client = None
    _db_mod._db = None


def _run(coro):
    _reset_motor()
    return asyncio.run(coro)


def teardown_module(module):  # noqa: D401
    _reset_motor()


# ────────────────────────────────────────────────────────────────────
# Tier T1 — Public surface contract
# ────────────────────────────────────────────────────────────────────

class TestT1Surface:

    def test_phase_order_is_strict_and_complete(self):
        assert em.PHASE_ORDER == (
            "EG-1", "EG-2", "EG-3", "EG-4", "EG-5", "EG-6",
        )

    def test_phase_names_match_roadmap_document(self):
        assert em.PHASE_NAMES["EG-1"] == "Universe Boundary Governance"
        assert em.PHASE_NAMES["EG-2"] == "Exploration Memory Layer"
        assert em.PHASE_NAMES["EG-3"] == "Rotational Ecosystem Scheduler"
        assert em.PHASE_NAMES["EG-4"] == "Adaptive Allocation Observation"
        assert em.PHASE_NAMES["EG-5"] == "Exploration vs Exploitation Governance"
        assert em.PHASE_NAMES["EG-6"] == "Full Ecosystem Autonomy"

    def test_eg_1_sealed_on_initial_load(self):
        """EG-1 = universe governance, sealed in Phase 30.2."""
        assert "EG-1" in em.SEALED_PHASES
        # All other phases are NOT auto-sealed.
        for pid in ("EG-2", "EG-3", "EG-4", "EG-5", "EG-6"):
            assert pid not in em.SEALED_PHASES


# ────────────────────────────────────────────────────────────────────
# Tier T2 — Signal-math correctness
# ────────────────────────────────────────────────────────────────────

class TestT2SignalMath:

    def test_eg_1_evaluator_reports_sealed(self):
        out = _run(em._evaluate_eg_1())
        assert out["phase"] == "EG-1"
        assert out["current_status"] == "sealed"
        assert out["ready_to_activate"] is False   # already sealed
        assert out["blockers"] == []

    def test_eg_2_requires_universe_age_and_perf_history(self):
        out = _run(em._evaluate_eg_2())
        # Empty perf history → blocker. Accept either "rows" or unreachable
        # marker depending on motor binding state during this test run.
        joined = " | ".join(out["blockers"])
        assert (
            "strategy_performance_history" in joined
            or "Universe age" in joined
        ), f"expected EG-2 blockers, got: {joined!r}"

    def test_eg_3_requires_memory_collection(self):
        out = _run(em._evaluate_eg_3())
        assert any("ecosystem_cell_memory" in b for b in out["blockers"])
        assert any("EG-2" in b for b in out["blockers"])

    def test_eg_4_requires_rule_13_history(self):
        out = _run(em._evaluate_eg_4())
        assert any("EG-3" in b for b in out["blockers"])
        assert any("RULE 13" in b for b in out["blockers"])

    def test_eg_5_requires_eg_4_and_phase_30_4(self):
        out = _run(em._evaluate_eg_5())
        assert any("EG-4" in b for b in out["blockers"])
        # Phase 30.4 (auto_replace_enabled) must be flipped — currently False.
        assert any("auto_replace_enabled" in b for b in out["blockers"])

    def test_eg_6_is_deferred(self):
        out = _run(em._evaluate_eg_6())
        assert out["current_status"] == "deferred"
        assert out["ready_to_activate"] is False
        # Must include explicit "deferred indefinitely" blocker.
        assert any("deferred indefinitely" in b for b in out["blockers"])


# ────────────────────────────────────────────────────────────────────
# Tier T3 — Dependency-chain invariants
# ────────────────────────────────────────────────────────────────────

class TestT3DependencyChain:

    def test_deps_strictly_grow(self):
        for i, pid in enumerate(em.PHASE_ORDER):
            deps = set(em.PHASE_DEPS[pid])
            expected_prefix = set(em.PHASE_ORDER[:i])
            assert deps == expected_prefix, (
                f"{pid} dependency set {deps} != strict prefix {expected_prefix}"
            )

    def test_every_phase_has_evaluator(self):
        for pid in em.PHASE_ORDER:
            assert pid in em._EVALUATORS

    def test_evaluate_all_returns_every_phase(self):
        snap = _run(em.evaluate_all())
        assert [p["phase"] for p in snap["phases"]] == list(em.PHASE_ORDER)


# ────────────────────────────────────────────────────────────────────
# Tier T4 — API endpoint
# ────────────────────────────────────────────────────────────────────

class TestT4APIShape:

    def test_endpoint_is_declared(self):
        from api.governance import router
        paths = [r.path for r in router.routes]
        assert "/governance/ecosystem-maturity" in paths

    def test_endpoint_is_read_only_get(self):
        from api.governance import router
        for r in router.routes:
            if r.path == "/governance/ecosystem-maturity":
                assert "GET" in (r.methods or set())
                assert not (r.methods & {"POST", "PUT", "PATCH", "DELETE"})
                return
        pytest.fail("/governance/ecosystem-maturity not declared")

    def test_snapshot_payload_advertises_advisory_only(self):
        snap = _run(em.evaluate_all())
        assert snap["advisory_only"] is True
        assert "operator decree" in snap["operator_authority"].lower()


# ────────────────────────────────────────────────────────────────────
# Tier T5 — Anti-drift / read-only invariants
# ────────────────────────────────────────────────────────────────────

class TestT5AntiDrift:

    def test_module_does_not_import_any_write_path(self):
        import inspect
        src = inspect.getsource(em)
        for forbidden in (
            "update_one",
            "insert_one",
            "delete_one",
            "replace_one",
            "find_one_and_update",
        ):
            assert forbidden not in src, (
                f"ecosystem_maturity must be READ-ONLY (found `{forbidden}`)"
            )

    def test_no_autonomous_activation_helpers(self):
        public = [n for n in dir(em) if not n.startswith("_")]
        for forbidden in (
            "activate_phase", "seal_phase", "transition_phase",
            "set_exploration_pct", "trigger_rotation",
            "trigger_allocation_advisory",
        ):
            assert forbidden not in public, (
                f"ecosystem_maturity exposes activation helper `{forbidden}` — forbidden"
            )

    def test_sealed_phases_is_module_constant(self):
        assert isinstance(em.SEALED_PHASES, tuple)

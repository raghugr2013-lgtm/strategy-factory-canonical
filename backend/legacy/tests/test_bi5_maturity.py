"""BI5 Maturity Detection Framework — trust gate.

Tiers:
  T1  Public surface contract — phase order, names, deps
  T2  Signal-math correctness — pure-function pieces of each evaluator
  T3  Dependency-chain invariants — strict ordering, deps satisfied
  T4  API endpoint shape — advisory-only payload
  T5  Anti-drift — read-only, no auto-activation paths
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

from engines import bi5_maturity as bm  # noqa: E402
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
        assert bm.PHASE_ORDER == (
            "BI5-1", "BI5-2", "BI5-3", "BI5-4", "BI5-5", "BI5-6",
        )

    def test_phase_names_match_roadmap_document(self):
        # Names mirror the headings in /app/memory/BI5_EVOLUTION_ROADMAP.md.
        # Any deviation indicates document/code drift.
        assert bm.PHASE_NAMES["BI5-1"] == "Canonicalise ingestion semantics"
        assert bm.PHASE_NAMES["BI5-2"] == "Raw tick storage substrate"
        assert bm.PHASE_NAMES["BI5-3"] == "Tick-derived realism"
        assert bm.PHASE_NAMES["BI5-4"] == "Tick replay engine"
        assert "Spread"  in bm.PHASE_NAMES["BI5-5"]
        assert "UI pivot" in bm.PHASE_NAMES["BI5-6"]

    def test_no_phase_seal_on_initial_load(self):
        # Roadmap v1.0 ships with zero phases sealed — they activate one
        # at a time under explicit operator decree.
        assert bm.SEALED_PHASES == ()


# ────────────────────────────────────────────────────────────────────
# Tier T2 — Signal-math correctness
# ────────────────────────────────────────────────────────────────────

class TestT2SignalMath:

    def test_signal_helper_shape(self):
        out = bm._signal(3, "≥ 5", ok=False)
        assert out == {"value": 3, "threshold": "≥ 5", "ok": False}

    def test_bi5_1_evaluator_does_not_raise_on_empty_db(self):
        out = _run(bm._evaluate_bi5_1())
        assert out["phase"] == "BI5-1"
        # BI5-1 is hygiene → always ready while not sealed.
        assert out["ready_to_activate"] is True
        assert "bi5_non_canonical_buckets" in out["signals"]

    def test_bi5_2_blocks_when_bi5_1_unsealed(self):
        out = _run(bm._evaluate_bi5_2())
        assert out["ready_to_activate"] is False
        # First blocker should call out the BI5-1 dependency.
        assert any("BI5-1" in b for b in out["blockers"])

    def test_bi5_2_blocks_on_deployment_ready_floor(self):
        out = _run(bm._evaluate_bi5_2())
        # In current state (0 deployment_ready) the floor blocker is present.
        assert any("deployment_ready" in b for b in out["blockers"])

    def test_bi5_3_requires_market_data_ticks_collection(self):
        out = _run(bm._evaluate_bi5_3())
        # Substrate missing → blocker.
        assert any("market_data_ticks" in b for b in out["blockers"])

    def test_bi5_4_requires_cbot_export_history(self):
        out = _run(bm._evaluate_bi5_4())
        assert any("cBot exports" in b for b in out["blockers"])

    def test_bi5_6_requires_all_upstream_sealed(self):
        out = _run(bm._evaluate_bi5_6())
        # All 5 upstream deps must be sealed.
        for dep in ("BI5-1", "BI5-2", "BI5-3", "BI5-4", "BI5-5"):
            assert any(dep in b for b in out["blockers"])


# ────────────────────────────────────────────────────────────────────
# Tier T3 — Dependency-chain invariants
# ────────────────────────────────────────────────────────────────────

class TestT3DependencyChain:

    def test_deps_strictly_grow(self):
        for i, pid in enumerate(bm.PHASE_ORDER):
            deps = set(bm.PHASE_DEPS[pid])
            expected_prefix = set(bm.PHASE_ORDER[:i])
            assert deps == expected_prefix, (
                f"{pid} dependency set {deps} != strict prefix {expected_prefix}"
            )

    def test_evaluator_existence_for_every_phase(self):
        for pid in bm.PHASE_ORDER:
            assert pid in bm._EVALUATORS, f"missing evaluator for {pid}"

    def test_evaluate_all_returns_every_phase(self):
        snap = _run(bm.evaluate_all())
        assert [p["phase"] for p in snap["phases"]] == list(bm.PHASE_ORDER)


# ────────────────────────────────────────────────────────────────────
# Tier T4 — API endpoint shape
# ────────────────────────────────────────────────────────────────────

class TestT4APIShape:

    def test_endpoint_is_declared(self):
        from api.governance import router
        paths = [r.path for r in router.routes]
        assert "/governance/bi5-maturity" in paths

    def test_endpoint_is_read_only_get(self):
        from api.governance import router
        for r in router.routes:
            if r.path == "/governance/bi5-maturity":
                assert "GET" in (r.methods or set())
                # No POST/PUT/PATCH/DELETE counterpart for this path.
                assert not (r.methods & {"POST", "PUT", "PATCH", "DELETE"})
                return
        pytest.fail("/governance/bi5-maturity not declared")

    def test_snapshot_payload_advertises_advisory_only(self):
        snap = _run(bm.evaluate_all())
        assert snap["advisory_only"] is True
        assert "operator_authority" in snap
        assert "operator decree" in snap["operator_authority"].lower()


# ────────────────────────────────────────────────────────────────────
# Tier T5 — Anti-drift / read-only invariants
# ────────────────────────────────────────────────────────────────────

class TestT5AntiDrift:

    def test_module_does_not_import_any_write_path(self):
        """The maturity module must NEVER import a write authority.
        It is strictly advisory."""
        import inspect
        src = inspect.getsource(bm)
        # No mutation primitives.
        for forbidden in (
            "update_one",
            "insert_one",
            "delete_one",
            "replace_one",
            "find_one_and_update",
        ):
            assert forbidden not in src, (
                f"bi5_maturity must be READ-ONLY (found `{forbidden}`)"
            )

    def test_no_autonomous_activation_helpers(self):
        """Maturity module must not expose any 'activate_phase' / 'seal_phase' helpers."""
        public = [n for n in dir(bm) if not n.startswith("_")]
        for forbidden in ("activate_phase", "seal_phase", "transition_phase"):
            assert forbidden not in public, (
                f"bi5_maturity exposes activation helper `{forbidden}` — forbidden"
            )

    def test_sealed_phases_is_module_constant_not_db_driven(self):
        """SEALED_PHASES must be a tuple constant — drift-protected.
        Auto-mutation of seal state is forbidden by operator decree."""
        assert isinstance(bm.SEALED_PHASES, tuple)

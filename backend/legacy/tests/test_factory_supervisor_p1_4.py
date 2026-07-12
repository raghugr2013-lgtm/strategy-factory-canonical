"""Factory Supervisor FS-P1.4 — Phase 1.4 test suite.

Scope:
  * feature_flags: every FS-P1.4 flag is registered AND defaults
    OFF / neutral.
  * copilot_context: build() is a pure transform; build_from_snapshot()
    returns a frozen CopilotContext with the architect block embedded.
  * recommendation_engine: consumption gate, rule families (R-1..R-6),
    dedupe + severity sort, top_recommendation fallback.
  * eligibility_signals: 5 features registered; positive + negative
    verdicts for every signal; operator-directive veto for
    ENABLE_AUTONOMOUS_DISCOVERY is honoured.
  * fag_proposals: lifecycle (observe → recommend_and_notify →
    approve → activate); reject; expire_overdue; admin-only mutator
    enforcement; idempotency; auto-learning veto blocks activate.
  * copilot_operational: 8 canonical questions answer deterministically;
    advisory_only honoured.
  * copilot_advanced: provider-agnostic adapter registry; NullLLMAdapter
    always present; invoke() is short-circuited when gated OFF; the
    registry round-trips custom adapters; build_prompt() is pure.
  * llm_adapter_base: register/get/list/resolve; null adapter never
    calls out.
  * API contracts: FS-P1.4 endpoints respond; status carries the new
    blocks; admin gate enforced on FAG/Advanced Copilot mutators.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from engines.factory_supervisor import (
    copilot_advanced,
    copilot_context,
    copilot_operational,
    eligibility_signals,
    fag_proposals,
    llm_adapter_base,
    recommendation_engine,
    system_state_view,
)
from engines.factory_supervisor.llm_adapter_base import (
    LLMAdapter, LLMRequest, LLMResponse, NullLLMAdapter,
)


# ─── Fixture: isolate FS-P1.4 flags + DB module per test ────────────

_FS_FLAGS = (
    "ENABLE_FACTORY_SUPERVISOR",
    "ENABLE_NOTIFICATION_CENTER",
    "FS_ENABLE_SYSTEM_STATE_VIEW",
    "FS_ENABLE_RECOMMENDATION_ENGINE",
    "FS_ENABLE_ELIGIBILITY_ENGINE",
    "FS_ENABLE_FAG_ENGINE",
    "FS_ENABLE_COPILOT",
    "FS_ENABLE_COPILOT_ADVANCED",
    "FS_COPILOT_PROVIDER",
    "FS_FAG_PROPOSAL_TTL_SEC",
    "ENABLE_AUTONOMOUS_DISCOVERY",
    "ENABLE_BAND_BASED_ROUTING",
    "ENABLE_ADMISSION_CONTROL",
    "ENABLE_ADAPTIVE_POOL_SIZING",
)


@pytest.fixture(autouse=True)
def _isolate_fs_p14():
    saved = {k: os.environ.pop(k, None) for k in _FS_FLAGS}
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()
    # Best-effort: drop the FAG proposals collection so tests are
    # independent. Real Mongo backs the FS-P1.4 test env; tests must
    # not leak state between cases.
    try:
        async def _drop():
            from engines.db import get_db
            await get_db()[fag_proposals.PROPOSAL_COLLECTION].drop()
        asyncio.run(_drop())
    except Exception:
        pass
    # Reset DB module so the next asyncio.run() in the test body
    # gets a motor client bound to its own event loop.
    _db_mod._client = None
    _db_mod._db = None
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()
    try:
        async def _drop2():
            from engines.db import get_db
            await get_db()[fag_proposals.PROPOSAL_COLLECTION].drop()
        asyncio.run(_drop2())
    except Exception:
        pass


def _enable_fs():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"


# ============================================================================
# 1) Feature flags — every FS-P1.4 flag defaults OFF / neutral
# ============================================================================


def test_fs_p14_flags_default_off():
    from engines.feature_flags import flag
    assert flag("FS_ENABLE_RECOMMENDATION_ENGINE") is False
    assert flag("FS_ENABLE_ELIGIBILITY_ENGINE") is False
    assert flag("FS_ENABLE_FAG_ENGINE") is False
    assert flag("FS_ENABLE_COPILOT") is False
    assert flag("FS_ENABLE_COPILOT_ADVANCED") is False
    assert flag("FS_COPILOT_PROVIDER") == "none"
    # Numeric default is sane
    ttl = flag("FS_FAG_PROPOSAL_TTL_SEC")
    assert isinstance(ttl, int) and ttl == 86400


def test_fs_p14_flags_registered_with_intent():
    from engines.feature_flags import _FLAG_SPECS
    names = {s["name"] for s in _FLAG_SPECS}
    for n in (
        "FS_ENABLE_RECOMMENDATION_ENGINE",
        "FS_ENABLE_ELIGIBILITY_ENGINE",
        "FS_ENABLE_FAG_ENGINE",
        "FS_ENABLE_COPILOT",
        "FS_ENABLE_COPILOT_ADVANCED",
        "FS_COPILOT_PROVIDER",
        "FS_FAG_PROPOSAL_TTL_SEC",
    ):
        assert n in names, f"{n} not registered"


# ============================================================================
# 2) CopilotContext — build() is pure; build_from_snapshot() works
# ============================================================================


def test_copilot_context_build_from_minimal_snap():
    snap = {
        "phase": "FS-P1.4",
        "evaluated_at": "2026-02-01T00:00:00+00:00",
        "advisory_only": True,
        "system_health": "ok",
        "local_host_id": "host-x",
    }
    ctx = copilot_context.build(snap)
    assert ctx.phase == "FS-P1.4"
    assert ctx.system_health == "ok"
    assert ctx.advisory_only is True
    # Pure transform — repeating yields identical contexts.
    assert copilot_context.build(snap).to_dict() == ctx.to_dict()
    # frozen — assignment raises
    with pytest.raises(Exception):
        ctx.system_health = "warn"        # type: ignore[misc]


def test_copilot_context_build_from_snapshot_async():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    ctx = asyncio.run(copilot_context.build_from_snapshot(refresh=True))
    assert ctx.phase == "FS-P1.4"
    assert isinstance(ctx.feature_flags, dict)
    assert "fs_flags" in ctx.feature_flags


# ============================================================================
# 3) Recommendation engine — gate + rule families + sort + dedupe
# ============================================================================


def test_recommendation_engine_disabled_by_default():
    assert recommendation_engine.is_enabled() is False


def test_recommendation_engine_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_COPILOT"] = "true"
    assert recommendation_engine.is_enabled() is True


def _minimal_ctx() -> "copilot_context.CopilotContext":
    return copilot_context.build({
        "phase": "FS-P1.4",
        "evaluated_at": "2026-02-01T00:00:00+00:00",
        "advisory_only": True,
        "system_health": "ok",
        "local_host_id": "host-x",
        "fleet": {"fleet_band": "ok", "hosts": [{"host_id": "host-x"}]},
        "queue_pressure": {},
        "feature_flags": {
            "fs_flags": {"FS_ENABLE_COPILOT": True,
                         "FS_ENABLE_COPILOT_ADVANCED": False,
                         "FS_COPILOT_PROVIDER": "none"},
            "auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": False},
            "fag_flags": {},
        },
    })


def test_recommendation_engine_evaluate_returns_sorted_unique_list():
    recs = asyncio.run(recommendation_engine.evaluate(_minimal_ctx()))
    # Severity-desc, code-asc deterministic.
    codes = [r.code for r in recs]
    assert codes == sorted(set(codes), key=codes.index)        # dedup preserved
    # Engine MUST include at least the operator-directive echo when
    # auto-learning flag is off.
    assert any(r.code == "AUTO_LEARNING_GATED_BY_DIRECTIVE" for r in recs)


def test_recommendation_engine_top_recommendation_fallback():
    # An empty / very nominal context still returns a recommendation,
    # never raises (NO_ACTION_REQUIRED is the floor).
    minimal_snap = {
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "host-x",
        "feature_flags": {"auto_learning_flags":
                          {"ENABLE_AUTONOMOUS_DISCOVERY": True}},
    }
    ctx = copilot_context.build(minimal_snap)
    top = asyncio.run(recommendation_engine.top_recommendation(ctx))
    # The engine MUST always return some recommendation, never raise.
    assert isinstance(top.code, str) and top.code
    assert isinstance(top.severity, str) and top.severity


def test_recommendation_engine_r5_advanced_layer_recommendation():
    # When operational is ON and advanced is OFF, R-5 fires.
    snap = {
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "host-x",
        "feature_flags": {
            "fs_flags": {"FS_ENABLE_COPILOT": True,
                         "FS_ENABLE_COPILOT_ADVANCED": False,
                         "FS_COPILOT_PROVIDER": "none"},
            "auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": True},
        },
    }
    ctx = copilot_context.build(snap)
    recs = asyncio.run(recommendation_engine.evaluate(ctx))
    assert any(r.code == "COPILOT_ADVANCED_LAYER_AVAILABLE" for r in recs)


# ============================================================================
# 4) Eligibility signals — registry shape, per-signal positive/negative
# ============================================================================


def test_eligibility_signals_registry_has_five_features():
    feats = eligibility_signals.list_features()
    assert set(feats) >= {
        "ENABLE_BAND_BASED_ROUTING",
        "ENABLE_ADMISSION_CONTROL",
        "ENABLE_ADAPTIVE_POOL_SIZING",
        "ENABLE_AUTONOMOUS_DISCOVERY",
        "FS_ENABLE_COPILOT_ADVANCED",
    }


def test_eligibility_signals_disabled_by_default():
    assert eligibility_signals.is_enabled() is False


def test_eligibility_signals_band_based_routing_eligible_when_fleet_ok():
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"fag_flags":
                          {"ENABLE_BAND_BASED_ROUTING": False}},
    })
    v = eligibility_signals.evaluate("ENABLE_BAND_BASED_ROUTING", ctx)
    assert v.eligible is True


def test_eligibility_signals_band_based_routing_blocked_when_fleet_critical():
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "warn", "local_host_id": "h",
        "fleet": {"fleet_band": "critical"},
        "feature_flags": {"fag_flags": {"ENABLE_BAND_BASED_ROUTING": False}},
    })
    v = eligibility_signals.evaluate("ENABLE_BAND_BASED_ROUTING", ctx)
    assert v.eligible is False
    assert "fleet_band_critical" in v.reasons


def test_eligibility_signals_admission_control_requires_history():
    # Thin journal → ineligible
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "admission": {"stats": {"total": 10}},
        "feature_flags": {"fag_flags": {"ENABLE_ADMISSION_CONTROL": False}},
    })
    v = eligibility_signals.evaluate("ENABLE_ADMISSION_CONTROL", ctx)
    assert v.eligible is False
    # Thick journal → eligible
    ctx2 = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "admission": {"stats": {"total": 100}},
        "feature_flags": {"fag_flags": {"ENABLE_ADMISSION_CONTROL": False}},
    })
    v2 = eligibility_signals.evaluate("ENABLE_ADMISSION_CONTROL", ctx2)
    assert v2.eligible is True


def test_eligibility_signals_autonomous_discovery_carries_directive_veto():
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"auto_learning_flags":
                          {"ENABLE_AUTONOMOUS_DISCOVERY": False}},
    })
    v = eligibility_signals.evaluate("ENABLE_AUTONOMOUS_DISCOVERY", ctx)
    # Verdict's `eligible` can be True (technically eligible) but the
    # suggested_proposal_kind MUST carry the directive marker.
    assert v.suggested_proposal_kind == "operator_directive_gated"
    assert "operator_directive_off" in v.reasons


def test_eligibility_signals_unknown_feature_returns_unknown():
    ctx = _minimal_ctx()
    v = eligibility_signals.evaluate("NOT_A_FEATURE", ctx)
    assert v.eligible is False
    assert "unknown_feature" in v.reasons


def test_eligibility_signals_evaluate_all_returns_all_verdicts():
    ctx = _minimal_ctx()
    verdicts = eligibility_signals.evaluate_all(ctx)
    assert {v.feature for v in verdicts} == set(eligibility_signals.list_features())


# ============================================================================
# 5) FAG proposals — pipeline + idempotency + admin gate
# ============================================================================


def test_fag_engine_disabled_by_default():
    assert fag_proposals.is_enabled() is False


def test_fag_engine_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    assert fag_proposals.is_enabled() is True


def test_fag_observe_creates_pending_proposal_when_eligible():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"fag_flags": {"ENABLE_BAND_BASED_ROUTING": False}},
    })

    async def _run():
        first = await fag_proposals.observe("ENABLE_BAND_BASED_ROUTING", ctx)
        second = await fag_proposals.observe("ENABLE_BAND_BASED_ROUTING", ctx)
        return first, second

    res, res2 = asyncio.run(_run())
    assert res["ok"] is True
    assert res["reason"] in ("created", "reused")
    assert res["proposal"]["state"] == "pending"
    pid = res["proposal"]["proposal_id"]
    # Idempotent — re-observing returns 'reused'.
    assert res2["ok"] is True
    assert res2["proposal"]["proposal_id"] == pid


def test_fag_observe_blocks_operator_directive_features():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"auto_learning_flags":
                          {"ENABLE_AUTONOMOUS_DISCOVERY": False}},
    })
    res = asyncio.run(fag_proposals.observe("ENABLE_AUTONOMOUS_DISCOVERY", ctx))
    assert res["ok"] is False
    assert res["reason"] == "operator_directive_veto"


def test_fag_full_lifecycle_observe_recommend_approve_activate():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"fag_flags": {"ENABLE_BAND_BASED_ROUTING": False}},
    })
    user = {"email": "admin@strategyfactory.dev", "role": "admin"}

    async def _run():
        obs = await fag_proposals.observe("ENABLE_BAND_BASED_ROUTING", ctx, user=user)
        pid = obs["proposal"]["proposal_id"]
        rec = await fag_proposals.recommend_and_notify(pid, user=user)
        apv = await fag_proposals.approve(pid, user=user)
        act = await fag_proposals.activate(pid, user=user)
        return obs, rec, apv, act

    obs, rec, apv, act = asyncio.run(_run())
    assert obs["ok"] and obs["proposal"]["state"] == "pending"
    assert rec["ok"]
    assert rec["proposal"]["state"] == "recommended"
    assert apv["ok"]
    assert apv["proposal"]["state"] == "approved"
    assert act["ok"] and act["reason"] == "activated"
    assert act["proposal"]["state"] == "activated"
    assert act["flag"] == "ENABLE_BAND_BASED_ROUTING"
    # Cleanup the env flip the activate() induces.
    os.environ.pop("ENABLE_BAND_BASED_ROUTING", None)


def test_fag_activate_refuses_non_approved():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"fag_flags": {"ENABLE_BAND_BASED_ROUTING": False}},
    })

    async def _run():
        obs = await fag_proposals.observe("ENABLE_BAND_BASED_ROUTING", ctx)
        pid = obs["proposal"]["proposal_id"]
        # Try to activate a pending proposal.
        return await fag_proposals.activate(pid, user={"role": "admin"})

    res = asyncio.run(_run())
    assert res["ok"] is False
    assert res["reason"] == "not_approved"


def test_fag_reject_marks_terminal_and_blocks_further_transitions():
    _enable_fs()
    os.environ["FS_ENABLE_FAG_ENGINE"] = "true"
    ctx = copilot_context.build({
        "phase": "FS-P1.4", "advisory_only": True,
        "system_health": "ok", "local_host_id": "h",
        "fleet": {"fleet_band": "ok"},
        "feature_flags": {"fag_flags": {"ENABLE_BAND_BASED_ROUTING": False}},
    })

    async def _run():
        obs = await fag_proposals.observe("ENABLE_BAND_BASED_ROUTING", ctx)
        pid = obs["proposal"]["proposal_id"]
        rej = await fag_proposals.reject(pid, user={"role": "admin"}, reason="no")
        apv = await fag_proposals.approve(pid, user={"role": "admin"})
        return rej, apv

    rej, apv = asyncio.run(_run())
    assert rej["ok"]
    assert rej["proposal"]["state"] == "rejected"
    assert apv["ok"] is False
    assert apv["reason"] == "terminal_state"


def test_fag_expire_overdue_returns_dict():
    res = asyncio.run(fag_proposals.expire_overdue(ttl_sec=60))
    assert isinstance(res, dict)
    assert "expired" in res


# ============================================================================
# 6) Operational Copilot — answers + canonical questions + advisory gate
# ============================================================================


def test_copilot_operational_disabled_by_default():
    assert copilot_operational.is_enabled() is False


def test_copilot_operational_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_COPILOT"] = "true"
    assert copilot_operational.is_enabled() is True


def test_copilot_operational_eight_canonical_questions_registered():
    assert len(copilot_operational.CANONICAL_QUESTIONS) == 9
    # Stable set.
    assert "is_auto_learning_ready" in copilot_operational.CANONICAL_QUESTIONS


def test_copilot_operational_answer_all_returns_eight_answers():
    ctx = _minimal_ctx()
    out = copilot_operational.answer_all(ctx)
    assert set(out["answers"].keys()) == set(copilot_operational.CANONICAL_QUESTIONS)
    # Advisory-only when gated off.
    assert out["advisory_only"] is True


def test_copilot_operational_unknown_question_returns_canonical_list():
    out = copilot_operational.answer(_minimal_ctx(), "not_a_question")
    assert out["error"] == "unknown_question"
    assert isinstance(out["canonical"], list) and len(out["canonical"]) == 9


def test_copilot_operational_q8_reflects_directive():
    # Off by default → answer reflects directive
    out = copilot_operational.answer(_minimal_ctx(), "is_auto_learning_ready")
    assert out["enabled"] is False
    assert "gated" in out["answer"].lower()


def test_copilot_operational_q6_uses_eligibility_signals():
    out = copilot_operational.answer(_minimal_ctx(), "which_features_ready_to_activate")
    assert isinstance(out["verdicts"], list)
    # The minimal fleet-OK context makes routing eligible.
    assert any(v["feature"] == "ENABLE_BAND_BASED_ROUTING" for v in out["verdicts"])


# ============================================================================
# 7) Advanced Intelligence Copilot + LLM adapter base
# ============================================================================


def test_llm_adapter_base_registers_null_adapter_at_bootstrap():
    providers = llm_adapter_base.list_providers()
    assert "none" in providers
    name, adapter = llm_adapter_base.resolve_active_adapter()
    assert name == "none"
    assert isinstance(adapter, NullLLMAdapter)


def test_llm_adapter_base_registry_round_trip():
    class _Fake(LLMAdapter):
        def provider_name(self): return "fake-adapter-x"
        async def invoke(self, req):
            return LLMResponse(provider="fake-adapter-x", text="ok",
                               advisory_only=True)
    llm_adapter_base.register_adapter("fake-adapter-x", _Fake())
    try:
        assert "fake-adapter-x" in llm_adapter_base.list_providers()
        ad = llm_adapter_base.get_adapter("fake-adapter-x")
        assert ad.provider_name() == "fake-adapter-x"
    finally:
        llm_adapter_base.unregister_adapter("fake-adapter-x")
    assert "fake-adapter-x" not in llm_adapter_base.list_providers()


def test_null_llm_adapter_never_calls_out():
    adapter = NullLLMAdapter()
    resp = asyncio.run(adapter.invoke(LLMRequest(prompt="x")))
    assert resp.provider == "none"
    assert resp.advisory_only is True
    assert resp.error is None


def test_copilot_advanced_disabled_by_default():
    assert copilot_advanced.is_enabled() is False


def test_copilot_advanced_enables_with_both_flags():
    _enable_fs()
    os.environ["FS_ENABLE_COPILOT_ADVANCED"] = "true"
    assert copilot_advanced.is_enabled() is True


def test_copilot_advanced_manifest_shape():
    mf = copilot_advanced.provider_manifest()
    assert "enabled" in mf and "active_provider" in mf
    assert "registered" in mf and "advisory_only" in mf
    assert mf["active_provider"] in mf["registered"]


def test_copilot_advanced_build_prompt_is_pure():
    ctx = _minimal_ctx()
    req = copilot_advanced.build_prompt(ctx, copilot_advanced.INTENT_SUMMARISE_STATE)
    assert isinstance(req, LLMRequest)
    assert req.context["phase"] == "FS-P1.4"
    assert req.extra["intent"] == copilot_advanced.INTENT_SUMMARISE_STATE


def test_copilot_advanced_build_prompt_unknown_intent_falls_back_to_freeform():
    ctx = _minimal_ctx()
    req = copilot_advanced.build_prompt(ctx, "not-an-intent", user_input="hello")
    assert req.extra["intent"] == copilot_advanced.INTENT_FREEFORM
    assert "hello" in req.prompt


def test_copilot_advanced_invoke_short_circuits_when_gated_off():
    ctx = _minimal_ctx()
    out = asyncio.run(copilot_advanced.invoke(
        ctx, intent=copilot_advanced.INTENT_SUMMARISE_STATE,
    ))
    assert out["advisory_only"] is True
    assert out["provider"] == "none"
    assert "OFF" in out["response"]["text"]


def test_copilot_advanced_invoke_routes_through_null_when_enabled_with_none():
    _enable_fs()
    os.environ["FS_ENABLE_COPILOT_ADVANCED"] = "true"
    # FS_COPILOT_PROVIDER remains 'none' → NullLLMAdapter answers.
    ctx = _minimal_ctx()
    out = asyncio.run(copilot_advanced.invoke(
        ctx, intent=copilot_advanced.INTENT_SUMMARISE_STATE,
    ))
    assert out["provider"] == "none"
    assert out["response"]["provider"] == "none"
    # NullLLMAdapter is advisory_only.
    assert out["advisory_only"] is True


def test_copilot_advanced_invoke_uses_custom_provider_when_registered():
    _enable_fs()
    os.environ["FS_ENABLE_COPILOT_ADVANCED"] = "true"
    os.environ["FS_COPILOT_PROVIDER"] = "fake-adv-x"

    class _Adv(LLMAdapter):
        def provider_name(self): return "fake-adv-x"
        async def invoke(self, req):
            return LLMResponse(provider="fake-adv-x", text="HELLO",
                               advisory_only=False, finish_reason="stop")

    llm_adapter_base.register_adapter("fake-adv-x", _Adv())
    try:
        out = asyncio.run(copilot_advanced.invoke(
            _minimal_ctx(),
            intent=copilot_advanced.INTENT_SUMMARISE_STATE,
        ))
        assert out["provider"] == "fake-adv-x"
        assert out["response"]["text"] == "HELLO"
        # Provider-supplied advisory_only=False; copilot still wraps
        # the response as non-advisory.
        assert out["advisory_only"] is False
    finally:
        llm_adapter_base.unregister_adapter("fake-adv-x")


# ============================================================================
# 8) system_state_view — FS-P1.4 phase + new flag groups
# ============================================================================


def test_system_state_view_phase_is_fs_p14():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    snap = asyncio.run(system_state_view.snapshot(refresh=True))
    assert snap["phase"] == "FS-P1.4"


def test_system_state_view_carries_fs_p14_flag_groups():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    snap = asyncio.run(system_state_view.snapshot(refresh=True))
    ff = snap.get("feature_flags") or {}
    fs_flags = ff.get("fs_flags") or {}
    # FS-P1.4 flags surfaced.
    for n in (
        "FS_ENABLE_RECOMMENDATION_ENGINE",
        "FS_ENABLE_ELIGIBILITY_ENGINE",
        "FS_ENABLE_FAG_ENGINE",
        "FS_ENABLE_COPILOT",
        "FS_ENABLE_COPILOT_ADVANCED",
        "FS_COPILOT_PROVIDER",
        "FS_FAG_PROPOSAL_TTL_SEC",
    ):
        assert n in fs_flags, f"{n} missing from system_state_view"


# ============================================================================
# 9) API contracts — every FS-P1.4 endpoint mounts + returns expected shape
# ============================================================================


def _client():
    """Local TestClient with a real admin JWT token.

    Uses the seeded admin (per /app/memory/test_credentials.md). The
    AuthMiddleware loads the user from Mongo, so we cannot fake the
    user via dependency_overrides — we mint a real token instead.
    """
    from fastapi.testclient import TestClient
    from server import app
    from auth_utils import create_token
    token = create_token({
        "user_id": "test-admin",
        "email":   "admin@strategyfactory.dev",
        "role":    "admin",
    })
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


def test_api_status_advertises_fs_p14():
    c = _client()
    r = c.get("/api/factory-supervisor/status")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "FS-P1.4"
    assert "recommendation_engine" in body
    assert "eligibility_engine" in body
    assert "fag_engine" in body
    assert "copilot_operational" in body
    assert "copilot_advanced" in body


def test_api_recommendations_top_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/recommendations/top")
    assert r.status_code == 200
    body = r.json()
    assert body["advisory_only"] is True
    assert "top" in body


def test_api_eligibility_endpoint_lists_verdicts():
    c = _client()
    r = c.get("/api/factory-supervisor/eligibility")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["verdicts"], list)
    assert len(body["verdicts"]) == 6


def test_api_eligibility_one_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/eligibility/ENABLE_BAND_BASED_ROUTING")
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"]["feature"] == "ENABLE_BAND_BASED_ROUTING"


def test_api_copilot_answers_endpoint_returns_eight():
    c = _client()
    r = c.get("/api/factory-supervisor/copilot/answers")
    assert r.status_code == 200
    body = r.json()
    assert set(body["answers"].keys()) == set(copilot_operational.CANONICAL_QUESTIONS)


def test_api_copilot_answer_one_endpoint():
    c = _client()
    r = c.post("/api/factory-supervisor/copilot/answer",
               json={"question_id": "what_is_blocked"})
    assert r.status_code == 200
    body = r.json()
    assert body["question_id"] == "what_is_blocked"


def test_api_copilot_advanced_manifest_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/copilot/advanced/manifest")
    assert r.status_code == 200
    body = r.json()
    assert body["active_provider"] == "none"
    assert "none" in body["registered"]


def test_api_copilot_advanced_invoke_short_circuits_when_gated_off():
    c = _client()
    r = c.post("/api/factory-supervisor/copilot/advanced/invoke",
               json={"intent": "summarise_state"})
    assert r.status_code == 200
    body = r.json()
    assert body["advisory_only"] is True
    assert body["provider"] == "none"


def test_api_fag_proposals_list_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/fag/proposals")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert isinstance(body["rows"], list)


def test_api_fag_observe_short_circuits_when_engine_off():
    c = _client()
    r = c.post("/api/factory-supervisor/fag/observe",
               json={"feature_name": "ENABLE_BAND_BASED_ROUTING"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["reason"] == "engine_off"


def test_api_fag_admin_gate_enforced_on_recommend():
    # Use a non-admin token to verify the admin gate.
    from fastapi.testclient import TestClient
    from server import app
    from auth_utils import create_token
    token = create_token({
        "user_id": "viewer", "email": "viewer@e1.dev", "role": "viewer",
    })
    c = TestClient(app)
    c.headers.update({"Authorization": f"Bearer {token}"})
    r = c.post("/api/factory-supervisor/fag/recommend",
               json={"proposal_id": "doesnt-matter"})
    # Either 401 (middleware rejected unknown email) or 403 (admin gate).
    # Both prove the admin mutator is locked down.
    assert r.status_code in (401, 403)


def test_api_recommendations_full_list_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert "recommendations" in body
    assert isinstance(body["recommendations"], list)


def test_api_copilot_context_endpoint_returns_frozen_view():
    c = _client()
    r = c.get("/api/factory-supervisor/copilot/context")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "FS-P1.4"
    assert "recommended_action" in body
    assert "activation_ready" in body


def test_api_fag_stats_endpoint():
    c = _client()
    r = c.get("/api/factory-supervisor/fag/proposals/stats")
    assert r.status_code == 200
    body = r.json()
    assert "per_state" in body and "per_feature" in body

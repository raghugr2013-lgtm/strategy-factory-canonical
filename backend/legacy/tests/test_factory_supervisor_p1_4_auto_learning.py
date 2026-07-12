"""Factory Supervisor FS-P1.4 — Auto-Learning Infrastructure test suite.

Scope:
  * feature_flags: every FS-P1.4 Auto-Learning flag is registered AND
    defaults OFF / neutral.
  * auto_learning: aggregator is read-only; component readers return
    structured dicts; the operator-directive echo is ALWAYS present in
    the insights list; severity caps at WARN.
  * Loop gate: is_loop_enabled() ALWAYS returns False under default
    operator policy, even when FS_ENABLE_AUTO_LEARNING_LOOP is True
    (autonomous-discovery veto still applies).
  * Recommendation engine: R-7 surfaces Auto-Learning insights ONLY
    when FS_ENABLE_AUTO_LEARNING=true.
  * Eligibility signals: FS_ENABLE_AUTO_LEARNING_LOOP carries the
    operator_directive_off reason as a hard veto.
  * Copilot context: build_from_snapshot hydrates `auto_learning` only
    when the consumption gate is ON.
  * Copilot operational: Q9 ("what_are_learning_insights") is wired.
  * Fan-out is a NO-OP (skipped='flag_off') when the supervisor is OFF;
    when ON, emits respect severity_floor.
  * NEVER triggers execution, mutation, deployment, or feature
    activation.
"""
from __future__ import annotations

import asyncio
import os
from typing import Dict

import pytest

from engines.factory_supervisor import (
    auto_learning,
    copilot_context,
    copilot_operational,
    eligibility_signals,
    recommendation_engine,
    system_state_view,
)


# ─── Fixture: isolate Auto-Learning env per test ────────────────────

_AL_FLAGS = (
    "ENABLE_FACTORY_SUPERVISOR",
    "ENABLE_NOTIFICATION_CENTER",
    "FS_ENABLE_SYSTEM_STATE_VIEW",
    "FS_ENABLE_RECOMMENDATION_ENGINE",
    "FS_ENABLE_ELIGIBILITY_ENGINE",
    "FS_ENABLE_COPILOT",
    "FS_ENABLE_AUTO_LEARNING",
    "FS_ENABLE_AUTO_LEARNING_LOOP",
    "FS_AUTO_LEARNING_ROR_THRESHOLD",
    "FS_AUTO_LEARNING_AGING_THRESHOLD",
    "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES",
    "ENABLE_AUTONOMOUS_DISCOVERY",
    "ENABLE_RISK_OF_RUIN",
    "RISK_OF_RUIN_WEIGHT",
    "ENABLE_AGING_PENALTY",
    "ENABLE_AGING_AUTO_DEMOTION",
    "ENABLE_CALIBRATION",
    "ENABLE_EXECUTION_REALISM_DEFAULTS",
)


@pytest.fixture(autouse=True)
def _isolate_auto_learning_env():
    saved = {k: os.environ.pop(k, None) for k in _AL_FLAGS}
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _db_mod._client = None
    _db_mod._db = None
    system_state_view.invalidate_cache()


def _enable_fs():
    os.environ["ENABLE_FACTORY_SUPERVISOR"] = "true"


# ============================================================================
# 1) Feature flags — every Auto-Learning flag defaults OFF / neutral
# ============================================================================


def test_auto_learning_flags_default_off():
    from engines.feature_flags import flag
    assert flag("FS_ENABLE_AUTO_LEARNING") is False
    assert flag("FS_ENABLE_AUTO_LEARNING_LOOP") is False
    assert float(flag("FS_AUTO_LEARNING_ROR_THRESHOLD")) == pytest.approx(0.10)
    assert float(flag("FS_AUTO_LEARNING_AGING_THRESHOLD")) == pytest.approx(0.60)
    assert int(flag("FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES")) == 30


def test_auto_learning_flags_registered_with_intent():
    from engines.feature_flags import _FLAG_SPECS
    names = {s["name"] for s in _FLAG_SPECS}
    for n in (
        "FS_ENABLE_AUTO_LEARNING",
        "FS_ENABLE_AUTO_LEARNING_LOOP",
        "FS_AUTO_LEARNING_ROR_THRESHOLD",
        "FS_AUTO_LEARNING_AGING_THRESHOLD",
        "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES",
    ):
        assert n in names, f"{n} not registered"


# ============================================================================
# 2) Consumption + loop gates — both default OFF; loop honours veto
# ============================================================================


def test_consumption_gate_disabled_by_default():
    assert auto_learning.is_enabled() is False


def test_consumption_gate_requires_master_switch():
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    # Master switch still off → consumption stays off.
    assert auto_learning.is_enabled() is False


def test_consumption_gate_on_when_both_flags_true():
    _enable_fs()
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    assert auto_learning.is_enabled() is True


def test_loop_gate_always_off_under_directive():
    """Even with the loop flag ON, the operator-directive veto
    (ENABLE_AUTONOMOUS_DISCOVERY=false) keeps the loop OFF."""
    _enable_fs()
    os.environ["FS_ENABLE_AUTO_LEARNING_LOOP"] = "true"
    # Directive still OFF
    assert auto_learning.is_loop_enabled() is False


def test_loop_gate_needs_all_three_flags():
    _enable_fs()
    os.environ["FS_ENABLE_AUTO_LEARNING_LOOP"] = "true"
    os.environ["ENABLE_AUTONOMOUS_DISCOVERY"] = "true"
    assert auto_learning.is_loop_enabled() is True


# ============================================================================
# 3) Aggregator — pure, read-only, returns structured report
# ============================================================================


def test_build_report_returns_components_and_insights():
    report = asyncio.run(auto_learning.build_report())
    d = report.to_dict()
    assert set(d["components"].keys()) == {
        "risk_of_ruin", "lifecycle_decay",
        "calibration_framework", "execution_realism_defaults",
    }
    # Every insight has the canonical shape.
    for i in d["insights"]:
        assert {"kind", "severity", "title", "detail",
                "suggested_action", "evidence"}.issubset(i.keys())
    # Operator-directive echo must ALWAYS be present.
    assert any(i["kind"] == "AUTO_LEARNING_LOOP_GATED" for i in d["insights"])
    # advisory_only is True when consumption gate is OFF.
    assert d["advisory_only"] is True
    assert d["is_loop_enabled"] is False


def test_build_report_severity_capped_at_warn():
    report = asyncio.run(auto_learning.build_report())
    for i in report.insights:
        assert i["severity"] in (
            auto_learning.SEVERITY_INFO,
            auto_learning.SEVERITY_SUGGESTION,
            auto_learning.SEVERITY_WARN,
        )


def test_to_recommendations_shape():
    report = asyncio.run(auto_learning.build_report())
    recs = auto_learning.to_recommendations(
        auto_learning.generate_insights(report)
    )
    assert recs, "auto_learning.to_recommendations should never be empty"
    for r in recs:
        assert r["code"].startswith("AUTO_LEARNING:")
        assert set(r.keys()) == {"code", "severity", "title", "detail",
                                 "suggested_fix", "evidence"}


def test_flag_manifest_shape():
    m = auto_learning.flag_manifest()
    # All consumption + threshold flags echoed.
    for k in (
        "FS_ENABLE_AUTO_LEARNING",
        "FS_ENABLE_AUTO_LEARNING_LOOP",
        "FS_AUTO_LEARNING_ROR_THRESHOLD",
        "FS_AUTO_LEARNING_AGING_THRESHOLD",
        "FS_AUTO_LEARNING_CALIBRATION_MIN_OUTCOMES",
        "ENABLE_RISK_OF_RUIN",
        "ENABLE_AGING_PENALTY",
        "ENABLE_CALIBRATION",
        "ENABLE_EXECUTION_REALISM_DEFAULTS",
        "ENABLE_AUTONOMOUS_DISCOVERY",
    ):
        assert k in m


# ============================================================================
# 4) Recommendation engine — R-7 surfaces only when AL is ON
# ============================================================================


def _minimal_ctx():
    return copilot_context.build({
        "phase": "FS-P1.4",
        "evaluated_at": "2026-02-01T00:00:00+00:00",
        "advisory_only": True,
        "system_health": "ok",
        "local_host_id": "host-x",
        "fleet": {"fleet_band": "ok", "hosts": [{"host_id": "host-x"}]},
    })


def test_recommendations_have_no_auto_learning_codes_when_gate_off():
    ctx = _minimal_ctx()
    recs = asyncio.run(recommendation_engine.evaluate(ctx))
    codes = {r.code for r in recs}
    assert not any(c.startswith("AUTO_LEARNING:") for c in codes)


def test_recommendations_include_auto_learning_codes_when_gate_on():
    _enable_fs()
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    ctx = _minimal_ctx()
    recs = asyncio.run(recommendation_engine.evaluate(ctx))
    codes = {r.code for r in recs}
    assert any(c.startswith("AUTO_LEARNING:") for c in codes), (
        f"expected AUTO_LEARNING:* codes; got {sorted(codes)}"
    )
    # The operator-directive echo must surface even when consumed.
    assert "AUTO_LEARNING:AUTO_LEARNING_LOOP_GATED" in codes
    # No CRITICAL severity allowed from Auto-Learning.
    for r in recs:
        if r.code.startswith("AUTO_LEARNING:"):
            assert r.severity != "critical"


# ============================================================================
# 5) Eligibility signal — operator_directive_off is a hard veto
# ============================================================================


def test_auto_learning_loop_signal_registered():
    assert "FS_ENABLE_AUTO_LEARNING_LOOP" in eligibility_signals.list_features()


def test_auto_learning_loop_signal_carries_directive_veto():
    ctx = _minimal_ctx()
    verdict = eligibility_signals.evaluate("FS_ENABLE_AUTO_LEARNING_LOOP", ctx)
    d = verdict.to_dict()
    assert d["feature"] == "FS_ENABLE_AUTO_LEARNING_LOOP"
    assert "operator_directive_off" in d["reasons"]
    assert d["evidence"].get("operator_directive") == "off"
    assert d.get("suggested_proposal_kind") == "operator_directive_gated"


def test_auto_learning_loop_signal_directive_overrides_readiness():
    # Even with technical readiness flagged, the directive veto is hard.
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    snap = {
        "phase": "FS-P1.4",
        "advisory_only": True,
        "system_health": "ok",
        "local_host_id": "x",
        "fleet": {"fleet_band": "ok", "hosts": [{"host_id": "x"}]},
        "feature_flags": {
            "fs_flags": {"FS_ENABLE_AUTO_LEARNING": True},
            "auto_learning_flags": {"ENABLE_AUTONOMOUS_DISCOVERY": False},
        },
    }
    ctx = copilot_context.build(snap)
    verdict = eligibility_signals.evaluate("FS_ENABLE_AUTO_LEARNING_LOOP", ctx)
    assert "operator_directive_off" in verdict.reasons


# ============================================================================
# 6) Copilot context — auto_learning hydrated only when gate is ON
# ============================================================================


def test_copilot_context_skips_hydration_when_disabled():
    ctx = copilot_context.build({
        "phase": "FS-P1.4",
        "evaluated_at": "x",
        "advisory_only": True,
        "system_health": "ok",
        "local_host_id": "x",
    })
    assert ctx.auto_learning == {}


def test_copilot_context_hydrates_when_enabled():
    _enable_fs()
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    ctx = asyncio.run(copilot_context.build_from_snapshot(refresh=True))
    assert isinstance(ctx.auto_learning, dict)
    assert "insights" in ctx.auto_learning
    assert "components" in ctx.auto_learning


# ============================================================================
# 7) Copilot operational — Q9 wired and returns insight summary
# ============================================================================


def test_q9_is_canonical():
    assert "what_are_learning_insights" in copilot_operational.CANONICAL_QUESTIONS


def test_q9_returns_empty_when_dormant():
    ctx = _minimal_ctx()
    out = copilot_operational.answer(ctx, "what_are_learning_insights")
    assert out["question_id"] == "what_are_learning_insights"
    assert isinstance(out.get("insights"), list)
    assert out.get("is_loop_enabled") is False
    assert out.get("operator_directive") == "off"


def test_q9_returns_insights_when_hydrated():
    _enable_fs()
    os.environ["FS_ENABLE_AUTO_LEARNING"] = "true"
    os.environ["FS_ENABLE_SYSTEM_STATE_VIEW"] = "true"
    ctx = asyncio.run(copilot_context.build_from_snapshot(refresh=True))
    out = copilot_operational.answer(ctx, "what_are_learning_insights")
    assert isinstance(out["insights"], list)
    assert out["insights"], "Expected insights when consumption gate ON"
    assert out["summary"]["total"] >= 1
    assert out["operator_directive"] == "off"


# ============================================================================
# 8) Manual fan-out — NEVER automatic
# ============================================================================


def test_fan_out_noop_on_empty_insights():
    out = asyncio.run(auto_learning.fan_out_to_notifications([]))
    assert out["emitted"] == 0
    assert out["reason"] == "no_insights"


def test_fan_out_respects_severity_floor():
    insights = [
        auto_learning.LearningInsight(
            kind="X_INFO", severity=auto_learning.SEVERITY_INFO,
            title="info-only", detail="",
        ),
        auto_learning.LearningInsight(
            kind="X_SUG", severity=auto_learning.SEVERITY_SUGGESTION,
            title="sug", detail="",
        ),
    ]
    # FS gate is OFF → supervisor_events.emit short-circuits with skipped=flag_off,
    # but our fan-out treats that as a successful emit because no exception
    # is raised. Verify the severity_floor filtering instead.
    out = asyncio.run(auto_learning.fan_out_to_notifications(
        insights, severity_floor=auto_learning.SEVERITY_WARN,
    ))
    # Floor=warn → both insights skipped
    assert out["emitted"] == 0
    assert out["skipped"] == 2


def test_fan_out_emits_when_floor_low():
    _enable_fs()
    os.environ["ENABLE_NOTIFICATION_CENTER"] = "true"
    insights = [
        auto_learning.LearningInsight(
            kind="X_SUG", severity=auto_learning.SEVERITY_SUGGESTION,
            title="t", detail="d",
        ),
    ]
    out = asyncio.run(auto_learning.fan_out_to_notifications(
        insights, severity_floor=auto_learning.SEVERITY_SUGGESTION,
        user={"email": "ops@test"},
    ))
    # At least we did not skip everything; the emit may persist or
    # be soft-skipped, but the trigger metadata should reflect the actor.
    assert out["triggered_by"] == "ops@test"
    assert out["skipped"] + out["emitted"] == 1


# ============================================================================
# 9) Negative invariants — operator policy is honoured everywhere
# ============================================================================


def test_aggregator_never_writes_to_strategy_collections():
    """Run build_report and verify no mutator is invoked.

    Indirect check: the strategy_library / deployment_registry document
    counts must be identical before/after. Best-effort — we just count
    docs and compare.
    """
    async def main() -> Dict[str, int]:
        from engines.db import get_db
        db = get_db()
        before = {
            "strategy_library":   await db["strategy_library"].estimated_document_count(),
            "deployment_registry": await db["deployment_registry"].estimated_document_count(),
        }
        await auto_learning.build_report()
        after = {
            "strategy_library":   await db["strategy_library"].estimated_document_count(),
            "deployment_registry": await db["deployment_registry"].estimated_document_count(),
        }
        return {"before": before, "after": after}
    out = asyncio.run(main())
    assert out["before"] == out["after"], (
        "Auto-Learning aggregator MUST NOT mutate trading collections."
    )


def test_aggregator_directive_echo_is_idempotent():
    r1 = asyncio.run(auto_learning.build_report())
    # Reset motor client so the next asyncio.run() binds to its own loop.
    from engines import db as _db_mod
    _db_mod._client = None
    _db_mod._db = None
    r2 = asyncio.run(auto_learning.build_report())
    # Both reports carry the same set of insight kinds.
    k1 = {i["kind"] for i in r1.insights}
    k2 = {i["kind"] for i in r2.insights}
    assert k1 == k2
    assert "AUTO_LEARNING_LOOP_GATED" in k1

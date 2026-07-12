"""Unit tests for engines.feature_flags (latent — Phase 4/5 manifest)."""
from __future__ import annotations

import pytest

from engines import feature_flags as ff

pytestmark = pytest.mark.latent


def test_every_flag_has_required_metadata():
    """The registry contract — every spec must declare these fields
    so the audit surface remains complete."""
    required = {"name", "default", "kind", "scope", "intent"}
    for spec in ff.iter_specs():
        missing = required - set(spec.keys())
        assert not missing, f"{spec.get('name')!r} missing fields: {missing}"


def test_known_flags_are_registered():
    """If any of these is missing, an engine is silently reading an
    unregistered env var → audit drift."""
    expected = {
        "ENABLE_RISK_OF_RUIN",
        "RISK_OF_RUIN_WEIGHT",
        "ENABLE_AGING_PENALTY",
        "ENABLE_AGING_AUTO_DEMOTION",
        "ENABLE_CALIBRATION",
        "ENABLE_ADAPTIVE_ROTATION",
        "ENABLE_ANTI_CORRELATION_FILTER",
        "ENABLE_AI_ADVISORY",
        "ENABLE_DEPLOYMENT_THROTTLE",
        "AUDIT_LOG_RETENTION_DAYS",
    }
    actual = {spec["name"] for spec in ff.iter_specs()}
    missing = expected - actual
    assert not missing, f"unregistered flags: {missing}"


def test_all_enable_flags_default_dormant():
    """Operator decree — every ENABLE_* must default to False."""
    for spec in ff.iter_specs():
        if spec["name"].startswith("ENABLE_"):
            assert spec["default"] is False, (
                f"{spec['name']} default={spec['default']} — "
                "ENABLE_* flags MUST default to False per institutional discipline"
            )


def test_risk_of_ruin_weight_default_zero():
    """RoR contribution to deploy_score must remain 0.0 by default."""
    for spec in ff.iter_specs():
        if spec["name"] == "RISK_OF_RUIN_WEIGHT":
            assert spec["default"] == 0.0
            return
    pytest.fail("RISK_OF_RUIN_WEIGHT not in manifest")


def test_env_override_bool(monkeypatch):
    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "true")
    assert ff.flag("ENABLE_RISK_OF_RUIN") is True
    monkeypatch.setenv("ENABLE_RISK_OF_RUIN", "0")
    assert ff.flag("ENABLE_RISK_OF_RUIN") is False


def test_env_override_float(monkeypatch):
    monkeypatch.setenv("AGING_TAU_DAYS", "30.5")
    assert ff.flag("AGING_TAU_DAYS") == pytest.approx(30.5)


def test_env_override_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("AGING_TAU_DAYS", "not-a-number")
    # Default is 60.0 — invalid input must NOT raise.
    assert ff.flag("AGING_TAU_DAYS") == 60.0


def test_unknown_flag_raises():
    with pytest.raises(KeyError):
        ff.flag("THIS_FLAG_DOES_NOT_EXIST")


def test_all_flags_serialisable():
    snap = ff.all_flags()
    import json
    # Must be JSON-roundtrippable for the /api/latent/feature-flags endpoint.
    json.loads(json.dumps(snap))


def test_no_flags_overridden_in_clean_env(monkeypatch):
    """Sanity — without env overrides, every flag is dormant."""
    # Clear any test-leaking env vars first.
    for spec in ff.iter_specs():
        monkeypatch.delenv(spec["name"], raising=False)
    active = ff.active_flags()
    assert active == {}, f"unexpected active flags in clean env: {active}"


# ─────────────────────────────────────────────────────────────────────
# Phase 4/5 — forensic governance-state transition tracking
# (latent_capability:override_diff). Pure-helper coverage; the
# DB-coupled `emit_override_diff_event` is exercised only at boot
# and protected by best-effort error swallowing (never raises).
# ─────────────────────────────────────────────────────────────────────

def test_compute_override_diff_first_boot_shape():
    """No prior overrides → every current override is `added`."""
    diff = ff._compute_override_diff({}, {"ENABLE_AGING_PENALTY": True})
    assert diff == {
        "added":   {"ENABLE_AGING_PENALTY": True},
        "removed": {},
        "changed": {},
    }


def test_compute_override_diff_removed_only():
    """A previously-overridden flag returning to dormant → `removed`."""
    diff = ff._compute_override_diff(
        {"ENABLE_AGING_PENALTY": True}, {},
    )
    assert diff == {
        "added":   {},
        "removed": {"ENABLE_AGING_PENALTY": True},
        "changed": {},
    }


def test_compute_override_diff_changed_value():
    """Value mutation (e.g. RoR_WEIGHT 0.05 → 0.10) → `changed`."""
    diff = ff._compute_override_diff(
        {"RISK_OF_RUIN_WEIGHT": 0.05},
        {"RISK_OF_RUIN_WEIGHT": 0.10},
    )
    assert diff == {
        "added":   {},
        "removed": {},
        "changed": {"RISK_OF_RUIN_WEIGHT": {"from": 0.05, "to": 0.10}},
    }


def test_compute_override_diff_multi_bucket_mix():
    """Mixed add+remove+change in a single transition."""
    prev = {
        "ENABLE_AGING_PENALTY":      True,
        "RISK_OF_RUIN_WEIGHT":       0.05,
        "ENABLE_DEPLOYMENT_THROTTLE": True,
    }
    curr = {
        "RISK_OF_RUIN_WEIGHT":  0.10,            # changed
        "ENABLE_AGING_PENALTY": True,            # unchanged
        "ENABLE_CALIBRATION":   True,            # added
        # ENABLE_DEPLOYMENT_THROTTLE removed
    }
    diff = ff._compute_override_diff(prev, curr)
    assert diff["added"]   == {"ENABLE_CALIBRATION": True}
    assert diff["removed"] == {"ENABLE_DEPLOYMENT_THROTTLE": True}
    assert diff["changed"] == {"RISK_OF_RUIN_WEIGHT": {"from": 0.05, "to": 0.10}}


def test_compute_override_diff_identical_dicts_is_empty():
    """No transition → all three buckets empty."""
    same = {"ENABLE_AGING_PENALTY": True, "RISK_OF_RUIN_WEIGHT": 0.05}
    diff = ff._compute_override_diff(same, dict(same))
    assert diff == {"added": {}, "removed": {}, "changed": {}}
    assert ff._is_empty_diff(diff) is True


def test_is_empty_diff_non_empty_paths():
    """Each non-empty bucket independently disqualifies emptiness."""
    assert ff._is_empty_diff({"added": {"X": 1}, "removed": {}, "changed": {}}) is False
    assert ff._is_empty_diff({"added": {}, "removed": {"X": 1}, "changed": {}}) is False
    assert ff._is_empty_diff({"added": {}, "removed": {}, "changed": {"X": {"from": 1, "to": 2}}}) is False
    assert ff._is_empty_diff({"added": {}, "removed": {}, "changed": {}}) is True


def test_emit_override_diff_event_callable_and_async():
    """Signature integrity — emitter is an async coroutine function.
    Runtime behaviour (DB-backed) is best-effort and intentionally
    swallows errors; we only assert the public surface stays stable."""
    import inspect
    assert inspect.iscoroutinefunction(ff.emit_override_diff_event)
    sig = inspect.signature(ff.emit_override_diff_event)
    # Public keyword-only contract: source (positional/keyword), extra (kw-only).
    assert "source" in sig.parameters
    assert "extra" in sig.parameters
    assert sig.parameters["extra"].kind == inspect.Parameter.KEYWORD_ONLY

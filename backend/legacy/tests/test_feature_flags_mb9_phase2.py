"""MB-9 Phase 2.B — Feature-flag registration regression.

Ensures the six Phase 2.B flags are declared in ``_FLAG_SPECS`` with
the correct names / kinds / defaults / scope, are visible via the
public ``all_flags()`` introspection, and degrade cleanly when no
override is present in the environment.
"""
from __future__ import annotations

import os
import pytest

from engines import feature_flags as ff


PHASE2_FLAGS = {
    "RUNNER_AFFINITY_POLICY":          ("str",  "sticky_pair_tf"),
    "RUNNER_TOKEN_GRACE_SEC":          ("int",  300),
    "RUNNER_ROTATE_INTERVAL_SEC":      ("int",  2_592_000),
    "RUNNER_AUTO_ROTATE":              ("bool", False),
    "RUNNER_PARITY_DRIFT_WINDOW_DAYS": ("int",  7),
    "RUNNER_MULTI_ACCOUNT_ENABLED":    ("bool", False),
}


def _spec(name: str) -> dict:
    for s in ff._FLAG_SPECS:
        if s["name"] == name:
            return s
    raise AssertionError(f"flag spec missing: {name}")


@pytest.mark.parametrize("name,expected", list(PHASE2_FLAGS.items()))
def test_phase2_flag_spec_present(name, expected):
    kind, default = expected
    spec = _spec(name)
    assert spec["kind"] == kind, f"{name} kind {spec['kind']} != {kind}"
    assert spec["default"] == default, f"{name} default {spec['default']!r} != {default!r}"
    assert spec["scope"] == "mb9_phase2"
    intent = spec.get("intent") or ""
    assert isinstance(intent, str) and len(intent) >= 16, (
        f"{name} must carry a non-trivial intent docstring"
    )


def test_phase2_flag_default_values_match_env_off():
    """When the operator has not set the env override the engine
    consumers MUST see the spec defaults — guarantees Phase 1 byte-
    identical behaviour holds."""
    snapshot = {}
    for n in PHASE2_FLAGS:
        snapshot[n] = os.environ.pop(n, None)
    try:
        for n, (_, default) in PHASE2_FLAGS.items():
            assert ff.flag(n) == default, f"{n} != {default}"
    finally:
        for n, v in snapshot.items():
            if v is not None:
                os.environ[n] = v


def test_phase2_flags_listed_in_all_flags():
    all_f = ff.all_flags()
    for n in PHASE2_FLAGS:
        assert n in all_f, f"{n} missing from all_flags()"
        assert all_f[n]["scope"] == "mb9_phase2"


def test_phase2_flag_env_overrides_apply():
    """Setting the env var changes the live value (sanity)."""
    name, expected_default = "RUNNER_PARITY_DRIFT_WINDOW_DAYS", 7
    prev = os.environ.get(name)
    try:
        os.environ[name] = "14"
        assert ff.flag(name) == 14
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev
        assert ff.flag(name) == expected_default


def test_phase2_int_flag_rejects_garbage_gracefully():
    """Bogus env value must fall back to default rather than crash."""
    name = "RUNNER_TOKEN_GRACE_SEC"
    prev = os.environ.get(name)
    try:
        os.environ[name] = "not-a-number"
        v = ff.flag(name)
        assert v == 300, f"expected default 300, got {v!r}"
    finally:
        if prev is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prev


def test_phase2_total_flag_count_at_least_six():
    """No accidental removal of Phase 1 flags. Phase 2.B contributed
    six entries; Phase 2.C may add more — assert ≥6 with scope mb9_phase2."""
    p2 = [s for s in ff._FLAG_SPECS if s.get("scope") == "mb9_phase2"]
    assert len(p2) >= 6, f"expected ≥6 mb9_phase2 flags, found {len(p2)}"
    # All six Phase 2.B specs must still be present.
    p2_names = {s["name"] for s in p2}
    for n in PHASE2_FLAGS:
        assert n in p2_names, f"Phase 2.B flag {n} lost"

"""Phase 2, Stage 1 — Universal Health Contract tests.

Verifies:
  * `HealthSnapshot` shape, field defaults, JSON serialisation
  * Score clamping to [0, 100]
  * Enum round-trip via to_dict()
  * `empty_snapshot()` sentinel
  * Provider registry API
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow legacy import path
_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.health.contract import (  # noqa: E402
    ActionRequired,
    FailureCount,
    HealthSnapshot,
    LastSuccessfulRun,
    RecoveryState,
    RecoveryStatus,
    ResourceUsage,
    empty_snapshot,
)


def test_empty_snapshot_shape():
    s = empty_snapshot("test_sub")
    d = s.to_dict()
    for key in [
        "subsystem", "ts",
        "health_score", "readiness_score", "confidence_score",
        "resource_usage", "last_successful_run", "failure_count", "recovery_status",
    ]:
        assert key in d, f"missing key: {key}"


def test_scores_clamp_high():
    s = HealthSnapshot(subsystem="x", health_score=999)
    assert s.health_score == 100


def test_scores_clamp_low():
    s = HealthSnapshot(subsystem="x", health_score=-50)
    assert s.health_score == 0


def test_scores_nonint_coerced():
    s = HealthSnapshot(subsystem="x", health_score="abc")  # type: ignore[arg-type]
    assert s.health_score == 0


def test_ts_auto_filled():
    s = HealthSnapshot(subsystem="x")
    assert s.ts and "T" in s.ts and s.ts.endswith("+00:00")


def test_recovery_enum_roundtrip_json():
    s = HealthSnapshot(
        subsystem="x",
        recovery_status=RecoveryStatus(
            state=RecoveryState.DEGRADED,
            reason="test",
            action_required=ActionRequired.OPERATOR_REVIEW,
        ),
    )
    d = s.to_dict()
    # JSON serialisation succeeds (no non-JSON-safe enum objects)
    j = json.dumps(d)
    parsed = json.loads(j)
    assert parsed["recovery_status"]["state"] == "degraded"
    assert parsed["recovery_status"]["action_required"] == "operator_review"


def test_resource_usage_defaults():
    s = HealthSnapshot(subsystem="x")
    ru = s.resource_usage
    assert isinstance(ru, ResourceUsage)
    assert ru.in_flight == 0
    assert ru.queue_depth == 0
    assert ru.budget_headroom is None


def test_failure_count_defaults():
    s = HealthSnapshot(subsystem="x")
    fc = s.failure_count
    assert isinstance(fc, FailureCount)
    assert fc.last_hour == 0 and fc.last_day == 0 and fc.since_boot == 0


def test_last_successful_run_defaults():
    s = HealthSnapshot(subsystem="x")
    lsr = s.last_successful_run
    assert isinstance(lsr, LastSuccessfulRun)
    assert lsr.at is None


def test_default_state_ok():
    s = HealthSnapshot(subsystem="x")
    assert s.recovery_status.state == RecoveryState.OK
    assert s.recovery_status.action_required == ActionRequired.NONE


def test_providers_registry():
    from engines.health.providers import (
        all_provider_names, collect_all, get_provider, platform_health_score,
    )
    names = all_provider_names()
    assert "coe" in names
    assert "vie" in names
    fn = get_provider("coe")
    assert fn is not None
    snap = fn()
    assert snap.subsystem == "coe"
    # collect_all returns dicts
    all_snaps = collect_all()
    assert len(all_snaps) >= 2
    # platform score is 0..100 int
    p = platform_health_score(all_snaps)
    assert 0 <= p <= 100


def test_platform_score_empty_defaults_100():
    from engines.health.providers import platform_health_score
    assert platform_health_score([]) == 100

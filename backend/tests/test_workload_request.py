"""Phase 2, Stage 1 — WorkloadRequest + WorkloadClass extension tests."""
from __future__ import annotations

import sys
from pathlib import Path

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.coe import Lane, RetryPolicy, WorkloadRequest, new_job_id  # noqa: E402
from engines.workload_classes import (  # noqa: E402
    WorkloadClass, profile_for, reservation_for, all_classes,
)


def test_workload_classes_extended_to_ten():
    names = {c.value for c in all_classes()}
    # Historical five
    assert {"api_hot", "backtest", "mutation", "factory_cycle", "agent"} <= names
    # Stage 1 additions
    assert {"market_data", "knowledge", "execution", "monitoring", "meta_learning"} <= names
    assert len(names) == 10


def test_profile_has_reservation_field():
    for c in all_classes():
        p = profile_for(c)
        assert "reservation" in p, f"{c.value} missing reservation"
        assert isinstance(p["reservation"], int)
        assert p["reservation"] >= 0


def test_execution_reservation_conservative():
    """Operator directive: 'Live execution must never be starved.'"""
    assert reservation_for(WorkloadClass.EXECUTION) >= 2


def test_market_data_responsive():
    """Operator directive: 'Market data ingestion must remain responsive.'"""
    assert reservation_for(WorkloadClass.MARKET_DATA) >= 1


def test_background_zero_reservation():
    """Operator directive: 'Background learning and research should use remaining capacity.'"""
    assert reservation_for(WorkloadClass.FACTORY_CYCLE) == 0
    assert reservation_for(WorkloadClass.META_LEARNING) == 0
    assert reservation_for(WorkloadClass.KNOWLEDGE) == 0


def test_reservation_env_override(monkeypatch):
    monkeypatch.setenv("ORCH_RESERVATION_EXECUTION", "5")
    assert reservation_for(WorkloadClass.EXECUTION) == 5


def test_reservation_env_bad_value_falls_back():
    import os
    os.environ["ORCH_RESERVATION_EXECUTION"] = "not_a_number"
    try:
        assert reservation_for(WorkloadClass.EXECUTION) >= 2  # falls back to default
    finally:
        os.environ.pop("ORCH_RESERVATION_EXECUTION", None)


def test_workload_request_defaults():
    r = WorkloadRequest()
    assert r.job_id
    assert len(r.job_id) == 16
    assert r.lane == Lane.P1.value
    assert r.retry_policy == RetryPolicy.DEFAULT.value
    assert r.submitted_at.endswith("+00:00")


def test_workload_request_roundtrip_json():
    r = WorkloadRequest(
        class_="backtest",
        lane=Lane.P0.value,
        task_name="backtest",
        submitted_by="test",
        payload={"pair": "EURUSD"},
        est_cost_usd=0.5,
        provider_hint="anthropic",
    )
    d = r.to_dict()
    import json
    j = json.dumps(d)
    parsed = json.loads(j)
    r2 = WorkloadRequest.from_dict(parsed)
    assert r2.job_id == r.job_id
    assert r2.class_ == "backtest"
    assert r2.lane == "P0"
    assert r2.provider_hint == "anthropic"
    assert r2.payload == {"pair": "EURUSD"}


def test_workload_request_ignores_unknown_fields():
    d = {"job_id": "abc", "unknown_field": "x", "class_": "backtest"}
    r = WorkloadRequest.from_dict(d)
    assert r.class_ == "backtest"
    assert not hasattr(r, "unknown_field")


def test_new_job_id_unique():
    ids = {new_job_id() for _ in range(20)}
    assert len(ids) == 20

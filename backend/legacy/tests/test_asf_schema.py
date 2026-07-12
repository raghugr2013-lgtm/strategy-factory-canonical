"""ASF schema — model coverage + unknown-key preservation."""
from __future__ import annotations

import pytest

from engines.asf.schema import (
    CalibrationSnapshot,
    DedupOutcome,
    Manifest,
    StrategyDoc,
)


def _strategy_payload(**overrides) -> dict:
    base = {
        "asf_schema_version": "1.0",
        "exported_at": "2026-02-01T00:00:00+00:00",
        "exporter": {
            "pod_host_id": "receiver",
            "build_label": "BUILD 30.4",
            "git_sha": "abc",
            "exporter_module": "engines.asf.importer.migration_adapter@v1",
        },
        "fingerprint": "a" * 40,
        "fingerprint_inputs": {
            "pair": "EURUSD",
            "timeframe": "H1",
            "style": "unknown",
            "params_canon": "x=1",
            "strategy_text": "stub",
        },
        "strategy_hash": "b" * 64,
        "strategy_text": "stub",
        "params": {"x": 1},
        "metrics": {"total_trades": 100, "profit_factor": 1.3},
        "lineage": {"parent_fingerprint": None, "ancestors_complete": False},
        "lifecycle": {"stage": "IMPORTED_SEED", "stage_locked_until": "2027-01-01T00:00:00+00:00"},
        "provenance": {"source": "1vcpu_migration", "tier_class": "T1",
                       "relaxation_reason": "pf_floor_1.20+wr_floor_0.38",
                       "cohort_id": "1vcpu_2026_migration"},
    }
    base.update(overrides)
    return base


def test_strategy_doc_minimum_roundtrip():
    sd = StrategyDoc.model_validate(_strategy_payload())
    assert sd.fingerprint == "a" * 40
    assert sd.strategy_hash == "b" * 64
    assert sd.metrics.total_trades == 100
    assert sd.lifecycle.stage == "IMPORTED_SEED"
    assert sd.provenance.tier_class == "T1"
    assert sd.provenance.relaxation_reason == "pf_floor_1.20+wr_floor_0.38"
    assert sd.provenance.cohort_id == "1vcpu_2026_migration"


def test_strategy_doc_preserves_unknown_keys():
    payload = _strategy_payload()
    payload["extensions"] = {"marketplace": {"licence": "CC-BY-SA-4.0"}}
    payload["future_field_v1_1"] = "must-survive"
    sd = StrategyDoc.model_validate(payload)
    dumped = sd.model_dump(mode="json")
    assert dumped["extensions"]["marketplace"]["licence"] == "CC-BY-SA-4.0"
    # Pydantic stores extras alongside declared fields by default.
    assert dumped.get("future_field_v1_1") == "must-survive"


def test_strategy_doc_defaults_when_minimal():
    payload = _strategy_payload()
    sd = StrategyDoc.model_validate(payload)
    # bi5_cert / explorer default to None per spec §4.1.
    assert sd.bi5_cert is None
    assert sd.explorer is None
    # portfolio + master_bot lists default to [].
    assert sd.portfolio_assignments == []
    assert sd.master_bot_memberships == []
    # historical_scores object is always present.
    assert sd.provenance.historical_scores is not None


def test_manifest_minimum_roundtrip():
    m = Manifest.model_validate({
        "asf_schema_version": "1.0",
        "package_type": "migration",
        "package_id": "pkg-uuid",
        "created_at": "2026-02-01T00:00:00+00:00",
        "exporter": {
            "pod_host_id": "receiver",
            "build_label": "BUILD 30.4",
            "git_sha": "abc",
            "exporter_module": "engines.asf.importer.migration_adapter@v1",
        },
    })
    assert m.package_type == "migration"
    assert m.schema_compatibility["min_reader_version"] == "1.0"


def test_calibration_snapshot_default_thresholds():
    c = CalibrationSnapshot(
        tick_validator_version="tick_validator@P0B-v2",
        density_table_snapshot={"EURUSD": {"H1": 0.5}},
        ranker_version="master_bot_ranker@v1.1",
    )
    assert c.pass_threshold == 0.85
    assert c.warn_threshold == 0.70


def test_invalid_stage_rejected():
    payload = _strategy_payload()
    payload["lifecycle"] = {"stage": "BOGUS_STAGE"}
    with pytest.raises(Exception):
        StrategyDoc.model_validate(payload)


def test_dedup_outcome_schema():
    o = DedupOutcome(outcome="skip", match_kind="fingerprint",
                     canonical_id="abc123")
    assert o.outcome == "skip"
    assert o.match_kind == "fingerprint"
    assert o.canonical_id == "abc123"

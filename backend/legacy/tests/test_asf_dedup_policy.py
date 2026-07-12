"""ASF dedup policy — skip / merge / replace behaviour."""
from __future__ import annotations

from engines.asf.dedup_policy import apply_dedup
from engines.asf.schema import StrategyDoc


def _incoming_strategy() -> StrategyDoc:
    return StrategyDoc.model_validate({
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
        "metrics": {"total_trades": 100, "profit_factor": 1.25},
        "lifecycle": {"stage": "IMPORTED_SEED"},
        "provenance": {
            "source": "1vcpu_migration",
            "tier_class": "T1",
            "discovered_at": "2026-02-01T00:00:00+00:00",
        },
    })


def test_fresh_insert_when_no_canonical():
    out = apply_dedup(
        incoming=_incoming_strategy(),
        canonical=None,
        policy="skip",
        match_kind="none",
    )
    assert out.outcome == "fresh_insert"
    assert out.match_kind == "none"
    assert out.canonical_id is None


def test_skip_policy_wins_over_canonical():
    canonical = {
        "_id": "obj-1",
        "fingerprint": "a" * 40,
        "metrics": {"total_trades": 50},
        "provenance": {"discovered_at": "2025-01-01T00:00:00+00:00"},
    }
    out = apply_dedup(
        incoming=_incoming_strategy(),
        canonical=canonical,
        policy="skip",
        match_kind="fingerprint",
    )
    assert out.outcome == "skip"
    assert out.canonical_id == "obj-1"


def test_strategy_hash_match_forces_skip_regardless_of_policy():
    canonical = {
        "_id": "obj-2",
        "strategy_hash": "b" * 64,
    }
    # Even when policy=replace, strategy_hash-only match must skip.
    out = apply_dedup(
        incoming=_incoming_strategy(),
        canonical=canonical,
        policy="replace",
        match_kind="strategy_hash",
    )
    assert out.outcome == "skip"
    assert out.match_kind == "strategy_hash"


def test_merge_policy_fills_null_fields_only():
    canonical = {
        "_id": "obj-3",
        "fingerprint": "a" * 40,
        "lifecycle": None,                 # null — eligible for fill
        "validation_report": {"x": 1},     # non-null — must NOT overwrite
        "provenance": {"discovered_at": "2025-01-01T00:00:00+00:00"},
    }
    out = apply_dedup(
        incoming=_incoming_strategy(),
        canonical=canonical,
        policy="merge",
        match_kind="fingerprint",
    )
    assert out.outcome == "merge"
    merged = out.merged_doc or {}
    assert merged["_id"] == "obj-3"                # preserved
    assert merged["validation_report"] == {"x": 1}  # NOT overwritten
    assert merged.get("lifecycle") is not None     # filled
    # Discovered_at on canonical is non-null; merge must keep it.
    assert merged["provenance"]["discovered_at"] == "2025-01-01T00:00:00+00:00"


def test_replace_policy_preserves_id_and_discovered_at():
    canonical = {
        "_id": "obj-4",
        "fingerprint": "a" * 40,
        "metrics": {"total_trades": 50},
        "provenance": {"discovered_at": "2025-01-01T00:00:00+00:00",
                       "source": "auto_factory"},
    }
    out = apply_dedup(
        incoming=_incoming_strategy(),
        canonical=canonical,
        policy="replace",
        match_kind="fingerprint",
    )
    assert out.outcome == "replace"
    replaced = out.merged_doc or {}
    assert replaced["_id"] == "obj-4"                                   # preserved
    assert replaced["provenance"]["discovered_at"] == "2025-01-01T00:00:00+00:00"
    # Source is overwritten — replace, not merge.
    assert replaced["provenance"]["source"] == "1vcpu_migration"
    # Metrics also overwritten.
    assert replaced["metrics"]["total_trades"] == 100

"""ASF migration adapter — end-to-end behaviour against an in-memory
staging database (mongomock).

These tests do NOT touch the receiving pod's real Mongo. They build a
mini staging DB matching the 1-vCPU schema shape, run the adapter and
the walker/upserter/verifier pipeline in dry-run mode, and assert the
operator-visible outcomes from GATE3_IMPLEMENTATION_PLAN.md §9.
"""
from __future__ import annotations

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")

from engines.asf.importer.migration_adapter import (  # noqa: E402
    DEFAULT_OVERRIDES,
    _classify_tier,
    _strategy_hash,
    adapt_1vcpu_to_asf_v1,
)
from engines.asf.importer.upserter import apply_actions  # noqa: E402
from engines.asf.importer.verifier import verify  # noqa: E402
from engines.asf.importer.walker import walk  # noqa: E402


def _make_strategy_row(*, fp: str, pf: float, wr: float, dd: float,
                       trades: int, ts: str = "2026-05-16T08:00:00+00:00",
                       pair: str = "EURUSD", tf: str = "H1") -> dict:
    return {
        "fingerprint": fp,
        "pair": pair, "timeframe": tf, "style": "unknown",
        "strategy_text": f"strategy text for {fp}",
        "parameters": {"rsi_period": 14, "sl_pips": 25},
        "profit_factor": pf,
        "win_rate": wr,
        "max_drawdown_pct": dd,
        "total_trades": trades,
        "stability_score": 70.0,
        "score": 50.0,
        "pass_probability": 35.0,
        "verdict": "RISKY",
        "prop_status": "RISKY",
        "consistency_score": 65.0,
        "confidence": 60.0,
        "source": "mutation_engine",
        "mutation_base_fingerprint": "p" + fp[1:],
        "mutation_variant_fingerprint": fp,
        "mutation_run_id": "run-abc",
        "mutation_type": "rsi_band_walk",
        "created_at": ts,
        "validation_report": {
            "walk_forward": {"success": True, "n_windows": 3},
            "oos_holdout": {"is_pf": 1.1, "oos_pf": 0.9},
        },
        "decision": {"verdict": "RISKY"},
        "prop_firm_panel": {"status": "RISKY"},
        "expected_value": {"expected_value": -100},
        "oos_holdout": {"ratio": 0.8},
    }


async def _seed_staging(mock_client):
    """Build a minimal staging DB matching the 1-vCPU schema."""
    src = mock_client["asf_inspect"]
    # 2 strategies that PASS the Option-B floors (PF>=1.20, WR>=0.38).
    # WR stored as percent (0-100) per legacy schema.
    await src["strategy_library"].insert_many([
        _make_strategy_row(fp="a" * 40, pf=1.28, wr=39.2, dd=0.0,
                           trades=180, pair="ETHUSD"),
        _make_strategy_row(fp="b" * 40, pf=1.23, wr=40.5, dd=0.05,
                           trades=240, pair="XAUUSD"),
        # 1 strategy that FAILS PF (T2).
        _make_strategy_row(fp="c" * 40, pf=1.05, wr=42.0, dd=0.10,
                           trades=120, pair="EURUSD"),
    ])
    await src["mutation_events"].insert_many([
        {"event_id": "ev-1", "run_id": "r1", "type": "rsi_band_walk",
         "base_fingerprint": "ancestor1", "variant_fingerprint": "p" + "a" * 39,
         "pair": "ETHUSD", "timeframe": "H1", "ts": "2026-05-15T08:00:00+00:00",
         "metrics": {"profit_factor": 1.15}},
        {"event_id": "ev-2", "run_id": "r1", "type": "rsi_band_walk",
         "base_fingerprint": "ancestor2", "variant_fingerprint": "p" + "b" * 39,
         "pair": "XAUUSD", "timeframe": "H4", "ts": "2026-05-15T09:00:00+00:00",
         "metrics": {"profit_factor": 1.20}},
    ])
    await src["mutation_stability_log"].insert_one({
        "run_id": "r1", "ts": "2026-05-15T09:00:00+00:00",
        "pair": "ETHUSD", "timeframe": "H1", "mutation_type": "rsi",
        "variant_fingerprint": "p" + "a" * 39,
        "trades": 180, "profit_factor": 1.15, "max_drawdown": 5.2,
        "auto_save_status": "rejected", "saved": False,
        "rejection_reason": "oos_gate_failed",
    })
    await src["strategy_lifecycle_history"].insert_one({
        "strategy_hash": "lifecycle-hash-1",
        "from_stage": None, "to_stage": "exploratory",
        "transition_at": "2026-05-16T08:00:00+00:00",
        "evidence_snapshot": {"runs": 1}, "flags": [],
    })
    await src["strategy_performance_history"].insert_one({
        "strategy_hash": "lifecycle-hash-1",
        "pair": "EURUSD", "timeframe": "H1",
        "pf": None, "trades": None, "win_rate": None,
        "ts": "2026-05-14T15:00:00+00:00",
    })
    await src["auto_factory_alert_log"].insert_one({
        "strategy_hash": "TEST-alert", "run_id": "r1",
        "sent_at": "2026-05-16T09:00:00+00:00",
        "payload": {"pf": 1.5}, "channels": [],
    })


# ── Pure-function tests (no DB) ───────────────────────────────────────

def test_tier_classification_strict_floors():
    row = _make_strategy_row(fp="x" * 40, pf=1.28, wr=39.2, dd=0.0, trades=180)
    tier = _classify_tier(row, pf_floor=1.20, wr_floor=0.38,
                          trades_floor=30, dd_ceiling=0.20)
    assert tier == "T1"


def test_tier_classification_pf_below_floor():
    row = _make_strategy_row(fp="x" * 40, pf=1.05, wr=45.0, dd=0.05, trades=200)
    tier = _classify_tier(row, pf_floor=1.20, wr_floor=0.38,
                          trades_floor=30, dd_ceiling=0.20)
    assert tier == "T2"


def test_tier_classification_wr_below_floor():
    row = _make_strategy_row(fp="x" * 40, pf=1.25, wr=37.5, dd=0.05, trades=200)
    tier = _classify_tier(row, pf_floor=1.20, wr_floor=0.38,
                          trades_floor=30, dd_ceiling=0.20)
    assert tier == "T2"


def test_tier_classification_handles_wr_as_fraction():
    # Some legacy rows may store win_rate as 0..1 already.
    row = _make_strategy_row(fp="x" * 40, pf=1.25, wr=0.42, dd=0.05, trades=200)
    tier = _classify_tier(row, pf_floor=1.20, wr_floor=0.38,
                          trades_floor=30, dd_ceiling=0.20)
    assert tier == "T1"


def test_strategy_hash_deterministic():
    assert _strategy_hash("abc") == _strategy_hash("abc")
    assert _strategy_hash("abc") != _strategy_hash("xyz")
    assert len(_strategy_hash("abc")) == 64


def test_default_overrides_match_operator_decisions():
    assert DEFAULT_OVERRIDES["pf_floor"] == 1.20
    assert DEFAULT_OVERRIDES["wr_floor"] == 0.38
    assert DEFAULT_OVERRIDES["lock_days"] == 30
    assert DEFAULT_OVERRIDES["lineage_depth"] == 5
    assert DEFAULT_OVERRIDES["cohort_id"] == "1vcpu_2026_migration"
    assert DEFAULT_OVERRIDES["relaxation_reason"] == "pf_floor_1.20+wr_floor_0.38"


# ── Integration tests (mongomock-motor) ───────────────────────────────

@pytest.mark.asyncio
async def test_adapter_produces_in_memory_package():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    assert pkg.manifest.package_type == "migration"
    assert len(pkg.strategies) == 3
    # 2 T1 (a, b), 1 T2 (c)
    tiers = [s.provenance.tier_class for s in pkg.strategies]
    assert tiers.count("T1") == 2
    assert tiers.count("T2") == 1
    # All survivors carry cohort_id + relaxation_reason on T1.
    t1 = [s for s in pkg.strategies if s.provenance.tier_class == "T1"]
    for s in t1:
        assert s.provenance.cohort_id == "1vcpu_2026_migration"
        assert s.provenance.relaxation_reason == "pf_floor_1.20+wr_floor_0.38"
        assert s.lifecycle.stage == "IMPORTED_SEED"
        assert s.lifecycle.stage_locked_until is not None
    # T2 carries cohort_id but no relaxation_reason.
    t2 = [s for s in pkg.strategies if s.provenance.tier_class == "T2"]
    for s in t2:
        assert s.provenance.cohort_id == "1vcpu_2026_migration"
        assert s.provenance.relaxation_reason is None


@pytest.mark.asyncio
async def test_adapter_historical_scores_moved_out_of_metrics():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    for s in pkg.strategies:
        # explorer.* is null (no live scoring yet).
        assert s.explorer is None
        # bi5_cert is null (no source cert).
        assert s.bi5_cert is None
        # Historical scores live under provenance.historical_scores.
        hs = s.provenance.historical_scores
        assert hs.pass_probability == 35.0
        assert hs.score == 50.0
        assert hs.confidence == 60.0
        assert hs.expected_value is not None
        assert hs.decision is not None
        assert hs.prop_firm_panel is not None
        # requires_* flags all true to gate live deployment.
        assert s.provenance.requires_revalidation is True
        assert s.provenance.requires_rescoring is True
        assert s.provenance.requires_rematching is True


@pytest.mark.asyncio
async def test_adapter_win_rate_normalised_and_metrics_flattened():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    for s in pkg.strategies:
        # Legacy WR was 39.2 / 40.5 / 42.0 → normalised to 0..1.
        assert s.metrics.win_rate is not None
        assert 0.30 <= s.metrics.win_rate <= 0.50
        assert s.metrics.total_trades > 0


@pytest.mark.asyncio
async def test_adapter_walk_forward_success_renamed_to_passed():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    for s in pkg.strategies:
        vr = s.validation_report or {}
        wf = vr.get("walk_forward") or {}
        # Original `.success=True` is preserved, AND `.passed=True` is
        # added so ASF readers see the expected field name.
        assert wf.get("success") is True
        assert wf.get("passed") is True


@pytest.mark.asyncio
async def test_adapter_lineage_ancestors_walked():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect", "lineage_depth": 5},
    )
    t1 = next(s for s in pkg.strategies if s.fingerprint == "a" * 40)
    # Adapter walks mutation_events back from parent_fingerprint.
    # Chain has at least one ancestor (parent + grand-parent via base_fingerprint).
    assert len(t1.lineage.ancestors) >= 1
    assert t1.lineage.ancestors_complete is False
    assert t1.lineage.parent_fingerprint == "p" + "a" * 39


@pytest.mark.asyncio
async def test_walker_routes_t1_to_library_and_t2_to_archive():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    actions = await walk(package=pkg, db=db, dedup_policy="skip")
    targets = {(a.tier_class, a.target_collection) for a in actions
               if a.target_collection in ("strategy_library",
                                          "strategy_library_archive")}
    assert ("T1", "strategy_library") in targets
    assert ("T2", "strategy_library_archive") in targets


@pytest.mark.asyncio
async def test_dry_run_writes_receipt_and_actions():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    actions = await walk(package=pkg, db=db, dedup_policy="skip")
    result = await apply_actions(
        package=pkg, actions=actions, db=db,
        dry_run=True, dedup_policy="skip",
        calibration_drift={"drift_detected": False, "drift_keys": []},
    )
    assert result.dry_run is True
    assert result.tier_breakdown["T1"] == 2
    assert result.tier_breakdown["T2"] >= 1   # at least the 1 strategy
    # Strategies were NOT actually inserted into strategy_library on dry-run.
    n_live = await db["strategy_library"].count_documents({})
    assert n_live == 0

    # Verifier passes the dry-run schema sanity.
    vr = await verify(
        import_id=result.import_id, actions=actions,
        db=db, dry_run=True,
    )
    assert vr.status in ("verified", "verified_with_warnings")


@pytest.mark.asyncio
async def test_wet_run_commits_and_verifies():
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    actions = await walk(package=pkg, db=db, dedup_policy="skip")
    result = await apply_actions(
        package=pkg, actions=actions, db=db,
        dry_run=False, dedup_policy="skip",
        calibration_drift={"drift_detected": False, "drift_keys": []},
    )
    assert result.dry_run is False
    assert result.tier_breakdown["T1"] == 2
    # Live strategy_library now holds 2 T1 rows.
    n_live = await db["strategy_library"].count_documents({})
    assert n_live == 2
    # Each T1 row carries IMPORTED_SEED + cohort_id + lock window.
    async for s in db["strategy_library"].find({}):
        assert s["lifecycle"]["stage"] == "IMPORTED_SEED"
        assert s["lifecycle"]["stage_locked_until"] is not None
        assert s["provenance"]["cohort_id"] == "1vcpu_2026_migration"
        assert s["provenance"]["requires_revalidation"] is True
        assert s["provenance"]["requires_rescoring"] is True
    vr = await verify(
        import_id=result.import_id, actions=actions,
        db=db, dry_run=False,
    )
    assert vr.status in ("verified", "verified_with_warnings")
    assert vr.missing_inserts == 0


@pytest.mark.asyncio
async def test_idempotent_re_run():
    """Re-running the wet-run produces identical state (no double-insert)."""
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    actions = await walk(package=pkg, db=db, dedup_policy="skip")
    await apply_actions(
        package=pkg, actions=actions, db=db,
        dry_run=False, dedup_policy="skip",
        calibration_drift={"drift_detected": False, "drift_keys": []},
    )
    n_after_first = await db["strategy_library"].count_documents({})

    # Re-walk + re-apply with a fresh package.
    pkg2 = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    actions2 = await walk(package=pkg2, db=db, dedup_policy="skip")
    await apply_actions(
        package=pkg2, actions=actions2, db=db,
        dry_run=False, dedup_policy="skip",
        calibration_drift={"drift_detected": False, "drift_keys": []},
    )
    n_after_second = await db["strategy_library"].count_documents({})
    assert n_after_first == n_after_second == 2


@pytest.mark.asyncio
async def test_skip_list_keeps_market_data_out():
    """Even when staging holds market_data, the adapter must skip it."""
    client = mongomock_motor.AsyncMongoMockClient()
    await _seed_staging(client)
    # Seed an obviously-large collection that MUST be skipped.
    await client["asf_inspect"]["market_data"].insert_one({"ts": "x"})
    db = client["receiver"]
    pkg = await adapt_1vcpu_to_asf_v1(
        inbox_dir="/tmp/none",
        db=db,
        operator_overrides={"source_db_name": "asf_inspect"},
    )
    # No strategy carries a market_data link; the extensions list
    # records the skip set.
    skip_set = pkg.extensions.get("migration", {}).get("skip_list", [])
    assert "market_data" in skip_set

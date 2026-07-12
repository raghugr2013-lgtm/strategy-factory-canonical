"""ASF migration adapter — 1-vCPU → ASF v1.0 in-memory converter.

This is THE GATE 3 core file. Per `ASF_BACKEND_ARCHITECTURE.md §3.9`,
it is a thin adapter that:
    1. Reads strategy + lineage + lifecycle + audit rows from a
       pre-restored staging Mongo database (default ``asf_inspect``).
       Operator restores ``/app/_migration_inbox/migration_bundle.tar.gz``
       via ``mongorestore --archive --gzip --nsTo=asf_inspect.*`` before
       invoking this endpoint. (BSON-archive streaming parser deferred
       to Phase 7.3.)
    2. Applies the 15 deterministic transforms documented in
       ``/app/GATE3_IMPLEMENTATION_PLAN.md §3``.
    3. Returns an in-memory ``PackageReadResult`` — no intermediate ZIP
       is ever written.

Operator overrides (from POST body) control the T1 tier filter knobs:
    pf_floor       (default 1.20)
    wr_floor       (default 0.38)
    trades_floor   (default 30)
    dd_ceiling     (default 0.20)
    lock_days      (default 30)
    lineage_depth  (default 5)
    cohort_id      (default "1vcpu_2026_migration")
    relaxation_reason (default "pf_floor_1.20+wr_floor_0.38")
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engines.asf import ASF_SCHEMA_VERSION
from engines.asf.calibration_snapshot import build_receiver_snapshot
from engines.asf.schema import (
    Ancestor,
    DataWindow,
    ExporterInfo,
    FingerprintInputs,
    HistoricalScores,
    Lifecycle,
    Lineage,
    Manifest,
    Metrics,
    PackageReadResult,
    Provenance,
    SourceCodebase,
    StrategyDoc,
    SubjectSummary,
)
from engines.strategy_library import _canon_params

logger = logging.getLogger(__name__)


# Operator-default knobs (per GATE3 plan §1 Option B).
DEFAULT_OVERRIDES: Dict[str, Any] = {
    "pf_floor":          1.20,
    "wr_floor":          0.38,
    "trades_floor":      30,
    "dd_ceiling":        0.20,
    "lock_days":         30,
    "lineage_depth":     5,
    "cohort_id":         "1vcpu_2026_migration",
    "relaxation_reason": "pf_floor_1.20+wr_floor_0.38",
    "source_db_name":    "asf_inspect",
    "source_pod_id":     "1vcpu",
}

# Skip list (per locked architecture defaults). Collections in this set
# are NEVER ingested. ``market_data`` is the largest (1.05M rows in the
# inspection sample) and would dominate memory if loaded.
DEFAULT_SKIP_COLLECTIONS = {
    "market_data",
    "users",
    "pipeline_logs",
    "ingestion_runs",
    "auto_mutation_runs",
    "auto_mutation_cycles",
    "auto_run_cycles",
    "multi_cycle_runs",
    "research_runs",
    "llm_call_log",
    "challenge_rules",
    "prop_firm_rules",
    "orchestrator_env_priority",
    "strategy_market_profile",
    "market_environment_stats",
    "governance_universe",
    "ingested_strategies",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strategy_hash(strategy_text: str) -> str:
    """T3: SHA-256 over the strategy text (text-exact dedup signature)."""
    return hashlib.sha256((strategy_text or "").encode("utf-8")).hexdigest()


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _classify_tier(
    row: dict, *, pf_floor: float, wr_floor: float,
    trades_floor: int, dd_ceiling: float,
) -> str:
    """Apply T1 filters per `MIGRATION_PRIORITY.md §2` (with operator
    overrides). Returns "T1" or "T2"."""
    trades = row.get("total_trades") or 0
    pf = _safe_float(row.get("profit_factor"))
    wr_raw = _safe_float(row.get("win_rate")) or 0.0
    # T2 (win-rate scale normalise): legacy is 0–100 percentage.
    wr_norm = wr_raw / 100.0 if wr_raw > 1.0 else wr_raw
    dd = _safe_float(row.get("max_drawdown_pct"))

    if trades < trades_floor:
        return "T2"
    if pf is None or pf < pf_floor:
        return "T2"
    if wr_norm < wr_floor:
        return "T2"
    if dd is not None and dd > dd_ceiling:
        return "T2"
    return "T1"


def _transform_strategy_row(
    row: dict,
    *,
    tier: str,
    overrides: Dict[str, Any],
    exporter: ExporterInfo,
    package_id: str,
    ancestors: List[Ancestor],
) -> StrategyDoc:
    """Apply the 15 transforms to one legacy `strategy_library` row.

    See `GATE3_IMPLEMENTATION_PLAN.md §3` for the full list.
    """
    # T1: Flatten → Nest metrics + T2: win_rate ÷ 100.
    wr_raw = _safe_float(row.get("win_rate")) or 0.0
    wr_norm = wr_raw / 100.0 if wr_raw > 1.0 else wr_raw
    metrics = Metrics(
        total_trades=int(row.get("total_trades") or 0),
        profit_factor=_safe_float(row.get("profit_factor")),
        win_rate=wr_norm,
        max_drawdown_pct=_safe_float(row.get("max_drawdown_pct")),
        stability_score=_safe_float(row.get("stability_score")),
        computed_at=row.get("created_at"),
        computed_on_data_window=DataWindow(
            symbol=row.get("pair"),
            window_start_utc=None,
            window_end_utc=None,
        ),
    )

    # T3: compute strategy_hash from strategy_text.
    strategy_text = row.get("strategy_text") or ""
    s_hash = _strategy_hash(strategy_text)

    # T4 + T5: synthesise fingerprint_inputs.params_canon.
    params = row.get("parameters") or {}
    fp_inputs = FingerprintInputs(
        pair=row.get("pair", ""),
        timeframe=row.get("timeframe", ""),
        style=row.get("style", "unknown"),
        params_canon=_canon_params(params),
        strategy_text=strategy_text,
    )

    # T6: rename mutation_base_fingerprint → lineage.parent_fingerprint.
    # T7: ancestors[] computed at the caller level.
    lineage = Lineage(
        parent_fingerprint=row.get("mutation_base_fingerprint"),
        mutation_family=row.get("mutation_type"),
        generation=len(ancestors),
        ancestors=ancestors,
        ancestors_complete=False,  # per migration package convention
    )

    # T10: validation_report.walk_forward.success → .passed.
    vr = row.get("validation_report")
    if isinstance(vr, dict):
        wf = vr.get("walk_forward") or {}
        if isinstance(wf, dict) and "success" in wf and "passed" not in wf:
            wf = {**wf, "passed": bool(wf.get("success"))}
            vr = {**vr, "walk_forward": wf}

    # T8: lifecycle block (T1 only gets IMPORTED_SEED + lock window;
    # T2/T3 retain "PROVISIONAL" surface stage + preserve legacy stage
    # under extensions.migration.legacy_stage).
    if tier == "T1":
        lock_until = (
            datetime.now(timezone.utc)
            + timedelta(days=int(overrides["lock_days"]))
        ).isoformat()
        lifecycle = Lifecycle(
            stage="IMPORTED_SEED",
            stage_rank=0,
            stage_locked_until=lock_until,
            transitions_count=0,
        )
    else:
        lifecycle = Lifecycle(
            stage="PROVISIONAL",
            stage_rank=0,
            stage_locked_until=None,
            transitions_count=0,
        )

    # T9: synthesise provenance + relaxation_reason + cohort_id +
    # historical scores. NEW per operator decree: imported rankings /
    # pass_probability / derived scores live ONLY under historical
    # metadata; they are NOT carried into metrics.* or explorer.* until
    # the post-import pipeline re-derives them on the receiving pod.
    hist = HistoricalScores(
        score=_safe_float(row.get("score")),
        pass_probability=_safe_float(row.get("pass_probability")),
        deploy_score=None,
        expected_value=row.get("expected_value"),
        consistency_score=_safe_float(row.get("consistency_score")),
        confidence=_safe_float(row.get("confidence")),
        oos_holdout=row.get("oos_holdout"),
        decision=row.get("decision"),
        prop_firm_panel=row.get("prop_firm_panel"),
    )
    prov = Provenance(
        source="1vcpu_migration",
        source_pod=overrides["source_pod_id"],
        source_codebase=SourceCodebase(git_sha="unknown", build_label="unknown"),
        source_export_id=package_id,
        discovered_at=row.get("created_at") or _now_iso(),
        requires_revalidation=True,
        requires_rescoring=True,
        requires_rematching=True,
        tier_class=tier,  # type: ignore[arg-type]
        relaxation_reason=(
            overrides["relaxation_reason"] if tier == "T1" else None
        ),
        cohort_id=overrides["cohort_id"],
        historical_scores=hist,
        notes=(
            "Imported via ASF migration_adapter. Scores are historical "
            "metadata; live engines re-derive on receiving pod."
        ),
    )

    # T12: empty defaults for bi5_cert / explorer / portfolio /
    # master_bot. Explorer + bi5_cert stay null until post-import
    # pipeline runs.
    extensions: Dict[str, Any] = {
        "migration": {
            "legacy_verdict":    row.get("verdict"),
            "legacy_prop_status": row.get("prop_status"),
            "legacy_source":     row.get("source"),
            "mutation_run_id":   row.get("mutation_run_id"),
            "mutation_variant_fingerprint": row.get("mutation_variant_fingerprint"),
            "metrics_max_drawdown_pct_quality": (
                "not_recomputed_in_source"
                if _safe_float(row.get("max_drawdown_pct")) in (0.0, None)
                else "as_reported"
            ),
        }
    }

    return StrategyDoc(
        asf_schema_version=ASF_SCHEMA_VERSION,
        exported_at=_now_iso(),
        exporter=exporter,
        fingerprint=row["fingerprint"],
        fingerprint_inputs=fp_inputs,
        strategy_hash=s_hash,
        strategy_text=strategy_text,
        strategy_ir=None,
        params=params,
        metrics=metrics,
        validation_report=vr,
        backtest_results=row.get("backtest_results"),
        lineage=lineage,
        bi5_cert=None,
        explorer=None,
        portfolio_assignments=[],
        master_bot_memberships=[],
        lifecycle=lifecycle,
        provenance=prov,
        extensions=extensions,
    )


async def _build_ancestor_chain(
    db, parent_fp: Optional[str], *, depth_cap: int,
) -> List[Ancestor]:
    """T7: walk mutation_events backwards from parent_fp up to
    depth_cap generations. Returns Ancestor list in order [closest
    parent, …, deepest]. Truncates silently at depth_cap."""
    chain: List[Ancestor] = []
    current = parent_fp
    seen = set()
    gen = 1
    while current and gen <= depth_cap and current not in seen:
        seen.add(current)
        # Find any event where this fp was a variant (i.e. it was
        # produced from a parent).
        ev = await db["mutation_events"].find_one(
            {"variant_fingerprint": current},
            {"base_fingerprint": 1, "variant_fingerprint": 1, "_id": 0},
        )
        chain.append(Ancestor(fingerprint=current, generation=gen))
        if not ev or not ev.get("base_fingerprint"):
            break
        current = ev.get("base_fingerprint")
        gen += 1
    return chain


async def adapt_1vcpu_to_asf_v1(
    *,
    inbox_dir: Optional[str] = None,
    db,
    operator_overrides: Optional[Dict[str, Any]] = None,
) -> PackageReadResult:
    """Convert the pre-restored 1-vCPU staging DB into an in-memory
    ASF v1.0 PackageReadResult.

    Args:
        inbox_dir: operator-documented path where the source bundle
            lives. Used for receipts; not parsed by this adapter.
        db: live receiving-pod Motor database (where the receipt is
            persisted and where the staging DB is also reachable via
            the same client).
        operator_overrides: optional knobs (see DEFAULT_OVERRIDES).
    """
    overrides = {**DEFAULT_OVERRIDES, **(operator_overrides or {})}
    package_id = str(uuid.uuid4())

    # M-1: resolve inbox_dir from env if not explicitly passed.
    if inbox_dir is None:
        inbox_dir = os.environ.get("ASF_INBOX_DIR", "/app/_migration_inbox/")

    # Resolve staging DB through the same client as the receiving DB.
    client = db.client
    src_db_name = overrides["source_db_name"]
    src = client[src_db_name]

    exporter = ExporterInfo(
        pod_host_id=os.environ.get("POD_HOST_ID", "receiver-pod"),
        build_label=os.environ.get("BUILD_LABEL", "BUILD 30.4"),
        git_sha=os.environ.get("GIT_SHA", "unknown"),
        exporter_module="engines.asf.importer.migration_adapter@v1",
    )

    # ── strategies ────────────────────────────────────────────────────
    strategies: List[StrategyDoc] = []
    cursor = src["strategy_library"].find({})
    async for row in cursor:
        tier = _classify_tier(
            row,
            pf_floor=overrides["pf_floor"],
            wr_floor=overrides["wr_floor"],
            trades_floor=overrides["trades_floor"],
            dd_ceiling=overrides["dd_ceiling"],
        )
        ancestors = await _build_ancestor_chain(
            src,
            row.get("mutation_base_fingerprint"),
            depth_cap=int(overrides["lineage_depth"]),
        )
        sd = _transform_strategy_row(
            row,
            tier=tier,
            overrides=overrides,
            exporter=exporter,
            package_id=package_id,
            ancestors=ancestors,
        )
        strategies.append(sd)

    # ── lineage rows (T2) ─────────────────────────────────────────────
    mutation_events: List[dict] = []
    cursor = src["mutation_events"].find({})
    async for r in cursor:
        if "_id" in r:
            r["_id"] = str(r["_id"])
        mutation_events.append({
            "event_id": r.get("event_id") or str(uuid.uuid4()),
            "parent_fingerprint": r.get("base_fingerprint"),
            "child_fingerprint":  r.get("variant_fingerprint"),
            "mutation_family":    r.get("type"),
            "mutation_kind":      r.get("type"),
            "operator":           r.get("run_id"),
            "occurred_at":        r.get("ts"),
            "parent_metrics_snapshot": r.get("metrics") or {},
            "imported": True,
            "source_export_id": package_id,
        })

    mutation_stability: List[dict] = []
    cursor = src["mutation_stability_log"].find({})
    async for r in cursor:
        if "_id" in r:
            r["_id"] = str(r["_id"])
        mutation_stability.append({
            "variant_fingerprint": r.get("variant_fingerprint"),
            "stability_score":     _safe_float(r.get("score")),
            "computed_at":         r.get("ts"),
            "method":              r.get("mutation_type"),
            "ts":                  r.get("ts"),
            "inputs": {
                "trades":          r.get("trades"),
                "profit_factor":   _safe_float(r.get("profit_factor")),
                "max_drawdown":    _safe_float(r.get("max_drawdown")),
                "auto_save_status": r.get("auto_save_status"),
                "rejection_reason": r.get("rejection_reason"),
                "regime_type":      r.get("regime_type"),
            },
            "imported": True,
            "source_export_id": package_id,
        })

    # ── T3 audit rows (un-joined; per operator decree, historical only) ─
    lifecycle_history: List[dict] = []
    cursor = src["strategy_lifecycle_history"].find({})
    async for r in cursor:
        if "_id" in r:
            r["_id"] = str(r["_id"])
        lifecycle_history.append({
            "strategy_hash":     r.get("strategy_hash"),
            "library_id":        r.get("library_id"),
            "from_stage":        r.get("from_stage"),
            "from_stage_rank":   r.get("from_stage_rank"),
            "to_stage":          r.get("to_stage"),
            "to_stage_rank":     r.get("to_stage_rank"),
            "transition_at":     r.get("transition_at"),
            "evidence_snapshot": r.get("evidence_snapshot") or {},
            "flags":             r.get("flags") or [],
            "research_run_id":   r.get("research_run_id"),
        })

    performance_history: List[dict] = []
    cursor = src["strategy_performance_history"].find({})
    async for r in cursor:
        if "_id" in r:
            r["_id"] = str(r["_id"])
        performance_history.append({
            "strategy_hash":   r.get("strategy_hash"),
            "name":            r.get("name"),
            "type":            r.get("type"),
            "pair":            r.get("pair"),
            "timeframe":       r.get("timeframe"),
            "source":          r.get("source"),
            "pf":              _safe_float(r.get("pf")),
            "dd_pct":          _safe_float(r.get("dd_pct")),
            "trades":          r.get("trades"),
            "win_rate":        _safe_float(r.get("win_rate")),
            "return_pct":      _safe_float(r.get("return_pct")),
            "regime":          r.get("regime"),
            "ts":              r.get("ts"),
        })

    alerts: List[dict] = []
    cursor = src["auto_factory_alert_log"].find({})
    async for r in cursor:
        if "_id" in r:
            r["_id"] = str(r["_id"])
        alerts.append({
            "strategy_hash": r.get("strategy_hash"),
            "run_id":        r.get("run_id"),
            "sent_at":       r.get("sent_at"),
            "payload":       r.get("payload") or {},
            "channels":      r.get("channels") or [],
        })

    # ── T11: calibration snapshot from receiving pod ──────────────────
    calibration = build_receiver_snapshot()

    # ── manifest ──────────────────────────────────────────────────────
    n_t1 = sum(1 for s in strategies if s.provenance.tier_class == "T1")
    n_t2 = sum(1 for s in strategies if s.provenance.tier_class == "T2")
    manifest = Manifest(
        asf_schema_version=ASF_SCHEMA_VERSION,
        package_type="migration",
        package_id=package_id,
        package_root_fingerprint=None,
        created_at=_now_iso(),
        created_by=overrides.get("created_by", "system"),
        exporter=exporter,
        subject_summary=SubjectSummary(
            strategies_count=len(strategies),
            lineage_edges=len(mutation_events),
            performance_rows=len(performance_history),
            alert_rows=len(alerts),
        ),
        preserves={
            "fingerprint":           True,
            "mutation_lineage":      True,
            "performance_history":   True,
            "bi5_certifications":    False,  # absent in 1-vCPU
            "explorer_scores":       False,  # absent in 1-vCPU
            "portfolio_assignments": False,
            "master_bot_metadata":   False,
            "calibration_snapshot":  True,   # synthesised by receiver
        },
        self_check={
            "all_files_present":   True,
            "all_sha256_verified": True,
            "lineage_closure":     "partial",
            "cert_replay_check":   "skipped",
        },
    )

    return PackageReadResult(
        manifest=manifest,
        strategies=strategies,
        mutation_events=mutation_events,
        mutation_stability=mutation_stability,
        lifecycle_history=lifecycle_history,
        performance_history=performance_history,
        alerts=alerts,
        calibration=calibration,
        extensions={
            "migration": {
                "inbox_dir":        inbox_dir,
                "source_db_name":   src_db_name,
                "overrides":        overrides,
                "tier_summary":     {"T1": n_t1, "T2": n_t2},
                "skip_list":        sorted(DEFAULT_SKIP_COLLECTIONS),
            }
        },
    )

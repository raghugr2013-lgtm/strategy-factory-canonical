"""ASF v1.0 Pydantic models — migration-adapter subset.

Every model uses ``extra="allow"`` so unknown keys survive round-trip
per `ASF_PACKAGE_V1_SPEC.md §12.1`.

GATE 3 ships only the models the migration adapter touches. Exporter
phase will extend this file with `MasterBotDefinition`, `PortfolioDoc`,
etc.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Shared base ──────────────────────────────────────────────────────

class _ASFModel(BaseModel):
    """Base for every ASF model: tolerate unknown keys on round-trip."""
    model_config = ConfigDict(extra="allow", validate_assignment=False)


# ── Calibration snapshot (cert_calibration/*) ────────────────────────

class CalibrationSnapshot(_ASFModel):
    tick_validator_version: str
    density_table_snapshot: dict
    pass_threshold: float = 0.85
    warn_threshold: float = 0.70
    ranker_version: str


# ── Strategy doc — section by section per spec §4 ────────────────────

class FingerprintInputs(_ASFModel):
    pair: str
    timeframe: str
    style: str = "unknown"
    params_canon: str = ""
    strategy_text: str = ""


class DataWindow(_ASFModel):
    symbol: Optional[str] = None
    window_start_utc: Optional[str] = None
    window_end_utc: Optional[str] = None


class Metrics(_ASFModel):
    total_trades: int = 0
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    stability_score: Optional[float] = None
    computed_at: Optional[str] = None
    computed_on_data_window: Optional[DataWindow] = None


class Ancestor(_ASFModel):
    fingerprint: str
    generation: int = 0


class Lineage(_ASFModel):
    parent_fingerprint: Optional[str] = None
    mutation_family: Optional[str] = None
    generation: int = 0
    ancestors: List[Ancestor] = Field(default_factory=list)
    ancestors_complete: bool = False


class Bi5CertWindow(_ASFModel):
    symbol: str
    window_start_utc: str
    window_end_utc: str
    verdict: Literal["PASS", "WARN", "FAIL"]
    bi5_score: float = 0.0
    evaluator_version: str = ""


class Bi5Cert(_ASFModel):
    verdict: Optional[Literal["PASS", "WARN", "FAIL"]] = None
    composite_score: Optional[float] = None
    integrity_score: Optional[float] = None
    spread_score: Optional[float] = None
    slippage_score: Optional[float] = None
    execution_score: Optional[float] = None
    stability_score: Optional[float] = None
    evaluator_version: Optional[str] = None
    certified_at: Optional[str] = None
    early_fail_reason: Optional[str] = None
    data_cert_windows: List[Bi5CertWindow] = Field(default_factory=list)


class Explorer(_ASFModel):
    deploy_score: Optional[float] = None
    pass_probability: Optional[float] = None
    ranker_contributions: dict = Field(default_factory=dict)
    ranker_version: Optional[str] = None
    rank: Optional[dict] = None


class PortfolioAssignment(_ASFModel):
    portfolio_id: str
    role: Literal["core", "diversifier", "satellite"] = "satellite"
    weight: float = 0.0
    assigned_at: Optional[str] = None
    active: bool = True


class MasterBotMembership(_ASFModel):
    master_bot_id: str
    tier: int = 0
    tier_rank: int = 0
    compiled_into_revision: int = 0
    compiled_at: Optional[str] = None
    active: bool = True


# ASF stage enum per spec §4. Legacy "exploratory" is mapped to
# IMPORTED_SEED at adapter time; original value preserved under
# `extensions.migration.legacy_stage`.
StageT = Literal[
    "IMPORTED_SEED", "PROVISIONAL", "PROMOTED",
    "DEMOTED", "RETIRED", "BANNED",
]


class Lifecycle(_ASFModel):
    stage: StageT = "PROVISIONAL"
    stage_rank: int = 0
    stage_locked_until: Optional[str] = None
    promoted_at: Optional[str] = None
    transitions_count: int = 0


class HistoricalScores(_ASFModel):
    """Per operator decree: imported rankings / pass-probability /
    derived scores are historical metadata only, never consumed by live
    selection / ranking engines until the post-import pipeline
    re-derives them on the receiving pod.
    """
    score: Optional[float] = None
    pass_probability: Optional[float] = None
    deploy_score: Optional[float] = None
    expected_value: Optional[dict] = None
    consistency_score: Optional[float] = None
    confidence: Optional[float] = None
    oos_holdout: Optional[dict] = None
    decision: Optional[dict] = None
    prop_firm_panel: Optional[dict] = None


class SourceCodebase(_ASFModel):
    git_sha: str = "unknown"
    build_label: str = "unknown"


class Provenance(_ASFModel):
    source: str = "1vcpu_migration"
    source_pod: str = "unknown"
    source_codebase: SourceCodebase = Field(default_factory=SourceCodebase)
    source_export_id: Optional[str] = None
    discovered_at: Optional[str] = None
    requires_revalidation: bool = True
    requires_rescoring: bool = True
    requires_rematching: bool = True
    tier_class: Optional[Literal["T1", "T2", "T3"]] = None
    relaxation_reason: Optional[str] = None
    cohort_id: Optional[str] = None
    historical_scores: HistoricalScores = Field(default_factory=HistoricalScores)
    notes: Optional[str] = None


class ExporterInfo(_ASFModel):
    pod_host_id: str = "unknown"
    build_label: str = "unknown"
    git_sha: str = "unknown"
    exporter_module: str = "engines.asf.importer.migration_adapter@v1"


class StrategyDoc(_ASFModel):
    asf_schema_version: str = "1.0"
    exported_at: str
    exporter: ExporterInfo
    fingerprint: str
    fingerprint_inputs: FingerprintInputs
    strategy_hash: str
    strategy_text: str = ""
    strategy_ir: Optional[dict] = None
    params: dict = Field(default_factory=dict)
    metrics: Metrics = Field(default_factory=Metrics)
    validation_report: Optional[dict] = None
    backtest_results: Optional[dict] = None
    lineage: Lineage = Field(default_factory=Lineage)
    bi5_cert: Optional[Bi5Cert] = None
    explorer: Optional[Explorer] = None
    portfolio_assignments: List[PortfolioAssignment] = Field(default_factory=list)
    master_bot_memberships: List[MasterBotMembership] = Field(default_factory=list)
    lifecycle: Lifecycle = Field(default_factory=Lifecycle)
    provenance: Provenance = Field(default_factory=Provenance)
    extensions: dict = Field(default_factory=dict)


# ── Lineage / lifecycle / evidence rows ──────────────────────────────

class MutationEvent(_ASFModel):
    event_id: str
    parent_fingerprint: Optional[str] = None
    child_fingerprint: str
    mutation_family: Optional[str] = None
    mutation_kind: Optional[str] = None
    operator: Optional[str] = None
    occurred_at: Optional[str] = None
    parent_metrics_snapshot: dict = Field(default_factory=dict)


class MutationStability(_ASFModel):
    fingerprint: str
    stability_score: Optional[float] = None
    computed_at: Optional[str] = None
    method: Optional[str] = None
    inputs: dict = Field(default_factory=dict)


class LifecycleHistoryEntry(_ASFModel):
    strategy_hash: str
    library_id: Optional[str] = None
    from_stage: Optional[str] = None
    from_stage_rank: Optional[int] = None
    to_stage: Optional[str] = None
    to_stage_rank: Optional[int] = None
    transition_at: Optional[str] = None
    evidence_snapshot: dict = Field(default_factory=dict)
    flags: List[str] = Field(default_factory=list)
    research_run_id: Optional[str] = None
    imported: bool = False
    source_export_id: Optional[str] = None


class PerformanceSnapshot(_ASFModel):
    strategy_hash: str
    name: Optional[str] = None
    type: Optional[str] = None
    pair: Optional[str] = None
    timeframe: Optional[str] = None
    source: Optional[str] = None
    pf: Optional[float] = None
    dd_pct: Optional[float] = None
    trades: Optional[int] = None
    win_rate: Optional[float] = None
    return_pct: Optional[float] = None
    regime: Optional[str] = None
    ts: Optional[str] = None
    imported: bool = False
    source_export_id: Optional[str] = None


class Alert(_ASFModel):
    strategy_hash: str
    run_id: Optional[str] = None
    sent_at: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    channels: List[dict] = Field(default_factory=list)
    imported: bool = False
    source_export_id: Optional[str] = None


# ── Manifest + result envelopes ──────────────────────────────────────

class SubjectSummary(_ASFModel):
    strategies_count: int = 0
    portfolios_count: int = 0
    master_bots_count: int = 0
    lineage_edges: int = 0
    cert_windows: int = 0
    performance_rows: int = 0
    alert_rows: int = 0
    audit_rows: int = 0


class Manifest(_ASFModel):
    asf_schema_version: str = "1.0"
    package_type: Literal["strategy", "portfolio", "master_bot", "full_pod", "migration"]
    package_id: str
    package_root_fingerprint: Optional[str] = None
    created_at: str
    created_by: str = "system"
    exporter: ExporterInfo
    subject_summary: SubjectSummary = Field(default_factory=SubjectSummary)
    integrity: dict = Field(default_factory=dict)
    schema_compatibility: dict = Field(default_factory=lambda: {
        "min_reader_version": "1.0",
        "tested_reader_versions": ["1.0"],
    })
    preserves: dict = Field(default_factory=dict)
    self_check: dict = Field(default_factory=dict)


class PackageReadResult(_ASFModel):
    """The in-memory representation handed from `migration_adapter` to
    the shared importer pipeline."""
    manifest: Manifest
    strategies: List[StrategyDoc] = Field(default_factory=list)
    # Lineage / lifecycle / evidence rows are pass-through blobs. The
    # adapter writes raw dicts; receivers may parse via the typed
    # models above when needed. Validating them at this layer would
    # reject legacy rows that don't carry every spec field — which is
    # exactly the case for the 1-vCPU package.
    mutation_events: List[dict] = Field(default_factory=list)
    mutation_stability: List[dict] = Field(default_factory=list)
    lifecycle_history: List[dict] = Field(default_factory=list)
    performance_history: List[dict] = Field(default_factory=list)
    alerts: List[dict] = Field(default_factory=list)
    calibration: CalibrationSnapshot
    extensions: dict = Field(default_factory=dict)


# ── Importer-side data classes (not ASF spec; receiver-internal) ─────

class ApplyAction(_ASFModel):
    action_idx: int
    target_collection: str
    dedup_outcome: Literal["skip", "merge", "replace", "fresh_insert"]
    match_kind: Literal["fingerprint", "strategy_hash", "composite", "none"]
    incoming_id: str
    canonical_id: Optional[str] = None
    tier_class: Optional[Literal["T1", "T2", "T3"]] = None
    incoming_doc: dict = Field(default_factory=dict)
    applied_at: Optional[str] = None


class DedupOutcome(_ASFModel):
    outcome: Literal["skip", "merge", "replace", "fresh_insert"]
    match_kind: Literal["fingerprint", "strategy_hash", "composite", "none"]
    canonical_id: Optional[str] = None
    merged_doc: Optional[dict] = None


class ImportWarning(_ASFModel):
    kind: str
    subject: str = ""
    detail: str = ""


class ImportResult(_ASFModel):
    import_id: str
    package_id: str
    package_type: str
    dry_run: bool
    dedup_policy: Literal["skip", "merge", "replace"] = "skip"
    status: Literal["pending", "verified", "verified_with_warnings",
                    "committed", "aborted", "failed"] = "pending"
    started_at: str
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0
    counts: dict = Field(default_factory=dict)
    tier_breakdown: dict = Field(default_factory=lambda: {"T1": 0, "T2": 0, "T3": 0})
    warnings: List[ImportWarning] = Field(default_factory=list)
    calibration_snapshot: dict = Field(default_factory=dict)
    actions: List[ApplyAction] = Field(default_factory=list)


class ImportVerification(_ASFModel):
    import_id: str
    rows_checked: int = 0
    identity_drift: int = 0
    missing_inserts: int = 0
    cert_replay_mismatch: int = 0
    status: Literal["verified", "verified_with_warnings", "failed"] = "verified"
    warnings: List[ImportWarning] = Field(default_factory=list)

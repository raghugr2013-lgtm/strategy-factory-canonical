"""v1.2.0-alpha2 Phase I — Meta-Learning Engine.

Independent engine — read-only in OBSERVE mode. Reads outcome_events
from every prior phase, evaluates how well each decision surface
(brain weights, thresholds, portfolio caps, market weights,
execution gates) predicted realised outcomes, and produces ranked
recommendations for operator (or future autonomous) review.

Design guarantees (§17 in design doc):
  * OBSERVE mode structurally cannot mutate any active surface.
  * No edits to brain / portfolio / execution / market source files.
  * Deterministic + explainable — every recommendation carries a
    full immutable-ID evidence chain.
  * Additive package + additive router + additive orchestrator task.
  * Instant rollback via `META_LEARNING_MODE=disabled`.

Master switch: `META_LEARNING_MODE` (default `observe`).
"""
from __future__ import annotations

from .types import (           # noqa: F401
    MetaEvaluation, MetaRecommendation, MetaApplication,
    MetaLearningConfig, MetaMode, MetaSurface, MetaSeverity, MetaRiskBand,
    MetaRecStatus,
)
from .config import (          # noqa: F401
    mode, cadence_sec, window_hours, min_samples,
    sig_threshold, weight_step, max_delta_per_tick,
    rec_ttl_days, rank_floor, calib_gap_min, autonomous_confirm,
    warmup_until, use_meta_overrides_brain,
    use_meta_overrides_portfolio, use_meta_overrides_exec,
    autonomous_whitelist, class_caps, config_snapshot,
)
from .ledger import (          # noqa: F401
    ensure_indexes,
    upsert_evaluation, read_evaluation, read_evaluations,
    upsert_recommendation, read_recommendation, read_recommendations,
    read_pending_recommendations, update_recommendation_status,
    upsert_application, read_applications,
    upsert_override, read_override, read_overrides, delete_override,
    append_mode_change, read_mode_history,
    wipe_all,
)
from .engine import run_meta_learning_cycle  # noqa: F401

"""v1.2.0-alpha2 Phase J — Factory Self-Evaluation engine.

Factory-level peer of Phase I Meta-Learning. Aggregates outcome_events
+ engine ledgers to evaluate the factory's health, efficiency, and
evolution as a whole. Recommends compute reallocation, budget shifts,
research investment, strategy pruning candidates, portfolio hints,
and preferred execution paths.

OBSERVE mode is the default. In OBSERVE, downstream engines are
untouched — Phase J writes only to its own factory_eval_* collections
and emits outcome events.

Master switch: `FACTORY_EVAL_MODE` (default `observe`).
"""
from __future__ import annotations

from .types import (           # noqa: F401
    FactoryReport, FactoryInsight, FactoryRecommendation,
    FactoryApplication, FactoryEvalConfig,
    FEMode, FESurface, FESeverity, FERiskBand, FERecStatus,
)
from .config import (          # noqa: F401
    mode, cadence_sec, daily_report_hour,
    window_hours_short, window_hours_long,
    min_samples, sig_threshold, max_delta_per_tick,
    rec_ttl_days, rank_floor, autonomous_confirm,
    autonomous_whitelist, class_caps,
    use_overrides_orch, use_overrides_exec, use_overrides_learning,
    config_snapshot,
)
from .ledger import (          # noqa: F401
    ensure_indexes,
    upsert_report, read_report, read_reports, read_latest_report,
    upsert_insight, read_insight, read_insights,
    upsert_recommendation, read_recommendation, read_recommendations,
    read_pending_recommendations, update_recommendation_status,
    upsert_application, read_applications,
    upsert_override, read_override, read_overrides, delete_override,
    append_mode_change, read_mode_history,
    wipe_all,
)
from .engine import run_factory_evaluation_cycle  # noqa: F401

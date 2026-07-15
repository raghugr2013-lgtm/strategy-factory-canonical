"""Learning package — outcome-event ledger + Phase B self-improving engine."""
from .emitter import (           # noqa: F401
    emit,
    emit_generate,
    emit_operator_decision,
    emit_outcome,
    ensure_indexes,
    hash_context,
    new_run_id,
    OutcomeEvent,
    SCHEMA_VERSION,
    VALID_STAGES,
    COLL,
)
from . import config             # noqa: F401
from .lineage import stamp_lineage, get_lineage    # noqa: F401
from .supervisor import (        # noqa: F401
    LearningRun,
    LearningSeed,
    counters_snapshot,
    get_run,
    run_learning_cycle,
    scheduler_status,
    start_scheduler,
    stop_scheduler,
)

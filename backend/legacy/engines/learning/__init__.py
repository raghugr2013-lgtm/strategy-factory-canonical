"""Learning package — outcome-event ledger for the v1.2.0-alpha2 milestone."""
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

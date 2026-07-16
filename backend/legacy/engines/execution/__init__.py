"""v1.2.0-alpha2 Phase H — Execution Intelligence engine.

Independent engine — loosely coupled to Trading Brain / Portfolio /
Market Intelligence via CONTRACTS + EVENTS. Execution NEVER mutates
brain state directly; feedback flows via outcome_events → closed
learning → knowledge → future brain decisions.

Master switch: `EXEC_ENABLED` (default true, but with `BROKER=paper`
so nothing hits a live venue by default).

Two-step opt-in for brain integration (mirrors Phase G):
  * `EXEC_LIVE_MEASUREMENT=true`  — ledger measures live quality
  * `BRAIN_USES_LIVE_EXECUTION=true` — brain consumes measurements

Backward compatible: with defaults, all Phase A–G behaviour is
byte-identical to Phase G. `PaperBrokerAdapter` is deterministic and
requires no external credentials → CI / dev / VPS boot is always safe.
"""
from __future__ import annotations

from .types import (            # noqa: F401
    OrderRequest, OrderState, FillEvent, Position, PositionState,
    BrokerHealth, ExecutionQualitySnapshot, ExecutionAttribution,
    JournalEvent, JournalEventType, RiskRecommendation, RiskGuard,
)
from .config import (           # noqa: F401
    exec_enabled, broker_name, broker_kill_switch, live_measurement_enabled,
    brain_uses_live_execution, exec_config_snapshot,
    risk_thresholds, health_windows, broker_credentials,
    default_account_id,
)
from .ledger import (           # noqa: F401
    ensure_indexes,
    append_order_request, update_order_state, read_order,
    read_orders, append_fill_event, read_fills,
    upsert_position, read_position, read_positions,
    read_closed_positions,
    upsert_broker_health, read_latest_broker_health, read_broker_health_history,
    upsert_execution_quality, read_execution_quality,
    upsert_attribution, read_attribution, read_attributions_for_strategy,
    append_journal, read_journal_range, wipe_account,
)
from .ledger_backends import (  # noqa: F401
    LedgerBackend, MemoryLedgerBackend, MongoLedgerBackend,
    get_backend, set_backend, reset_backend, active_backend_name,
)
from .broker import (           # noqa: F401
    BrokerAdapter, BrokerError, BrokerDisconnected,
    PaperBrokerAdapter, get_paper_adapter, reset_paper_adapter,
    get_active_adapter,
)
from .order_lifecycle import (  # noqa: F401
    submit_order, process_fill, cancel_order,
)
from .position_lifecycle import apply_fill_to_position  # noqa: F401
from .broker_health import (      # noqa: F401
    sample_broker_health, read_latest_health,
    is_broker_healthy_for_new_orders, compute_health_score,
)

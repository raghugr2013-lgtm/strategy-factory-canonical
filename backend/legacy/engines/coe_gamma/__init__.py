"""Phase 2 Stage 4 — COE γ package (P4B).

Additive resilience layer on top of the existing orchestrator. Every
module in this package is feature-flag gated and dormant by default;
the existing COE α/β behaviour is preserved byte-identically until
each flag is explicitly enabled.

Design invariants:
  * Every module is standalone — no reach into orchestrator internals.
  * Composition happens through explicit hook points that the operator
    wires post-freeze during Coherent UKIE Activation.
  * Every mutation writes an audit row.
  * Every operator control action is admin-gated + audited.
"""
from .retry_executor import (                                   # noqa: F401
    CLASS_RETRY_POLICIES,
    RetryOutcome,
    RetryExecutor,
    is_retry_enabled,
    retry_policy_for_class,
)
from .dead_letter import (                                      # noqa: F401
    DEAD_LETTER_COLLECTION,
    DeadLetterRepository,
    DeadLetterRow,
    get_dead_letter_repository,
    is_dead_letter_enabled,
)
from .work_recovery import (                                    # noqa: F401
    WorkRecovery,
    is_work_recovery_enabled,
)
from .provider_admission import (                               # noqa: F401
    AdmissionDecision,
    ProviderAwareAdmission,
    is_provider_aware_admission_enabled,
)
from .age_boost import (                                        # noqa: F401
    AgeBoost,
    compute_age_boost,
    is_age_boost_enabled,
)
from .elastic_bands import (                                    # noqa: F401
    ElasticBandPlan,
    ElasticBandRedistributor,
    is_elastic_bands_enabled,
)
from .budget_hard_cap import (                                  # noqa: F401
    BudgetHardCap,
    BudgetHardCapDecision,
    is_budget_hard_cap_enabled,
)
from .operator_controls import (                                # noqa: F401
    OperatorControls,
    is_operator_controls_enabled,
)

__all__ = [
    "CLASS_RETRY_POLICIES",
    "RetryOutcome",
    "RetryExecutor",
    "is_retry_enabled",
    "retry_policy_for_class",
    "DEAD_LETTER_COLLECTION",
    "DeadLetterRepository",
    "DeadLetterRow",
    "get_dead_letter_repository",
    "is_dead_letter_enabled",
    "WorkRecovery",
    "is_work_recovery_enabled",
    "AdmissionDecision",
    "ProviderAwareAdmission",
    "is_provider_aware_admission_enabled",
    "AgeBoost",
    "compute_age_boost",
    "is_age_boost_enabled",
    "ElasticBandPlan",
    "ElasticBandRedistributor",
    "is_elastic_bands_enabled",
    "BudgetHardCap",
    "BudgetHardCapDecision",
    "is_budget_hard_cap_enabled",
    "OperatorControls",
    "is_operator_controls_enabled",
]

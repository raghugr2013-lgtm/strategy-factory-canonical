"""Phase 2 Stage 3.β — pipeline version constants.

Two independent version streams, both carried on every pipeline
outcome record and every repository write:

- `PIPELINE_VERSION` — bumped for any implementation refactor.
  Represents "the code that produced this outcome".
- `PIPELINE_CONTRACT_VERSION` — bumped ONLY when pipeline SEMANTICS
  change (e.g. a new stage is inserted before an existing one; the
  trust-tier ladder gains a new tier; the license outcome enum
  changes). Represents "the meaning of the outcome".

Rationale (operator directive, 2026-02-19):
  Retro-processing / audit / replay must be able to decide whether a
  historical outcome is comparable to a fresh one. `pipeline_version`
  distinguishes reruns; `pipeline_contract_version` distinguishes
  semantic shifts.

Bump policy:
  * Fixing a bug in `trust_scorer.py` → bump `PIPELINE_VERSION` only.
  * Adding a new tier to the trust ladder → bump BOTH.
  * Refactoring `pipeline.py` to use a different composition helper
    → bump `PIPELINE_VERSION` only.
  * Reordering the stages so `license_gate` runs before
    `dedup_check` → bump `PIPELINE_CONTRACT_VERSION`.

Immutability:
  These are module-level constants; do not mutate at runtime.
"""
from __future__ import annotations


# Bump this for every implementation change (bug fix, refactor, code
# clean-up). Increment in the shipping commit that lands the change.
PIPELINE_VERSION: str = "0.1.0"


# Bump this ONLY when the pipeline's observable semantics change.
# Downstream consumers may key retro-processing decisions on this.
PIPELINE_CONTRACT_VERSION: str = "0.1.0"


# Storage DB name — one DB, per-domain sub-collections.
# The domain-registry is the source of truth for collection names.
KNOWLEDGE_DB_NAME: str = "strategy_knowledge_base"

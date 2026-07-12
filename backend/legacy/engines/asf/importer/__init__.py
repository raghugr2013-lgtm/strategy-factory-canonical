"""ASF importer surface (GATE 3 scope).

Modules:
    walker             — classify rows into ApplyAction list (pure)
    upserter           — apply actions to Mongo (idempotent)
    verifier           — post-commit cross-check vs. manifest
    migration_adapter  — 1-vCPU-specific in-memory adapter
"""

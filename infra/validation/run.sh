#!/usr/bin/env bash
# Strategy Factory — Production Validation launcher.
#
# Purpose: run the validation suite from the correct CWD (the repository
# root) regardless of where the operator invokes it from. This avoids the
# `ModuleNotFoundError: No module named 'infra.validation'` gotcha caused
# by running from the wrong working directory.
#
# Usage (identical to `python -m infra.validation.run_validation ...`):
#   ./infra/validation/run.sh
#   ./infra/validation/run.sh --full
#   ./infra/validation/run.sh --module health
#   ./infra/validation/run.sh --tier5 --tier5-hours 24 --tier5-interval-s 300
#
# Environment (all optional; defaults documented in README.md):
#   VALIDATION_BASE_URL, VALIDATION_ADMIN_EMAIL, VALIDATION_ADMIN_PASSWORD,
#   VALIDATION_TIMEOUT_S, VALIDATION_SLOW_MS_WARN, VALIDATION_REPORTS_DIR,
#   TIER5_DURATION_HOURS, TIER5_INTERVAL_SECONDS
set -euo pipefail

# Resolve repo root = two dirs above this file.
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$HERE/../.." && pwd)"

cd "$REPO_ROOT"
exec "${PYTHON:-python3}" -m infra.validation.run_validation "$@"

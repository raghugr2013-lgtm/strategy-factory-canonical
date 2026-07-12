#!/usr/bin/env bash
# Strategy Factory — migration wrapper.
#
# Runs infra/scripts/migrate-data.py inside a NAMED (not --rm) python:3.12-slim
# container on vqb-network. All stdout+stderr are tee'd into a persistent log
# file. On any failure the container is preserved so `docker logs` and
# `docker inspect` can be used for post-mortem, and the final report contains
# the Python traceback.
#
# Usage:
#   ./infra/scripts/migrate-data.sh                        # live LEAN (default)
#   ./infra/scripts/migrate-data.sh --dry-run              # dry-run lean
#   ./infra/scripts/migrate-data.sh --profile full         # live FULL migration
#   ./infra/scripts/migrate-data.sh --profile full --dry-run
#   ./infra/scripts/migrate-data.sh --resume               # continue an interrupted run
#   ./infra/scripts/migrate-data.sh --progress-every 5000 --resume
#
# Env vars (from .env or exported):
#   SOURCE_MONGO_URL      full URI to the source (v01) DB
#   SOURCE_MONGO_DB       source DB name (default: test_database)
#   SHARED_MONGO_URL      target URI (already used by the deployed stack)
#   FACTORY_DB_NAME       target DB name (default: strategy_factory_v1)
#   MIGRATION_REPORT_DIR  where to write logs+reports (default: /var/log/strategy-factory)
#
# On success: exit 0, report + log in $MIGRATION_REPORT_DIR.
# On failure: exit code from python migrate-data.py, log + partial report
#             preserved, container NOT removed. Recovery hints printed.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="$ROOT/.env"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

: "${SOURCE_MONGO_URL:?SOURCE_MONGO_URL required (source v01 Mongo URI)}"
: "${SHARED_MONGO_URL:?SHARED_MONGO_URL required (target v1.0 Mongo URI, from .env)}"

SRC_DB="${SOURCE_MONGO_DB:-test_database}"
TGT_DB="${FACTORY_DB_NAME:-strategy_factory_v1}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
REPORT_DIR="${MIGRATION_REPORT_DIR:-/var/log/strategy-factory}"
mkdir -p "$REPORT_DIR"
REPORT_HOST="$REPORT_DIR/migration-${STAMP}.json"
LOGFILE="$REPORT_DIR/migration-${STAMP}.log"
CONTAINER="sf-migrate-${STAMP}"

# Pass extra CLI args (--dry-run, --resume, --progress-every, --skip-unplanned) through
EXTRA_ARGS="$*"

# Header
{
  echo "──────────────────────────────────────────────────────────────"
  echo " Strategy Factory migration"
  echo " Started:   $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo " Source DB: $SRC_DB"
  echo " Target DB: $TGT_DB"
  echo " Report:    $REPORT_HOST"
  echo " Log:       $LOGFILE"
  echo " Container: $CONTAINER  (kept for post-mortem — remove manually when done)"
  echo " Extra:     $EXTRA_ARGS"
  echo "──────────────────────────────────────────────────────────────"
} | tee "$LOGFILE"

# NOTE: no --rm. Container is preserved on both success and failure so:
#   * `docker logs $CONTAINER` still works after the wrapper exits
#   * `docker inspect $CONTAINER` shows the exit code / OOM state
#   * a killed OOM container leaves inspect data behind
# On success we print the cleanup hint; on failure we print the recovery hints.

set +e
docker run \
    --name "$CONTAINER" \
    --network vqb-network \
    -v "$ROOT:/work" -w /work \
    -e SOURCE_MONGO_URL -e SHARED_MONGO_URL \
    python:3.12-slim sh -c "
      set -e
      pip install -q pymongo==4.9.2 &&
      python -u infra/scripts/migrate-data.py \
        --source '$SOURCE_MONGO_URL' --source-db '$SRC_DB' \
        --target '$SHARED_MONGO_URL' --target-db '$TGT_DB' \
        --report /work/migration-${STAMP}.json $EXTRA_ARGS
    " 2>&1 | tee -a "$LOGFILE"
PY_EXIT=${PIPESTATUS[0]}
set -e

# Move partial/final report to the log dir
if [[ -f "$ROOT/migration-${STAMP}.json" ]]; then
  mv "$ROOT/migration-${STAMP}.json" "$REPORT_HOST" 2>/dev/null || true
fi

# Grab the container's exit code as well (useful when OOM-killed etc.)
CONTAINER_EXIT="$(docker inspect --format='{{.State.ExitCode}}' "$CONTAINER" 2>/dev/null || echo unknown)"
CONTAINER_OOM="$(docker inspect --format='{{.State.OOMKilled}}' "$CONTAINER" 2>/dev/null || echo unknown)"

{
  echo "──────────────────────────────────────────────────────────────"
  echo " Finished:        $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo " Python exit:     $PY_EXIT"
  echo " Container exit:  $CONTAINER_EXIT"
  echo " OOM killed:      $CONTAINER_OOM"
  echo "──────────────────────────────────────────────────────────────"
} | tee -a "$LOGFILE"

if [[ "$PY_EXIT" -ne 0 ]]; then
  {
    echo
    echo "[migrate] FAILED with exit code $PY_EXIT"
    echo "[migrate]   log:                $LOGFILE"
    echo "[migrate]   partial report:     $REPORT_HOST"
    echo "[migrate]   container:          $CONTAINER  (kept)"
    echo
    echo "[migrate] Diagnostic commands:"
    echo "  docker logs $CONTAINER                       # full stderr including traceback"
    echo "  docker inspect $CONTAINER                    # exit code / OOM / start time"
    echo "  python -c 'import json;d=json.load(open(\"$REPORT_HOST\"));print(json.dumps(d[\"errors\"],indent=2))'"
    echo
    echo "[migrate] To resume from the point of failure (skips completed collections):"
    echo "  ./infra/scripts/migrate-data.sh --resume $EXTRA_ARGS"
    echo
    echo "[migrate] When you're done post-mortem, remove the container:"
    echo "  docker rm $CONTAINER"
  } | tee -a "$LOGFILE" >&2
  exit "$PY_EXIT"
fi

{
  echo "[migrate] SUCCESS"
  echo "[migrate]   report: $REPORT_HOST"
  echo "[migrate]   log:    $LOGFILE"
  echo "[migrate] Remove the container when finished:  docker rm $CONTAINER"
} | tee -a "$LOGFILE"

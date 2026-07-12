#!/usr/bin/env bash
# ------------------------------------------------------------
# Strategy Factory v1.1 — restore the canonical baseline dump
# ------------------------------------------------------------
# Restores backup/strategy_factory_v1.1_baseline.archive into the
# target Mongo instance. Works against both:
#   • the bundled `factory-mongo` container (docker exec)
#   • an external Mongo (uses SHARED_MONGO_URL from .env)
#
# Usage: ./scripts/restore_baseline.sh [--drop] [--target <db_name>]
# ------------------------------------------------------------
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ARCHIVE="$ROOT/backup/strategy_factory_v1.1_baseline.archive"
ENV_FILE="$ROOT/.env"

[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

TARGET_DB="${FACTORY_DB_NAME:-strategy_factory_v1}"
DROP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --drop) DROP="--drop"; shift ;;
    --target) TARGET_DB="$2"; shift 2 ;;
    *) echo "unknown arg $1" >&2; exit 2 ;;
  esac
done

[[ -f "$ARCHIVE" ]] || { echo "archive not found: $ARCHIVE" >&2; exit 1; }
echo "→ restoring $(du -h "$ARCHIVE" | cut -f1) baseline dump into '$TARGET_DB' $DROP"

# Prefer the local `factory-mongo` container if present, else use SHARED_MONGO_URL
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^factory-mongo$'; then
  echo "→ target: factory-mongo container"
  docker exec -i factory-mongo mongorestore \
    --archive --gzip $DROP \
    --nsFrom "test_database.*" --nsTo "${TARGET_DB}.*" \
    < "$ARCHIVE"
elif command -v mongorestore >/dev/null 2>&1 && [[ -n "${SHARED_MONGO_URL:-}" ]]; then
  echo "→ target: SHARED_MONGO_URL"
  mongorestore --uri "$SHARED_MONGO_URL" \
    --archive --gzip $DROP \
    --nsFrom "test_database.*" --nsTo "${TARGET_DB}.*" \
    < "$ARCHIVE"
else
  echo "error: no factory-mongo container and no local mongorestore + SHARED_MONGO_URL." >&2
  echo "       Start the compose stack first, or install mongodb-tools." >&2
  exit 1
fi

echo "✓ baseline restored into '$TARGET_DB'"

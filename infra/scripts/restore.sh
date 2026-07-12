#!/usr/bin/env bash
# Strategy Factory — restore MongoDB from a mongodump archive.
# Usage:  ./infra/scripts/restore.sh /path/to/dump.archive.gz
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="$ROOT/.env"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

ARCHIVE="${1:?path to archive required}"
[[ -f "$ARCHIVE" ]] || { echo "archive not found: $ARCHIVE" >&2; exit 1; }

DIR="$(cd "$(dirname "$ARCHIVE")" && pwd)"
NAME="$(basename "$ARCHIVE")"

echo "[restore] $ARCHIVE → ${SHARED_MONGO_URL}"
docker run --rm --network vqb-network -v "$DIR:/dump" mongo:7.0 \
  mongorestore --uri "${SHARED_MONGO_URL:?SHARED_MONGO_URL required}" \
    --archive="/dump/${NAME}" --gzip --drop

echo "[restore] done"

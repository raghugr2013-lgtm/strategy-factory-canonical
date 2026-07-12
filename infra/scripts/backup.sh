#!/usr/bin/env bash
# Strategy Factory — dump MongoDB `strategy_factory` DB via shared mongo.
# Usage:  ./infra/scripts/backup.sh [/path/to/backup-dir]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="$ROOT/.env"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

OUT="${1:-/var/backups/strategy-factory}"
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
ARCHIVE="$OUT/strategy_factory-${STAMP}.archive.gz"

echo "[backup] dumping to $ARCHIVE"
docker run --rm --network vqb-network \
  -v "$OUT:/dump" \
  mongo:7.0 \
  mongodump --uri "${SHARED_MONGO_URL:?SHARED_MONGO_URL required}" \
    --archive="/dump/$(basename "$ARCHIVE")" --gzip

echo "[backup] pruning older than 30 days"
find "$OUT" -type f -name '*.archive.gz' -mtime +30 -delete || true
echo "[backup] done"

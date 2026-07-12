#!/usr/bin/env bash
# Strategy Factory — rollback to a previous image tag.
# Usage:  FACTORY_IMAGE_TAG=<previous> ./infra/scripts/rollback.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
COMPOSE="$ROOT/infra/compose/docker-compose.prod.yml"
ENV_FILE="$ROOT/.env"

TAG="${FACTORY_IMAGE_TAG:?FACTORY_IMAGE_TAG required (e.g. 1.0.0 or a commit sha)}"
export FACTORY_IMAGE_TAG="$TAG"

echo "[rollback] switching to tag $TAG"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d --no-deps factory-backend factory-vie factory-frontend
echo "[rollback] done"

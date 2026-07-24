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

echo "[deploy] switching to tag $TAG"
# Delegate to compose.sh so the canonical --project-name=strategy-factory
# is applied (raw `docker compose` here would create orphans under the
# auto-derived project name `compose`, causing later day-2 operations
# via compose.sh to see the container-name conflict and skip recreation).
# See docs/PHASE2_ACTIVATION_MATRIX.md §"container project drift".
"$ROOT/infra/scripts/compose.sh" up -d --no-deps factory-backend factory-vie factory-frontend
echo "[rollback] done"

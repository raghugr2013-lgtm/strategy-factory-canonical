#!/usr/bin/env bash
# Strategy Factory — one-shot deploy from a clean checkout.
# Usage:  ./infra/scripts/deploy.sh          → full flow (precheck + build + up + health)
#         ./infra/scripts/deploy.sh --skip-precheck   → skip precheck (CI/rollback path)
# Requires: docker + docker compose plugin, .env at repo root.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
COMPOSE="$ROOT/infra/compose/docker-compose.prod.yml"
ENV_FILE="$ROOT/.env"
SKIP_PRECHECK="${1:-}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: .env not found at $ENV_FILE (copy from .env.example)" >&2
  exit 1
fi

if [[ "$SKIP_PRECHECK" != "--skip-precheck" ]]; then
  echo "[deploy] running precheck"
  "$HERE/precheck.sh" || { echo "[deploy] precheck failed — refusing to proceed"; exit 1; }
fi

echo "[deploy] ensuring vqb-network exists"
docker network inspect vqb-network >/dev/null 2>&1 || docker network create vqb-network

echo "[deploy] building images"
BUILD_COMMIT="$(git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo "unknown")"
BUILD_DATE="$(date -u +%FT%TZ)"
BUILD_VERSION="$(cat "$ROOT/VERSION" 2>/dev/null || echo 0.0.0)"
export BUILD_COMMIT BUILD_DATE BUILD_VERSION

docker compose --env-file "$ENV_FILE" -f "$COMPOSE" build

echo "[deploy] starting stack"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE" up -d

echo "[deploy] waiting for health"
sleep 8
"$HERE/health.sh" || {
  echo "[deploy] health check failed — see docker compose logs" >&2
  exit 1
}
echo "[deploy] done — $BUILD_VERSION @ $BUILD_COMMIT"

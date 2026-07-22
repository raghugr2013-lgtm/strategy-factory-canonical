#!/usr/bin/env bash
# Strategy Factory — one-shot deploy from a clean checkout.
# Usage:  ./infra/scripts/deploy.sh          → full flow (precheck + build + up + health)
#         ./infra/scripts/deploy.sh --skip-precheck   → skip precheck (CI/rollback path)
# Requires: docker + docker compose plugin, .env at repo root.
#
# For one-off compose commands outside this script (logs, ps, restart,
# exec, …), always use the sibling wrapper `./infra/scripts/compose.sh`
# — it enforces the same repo-root + --env-file rule regardless of the
# caller's current working directory. Do NOT `cd infra/compose &&
# docker compose -f docker-compose.prod.yml …`; the compose file's
# ${VAR:?…} interpolation guards will refuse to parse without an
# explicit env file, but the wrapper is the frictionless path. See
# docs/DEPLOYMENT.md §3 for the canonical rule.
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

# ── Belt-and-suspenders: guarantee factory-backend + factory-runner are
# on vqb-network even if a previous manual `docker compose up` (using
# the dev overlay at repo-root ./docker-compose.yml) attached them to a
# compose-local bridge. `network connect` is idempotent — if the
# container is already on the network, docker prints a harmless notice
# and returns non-zero, which we ignore.
echo "[deploy] ensuring containers are attached to vqb-network"
for c in factory-backend factory-runner; do
  if docker inspect "$c" >/dev/null 2>&1; then
    on_net=$(docker inspect "$c" -f '{{if index .NetworkSettings.Networks "vqb-network"}}yes{{end}}' 2>/dev/null || echo "")
    if [[ "$on_net" != "yes" ]]; then
      echo "[deploy]   $c missing from vqb-network — attaching"
      docker network connect vqb-network "$c" || true
    else
      echo "[deploy]   $c already on vqb-network"
    fi
  fi
done

echo "[deploy] waiting for health"
sleep 8
"$HERE/health.sh" || {
  echo "[deploy] health check failed — see docker compose logs" >&2
  exit 1
}
echo "[deploy] done — $BUILD_VERSION @ $BUILD_COMMIT"

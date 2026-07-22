#!/usr/bin/env bash
# Strategy Factory — canonical docker compose wrapper.
#
# Purpose: guarantee that every `docker compose` invocation against the
# production stack uses the correct compose file AND the correct .env
# file regardless of the caller's current working directory. Prevents
# the 2026-07-22 VPS failure mode where `cd infra/compose && docker
# compose -f docker-compose.prod.yml up -d` loaded a non-existent
# `.env` in `infra/compose/`, leaving SHARED_MONGO_URL + JWT_SECRET
# empty and preventing the backend from starting.
#
# Usage — behaves like `docker compose` on any subcommand:
#   ./infra/scripts/compose.sh build
#   ./infra/scripts/compose.sh up -d
#   ./infra/scripts/compose.sh logs -f factory-backend
#   ./infra/scripts/compose.sh ps
#   ./infra/scripts/compose.sh exec factory-backend bash
#   ./infra/scripts/compose.sh --project-name strategy-factory restart factory-backend
#
# Overrides (optional, useful for CI / rollback dry-runs):
#   COMPOSE_ENV_FILE=/path/to/other.env  ./infra/scripts/compose.sh up -d
#   COMPOSE_FILE_OVERRIDE=/path/to/other.yml ./infra/scripts/compose.sh …
#
# Rules enforced:
#   * The compose file used is ALWAYS the repo-root canonical prod
#     compose file (`infra/compose/docker-compose.prod.yml`), no matter
#     which directory the operator invoked this script from.
#   * The env file used is ALWAYS the repo-root `.env` (unless
#     $COMPOSE_ENV_FILE overrides). Empty / missing → fail fast.
#   * The project name is stable (`strategy-factory`) unless the caller
#     explicitly passes `--project-name` (or its `-p` shortcut).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

COMPOSE_FILE="${COMPOSE_FILE_OVERRIDE:-$ROOT/infra/compose/docker-compose.prod.yml}"
ENV_FILE="${COMPOSE_ENV_FILE:-$ROOT/.env}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "error: compose file not found at $COMPOSE_FILE" >&2
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: env file not found at $ENV_FILE" >&2
  echo "       copy the template with: cp .env.example .env" >&2
  echo "       or override with: COMPOSE_ENV_FILE=/path/to/other.env $0 ..." >&2
  exit 2
fi

# Preserve `--project-name`/`-p` if the caller supplied it; otherwise
# inject the canonical stable name so `docker ps` / `docker compose ps`
# output stays consistent across runs.
project_flag=(--project-name strategy-factory)
for arg in "$@"; do
  case "$arg" in
    --project-name|--project-name=*|-p) project_flag=() ; break ;;
  esac
done

exec docker compose \
  --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" \
  "${project_flag[@]}" \
  "$@"

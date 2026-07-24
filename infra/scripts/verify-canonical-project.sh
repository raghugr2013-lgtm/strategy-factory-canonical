#!/usr/bin/env bash
# Strategy Factory — project-label drift detector.
#
# Verifies that every container declared in docker-compose.prod.yml is
# labelled with the canonical Compose project name `strategy-factory`.
# A container carrying a foreign label (typically `compose`, from a
# historical `docker compose up` invocation that skipped
# `--project-name`) is treated as drift and reported loudly, because
# every future `compose.sh up -d --force-recreate` will silently skip
# such containers (see the "container name conflict" root-cause note
# in docs/PHASE2_ACTIVATION_MATRIX.md).
#
# Usage
# -----
#   ./infra/scripts/verify-canonical-project.sh
#     → exits 0 when all services carry the canonical label;
#       exits 1 when drift is found and prints the migration steps.
#
# Optional env
# ------------
#   CANONICAL_PROJECT   default: strategy-factory
#   SERVICES            default: parsed from docker-compose.prod.yml
#
# Runs read-only. Does NOT modify any container.
set -u

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'
else G=""; R=""; Y=""; C=""; B=""; N=""; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/infra/compose/docker-compose.prod.yml}"
CANONICAL_PROJECT="${CANONICAL_PROJECT:-strategy-factory}"
SERVICES_INPUT="${SERVICES:-}"

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "${R}error${N}: compose file not found: $COMPOSE_FILE" >&2
  exit 2
fi

# Discover service list — grep the compose file for `container_name:`
# entries (they are the actual docker names). Falls back to the SERVICES
# env override for setups that pin names differently.
if [[ -n "$SERVICES_INPUT" ]]; then
  # shellcheck disable=SC2206
  services=($SERVICES_INPUT)
else
  mapfile -t services < <(grep -E '^\s+container_name:' "$COMPOSE_FILE" | awk '{print $2}' | tr -d '"' | sort -u)
fi

if [[ ${#services[@]} -eq 0 ]]; then
  echo "${R}error${N}: no container_name entries found in $COMPOSE_FILE" >&2
  exit 2
fi

echo "${B}${C}── canonical-project drift check ──${N}"
echo "  canonical project = ${CANONICAL_PROJECT}"
echo "  compose file      = ${COMPOSE_FILE}"
echo "  services checked  = ${services[*]}"
echo

drift=()
missing=()
canonical=()

for svc in "${services[@]}"; do
  if ! docker inspect "$svc" >/dev/null 2>&1; then
    missing+=("$svc")
    printf "  %-24s %s\n" "$svc" "${Y}NOT RUNNING${N}"
    continue
  fi
  label=$(docker inspect "$svc" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null)
  if [[ "$label" == "$CANONICAL_PROJECT" ]]; then
    canonical+=("$svc")
    printf "  %-24s %s (project=%s)\n" "$svc" "${G}OK${N}" "$label"
  else
    drift+=("$svc:$label")
    printf "  %-24s %s (project=%s ← expected %s)\n" \
      "$svc" "${R}DRIFT${N}" "${label:-<none>}" "$CANONICAL_PROJECT"
  fi
done

echo
if [[ ${#drift[@]} -eq 0 ]]; then
  echo "${G}✓ no drift detected${N} — all running services carry project=${CANONICAL_PROJECT}"
  [[ ${#missing[@]} -gt 0 ]] && echo "  (${#missing[@]} service(s) not currently running: ${missing[*]} — informational only)"
  exit 0
fi

echo "${R}${#drift[@]} service(s) show project-label drift:${N}"
for row in "${drift[@]}"; do
  svc="${row%%:*}"
  cur="${row#*:}"
  echo "    - ${svc}   current project = '${cur:-<none>}'"
done

cat <<EOF

${B}Migration procedure (safe, one service at a time)${N}
The docker container name is a globally-unique registry — a foreign
project label means the compose wrapper cannot force-recreate the
container. Stop + remove the orphan and let compose.sh recreate it
under project=${CANONICAL_PROJECT}. Do this ONE SERVICE at a time so
the outage per service is <10 seconds and never affects the whole
stack.

For each drifted service:
  docker stop <service>
  docker rm   <service>
  ./infra/scripts/compose.sh up -d --no-deps <service>

Then re-run this script to confirm.

Notes
-----
* factory-mongo lives in a SEPARATE compose file
  (deploy-artifacts/factory-mongo/docker-compose.yml) and is not
  managed by compose.sh. It is intentionally excluded from this check.
* If you see a fresh drift after a recent deploy, the offending
  script probably invoked \`docker compose\` without
  \`--project-name ${CANONICAL_PROJECT}\`. Prefer \`compose.sh\`.
EOF

exit 1

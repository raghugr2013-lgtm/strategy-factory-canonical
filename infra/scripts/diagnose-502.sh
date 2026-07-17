#!/usr/bin/env bash
# Strategy Factory — production 502 diagnostic.
#
# Run this on the VPS (as the user that manages docker), from anywhere.
# It probes every hop between the public Traefik entrypoint and the
# factory-backend container to isolate a 502 Bad Gateway.
#
# Exits 0 if all hops succeed, 1 otherwise.
set -u

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; C=$'\e[36m'; B=$'\e[1m'; N=$'\e[0m'
else G=""; R=""; Y=""; C=""; B=""; N=""; fi

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a

DOMAIN="${FACTORY_DOMAIN:-strategy.coinnike.com}"
NET="${VQB_NETWORK:-vqb-network}"
BACKEND="${BACKEND_CONTAINER:-factory-backend}"
TRAEFIK="${TRAEFIK_CONTAINER:-}"

section(){ echo; echo "${B}${C}── $1 ──${N}"; }
ok(){    echo "${G}✓${N} $1"; }
warn(){  echo "${Y}!${N} $1"; }
bad(){   echo "${R}✗${N} $1" >&2; FAIL=$((FAIL+1)); }

FAIL=0

# ── 0. Environment sanity ─────────────────────────────────────────────
section "0. Environment"
echo "  FACTORY_DOMAIN = ${DOMAIN}"
echo "  vqb-network    = ${NET}"
echo "  backend cntr   = ${BACKEND}"

# ── 1. Public HTTPS layer (what the user sees) ────────────────────────
section "1. Public HTTPS layer"
code=$(curl -sSk -o /dev/null -w "%{http_code}" --max-time 8 "https://${DOMAIN}/api/health" || echo "000")
hdr=$(curl -sSk -I --max-time 8 "https://${DOMAIN}/api/health" 2>/dev/null | tr -d '\r' | head -20)
if [[ "$code" == "200" ]]; then ok "https://${DOMAIN}/api/health → 200 (nothing to fix)"
elif [[ "$code" == "502" ]]; then bad "https://${DOMAIN}/api/health → 502 Bad Gateway (Traefik cannot reach upstream)"
elif [[ "$code" == "000" ]]; then bad "https://${DOMAIN}/api/health → connection failed (DNS / firewall / no Traefik listener)"
else warn "https://${DOMAIN}/api/health → HTTP ${code}"; fi
echo "$hdr" | sed 's/^/    /'

# ── 2. Docker network topology ────────────────────────────────────────
section "2. Docker network — is Traefik on the same network as factory-backend?"
if ! docker network inspect "$NET" >/dev/null 2>&1; then
  bad "network '${NET}' does not exist"
  echo "    fix:  docker network create ${NET}"
else
  ok "network '${NET}' exists"
  # Every container on the network
  members=$(docker network inspect "$NET" -f '{{range $k,$v := .Containers}}{{$v.Name}} {{end}}')
  echo "    members: ${members:-<none>}"
  # Factory-backend attached?
  if echo " $members " | grep -q " $BACKEND "; then
    ok "${BACKEND} is attached to ${NET}"
  else
    bad "${BACKEND} is NOT attached to ${NET} — Traefik cannot resolve it"
    echo "    fix:  docker network connect ${NET} ${BACKEND}"
    echo "          (or rebuild:  cd $ROOT && docker compose --env-file .env \\"
    echo "                        -f infra/compose/docker-compose.prod.yml up -d factory-backend)"
  fi
  # Traefik attached?
  if [[ -z "$TRAEFIK" ]]; then
    TRAEFIK=$(echo "$members" | tr ' ' '\n' | grep -i traefik | head -1)
  fi
  if [[ -n "$TRAEFIK" ]]; then
    ok "Traefik container on ${NET}: ${TRAEFIK}"
  else
    bad "no Traefik container is attached to ${NET}"
    echo "    fix:  docker network connect ${NET} <your-traefik-container>"
    echo "    (list candidates:  docker ps --filter 'ancestor=traefik' --format '{{.Names}}')"
  fi
fi

# ── 3. Backend container health & port binding ────────────────────────
section "3. Backend container state"
if ! docker inspect "$BACKEND" >/dev/null 2>&1; then
  bad "container ${BACKEND} does not exist — nothing to route to"
else
  state=$(docker inspect -f '{{.State.Status}}' "$BACKEND")
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$BACKEND")
  restarts=$(docker inspect -f '{{.RestartCount}}' "$BACKEND")
  case "$state:$health" in
    running:healthy|running:n/a) ok "state=${state} health=${health} restarts=${restarts}" ;;
    running:starting)            warn "state=${state} health=${health} restarts=${restarts} — still initialising" ;;
    running:*)                   bad  "state=${state} health=${health} restarts=${restarts}" ;;
    *)                           bad  "state=${state} (container is NOT running)" ;;
  esac
  echo "    IPs on all networks:"
  docker inspect "$BACKEND" -f '{{range $k,$v := .NetworkSettings.Networks}}      {{$k}} → {{$v.IPAddress}}{{"\n"}}{{end}}'
  # In-container reachability
  if docker exec "$BACKEND" curl -fsS --max-time 5 http://127.0.0.1:8001/api/health >/dev/null 2>&1; then
    ok "in-container 127.0.0.1:8001/api/health → 200"
  else
    bad "in-container 127.0.0.1:8001/api/health FAILED — app is not answering"
  fi
fi

# ── 4. Traefik → backend reachability (proves the 502 hop) ────────────
section "4. Traefik → backend upstream test"
if [[ -n "${TRAEFIK:-}" ]] && docker inspect "$TRAEFIK" >/dev/null 2>&1; then
  # Get backend IP on vqb-network
  bip=$(docker inspect "$BACKEND" -f "{{with index .NetworkSettings.Networks \"${NET}\"}}{{.IPAddress}}{{end}}" 2>/dev/null)
  if [[ -z "$bip" ]]; then
    bad "no IP for ${BACKEND} on ${NET} — cannot test upstream"
  else
    if docker exec "$TRAEFIK" wget -qO- --tries=1 --timeout=5 "http://${bip}:8001/api/health" 2>/dev/null >/dev/null \
       || docker exec "$TRAEFIK" curl -fsS --max-time 5 "http://${bip}:8001/api/health" >/dev/null 2>&1; then
      ok "Traefik CAN reach ${BACKEND} at http://${bip}:8001/api/health"
      warn "Since Traefik can reach it, the 502 is a ROUTER / LABEL problem (see §5)"
    else
      bad "Traefik CANNOT reach ${BACKEND} at http://${bip}:8001/api/health"
      echo "    → the 502 is a NETWORK problem (Traefik and backend on different networks)"
    fi
    # Also try by name
    if docker exec "$TRAEFIK" getent hosts "$BACKEND" >/dev/null 2>&1 \
       || docker exec "$TRAEFIK" nslookup "$BACKEND" >/dev/null 2>&1; then
      ok "Traefik resolves DNS name '${BACKEND}' on ${NET}"
    else
      warn "Traefik cannot DNS-resolve '${BACKEND}' on ${NET}"
    fi
  fi
else
  warn "no Traefik container detected — skipping upstream test"
fi

# ── 5. Router / label registration ────────────────────────────────────
section "5. Traefik labels on ${BACKEND}"
docker inspect "$BACKEND" -f '{{range $k,$v := .Config.Labels}}{{if or (eq $k "traefik.enable") (contains $k "traefik.http.routers.factory") (contains $k "traefik.http.services.factory") (eq $k "traefik.docker.network")}}      {{$k}} = {{$v}}{{"\n"}}{{end}}{{end}}' 2>/dev/null \
  | sed 's/^      /    /'
if docker inspect "$BACKEND" -f '{{index .Config.Labels "traefik.enable"}}' 2>/dev/null | grep -qi true; then
  ok "traefik.enable=true"
else
  bad "traefik.enable is NOT set to 'true' — Traefik will ignore this container"
fi
declared_net=$(docker inspect "$BACKEND" -f '{{index .Config.Labels "traefik.docker.network"}}' 2>/dev/null)
if [[ "$declared_net" == "$NET" ]]; then
  ok "traefik.docker.network=${NET} matches"
else
  bad "traefik.docker.network='${declared_net}' does not match actual network '${NET}'"
fi

# ── 6. Duplicates / stale containers ──────────────────────────────────
section "6. Duplicate / stale factory-backend containers"
dupes=$(docker ps -a --filter "name=factory-backend" --format '{{.Names}} {{.Status}}' | wc -l)
if [[ "$dupes" -le 1 ]]; then
  ok "exactly one ${BACKEND} container (no stale duplicates)"
else
  warn "found ${dupes} factory-backend* containers — stale ones can confuse Traefik:"
  docker ps -a --filter "name=factory-backend" --format '    {{.Names}}  {{.Status}}  ({{.RunningFor}})'
  echo "    fix:  docker rm -f <stale-name>"
fi

# ── 7. Traefik-side view (routers/services registered) ────────────────
section "7. Traefik registered routers/services (best-effort)"
if [[ -n "${TRAEFIK:-}" ]]; then
  # Try the Traefik dashboard API from inside the Traefik container.
  # Port defaults: 8080 (internal API). Non-fatal if disabled.
  for port in 8080 9000 8081; do
    if docker exec "$TRAEFIK" wget -qO- --tries=1 --timeout=3 "http://127.0.0.1:${port}/api/http/routers" 2>/dev/null | grep -q factory-api; then
      ok "Traefik has router 'factory-api' registered (api port ${port})"
      break
    fi
  done
  # Check recent Traefik logs for the domain
  echo "    Recent Traefik log lines mentioning ${DOMAIN}:"
  docker logs --since 5m "$TRAEFIK" 2>&1 | grep -iE "${DOMAIN}|factory-|502" | tail -10 | sed 's/^/      /'
fi

# ── 8. Recent backend log lines ───────────────────────────────────────
section "8. Recent ${BACKEND} log tail (last 20 lines)"
docker logs --tail 20 "$BACKEND" 2>&1 | sed 's/^/    /'

echo
if [[ $FAIL -eq 0 ]]; then
  echo "${G}All diagnostics passed${N}"
  exit 0
else
  echo "${R}${FAIL} problem(s) detected${N} — apply the printed fixes and re-run this script"
  exit 1
fi

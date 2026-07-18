# Strategy Factory — Production Deployment Runbook
### Target: `https://strategy.coinnike.com` (VPS 144.91.78.175)

All commands are run **on the VPS as root** (or via `sudo -i`). The
canonical repository is assumed to be checked out at
`/opt/strategy-factory` (adjust the path in step 3 if yours differs).

Order matters — Mongo must exist **before** the factory stack starts,
and Caddy must exist **before** you try to hit the public HTTPS URL.

---

## 0. One-time host prep (skip if already done)

```bash
# Confirm the shared docker network exists — every layer joins it.
docker network inspect vqb-network >/dev/null 2>&1 || docker network create vqb-network

# Open the firewall for HTTP/HTTPS (Caddy needs :80 to solve HTTP-01
# ACME challenges, and :443 for real traffic + HTTP/3).
ufw allow 80/tcp   || true
ufw allow 443/tcp  || true
ufw allow 443/udp  || true
```

---

## 1. Stand up the self-hosted production MongoDB

```bash
mkdir -p /opt/factory-mongo
# Copy these two artifacts from the deploy bundle:
#   /opt/factory-mongo/docker-compose.yml
#   /opt/factory-mongo/.env
chmod 600 /opt/factory-mongo/.env

cd /opt/factory-mongo
docker compose --env-file /opt/factory-mongo/.env up -d

# Verify — must print `1`.
docker exec factory-mongo mongosh \
  -u root -p "$(grep MONGO_ROOT_PASSWORD .env | cut -d= -f2)" \
  --authenticationDatabase admin \
  --quiet --eval "db.adminCommand({ping:1}).ok"
# → 1

# Confirm the DNS alias resolves on vqb-network from another container.
docker run --rm --network vqb-network alpine \
  sh -c 'getent hosts factory-mongo'
# → 172.x.x.x  factory-mongo
```

If the ping returns `1`, MongoDB production is up.

---

## 2. Stand up Caddy (auto-HTTPS reverse proxy)

```bash
mkdir -p /opt/caddy
# Copy these two artifacts from the deploy bundle:
#   /opt/caddy/docker-compose.yml
#   /opt/caddy/Caddyfile

# IMPORTANT: edit the ACME email in the Caddyfile before starting.
sed -i 's|REPLACE_WITH_LETSENCRYPT_EMAIL@example.com|YOUR_REAL_EMAIL@example.com|' \
  /opt/caddy/Caddyfile

cd /opt/caddy
docker compose up -d

# First cert issuance can take 10-30 seconds — tail Caddy's log to
# watch Let's Encrypt HTTP-01 succeed.
docker logs -f caddy 2>&1 | grep -E 'certificate|obtained|error' | head -20
# You want to see: "certificate obtained successfully" for strategy.coinnike.com
```

At this point `https://strategy.coinnike.com` will already respond,
but with a **502 Bad Gateway** because the factory backend/frontend
haven't started yet. That is expected — proceed to step 3.

---

## 3. Deploy the factory stack from the canonical repo

Repository:
`https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git` (branch `main`)

```bash
# If you already have the repo cloned, skip the clone and just make
# sure it's on the canonical main.
cd /opt
[[ -d strategy-factory ]] || git clone \
  https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git \
  strategy-factory
cd /opt/strategy-factory
git fetch origin
git checkout main
git reset --hard origin/main

# Copy the production .env from the deploy bundle:
#   /opt/strategy-factory/.env
chmod 600 /opt/strategy-factory/.env

# Sanity-check env values you might want to rotate:
#   ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET (already fresh 64-char hex)

# Run the built-in precheck. This validates .env, that Docker + the
# vqb-network + DNS + reverse-proxy container + Mongo are all in
# order BEFORE any container is (re)built.
./infra/scripts/precheck.sh
# Expected: "precheck OK" (warnings for SHARED_REDIS_URL are fine).

# One-shot deploy (build + up + health).
./infra/scripts/deploy.sh
```

`deploy.sh` will:
1. Build backend / frontend / VIE / runner images.
2. `docker compose ... up -d` the production compose file.
3. Ensure factory-backend + factory-runner are attached to `vqb-network`.
4. Run `./infra/scripts/health.sh` which is the same probe the
   acceptance suite uses.

---

## 4. Verify — all four gates must be green

```bash
# 4.1  Container states + readiness (in-cluster).
/opt/strategy-factory/infra/scripts/health.sh

# 4.2  Public HTTPS API.
curl -fsS https://strategy.coinnike.com/api/health
# → {"status":"ok", ...}    HTTP 200

# 4.3  Public HTTPS frontend.
curl -fsS -o /dev/null -w '%{http_code}\n' https://strategy.coinnike.com/
# → 200

# 4.4  Readiness — mongo, vie must be "green", redis "skipped" is OK.
docker exec factory-backend curl -fsS http://127.0.0.1:8001/api/readiness \
  | python3 -m json.tool
```

Expected `health.sh` output tail:
```
✓ container factory-backend  → running (health=healthy)
✓ container factory-vie      → running (health=healthy)
✓ container factory-frontend → running (health=healthy)
✓ in-cluster /api/health → 200
✓ backend → VIE reachable
✓ frontend /healthz → 200
✓ readiness → mongo=green
✓ readiness → vie=green
✓ readiness → redis=skipped (SHARED_REDIS_URL not configured)
✓ public https://strategy.coinnike.com/api/health → 200
✓ public https://strategy.coinnike.com/ → 200
All checks passed
```

---

## 5. First-login sanity check

Browse to `https://strategy.coinnike.com` and log in with:

- Email:    `admin@coinnike.com`  (whatever `ADMIN_EMAIL` you set)
- Password: `Tmn0SECEyDxV1KqfbHMw` (whatever `ADMIN_PASSWORD` you set)

Rotate `ADMIN_PASSWORD` in the UI, then update `/opt/strategy-factory/.env`
and re-run `./infra/scripts/deploy.sh --skip-precheck` so the new value
is baked into the container env.

---

## Troubleshooting

| Symptom | First look |
|---|---|
| `https://.../api/health` → 502 | `docker logs caddy \| tail -50` — likely Caddy can't resolve `factory-backend` because a container isn't on `vqb-network`. |
| Backend never becomes healthy | `docker logs factory-backend \| tail -100` — usually a Mongo auth failure (wrong SHARED_MONGO_URL creds). |
| `readiness → mongo=red` | `docker exec factory-backend python -c "import os; from pymongo import MongoClient; MongoClient(os.environ['MONGO_URL']).admin.command('ping')"` |
| Cert stays self-signed | Ensure the DNS A record for `strategy.coinnike.com` still points to this VPS's public IP; Caddy re-tries every ~2 minutes. |
| Full-hop diagnostic | `/opt/strategy-factory/infra/scripts/diagnose-502.sh` |

---

## Rollback

The repo ships a rollback script:

```bash
cd /opt/strategy-factory
./infra/scripts/rollback.sh   # reverts the compose stack to the
                              # previous known-good image tags.
```

MongoDB data is on the `factory_mongo_data` volume and survives all
stack rebuilds — rollback does not touch it.

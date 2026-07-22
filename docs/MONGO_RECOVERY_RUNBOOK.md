# MongoDB Recovery Runbook — v1.2.0-alpha2-feature-freeze RC1

**Situation (2026-02-17):**
* Current deployment uses Docker volume `strategy-factory_factory_mongo_data` (created 2026-07-15).
* Current MongoDB shows only `admin`, `config`, `local`, and a `READ_ME_TO_RECOVER_YOUR_DATA` collection — **this is a ransomware/scanner marker**, not benign.
* Older volume `strategy-factory-v110-56545c65e6f3_factory_mongo_data` (2026-07-12) exists but is not attached.
* Backend login returns HTTP 500 → `AuthenticationFailed (code 18)` because no users are provisioned in the current volume.
* Backend routing fix (100→101 routers, Phase-1 canonical `/api/strategies*` vs legacy `/api/legacy/strategies*`) is deployed and verified.

**Goal:** determine whether the older volume holds recoverable Strategy Factory data. If yes, migrate it in cleanly. If no, initialise a fresh, **hardened** deployment. Never destroy the current volume during triage — it may itself contain forensic evidence about the attacker.

---

## Phase 0 — Freeze and preserve (do this FIRST, ~5 min)

Attacker may return. Preserve every artefact before you touch anything.

```bash
# Set on the VPS host
export STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/backups/factory_recovery_$STAMP

# 1. Snapshot both Docker volumes to tarballs (both must be preserved).
docker run --rm \
  -v strategy-factory_factory_mongo_data:/data:ro \
  -v /var/backups/factory_recovery_$STAMP:/backup \
  alpine tar czf /backup/CURRENT_volume_$STAMP.tar.gz -C /data .

docker run --rm \
  -v strategy-factory-v110-56545c65e6f3_factory_mongo_data:/data:ro \
  -v /var/backups/factory_recovery_$STAMP:/backup \
  alpine tar czf /backup/OLDER_volume_$STAMP.tar.gz -C /data .

# 2. Take a live mongodump of the current DB (captures the ransom collection too).
docker exec factory-mongo mongodump \
  --uri="mongodb://localhost:27017" \
  --out=/tmp/mongodump_current_$STAMP
docker cp factory-mongo:/tmp/mongodump_current_$STAMP \
  /var/backups/factory_recovery_$STAMP/

# 3. Compute + record integrity hashes so you can detect any future tampering.
cd /var/backups/factory_recovery_$STAMP && sha256sum * > SHA256SUMS.txt

# 4. Optional but recommended: chattr +i to lock the recovery dir.
chattr -R +i /var/backups/factory_recovery_$STAMP  # requires ext4/xfs
```

Also copy every backend log covering the last ≥7 days off the box:

```bash
tar czf /var/backups/factory_recovery_$STAMP/backend_logs.tar.gz \
  /var/log/supervisor/backend.*.log
```

---

## Phase 1 — Read-only inspection of the older volume (do NOT unmount the current one)

Spin up an isolated inspection Mongo on a **non-standard port**, bound to `127.0.0.1` only, reading the older volume **read-only**. This gives you a Mongo shell against the historical data without disturbing the running deployment or exposing another Mongo to the network.

```bash
# 1. Start an isolated inspection container.
docker run -d --rm \
  --name factory-mongo-inspect \
  --network none \
  -v strategy-factory-v110-56545c65e6f3_factory_mongo_data:/data/db:ro \
  -v /tmp/inspect_out:/inspect \
  --entrypoint mongod \
  mongo:6.0 \
    --dbpath /data/db \
    --bind_ip 127.0.0.1 \
    --port 27099 \
    --noauth

# 2. Wait for it, then exec a shell inside the same container.
sleep 3
docker exec -it factory-mongo-inspect mongosh --port 27099 --quiet <<'JS'
// A. What databases exist?
print("=== databases ===");
db.adminCommand({listDatabases: 1}).databases.forEach(d => print(d.name, d.sizeOnDisk));

// B. Does strategy_factory_v1 exist?
const target = "strategy_factory_v1";
const dbs = db.adminCommand({listDatabases:1}).databases.map(d => d.name);
if (!dbs.includes(target)) {
  print("!! " + target + " NOT FOUND in this volume.");
  quit(0);
}

// C. Enumerate collections and row counts.
print("=== " + target + " collections ===");
const target_db = db.getSiblingDB(target);
target_db.getCollectionNames().sort().forEach(c => {
  const n = target_db.getCollection(c).countDocuments({});
  print(c, "→", n, "rows");
});

// D. Verify Strategy Factory canonical collections are present.
const canonical = [
  "users", "strategies", "master_bots",
  "outcome_events", "execution_journal",
  "meta_learning_recommendations", "factory_eval_reports",
];
print("=== canonical collections present? ===");
canonical.forEach(c => {
  const has = target_db.getCollectionNames().includes(c);
  const n = has ? target_db.getCollection(c).countDocuments({}) : 0;
  print((has ? "✓" : "✗"), c, has ? "(" + n + " rows)" : "");
});

// E. Check for the ransom marker.
if (target_db.getCollectionNames().some(c => c.toLowerCase().includes("read_me"))) {
  print("!! Ransom marker present in older volume too — it is also compromised.");
} else {
  print("== No ransom marker in older volume ==");
}

// F. Latest audit trail — is this actually recent?
if (target_db.getCollectionNames().includes("outcome_events")) {
  const last = target_db.outcome_events.find({}).sort({ts:-1}).limit(1).toArray();
  if (last.length) print("Newest outcome_event ts:", last[0].ts);
}
JS

# 3. Also mongodump the older volume to a tarball for portable inspection.
docker exec factory-mongo-inspect mongodump \
  --uri="mongodb://localhost:27099" \
  --out=/inspect/older_dump
tar czf /var/backups/factory_recovery_$STAMP/older_volume_mongodump.tar.gz \
  -C /tmp/inspect_out older_dump

# 4. Tear down inspection container.
docker stop factory-mongo-inspect
```

Record the output verbatim in a text file inside `/var/backups/factory_recovery_$STAMP/inspection_report.txt`.

---

## Phase 2 — Decision tree based on inspection output

### Case A — Older volume has `strategy_factory_v1` with expected canonical collections AND no ransom marker

**Meaning:** you have a golden pre-attack snapshot. Attacker got in AFTER 2026-07-12 and hit the volume created 2026-07-15.

**Recovery path:**
1. Stop the current backend service on the VPS. Run every `docker compose` command from the repository root with `--env-file .env`, or use the `infra/scripts/compose.sh` wrapper (see `docs/DEPLOYMENT.md` §3):
   ```bash
   cd /home/raghu/projects/strategy-factory-canonical
   ./infra/scripts/compose.sh stop factory-backend
   ```
2. Stop the current MongoDB and **do not delete** its volume — you already snapshotted it in Phase 0.
   ```bash
   ./infra/scripts/compose.sh stop mongo
   ```
3. Edit the compose file so `mongo.volumes` binds to the older volume:
   ```yaml
   services:
     mongo:
       volumes:
         - strategy-factory-v110-56545c65e6f3_factory_mongo_data:/data/db
   volumes:
     strategy-factory-v110-56545c65e6f3_factory_mongo_data:
       external: true
   ```
4. Bring Mongo up **on the internal Docker network only** (never on `0.0.0.0`):
   ```bash
   ./infra/scripts/compose.sh up -d mongo
   ```
5. Enable auth (see Phase 4 — mandatory before backend restart).
6. Bring the backend up. Verify:
   * Login → 200 with valid JWT.
   * `GET /api/strategies` → Phase-1 canonical shape (bare list, `strategy_id`).
   * `GET /api/legacy/strategies` → `{strategies:[...]}` with historical data.
   * Boot log: `legacy full-recovery mount: 101 routers/attachers online`.

### Case B — Older volume has `strategy_factory_v1` but also has ransom marker OR is short of canonical collections

**Meaning:** both volumes were hit; older is a partial pre-attack state.

**Recovery path:**
1. Do NOT attach the older volume as primary. Keep it archived.
2. Provision a fresh volume for a clean deployment (Phase 3 below).
3. Manually restore any recoverable collections by using `mongorestore` from the older-volume dump, but **only** the collections you know are intact.
   ```bash
   docker exec -i factory-mongo mongorestore \
     --uri="mongodb://admin:$MONGO_ADMIN_PW@localhost:27017/?authSource=admin" \
     --db=strategy_factory_v1 \
     --nsInclude="strategy_factory_v1.strategies" \
     --nsInclude="strategy_factory_v1.master_bots" \
     --nsInclude="strategy_factory_v1.outcome_events" \
     /path/to/older_dump/strategy_factory_v1
   ```
4. Users collection MUST NOT be restored — attacker may have altered credentials. Re-seed admin via the backend seeding flow.

### Case C — Older volume has NO `strategy_factory_v1` database

**Meaning:** the older volume was already empty when it was retired; the current volume was where data lived and it is now destroyed.

**Recovery path:**
1. Search for other backups: cloud snapshots (DigitalOcean/Hetzner/AWS EBS), off-box mongodumps, previous CI artefacts.
2. If truly none exist, the data is unrecoverable. Proceed to Phase 3 with a fresh initialisation. This is a business event — record it in the incident log with timestamp, evidence collected, and any operator/regulatory reporting obligations.

---

## Phase 3 — Fresh initialisation (only if Case B or C)

Provision a new named volume so archived volumes remain untouched and clearly labelled by date:

```bash
docker volume create factory_mongo_$(date +%Y%m%d)
```

Update `docker-compose.prod.yml` to reference the new volume as `external: true`. Bring Mongo up. Then run the backend's admin-seeding flow (idempotent — safe to re-run):

```bash
# The backend seeds ADMIN_EMAIL / ADMIN_PASSWORD on lifespan startup.
# Just start it and verify the boot log.
docker compose up -d backend
docker logs --tail=200 backend | grep -E "seed|admin|Application startup complete"
```

---

## Phase 4 — Mandatory hardening BEFORE restart (Cases A, B, and C all require this)

The reason you were hit is that `factory-mongo` accepted an unauthenticated connection from the internet. Do not restart until every item is done.

### 4.1 Enable MongoDB authentication

```bash
# 1. Add these env vars to the mongo service in docker-compose.prod.yml
services:
  mongo:
    image: mongo:6.0
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ADMIN_USER}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ADMIN_PW}
    command: ["mongod", "--auth", "--bind_ip_all"]

# 2. Update .env.prod
MONGO_ADMIN_USER=factory_admin
MONGO_ADMIN_PW=<32+ char random>  # openssl rand -base64 32
MONGO_URL=mongodb://factory_admin:<same>@factory-mongo:27017/strategy_factory_v1?authSource=admin
DB_NAME=strategy_factory_v1
```

**Also rotate JWT_SECRET, ADMIN_PASSWORD, and any provider API keys**. Assume every credential from before the attack is compromised.

### 4.2 Verify Mongo port is NOT exposed publicly

```bash
# On the VPS
ss -tlnp | grep 27017
# EXPECTED: nothing bound to 0.0.0.0 or the public IP.
#           Only container-internal :27017 is acceptable.

# Also check the compose file:
grep -A2 "ports:" docker-compose.prod.yml | grep 27017
# EXPECTED: no line here at all. Never publish 27017.
```

If `27017` was in the `ports:` block, remove it. Backend reaches Mongo through the Docker bridge network by hostname `factory-mongo`.

### 4.3 UFW / firewall audit

```bash
sudo ufw status verbose
# Only 22 (or your SSH port) + 443 should be reachable.
# 27017 must never appear as ALLOW.
```

### 4.4 Emergent-managed Google Auth (optional, longer-term)

Since your admin credential seed is fragile, consider migrating auth to Emergent-managed Google OAuth after this incident settles. Ask me to wire it in when you're ready — it's a supported integration in this codebase.

### 4.5 Volume housekeeping (only after successful recovery + 24h paper validation)

Once Phase 5 validation passes:
```bash
# Rename retained volumes so they're clearly forensic:
docker volume create factory_mongo_archive_ATTACK_$STAMP
docker run --rm \
  -v strategy-factory_factory_mongo_data:/from:ro \
  -v factory_mongo_archive_ATTACK_$STAMP:/to \
  alpine sh -c "cp -a /from/. /to/"
# Do NOT delete the originals until you have three independent copies.
```

---

## Phase 5 — Post-restore verification

Run the boot invariants + Phase-1/legacy smoke you already know:

```bash
# 1. Boot invariants
docker logs backend --tail=200 | grep -E "full-recovery mount|meta_learning engine ready|factory_eval engine ready|Application startup complete"
# EXPECTED:
#   legacy full-recovery mount: 101 routers/attachers online
#   meta_learning engine ready (mode=observe, cadence=900s)
#   factory_eval engine ready (mode=observe, cadence=3600s)
#   Application startup complete.

# 2. Auth + canonical routing
TOK=$(curl -sf -X POST https://<host>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<admin>","password":"<new_pw>"}' | jq -r .access_token)

curl -sf -H "Authorization: Bearer $TOK" https://<host>/api/strategies | jq 'type'
# EXPECTED: "array"  (Phase-1 canonical shape)

curl -sf -H "Authorization: Bearer $TOK" https://<host>/api/legacy/strategies | jq 'has("strategies")'
# EXPECTED: true      (legacy wrapper)

curl -sf -H "Authorization: Bearer $TOK" https://<host>/api/orchestrator/tasks | jq '.count'
# EXPECTED: 17

curl -sf -H "Authorization: Bearer $TOK" https://<host>/api/meta-learning/config \
  | jq '.config.META_LEARNING_MODE'
# EXPECTED: "observe"

curl -sf -H "Authorization: Bearer $TOK" https://<host>/api/factory-eval/config \
  | jq '.config.FACTORY_EVAL_MODE'
# EXPECTED: "observe"
```

Only after ALL of those pass do you resume the planned 24h + 72h Tier 5 validation.

---

## Phase 6 — Incident record

Append to `/app/docs/PRODUCTION_SIGN_OFF.md` (or a separate `INCIDENT_2026-02-17.md`):

* Volumes preserved and their SHA256 sums.
* Which case (A/B/C) applied.
* Which collections were restored, from which volume.
* Every credential rotated.
* Hardening steps completed.
* Time-to-recover from first symptom to green Phase 5 verification.

Sign the incident record before proceeding to Tier 5 validation.

---

## What NOT to do

* Do NOT pay a ransom demand. The `READ_ME_TO_RECOVER_YOUR_DATA` family typically **does not actually hold the data hostage** — they extort based on the fear of exfiltration. Even if they did, paying does not guarantee recovery and identifies you as a soft target for the next campaign.
* Do NOT bind MongoDB to `0.0.0.0` or publish port 27017 through Docker. Ever. That single misconfiguration is the root cause.
* Do NOT delete either volume until Phase 5 verification passes AND at least 24 hours have elapsed.
* Do NOT restore the `users` collection from the older volume — password hashes may have been rewritten by the attacker. Always re-seed admin.
* Do NOT restart the current stack until Phase 4 hardening is complete.

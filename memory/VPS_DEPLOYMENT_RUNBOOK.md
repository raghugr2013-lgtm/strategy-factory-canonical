# VPS Deployment Runbook — Commit 5937100 (frozen backend + P0 fixes)

> **Status:** Operator playbook. No code changes.
> **Target:** VPS `144.91.78.175` (Ubuntu 24.04), `https://strategy.coinnike.com`.
> **Compose project:** `strategy-factory` at `/home/raghu/projects/strategy-factory-canonical`.
> **Backend Feature Freeze:** IN EFFECT. Do NOT enable any Stage-3 or Stage-4 flag during this deployment.
> **Expected wall-clock:** 15–25 minutes end-to-end assuming no rebuild-time issues.

---

## 0. What this deployment does

Deploys commit `5937100` (or later HEAD on `main`) to the VPS. This
commit includes:

- **Batch 1** — Activation Plan v2 documentation
- **Batch 2** — Freeze-permitted operational wiring:
  - W1: TTL specs for 5 Stage-4 audit collections in
    `engines/db_indexes.py`
  - W2: Aggregator wiring (retrofit providers auto-register; UKIE
    async block in `/api/health/system`)
- **Batch 3(a)** — Phase E rewritten around native Alertmanager silences
- **P0-F1** — Stage-4 UKIE health endpoint renamed
  `/api/knowledge/health` → `/api/knowledge/ukie/health` (Phase-1
  endpoint at `/api/knowledge/health` unaffected)
- **P0-F2** — `engines.db_indexes.ensure_indexes()` wired into
  application startup (~54 indexes now created at boot)

**Runtime behaviour change on VPS after deploy:**
- 54 Mongo indexes will be applied at first boot post-deploy.
- Stage-4 endpoint at `/api/knowledge/ukie/health` becomes the
  Stage-4 UKIE health surface (still 503 because
  `UKIE_HEALTH_PROVIDER_ENABLED` remains OFF — no activation change).
- **NO** feature flags are being flipped. Post-deploy dormancy
  posture is identical to pre-deploy for all Stage-4 subsystems.

---

## 1. Pre-deployment checklist (5 min)

Run these BEFORE touching the VPS:

- [ ] Confirm you have SSH access: `ssh raghu@144.91.78.175`
- [ ] Confirm `strategy.coinnike.com` currently returns 200 for
      `/api/health` and the site is up (baseline "before" evidence)
- [ ] Confirm the GitHub repo contains commit `5937100` (or later HEAD)
      with the files listed in §7.1 of `PHASE_0_BASELINE_REPORT_V2.md`
- [ ] Announce the deployment window in your ops channel (10 min
      expected read-only impact during rebuild)
- [ ] No active operator work touching the DB
      (`workload_dead_letter`, `strategy_knowledge_base` collections
      will be indexed idempotently on first boot; safe but a busy
      write pattern could slow index build)

Optional (nice to have):
- [ ] A second terminal open to `tail -f` the backend logs during boot
- [ ] The Phase 0 report v2 open in a browser tab for cross-reference

---

## 2. Backup verification (2 min)

Before pulling new code, capture a rollback snapshot.

**Mongo dump (both DBs):**
```bash
ssh raghu@144.91.78.175
cd /home/raghu/projects/strategy-factory-canonical

# Capture a timestamped dump. Retain at least the most recent 5.
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /home/raghu/backups/pre-deploy-${TS}
docker exec factory-mongo mongodump \
  --archive=/tmp/pre_deploy_${TS}.archive --gzip
docker cp factory-mongo:/tmp/pre_deploy_${TS}.archive \
  /home/raghu/backups/pre-deploy-${TS}/
docker exec factory-mongo rm /tmp/pre_deploy_${TS}.archive
ls -lh /home/raghu/backups/pre-deploy-${TS}/
echo "PRE_DEPLOY_BACKUP=${TS}"    # RECORD THIS VALUE
```

**Git tag current HEAD (rollback anchor):**
```bash
git fetch origin
CURRENT_HEAD=$(git rev-parse HEAD)
git tag "pre-deploy-${TS}" ${CURRENT_HEAD} || true
echo "CURRENT_HEAD_BEFORE_DEPLOY=${CURRENT_HEAD}"    # RECORD THIS
```

**Env snapshot (whichever `.env` your compose project uses):**
```bash
cp /home/raghu/projects/.../env \
   /home/raghu/backups/pre-deploy-${TS}/env.snapshot 2>/dev/null || \
   echo "note: adjust env path per your production install"
```

**Verification:**
- [ ] Mongo dump file is non-empty (`ls -lh` shows > 1 KB)
- [ ] `pre-deploy-${TS}` git tag exists locally
      (`git tag | grep pre-deploy-`)
- [ ] `.env.snapshot` is preserved

**If any of the above fails: STOP. Do NOT continue until backup is confirmed.**

---

## 3. Git update commands (2 min)

```bash
cd /home/raghu/projects/strategy-factory-canonical
git fetch origin main
git log --oneline HEAD..origin/main | head -20     # preview what will land
git reset --hard origin/main                        # or `git pull --ff-only`
NEW_HEAD=$(git rev-parse HEAD)
echo "NEW_HEAD_AFTER_PULL=${NEW_HEAD}"              # RECORD THIS
```

Verification:
- [ ] `${NEW_HEAD}` is `5937100` OR a later commit whose message references Phase 0 fixes / activation plan
- [ ] `backend/legacy/engines/db_indexes.py` contains `KB_TTL_SPECS`:
```bash
grep -c "KB_TTL_SPECS" backend/legacy/engines/db_indexes.py    # expect 1+
grep -c "workload_dead_letter" backend/legacy/engines/db_indexes.py   # expect ≥ 2
```
- [ ] `backend/app/main.py` contains the P0-F2 wiring:
```bash
grep -c "_engines_ensure_indexes" backend/app/main.py    # expect 2 (import alias + call)
```
- [ ] `backend/legacy/engines/knowledge/observability_router.py` contains new path:
```bash
grep -c '"/ukie/health"' backend/legacy/engines/knowledge/observability_router.py    # expect 1
grep '@router.get("/health")' backend/legacy/engines/knowledge/observability_router.py    # expect NO output
```

---

## 4. Docker rebuild + restart (5–15 min)

> **Invocation rule (added after the 2026-07-22 incident).** Run every
> `docker compose` command **from the repository root** with an
> explicit `--env-file .env`, or use the `infra/scripts/compose.sh`
> wrapper. Do NOT `cd infra/compose` first — compose then loads
> `<cwd>/.env` (which does not exist there) and every `${VAR}`
> interpolation resolves to empty; the compose file now guards
> `SHARED_MONGO_URL` and `JWT_SECRET` with `${VAR:?…}` so the wrong
> variant fails at YAML parse time with a clear error. Reference:
> `docs/DEPLOYMENT.md` §3.

```bash
cd /home/raghu/projects/strategy-factory-canonical

# Rebuild only the backend + factory-runner images (both depend on
# the same backend Dockerfile). Frontend + VIE untouched.
./infra/scripts/compose.sh build factory-backend factory-runner

# Stop + start with the new image. Keeps mongo + caddy + frontend up.
./infra/scripts/compose.sh up -d --no-deps factory-backend factory-runner

# Wait for the container to settle
sleep 8

# Verify the backend container is Up (healthy)
docker ps --filter name=factory-backend --format '{{.Names}}: {{.Status}}'
```

Verification (must ALL be true before continuing):
- [ ] `docker ps` shows `factory-backend` as `Up X seconds`
- [ ] `docker ps` shows `factory-runner` as `Up X seconds`
- [ ] `docker ps` shows `factory-mongo`, `factory-frontend`, and the
      Caddy container as `Up` (unchanged, not restarted)

Boot log verification (CRITICAL — evidence of P0-F2 fix):
```bash
docker logs factory-backend --tail 200 | grep -E "db_indexes|ensure_indexes|Application startup"
```

Expected output (both lines present):
```
strategy_factory: engines.db_indexes.ensure_indexes: created=<N> existed=<M> errors=0
INFO:     Application startup complete.
```

- [ ] The `created=N existed=M errors=0` line appears (N+M ≈ 54)
- [ ] `errors=0` — CRITICAL. If errors > 0, capture the exception log and STOP.
- [ ] `Application startup complete.` appears immediately after
- [ ] No `CRITICAL` or `ERROR` level lines in the last 200 log entries

---

## 5. Health verification (3 min)

Run these against the public URL. All must return 200.

```bash
BASE=https://strategy.coinnike.com

# ── Phase-1 health ──
for ep in health health/config version; do
  printf "%-30s %s\n" "/api/$ep" "$(curl -sS -o /dev/null -w '%{http_code}' $BASE/api/$ep)"
done

# ── Full health payloads ──
curl -sS $BASE/api/health         | jq -c
curl -sS $BASE/api/version        | jq -c
curl -sS $BASE/api/health/config  | jq -c
```

Expected:
- [ ] `/api/health` → **200**, JSON has `"status":"ok"`
- [ ] `/api/version` → **200**, `"version"` matches expected image tag
      (e.g., `1.1.0-stage4` or the tag you built), `"commit"` matches
      `${NEW_HEAD}` from §3
- [ ] `/api/health/config` → **200**, `"required":{"MONGO_URL":true,"DB_NAME":true,"JWT_SECRET":true}`
      all true; `"flags":{"enable_legacy_routers":true,...}` matches
      your production config
- [ ] `/api/health/config.flags.enable_legacy_routers` = **true**
      (production has legacy routers on per PRD.md session 1-2)
- [ ] `/api/version.build_date` is a real ISO date (not `unknown`)

If any of these fail, **STOP and rollback** (§8). Do not proceed to
Phase 0 verification.

---

## 6. VPS Phase 0 verification (7 min)

This is the production Phase 0 baseline capture. It replaces the
preview rehearsal capture and is the artifact that gates Phase A.

### 6.1 Preconditions to verify

```bash
BASE=https://strategy.coinnike.com

# COE_HEALTH_CONTRACT_ENABLED is a Stage-1 flag; production has it on.
# When on, /api/health/system returns 200 (not 503).
curl -sS -o /dev/null -w 'health/system: %{http_code}\n' $BASE/api/health/system
```

- [ ] `/api/health/system` → **200** (Plan v2 §3 precondition #3)

If this returns 503, the flag is off on the VPS. Not a blocker for
deployment success, but Phase A cannot begin until the flag is on.
Set `COE_HEALTH_CONTRACT_ENABLED=true` in the production `.env`,
restart backend, and re-verify.

### 6.2 20-endpoint dormancy matrix (must ALL be 503 for Stage-4)

```bash
BASE=https://strategy.coinnike.com
OUT=/home/raghu/vps_phase0_$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p $OUT

for ep in knowledge/ukie/health knowledge/metrics \
          knowledge/promote-events knowledge/retro-score-runs \
          knowledge/connector-events \
          meta-learning/health mi/health execution/health \
          portfolio/health factory-eval/health \
          coe/dead-letter coe/dead-letter/depth; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" $BASE/api/$ep)
    printf "%-38s %s\n" "$ep" "$code" | tee -a $OUT/stage4_dormancy.txt
done
# POST for query
code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
       -H "Content-Type: application/json" -d '{}' \
       $BASE/api/knowledge/query)
printf "%-38s %s (POST)\n" "knowledge/query" "$code" | tee -a $OUT/stage4_dormancy.txt

# Phase-1 knowledge endpoint MUST still be 200
code=$(curl -sS -o /dev/null -w "%{http_code}" $BASE/api/knowledge/health)
printf "%-38s %s   (Phase-1, expected 200)\n" "knowledge/health" "$code" | tee -a $OUT/stage4_dormancy.txt
```

Verification:
- [ ] **All 12 Stage-4 endpoints return 503**
- [ ] `knowledge/ukie/health` → **503** (P0-F1 fix landed)
- [ ] `knowledge/health` → **200** (Phase-1 unaffected)

### 6.3 P0-F2 index verification (Mongo, TTL indexes must be live)

```bash
# Enter the mongo container. Adjust to your production DB name.
docker exec -it factory-mongo mongosh --quiet <<'EOF'
const PROD_DB = "strategy_factory_v1";                        // adjust if different
const KB_DB   = "strategy_knowledge_base";

print("=== main DB: workload_dead_letter TTL ===");
printjson(db.getSiblingDB(PROD_DB).workload_dead_letter.getIndexes()
  .filter(i => i.name === "ttl_workload_dead_letter"));

print("=== KB DB: 4 audit collection TTLs ===");
for (const c of ["lifecycle_events","knowledge_endorsement_events",
                 "knowledge_contradiction_events","connector_events"]) {
  print("--> " + c);
  printjson(db.getSiblingDB(KB_DB)[c].getIndexes()
    .filter(i => i.name && i.name.startsWith("ttl_")));
}

print("=== Sample pre-existing INDEX_SPEC (audit_log) ===");
printjson(db.getSiblingDB(PROD_DB).audit_log.getIndexes()
  .map(i => i.name));
EOF
```

Expected TTL values (in seconds):
| Collection | Expected `expireAfterSeconds` | Days |
|---|---|---|
| `workload_dead_letter.ttl_workload_dead_letter` | 7,776,000 | 90 |
| `lifecycle_events.ttl_lifecycle_events` | 15,552,000 | 180 |
| `knowledge_endorsement_events.ttl_knowledge_endorsement_events` | 7,776,000 | 90 |
| `knowledge_contradiction_events.ttl_knowledge_contradiction_events` | 31,536,000 | 365 |
| `connector_events.ttl_connector_events` | 15,552,000 | 180 |

- [ ] All 5 TTL indexes visible with correct `expireAfterSeconds`
- [ ] `audit_log` shows at least `ttl_audit_log` and `ix_audit_ts` (side benefit of P0-F2)

### 6.4 Data-invariant check (mandatory)

```bash
docker exec factory-mongo mongosh --quiet --eval '
const PROD_DB = "strategy_factory_v1";
const KB_DB   = "strategy_knowledge_base";
print("strategies: " + db.getSiblingDB(PROD_DB).strategies.countDocuments({}));
print("ingested_strategies: " + db.getSiblingDB(PROD_DB).ingested_strategies.countDocuments({}));
print("KB strategies: " + db.getSiblingDB(KB_DB).strategies.countDocuments({}));
print("KB research: "   + db.getSiblingDB(KB_DB).research.countDocuments({}));
print("promote_events: " + db.getSiblingDB(KB_DB).promote_events.countDocuments({}));
'
```

Record these counts as the Phase-0 baseline for post-Phase-A regression.

- [ ] Legacy `ingested_strategies` count RECORDED (baseline — must not
      grow during activation; growth = invariant break)
- [ ] Production `strategies` count RECORDED
- [ ] KB collection counts RECORDED

### 6.5 Save the Phase 0 evidence bundle

```bash
# Copy artifacts off the VPS for the report record
cp $OUT/stage4_dormancy.txt ~/vps_phase0_evidence/
curl -sS $BASE/api/health         > ~/vps_phase0_evidence/01_health.json
curl -sS $BASE/api/health/config  > ~/vps_phase0_evidence/03a_health_config.json
curl -sS $BASE/api/version        > ~/vps_phase0_evidence/06_version.json
curl -sS $BASE/api/health/system  > ~/vps_phase0_evidence/02_health_system.json
docker logs factory-backend --tail 200 > ~/vps_phase0_evidence/backend_boot.log
```

Paste these back to the main agent for the VPS Phase 0 report.

---

## 7. Rollback procedure

Choose the smallest rollback that resolves the issue.

### 7.1 Configuration rollback (fastest — no rebuild)

If the deploy broke because of `.env` drift only:
```bash
cd /home/raghu/projects/strategy-factory-canonical
cp /home/raghu/backups/pre-deploy-${TS}/env.snapshot ./.env
./infra/scripts/compose.sh restart factory-backend factory-runner
```
Recovery SLA: ≤ 30 s.

### 7.2 Code rollback (git + rebuild)

```bash
cd /home/raghu/projects/strategy-factory-canonical
git reset --hard "pre-deploy-${TS}"      # tag from §2
./infra/scripts/compose.sh build factory-backend factory-runner
./infra/scripts/compose.sh up -d --no-deps factory-backend factory-runner
```
Recovery SLA: 5–10 min (rebuild time dominates).

### 7.3 Data rollback (only if Mongo corruption suspected)

```bash
docker cp /home/raghu/backups/pre-deploy-${TS}/pre_deploy_${TS}.archive \
  factory-mongo:/tmp/
docker exec factory-mongo mongorestore \
  --archive=/tmp/pre_deploy_${TS}.archive --gzip --drop
```
Recovery SLA: 5–15 min (dump size dependent).

**Note on new indexes and rollback**: the 54 indexes added by P0-F2
are idempotent. Rolling back the code does NOT drop them. If you
truly want to remove them:
```bash
docker exec factory-mongo mongosh --eval '
for (const dbName of ["strategy_factory_v1","strategy_knowledge_base"]) {
  const d = db.getSiblingDB(dbName);
  for (const coll of d.getCollectionNames()) {
    for (const idx of d[coll].getIndexes()) {
      if (idx.name.startsWith("ttl_") || idx.name.startsWith("ix_")) {
        try { d[coll].dropIndex(idx.name); print("dropped " + dbName + "." + coll + "." + idx.name); } catch(e){}
      }
    }
  }
}
'
```
**Not recommended** — the indexes are pre-existing spec + freeze-permitted W1 additions; removing them regresses query performance.

### 7.4 When to invoke rollback

| Symptom | Rollback |
|---|---|
| Backend fails to start (`docker ps` shows Restarting) | 7.2 |
| Boot log shows `errors=N` where N > 0 in db_indexes summary | 7.2 (investigate first — errors is best-effort so app may still be up) |
| `/api/health` returns 5xx | 7.2 |
| Stage-4 endpoint returns 200 when it should be 503 | Investigation first — likely a fix regression, not a rollback trigger |
| Production `strategies` gains rows without `origin="ukie_promote"` | 7.3 (data integrity) |
| Env drift only | 7.1 |

---

## 8. Final PASS / FAIL checklist

Copy this to the ops channel with each box explicitly checked.

### Pre-deploy
- [ ] Backup captured: `${TS}` = ______________
- [ ] Pre-deploy git HEAD: ______________
- [ ] `.env.snapshot` saved

### Deploy
- [ ] New HEAD: ______________ (matches expected `5937100` or later)
- [ ] File check: `KB_TTL_SPECS` present in db_indexes.py
- [ ] File check: `_engines_ensure_indexes` present in app/main.py
- [ ] File check: `/ukie/health` present in observability_router.py; old `/health` route removed
- [ ] `docker compose build` completed with no errors
- [ ] `docker ps` shows `factory-backend` Up and `factory-runner` Up
- [ ] Boot log shows `ensure_indexes: created=N existed=M errors=0`

### Health
- [ ] `/api/health` → 200 with `status:"ok"`
- [ ] `/api/health/config.required.MONGO_URL/DB_NAME/JWT_SECRET` all true
- [ ] `/api/version` returns real commit + build date

### VPS Phase 0
- [ ] `COE_HEALTH_CONTRACT_ENABLED=true` verified on VPS (aggregator returns 200)
- [ ] All 12 Stage-4 endpoints return **503**
- [ ] `/api/knowledge/ukie/health` → 503 (P0-F1)
- [ ] `/api/knowledge/health` → 200 (Phase-1 unaffected)
- [ ] 5 W1 TTL indexes present with correct `expireAfterSeconds`
- [ ] Legacy `ingested_strategies` count recorded: ______________
- [ ] Production `strategies` count recorded: ______________
- [ ] Evidence bundle saved at `~/vps_phase0_evidence/`

### Freeze compliance
- [ ] No Stage-3 flag flipped
- [ ] No Stage-4 flag flipped
- [ ] No production `strategies` writes observed during deploy
- [ ] No legacy `ingested_strategies` writes observed during deploy

**Overall verdict:**
- [ ] ✅ **DEPLOY PASSED — VPS Phase 0 ready for review**
- [ ] ⚠ **DEPLOY PASSED WITH DEVIATIONS** (list below)
- [ ] ❌ **DEPLOY FAILED — rolled back at step ____ per §7**

### Deviations / notes
```
(fill in)
```

---

## 9. Next step

Paste the evidence bundle back to the main agent for the **VPS Phase 0 report** compilation. Recommended pasting order:

1. The completed §8 checklist (with counts filled in)
2. Contents of `~/vps_phase0_evidence/stage4_dormancy.txt`
3. `~/vps_phase0_evidence/03a_health_config.json`
4. `~/vps_phase0_evidence/06_version.json`
5. `~/vps_phase0_evidence/02_health_system.json`
6. Last 200 lines of `backend_boot.log` (or at least the `db_indexes` +
   `Application startup` grep output)
7. Mongo TTL verification (§6.3 output block)
8. Data-invariant counts (§6.4)

The main agent will then compile a `VPS_PHASE_0_REPORT.md` mirroring
the structure of `PHASE_0_BASELINE_REPORT_V2.md`, verifying every
check, and emit the final PROCEED / DO-NOT-PROCEED verdict for
Phase A start.

---

*End of runbook.*

# Strategy Factory — Deployment Architecture Review

**Scope:** Canonical continuation. Repo state at HEAD `24bc6fa`
(`deploy(compose): canonical .env loading + wrapper script`).
**Objective:** Document the existing deployment, name a single canonical
production Compose workflow, and enumerate every deployment
inconsistency that must be corrected before feature development
resumes.

> This review is **read-only + non-destructive**. It renames nothing,
> deletes nothing, and does not touch application logic, API surfaces,
> DB schemas, engine code, or OBSERVE-mode gates.

---

## 1 · Current deployment topology (as-is)

### 1.1 · Physical layout on the VPS

```
/opt/strategy-factory   → /home/raghu/projects/strategy-factory-canonical   (symlink)
                          canonical git checkout · GitHub origin/main
/opt/factory-mongo/     → self-hosted MongoDB compose project             (out-of-repo)
/opt/caddy/             → Caddy reverse proxy compose project             (out-of-repo)
```

### 1.2 · Docker Compose projects on the VPS

| Compose project      | Compose file                                                   | Purpose                                              | Managed from |
|----------------------|----------------------------------------------------------------|------------------------------------------------------|--------------|
| `strategy-factory`   | `/opt/strategy-factory/infra/compose/docker-compose.prod.yml`  | factory-backend · factory-vie · factory-frontend · factory-runner | Canonical repo |
| `factory-mongo`      | `/opt/factory-mongo/docker-compose.yml`                        | factory-mongo (self-hosted Mongo 7, `--auth`)         | Out-of-repo (reference copy in `deploy-artifacts/factory-mongo/`) |
| `caddy`              | `/opt/caddy/docker-compose.yml`                                | caddy (auto-HTTPS reverse proxy)                     | Out-of-repo (reference copy in `deploy-artifacts/caddy/`) |

All six containers (`factory-backend`, `factory-frontend`, `factory-vie`,
`factory-runner`, `factory-mongo`, `caddy`) share the external
Docker network **`vqb-network`**, which is the DNS domain each
container uses to reach its peers by name.

### 1.3 · Repository-level Compose files

The canonical repo ships **two** Compose files with clearly different
purposes:

| File                                              | Purpose | Runs Mongo? | Reverse proxy | Ports on host |
|---------------------------------------------------|---------|-------------|---------------|---------------|
| `docker-compose.yml`                              | **DEV / LOCAL overlay** — `docker compose up -d` on a laptop | Yes (`factory-mongo` bundled) | None (frontend on `:3000`, backend on `:8001`) | 3000, 8001, 27017 |
| `infra/compose/docker-compose.prod.yml`           | **PRODUCTION**                                             | No (uses external `SHARED_MONGO_URL`) | External Caddy on `vqb-network` (TLS on `:443`) | None (only `expose:`) |

The dev overlay is header-commented as such (lines 1–11 of the file);
the prod file carries an aggressive `${VAR:?...}` interpolation guard
that fails at YAML-parse time if `.env` was not loaded correctly.
**Neither file is redundant.** They target two different environments
and share no state.

### 1.4 · Runtime lifecycle (production)

```
                        ┌───────────────────────────────┐
                        │  Caddy (80/443, HTTP/3 :443)  │
                        │  /api/*  → factory-backend    │
                        │  /*      → factory-frontend   │
                        └────┬──────────────────┬───────┘
                             │   vqb-network    │
              ┌──────────────┴──────┐    ┌──────┴────────────┐
              ▼                     ▼    ▼                   ▼
    ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
    │ factory-frontend │   │ factory-backend  │   │ factory-vie      │
    │ nginx :80        │◄──┤ FastAPI :8001    │◄──┤ FastAPI :8100    │
    │ SPA static bundle│   │ /api/health ✓    │   │ /health ✓        │
    └──────────────────┘   └────┬─────┬───────┘   └──────────────────┘
                                │     │
                                │     ▼
                                │  ┌──────────────────┐
                                │  │ factory-runner   │
                                │  │ APScheduler      │
                                │  │ hb → /tmp/*.hb   │
                                │  └────┬─────────────┘
                                │       │
                                ▼       ▼
                            ┌──────────────────┐
                            │ factory-mongo    │
                            │ :27017 (internal)│
                            │ --auth · vol      │
                            └──────────────────┘
```

- **factory-mongo** stores every persistent record: users, strategies,
  timeline events, dataset metadata, validation ledger. Backed by the
  Docker volume `factory_mongo_data` and a backup volume
  `factory_mongo_backup` (see §5 of `DEPLOYMENT_OPERATIONS.md`).
- **factory-runner** owns APScheduler-driven jobs (auto scheduler,
  mutation runner, BI5 cert sweep, orchestrator). Under freeze it is
  a heartbeat-only stub.
- **factory-vie** is the Vendor-Independent Engine — a stateless LLM
  gateway (six providers). It has no persistent storage.
- **Caddy** is externally managed and owns the TLS lifecycle
  (Let's Encrypt HTTP-01 renewal). See `infra/caddy/README.md`.

---

## 2 · Why two Compose files exist

The header of `/app/docker-compose.yml` explicitly names its purpose
(lines 1–11):

> Strategy Factory — LOCAL / DEV overlay compose
> Purpose: `docker compose up -d` on a developer laptop or lightweight box.

Differences from prod:
1. Includes a **bundled MongoDB** (prod uses `SHARED_MONGO_URL` against
   the self-hosted Mongo at `/opt/factory-mongo/`).
2. **No Traefik / Prometheus / Loki labels** (prod carries them for
   monitoring integration + a possible future migration).
3. **No `vqb-network` join** (uses a compose-local bridge).
4. **Publishes 3000 / 8001** to the host (prod publishes nothing to the
   host — traffic arrives through Caddy).
5. Runs `factory-runner` by default (parity with production).

This is a deliberate split. `docker-compose.yml` is NOT a substitute
for the prod compose file; it is a self-contained developer overlay.

---

## 3 · Recommendation — canonical production workflow

### 3.1 · Canonical compose file
**`infra/compose/docker-compose.prod.yml`** is the single canonical
production entry point. Reasons:

- It is the file that is currently managing every running production
  container.
- It joins the shared `vqb-network` and integrates with the external
  Caddy + Mongo compose projects.
- It carries the `${VAR:?…}` interpolation guards that make the
  historical 2026-07-22 "empty MONGO_URL" failure mode impossible.
- It emits the Prometheus / Loki labels that the external monitoring
  stack expects.
- It has an established idempotent CI-friendly wrapper
  (`infra/scripts/compose.sh`) that guarantees the compose file + env
  file combination regardless of caller CWD.

### 3.2 · Canonical invocation

All operators (humans and CI) MUST use ONE of these three forms and
NO other:

1. **`./infra/scripts/deploy.sh`** — full deploy from a clean checkout
   (precheck → network → build → up → health).
2. **`./infra/scripts/compose.sh <subcommand>`** — wrapper for one-off
   compose commands (`logs`, `ps`, `restart`, `exec`, …). Works from
   any working directory. Enforces the correct compose file, `.env`
   file, and stable `--project-name strategy-factory`.
3. **Explicit form from repo root** *(fallback for scripts that
   cannot depend on the wrapper)*:
   `docker compose --env-file .env -f infra/compose/docker-compose.prod.yml <subcommand>`

**Forbidden:** `cd infra/compose && docker compose -f docker-compose.prod.yml …`
The compose file guards this at parse time (`${VAR:?…}`), but the
wrapper is the frictionless path.

### 3.3 · Canonical env file
- Repo root: **`/opt/strategy-factory/.env`** (chmod 600) — the single
  source of truth for application secrets (JWT, admin credentials,
  `SHARED_MONGO_URL`, provider keys, `FACTORY_DOMAIN`, `CORS_ORIGINS`,
  feature flags).
- Out-of-repo Mongo: **`/opt/factory-mongo/.env`** (chmod 600) —
  `MONGO_ROOT_USERNAME` / `MONGO_ROOT_PASSWORD` only.
- Caddy: no env — configuration lives in `/opt/caddy/Caddyfile`.

### 3.4 · Migration required?
**No structural migration is required.** The canonical stack is already
under `strategy-factory` compose project management on the VPS. The
scope of change is limited to:

1. Restore the accidentally-deleted `.env.example` (see §4.1).
2. Publish `docs/DEPLOYMENT_OPERATIONS.md` as the single operational
   entry point (this task).
3. Enumerate + track the documentation-drift items in §4.

`docs/DEPLOYMENT_MIGRATION_PLAN.md` documents the (short) sequence of
non-destructive actions and the (empty) list of destructive actions
required.

---

## 4 · Deployment inconsistencies (must be tracked)

Ordered by risk — HIGH first.

### 4.1 · [HIGH] `.env.example` is missing from the tracked repo
- **Symptom:** Every deploy script (`one_click_deploy.sh`,
  `factory-bootstrap.sh`, `docs/DEPLOYMENT.md`) references
  `cp .env.example .env`, but `.env.example` was deleted by an
  automated commit (`f676526`, 2026-07-20).
- **Impact:** A fresh clone on a new VPS cannot bootstrap without
  looking at a foreign copy of the file.
- **Fix (applied by this review):** Restored a canonical
  `.env.example` at the repo root. The restore is byte-compatible
  with the tracked content immediately prior to the accidental
  deletion, plus a pointer to `DEPLOYMENT_OPERATIONS.md`.

### 4.2 · [MEDIUM] `docs/DEPLOYMENT.md` §10 is stale
- Lines 195–202 state "No Mongo container" and "No factory-runner
  sibling scheduler in Phase 1".
- **Reality:** production runs both — Mongo as a separate
  out-of-repo container on `vqb-network`, and factory-runner as an
  in-repo container in the `strategy-factory` compose project.
- **Fix:** Superseded by `DEPLOYMENT_OPERATIONS.md`. `DEPLOYMENT.md`
  remains as legacy reference; its stale claims are annotated in the
  new document rather than edited in place to preserve historical
  context.

### 4.3 · [MEDIUM] `scripts/one_click_deploy.sh` uses the DEV overlay
- Line 28: `docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" up -d --build`.
- **Impact:** If an operator confuses this with a production deploy
  path they will spin up a *second, parallel* stack that also runs
  its own `factory-mongo` (bundled) on port 27017 — which then
  clashes with the production `factory-mongo` on the same host if
  present.
- **Fix:** This is the acceptance-verifier flow for a local box; the
  scripts and README already treat it as local-only. The mitigation
  in this review is to make the intent explicit in
  `DEPLOYMENT_OPERATIONS.md` (§2.4) — the file explicitly warns
  operators never to invoke `scripts/one_click_deploy.sh` on the
  production VPS.

### 4.4 · [LOW] `traefik.*` labels on production services are inert
- `infra/compose/docker-compose.prod.yml` still emits `traefik.*`
  routing labels for every service. Caddy — the actual production
  reverse proxy — ignores them.
- **Impact:** None runtime-wise (labels are ignored). Cognitive
  overhead only.
- **Fix:** Left in place per `infra/traefik/README.md` — a future
  Traefik migration remains a one-container swap. Documented in
  `DEPLOYMENT_OPERATIONS.md` §4.2 so a new operator does not chase
  a false lead.

### 4.5 · [LOW] Reference bundle in `deploy-artifacts/` includes a
`.env.example` for the out-of-repo compose projects that never got
committed
- `deploy-artifacts/factory-mongo/` and `deploy-artifacts/caddy/` ship
  their `docker-compose.yml` (and Caddyfile) but do not ship an
  `.env.example` template for the Mongo root credentials.
- **Impact:** A new operator building the bundle from scratch has no
  template for `/opt/factory-mongo/.env`.
- **Fix (deferred, non-blocking):** Documented in
  `DEPLOYMENT_MIGRATION_PLAN.md` §4 as an optional follow-up.

### 4.6 · [LOW] Documentation duplication
- `docs/DEPLOYMENT.md`, `docs/DEPLOYMENT_ASSUMPTIONS.md`,
  `docs/POST_FREEZE_DEPLOYMENT_CHECKLIST.md`,
  `docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md`,
  `deploy-artifacts/DEPLOY_RUNBOOK.md`, and
  `memory/VPS_DEPLOYMENT_RUNBOOK.md` all cover overlapping ground.
- **Impact:** Ops truth is currently spread across six files.
- **Fix:** `DEPLOYMENT_OPERATIONS.md` is the new single source of
  truth. Old files remain as historical / narrower artifacts; the
  new file names them and states which section supersedes which.

---

## 5 · Deliverables produced by this review

1. **This review** — `docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md`.
2. **Operations manual** — `docs/DEPLOYMENT_OPERATIONS.md` (per the
   §5 outline the user supplied).
3. **Migration plan** — `docs/DEPLOYMENT_MIGRATION_PLAN.md`.
4. **Restored** `.env.example` at repo root (non-destructive fix for
   §4.1).

No application code was modified. No Compose file was renamed. No
container was created, moved, or deleted. All MongoDB data is
preserved.

# Strategy Factory · v1.1

**Canonical release · Feb 15 2026 · frozen candidate**

Self-hosted AI Strategy Engineering Platform. Recovery + modernization of the
v0.1 factory into a single, reproducible, production-ready repository. This
is the **canonical foundation** on which ArbiCore X, GemHunter, and future
intelligence modules will be integrated as separate plug-in modules — the
core is frozen from v1.1 onward.

- **Frontend** — React 19 + v01 Command OS (CommandShell, TopTabBar, LifecycleRail, StatusRail, AuthGate). 202/215 files byte-identical to v01.
- **Backend** — FastAPI 0.116 + MongoDB 6. Phase-1 core (auth + admin) + 83 legacy v01 routers, **497 API endpoints, 169 engines**.
- **VIE (Vendor Independent Engine)** — standalone provider-agnostic gateway. 6 providers: OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi. **Zero `EMERGENT_LLM_KEY` references.**
- **Auth** — JWT + refresh-token rotation + 5-role RBAC + admin-approve signup. Login endpoint emits both Phase-1 flat (`access_token`) and v01 nested (`token`, `user`) shapes for backward compat.
- **Deploy** — Docker Compose (local + VPS overlay). `ENABLE_LEGACY_ROUTERS=true` by default.

---

## 30-second bring-up

```bash
git clone <repo> strategy-factory && cd strategy-factory
cp .env.example .env
$EDITOR .env                          # ADMIN_PASSWORD, JWT_SECRET, optional VIE keys

./scripts/one_click_deploy.sh         # builds → up → restores baseline dump → runs 31-step verifier
```

Open http://localhost:3000, sign in with the admin credentials from `.env`.

For a production VPS with an existing Traefik + Mongo stack:

```bash
docker compose --env-file .env -f infra/compose/docker-compose.prod.yml up -d --build
./infra/scripts/health.sh
```

---

## Repository layout at a glance

```
/app
├── backend/           Core Strategy Factory (Phase-1 core + legacy 83 routers + 169 engines)
├── frontend/          Core Strategy Factory UI (v01 Command OS + 66 operator components)
├── vie/               Vendor Independent Engine (LLM provider gateway)
├── infra/             Infrastructure (Docker, Compose, ops scripts, Traefik, monitoring)
├── modules/           Future modules mount point (ArbiCore X, GemHunter, Research Intel)
├── backup/            v1.1 canonical MongoDB dump + manifest
├── scripts/           Repo-root helpers: one-click deploy, acceptance verifier, bundle builder
├── docs/              Documentation
│   └── acceptance_v1_1/   Release acceptance pack (10 reports + screenshot bundle)
└── memory/            PRD.md + test_credentials.md
```

Full layout: [`docs/acceptance_v1_1/FILESYSTEM_LAYOUT.md`](docs/acceptance_v1_1/FILESYSTEM_LAYOUT.md)

---

## Release acceptance pack (v1.1)

Every deliverable is under `docs/acceptance_v1_1/`:

| Document | What it proves |
|---|---|
| [`RELEASE_PACKAGE.md`](docs/acceptance_v1_1/RELEASE_PACKAGE.md) | Full manifest + sign-off block + freeze policy |
| [`RELEASE_NOTES_v1.1.md`](docs/acceptance_v1_1/RELEASE_NOTES_v1.1.md) | Highlights + statistics + limitations |
| [`BACKEND_ACCEPTANCE_REPORT.md`](docs/acceptance_v1_1/BACKEND_ACCEPTANCE_REPORT.md) | 21 modules × Engine · API · UI · DB · Scheduler · Auth · VIE · Status |
| [`API_INVENTORY.md`](docs/acceptance_v1_1/API_INVENTORY.md) | Every one of the 497 endpoints × Method · Auth · Status · Tested |
| [`ENGINE_INVENTORY.md`](docs/acceptance_v1_1/ENGINE_INVENTORY.md) | All 169 engines × Source · Deps · API · UI · Status |
| [`FRONTEND_RESTORATION_REPORT.md`](docs/acceptance_v1_1/FRONTEND_RESTORATION_REPORT.md) | Per-file classification (Unchanged / Compat fix / Replaced) |
| [`E2E_WORKFLOW_LOG.md`](docs/acceptance_v1_1/E2E_WORKFLOW_LOG.md) | 31-step workflow — 31/31 PASS |
| [`DEPLOY_VERIFY_RUN.log`](docs/acceptance_v1_1/DEPLOY_VERIFY_RUN.log) | Live output of `scripts/deploy_verify.sh` |
| [`DEPLOYMENT_GUIDE.md`](docs/acceptance_v1_1/DEPLOYMENT_GUIDE.md) | Local + VPS deploy walkthrough |
| [`ARCHITECTURE_DIAGRAM.md`](docs/acceptance_v1_1/ARCHITECTURE_DIAGRAM.md) | Topology + request lifecycle |
| [`FILESYSTEM_LAYOUT.md`](docs/acceptance_v1_1/FILESYSTEM_LAYOUT.md) | Directory tree + separation rules |
| `screenshots_original/` (12) + `screenshots_recovered/` (10) | Side-by-side visual parity |

---

## Adding a future module

`ArbiCore X`, `GemHunter`, `research_intel`, and any subsequent intelligence
module MUST be integrated as a plug-in under `/app/modules/<slug>/`.

Read the contract: [`docs/modules/ADDING_A_MODULE.md`](docs/modules/ADDING_A_MODULE.md)

The frozen core (`backend/legacy/`, `backend/app/`, `frontend/src/` except
`src/modules/`) must not be modified. Any change that requires touching the
frozen core needs its own v2.x release train.

---

## Utility scripts

| Command | Purpose |
|---|---|
| `./scripts/one_click_deploy.sh` | Zero-touch cold-start (build → up → restore → verify) |
| `./scripts/deploy_verify.sh` | Runs the 31-step E2E acceptance workflow (exit 0 on green) |
| `./scripts/restore_baseline.sh` | Restore `backup/strategy_factory_v1.1_baseline.archive` |
| `./scripts/build_release_bundle.sh` | Package the repo as `dist/strategy-factory-v1.1.0-*.tar.gz` |
| `./infra/scripts/deploy.sh` | Production deploy behind the shared Caddy reverse proxy on `vqb-network` |
| `./infra/scripts/compose.sh <subcommand>` | Canonical `docker compose` wrapper (always uses repo `.env` + prod compose file) |
| `./infra/scripts/backup.sh` | Nightly mongodump |
| `./infra/scripts/restore.sh <archive>` | Restore a mongodump archive |
| `./infra/scripts/health.sh` | Multi-service health probes |
| `./infra/scripts/rollback.sh` | Roll back to the previous release |

**Deployment truth:** `docs/DEPLOYMENT_OPERATIONS.md` is the single
operational source of truth for the production VPS
(`/opt/strategy-factory` → `strategy.coinnike.com`). See also
`docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md` and
`docs/DEPLOYMENT_MIGRATION_PLAN.md`.

**Architectural blueprint (2026-07-23):** capability inventory,
gap analysis, dependency map, autonomous factory readiness, and the
prioritised implementation roadmap live at
`docs/CAPABILITY_INVENTORY.md`, `docs/GAP_ANALYSIS.md`,
`docs/DEPENDENCY_MAP.md`, `docs/AUTONOMOUS_FACTORY_READINESS.md`, and
`docs/IMPLEMENTATION_ROADMAP.md`. These five documents guide all
remaining implementation work.

**Phase 1 activation (2026-07-23):** the sibling factory-runner
dispatcher + orchestrator activation surface is now landed
backward-compatibly. Operator work + observability contract are in
`docs/PHASE_1_ACTIVATION_PLAN.md` and
`docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md`.

**Operational validation harness (2026-07-23):**
`infra/scripts/phase1_validate.sh` — one-shot read-only VPS probe
that gathers every sign-off signal. Reports:
`docs/PHASE_1_FACTORY_VALIDATION_REPORT.md` (operational + restart
recovery) · `docs/PHASE_1_FACTORY_KPI_REPORT.md` (24 h cycle
throughput + failure/skip decomposition + budget + provider
health).

---

## Freeze policy

Once the reviewer signs the block in `docs/acceptance_v1_1/RELEASE_PACKAGE.md`:

1. Tag: `git tag strategy-factory@1.1.0 && git push --tags`
2. `main @ tag` becomes the canonical Strategy Factory v1.1.
3. ArbiCore X begins as a **separate module** under `/app/modules/arbicorex/`.
4. Any non-backward-compatible change to the frozen core cuts a new v2.x release.

---

## Test credentials

Admin bootstrap credentials, storage keys, and refresh-token semantics live
in [`memory/test_credentials.md`](memory/test_credentials.md).

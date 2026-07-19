# Strategy Factory — Deployment + Phase-1 Certification PRD

## Original problem statement (session 1)

Complete the production deployment ONLY of the canonical repository
`raghugr2013-lgtm/strategy-factory-canonical` (branch `main`) to
`https://strategy.coinnike.com` on VPS `144.91.78.175`
(Ubuntu 24.04, Docker installed, images built, DNS live).

Blockers on entry: prod MongoDB, Caddy reverse proxy, prod `.env`.

## What is running in production today

- Application at `https://strategy.coinnike.com`
- Backend commit ≥ `546d0a9` + `e873af3` (ENABLE_* flags in factory-backend env block)
- Legacy full-recovery mount: **101 routers online**
- OpenAPI paths: **616**
- Reverse proxy: Caddy 2 auto-HTTPS on `vqb-network`
- MongoDB: self-hosted `factory-mongo` container on `vqb-network`, port not published to host
- All four factory-* containers on a single unified compose project `strategy-factory` from
  `/home/raghu/projects/strategy-factory-canonical`
- Meta-Learning default mode: **OBSERVE** (structurally cannot mutate)

## Sessions summary

### Session 1 — Production infra (COMPLETE)
- External Mongo (`/opt/factory-mongo/`)
- External Caddy (`/opt/caddy/`)
- Prod `.env` (`/home/raghu/projects/.../env`)
- Bootstrap script + safety features (snapshot, no-reset)

### Session 2 — Config-drift fix (COMPLETE)
- Root cause: `factory-backend.environment:` block was missing the three
  `ENABLE_*` flags → `_bool_env(default=False)` disabled all legacy routers
- Fix: 12-line patch to `infra/compose/docker-compose.prod.yml` (commit landed
  via Emergent auto-commit)

### Session 3 — Deployment unification (COMPLETE)
- Root cause: two `docker compose` projects merged under default name `compose`
  because both invocation `cwd`s ended in `infra/compose/`
- Fix: `COMPOSE_PROJECT_NAME=strategy-factory` pinned; stale `/opt/strategy-factory`
  factory-* containers removed by name; all four services recreated from
  `/home/raghu/projects/...canonical` under a single project.
  Result: legacy full-recovery mount = 101 routers, OpenAPI = 616 paths.

### Session 4 — Phase-1 autonomous validation (COMPLETE)
- 24/24 modules PASS
- 1 real defect found + fixed: `bi5_maturity` placeholder body (2-line body added)
- 0 broken frontend↔backend wires (89 unique frontend calls, 89 registered backend routes)
- 32 MongoDB collections auto-initialised
- Meta-Learning confirmed OBSERVE
- **GREEN SIGNAL — cleared for AI provider integration**
- Full report: `/app/memory/PHASE_1_CERTIFICATION.md`

## What's ready for Phase 2

- Controlled UI migration from the newer-UI repo (per session-1 deferred item).
- AI provider integration (Claude Anthropic recommended as first provider).
- ENABLE_FACTORY_RUNNER can be flipped to `true` in prod (compose already
  supports it under both services).

## Architecture Review Phase (Session 5 — COMPLETE)

**All four Phase-2 architecture reviews delivered, plus consolidated cross-review:**

- `PHASE_2A_AI_ARCHITECTURE_REVIEW.md` — Vendor-Independent Intelligence Engine (VIE). 634 lines. **Approved.**
- `PHASE_2B_MARKET_DATA_REVIEW.md` — BI5 canonical-M1 read-side + coverage reports. 525 lines. **Approved.**
- `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md` — Universal Knowledge Ingestion Engine (UKIE), **now organised around six Knowledge Domains** (`strategy`, `research`, `indicator`, `market`, `execution`, `internal_history`) with connectors as interchangeable implementations beneath them. 582 lines. **Approved with domain-first framing (updated 2026-02-19).**
- `PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md` — Compute Orchestration Engine (COE): extended 10-class taxonomy, priority lanes (P0/P1/P2), reservations, `WorkloadRequest` envelope, retry + dead-letter, provider-aware admission. 780 lines. **New (2026-02-19).**
- `PHASE_2_CONSOLIDATED_REVIEW.md` — cross-phase implementation sequence, parallelisation opportunities, integration hot-spots, cross-cutting invariants. 377 lines. **New (2026-02-19).**

**Recommended implementation order (per consolidated review §3):**
1. COE α (foundations) — 5 days
2. VIE hardening — 3 days (parallel with COE α)
3. COE β (lanes + reservations + I/O pool) — 5 days
4. BI5 read-side refactor — 4 days (parallel with COE β)
5. UKIE α (domain registry + connector Protocol) — 2 days
6. UKIE β (pipeline stages + governance cutover) — 5 days
7. COE γ (retries + dead-letter + provider-aware admission) — 4 days
8. UKIE γ (connector fleet — 5 connectors in parallel) — ~1 day each
9. Consolidated observability — 2 days

**Critical path:** ~30 days serial / ~18 days with parallel tracks.

**NO code changes yet.** Awaiting operator approval on the consolidated
implementation sequence before beginning Phase-2 implementation.

## Backlog (P2 / cosmetic)

- Duplicate `operation_id` warning at `legacy/api/admin.py:list_users` (30-sec fix)
- Remove accidental self-submodule pointer at repo root
  (`git rm --cached strategy-factory-canonical`)
- Optional: nightly `mongodump` cron in `factory-mongo` compose

## Test credentials — local validation (NOT production)

See `/app/memory/test_credentials.md`. Production admin credentials (unchanged from session 1):
- Email: `admin@coinnike.com`
- Password: `Tmn0SECEyDxV1KqfbHMw` — rotate after first login

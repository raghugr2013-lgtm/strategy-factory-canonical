# Release Notes

## 1.0.0 — Phase 1 Consolidation (2026-02)

**First consolidated, production-ready release of Strategy Factory.**

### Highlights
- Consolidated three historical bundles (`v01-handoff`, `v06-prod`, `VQB_VPS_ADDITIONS`) into a single repository.
- **Zero Emergent runtime dependencies.** `EMERGENT_LLM_KEY` and Emergent SDKs removed from source, env, and frontend.
- **VIE fully integrated** as an independent HTTP service. 6 providers wired (OpenAI, Anthropic, Gemini, DeepSeek, Groq, Kimi), env-gated, no-crash-on-missing-key.
- **Local JWT + RBAC** in MongoDB with 5 roles (Admin, Developer, Researcher, Operator, Viewer). Refresh-token rotation.
- **Production Docker Compose bundle** — three containers (backend, VIE, frontend) joining an external `vqb-network` with shared Traefik + Mongo + monitoring stack preserved.
- **Versioning & release metadata** baked into images. Exposed at `GET /api/version` and shown in the dashboard.
- **Stage 2 architecture preserved verbatim** under `backend/legacy/` — 145 engines, 60 API routers, cbot/data engines, factory supervisor. Not loaded at runtime; re-enablement documented.

### New surfaces (Phase 1)
- Backend routes: `/api/{auth,admin,strategies,research,dashboard,health,readiness,version}` + `/api/admin/providers/probe`
- VIE service on port 8100 (in-cluster only): `/health`, `/providers`, `/generate`, `/probe`
- Frontend pages: Login · Dashboard · Strategies · Research · Providers (operational dashboard) · Admin

### Ops
- `infra/scripts/{deploy,health,rollback,backup,restore}.sh` — reproducible from clean Ubuntu 24.04 checkout.
- Health probe covers containers, in-cluster reachability, and public HTTPS through Traefik.
- Docker images tagged with `${VERSION}` and `${VERSION}-${COMMIT_SHORT}`.

### Known follow-ups (deferred)
- Sibling APScheduler (`factory_runner`) not enabled — belongs to Stage 2 re-enablement.
- Prometheus `/api/metrics` endpoint on backend — optional additive change, playbook in `docs/DEPLOYMENT.md`.
- Stage 2 engine mounting behind an `ENABLE_LEGACY_ROUTERS=true` flag.
- Conversation memory / streaming in VIE.

See `docs/AUDIT_REPORT.md` for the file-level classification matrix and `docs/MIGRATION_NOTES.md` for the runtime migration path.
g.
- Conversation memory / streaming in VIE.

See `docs/AUDIT_REPORT.md` for the file-level classification matrix and `docs/MIGRATION_NOTES.md` for the runtime migration path.

# Strategy Factory — Deployment Migration Plan

**Companion to:** `docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md` ·
`docs/DEPLOYMENT_OPERATIONS.md`.
**Status:** Canonical stack already under single-project management on
the VPS. This plan documents the **short, non-destructive sequence of
actions** required to align the repository with that state going
forward. **No downtime is required. No container is destroyed. No
MongoDB data is touched.**

---

## 1 · Migration verdict

**No structural migration is required.** The production stack is
already:

- Under a single Compose project (`strategy-factory`) managed by
  `infra/compose/docker-compose.prod.yml`.
- Sharing the `vqb-network` with the two out-of-repo compose projects
  (`factory-mongo`, `caddy`).
- Bound to the canonical repo path `/opt/strategy-factory` (symlink
  to `/home/raghu/projects/strategy-factory-canonical`).

The scope of this migration plan is therefore limited to
**documentation + safety-net** work.

---

## 2 · Steps applied by this pass (safe, non-destructive)

Every step below has been executed as part of this review. Nothing on
the VPS was touched.

| # | Step | Effect | Rollback |
|---|------|--------|----------|
| 1 | Restore `/.env.example` at the repo root (deleted in accidental auto-commit `f676526`, 2026-07-20). | Fresh clones can bootstrap `cp .env.example .env` again. | `git rm .env.example` reverts. |
| 2 | Create `docs/DEPLOYMENT_ARCHITECTURE_REVIEW.md`. | Documents the as-is topology + inconsistencies. | Delete the file. |
| 3 | Create `docs/DEPLOYMENT_OPERATIONS.md`. | Single source of truth for operations. | Delete the file. |
| 4 | Create `docs/DEPLOYMENT_MIGRATION_PLAN.md` (this file). | Records the plan + inventory. | Delete the file. |

None of the steps above touch application logic, API contracts,
database schemas, engine code, strategy definitions, OBSERVE-mode
enforcement, or backward-compatibility surfaces.

---

## 3 · Post-review VPS verification checklist (run BEFORE next deploy)

Order matters. Stop on the first `FAIL` and remediate.

```bash
# On the VPS as root or the docker-group user.
cd /opt/strategy-factory

# 1. Confirm the canonical checkout is on origin/main and clean.
git rev-parse HEAD                                     # should equal `git rev-parse origin/main`
git status --short --branch                            # should print exactly `## main...origin/main`

# 2. Confirm the four factory containers are managed by the
#    `strategy-factory` compose project (single project, no duplicates).
docker compose ls | grep strategy-factory              # exactly one row
docker compose --project-name strategy-factory ps       # 4 rows: backend / vie / frontend / runner

# 3. Confirm the two external services are in their own compose projects.
docker compose ls | grep -E 'factory-mongo|caddy'      # two additional rows

# 4. Confirm no orphaned duplicate factory containers exist.
docker ps -a --format '{{.Names}}' | sort | uniq -c | awk '$1>1'   # should print nothing

# 5. Confirm all six containers are on vqb-network.
for c in factory-backend factory-frontend factory-vie factory-runner factory-mongo caddy; do
  on=$(docker inspect "$c" -f '{{if index .NetworkSettings.Networks "vqb-network"}}yes{{end}}')
  printf '%-20s vqb-network=%s\n' "$c" "${on:-NO}"
done                                                    # all six must print 'yes'

# 6. Confirm SHARED_MONGO_URL uses factory-mongo alias + authSource=admin.
grep '^SHARED_MONGO_URL=' /opt/strategy-factory/.env    # mongodb://root:...@factory-mongo:27017/?authSource=admin

# 7. Full health check.
/opt/strategy-factory/infra/scripts/health.sh           # must exit 0, all green
```

If step 4 finds duplicate names, one of them is a leftover from the
dev overlay (`/opt/strategy-factory/docker-compose.yml`) or a manual
`docker run`. Follow `DEPLOYMENT_OPERATIONS.md` §4.4 (container
recovery runbook) to remove the extra container without losing data.

---

## 4 · Deferred / optional follow-ups (backlog, not blocking)

None of these are required to declare the production foundation
stable. They are catalogued so future ops passes can pick them up.

| # | Item | Priority | Notes |
|---|------|----------|-------|
| 1 | Publish `.env.example` templates for the two out-of-repo compose projects (`deploy-artifacts/factory-mongo/.env.example` and — if ever needed — `deploy-artifacts/caddy/.env.example`). | LOW | Only content: `MONGO_ROOT_USERNAME=root` + `MONGO_ROOT_PASSWORD=change-me`. Non-blocking; the runbook already documents these values. |
| 2 | Retire stale documentation copies (`docs/DEPLOYMENT_ASSUMPTIONS.md`, `docs/POST_FREEZE_DEPLOYMENT_CHECKLIST.md`, `memory/VPS_DEPLOYMENT_RUNBOOK.md`) once `DEPLOYMENT_OPERATIONS.md` has been signed off by ops. | LOW | Move them to `docs/legacy/` rather than delete — historical context matters. |
| 3 | Remove `traefik.*` labels from `docker-compose.prod.yml` once the ops team commits to Caddy long-term. | LOW | Labels are inert under Caddy today; deleting them buys nothing except readability. |
| 4 | Add a CI job that runs `docker compose --env-file .env.example -f infra/compose/docker-compose.prod.yml config` on every PR — catches interpolation regressions before merge. | LOW | Purely a safety net. |

---

## 5 · What this migration explicitly **does not do**

- Does not rename `docker-compose.yml` at the repo root. It is the
  documented dev overlay and is used by
  `scripts/one_click_deploy.sh` for local acceptance runs.
- Does not delete `deploy-artifacts/`. Those are reference copies of
  the two out-of-repo compose projects and are intentionally committed
  so a fresh VPS build can be reproduced from a single git clone.
- Does not modify `infra/compose/docker-compose.prod.yml` or any
  script under `infra/scripts/`. Those already carry the canonical
  behaviour.
- Does not change any environment variable name, default, or feature
  flag. `.env.example` was restored verbatim from git history plus a
  brief pointer to the new operations doc.
- Does not touch MongoDB data, indexes, or user records.
- Does not alter OBSERVE-mode gates or freeze policy.

---

## 6 · Sign-off gate

Migration is considered complete when:

1. `git status` on `/opt/strategy-factory` is clean and at
   `origin/main`.
2. `./infra/scripts/health.sh` exits 0 with all-green output.
3. Section 3's checklist steps 1–7 all pass.
4. Ops confirms this document + `DEPLOYMENT_OPERATIONS.md` supersede
   the six stale runbooks listed in §4.6 of the review.

Once all four are true, the production foundation is stable and the
next development phase (Historical Knowledge Base Compatibility &
Migration) may begin.

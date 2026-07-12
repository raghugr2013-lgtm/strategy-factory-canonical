# Versioning

Semantic versioning driven from the `VERSION` file at the repo root.

## Sources of truth

- `VERSION` — plain-text semver (e.g. `1.0.0`). Human-edited on each release.
- `git rev-parse HEAD` — commit SHA at build time.
- Build date — set at `docker build` invocation time.

## Injection

`deploy.sh` sets three build args on every image:

```
--build-arg BUILD_VERSION=$(cat VERSION)
--build-arg BUILD_COMMIT=$(git rev-parse --short=12 HEAD)
--build-arg BUILD_DATE=$(date -u +%FT%TZ)
```

- Backend Dockerfile propagates these to env → `app/core/versioning.py` reads them at request time.
- Frontend Dockerfile (multi-stage) can pass them via `REACT_APP_BACKEND_URL` build args + a small `<meta>` tag in the SPA if desired (Phase 1 uses the backend-exposed values in the dashboard).

## Runtime surfaces

- `GET /api/version` → `{ version, commit, build_date, service }`
- `GET /api/health` includes the same fields
- Dashboard footer/panel shows `version`, first 10 chars of `commit`, `build_date`

## Image tagging

Convention (used by `deploy.sh` and `rollback.sh`):

```
strategy-factory/backend:${VERSION}
strategy-factory/backend:${VERSION}-${COMMIT_SHORT}
strategy-factory/vie:${VERSION}
strategy-factory/vie:${VERSION}-${COMMIT_SHORT}
strategy-factory/frontend:${VERSION}
strategy-factory/frontend:${VERSION}-${COMMIT_SHORT}
```

The `.env` file's `FACTORY_IMAGE_TAG` selects which tag Compose will pull/run. Rollback = change tag + `up -d`.

## Release process

1. Update `VERSION` (`1.0.0 → 1.1.0`).
2. Update `docs/RELEASE_NOTES.md` with the changes.
3. Commit + tag: `git tag v1.1.0 && git push --tags`.
4. On the VPS: `git pull && ./infra/scripts/deploy.sh` — the deploy script picks up the new VERSION and commit automatically.

## Migration notes

`docs/MIGRATION_NOTES.md` — one section per breaking change, with the exact command sequence to migrate data or configuration.

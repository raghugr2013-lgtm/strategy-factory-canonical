# Migration Notes

Cumulative log of runtime migrations. Each release adds a section.

## 1.0.0 — from v01 handoff bundle

### Environment variables

| Old (v01 `.env`) | New (`.env.example`) | Notes |
|---|---|---|
| `MONGO_URL="mongodb://localhost:27017"` | `SHARED_MONGO_URL=<full URI>` | Now requires the DB in the URI or `?authSource=admin`. Backend reads `MONGO_URL` — compose maps `SHARED_MONGO_URL` onto it. |
| `DB_NAME="test_database"` | `FACTORY_DB_NAME="strategy_factory_v1"` | Fresh, non-conflicting DB name. Any pre-existing `strategy_factory` on the source Mongo (from earlier exploratory runs) is preserved untouched. Use the migration engine (`infra/scripts/migrate-data.py`) rather than `mongorestore` — it stamps `_migration_meta.source_fingerprint` for zero-loss verification. |
| `EMERGENT_LLM_KEY=…` | *(removed)* | Replaced by per-provider keys. |
| *(none)* | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `GROQ_API_KEY`, `KIMI_API_KEY` | Missing key → provider disabled, no crash. |
| `JWT_SECRET=<hex>` | same | unchanged. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | same | Idempotent seed. |
| *(none)* | `JWT_ACCESS_TTL_MIN`, `JWT_REFRESH_TTL_DAYS` | Tunable token TTLs. |
| *(none)* | `BUILD_VERSION`, `BUILD_COMMIT`, `BUILD_DATE` | Baked into images by `deploy.sh`. |

### MongoDB

- New collections owned by Phase 1: `users`, `refresh_tokens`, `strategies`, `research_queries`.
- Legacy `strategy_library` (14-doc cohort) is untouched; Stage 2 modules that consumed it are archived. To bring them back:
  ```bash
  # restore the legacy dump into the new DB
  docker run --rm --network vqb-network -v /path/to/dump:/dump mongo:7.0 \
    mongorestore --uri "$SHARED_MONGO_URL" \
      --archive=/dump/mongodb-dump-20260614_151752.archive.gz --gzip \
      --nsFrom='test_database.*' --nsTo='strategy_factory.*'
  ```

### Users

- v01 used a `pending → approved` workflow with a single `user` role.
- Phase 1 uses `status ∈ {active, disabled}` and one of 5 explicit roles.
- Existing users can be migrated in-place:
  ```javascript
  db.users.updateMany(
    { role: { $exists: false } },
    { $set: { role: "viewer", status: "active" } }
  );
  db.users.updateMany({ status: "pending" },  { $set: { status: "active" } });
  db.users.updateMany({ status: "approved" }, { $set: { status: "active" } });
  ```

### Legacy runtime

- The `factory-runner` sibling scheduler is NOT started by the Phase 1 compose. To re-enable Stage 2 modules:
  1. `pip install -r backend/legacy/requirements.legacy.txt` inside the backend image (edit the Dockerfile).
  2. Mount the desired routers in `app/main.py`:
     ```python
     if os.getenv("ENABLE_LEGACY_ROUTERS") == "true":
         from legacy.api.strategies import router as legacy_strategies_router
         app.include_router(legacy_strategies_router, prefix="/api/legacy")
     ```
  3. Add a `factory-runner` service to `docker-compose.prod.yml` using the same image but a different entrypoint.

### Frontend

- v01 `App.js` and `services/api.js` (Emergent-preview-aware) are removed.
- `REACT_APP_BACKEND_URL` is the single source of truth. Set at `docker build` time via the `--build-arg REACT_APP_BACKEND_URL=https://<domain>` in the frontend Dockerfile.

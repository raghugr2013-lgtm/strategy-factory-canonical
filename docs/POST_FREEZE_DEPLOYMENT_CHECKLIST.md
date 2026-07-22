# Post-Freeze VPS Deployment Checklist

**Use this checklist to bring `v1.2.0-alpha2-feature-freeze` up on the target VPS.**

The full playbook lives in `docs/VPS_MIGRATION_PLAYBOOK.md`. This checklist is the concrete, tickable go-live sequence for this freeze tag.

---

## 0. Prerequisites

- [ ] SSH access to the VPS as the deploy user.
- [ ] MongoDB reachable from the VPS (either co-located or managed).
- [ ] All secrets ready:
  - [ ] `MONGO_URL`, `DB_NAME`
  - [ ] `JWT_SECRET` (32+ random bytes — regenerate for prod, never reuse dev)
  - [ ] `ADMIN_EMAIL`, `ADMIN_PASSWORD`
  - [ ] `CTRADER_CLIENT_ID`, `CTRADER_CLIENT_SECRET`, `CTRADER_ACCOUNT_ID` (only if BROKER=ctrader)

## 1. Fetch the freeze commit

```bash
git clone <repo>
cd <repo>
git fetch --tags
git checkout v1.2.0-alpha2-feature-freeze
git rev-parse HEAD > /tmp/deploy_sha.txt
```

## 2. Environment file

Copy `.env.example` → `.env` at the **repository root** and fill in:

> The `.env` file MUST live at the repo root (not at `infra/compose/.env`). Every deployment tool in this repo — `deploy.sh`, `precheck.sh`, `health.sh`, `rollback.sh`, the `infra/scripts/compose.sh` wrapper, and every documented `docker compose … --env-file .env -f infra/compose/docker-compose.prod.yml …` invocation — resolves `.env` from the repo root. Placing it anywhere else, or invoking compose from `infra/compose/` without an explicit `--env-file`, silently loads an empty environment (compose defaults to `<cwd>/.env`) and the backend crashes with empty `MONGO_URL` / `JWT_SECRET`. The compose file now emits a hard `${VAR:?…}` interpolation error at YAML parse time if the required variables are missing, so the wrong invocation now fails fast with an explicit message — but the layout rule remains: **`.env` at repo root, always**.

```
MONGO_URL=<prod>
DB_NAME=strategy_factory_v1_prod
JWT_SECRET=<32-byte random>
ADMIN_EMAIL=<ops>
ADMIN_PASSWORD=<strong>

# Master switches — leave defaults for first boot
ORCHESTRATOR_ENABLED=false
MI_ENABLED=false
EXEC_ENABLED=false
BROKER=paper
META_LEARNING_MODE=observe
FACTORY_EVAL_MODE=observe
LEARNING_CONTINUOUS_MODE=false
```

**Deliberately conservative first boot.** Enable engines one at a time after each smoke check.

## 3. Install deps

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
```

## 4. First boot smoke test (dry-run)

```bash
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 &
sleep 5
curl -sf http://localhost:8001/api/health && echo ok
kill %1
```

Watch the boot log for these **required** lines:

- [ ] `legacy full-recovery mount: 100 routers/attachers online`
- [ ] `meta_learning engine ready (mode=observe, cadence=900s)`
- [ ] `factory_eval engine ready (mode=observe, cadence=3600s)`
- [ ] `Application startup complete`

If any line is missing → abort deployment, investigate before continuing.

## 5. Verify orchestrator task count

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<admin>","password":"<pw>"}' | \
  python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -sf -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/orchestrator_engine/tasks \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('tasks:', d['count'])"
```

**Expected: `tasks: 17`.**

## 6. Verify engine modes

```bash
curl -sf -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/meta-learning/config | grep MODE
curl -sf -H "Authorization: Bearer $TOKEN" \
  http://localhost:8001/api/factory-eval/config | grep MODE
```

Both must show `observe`.

## 7. Register with supervisord (or systemd)

```
[program:strategy_factory_backend]
command=/path/to/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
directory=/path/to/backend
user=<deploy>
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/backend.out.log
stderr_logfile=/var/log/supervisor/backend.err.log
environment=PYTHONPATH="/path/to/backend/legacy:/path/to/backend"
```

`supervisorctl reread && supervisorctl update && supervisorctl start strategy_factory_backend`

## 8. Fronting proxy

**Production reverse proxy: Caddy** (see `infra/caddy/README.md`).

- [ ] Caddy is on Docker network `vqb-network` and can resolve
      `factory-backend` and `factory-frontend`.
- [ ] Caddyfile reverse-proxies `/api/*` → `factory-backend:8001`
      and everything else → `factory-frontend:80`.
- [ ] TLS is terminated by Caddy on `:443` (auto-cert via Let's Encrypt).
- [ ] Health probe hitting `/api/health` every 30s.
- [ ] Rate limit `/api/auth/login` (≤10/min per IP recommended — configure
      via Caddy `rate_limit` directive or the shared network policy).
- [ ] `docker-compose.prod.yml` emits `traefik.*` labels; these are INERT
      under Caddy and do not need to be removed.

## 9. Firewall

- [ ] Port 8001 not reachable from public internet directly.
- [ ] MongoDB port not reachable from public internet.
- [ ] Only 443 (and 22 for SSH) exposed.

## 10. Baseline snapshot

Record the following BEFORE running any validation:

```bash
curl -sf -H "Authorization: Bearer $TOKEN" http://<host>/api/deployment/status > /tmp/baseline_status.json
curl -sf -H "Authorization: Bearer $TOKEN" http://<host>/api/orchestrator_engine/tasks > /tmp/baseline_tasks.json
curl -sf -H "Authorization: Bearer $TOKEN" http://<host>/api/factory-eval/config > /tmp/baseline_fe_config.json
```

Attach all three to the Production Sign-off document.

## 11. Green-light for validation

Only after all above boxes are ticked, proceed to:

- Paper Broker Validation → `backend/scripts/paper_flow_drill.py`
- 24-hour Tier 5 → `backend/scripts/tier5_validation.py --duration-s 86400`
- 72-hour Tier 5 → `backend/scripts/tier5_validation.py --duration-s 259200`

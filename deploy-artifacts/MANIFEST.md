# Strategy Factory — deployment artifact manifest

## Verified against canonical repository

- Repo:   `https://github.com/raghugr2013-lgtm/strategy-factory-canonical.git`
- Branch: `main`
- Commit: `546d0a9cbd9af0fced373b7aac3d893255febeae`
- Date:   `2026-07-18T15:18:45Z`

The infrastructure contract in the canonical repo — production compose
file (`infra/compose/docker-compose.prod.yml`), deploy scripts
(`infra/scripts/*`), and env contract (`.env.example`) — is **byte-for-byte
identical** between the previous verified commit `ee62c12…` and this
commit `546d0a9…`. No artifact content change was required; only this
manifest header + a comment line in `factory-bootstrap.sh` were updated.

Application-code changes between the two commits are limited to
`backend/legacy/tests/*` + `backend/tests/backend_test.py` and various
docs — none of which affect deployment topology.

## Contents

```
deploy-artifacts/
├── DEPLOY_RUNBOOK.md              # step-by-step + troubleshooting + rollback
├── MANIFEST.md                    # this file
├── factory-bootstrap.sh           # one-shot idempotent installer (chmod +x)
├── factory-mongo/
│   ├── docker-compose.yml         # Mongo 7, --auth, vqb-network, no host port
│   └── .env                       # MONGO_ROOT_USERNAME / MONGO_ROOT_PASSWORD
├── caddy/
│   ├── docker-compose.yml         # caddy:2-alpine, 80/443 tcp + 443 udp
│   └── Caddyfile                  # /api/* → backend, / → frontend
└── repo-env/
    └── .env                       # to be placed at /opt/strategy-factory/.env
```

## VPS layout after transfer

| Artifact | Destination on VPS |
|---|---|
| `factory-mongo/docker-compose.yml` | `/opt/factory-mongo/docker-compose.yml` |
| `factory-mongo/.env` | `/opt/factory-mongo/.env` (chmod 600) |
| `caddy/docker-compose.yml` | `/opt/caddy/docker-compose.yml` |
| `caddy/Caddyfile` | `/opt/caddy/Caddyfile` — edit ACME email first |
| `repo-env/.env` | `/opt/strategy-factory/.env` (chmod 600) |
| `factory-bootstrap.sh` | `/opt/factory-bootstrap.sh` (chmod +x) |

## Transfer + install one-liner

```bash
# On your workstation → VPS
scp deploy-artifacts.tar.gz root@144.91.78.175:/tmp/
scp deploy-artifacts.tar.gz.sha256 root@144.91.78.175:/tmp/

# On the VPS
cd /tmp && sha256sum -c deploy-artifacts.tar.gz.sha256   # must print OK
sudo mkdir -p /opt/factory-mongo /opt/caddy /opt/strategy-factory
sudo tar -xzf deploy-artifacts.tar.gz -C /tmp/deploy-artifacts-unpack --strip-components=0 || {
  mkdir -p /tmp/deploy-artifacts-unpack
  sudo tar -xzf deploy-artifacts.tar.gz -C /tmp/deploy-artifacts-unpack
}

# Place files (idempotent)
sudo install -m 644 /tmp/deploy-artifacts-unpack/factory-mongo/docker-compose.yml  /opt/factory-mongo/
sudo install -m 600 /tmp/deploy-artifacts-unpack/factory-mongo/.env                /opt/factory-mongo/
sudo install -m 644 /tmp/deploy-artifacts-unpack/caddy/docker-compose.yml          /opt/caddy/
sudo install -m 644 /tmp/deploy-artifacts-unpack/caddy/Caddyfile                   /opt/caddy/
sudo install -m 600 /tmp/deploy-artifacts-unpack/repo-env/.env                     /opt/strategy-factory/.env
sudo install -m 755 /tmp/deploy-artifacts-unpack/factory-bootstrap.sh              /opt/factory-bootstrap.sh

# Edit the ACME email BEFORE running the bootstrap
sudo sed -i 's|REPLACE_WITH_LETSENCRYPT_EMAIL@example.com|YOUR@REAL_EMAIL|' /opt/caddy/Caddyfile

# Run
sudo bash /opt/factory-bootstrap.sh
```

## Observations about the new canonical HEAD

1. `deploy-artifacts/` folder was **committed into the canonical repo** at
   `546d0a9`. That's fine — those are non-secret reference copies. The
   secret files (`factory-mongo/.env`, `repo-env/.env`) are NOT in git.
2. There is a **stray submodule pointer** at the repo root named
   `strategy-factory-canonical` (mode `160000`, pointing to previous
   SHA `ee62c122…`). Almost certainly accidental — a nested clone got
   `git add`-ed. Non-blocking for deploy; recommended cleanup:
   ```bash
   cd /opt/strategy-factory
   git rm --cached strategy-factory-canonical
   git commit -m "chore: remove accidental self-submodule"
   git push origin main
   ```
   Once removed, the bootstrap's clean-tree check will not be
   disturbed by it (a submodule pointer registers as clean, but it is
   dead weight).

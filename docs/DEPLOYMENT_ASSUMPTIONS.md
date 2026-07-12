# Deployment Assumptions

Explicit list of every assumption `bootstrap-vps.sh`, `precheck.sh`, `deploy.sh`, and `health.sh` make about the VPS environment. If any of these is violated, the scripts will surface the exact reason and refuse to proceed — no debugging spelunking required.

---

## 1. Host

| Assumption | Rationale | Failure mode if violated |
|---|---|---|
| Ubuntu 24.04 LTS (`noble`) | apt sources for Docker's official repo are keyed on the codename | `bootstrap-vps.sh` installs Docker via the Ubuntu 24.04 apt line; on other distros it will silently install nothing or the wrong package. Use `bootstrap-vps.sh` only on Ubuntu 24.04. |
| Root or sudo available for the operator | `bootstrap-vps.sh` runs `apt-get`, `systemctl enable`, `usermod -aG docker` | Script exits with `error: must run as root (sudo)` |
| At least 4 vCPU / 8 GB RAM | Backend + VIE + frontend + shared Mongo + shared monitoring stack fit comfortably on 12/48. Below 8 GB you may see OOM on the frontend build step (Node + webpack). | `docker compose build` may kill Node during production bundling |
| Network egress to `download.docker.com`, `deb.debian.org`, `pypi.org`, `registry.npmjs.org` | Package pulls during `apt-get` and `docker build` | Corresponding pip/yarn/apt step fails; deploy aborts |
| Ports 80 and 443 free (owned by the shared Traefik) | Our containers do not bind host ports; only Traefik does | If Traefik is not running, our services still start but the domain is unreachable. `precheck.sh` warns about missing Traefik. |

## 2. Docker environment

| Assumption | Rationale | Failure mode if violated |
|---|---|---|
| Docker Engine 24+ with Compose plugin v2+ | `docker compose` (not `docker-compose`) is required | `precheck.sh` fails: "docker compose plugin not installed" |
| The operator's shell is in the `docker` group OR they invoke via `sudo` | Compose commands need daemon access | `precheck.sh` fails: "docker daemon not reachable" |
| An external Docker network named `vqb-network` exists | All three of our services attach to it, as do Traefik, Mongo, Redis, monitoring | `bootstrap-vps.sh` and `deploy.sh` both create it if missing; no failure |

## 3. Shared platform services (out of this repository's scope, must be running separately on the VPS)

| Service | Assumption | Failure mode |
|---|---|---|
| **Traefik v3** | Running on `vqb-network`, terminates TLS on `TRAEFIK_WEBSECURE_ENTRYPOINT`, has the cert resolver named in `TRAEFIK_CERT_RESOLVER`. Our compose file's Traefik labels attach a router; Traefik reads them via its Docker provider. | `precheck.sh` warns "no Traefik container detected on vqb-network"; public HTTPS won't work. |
| **MongoDB (shared)** | Running on `vqb-network`, resolvable by hostname (typically `mongo`), reachable at `SHARED_MONGO_URL` with the credentials given. The `strategy_factory` DB either exists or the connecting user has permission to create it. | `precheck.sh` fails: "SHARED_MONGO_URL not reachable". The backend also fails at startup with a clear log line. |
| **Redis (optional)** | If `SHARED_REDIS_URL` is set, Redis must be on `vqb-network` and reachable via that URL. If unset, backend readiness reports `skipped`. | `precheck.sh` warns non-fatally; overall status stays green if Redis is unused. |
| **Prometheus / Grafana / Loki / Promtail / cAdvisor / node-exporter** | Running on `vqb-network`, using Docker labels for target discovery. Our containers carry `prometheus.scrape=true` + `logging=promtail` + `loki_service=…` labels. | Metrics/logs simply do not appear in the shared dashboards. No functional impact on Strategy Factory. |

**None of these services are managed by this repository.** They pre-exist on the VPS and are owned by the shared platform infrastructure.

## 4. DNS

| Assumption | Rationale | Failure mode |
|---|---|---|
| `FACTORY_DOMAIN` (`strategy.coinnike.com`) has an A record (and optionally AAAA) pointing at the VPS's public IP **before** the first deploy | Let's Encrypt HTTP-01 challenge requires DNS to resolve before the cert can be issued | Traefik logs will show a cert-issuance failure. First-time deploys can loop until DNS propagates. |
| `getent hosts $FACTORY_DOMAIN` succeeds on the VPS itself | Confirms DNS is queryable from the box | `precheck.sh` fails: "DNS lookup failed for $FACTORY_DOMAIN" |

## 5. Repository / operator workflow

| Assumption | Rationale | Failure mode |
|---|---|---|
| `.env` at repo root, `600` permissions | Compose reads it; ensures secrets aren't world-readable | `deploy.sh` fails: ".env not found" |
| All required env vars filled; no `CHANGE_ME` placeholders | Fail-fast validation | `precheck.sh` fails: "env var X is unset or still a placeholder" |
| Repo is on a filesystem that supports Docker bind mounts | Compose reads `../../backend`, `../../vie`, `../../frontend` build contexts from `infra/compose/` | Bind-mount errors during build |
| Operator has ≥ 5 GB free disk for the built images | Multi-stage builds retain intermediate layers | `docker build` fails with `no space left on device` |
| Server clock is roughly correct (NTP-synced within ~5 min of true) | JWT tokens' `exp` and `iat` are absolute timestamps; wildly wrong clock = tokens invalid | Login "works" but every subsequent call 401s. Symptom: users get logged out immediately. |

## 6. Provider API keys (VIE)

| Assumption | Rationale | Failure mode |
|---|---|---|
| API keys in `.env` are current and belong to accounts with quota | VIE probes them live via `POST /api/admin/providers/probe` | Provider card turns red with the exact upstream 401/429/etc. error message |
| Missing keys are simply left blank | Env-gated: blank = provider disabled | No failure. Provider reports `available: false, error: "api key not configured"` |

## 7. Network egress from containers

| Destination | Purpose | Required? |
|---|---|---|
| `api.openai.com`, `api.anthropic.com`, `generativelanguage.googleapis.com`, `api.deepseek.com`, `api.groq.com`, `api.moonshot.ai` | VIE provider calls | Only for the providers you enabled |
| `fonts.googleapis.com`, `fonts.gstatic.com` | UI web font (Inter / JetBrains Mono via `<link>` in `index.html`) | Yes (for frontend) — if your VPS blocks outbound, mirror the fonts locally or self-host them (~150 KB) |
| `acme-v02.api.letsencrypt.org` | Cert renewal (managed by shared Traefik, not by us) | Only during cert issue/renewal |

If the VPS runs behind egress restrictions, whitelist the domains above.

## 8. Backup / restore

- `./infra/scripts/backup.sh` assumes `SHARED_MONGO_URL` is reachable from a fresh `mongo:7.0` container on `vqb-network`. It writes to a host directory that must be writable by root.
- `./infra/scripts/restore.sh` requires the archive to be on the host filesystem, readable by root, and takes a full `mongorestore --drop` — destructive for the `strategy_factory` DB.

## 9. What the scripts DO NOT assume

To reduce ambiguity, here is what the scripts **do not** require:

- ❌ You do NOT need to pre-install pip / yarn / Node / Python on the host — everything is inside container images.
- ❌ You do NOT need to open any host ports — Traefik owns 80/443.
- ❌ You do NOT need to create the `strategy_factory` DB in Mongo manually — the backend does it on first write.
- ❌ You do NOT need to seed the admin — `app/auth/seed.py` runs idempotently on every backend boot.
- ❌ You do NOT need to create Mongo indexes — `ensure_indexes()` runs at startup.
- ❌ You do NOT need to configure Prometheus/Grafana/Loki — they pick up our labels via docker_sd automatically.
- ❌ You do NOT need to install Redis — it's optional.
- ❌ You do NOT need to modify any source code between download and deploy.

## 10. If a deploy fails

`health.sh` prints exactly what failed. Common paths:

| Symptom | Fix |
|---|---|
| `container factory-backend → state=exited` | `docker logs factory-backend` — most common cause: `SHARED_MONGO_URL` wrong or Mongo not reachable |
| `container factory-vie → health=starting` (stuck) | `docker logs factory-vie` — usually a Python import error; the compiled Python check in `precheck.sh` catches most of these at deploy time |
| `readiness → mongo=red` | Mongo credentials wrong or Mongo not reachable from `vqb-network` |
| `readiness → vie=yellow` | Backend can't reach VIE — verify `factory-vie` is up and both are on `vqb-network` |
| `public https://.../api/health failed` | Traefik router misconfigured — check `docker logs traefik` for cert or route issues |
| Login "works" then everything 401s | Server clock is wrong — `sudo timedatectl status` |

Each of the above is a well-known Docker/networking issue, not a Strategy Factory bug. The scripts are engineered to surface these fast, not hide them.

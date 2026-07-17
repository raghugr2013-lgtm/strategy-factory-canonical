# Caddy — production reverse proxy

**Caddy is the production reverse proxy for `strategy.coinnike.com`.** It
runs *outside* this repository (as an "externally managed" shared service on
the VPS) and is configured via a Caddyfile hosted at
`/etc/caddy/Caddyfile` (native install) or bind-mounted into a Caddy
container. This directory documents the contract this stack expects of that
external Caddy instance — it does not run Caddy.

## Contract

Caddy MUST:

1. Terminate TLS on `:443` for `${FACTORY_DOMAIN}` (auto-cert via Let's
   Encrypt or Cloudflare — Caddy's default).
2. Be attached to Docker network **`vqb-network`** so it can resolve
   `factory-backend` and `factory-frontend` by their compose DNS aliases.
3. Reverse-proxy `/api/*` requests to `factory-backend:8001`.
4. Reverse-proxy everything else to `factory-frontend:80`.

## Reference Caddyfile

```caddyfile
strategy.coinnike.com {
    encode zstd gzip

    # API surface — Phase-1 core + 89 legacy routers all live under /api.
    handle /api/* {
        reverse_proxy factory-backend:8001 {
            transport http {
                dial_timeout    5s
                read_timeout   60s
                write_timeout  60s
            }
            # Preserve the client's original host / IP so the backend's
            # CORS + RBAC + audit-journal logic sees the real caller.
            header_up Host              {host}
            header_up X-Real-IP         {remote}
            header_up X-Forwarded-For   {remote}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # Everything else → static frontend (React SPA behind nginx).
    handle {
        reverse_proxy factory-frontend:80
    }

    # Access log for /api/* — useful for the Production Validation Suite
    # and Tier 5 latency correlation.
    log {
        output file /var/log/caddy/strategy-factory.access.log
        format json
    }
}
```

## Deploying Caddy as a Docker container (recommended)

If Caddy runs as a container, it MUST join `vqb-network`:

```yaml
# /opt/caddy/docker-compose.yml   (managed separately from this repo)
services:
  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks: [vqb-network]

networks:
  vqb-network:
    external: true

volumes:
  caddy_data: {}
  caddy_config: {}
```

Reload without downtime after Caddyfile changes:
```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## Deploying Caddy as a systemd service on the host

If Caddy runs natively (not in a container), it CANNOT resolve
`factory-backend` via Docker DNS. In that case:

- Either publish backend port 8001 to the host and use
  `reverse_proxy 127.0.0.1:8001` (requires editing
  `infra/compose/docker-compose.prod.yml` to add
  `ports: ["127.0.0.1:8001:8001"]`), **or**
- Run Caddy in a container as above (preferred — no host port exposure).

## Verifying the wiring

From the VPS, after `docker compose up -d` completes:

```bash
# Public HTTPS should return 200
curl -fsS https://strategy.coinnike.com/api/health

# Full validation suite against the deployed URL
cd /opt/strategy-factory
VALIDATION_BASE_URL=https://strategy.coinnike.com \
VALIDATION_ADMIN_EMAIL="$ADMIN_EMAIL" \
VALIDATION_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
./infra/validation/run.sh --full
```

If `curl` returns `502 Bad Gateway`, run
`./infra/scripts/diagnose-502.sh` — it walks every hop between Caddy
and the container.

## Historical note

Earlier revisions of this repo assumed Traefik. The compose file still
emits `traefik.*` labels for a possible future Traefik migration —
those labels are **INERT** under Caddy. See
`infra/traefik/README.md` for the deprecation record.

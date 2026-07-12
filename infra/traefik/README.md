# Traefik configuration

Traefik is **externally managed** on the VPS — this stack does not run its own Traefik and does not modify the shared instance's config.

Our containers plug into the shared `vqb-network` and expose Traefik routing labels in `infra/compose/docker-compose.prod.yml`:

- `factory-backend`  ← Host(FACTORY_DOMAIN) && PathPrefix(/api)  → port 8001  (priority 100)
- `factory-frontend` ← Host(FACTORY_DOMAIN)                       → port 80    (priority 10)
- `factory-vie` — NOT exposed (in-cluster only)

TLS is issued by the resolver named in `TRAEFIK_CERT_RESOLVER` (default `letsencrypt`) on the entryPoint `TRAEFIK_WEBSECURE_ENTRYPOINT` (default `websecure`).

For the reference shared-Traefik config that this stack assumes, see `docs/legacy/vps-snapshot/`.

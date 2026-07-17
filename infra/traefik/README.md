# Traefik configuration — NOT USED

> **This deployment uses Caddy, not Traefik.** See
> [`infra/caddy/README.md`](../caddy/README.md) for the actual reverse-proxy
> contract.

## Deprecation record

Earlier revisions of this repo assumed a shared Traefik instance on the
VPS. When the production VPS was actually provisioned, a Caddy reverse
proxy was chosen instead. The `traefik.*` labels still emitted by
`infra/compose/docker-compose.prod.yml` are therefore **inert** — Caddy
ignores them.

The labels are retained (not deleted) because they:

- Cost nothing (Caddy ignores unknown labels).
- Encode the intended router / service / port / TLS contract in one place,
  so a future migration back to Traefik is a one-line switch (attach
  Traefik to `vqb-network`, remove the Caddy container).

## Assumed contract (kept for reference)

If a future migration re-enables Traefik, the labels declare:

- `factory-backend`  ← `Host(FACTORY_DOMAIN) && PathPrefix(/api)`  → port 8001  (priority 100)
- `factory-frontend` ← `Host(FACTORY_DOMAIN)`                      → port 80    (priority 10)
- `factory-vie` — NOT exposed (in-cluster only)
- TLS: `TRAEFIK_CERT_RESOLVER` (default `letsencrypt`) on the entryPoint
  `TRAEFIK_WEBSECURE_ENTRYPOINT` (default `websecure`).

To re-activate Traefik: attach a Traefik container to `vqb-network`,
disable Caddy for `${FACTORY_DOMAIN}`, and the labels take effect
without any code change.

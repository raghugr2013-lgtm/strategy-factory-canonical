# Monitoring

Prometheus / Grafana / Loki / Promtail / cAdvisor / Node Exporter are **externally managed** on the VPS and shared with other stacks.

Our three containers carry the standard scrape + logging labels:

```
prometheus.scrape=true
prometheus.service=factory-{backend,vie,frontend}
logging=promtail
loki_service=factory-{backend,vie,frontend}
```

**No code changes required on the shared monitoring stack** — the existing cAdvisor + Promtail docker_sd discovery picks up any container with these labels.

## Optional additions

- **`/api/metrics` Prometheus endpoint on the backend:** playbook in `docs/DEPLOYMENT.md`. Not enabled in Phase 1.
- **Grafana dashboards:** import cAdvisor Dashboard 14282 and add a JSON-API datasource pointing at `https://${FACTORY_DOMAIN}/api/readiness` for the tile matrix.

For reference dashboards from the pre-consolidation VPS, see `docs/legacy/vps-snapshot/`.

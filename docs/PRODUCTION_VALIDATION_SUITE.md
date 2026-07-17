# Production Validation Suite

Automated backend validation framework. Runs before every production release and doubles as our permanent regression harness.

## Layout

```
infra/validation/
├── run_validation.py        # entrypoint
├── config.py                # env-driven config
├── auth.py                  # JWT session helper
├── reporter.py              # JSON / MD / TXT / console output
├── modules/
│   ├── health.py
│   ├── authentication.py
│   ├── strategy_engineering.py
│   ├── portfolio.py
│   ├── propfirm.py
│   ├── market_intelligence.py
│   ├── execution_intelligence.py
│   ├── meta_learning.py
│   └── factory_evaluation.py
└── reports/                 # JSON/MD/TXT reports land here
```

## Usage

```bash
# Full run (all 9 modules)
python -m infra.validation.run_validation

# Single module (name or alias)
python -m infra.validation.run_validation --module strategy
python -m infra.validation.run_validation --module portfolio
python -m infra.validation.run_validation --module execution
python -m infra.validation.run_validation --module meta        # meta-learning
python -m infra.validation.run_validation --module factory     # factory-eval
python -m infra.validation.run_validation --module market      # market-intel
python -m infra.validation.run_validation --module propfirm
python -m infra.validation.run_validation --module auth
python -m infra.validation.run_validation --module health

# Print the most recent stored report
python -m infra.validation.run_validation --report-only

# 24-hour continuous validation with system metrics
python -m infra.validation.run_validation --tier5

# 72-hour (or arbitrary) continuous
python -m infra.validation.run_validation --tier5 \
  --tier5-hours 72 --tier5-interval-s 600
```

## Environment

| Var | Default | Purpose |
|-----|---------|---------|
| `REACT_APP_BACKEND_URL` or `VALIDATION_BASE_URL` | `http://localhost:8001` | Backend under test |
| `VALIDATION_ADMIN_EMAIL` | `admin@strategy-factory.local` | Login email |
| `VALIDATION_ADMIN_PASSWORD` | `admin123` | Login password |
| `VALIDATION_TIMEOUT_S` | `30` | Per-request timeout |
| `VALIDATION_SLOW_MS_WARN` | `2500` | Latency threshold for WARN |
| `VALIDATION_REPORTS_DIR` | `<pkg>/reports` | Where reports are written |
| `TIER5_DURATION_HOURS` | `24` | Tier 5 duration |
| `TIER5_INTERVAL_SECONDS` | `300` | Tier 5 cadence |

## Reports

Every run writes:
- `reports/validation_report_<STAMP>.json` — machine-readable
- `reports/validation_report_<STAMP>.md` — human-readable per-probe table
- `reports/validation_summary_<STAMP>.txt` — one-page summary
- `reports/validation_report.{json,md}` + `validation_summary.txt` — always-latest (overwritten)

Tier 5 additionally writes:
- `reports/tier5_metrics.json` — per-cycle metrics (updated each cycle)
- `reports/tier5_report.md` — final markdown after the run

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All probes PASS (or WARN — non-blocking) |
| 1 | One or more probes FAIL |
| 2 | Authentication failed or invalid `--module` |

## OBSERVE-mode invariants enforced

Both Meta-Learning (Phase I) and Factory Self-Evaluation (Phase J) validators explicitly assert:

- Engine `mode == "observe"` in `/api/{engine}/config`
- `/api/{engine}/overrides` count == 0
- `/api/{engine}/applications` count == 0
- `POST /api/{engine}/recommendations/{id}/approve` returns HTTP 409

Any deviation is a FAIL, not a WARN. This is the load-bearing production safety guarantee.

## Console output shape

```
[PASS] health                    pass=  4 fail=  0 warn=  0 avg=  32.1ms p95=  60.4ms
[PASS] authentication            pass=  3 fail=  0 warn=  0 avg=  40.2ms p95=  75.1ms
[PASS] strategy_engineering      pass= 17 fail=  0 warn=  1 avg= 108.7ms p95= 240.6ms
[PASS] portfolio                 pass=  8 fail=  0 warn=  2 avg=  55.9ms p95= 120.3ms
[PASS] propfirm                  pass=  7 fail=  0 warn=  0 avg=  45.6ms p95=  90.0ms
[PASS] market_intelligence       pass=  6 fail=  0 warn=  0 avg=  33.0ms p95=  70.2ms
[PASS] execution_intelligence    pass= 11 fail=  0 warn=  0 avg=  42.7ms p95=  95.1ms
[PASS] meta_learning             pass=  9 fail=  0 warn=  0 avg=  65.4ms p95= 140.5ms
[PASS] factory_evaluation        pass= 18 fail=  0 warn=  0 avg=  71.8ms p95= 155.2ms

Summary  PASS 83   FAIL 0   WARN 3   avg_ms=59.4   p95_ms=140.5
```

## Extending

To add a probe module, subclass `ModuleRunner`, register it in `run_validation.py::MODULES`, add an alias to `MODULE_ALIASES`. The framework handles timing, latency-warn, grading, aggregation, and reporting for you.

## Design constraints (enforced)

- **Additive only** — no application-behaviour changes.
- **No new deps** — uses `requests` (already installed) + optional `psutil` (Tier 5 only).
- **Aligns with existing auth + API models** — reuses admin JWT + canonical endpoints.
- **Reproducible reports** — every run produces both stamped and "latest" artefacts.

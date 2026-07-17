# Strategy Factory — Production Validation Suite

Additive, read-only smoke + surface validator for the backend. It exercises
every Phase A–J endpoint surface, grades each response, and produces
JSON / Markdown / TXT reports.

Feature-Freeze compliant: this suite does **not** modify backend behaviour.
It only issues HTTP requests to public + authenticated endpoints.

---

## 1. Where does this run? (READ FIRST)

**On the host (or a jump box) — NOT inside the backend container.**

The suite lives at `<repo-root>/infra/validation/`, which sits **outside**
the `backend/` Docker build context. That is intentional: it is host-side
production infrastructure that probes the deployed public URL through
Traefik, exactly the same surface a real client sees. As a result:

- `infra/validation/` is **not shipped** inside the `factory-backend` image.
- Running `python3 -m infra.validation.run_validation` from inside the
  container will fail with `ModuleNotFoundError: No module named
  'infra.validation'`. This is expected.
- The command **must be executed from the repository root** (the directory
  produced by `git clone` / `git pull`, e.g. `/opt/strategy-factory` on the
  VPS) so that Python can resolve `infra` as a top-level package.

If you invoke from any other directory, use the launcher (see §3) — it
`cd`s to the correct root for you.

---

## 2. Prerequisites

- Python 3.11+ **on the host that will run the suite** (VPS shell,
  workstation, or CI runner — anywhere with network access to the deployed
  backend URL). It does **not** need to run on the same host as the
  containers.
- `requests` — install with `pip3 install -r infra/validation/requirements.txt`
  (also installs the optional `psutil` for Tier 5 system-metrics).
- Reachable backend at `VALIDATION_BASE_URL` (e.g. `https://strategy.coinnike.com`).
- Admin credentials (default: seeded `admin@strategy-factory.local`
  / `admin123` per `/app/memory/test_credentials.md`; overridable via
  `VALIDATION_ADMIN_EMAIL` / `VALIDATION_ADMIN_PASSWORD`).

---

## 2. Configuration

All settings are environment-driven; every one has a safe default:

| Env var | Default | Meaning |
|---------|---------|---------|
| `VALIDATION_BASE_URL` | `$REACT_APP_BACKEND_URL` or `http://localhost:8001` | Backend base URL |
| `VALIDATION_ADMIN_EMAIL` | `admin@strategy-factory.local` | Admin login |
| `VALIDATION_ADMIN_PASSWORD` | `admin123` | Admin password |
| `VALIDATION_TIMEOUT_S` | `30` | Per-probe HTTP timeout |
| `VALIDATION_SLOW_MS_WARN` | `2500` | Latency ≥ this ⇒ WARN |
| `VALIDATION_REPORTS_DIR` | `<repo>/infra/validation/reports` | Report output dir |
| `TIER5_DURATION_HOURS` | `24` | Tier 5 total duration |
| `TIER5_INTERVAL_SECONDS` | `300` | Tier 5 cadence between cycles |

---

## 3. How to run

### 3a. On the VPS (deployed environment)

```bash
# From the repository checkout root (the same dir where `git pull` runs).
cd /opt/strategy-factory       # adjust to your checkout path

# One-time: install runtime deps on the host Python (not in the container).
pip3 install -r infra/validation/requirements.txt

# Point at the deployed public URL and provide admin credentials.
export VALIDATION_BASE_URL="https://${FACTORY_DOMAIN}"
export VALIDATION_ADMIN_EMAIL="${ADMIN_EMAIL}"
export VALIDATION_ADMIN_PASSWORD="${ADMIN_PASSWORD}"

# Run the full suite once (recommended smoke check post-deploy).
python3 -m infra.validation.run_validation --full

# Or use the convenience launcher, which cd's to the repo root for you
# so it works no matter where you invoke it from:
./infra/validation/run.sh --full
```

### 3b. Local / preview environment

```bash
# From the repo root; base URL defaults to http://localhost:8001.
python3 -m infra.validation.run_validation
```

### 3c. All supported commands

```bash
# Default: run every module once, write reports, exit 0 if no FAILs.
python3 -m infra.validation.run_validation

# Explicit "full" run — equivalent to default.
python3 -m infra.validation.run_validation --full

# Single module (accepts either the alias or the full module name):
python3 -m infra.validation.run_validation --module health
python3 -m infra.validation.run_validation --module auth
python3 -m infra.validation.run_validation --module strategy
python3 -m infra.validation.run_validation --module portfolio
python3 -m infra.validation.run_validation --module propfirm
python3 -m infra.validation.run_validation --module market
python3 -m infra.validation.run_validation --module execution
python3 -m infra.validation.run_validation --module meta
python3 -m infra.validation.run_validation --module factory

# Print the last stored plain-text summary:
python3 -m infra.validation.run_validation --report-only

# Continuous run (Tier 5). Defaults: 24 h at 5-minute cadence.
python3 -m infra.validation.run_validation --tier5
python3 -m infra.validation.run_validation --tier5 \
    --tier5-hours 24 --tier5-interval-s 300
```

VPS example (background, 24-hour Tier 5):
```bash
cd /opt/strategy-factory
tmux new -d -s tier5 \
  "VALIDATION_BASE_URL=https://\${FACTORY_DOMAIN} \
   python3 -m infra.validation.run_validation \
     --tier5 --tier5-hours 24 --tier5-interval-s 300"
```

---

## 4. Report locations

Written under `VALIDATION_REPORTS_DIR`
(default `/app/infra/validation/reports/`):

| File | Purpose |
|------|---------|
| `validation_report.json` | Latest run — machine-readable payload |
| `validation_report.md` | Latest run — human-readable Markdown |
| `validation_summary.txt` | Latest run — plain-text one-page summary |
| `validation_report_<UTC>.{json,md}` | Timestamped run archives |
| `validation_summary_<UTC>.txt` | Timestamped plain-text archives |
| `tier5_metrics.json` | Tier 5 per-cycle metrics stream |
| `tier5_report.md` | Tier 5 Markdown roll-up (written at end) |

---

## 5. Expected PASS criteria

**Full suite** on a healthy Phase A–J backend (v1.2.0-alpha2):

| Module | Probes | Expected |
|--------|-------:|----------|
| `health` | 4 | all PASS |
| `authentication` | 3 | all PASS |
| `strategy_engineering` | 16 | all PASS |
| `portfolio` | 8 | all PASS |
| `propfirm` | 7 | all PASS |
| `market_intelligence` | 7 | all PASS |
| `execution_intelligence` | 11 | all PASS |
| `meta_learning` | 9 | all PASS (mode is `observe`) |
| `factory_evaluation` | 18 | all PASS (mode is `observe`) |
| **Total** | **83** | **PASS 83  FAIL 0  WARN 0** |

Grading rules applied by `modules/__init__.py::probe()`:
- HTTP status match (`expect` int / list / callable) → else FAIL
- `warn_on_status` codes → WARN not FAIL
- Optional `validate(response)` may downgrade to FAIL, or WARN if the string
  is prefixed with `warn:`
- Latency > `SLOW_MS_WARN` (default 2500 ms) → WARN

---

## 6. Interpreting failures

- **`FAIL` — unexpected HTTP N (expected …)**: the route either does not exist
  (404), is forbidden (403), or returned a server error (≥500). Reproduce with
  `curl` using the reported path + method. If a route was renamed, update the
  probe path in `infra/validation/modules/<module>.py` — the suite is
  intentionally kept in sync with the deployed router surface.
- **`FAIL` — validator raised / <custom message>**: body-shape assertion in the
  module’s `validate()` callback failed. The `detail` column names the exact
  violated invariant (e.g. `mode is 'recommend', expected 'observe'`).
- **`WARN` — slow: <ms> > 2500ms**: latency exceeded the threshold. Raise
  `VALIDATION_SLOW_MS_WARN` on cold cache runs, or investigate a slow handler.
- **`WARN` — unexpected HTTP <N> (warn-listed)**: expected transient state
  (e.g. `503` when a downstream broker/market feed is briefly unavailable).

---

## 6b. Troubleshooting invocation errors

- **`ModuleNotFoundError: No module named 'infra.validation'`**
  You are running from the wrong working directory (or from inside the
  backend container, which does not ship this suite). Fix:
  ```bash
  cd /opt/strategy-factory        # repo root, where `infra/` is visible
  python3 -m infra.validation.run_validation --full
  # …or use the launcher which cd's for you:
  ./infra/validation/run.sh --full
  ```

- **`ModuleNotFoundError: No module named 'requests'`**
  Install runtime deps on the host Python (not in the container):
  ```bash
  pip3 install -r infra/validation/requirements.txt
  ```

- **`[FATAL] authentication failed: login failed: HTTP 401`**
  The default admin credentials do not match the deployed environment.
  Export the correct ones before running:
  ```bash
  export VALIDATION_ADMIN_EMAIL="${ADMIN_EMAIL}"
  export VALIDATION_ADMIN_PASSWORD="${ADMIN_PASSWORD}"
  ```

- **`[FATAL] authentication failed: ConnectionError`**
  `VALIDATION_BASE_URL` is unreachable. Verify with:
  ```bash
  curl -fsS "${VALIDATION_BASE_URL}/api/health"
  ```
  On the VPS the deployed URL is `https://${FACTORY_DOMAIN}` via Traefik.

---

## 7. Exit codes

| Code | Meaning |
|-----:|---------|
| 0 | All probes PASS (or PASS + WARN only) — suite is green |
| 1 | At least one probe FAILed |
| 2 | Fatal setup failure (authentication failed, unknown module) |

Use in CI:
```bash
python -m infra.validation.run_validation || exit 1
```

---

## 8. What this suite is (and is not)

**It is**:
- A stateless surface / smoke validator against the deployed HTTP contract
- A continuous Tier 5 monitor when run with `--tier5`
- Fully idempotent — probes never mutate persisted business state beyond
  the transient strategy-engineering CRUD test (which cleans up after itself)

**It is not**:
- A replacement for the pytest regression suite (`backend/tests/`)
- A load / stress test — probes are single-shot, per-cycle
- A backend feature — it lives under `/app/infra/` and never modifies
  application code

Backend Feature Freeze (v1.2.0-alpha2) remains fully in effect.

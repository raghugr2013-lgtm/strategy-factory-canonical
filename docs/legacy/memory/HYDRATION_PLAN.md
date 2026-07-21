# HYDRATION_PLAN.md

**Plan type:** Strict pre-execution plan. No files modified. No services touched.
**Goal:** Reconstruct the canonical working codebase in `/app` from:
* `App.zip / App / backend/` → backend
* `Frontend.zip / src/` (+ root config files) → frontend
* `App.zip / App / memory/` → continuity/PRD/visual-approval
* `App.zip / App / _inventory/` → migration reference (read-only)

**State today:** `/app/backend` is an 88-line stub. `/app/frontend` is a default React scaffold. `/app/memory` contains the 5 audit docs already produced plus `test_credentials.md`.

---

## 1. Current vs canonical — at-a-glance delta

| Slice | Current `/app` | Canonical (zips) | Action |
|---|---|---|---|
| `backend/` | 88 LOC `server.py`, 27-line `requirements.txt`, no `auth_utils`, no engines, no API routers, no schedulers, `.env` has no `JWT_SECRET` / no `ADMIN_*` | App.zip — 543 .py files, 56 routers, 23 MB, 29-line `requirements.txt` with 10 critical deps (motor, pandas, dukascopy-python, APScheduler, pdfplumber, pypdf, reportlab, beautifulsoup4, lxml, pytest-asyncio, psutil) | **Overwrite contents.** Merge `.env`. |
| `frontend/` | default scaffold | Frontend.zip — 67 operator components, M0–M5 chrome, DSR-1 Symbol Registry UI, BI5 R1 Health panel, Phase 13/14/15 reservations, 3.2 MB | **Overwrite `src/`, `plugins/`, `public/`, `scripts/`, all config files.** Merge `.env`. |
| `memory/` | 5 audit docs + `test_credentials.md` | App.zip — `PRD.md`, `PROJECT_CONTINUITY_REPORT.md`, `visual_approval_package/` (12 docs + mockups) | **Add (do not overwrite audit docs).** |
| `data/` | absent | App.zip — `host_id` (8 KB) | Copy. |
| `tests/` | empty (`__init__.py`) | App.zip — `__init__.py` | No-op. |
| `test_reports/` | absent | App.zip — 7 `iteration_*.json` + `pytest/` | Copy. |
| `test_result.md` | absent | App.zip — 102 lines | Copy. |
| `yarn.lock` (root) | 86 B stub | App.zip — 86 B (identical placeholder) | No-op. |
| `_inventory/` | absent | App.zip — 190 MB (old1vcpu, app_extracted, frontend_extracted, asf_ui_handoff, screenshots) | **Operator decision** — see §6. |
| `.git/`, `.emergent/` | preserved | n/a | **Preserve as-is.** |

---

## 2. Exact hydration steps (proposed)

Each step is a single, idempotent, atomic operation. **Do not execute until operator authorises.**

### Phase H-0 — Pre-flight (read-only)

```bash
# 1. Snapshot current /app for instant rollback
mkdir -p /tmp/hydration_backup
cp -a /app/backend     /tmp/hydration_backup/backend.bak
cp -a /app/frontend    /tmp/hydration_backup/frontend.bak  # excludes node_modules
cp -a /app/memory      /tmp/hydration_backup/memory.bak
cp -a /app/.gitignore  /tmp/hydration_backup/gitignore.bak

# 2. Record current .env values (preserved verbatim across hydration)
cp /app/backend/.env  /tmp/hydration_backup/backend.env.preserve
cp /app/frontend/.env /tmp/hydration_backup/frontend.env.preserve
```

### Phase H-1 — Backend hydration

```bash
# 1. Wipe and replace
rm -rf /app/backend/*               # keeps the directory; removes pycache + stub
rm -rf /app/backend/.[^.]*          # any dotfiles inside (none expected)

# 2. Copy canonical backend from App.zip
cp -a /tmp/audit/app_zip/App/backend/. /app/backend/

# 3. Restore the operator-authorised .env (merge — see §5)
#    DO NOT overwrite with the zip's .env directly.
cp /tmp/hydration_backup/backend.env.preserve /app/backend/.env
#    Append the secrets that the canonical .env provides:
#      JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD
#      ENABLE_DYNAMIC_MARKET_UNIVERSE, ENABLE_CBOT_TRADE_PARITY,
#      ENABLE_HTF_PARITY_VALIDATION, ENABLE_HTF_PARITY_HARD_GATE,
#      ENABLE_TRADE_PARITY_HARD_GATE
#    (See §5 for the conflict-resolution recommendation.)

# 4. Install Python deps
cd /app/backend
pip install -r requirements.txt
```

### Phase H-2 — Frontend hydration

```bash
# 1. Wipe everything EXCEPT node_modules (saves ~5 minutes reinstall)
cd /app/frontend
find . -mindepth 1 -maxdepth 1 ! -name node_modules -exec rm -rf {} +

# 2. Copy canonical frontend from Frontend.zip
cp -a /tmp/audit/frontend_zip/. /app/frontend/
#    This brings: src/, public/, plugins/, scripts/, package.json,
#                 yarn.lock, craco.config.js, tailwind.config.js,
#                 postcss.config.js, jsconfig.json, components.json,
#                 README.md, .gitignore, .env.bak

# 3. Restore the operator pod's REACT_APP_BACKEND_URL
cp /tmp/hydration_backup/frontend.env.preserve /app/frontend/.env

# 4. Add one new dep, reuse existing node_modules
yarn install   # only adds @phosphor-icons/react ^2.1.10 (1 new dep)
```

### Phase H-3 — Memory & misc

```bash
# 1. Bring in PRD + continuity + visual approval package
cp /tmp/audit/app_zip/App/memory/PRD.md                          /app/memory/
cp /tmp/audit/app_zip/App/memory/PROJECT_CONTINUITY_REPORT.md    /app/memory/
cp -a /tmp/audit/app_zip/App/memory/visual_approval_package      /app/memory/

#  PRESERVE the 5 audit docs already in /app/memory/ — do NOT overwrite:
#    CODEBASE_RECONCILIATION.md
#    FEATURE_EXPOSURE_AUDIT.md
#    FEATURE_MAP.md
#    OPERATOR_MANUAL.md
#    ACTIVATION_MATRIX.md
#    test_credentials.md

# 2. Bring data/, test_reports/, test_result.md
cp -a /tmp/audit/app_zip/App/data/.         /app/data/
cp -a /tmp/audit/app_zip/App/test_reports/. /app/test_reports/
cp /tmp/audit/app_zip/App/test_result.md    /app/test_result.md

# 3. Merge .gitignore (zip has 1273 B, current has 953 B; zip is superset)
cp /tmp/audit/app_zip/App/.gitignore        /app/.gitignore
```

### Phase H-4 — Optional `_inventory/` (operator decision)

```bash
# Only run if operator explicitly approves (190 MB)
cp -a /tmp/audit/app_zip/App/_inventory     /app/_inventory
```

### Phase H-5 — Restart and validate

```bash
sudo supervisorctl restart backend
sudo supervisorctl restart frontend
sleep 8
# Then run §9 validation checklist
```

---

## 3. Expected directory structure AFTER hydration

```
/app
├── .emergent/                       (preserved — Emergent platform config)
├── .git/                            (preserved)
├── .gitignore                       (replaced — superset)
├── README.md                        (replaced from App.zip — 29 B)
├── backend/                         ← FROM App.zip / backend/
│   ├── .env                         (merged — pod values + zip secrets)
│   ├── Dockerfile
│   ├── PHASE1_COMPLETION_REPORT.md
│   ├── PHASE2_COMPLETION_REPORT.md
│   ├── PHASE2_5_SCHEMA_EXTENSION_REPORT.md
│   ├── PHASE3_COMPLETION_REPORT.md
│   ├── PHASE3_DESIGN.md
│   ├── api/                          (≈60 routers — diag_bi5_health, master_bot, admin_*, latent/*, …)
│   ├── auth_middleware.py
│   ├── auth_utils.py
│   ├── cbot_engine/                  (5 modules: generator, ir_*, transpiler, parity)
│   ├── config/                       (bi5_symbols.py, symbols.py)
│   ├── conftest.py
│   ├── data_engine/                  (BI5 + CSV + Dukascopy adapters, tick aggregators)
│   ├── engines/                      (≈170 engines incl. factory_supervisor/, persistence_adapters/, seed/)
│   ├── factory_runner.py             (sibling scheduler process — not auto-started)
│   ├── prop_firm_configs_example.json
│   ├── prop_firm_intelligence_example.json
│   ├── prop_firm_pdfs/               (5 sample PDFs, 220 KB)
│   ├── requirements.txt              (29 lines — pinned)
│   ├── scripts/                      (incl. bi5_one_shot_backfill.py — B-9)
│   ├── server.py                     (687 LOC, 56 routers wired)
│   ├── startup_validator.py
│   └── tests/                        (211 pytest files incl. test_bi5_r1, test_dsr1_schema, test_dsr2_scheduler)
├── data/
│   └── host_id                       (8 KB)
├── frontend/                        ← FROM Frontend.zip /
│   ├── .env                          (preserved — current pod URL)
│   ├── .env.bak
│   ├── .gitignore
│   ├── README.md
│   ├── components.json
│   ├── craco.config.js
│   ├── jsconfig.json
│   ├── node_modules/                 (preserved; `yarn install` adds @phosphor-icons/react)
│   ├── package.json                  (57 deps — adds @phosphor-icons/react ^2.1.10)
│   ├── plugins/health-check/
│   ├── postcss.config.js
│   ├── public/
│   ├── scripts/
│   ├── src/
│   │   ├── App.css
│   │   ├── App.js                    (wired to CommandShell + AuthGate)
│   │   ├── a11y/
│   │   ├── assets/
│   │   ├── command/
│   │   │   ├── reservations/         ← M2 cards (Phase 13/14/15 + Score + BrokerChips)
│   │   │   ├── shell/                ← CommandShell, TopTabBar, LifecycleRail, StatusRail, OperatorInboxDrawer, DangerRibbon, …
│   │   │   └── (BrandMark, CommandPreview, identity.css, motion.css, panels.css, premium.css, tokens.css, typography.css, …)
│   │   ├── components/               (67 operator components incl. SymbolRegistryPanel, BI5HealthPanel, ArchitectDashboard)
│   │   ├── constants/
│   │   ├── hooks/
│   │   ├── i18n/                     (en-US, de-DE)
│   │   ├── index.css
│   │   ├── index.js
│   │   ├── lib/
│   │   ├── pages/Welcome/            (empty — kept for layout)
│   │   ├── routes/
│   │   ├── services/                 (api · auth · phase9_api · throttledPost)
│   │   ├── stores/                   (theme · locale · notifications)
│   │   └── styles/                   (asf-design-tokens.css)
│   ├── tailwind.config.js
│   └── yarn.lock                     (11378 lines)
├── memory/
│   ├── ACTIVATION_MATRIX.md          (preserved — audit doc)
│   ├── CODEBASE_RECONCILIATION.md    (preserved — audit doc)
│   ├── FEATURE_EXPOSURE_AUDIT.md     (preserved — audit doc)
│   ├── FEATURE_MAP.md                (preserved — audit doc)
│   ├── HYDRATION_PLAN.md             (THIS DOC)
│   ├── OPERATOR_MANUAL.md            (preserved — audit doc)
│   ├── PRD.md                        ← NEW from App.zip
│   ├── PROJECT_CONTINUITY_REPORT.md  ← NEW from App.zip
│   ├── SYSTEM_READINESS_REPORT.md    (this audit pass)
│   ├── test_credentials.md           (preserved)
│   └── visual_approval_package/      ← NEW from App.zip (12 docs + mockups)
├── test_reports/
│   ├── iteration_1.json … iteration_7.json
│   └── pytest/
├── test_result.md
├── tests/
│   └── __init__.py
├── yarn.lock                         (root — 86 B placeholder, unchanged)
└── [optional] _inventory/            (190 MB — operator decision)
    ├── Frontend.zip                  (verbatim)
    ├── app_extracted/                (538 .py backend snapshot, older)
    ├── asf_ui_handoff/               (ASF_UI_Handoff_2026-06-08 package)
    ├── frontend_extracted/           (older frontend snapshot)
    ├── old1vcpu/                     (1-vCPU UI legacy)
    ├── old1vcpu_frontend.zip
    └── old_ui_screenshots*.docx
```

---

## 4. Files that would overwrite existing files

### 4.1 `/app/backend/` — wholesale replacement

| Current file | New file (App.zip) | Reason |
|---|---|---|
| `requirements.txt` (27 lines) | `requirements.txt` (29 lines, pinned) | New deps required (motor, pandas, dukascopy-python, APScheduler, pdfplumber, pypdf, reportlab, beautifulsoup4, lxml, pytest-asyncio, psutil); old deps unused (boto3, requests-oauthlib, cryptography, email-validator, pyjwt — replaced by `PyJWT==2.12.1`) |
| `server.py` (88 LOC stub) | `server.py` (687 LOC, 56 routers, 16 startup hooks) | Stub is non-functional |
| `__pycache__/` | (regenerated) | Compiled bytecode |

**New files added (all 540+):** every router, engine, data_engine adapter, cbot_engine module, config, tests/, scripts/, prop_firm_pdfs/, *.json examples, Dockerfile, phase reports, `factory_runner.py`, `startup_validator.py`, `auth_utils.py`, `auth_middleware.py`, `conftest.py`.

### 4.2 `/app/frontend/` — wholesale replacement (except `node_modules` and `.env`)

| Current file | New file (Frontend.zip) | Reason |
|---|---|---|
| `package.json` (56 deps) | `package.json` (57 deps; adds `@phosphor-icons/react` ^2.1.10) | New icon library used by M0–M5 chrome |
| `yarn.lock` | `yarn.lock` (11378 lines) | Matches the new package.json |
| `craco.config.js`, `tailwind.config.js`, `postcss.config.js`, `jsconfig.json`, `components.json` | replaced | Configured for design tokens, Tailwind theming, path aliases |
| `src/*` | wholesale replaced | (see §3) |
| `public/*` | replaced | New static assets |
| `plugins/health-check/` | replaced | Updated plugin |

### 4.3 `/app/memory/` — additive

| File | Source | Action |
|---|---|---|
| `PRD.md` | App.zip | **NEW** |
| `PROJECT_CONTINUITY_REPORT.md` | App.zip | **NEW** |
| `visual_approval_package/` | App.zip | **NEW** directory (12 docs + mockups/) |
| `CODEBASE_RECONCILIATION.md` … `ACTIVATION_MATRIX.md` (5 audit docs) | already present | **Preserve** |
| `test_credentials.md` | already present | **Preserve** (will be updated post-hydration with seeded admin creds — see §9) |

### 4.4 Root

| File | Action |
|---|---|
| `.gitignore` | Replace (zip is a superset) |
| `README.md` | Replace (zip is just 29 B) |
| `test_result.md` | Add (102 lines from zip) |
| `yarn.lock` | Identical 86 B placeholder, no-op |

---

## 5. Conflicts requiring operator decisions

### Conflict 5.1 — `backend/.env` flag activations

The canonical `App.zip / backend/.env` ships with these flags set:
```
ENABLE_DYNAMIC_MARKET_UNIVERSE=1     ← DSR-3 ON
ENABLE_CBOT_TRADE_PARITY=1           ← trade-parity simulator ON
ENABLE_HTF_PARITY_VALIDATION=1       ← HTF parity validator ON
ENABLE_HTF_PARITY_HARD_GATE=1        ← HTF parity required by cBot export hard gate
ENABLE_TRADE_PARITY_HARD_GATE=1      ← trade parity required by cBot export hard gate
```

The `engines/feature_flags.py` defaults are all OFF. This means the canonical operator who produced App.zip had **already approved these activations**. The `FEATURE_EXPOSURE_AUDIT.md` listed them as "F (dormant)" based on engine defaults — that classification flips to "active" once this `.env` is hydrated.

**Operator decision required (3 options):**

* **Option A — Honour the canonical decree.** Hydrate the `.env` as-is. DSR-3 active on first boot, both parity hard gates active.
* **Option B — Conservative restart.** Hydrate the secrets (`JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`) but leave the 5 ENABLE flags OFF for a fresh shadow-audit window, then flip after operator-approved soak.
* **Option C — Selective.** Honour `ENABLE_DYNAMIC_MARKET_UNIVERSE=1` (DSR is documented as a locked priority), keep parity hard gates OFF until cBot parity certification samples are reviewed.

**Recommendation:** **Option C.** Aligns with the locked roadmap priority (DSR first) and avoids untested hard-gates on cBot exports immediately after a cold pod with no parity sign-off history.

### Conflict 5.2 — `frontend/.env`

* Current pod: `REACT_APP_BACKEND_URL=https://strategy-factory-v1.preview.emergentagent.com`
* Frontend.zip ships: `REACT_APP_BACKEND_URL=https://strategy-factory-v1.preview.emergentagent.com`

**Operator decision required:** Which is the live preview URL? Default action is **keep current pod URL** (the zips contain stale environment-specific URLs). This is also the documented platform rule.

### Conflict 5.3 — `_inventory/` (190 MB)

Hydrating `_inventory/` brings the 1-vCPU migration trail and the screenshots/asf_ui_handoff package, which the upcoming `MIGRATION_*` docs will rely on. But it costs 190 MB of pod disk.

**Operator decision required:**
* **Option A — Hydrate fully.** Useful for the upcoming migration phase.
* **Option B — Skip.** Reference from `/tmp/audit/app_zip/App/_inventory/` on demand; saves disk; loses portability.
* **Option C — Hydrate a slice.** Bring only `asf_ui_handoff/` (12 docs) + `old1vcpu/src/` (50 components) — drop the zips and screenshots. Reduces to ≈3 MB.

**Recommendation:** **Option C** — preserves operational value at minimal cost.

### Conflict 5.4 — `requirements.txt` deps to drop

Current `/app/backend/requirements.txt` has these unused-in-canonical deps:
```
boto3>=1.34.129
requests-oauthlib>=2.0.0
cryptography>=42.0.8
email-validator>=2.2.0
pyjwt>=2.10.1        ← name collision with canonical PyJWT==2.12.1
```

**Recommendation:** Use the canonical `requirements.txt` verbatim; `pip install -r requirements.txt` will install the canonical set. Stale modules in `site-packages` are harmless until `pip freeze` is regenerated; the canonical file is the source of truth.

### Conflict 5.5 — Existing `node_modules`

The current `node_modules/` was installed against the stub `package.json` (56 deps). After hydration, `yarn install` will:
* Install `@phosphor-icons/react` (1 new dep)
* Possibly bump some transitive versions if `yarn.lock` resolution drifts
* Take ≈30 s if cached, ≈3 min if cold

**Recommendation:** Keep existing `node_modules/`, run `yarn install --frozen-lockfile`. If anything misbehaves at startup, fall back to full reinstall.

### Conflict 5.6 — `.emergent/emergent.yml`

`/app/.emergent/` exists and is preserved. **Verify after hydration** that `emergent.yml` still binds frontend to port 3000 and backend to 8001 (the Kubernetes ingress contract). The zips do NOT carry `.emergent/`.

---

## 6. Files NEWER in Frontend.zip than in App.zip's `_inventory/frontend_extracted/`

Already enumerated in `CODEBASE_RECONCILIATION.md §3.2`. Repeated here for the hydration plan:

| Newer file | Purpose | M-milestone |
|---|---|---|
| `command/shell/TopTabBar.jsx` (160 LOC) | Top tab navigation | M0 |
| `command/shell/LifecycleRail.jsx` (166 LOC) | Operator lifecycle timeline | M1 |
| `command/shell/OperatorInboxDrawer.jsx` (255 LOC) + `inboxEvents.js` (129 LOC) | Operator Inbox | M4 |
| `command/shell/DangerRibbon.jsx` (56 LOC) + `DangerRibbon.css` | Emergency banner | M4/M5 |
| `command/reservations/Phase13ReservationsCard.jsx` | Strategy Dossier placeholder | M2 / Phase 13 |
| `command/reservations/Phase14DualScorecardCard.jsx` | Auto Valuation placeholder | M2 / Phase 14 |
| `command/reservations/Phase15MarketplaceReservation.jsx` | Marketplace placeholder | M2 / Phase 15 |
| `command/reservations/StrategyScoreReservationCard.jsx` | Score architecture placeholder | M3 |
| `command/reservations/ExecutionBrokerChips.jsx` | Broker chip row | M2 |
| `command/reservations/reservations.css` | Shared reservation styles | M2 |
| `components/SymbolRegistryPanel.jsx` (601 LOC) + `.css` | DSR-1 UI | DSR-1 |
| `components/BI5HealthPanel.jsx` (249 LOC) + `.css` | BI5 R1 health panel | BI5 R1 |
| `command/shell/modulesRegistry.js` (355 LOC, up from 318) | adds DSR + BI5 + reservation mounts | M2/M3/DSR-1/BI5 R1 |
| `command/shell/CommandShell.jsx` | mounts TopTabBar + LifecycleRail + DangerRibbon + OperatorInboxDrawer | M0-M5 |
| `command/shell/CommandBar.jsx`, `CommandPalette.jsx`, `shell.css` | M0–M5 alignment | M0-M5 |
| `styles/asf-design-tokens.css` | refined tokens | M5 |

**Removed in Frontend.zip vs older snapshot** (intentional — visual approval `11_THEMETOGGLE_REMOVAL.md`):
* `components/ThemeToggle.js`
* `hooks/useTheme.js`
* `styles/asf-rc1-light-overrides.css`

---

## 7. Estimated time

| Phase | Duration |
|---|---|
| H-0 Pre-flight snapshot | 30 s |
| H-1 Backend file copy | 1 min |
| H-1 `pip install -r requirements.txt` | 3–5 min (cold install; faster if pip cache warm) |
| H-2 Frontend file copy | 30 s |
| H-2 `yarn install --frozen-lockfile` | 30 s – 3 min |
| H-3 Memory/data copy | 15 s |
| H-4 Optional `_inventory/` (Option C slice) | 30 s |
| H-5 Supervisor restart + boot | 30 s |
| Validation (§9) | 3–5 min manual |
| **Total** | **≈10–15 minutes** end-to-end |

If `_inventory/` Option A is chosen, add 20–40 s file copy + 190 MB disk usage.

---

## 8. Risks & mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `requirements.txt` install fails (network / pinned version yank) | Low | High (backend won't boot) | H-0 snapshot enables rollback; alternative: install one missing dep manually |
| `yarn install` resolves a transitive dep to a breaking version | Low | Medium (UI compile errors) | Run with `--frozen-lockfile`; if it fails, full reinstall |
| `.env` flag activations cause early errors before hydration finishes | Medium | Medium | Default to Option C (selective) — only DSR-3 active |
| Existing pod has uncommitted operator notes outside the 5 audit docs | Low | Low | H-0 snapshot covers all of `/app/memory/` |
| Live preview URL mismatch between zip and pod | High | High (frontend can't reach backend) | Always preserve current `/app/frontend/.env` |
| Schedulers immediately start hitting Mongo (no data yet) | Medium | Low (idempotent — just empty queries) | Acceptable; first cycle will report zero |
| `factory_runner.py` accidentally launched by supervisor | Low | Medium | The `.emergent/emergent.yml` does not reference `factory_runner.py`; verify before restart |
| The activated parity hard gates (Option A only) block all cBot exports | High under Option A | High | Choose Option B/C to avoid |
| Mongo `market_universe_symbols` seed runs but registry has no rows yet under DSR-3 ON | High | High (ingestion would narrow) | The startup hook unconditionally seeds 7 canonical symbols — safe |

---

## 9. Post-hydration validation checklist

### 9.1 Backend health (curl)

```bash
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2)

# Liveness
curl -s "$API/api/health"
# expect: {"status":"ok","service":"AI Strategy Factory"}

# Login + token
TOKEN=$(curl -s -X POST "$API/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@strategyfactory.dev\",\"password\":\"<ADMIN_PASSWORD>\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")

# Feature flag manifest
curl -s "$API/api/latent/feature-flags" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40

# Market universe registry (DSR)
curl -s "$API/api/latent/market-universe" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30

# BI5 health
curl -s "$API/api/diag/bi5/health" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -30

# Readiness
curl -s "$API/api/latent/deployment-readiness" -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -40

# Orchestrator heartbeat (StatusRail consumes this)
curl -s "$API/api/orchestrator/heartbeat" -H "Authorization: Bearer $TOKEN"

# Monitoring status (StatusRail / NotificationDrawer)
curl -s "$API/api/monitoring/status" -H "Authorization: Bearer $TOKEN"
```

### 9.2 Backend boot log expectations

`tail -n 200 /var/log/supervisor/backend.*.log` should contain:

- `[startup] mongo indexes — created=… existed=… errors=0`
- `[startup] market_universe seed — inserted=7 refreshed=0 skipped=0 errors=0` (first boot) OR `inserted=0 refreshed=7` (re-boot)
- `[startup] market_universe adapter cache — loaded=7 errors=0` (only if `ENABLE_DYNAMIC_MARKET_UNIVERSE=1`)
- `[startup] host_capability detected — host_id=… profile=…`
- `[startup] mongo indexes` for: admission, scaling_events, factory_supervisor, scaling, mb9
- `[feature_flags] N/M flags overridden — active: …` (lists the flags chosen in §5.1)
- `[startup] fs worker_scheduler — started=false …` (because `FS_ENABLE_WORKER_SCHEDULER=false` per the canonical .env)
- `admin seed failed` should NOT appear; `_seed_admin_user` should log nothing on success.
- No `validate_startup_env failed` (means `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` are present).

### 9.3 Frontend health

1. Load `https://<pod-host>/` → expect AuthGate.
2. Log in with seeded admin credentials.
3. Observe CommandShell renders with:
   * **TopTabBar** visible above CommandBar
   * **LifecycleRail** visible at the top of the module surface
   * **StatusRail** at bottom (orchestrator + LLM + ingestion chips)
   * **LeftRail** with 10 module glyphs
4. Click each of the 10 modules — each module surface should render without console errors.
5. Open `/c/diag/bi5-health` → BI5HealthPanel mounts; `GET /api/diag/bi5/health` succeeds.
6. Open `/c/governance/symbol-registry` → SymbolRegistryPanel mounts; lists at least the 7 seeded symbols.
7. Open the Phase 13/14/15 reservation cards in Explorer/Portfolio — should render as placeholders.
8. ⌘K → palette opens. ⌘. → inspector opens. ⌘J → copilot opens (advisory_only).
9. Switch posture by resizing the window → tablet sections drop, briefing reduces UI.

### 9.4 Specific feature verifications

| Check | Where | Expected |
|---|---|---|
| **JWT auth** | Login → Inspector pane → "Self" tab | Shows logged-in user; tokens issued |
| **DSR-1 CRUD** | `/c/governance/symbol-registry` | List shows seeded 7 symbols; can add a test row (`TESTSYM`); can toggle enable; can delete |
| **DSR-3 consumption** (only if flag ON) | Backend log on next scheduler tick | `[auto-maintenance] iterating over N ingestion-eligible symbols` where N = enabled count in registry |
| **BI5 R1 health endpoint** | `GET /api/diag/bi5/health` | Returns `{ rows: [...], summary: {...} }` |
| **BI5 R1 panel** | `/c/diag/bi5-health` | Sortable table renders; status pills appear |
| **BI5 R1 backfill** | `python -m scripts.bi5_one_shot_backfill EURUSD` | Reports `Inserted: …  Skipped (already seen): …  Errors: 0` |
| **Factory Supervisor dormancy** | `GET /api/latent/feature-flags` | `ENABLE_FACTORY_SUPERVISOR=false`, all `FS_ENABLE_*=false` |
| **Master Bot CRUD** | `/c/mutate/master-bot` | Dashboard renders; no compile errors |
| **Pipeline logs** | `/c/diag/pipeline` | Returns most recent log rows |
| **Operator Inbox** | Bell icon → drawer | Drawer opens; shows U-3 welcome row |
| **Copilot panel** | ⌘J | Opens; reads orchestrator heartbeat |

### 9.5 Update `/app/memory/test_credentials.md`

Post-hydration, write the seeded admin credentials (from `.env`) into:
```
/app/memory/test_credentials.md
```

So the testing subagent (and future operators) can authenticate without re-deriving from `.env`.

---

## 10. Rollback procedure

If validation fails irrecoverably:

```bash
sudo supervisorctl stop backend frontend
rm -rf /app/backend /app/frontend
cp -a /tmp/hydration_backup/backend.bak  /app/backend
cp -a /tmp/hydration_backup/frontend.bak /app/frontend
cp /tmp/hydration_backup/backend.env.preserve  /app/backend/.env
cp /tmp/hydration_backup/frontend.env.preserve /app/frontend/.env
# Keep node_modules from the backup (it pre-dated hydration anyway)
sudo supervisorctl start backend frontend
```

If `node_modules` was modified destructively, also:
```bash
cd /app/frontend
rm -rf node_modules
yarn install
```

---

## 11. Authorization gate

This plan is **inactive** until the operator confirms:

1. **§5.1 .env flag activation** — Option A / B / **C (recommended)**
2. **§5.3 `_inventory/`** — Option A / B / **C (recommended)**
3. **§5.2 `frontend/.env`** — confirm pod URL `autonomous-lab-1.preview.emergentagent.com` is correct
4. Any additional pre-flight steps

Upon `EXECUTE` authorization the steps in §2 will be run in order, with the validation checklist in §9 as the success gate.

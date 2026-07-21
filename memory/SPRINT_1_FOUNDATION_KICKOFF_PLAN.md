# Sprint 1 Foundation — Kickoff Plan

> **Status:** DRAFT — awaiting operator "go" to begin implementation.
> **Prepared:** 2026-07-21.
> **Authority:** `memory/D8_SPRINT_1_EXECUTION_PLAN.md` (execution architecture) + `memory/DESIGN_FREEZE_v1.0.md` (binding design contract).
> **Backend Feature Freeze:** in effect (v1.1.0-stage4). Sprint 1 is a frontend-only stream.
> **Target codebase:** `/app/frontend/**` (production React CRA). Prototype `/app/prototype/**` remains throw-away reference only.

---

## 1. Sprint 1 mandate

**Deliver the Foundation phase of the frozen operator frontend design** — the architectural skeleton and the three highest-leverage surfaces — against the v1.1.0-stage4 backend, on production build tooling, with the frozen `data-testid` registry preserved as the CI-enforced acceptance contract.

Sprint 1 explicitly does **not** ship every surface. Per D8 §2, Foundation covers what an operator needs to answer the six operator questions on their first shift; every deferred surface has a scheduled sprint in D8 §2.2.

## 2. Milestones (five phases · six calendar weeks recommended)

| M# | Milestone | Days | Deliverables | Exit gate |
|---|---|---:|---|---|
| **M1** | Foundation infrastructure | 11 | Design tokens (I5) · fonts (I6) · Workspace state store (I1) · URL scheme + routing (I2) · State Memory infra (I3) · AppShell (I4) · Mode switcher (I7) · ⌘K palette (I8) · Danger ribbon (I9) · Status rail (I10) | AppShell renders empty with all chrome active; mode switch works with 200ms crossfade; ⌘K palette opens and lists routes; keyboard walkthrough documented for shell |
| **M2** | Primitive library | 15 | 15 primitives (P1–P15) implemented against frozen contracts + Storybook stories (T1) + axe-core CI integration (T3) | ≥ 60 Storybook stories; axe-core 0 violations across all primitive stories; visual-regression baseline (T4) captured |
| **M3** | Feature machinery | 9 | FacetBar (F1) · TimeWindowChip (F2) · Optimistic-UI middleware (F3) · Timeline adapter (F4) · Approvals adapter (F5) · Factory adapter (F6) · Mission Control aggregator (F7) | Adapters return fixtures under Freeze mode; adapters wire against `/api/**` when `REACT_APP_BACKEND_URL` set; optimistic-UI rollback test passes |
| **M4** | Foundation surfaces | 15 | Mission Control (S1) · AI Activity Timeline (S2) · Approval Center (S3) · Attention panel severity (S7) · Empty states (S6) · Master Bot Dashboard skeleton (S4) · Strategy Explorer minimal (S5) | Every surface passes acceptance criteria (D8 §6); Playwright morning-routine journey passes end-to-end; 60 screenshots archived (4 modes × 3 postures × 5 surfaces) |
| **M5** | Integration + polish | 10 | Real-auth wiring against v1.1.0-stage4 backend · Playwright E2E harness (T2) · reduced-motion audit (T5) · keyboard walkthrough automation (T6) · CI-enforced testid presence check | All Sprint 1 exit criteria per D8 §14 satisfied; ≥ 115 Storybook stories; ≥ 60 archived screenshots; zero backend commits during Sprint 1 |

**Total:** 60 engineer-days at solo cadence; D8 recommends a 3-sprint (6-week) stretch with a small team for craftsmanship.

## 3. Milestone dependencies (topological order)

```
M1 (Foundation infra)
    │
    ├──> M2 (Primitives) ─── depends on I5 tokens + I1 store
    │
    └──> M3 (Feature machinery) ─── depends on I1 store + I2 routing
                │
                └──> M4 (Surfaces) ─── depends on M2 + M3
                            │
                            └──> M5 (Integration + polish) ─── depends on M4 + M1 (real-auth)
```

**Strict topological execution.** No M4 surface may build before M3 adapters exist. No M3 adapter may build before M1 store exists.

## 4. Phase-by-phase deliverables (detailed)

### M1 · Foundation infrastructure (Days 1–11)

**Objective:** deliver the persistent chrome and every store/route primitive that every feature depends on. When M1 exits, the AppShell renders with all six surfaces stubbed to "coming next milestone" `<StateTemplate>` empties.

| Item | Ref (Freeze §) | Ref (D8 §) | Effort |
|---|---|---|---:|
| I5 · Design tokens (`tokens.css` in prod codebase) | §1.7 tokens | §3.4 · §4.I | 2 d |
| I6 · Font loading + `@font-face` (system-font fallback per P0 §6) | §2.1 typeface deferral | §4.I | 1 d |
| I1 · Workspace state store (mode · advanced_lens · density · time_window · facets · pins) | §1.5 shared facet plane | §3.1 · §4.I | 4 d |
| I2 · URL scheme + routing + CNL payload | §1.5 return-crumb | §3.3 · §4.I | 3 d |
| I3 · State Memory infra (per-pathname session-storage slice) | §1.2 principle E5 | §3.2 · §4.I | 2 d |
| I4 · AppShell + persistent chrome | §1.4 surface Login + Mission Control shell | §3.5 · §4.I | 4 d |
| I7 · Mode switcher + Advanced Lens toggle | §1.2 principles | §4.I | 3 d |
| I8 · ⌘K palette (Sprint 1 subset — jump-to-surface, focus by strategy-id, open Approval Center) | §2.1 deferred → resolved | Bible §7.10 · §4.I | 4 d |
| I9 · Danger ribbon | §1.5 danger ribbon | Bible §14.2 · §4.I | 2 d |
| I10 · Status rail (6 chips) | §1.5 (P·W·F·A·I taxonomy) | Bible §7.6 · §4.I | 3 d |

**Exit gate for M1:**
- Empty AppShell renders with LeftRail · TopTabBar · Header · StatusRail · RightRail (empty until M4)
- ⌘K opens and lists all Sprint 1 routes
- Mode switch triggers 200 ms crossfade + full Decision Identity preservation
- URL scheme survives page reload
- State Memory smoke test passes on a stub surface

### M2 · Primitive library (Days 12–26)

**Objective:** every one of the 15 primitives from Design Freeze §1.3 available with props identical to the prototype's contract, backed by Storybook stories and axe-core clean.

**Primitives (Freeze §1.3):**
`Chip (P1)` · `MetricBlock (P2)` · `ChartTile (P3)` · `TableTile (P4)` · `PipelineStageBar (P5)` · `ActivityRow (P6)` · `WorkerCard (P7)` · `StateTemplate (P8)` · `ApprovalCard (P9)` · `EvidenceDrawer (P10)` · `LineageBar (P11)` · `ProvenanceTriple (P12)` · `SignatureFrame (P13)` · `DivisionCaption (P14)` · `KeyboardShortcut HUD (P15)`.

**Storybook targets (D8 §8):** ≥ 60 stories at M2 exit; final target ≥ 115 stories at M5 exit.

**Exit gate for M2:**
- Every primitive has ≥ 3 Storybook stories covering happy + empty + loading (D8 §8)
- axe-core CI is 0 violations across all primitive stories
- Visual regression baseline captured (D8 §T4)
- Every primitive respects `prefers-reduced-motion`
- Every primitive uses only tokens from `tokens.css` (Stylelint rule enforced)

### M3 · Feature machinery (Days 27–35)

**Objective:** shared machinery (FacetBar · TimeWindowChip · Optimistic-UI middleware) plus the three module adapters that bridge the frozen surface contracts to the v1.1.0-stage4 backend.

| Item | Sprint 1 backend surface |
|---|---|
| Timeline adapter (F4) | Read from `/api/llm-calls/*` + `/api/ai-workforce/*` |
| Approvals adapter (F5) | Read from `/api/meta-learning/recommendations` + `/api/factory-eval/recommendations`. Approve endpoints return 409 (OBSERVE mode) per PRD; UI shows read-only queue for Sprint 1. |
| Factory adapter (F6) | Read from `/api/coe/state` + `/api/health/system` + Master Bot status endpoints |

**Exit gate for M3:**
- Adapters return **fixtures** when `REACT_APP_BACKEND_URL` is absent (falls back to prototype-parity fixtures for Storybook)
- Adapters return **live data** when `REACT_APP_BACKEND_URL` is set + user is authenticated
- Optimistic-UI rollback test passes: force adapter error, verify UI rolls back to pre-action state and surfaces the error via `<StateTemplate variant="error">`

### M4 · Foundation surfaces (Days 36–50)

**Objective:** the three Foundation surfaces (Mission Control · Timeline · Approvals) render end-to-end with real data, plus skeleton surfaces for Master Bot and Explorer.

| Surface | State at M4 exit |
|---|---|
| Mission Control (S1) | Six panels answer the six operator questions with live data; Attention panel severity-ordered (S7); all empty states from D7 specimens |
| AI Activity Timeline (S2) | Right rail streams live events (polling; WebSocket deferred to Sprint 2) |
| Approval Center (S3) | Unified queue reads Meta-Learning + Factory-Eval + governance advisory; approve/defer/block optimistic + rollback path tested (409 in Sprint 1 by design) |
| Master Bot Dashboard skeleton (S4) | Identity strip + current plan (simple mode) + last decisions log |
| Strategy Explorer minimal (S5) | Sortable table + inline actions + evidence chips (origin · learning_only · trust_tier) |

**Exit gate for M4:**
- Playwright morning-routine journey passes end-to-end (login → glance → approve read-only → investigate → sign off)
- 60 screenshots archived (4 modes × 3 postures × 5 surfaces = visual-regression baseline)
- Every non-happy state uses `<StateTemplate>` (no ad-hoc empty markup — CI rule enforced)

### M5 · Integration + polish (Days 51–60)

**Objective:** real-auth wiring, full test suite, and Sprint 1 exit-criteria satisfaction per D8 §14.

| Item | Deliverable |
|---|---|
| Real-auth wiring | Login → `POST /api/auth/login` → JWT stored per `frontend/src/services/auth.js` conventions; RequireAuth guard replaces prototype's in-memory auth store |
| Playwright E2E harness (T2) | Morning-routine journey + at least one non-happy state per surface |
| Reduced-motion audit (T5) | Every animation respects `prefers-reduced-motion`; motion-off screenshots captured |
| Keyboard walkthrough automation (T6) | Every surface reachable + operable via keyboard only |
| CI testid presence check | Custom lint rule that fails CI if any interactive element from the frozen registry lacks its `data-testid` |
| Freeze audit | Every Sprint 1 PR title cites its D-doc reference per D8 §9.1; automated PR-title check in CI |

**Exit gate for M5 (= Sprint 1 exit per D8 §14):**
- Every §4 D8 item shipped to acceptance (§6)
- Mission Control renders end-to-end for Operations persona with real backend data
- Timeline streams live events in right rail
- Approvals unified queue works (read-only in Sprint 1 due to backend OBSERVE mode)
- Master Bot Dashboard skeleton shows identity + current plan + last decisions log
- Strategy Explorer lists strategies with inline actions
- Mode switcher toggles between 4 modes with 200 ms crossfade + Decision Identity + Context Never Lost + State Memory
- ⌘K palette navigates every route + fires actions
- Danger ribbon fires on kill-posture arm
- Every empty state matches its D7 specimen
- axe-core CI passes on every surface
- Storybook has ≥ 115 stories
- Playwright morning-routine passes
- Screenshots archived (60 frames)
- **Design-doc PR-title convention respected on 100 % of PRs**
- **Backend Feature Freeze verified — zero backend commits during Sprint 1**

## 5. Estimated phases summary

| Phase | Milestones | Days | Calendar weeks (solo) | Calendar weeks (2-eng team) |
|---|---|---:|---:|---:|
| Foundation infrastructure | M1 | 11 | 2.2 | 1.5 |
| Primitive library | M2 | 15 | 3.0 | 2.0 |
| Feature machinery | M3 | 9 | 1.8 | 1.2 |
| Foundation surfaces | M4 | 15 | 3.0 | 2.0 |
| Integration + polish | M5 | 10 | 2.0 | 1.5 |
| **Total** | **M1–M5** | **60** | **12** | **8** |

D8 recommends **3-sprint (6-week) stretch with a 2-engineer team** for craftsmanship.

## 6. Dependencies external to Sprint 1

| Dependency | Owner | When needed | Freeze impact |
|---|---|---|---|
| **`.env` populated in `/app/backend/.env` and `/app/frontend/.env`** | Operator | Before M5 real-auth wiring | None; backend is dormant until env is populated |
| **v1.1.0-stage4 backend deployed on pod** | Ops | Before M3 adapters run against live data | None; adapters fallback to fixtures |
| **Test operator account** (`admin@coinnike.com` or equivalent) | Ops | Before M5 real-auth wiring | None |
| **Typefaces licensed and available** (Berkeley Mono · Neue Haas · GT Sectra) | Operator | Before final Sprint 1 QA | Freeze §2.1 permits system-font fallback if unavailable |
| **CI infrastructure** (GitHub Actions or equivalent) | Ops | Before M2 axe-core integration | None if CI infra pre-exists |
| **Coherent UKIE Activation Phase A** on VPS (parallel track) | Operator | Independent of Sprint 1 | No Sprint 1 dependency; activation feeds later sprints |

## 7. Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Sprint 1 scope exceeds capacity (146 engineer-days total per D8 §4.X) | Timeline slip | D8 recommends 3-sprint stretch; kickoff scope can be reduced per D8 §4.X Options B/C |
| R2 | Backend endpoints for adapters not yet wired for OBSERVE-mode UI reads | M3/M4 slip | Adapters gracefully fall back to fixtures; UI shows read-only queue for approvals |
| R3 | Testid drift between prototype and production during rebuild | Freeze §1.6 violation | CI-enforced testid presence check (M5) rejects violations |
| R4 | Design-doc references drift out of sync during rebuild | Freeze §4 rule 3 violation | PR-title convention + automated check enforce reference on every PR |
| R5 | Real-auth wiring surfaces v1.1.0-stage4 backend bug | Freeze v backend Freeze conflict | Backend Feature Freeze §7 permits bug fixes without lifting freeze |
| R6 | Typefaces not available in time for Sprint 1 QA | Freeze §2.1 fallback becomes de facto ship state | Non-blocking; Freeze §2.1 explicitly permits system-font fallback with README annotation |

## 8. Sprint 1 acceptance summary (from D8 §14)

Sprint 1 is **DONE** when every checkbox below is green:

- [ ] Every §4 D8 item shipped to acceptance (§6)
- [ ] Mission Control renders end-to-end for the Operations persona with real backend data
- [ ] Timeline streams live events in the right rail
- [ ] Approvals unified queue works (approve/defer/deny round-trip; 409 acknowledgment in OBSERVE mode)
- [ ] Master Bot Dashboard skeleton shows identity + current plan + last decisions log
- [ ] Strategy Explorer lists strategies with inline actions
- [ ] Mode switcher toggles between 4 modes with 200 ms crossfade + full Decision Identity + full Context Never Lost + full State Memory
- [ ] ⌘K palette navigates every route + fires actions
- [ ] Danger ribbon fires on kill-posture arm
- [ ] Every empty state matches its D7 specimen
- [ ] axe-core CI passes on every surface
- [ ] Storybook has ≥ 115 stories
- [ ] Playwright morning-routine journey passes
- [ ] Screenshots archived (4 modes × 3 postures × 5 surfaces = 60 frames · visual-regression baseline)
- [ ] Design-doc PR-title convention respected on 100 % of PRs landed
- [ ] **Backend Feature Freeze verified — zero backend commits during Sprint 1**

## 9. What happens after Sprint 1

Per D8 §2.2, Sprint 2+ covers:

- Sprint 2: Lineage Graph mode · Pinned Preview · Full Master Bot Plan Contract with HITL cross-links · Full Workforce Org Chart · Chart drill-through table drawer
- Sprint 3: Copilot trace-as-UI · G3 Knowledge Graph · G5 Execution Constellation · G7 Learning Evolution Timeline · Executive Briefing surface · Research Workspace surface · Multi-user mode assignment UI
- Sprint 4: G6 Portfolio Risk Surface
- Sprint N+: Factory Replay full experience

Real-time WebSocket telemetry, multi-monitor briefing wall, custom cursor — all Sprint 2+.

## 10. Kickoff meeting agenda (recommended)

Before Day 1 of M1, run a 30-minute kickoff:

1. Confirm operator, engineering lead, and design steward are aligned on Freeze §4 operational rules.
2. Confirm `.env` files are populated on both dev workspace and CI.
3. Confirm v1.1.0-stage4 backend is deployed + healthy in the target pod.
4. Confirm Storybook + Playwright + axe-core + Stylelint tooling is present in `/app/frontend`; scaffold if missing.
5. Confirm typefaces status (procured or system-font fallback acknowledged).
6. Confirm PR-title-convention + testid-presence CI checks are ready to go on Day 1.
7. Ratify the 6-week / 60-engineer-day / 5-milestone plan below.
8. Assign M1 owners.

## 11. Awaiting operator "go"

This is a plan document. No production code will be written until the operator explicitly authorises Sprint 1 kickoff. Once authorised, M1 Day 1 begins immediately.

---

*End of Sprint 1 Foundation Kickoff Plan.*

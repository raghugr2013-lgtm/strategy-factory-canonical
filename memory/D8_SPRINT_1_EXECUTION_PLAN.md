# D8 — Sprint 1 Detailed Execution Plan

> The bridge document. Turns the completed D-series design system into
> a Sprint 1 engineering plan without changing a single design rule.
>
> D8 is authoritative on **what to build first**, **in what order**,
> **against which design references**, and **under what acceptance
> criteria**. It is not a design document; it is the design-to-code
> contract.
>
> Layered on **Bible v2.1** (`FRONTEND_DESIGN_BIBLE_V2_1.md`). Every
> item cites its governing design reference. Every acceptance criterion
> derives from a rule elsewhere in the D-series.
>
> Prepared 2026-07-20. Final D-series deliverable.

---

## 0. Design Principles Checklist (18 items — permanent quality gate)

D8 confirms:

- [x] **Invisible Luxury** — the plan prioritises craftsmanship primitives (State Template · Facet Bar · Signature Frame) before flashy features.
- [x] **Everything Connected** — every Sprint 1 surface exposes lineage links; the Lineage Graph mode (§10.2) is a Sprint 2 non-goal, but its architectural reservations are honoured in Sprint 1.
- [x] **Progressive Disclosure** — Advanced Lens ships in Sprint 1 as a system-wide toggle; per-surface Advanced chips ship together with their surfaces.
- [x] **Evidence First** — no metric-block ships without its evidence link; enforced by acceptance criterion.
- [x] **Persona Awareness** — modes ship in Sprint 1 as a switcher + shell chrome effect; per-mode landing surfaces beyond Mission Control are Sprint 2+.
- [x] **Mission Control First** — Mission Control is the Sprint 1 hero surface; everything else exists to support it.
- [x] **Accessibility (WCAG 2.2 AA)** — a11y is a Sprint 1 acceptance criterion per component, not a Sprint 2 sweep.
- [x] **Motion Discipline** — motion budget enforced by design tokens + `prefers-reduced-motion` handling shipped in Sprint 1 foundations.
- [x] **Design Token Compliance** — token file (`tokens.css`) is a Sprint 1 Day 1 deliverable.
- [x] **Six-Signal Rule** — enforced by token file; no additional hues in Sprint 1.
- [x] **Lineage Validation** — Lineage bar ships in Sprint 1 (one hop up + one hop down); full Graph mode is Sprint 2.
- [x] **Empty-State Quality** — every Sprint 1 surface ships with its authored states from D7.
- [x] **Consistency** — State Template, Signature Frame, Facet Bar, Time-window chip all ship Sprint 1 as shared components.
- [x] **Explainability** — every plan item cites its design reference; no orphaned components.
- [x] **Storytelling Copy Standard (D2 Addendum)** — every visible surface passes copy review against D2 + D7 specimens before ship.
- [x] **Context Never Lost (Bible §1.4.4)** — workspace state store is a Sprint 1 architectural foundation (§3.1).
- [x] **State Memory (Bible §1.4.5)** — per-surface session-storage slice pattern is a Sprint 1 foundation (§3.2).
- [x] **Purpose Before Status (D4 §5.1.1)** — every card renders purpose above state.
- [x] **Decision Identity (D6 §8.1a)** — components accept canonical objects; mode-conditional rendering only at presentation layer.

---

## 1. Purpose of D8

D8 exists so that engineering can begin Sprint 1 **without a single
open design question**. Every choice — component boundary, order of
work, dependency, acceptance bar, test scope — is authored here and
cross-linked to its D-doc reference.

**Anti-goals** (what D8 must not become):

- A technology-selection document (React / state store / bundler
  choices belong to `FRONTEND_TECHNICAL_STANDARDS.md`, out of scope).
- A ticket queue (engineering can generate tickets from §4).
- A roadmap beyond Sprint 1 (Sprint 2+ appears only as *non-goals*).
- A backend spec (Feature Freeze — no backend work in Sprint 1).

---

## 2. Sprint 1 mandate — what ships, what doesn't

### 2.1 What ships in Sprint 1

- **Architectural foundations** (§3) — state store, URL scheme, State
  Template primitive, shell chrome, design tokens.
- **Mission Control v1** (§4.S1) — six-panel layout answering the six
  operator questions.
- **AI Activity Timeline v1** (§4.S2) — persistent right rail with 10
  actor types, live streaming.
- **Approval Center v1** (§4.S3) — unified queue + header chip + drawer
  triple.
- **Master Bot Dashboard skeleton** (§4.S4) — identity strip + current
  plan (simple mode) + last decisions log. Full Plan Contract + HITL
  gate cross-links are Sprint 2.
- **Widget trichotomy primitives** (§4.P) — Metric Block, Chart Tile,
  Table Tile as shared components.
- **State Template** (§4.P8) — the D7 primitive powering every
  non-happy-path state.
- **Facet Bar** (§4.I5) — shared filter component.
- **Time-window chip** (§4.I6) — shared component with cascade.
- **Mode switcher + Advanced Lens toggle** (§4.I7) — persona
  personalisation active from Sprint 1.
- **Deep-link routing** (§4.I2) — URL carries CNL payload.
- **Attention panel with severity ordering** (§8.8 codified) —
  Mission Control's Q6 panel.
- **Danger ribbon** — critical-tier notifications (§14.2 codified).
- **Empty states across every shipped surface** (§4.S5 · D7 subset).
- **Optimistic-UI on filter apply + row selection + approve action**
  (§6.3 latency budget).

### 2.2 What does NOT ship in Sprint 1 (deferred to Sprint 2+)

Explicit non-goals:

- **Lineage Graph mode** (Bible §10.2) — the Lineage *bar* ships;
  Graph *mode* is Sprint 2.
- **Pinned Preview** (§7.12) — Sprint 2.
- **Full Master Bot Plan Contract with HITL cross-links** — Sprint 2.
- **Full Workforce Org Chart** (D4 §5) — Sprint 2 (Mission Control
  renders a summary strip only).
- **Copilot trace-as-UI** (§24 · P24) — Sprint 3.
- **G3 Knowledge Graph** (D5) — Sprint 3.
- **G5 Execution Constellation** (D5) — Sprint 3.
- **G6 Portfolio Risk Surface** (D5) — Sprint 4.
- **G7 Learning Evolution Timeline** (D5) — Sprint 3.
- **Executive Briefing surface** `/c/briefing` (D6 §4.2) — Sprint 3.
- **Research Workspace surface** `/c/research` (D6 §6.2) — Sprint 3.
- **Multi-user mode assignment UI** (D6 §13) — Sprint 3.
- **Factory Replay full experience** (Bible §16) — Sprint N+.
- **Full copy library** — Sprint 1 ships only D7 specimens for
  Sprint 1 surfaces.
- **Chart drill-through table drawer** — Sprint 1 charts drill-through
  to inline sub-list; full table-drawer is Sprint 2.

### 2.3 Sprint 1 non-goals that seem tempting but must wait

- Multi-monitor briefing wall.
- Real-time WebSocket telemetry (polling remains; §6.3 optimistic UI
  handles interaction perception).
- Custom cursor.
- Any icon set beyond lucide-react.
- Any font beyond Berkeley Mono · Neue Haas Grotesk · GT Sectra.

---

## 3. Architectural foundations (must ship before feature components)

These items are prerequisites. No feature component can build until
they are in place.

### 3.1 Workspace state store — Context Never Lost foundation

**Governs:** Bible §1.4.4.

**Contract (implementation-agnostic in D8; state library selection in
FRONTEND_TECHNICAL_STANDARDS.md):**

```ts
type WorkspaceState = {
  mode: 'executive' | 'operations' | 'research' | 'developer';
  advanced_lens: boolean;
  density: 'compact' | 'cozy' | 'cinema';
  selected_artefact?: { type: string; id: string };
  selected_worker?: string;
  time_window: TimeWindowState;
  facets: Record<string, FacetState>;          // per-surface
  pins: PinnedPreview[];                        // workspace-global
  evidence_drawer_open?: EvidenceDrawerState;
};
```

**Storage strategy:**

- `mode`, `advanced_lens`, `density` → **localStorage** (persistent).
- `time_window`, `facets`, `selected_artefact`, `selected_worker`,
  `pins`, `evidence_drawer_open` → **sessionStorage + URL query
  params** (per-tab session + deep-linkable).
- On page load: URL wins → sessionStorage → localStorage → defaults.

**API required by every feature component:**

- `useWorkspaceState()` — read + subscribe.
- `useSetMode(mode)` — triggers 200 ms crossfade.
- `useSetFacet(surfaceKey, facetKey, value)`.
- `useSetTimeWindow(value)` — cascades to every subscribed surface.
- `useSelectArtefact({ type, id })` — cross-module highlight.
- `usePin(item)` / `useUnpin(item)`.

**Test coverage requirement (§7):** ≥ 90 % branch coverage on the
store; ≥ 100 % on cascade rules.

### 3.2 State Memory infrastructure — Bible §1.4.5 foundation

**Governs:** Bible §1.4.5.

**Contract:**

```ts
type SurfaceState<T> = {
  key: string;                        // stable per surface, e.g. "mc.attention"
  scroll_position?: number;
  expanded_panels?: string[];
  active_tab?: string;
  local_layout?: Record<string, unknown>;
  drawer_state?: DrawerState;
  data: T;
};
```

**API:**

- `useSurfaceState(key)` — read + write per-surface slice.
- On mount: read; on unmount: write.
- Storage: sessionStorage-backed; keys survive within-tab navigation.

**Rule enforcement:** State Memory data **never enters the URL**.
Deep-linked visits start fresh on scroll / expand / tab.

**Test coverage:** ≥ 90 % branch; every Sprint 1 surface has a
State Memory smoke test.

### 3.3 URL scheme + routing

**Governs:** Bible §4.3 + §1.4.4.

**Route table (Sprint 1 subset):**

```
/c/mission                          — Mission Control (default landing)
/c/approvals                        — Approval Center
/c/approvals/:id                    — approval deep-link
/c/factory                          — Master Bot Dashboard (skeleton)
/c/strategies                       — Explorer (list only, Sprint 1)
/c/strategies/:id                   — strategy detail (Sprint 1 basic)
/c/advanced                         — Layer 4 landing
/c/advanced/:section                — Layer 4 sections
```

**Query params (CNL payload):**

- `?mode=<executive|operations|research|developer>` — override
- `?filters=<encoded>` — Facet Bar state
- `?since=<ISO>&until=<ISO>` — time window
- `?strategy=<id>` — cross-module highlight
- `?worker=<id>` — cross-module highlight
- `?lens=advanced` — Advanced Lens toggle

Deep-linkable; every URL is bookmarkable.

**⌘K palette items (Sprint 1 subset):**

- Navigate: every route above.
- Actions: `pin`, `unpin`, `switch mode`, `toggle advanced`,
  `open approval by id`.
- Developer group: hidden unless mode = developer.

### 3.4 Design token file — `tokens.css`

**Governs:** Bible §5 (all subsections) + D1 §3.

Must define, as CSS custom properties:

- Every surface / content / signal / stroke token from Bible §5.
- Every typography size / weight / line-height (Berkeley Mono, Neue Haas
  Grotesk, GT Sectra registered).
- Every spacing step 1–7.
- Every radius step 1–4.
- Motion durations 120 / 200 / 320 / 400 ms + `--ease-*` curves.

**Enforcement:** ESLint / Stylelint rule forbids any raw hex/px in
component styles.

### 3.5 Shell chrome — the persistent frame

**Governs:** Bible §4.

**Ships as one root component:**

```
<AppShell>
  <DangerRibbon />               — critical-only; hidden by default
  <Header>
    <BrandChip />
    <StatusRail compact />
    <ApprovalsChip />
    <MasterBotChip />
    <ModeSwitcher />
    <AdvancedLensToggle />
    <UserMenu />
  </Header>
  <LeftRail />                   — 8 modules
  <TopTabBar />                  — contextual sub-sections
  <main>
    <Outlet />                   — current route content
  </main>
  <RightRail>
    <Timeline />                 — persistent
  </RightRail>
  <StatusRail bottom />          — 6-chip footer
  <PinsTray />                   — appears when first pin added
</AppShell>
```

**Never unmounts on route change.** Only `<Outlet />` swaps. This
enforces both CNL and State Memory naturally.

### 3.6 `<StateTemplate>` primitive — D7 foundation

**Governs:** D7 §3.

**API:**

```ts
<StateTemplate
  variant="empty" | "loading" | "error" | "dormant" | "replay-empty" | "success"
  icon={LucideIcon}                     // or 'none' for loading tiers
  headline: string                      // ≤ 90 chars
  purpose?: string                      // ≤ 90 chars
  primaryAction?: { label, href, onClick }
  secondaryLink?: { label, href, onClick }
  advancedFootnote?: string             // ≤ 90 chars mono; shown on Advanced-Lens only
  code: string                          // stable D7 code, e.g. "mc-empty-nothing-pending"
  tone?: 'ok' | 'warn' | 'crit' | 'advisory' | 'info' | 'dormant'
/>
```

**Renders 6-slot anatomy** (D7 §3). Mode-tone variants derived from
workspace state store.

**Every Sprint 1 surface uses `<StateTemplate>`.** Ban on ad-hoc empty
state markup.

### 3.7 A11y baseline

**Governs:** Bible §17.

**Sprint 1 requires** (before any surface passes acceptance):

- axe-core CI integration — zero violations on every shipped surface.
- Keyboard walkthrough script per surface (documented as
  `<surface>.keyboard.md`).
- `prefers-reduced-motion` compatibility test per component.
- Screen-reader announcement audit on every stateful component.

---

## 4. Component inventory & work items

Each item has: **code** · **name** · **design reference** · **effort**
· **dependencies** · **acceptance summary**.

Effort is engineer-days at Sprint 1 skill level (rough — refine at
sprint planning). Dependencies cite item codes.

### 4.I · Infrastructure (must-ship-first)

| Code | Name | Ref | Effort | Deps | Ships |
|---|---|---|---|---|---|
| I1 | Workspace state store | §3.1, Bible §1.4.4 | 4 d | — | Sprint 1 Day 1–4 |
| I2 | URL scheme + routing | §3.3, Bible §4.3 | 3 d | I1 | Sprint 1 Day 3–5 |
| I3 | State Memory infra | §3.2, Bible §1.4.5 | 2 d | I1 | Sprint 1 Day 3–5 |
| I4 | AppShell + persistent chrome | §3.5, Bible §4 | 4 d | I1, I2 | Sprint 1 Day 5–8 |
| I5 | Design tokens (`tokens.css`) | §3.4, D1 §3–§5 | 2 d | — | Sprint 1 Day 1–2 |
| I6 | Font loading + `@font-face` | D1 §4 | 1 d | I5 | Sprint 1 Day 1 |
| I7 | Mode switcher + Advanced Lens | D6 §3, Bible §22 | 3 d | I1, I4 | Sprint 1 Day 6–8 |
| I8 | ⌘K palette (Sprint 1 subset) | Bible §7.10, §4.3 | 4 d | I1, I2 | Sprint 1 Day 6–10 |
| I9 | Danger ribbon | Bible §14.2, §14.4 | 2 d | I4 | Sprint 1 Day 8–9 |
| I10 | Status rail (6 chips) | Bible §7.6 | 3 d | I4, I5 | Sprint 1 Day 9–11 |

**Infrastructure total: 28 engineer-days.**

### 4.P · Primitive components (shared across surfaces)

| Code | Name | Ref | Effort | Deps |
|---|---|---|---|---|
| P1 | `<Chip>` + letter-glyph variants | Bible §7.1 | 2 d | I5 |
| P2 | `<MetricBlock>` A/B/C variants | Bible §7.11.1, D1 §7.2 | 3 d | P1, I5 |
| P3 | `<ChartTile>` (line + sparkline only for Sprint 1) | Bible §7.11.2, §14.5–14.8 | 5 d | P1, P4, P8, F1 |
| P4 | `<TableTile>` (virtualised list) | Bible §7.11.3 | 4 d | P1, P8, F1 |
| P5 | `<PipelineStageBar>` (G2 anatomy) | Bible §7.3, D5 §4 | 3 d | P1, I5 |
| P6 | `<ActivityRow>` (Timeline row · 10 actors) | Bible §7.4, D2 §3 | 3 d | P1, I5 |
| P7 | `<WorkerCard>` (Sprint 1 minimal · Purpose + state + subject only) | Bible §7.6, D4 §5.3 | 3 d | P1, I5 |
| P8 | `<StateTemplate>` (D7) | §3.6, D7 §3 | 3 d | P1, I5 |
| P9 | `<ApprovalCard>` (D3 §2) | Bible §7.5, D3 §2 | 5 d | P1, P5, P8, F1 |
| P10 | `<EvidenceDrawer>` | Bible §10 | 4 d | P1, P5, P8, F1 |
| P11 | `<LineageBar>` (one hop up + down · NO Graph mode) | Bible §10.1, D1 §10 | 2 d | P1 |
| P12 | `<ProvenanceTriple>` chip strip | Bible §10.2 (canonical §10.1 in v1) | 1 d | P1 |
| P13 | `<SignatureFrame>` (D5 §2 — for chart tiles + G-graphics) | D5 §2 | 3 d | P1, I5 |
| P14 | `<DivisionCaption>` (purpose header · D4 §5.2) | D4 §5.1.1, §5.2 | 1 d | P1 |
| P15 | `<KeyboardShortcut>` HUD (⌘K + `?`) | Bible §7.10 | 1 d | I8 |

**Primitives total: 43 engineer-days.**

### 4.F · Feature components (shared machinery)

| Code | Name | Ref | Effort | Deps |
|---|---|---|---|---|
| F1 | `<FacetBar>` shared filter | Bible §11.6 | 4 d | I1, P1 |
| F2 | `<TimeWindowChip>` with cascade | Bible §7.13 | 3 d | I1, P1 |
| F3 | Optimistic-UI middleware | Bible §6.3 | 3 d | I1 |
| F4 | Timeline adapter (`services/timeline.js`) | D2 §12 | 4 d | I1 |
| F5 | Approvals adapter (`services/approvals.js`) | D3 §7 | 4 d | I1 |
| F6 | Factory / Master-Bot adapter (`services/factory.js`) | D4 §14 | 5 d | I1 |
| F7 | Mission Control aggregator (composes above) | Bible §8.1 | 3 d | F4, F5, F6 |

**Feature-machinery total: 26 engineer-days.**

### 4.S · Surfaces (Sprint 1 destinations)

| Code | Name | Ref | Effort | Deps |
|---|---|---|---|---|
| S1 | `/c/mission` Mission Control v1 | Bible §8.1, D1 §8.1 | 6 d | F7, P2, P3, P4, P6, P8, I4, I10 |
| S2 | AI Activity Timeline (right rail) | D2 (full) | 6 d | F4, P6, P8, I4 |
| S3 | `/c/approvals` Approval Center v1 | D3 (full) | 7 d | F5, P9, P8, F1, F2, I4 |
| S4 | `/c/factory` Master Bot Dashboard skeleton | D4 §3, §6 (last decisions log only) | 5 d | F6, P2, P7, P8, I4 |
| S5 | `/c/strategies` Explorer (minimal — table + inline actions) | Bible §8.3, D3 §19.6 | 5 d | P4, P8, F1, P11 |
| S6 | Empty / loading / error / dormant states across S1–S5 | D7 (§8–§18 Sprint 1 specimens) | 3 d | P8 |
| S7 | Attention panel severity-ordered (Q6 of Mission Control) | Bible §8.8 | 2 d | S1 |

**Surfaces total: 34 engineer-days.**

### 4.T · Tests, tooling, ancillary

| Code | Name | Ref | Effort | Deps |
|---|---|---|---|---|
| T1 | Storybook setup + primitives Stories | §8 | 3 d | P1–P15 |
| T2 | Playwright E2E harness | §7 | 2 d | I2 |
| T3 | axe-core CI integration | §3.7 | 1 d | — |
| T4 | Visual-regression baseline (chromatic or equivalent) | §7 | 2 d | T1 |
| T5 | Reduced-motion audit | Bible §17 | 1 d | — |
| T6 | Keyboard walkthrough automation | Bible §17 | 2 d | T2 |

**Tests/tooling total: 11 engineer-days.**

### 4.X · Total Sprint 1 effort

Sum: **28 + 43 + 26 + 34 + 11 = 142 engineer-days**.

At a 4-engineer team over 2 sprints (10 working days each), this is
5 engineer-weeks capacity per person — matches 4 × 5 = 20 person-weeks
= 100 engineer-days available; Sprint 1 exceeds this by ~40 %.

**Recommended re-scoping** (choose one; discuss at kick-off):

- **Option A · Extend to 3 sprints.** Ship everything above across 6
  working weeks.
- **Option B · Reduce S5 to a placeholder** — Strategy Explorer full
  functionality moves to Sprint 2. Saves 5 d.
- **Option C · Simplify S4 to just the identity strip + last
  decisions.** Saves 3 d.
- **Option D · Keep Sprint 1 at 100 days by cutting P13 & P11 to
  Sprint 2.** Saves 5 d but breaks the Signature Frame invariant on
  chart tiles.

**D8 recommendation:** Option A (3-sprint stretch). Craftsmanship over
speed remains the operator's principle.

---

## 5. Dependency graph (visual)

```
                    ┌────────────────────────────────────┐
                    │  I5 tokens   I6 fonts   I1 store    │
                    │                          │          │
                    │                          ▼          │
                    │                    I2 routing       │
                    │                          │          │
                    │                    I3 State Memory  │
                    │                          │          │
                    │                          ▼          │
                    │                    I4 AppShell      │
                    │                          │          │
                    │                          ▼          │
                    │                    I7 Mode switch   │
                    │                    I8 ⌘K palette   │
                    │                    I9 Danger ribbon │
                    │                    I10 Status rail  │
                    └────────────────────────────────────┘
                                    │
                                    ▼
                    P1 Chip → P2 Metric · P4 Table · P8 State
                                    │
                                    ▼
                    P5 · P6 · P7 · P9 · P10 · P11 · P12 · P13 · P14
                                    │
                                    ▼
                    F1 FacetBar · F2 TimeWindow · F3 Optim
                    F4 · F5 · F6 · F7 (adapters + aggregator)
                                    │
                                    ▼
                    S1 · S2 · S3 · S4 · S5 · S6 · S7
                                    │
                                    ▼
                    T1 · T2 · T3 · T4 · T5 · T6
```

Sprint 1 (or 3-sprint stretch) executes strictly top-down.

---

## 6. Acceptance criteria — per component

Every component ships only if:

- ✅ Matches its D-doc reference (cited in the component's PR title).
- ✅ Uses only tokens from `tokens.css`.
- ✅ Uses only typography from Bible §5.2 + D1 §4.
- ✅ Respects motion budget (Bible §6.1 + §6.3).
- ✅ Composes from primitives §4.P (no ad-hoc markup).
- ✅ Uses `<StateTemplate>` for every non-happy state (no inline empty
  markup).
- ✅ Uses `<FacetBar>` if filterable (no per-surface reimplementation).
- ✅ Uses `<TimeWindowChip>` if time-scoped.
- ✅ Data flows through the workspace state store (I1).
- ✅ State Memory slice used where applicable (I3).
- ✅ Renders correctly in Simple + Advanced Lens.
- ✅ Renders correctly in every mode (E · O · R · D · with mode-
  specific tone but Decision Identity preserved).
- ✅ Has authored empty / loading / error / dormant states from D7.
- ✅ Has `data-testid` on every interactive element.
- ✅ Passes axe-core with zero violations.
- ✅ Passes keyboard walkthrough.
- ✅ Respects `prefers-reduced-motion`.
- ✅ Ships with ≥ 1 Storybook story per variant.
- ✅ Meets latency budget (§6.3) verified by Playwright timing.
- ✅ Screenshot in workstation + tablet + briefing postures archived.
- ✅ Purpose Before Status (D4 §5.1.1) verified where applicable.
- ✅ Decision Identity verified — same object, four modes, byte-
  identical underlying values.

---

## 7. Test coverage requirements

Sprint 1 minimum bars:

| Layer | Unit | Integration | E2E |
|---|---|---|---|
| Workspace state store (I1) | ≥ 90 % branch | — | — |
| State Memory infra (I3) | ≥ 90 % branch | — | — |
| Adapters (F4–F6) | ≥ 80 % branch | — | — |
| Primitives (P1–P15) | ≥ 70 % branch | — | 1 Storybook interaction test each |
| Feature machinery (F1–F3, F7) | ≥ 80 % branch | ≥ 70 % of interactions | — |
| Surfaces (S1–S5) | — | ≥ 60 % | Playwright happy-path + at least 1 non-happy state |
| Optimistic UI | — | 100 % rollback path | 1 happy + 1 rollback |
| a11y | — | axe-core 0 violations | ✅ |

Reduced-motion test: 1 per component that ships motion.

---

## 8. Storybook targets (Sprint 1)

Every primitive and every stateful component ships with Storybook
stories:

- `<Chip>` — variants × states × letter glyphs = ≥ 12 stories.
- `<MetricBlock>` — 3 variants × 4 modes × Simple/Advanced = ≥ 12
  stories.
- `<ChartTile>` — line + sparkline × happy + empty + loading + error
  + dormant + replay-empty = ≥ 6 stories.
- `<TableTile>` — happy + empty + hover-actions + column-sort + drill = ≥ 5.
- `<PipelineStageBar>` — 8 stages × 5 states = ≥ 8 stories.
- `<ActivityRow>` — 10 actor types × Simple + Advanced = ≥ 20 stories.
- `<WorkerCard>` — 5 states × 4 modes = ≥ 20 stories.
- `<StateTemplate>` — 6 variants × mode tones = ≥ 12 stories.
- `<ApprovalCard>` — 3 risk levels × 6 origins × Simple/Advanced ≥ 8
  stories.
- `<EvidenceDrawer>` — variants + empty + loading = ≥ 5 stories.
- `<LineageBar>` — with ancestors + descendants; root generation empty
  ≥ 3 stories.
- `<SignatureFrame>` — 4 tone × icon fixtures ≥ 4 stories.

Storybook target: **≥ 115 stories at Sprint 1 close.**

---

## 9. Design-implementation contract

### 9.1 Design remains authoritative

- Every PR title cites its D-doc reference (`refs D3 §7.5`,
  `refs D7 §8.4`).
- Reviewers reject PRs that ship without a citation.
- If an engineer disagrees with a design rule, the resolution is
  through a design PR against the relevant D-doc — **never** an
  in-code override.

### 9.2 Component ownership

- **Primitives (§4.P)** — owned by a "design system" pair (one designer
  + one engineer). Primitives are the identity of the product.
- **Adapters (§4.F.4–F.6)** — owned by feature-team pairs.
- **Surfaces (§4.S)** — owned by product engineers with design review
  gate before ship.

### 9.3 Change propagation

- Changing a primitive requires: PR + Storybook update + visual-
  regression review + downstream-consumer smoke test.
- Changing a token requires: PR against `tokens.css` + Bible v-major
  bump note if the token is signal-tier (Bible §20.3).

### 9.4 Feedback into design

- Engineer-discovered design gaps route back to a **weekly design
  triage** — the operator + lead designer + one engineer.
- Triage decisions are captured as D-doc addenda or as items in
  `ROADMAP.md`.

---

## 10. Backend Feature Freeze verification

Sprint 1 must not touch backend. Verification checklist per PR:

- ✅ No new endpoints created.
- ✅ No existing endpoints modified.
- ✅ Only reads from documented endpoints; no writes to un-documented
  ones.
- ✅ Adapters (F4–F6) normalise but do not aggregate on backend side.
- ✅ Feature flags read-only.
- ✅ Kill posture read-only (arm/disarm is a governance-gated flow
  reserved for later — Sprint 1 shows current state only).

**Freeze exit:** only via explicit operator instruction. D8 asserts
Freeze integrity for Sprint 1.

---

## 11. Rollout order — recommended sequence

**Days 1–2:** I5 (tokens) · I6 (fonts) · start I1 (store).
**Days 3–5:** finish I1 · I2 · I3 · T3 (axe-core).
**Days 6–8:** I4 (AppShell) · I7 (mode switcher).
**Days 9–11:** I8 (⌘K) · I9 (danger ribbon) · I10 (status rail).
**Days 12–16:** P1 · P2 · P4 · P8 (core primitives) · start T1
(Storybook).
**Days 17–22:** P5 · P6 · P7 · P11 · P12 · P13 · P14.
**Days 23–28:** F1 · F2 · F3 · start adapters F4/F5/F6.
**Days 29–35:** finish adapters · F7 aggregator · S2 (Timeline) · S6
(empty states across S1–S5).
**Days 36–42:** S1 (Mission Control) · S7 (Attention panel).
**Days 43–48:** S3 (Approval Center).
**Days 49–53:** S4 (Master Bot skeleton) · S5 (Explorer minimal).
**Days 54–60:** T2 · T4 · T5 · T6 · integration + polish.

Cadence assumes a 4-engineer team; scale linearly.

---

## 12. Risks & mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Workspace state store becomes a god-object | high maintenance drag | Enforce per-slice reducers; no cross-slice mutation |
| R2 | Optimistic UI rollback paths under-tested | operator sees ghost state | 100 % test coverage on rollback (§7) |
| R3 | Font loading FOIT/FOUT breaks first-impression | high | Preload weights; `font-display: swap`; verify on cold cache |
| R4 | Timeline stream saturates on high-event days | motion budget breach | Batch after 12 concurrent tweens (D2 §10) — already spec'd |
| R5 | Mode switcher flicker on rapid switching | brand damage | Debounce switches to ≥ 200 ms (matches crossfade tier) |
| R6 | Accessibility regressions on ambient motion | WCAG failure | `prefers-reduced-motion` locked in tokens; enforced at CSS layer |
| R7 | Empty state library drift from D7 | inconsistency | Storybook + copy review gate at PR time |
| R8 | Deep-link URL becomes unreadable | operator distrust | Cap query params at 5 keys; document each |
| R9 | Adapter proliferation | backend Freeze pressure | Adapter code review with the operator monthly |

---

## 13. Post-D8 gate — Experience Design Suite

Per operator instruction (2026-07-20): **before Sprint 1
implementation begins**, the following experience-design deliverables
will be authored. They form a gate between D8 and code.

### 13.1 Rationale

D1–D7 codified visual system and primitives. D8 codifies component
architecture. The experience-design suite codifies **how these
compose into operator journeys** — which is the last thing to lock
before pixels move.

### 13.2 Deliverables (E-series)

| # | Doc | Purpose |
|---|---|---|
| E1 | **Strategy Experience** | End-to-end journey of a single strategy from generation → validation → optimization → certification → promotion → portfolio → execution → retirement. One artefact, one lifetime, every surface it touches. |
| E2 | **Authentication Experience** | First login through session lifecycle, multi-mode users, SSO handoffs, logout, session-expiry recovery. |
| E3 | **First-Time User Journey** | The moment-zero experience per mode. Empty Mission Control on first visit; first navigation choice; onboarding without wizards. |
| E4 | **Daily Operator Journey** | Routine on-shift flow: login → glance → approve → investigate → sign off. Choreographed against the 6 operator questions. |
| E5 | **Cross-Module Navigation** | The graph of intra-workspace transitions. Which module leads to which; how CNL + State Memory play across every path. |

### 13.3 What the E-series catches

- **Sequencing defects** — screen-A's exit state incompatible with
  screen-B's entry state.
- **Context loss** — where CNL / State Memory fail across module
  boundaries.
- **Journey friction** — an operator's third click on a common task
  is too deep.
- **First-time confusion** — moment-zero state feels like a broken
  install.
- **Cross-module inconsistency** — the same object presented
  differently across two modules (Decision Identity violation).

### 13.4 Structure per E-doc

Each will follow the D-series discipline:

- Design Principles Checklist (18 items as of Bible v2.1)
- Purpose
- Journey map (linear or graph)
- Per-step surface reference
- Copy specimens (from D7 library where applicable)
- Mode-specific variations
- Edge cases + failure recovery
- Sprint acceptance criteria
- Data contract (frontend-only, Feature Freeze respected)

### 13.5 Expected timeline

- E1 Strategy Experience — 2–3 days
- E2 Authentication Experience — 2 days
- E3 First-Time User Journey — 2 days
- E4 Daily Operator Journey — 2 days
- E5 Cross-Module Navigation — 2–3 days

**Total: ~11 working days.** After E5 sign-off, Sprint 1 implementation
begins.

### 13.6 Order of authorship (recommended)

Recommended order: **E2 → E3 → E4 → E1 → E5.**

Rationale:
- E2 (Auth) is prerequisite for E3 (First-Time).
- E4 (Daily) codifies the routine after first-time.
- E1 (Strategy Experience) is orthogonal to auth flow and can slot in
  parallel.
- E5 (Cross-Module Navigation) integrates all prior E-docs.

---

## 14. Sprint 1 exit criteria — "done" means

Sprint 1 is complete when:

- ✅ Every §4 item shipped to acceptance (§6).
- ✅ Mission Control renders end-to-end for the Operations persona
  with real backend data.
- ✅ Timeline streams live events in the right rail.
- ✅ Approvals unified queue works — approve, defer, deny, route
  round-trip.
- ✅ Master Bot Dashboard skeleton shows identity + current plan (simple
  mode) + last decisions log.
- ✅ Strategy Explorer lists strategies with inline actions.
- ✅ Mode switcher toggles between 4 modes with 200 ms crossfade + full
  Decision Identity + full Context Never Lost + full State Memory.
- ✅ ⌘K palette navigates every route + fires actions.
- ✅ Danger ribbon fires on kill-posture arm.
- ✅ Every empty state matches its D7 specimen.
- ✅ axe-core CI passes on every surface.
- ✅ Storybook has ≥ 115 stories.
- ✅ Playwright smoke passes for Operations morning-routine journey.
- ✅ Screenshots archived: 4 modes × 3 postures × 5 surfaces = 60
  frames (visual regression baseline).
- ✅ Design-doc PR-title convention respected on 100 % of PRs
  landed.
- ✅ Backend Feature Freeze verified — zero backend commits during
  Sprint 1.

---

## 15. What D8 does NOT include

- Coded prototype (there's no code in the design phase).
- Technology-selection (React version, state library, bundler,
  test runners) — belongs to `FRONTEND_TECHNICAL_STANDARDS.md`.
- CI/CD pipeline design.
- Deployment plan.
- Feature-flag governance for Sprint 2+ rollouts.
- Sprint 2+ scope beyond the *non-goals* list (§2.2).
- Backend spec (Feature Freeze).

---

## 16. Handoff to Sprint 1 (recommended sequence)

1. Operator reviews and approves D8.
2. Operator schedules the E-series (§13).
3. E-series authored in ~11 working days (§13.5).
4. Operator reviews and approves each E-doc.
5. Sprint 1 kick-off with:
   - D-series (D0–D7) as design system
   - Bible v2.1 as canonical spec
   - E-series (E1–E5) as journey spec
   - D8 as execution plan
6. Sprint 1 begins Day 1 with §11 rollout order.
7. Sprint 1 exits per §14 criteria.
8. Sprint 2 planning references §2.2 non-goals list.

---

## 17. Appendix A — Sprint 1 file / folder skeleton (illustrative)

The engineering team may adapt structure; D8 records D-doc-friendly
suggested layout:

```
/app/frontend/src/
  ├─ app-shell/                       (I4)
  ├─ tokens.css                       (I5)
  ├─ fonts/                           (I6)
  ├─ workspace-state/                 (I1, I3)
  │   ├─ store.ts
  │   ├─ selectors.ts
  │   ├─ state-memory.ts
  │   └─ url-sync.ts
  ├─ routing/                         (I2)
  ├─ palette/                         (I8)
  ├─ mode-switcher/                   (I7)
  ├─ shell/
  │   ├─ danger-ribbon/               (I9)
  │   ├─ status-rail/                 (I10)
  │   ├─ header/
  │   ├─ left-rail/
  │   ├─ top-tab-bar/
  │   ├─ right-rail/
  │   └─ pins-tray/
  ├─ primitives/                      (P1–P15)
  ├─ services/                        (adapters F4–F6)
  ├─ modules/                         (surfaces S1–S5)
  │   ├─ mission/                     (S1)
  │   ├─ timeline/                    (S2)
  │   ├─ approvals/                   (S3)
  │   ├─ factory/                     (S4)
  │   └─ strategies/                  (S5)
  ├─ storybook/
  └─ tests/
      ├─ unit/
      ├─ integration/
      └─ e2e/
```

**This layout is a suggestion.** The design contract is invariant;
folder names are not.

---

## 18. Appendix B — Cross-D-doc reference index

For engineering convenience, every Sprint 1 item and its authoritative
D-doc reference in one place.

| Sprint 1 item | Primary D-doc | Additional refs |
|---|---|---|
| Workspace state store | Bible §1.4.4 | §4.3, §11.6 |
| State Memory | Bible §1.4.5 | — |
| URL scheme | Bible §4.3 | §1.4.4 |
| AppShell | Bible §4 | §7 |
| Tokens | Bible §5, D1 §3–§5 | — |
| Fonts | D1 §4 | Bible §5.2 |
| Mode switcher | D6 §3 | Bible §22 |
| ⌘K palette | Bible §7.10 | §4.3 |
| Danger ribbon | Bible §14.2 | §14.4 |
| Status rail | Bible §7.6 | §8.6 |
| `<Chip>` | Bible §7.1 | D1 §7.1 |
| `<MetricBlock>` | Bible §7.11.1 | D1 §7.2 |
| `<ChartTile>` | Bible §7.11.2, §14.5–14.8 | D5 §2 (Signature Frame) |
| `<TableTile>` | Bible §7.11.3 | §7.9 |
| `<PipelineStageBar>` | Bible §7.3 | D5 §4 |
| `<ActivityRow>` | Bible §7.4 | D2 §3–§5 |
| `<WorkerCard>` | Bible §7.6 | D4 §5.3 |
| `<StateTemplate>` | D7 §3 | Bible §15 |
| `<ApprovalCard>` | Bible §7.5 | D3 §2 |
| `<EvidenceDrawer>` | Bible §10 | D1 §10 |
| `<LineageBar>` | Bible §10.1 | D1 §10 |
| `<FacetBar>` | Bible §11.6 | D2 §8, D3 §4 |
| `<TimeWindowChip>` | Bible §7.13 | D2 §6.3 |
| Optimistic UI middleware | Bible §6.3 | — |
| Timeline adapter | D2 §12 | — |
| Approvals adapter | D3 §7 | — |
| Factory adapter | D4 §14 | — |
| Mission Control surface | Bible §8.1 | D1 §8.1 |
| Timeline surface | D2 (full) | — |
| Approval Center surface | D3 (full) | — |
| Master Bot skeleton | D4 §3, §6 | — |
| Explorer minimal | Bible §8.3 | §19.6 |
| Empty states | D7 (full) | — |
| Attention severity | Bible §8.8 | — |

---

*End of D8 — Sprint 1 Detailed Execution Plan.*

*All 18 checklist items confirmed. Bible v2.1 · D6 Decision Identity ·
D7 State Template · Bible §1.4.5 State Memory · Backend Feature Freeze
all respected.*

*Total Sprint 1 effort: 142 engineer-days. Recommended 3-sprint stretch
for craftsmanship at the level the D-series demands.*

*Post-D8 experience-design suite (E1–E5) sequenced as the gate between
D8 and Sprint 1 implementation.*

*The D-series is complete. Awaiting your review before authoring the
E-series (recommended start: E2 · Authentication Experience).*

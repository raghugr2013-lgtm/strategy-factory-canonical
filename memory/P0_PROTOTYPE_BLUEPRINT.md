# P0 — Interactive Prototype Blueprint

> The design contract for the prototype. Specifies **what will be
> built · how it will be evaluated · what constitutes prototype exit
> criteria · and how refinements become formal D/E-series addenda**.
>
> The prototype is a **design-validation instrument**, not a demo. Its
> purpose is to prove the six evaluation dimensions (Discoverability ·
> Navigation Predictability · Cognitive Load · Interaction Rhythm ·
> Operator Trust · Product Identity) — not to demonstrate features.
>
> Layered on Bible v2.1 + D-series + E-series. Governed by D8 §13.7
> (Interactive Prototype Gate).
>
> Prepared 2026-07-20. First prototype-phase deliverable.

---

## 0. Design Principles Checklist (21 items — permanent quality gate)

P0 confirms:

- [x] All 21 items from E5 §0 apply. The prototype must demonstrate every principle it inherits, not just render them.
- [x] The prototype is discipline-preserving — no new tokens, no new components, no new rules invented during the build.

---

## 1. Purpose

The Interactive Prototype exists to **validate the completed design
architecture** before Sprint 1 production code is written.

**Success is measured against six operator-directed dimensions:**

1. **Discoverability** — can operators find affordances without being
   told?
2. **Navigation Predictability** — does Rule of Predictable Return
   hold under a 10-hop test?
3. **Cognitive Load** — does an 8-hour simulated shift feel sustainable?
4. **Interaction Rhythm** — do motion budget · latency budget ·
   optimistic UI · interrupt frugality feel coherent?
5. **Operator Trust** — does Trust Before Credentials · Silent
   Confidence · Rule of Continuity produce felt reliability?
6. **Product Identity** — is the prototype unmistakably Strategy
   Factory (five recognisability heuristics · Design Inspiration
   Study §5.1)?

**Anti-goals:**

- Not a feature demo.
- Not a marketing artefact.
- Not production code (throw-away discipline · D8 §13.7).
- Not a stakeholder presentation.
- Not a substitute for Sprint 1.
- Not a place to invent new design ideas.

---

## 2. The six evaluation dimensions — codified as verification tests

Each dimension gets a specific, executable evaluation protocol.

### 2.1 Discoverability tests

Operator walk-through without prior product knowledge. Success:

- [ ] Operator locates ⌘K within 60 s (via the persistent hint · E3
      §5.3).
- [ ] Operator discovers Advanced Lens within 3 min (via `⋯ +N more`
      chip · E3 §7).
- [ ] Operator finds the mode switcher without prompting.
- [ ] Operator reaches Approval Center from Mission Control unaided.
- [ ] Operator identifies a strategy's Passport from a Timeline row
      unaided.
- [ ] Operator understands the meaning of the P/W/F/A/I letter glyphs
      from context alone.

**Fail state:** any test requiring explicit instruction escalates a
D/E-series addendum for empty-state or hint refinement.

### 2.2 Navigation Predictability tests

Rule of Predictable Return (E5 §4.5) under stress:

- [ ] 10-hop navigation test — every Back restores exact state.
- [ ] Mode-switch mid-investigation preserves scroll + drawer state.
- [ ] Triage interrupt during deep-dive returns exactly (E4 §5.4).
- [ ] ⌘K → destination → Back returns to origin (not to palette · E5
      §7.4).
- [ ] Deep-link entry disables Back appropriately (E5 §7.6).
- [ ] Three-Esc pattern returns to Mission Control while preserving
      State Memory (E4 §5.2).

**Fail state:** any inconsistency escalates a navigation-adapter
refinement in D8 §3 or E5 §4.5.

### 2.3 Cognitive Load tests

Simulated 8-hour session:

- [ ] Motion budget sustains without visual fatigue (ambient pulse ·
      G8 heartbeat).
- [ ] `prefers-reduced-motion` produces a completely still shift.
- [ ] No accumulated notification anxiety (Interrupt Frugality · E4
      §4.5).
- [ ] Attention panel severity ordering (Bible §8.8) surfaces
      priorities without operator hunting.
- [ ] Empty states feel calm, not alarming (D7 §2).
- [ ] Kill-posture state feels informational, not threatening.

**Fail state:** any fatigue point escalates a motion-budget or
attention-discipline refinement.

### 2.4 Interaction Rhythm tests

Under the interaction latency budget (Bible §6.3):

- [ ] Filter apply feels instant (< 100 ms optimistic UI).
- [ ] Approve commit feels instant (300 ms budget with optimistic UI).
- [ ] Row selection border draws immediately (< 100 ms).
- [ ] Module navigation is 200 ms Medium tier crossfade — no full-
      page reload feel.
- [ ] Mode switch is a 200 ms crossfade, not a reload.
- [ ] Chart re-render skeleton appears at 500 ms budget breach.

**Fail state:** any budget breach escalates a latency-adapter or
optimistic-UI-middleware refinement in D8 §4.F3.

### 2.5 Operator Trust tests

Trust Before Credentials (E2 §9) + Rule of Silent Confidence:

- [ ] Pre-auth shell renders the 8 non-sensitive signals (E2 §9.1).
- [ ] Pre-auth shell renders none of the 12 forbidden signals
      (E2 §9.2).
- [ ] Kill posture pre-auth banner uses `--sig-dormant`, not
      `--sig-crit` (E2 §9.5).
- [ ] Session expiry recovery preserves the operator's vantage point
      (E2 §5).
- [ ] Optimistic UI rollback produces a legible error, not a spinner-
      of-shame (Bible §6.3).
- [ ] Copilot answers never invent — Copilot-empty-no-grounded state
      fires when appropriate (D7 §17.6).
- [ ] Progressive Confidence milestones render in factual Division
      voice, not celebratory (E3 §8.4.4).

**Fail state:** any trust violation escalates a copy-library or
signal-token refinement.

### 2.6 Product Identity tests

Five recognisability heuristics from Design Inspiration Study §5.1:

- [ ] Division-voice text present on every visible surface.
- [ ] Cool-shifted `--surface-0` background — never white.
- [ ] Six-signal palette respected — no seventh hue.
- [ ] Berkeley Mono numeric visible on every metric-block.
- [ ] Lineage / evidence link present on every artefact card.

Plus the five anti-tests (must NOT be present):
- [ ] No purple/violet gradient.
- [ ] No colourful "agent" avatars.
- [ ] No drag-and-drop workflow canvas.
- [ ] No LangSmith-style verbose JSON trace as primary panel.
- [ ] No *"click here"* / *"seamless"* / *"welcome back!"* copy.

**Fail state:** any identity violation escalates a token, primitive,
or copy refinement.

---

## 3. Prototype scope

### 3.1 Surfaces included

Every Sprint 1 surface end-to-end:

- `/login` — Login screen (E2 §3) with Trust-Before-Credentials shell
- `/c/mission` — Mission Control v1 (Bible §8.1)
- `/c/approvals` — Approval Center v1 (D3)
- `/c/approvals/:id` — Approval detail
- `/c/factory` — Master Bot Dashboard skeleton (D4 §3, §6)
- `/c/strategies` — Strategy Explorer list
- `/c/strategies/:id` — Strategy Passport 11-section (E1 §6.7)
- `/c/advanced` — Layer 4 landing

### 3.2 Primitives included

All 15 Sprint 1 primitives (D8 §4.P):

- `<Chip>` · `<MetricBlock>` · `<ChartTile>` · `<TableTile>` ·
  `<PipelineStageBar>` · `<ActivityRow>` · `<WorkerCard>` ·
  `<StateTemplate>` · `<ApprovalCard>` · `<EvidenceDrawer>` ·
  `<LineageBar>` · `<ProvenanceTriple>` · `<SignatureFrame>` ·
  `<DivisionCaption>` · `<KeyboardShortcut>` HUD

### 3.3 Infrastructure included

All Sprint 1 infrastructure (D8 §3):

- Workspace state store (I1) with CNL + State Memory
- URL scheme + routing (I2, I3)
- AppShell + persistent chrome (I4)
- `tokens.css` + font loading (I5, I6)
- Mode switcher + Advanced Lens toggle (I7)
- ⌘K palette (I8 · Sprint 1 subset)
- Danger ribbon (I9)
- Status rail (I10)

### 3.4 Feature machinery included

- `<FacetBar>` shared component (Bible §11.6)
- `<TimeWindowChip>` with cascade (Bible §7.13)
- Optimistic-UI middleware (Bible §6.3)
- Fixture-backed Timeline adapter (D2 §12 shape)
- Fixture-backed Approvals adapter (D3 §7 shape)
- Fixture-backed Factory adapter (D4 §14 shape)
- Fixture-backed Strategy adapter (E1 §11 shape)

### 3.5 Behaviours included

- All 5 cross-module invariants (E5 §4)
- Rule of Predictable Return (E5 §4.5)
- Silent Graduation (E3 §8.3)
- Progressive Confidence — all 5 milestones fireable via fixture toggle
- Interrupt Frugality (E4 §4.5)
- Session expiry recovery (E2 §5) — fireable via fixture toggle
- Trust Before Credentials pre-auth shell (E2 §9)

---

## 4. Prototype non-scope

Explicit exclusions:

- No backend integration.
- No LLM calls (Copilot answers come from a fixture library).
- No real auth (login accepts any credentials).
- No production build tooling (Vite dev server sufficient).
- No CI/CD.
- No test suites (tests are Sprint 1 · D8 §7).
- No i18n scaffolding.
- No PWA / offline manifest.
- No analytics.
- No production error monitoring.
- Sprint 2+ surfaces: Lineage Graph mode · Pinned Preview · full Plan
  Contract · Copilot trace-as-UI · G3/G5/G6/G7 · Executive Briefing ·
  Research Workspace (fixtures show them as "Sprint 2+" dormant
  states).

---

## 5. Fixture strategy

Representative data lives in `prototype/fixtures/`. Fixtures are:

- **Deterministic** — same data across sessions; enables reproducible
  walk-throughs.
- **Coherent** — a strategy referenced in Approvals appears in Timeline
  with matching lineage.
- **Realistic** — Division-voice copy per D2 Addendum; no lorem ipsum.
- **Toggleable** — every fixture has variants (happy path · empty ·
  error · dormant · replay-empty · loading) accessible via a
  keyboard-triggered Fixture Debug Panel.

### 5.1 Fixture catalogue

- `fixtures/strategies.ts` — 12 strategies across 8 lifecycle stages
- `fixtures/approvals.ts` — 4 pending approvals (Safety pinned · Master
  Bot · Learning · Governance)
- `fixtures/timeline.ts` — 200 rows across 24 h; covers all 10 actor
  types
- `fixtures/workers.ts` — 24 workers across 8 divisions
- `fixtures/plans.ts` — 1 current plan (7 steps · 1 in `⏸` HITL gate)
- `fixtures/kill-posture.ts` — armed / disarmed variants
- `fixtures/copilot.ts` — canned Copilot answers with citation refs
  (never invented — always cite one of the above fixtures)
- `fixtures/milestones.ts` — 5 Progressive Confidence milestones,
  fireable individually

### 5.2 Fixture Debug Panel (⌘⇧D)

Prototype-only affordance. Never present in Sprint 1 production code.

```
┌────────────────────────────────────┐
│  FIXTURE DEBUG                      │
│  ─────────────                      │
│  STATES                             │
│  ○ happy path (default)             │
│  ○ mc-empty-nothing-pending         │
│  ○ mc-empty-all-nominal             │
│  ○ mc-dormant-freeze                │
│  ○ mc-error-partial-panels          │
│  ○ mc-replay-empty                  │
│                                      │
│  FIRE MILESTONE                     │
│  ▸ M1 first-strategy-promoted        │
│  ▸ M2 first-strategy-retired         │
│  ▸ M3 first-portfolio-of-3           │
│  ▸ M4 first-month-continuous         │
│  ▸ M5 first-contradiction-resolved   │
│                                      │
│  SESSION                            │
│  ▸ trigger session expiry           │
│  ▸ arm kill posture                 │
│  ▸ disarm kill posture              │
│  ▸ set first-time flag              │
│  ▸ clear first-time flag            │
│                                      │
│  MODES                              │
│  ○ executive                        │
│  ● operations (current)             │
│  ○ research                         │
│  ○ developer                        │
│                                      │
│  LATENCY                            │
│  slider · 0 ms – 8000 ms            │
│                                      │
└────────────────────────────────────┘
```

Every prototype state is one keystroke + one click away.

---

## 6. Technology

Per D8 §13.7 (throw-away discipline):

- **React 18+** with Vite dev server.
- **Tailwind CSS** for utility classes; tokens injected via
  `tokens.css`.
- **Zustand** for workspace state store (matches Sprint 1 intent
  without ceremony).
- **React Router v6** for routing.
- **Framer Motion** for the 200 ms Medium tier crossfades.
- **Lucide React** for icons (locked in Bible v2.1 §5.5).
- **Berkeley Mono / Neue Haas Grotesk / GT Sectra** — self-hosted via
  `@font-face` in `tokens.css`; fall back to system mono / sans /
  serif if licences unavailable during prototype phase (annotate in
  README).

**Explicit throw-away signals:**
- No production build config.
- No SSR / hydration ceremony.
- No production tree-shaking beyond Vite defaults.
- No component test setup (Sprint 1 §D8 §7).

---

## 7. Directory layout

```
/prototype/
  ├─ package.json                       (Vite · React · Zustand · Framer · Tailwind · Lucide)
  ├─ vite.config.ts
  ├─ tailwind.config.ts
  ├─ index.html
  ├─ src/
  │   ├─ tokens.css                     (Bible v2.1 §5 tokens; the design system in CSS variables)
  │   ├─ main.tsx                       (entry)
  │   ├─ App.tsx                        (AppShell)
  │   │
  │   ├─ workspace-state/               (Bible §1.4.4, §1.4.5)
  │   │   ├─ store.ts                   (Zustand — mode · lens · density · pins · CNL fields)
  │   │   ├─ state-memory.ts            (per-surface session-storage slices)
  │   │   ├─ url-sync.ts                (URL ⇄ store)
  │   │   └─ selectors.ts               (derived · milestone detection · etc.)
  │   │
  │   ├─ routing/                       (React Router)
  │   │   └─ routes.tsx                 (module + detail routes per D8 §3.3)
  │   │
  │   ├─ shell/                         (persistent chrome · never re-mounts on nav)
  │   │   ├─ AppShell.tsx
  │   │   ├─ DangerRibbon.tsx
  │   │   ├─ Header.tsx
  │   │   ├─ StatusRail.tsx
  │   │   ├─ LeftRail.tsx
  │   │   ├─ TopTabBar.tsx
  │   │   ├─ RightRail.tsx              (Timeline)
  │   │   ├─ PinsTray.tsx               (Sprint 2 placeholder)
  │   │   ├─ ModeSwitcher.tsx
  │   │   ├─ AdvancedLensToggle.tsx
  │   │   ├─ Palette.tsx                (⌘K)
  │   │   └─ FixtureDebugPanel.tsx      (⌘⇧D · prototype-only)
  │   │
  │   ├─ primitives/                    (15 primitives · D8 §4.P)
  │   │   ├─ Chip.tsx
  │   │   ├─ MetricBlock.tsx
  │   │   ├─ ChartTile.tsx
  │   │   ├─ TableTile.tsx
  │   │   ├─ PipelineStageBar.tsx
  │   │   ├─ ActivityRow.tsx
  │   │   ├─ WorkerCard.tsx
  │   │   ├─ StateTemplate.tsx
  │   │   ├─ ApprovalCard.tsx
  │   │   ├─ EvidenceDrawer.tsx
  │   │   ├─ LineageBar.tsx
  │   │   ├─ ProvenanceTriple.tsx
  │   │   ├─ SignatureFrame.tsx
  │   │   ├─ DivisionCaption.tsx
  │   │   └─ KeyboardShortcutHUD.tsx
  │   │
  │   ├─ feature/                       (F1–F7 · D8 §4.F)
  │   │   ├─ FacetBar.tsx
  │   │   ├─ TimeWindowChip.tsx
  │   │   └─ OptimisticUI.ts            (middleware — rollback path)
  │   │
  │   ├─ modules/                       (surfaces · D8 §4.S)
  │   │   ├─ login/Login.tsx
  │   │   ├─ mission/Mission.tsx
  │   │   ├─ approvals/Approvals.tsx
  │   │   ├─ approvals/ApprovalDetail.tsx
  │   │   ├─ factory/Factory.tsx
  │   │   ├─ strategies/Explorer.tsx
  │   │   ├─ strategies/Passport.tsx    (E1 §6.7 · 11 sections)
  │   │   └─ advanced/Advanced.tsx
  │   │
  │   ├─ fixtures/                      (§5 fixture catalogue)
  │   │   ├─ strategies.ts
  │   │   ├─ approvals.ts
  │   │   ├─ timeline.ts
  │   │   ├─ workers.ts
  │   │   ├─ plans.ts
  │   │   ├─ kill-posture.ts
  │   │   ├─ copilot.ts
  │   │   └─ milestones.ts
  │   │
  │   └─ lib/
  │       ├─ formatters.ts              (Division-voice helpers · timestamp · numeric)
  │       ├─ concept.ts                 (D6: conceptFor · densityFor helpers)
  │       └─ hotkeys.ts                 (⌘K · ⌘M · ⌘⇧A · Esc-cascade)
  │
  └─ README.md                          (prototype scope · walk-through · exit criteria)
```

---

## 8. Build order

Six phases, executed sequentially:

**Phase 1 · Foundation (Day 1–2)**
- `tokens.css` + font loading
- Workspace state store
- URL sync
- State Memory infrastructure
- AppShell + routing skeleton
- Danger ribbon + Status rail (placeholders)
- Fixture Debug Panel

**Phase 2 · Primitives (Day 3–5)**
- All 15 primitives with Storybook-adjacent per-primitive playground
- StateTemplate first (unblocks empty states)
- Chip · MetricBlock · TableTile next
- Others in dependency order (D8 §5)

**Phase 3 · Login + Trust Before Credentials (Day 6)**
- Login screen with 8 pre-auth signals visible
- Session expiry recovery overlay
- Mandatory password change screen

**Phase 4 · Core surfaces (Day 7–10)**
- Mission Control v1 (six panels)
- Timeline right rail with fixture stream
- Approval Center with 4 fixture approvals
- Master Bot Dashboard skeleton
- Strategy Explorer list + full Passport (11 sections)

**Phase 5 · Cross-module wiring (Day 11–12)**
- Rule of Predictable Return in router
- Cross-module highlight via `?strategy=`
- Facet Bar cascade
- Time-window chip cascade
- Mode switch with Decision Identity verified

**Phase 6 · Polish + Walk-through prep (Day 13–14)**
- All D7 empty states connected
- Progressive Confidence milestone fixtures
- Copilot fixture answers
- Six-dimension evaluation harness (per §2)
- README walk-through script

**Total prototype build: ~14 working days for a single engineer, or ~7
days for a pair.**

---

## 9. Walk-through protocol

The operator + designer + lead engineer walk the prototype together.

### 9.1 Session 1 · Discoverability (60 min)

Operator has no prior knowledge of the product. Discovers per §2.1
tests. Observer records:
- Where operator paused, confused, or looked away.
- Which affordances required prompting.
- Which empty states successfully taught.

### 9.2 Session 2 · Navigation Predictability (45 min)

Operator executes the 10-hop test (§2.2). Observer records back-stack
inconsistencies.

### 9.3 Session 3 · Interaction Rhythm + Cognitive Load (90 min)

Simulated 90-min shift with rapid triage + one deep-dive. Observer
records fatigue points, latency budget breaches, motion complaints.

### 9.4 Session 4 · Trust + Identity (45 min)

Operator evaluates §2.5 + §2.6 tests explicitly. Team notes any
anti-pattern that slipped through.

### 9.5 Refinement capture

Each session produces a **refinement log** — a table:

| # | Session | Observation | Proposed refinement | D/E-doc target |
|---|---|---|---|---|
| R1 | Discoverability | ⌘K hint too subtle | Increase hint contrast token | D1 §4 |
| R2 | Navigation | Back after mode-switch felt unexpected | Add subtle mode-change chip | D6 §3.2 |
| ... | ... | ... | ... | ... |

Refinements resolve as **formal D/E-series addenda** — never as
in-code overrides.

### 9.6 Operator Scenario Library — canonical walk-through scripts

Four scenarios execute during prototype review. Each drives the six
evaluation dimensions (§2) through a realistic operator flow. These
scenarios are the *canonical* walk-through scripts — repeatable across
prototype iterations and Sprint 1 acceptance.

#### 9.6.1 Scenario S1 — Executive Morning Review (~5 min)

- **Starting context.** Executive mode. Fresh browser tab. Factory in
  freeze mode with 2 medium-risk approvals pending. Yesterday: 3
  strategies promoted.
- **Tasks.**
  1. Sign in.
  2. Glance at daily posture on landing.
  3. Open Approval Center; read the 2 medium-risk approvals.
  4. Approve 1 · defer 1.
  5. Sign out.
- **Expected navigation.** `/login → /c/mission → /c/approvals →
  /c/approvals/:id → /c/approvals → logout.` Back-stack unwinds cleanly.
- **Expected Decision Identity.** Approval count in header · Attention
  panel · Approval Center all read `2` before action, `0` after.
- **Expected CNL.** Executive mode filter default `risk ≥ medium`
  applies from landing; the deferred approval preserves its filter
  visibility on return.
- **Expected State Memory.** Returning to Approvals after opening the
  detail preserves scroll + selected card highlight.
- **Expected outcome.** Timeline records *"Operator approved …"* and
  *"Operator deferred …"* in Division voice. Session ends clean.
- **Dimensions exercised.** Discoverability · Trust · Identity · Rhythm.

#### 9.6.2 Scenario S2 — Operations Shift Burst (~15 min)

- **Starting context.** Operations mode. Returning operator (has visited
  before). 4 pending approvals · 1 critical Attention item · Master Bot
  running plan #47.
- **Tasks.**
  1. Sign in.
  2. Read "since you were away" divider on Timeline (E4 §3.2).
  3. Investigate the critical Attention item (Passport deep-dive).
  4. Return to Mission Control via three-Esc.
  5. Bulk-approve 3 low-risk approvals.
  6. Handle the medium-risk approval individually.
  7. Deny 1 with reason.
- **Expected navigation.** Mission → Passport → 3× Esc → Mission →
  Approvals → detail → Approvals. Every Back unwinds correctly.
- **Expected Decision Identity.** The critical Attention item and its
  Passport show identical evidence + confidence + risk.
- **Expected CNL.** Advanced-Lens preference persists across shift; time
  window `live ▸` cascades to all surfaces.
- **Expected State Memory.** After the Passport deep-dive, returning
  to Mission Control restores the exact scroll + expanded panels.
- **Expected outcome.** 5 approval events on Timeline. Attention count
  = 0. Optimistic-UI rollback path *not* triggered.
- **Dimensions exercised.** Navigation Predictability · Rhythm ·
  Cognitive Load · Trust.

#### 9.6.3 Scenario S3 — Research Investigation (~30 min)

- **Starting context.** Research mode. Investigating a strategy family
  with drift signals. 1 pending Learning-Division retirement approval
  in queue.
- **Tasks.**
  1. Sign in — lands with Copilot companion docked (D6 §6.5).
  2. Open Strategy Explorer; filter by `Research Division` origin.
  3. Open Passport for strategy #47.
  4. Read Confidence Evolution + Validation Evidence sections.
  5. Ask Copilot *"Why is this strategy's Sharpe declining?"* → follow
     Copilot's citation to a knowledge item (fixture).
  6. Return via ⌘[ — 2 Back presses restore Passport, then Explorer
     with filter intact.
  7. Switch to Operations mode via ⌘M — Passport re-renders with
     Concept-A treatment; Decision Identity holds.
  8. Review the retirement approval in Approvals inline (Everywhere-
     Actionable · E1 §5.7 five-path proof).
  9. Approve retirement.
- **Expected navigation.** Deep-dive-heavy path; Back-stack unwinds
  precisely; mode switch does *not* push stack entry (E5 §7.5).
- **Expected Decision Identity.** Strategy #47's confidence value +
  lineage + evidence identical across Research-mode Passport and
  Operations-mode Passport.
- **Expected CNL.** Explorer filter (`Research Division`) survives the
  Passport deep-dive and returns intact.
- **Expected State Memory.** Copilot session memory preserves the
  question thread across the Passport navigation.
- **Expected outcome.** Retirement approval commits · Timeline records
  in Division voice · Passport section 10 (Retirement information)
  now populated.
- **Dimensions exercised.** Discoverability · Navigation · Trust
  (Copilot Never Invents) · Identity · Rhythm.

#### 9.6.4 Scenario S4 — Incident Response (~10 min)

- **Starting context.** Developer mode. Governance armed kill posture
  4 minutes ago. Errors in ingestion subsystem (fixture).
- **Tasks.**
  1. Sign in — danger ribbon fires in landing crossfade (E2 §9.5).
  2. ⌘K palette pre-opens to developer group (D6 §7.2).
  3. Jump to `errors · last 100`.
  4. Correlate errors with Governance advisory via Timeline filter
     `[actor: error + telemetry]`.
  5. Ask Copilot for a grounded summary.
  6. Copilot cites the 2 relevant Timeline events; provides trace-as-UI
     under Advanced Lens (auto-on in Developer mode).
  7. Return to Mission Control via three-Esc.
  8. Verify kill-posture chip on status rail matches Attention panel.
- **Expected navigation.** ⌘K → destination → filter change → Copilot
  → Back to Mission Control. Every Back unwinds.
- **Expected Decision Identity.** Kill-posture state chip identical
  across danger ribbon, status rail, and Attention panel.
- **Expected CNL.** Developer-mode `error + telemetry` Timeline filter
  survives navigation to Copilot and back.
- **Expected State Memory.** Errors-last-100 scroll position preserved
  when returning from Copilot.
- **Expected outcome.** No approvals committed. Session ends with
  operator handing back to Operations (mode switch); kill posture
  visibly logged in Timeline.
- **Dimensions exercised.** Trust · Cognitive Load (crisis without
  panic) · Rhythm · Navigation.

#### 9.6.5 Scenario execution as walk-through scripts

- Scenarios S1–S4 execute in Sessions 1–4 respectively (§9.1–§9.4).
- Each scenario is repeated once per prototype iteration.
- Deviation from expected navigation / Decision Identity / CNL / State
  Memory triggers a Refinement Log entry.
- Scenarios become **canonical Sprint 1 Playwright test scripts** in
  D8 §7 test coverage.

---

## 10. Refinement addendum protocol

Every accepted refinement follows this process:

1. Refinement filed in `refinement_log.md` from the walk-through.
2. Author writes a **formal addendum** — e.g., `D6_ADDENDUM_MODE_SWITCH_HINT.md`.
3. Addendum includes: rationale · pattern-source (from evaluation) ·
   change spec · impact on other D-docs · sprint acceptance impact.
4. Operator approves the addendum.
5. Prototype updated to reflect the addendum.
6. Addendum count logged in `PRD.md`.

**Rule:** no refinement lands in the prototype without a formal
addendum. This preserves the design-first discipline through the
prototype phase.

---

## 11. Prototype exit criteria — leading to Design Freeze

The prototype exits (and Design Freeze is declared) when:

- ✅ All 6 evaluation dimensions (§2) pass their tests.
- ✅ All refinements captured are approved as addenda.
- ✅ Prototype's Fixture Debug Panel has been exercised (every state
      viewed at least once).
- ✅ Operator has walked the 10-hop Rule of Predictable Return test
      successfully.
- ✅ The 90-min simulated shift has passed the Cognitive Load
      criteria.
- ✅ Screenshot archive captured — 4 modes × 3 postures × 5 primary
      surfaces = 60 frames (Sprint 1 visual-regression baseline).
- ✅ `PRD.md` updated with Design Freeze declaration + addendum count.

**On Design Freeze:**
- The D-series + E-series + accepted addenda become the immutable
  Sprint 1 contract.
- No further design changes without a v-major bump (Bible §20.3).
- Sprint 1 code begins per D8 §11 rollout order.

---

## 12. What P0 does NOT include

- The prototype code itself (built in the phase authored by P0).
- Real-world data (the fixture library replaces this).
- Backend integration.
- User testing beyond operator + designer + lead engineer.
- Formal QA gates (Sprint 1's job).
- Deployment / hosting (the prototype runs locally).

---

## 13. What happens after Design Freeze

Per D8 §16 handoff sequence:

1. **Design Freeze declared** — D-series + E-series + accepted
   addenda are the Sprint 1 contract.
2. **Prototype archived** — becomes the reference artefact for
   Sprint 1 engineers.
3. **Sprint 1 kick-off** per D8 §11 rollout order.
4. **Prototype code is not carried into production** — Sprint 1
   builds afresh with production discipline.
5. **Prototype visual outputs (screenshots · fixtures) inform Sprint
   1 visual-regression baseline.**

**Rule of Prototype Termination.** The prototype's purpose ends at
Design Freeze. Its code does not become Sprint 1 code; its lessons do.

---

## 14. Backend Feature Freeze compliance

The prototype touches no backend. All data comes from
`fixtures/*.ts`. All state comes from the workspace state store.
Feature Freeze is trivially respected because no real backend is
invoked.

**Post-Design-Freeze, Sprint 1** integrates with the existing (frozen)
backend endpoints via the adapters listed in D8 §4.F4–F7 and E1 §11
(`services/strategy.js`). No new endpoints. No backend changes.

---

## 15. Next steps

1. **Operator reviews and approves P0.**
2. Prototype build begins per §8 (14 working days for single engineer;
   7 for a pair).
3. Six-session walk-through (§9) — approximately 4 hours of operator
   time distributed across the walk-through window.
4. Refinement addenda authored per §10.
5. Design Freeze declared per §11.
6. Sprint 1 kick-off per D8 §16.

---

*End of P0 — Interactive Prototype Blueprint.*

*The prototype gate is designed with the same discipline that
governed the D-series and E-series. Craftsmanship over speed.
Blueprint before code. Six evaluation dimensions codified. Refinement
addendum protocol locked. Backend Feature Freeze preserved.*

*Awaiting operator approval before prototype build begins.*

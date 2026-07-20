# D4 — Master Bot & AI Workforce Org Chart

> Codifies the CEO metaphor. Master Bot as the executive; the 8-division
> Workforce as its organization; every worker as a legible citizen with
> visible state, plan, lineage and voice.
>
> Layered on Bible **v2.1** (see `FRONTEND_DESIGN_BIBLE_V2_1.md`), D1
> visual system, D2 storytelling standard, D3 approval integration.
>
> Signature graphic **G1** (Bible §23) is codified here.
>
> Prepared 2026-07-20 · after Design Inspiration Study approval, folded
> deltas applied.

---

## 0. Design Principles Checklist (15 items — permanent quality gate)

Every design deliverable D2 onward must confirm all items before it is
considered complete. D4 confirms:

- [x] **Invisible Luxury** — CEO metaphor conveyed through composition, typography and ambient pulse; zero mascot art, zero avatar decoration, no gradient halos on the Master Bot chip.
- [x] **Everything Connected** — Master Bot Plan Contract shows every step's lineage; each worker card carries a lineage link; every approval-gate step cross-links to Approval Center (D3) and Timeline (D2).
- [x] **Progressive Disclosure** — Simple shows Plan + 8-division grid + last decisions; Advanced adds state-history micro-lines, worker sub-attribution, latency chips, transition history, and Copilot trace panel.
- [x] **Evidence First** — no worker is "Completed"; each card cites current state + last artefact + evidence link; every plan step cites its confidence / method under Advanced Lens.
- [x] **Persona Awareness** — Executive sees Master Bot header + summary chart only; Operations sees full plan + org chart; Research filters to Research/Mutation/Learning divisions; Developer sees Advanced + diagnostic actors.
- [x] **Mission Control First** — Master Bot header chip lives in the shell; every screen from every module shows the current plan step in the status rail extension.
- [x] **Accessibility** — WCAG 2.2 AA; keyboard-only navigation of plan steps + worker cards; screen-reader `role="list"` on the org chart; ambient pulse suspends under `prefers-reduced-motion`.
- [x] **Motion Discipline** — 200 ms card enter · 2 s ambient pulse ONLY when a worker is `running` · 320 ms plan-step transition · zero decorative animation on the Plan Contract.
- [x] **Design Token Compliance** — every colour from Bible v2.1 §5 tokens; typography from §5.2 (Berkeley Mono metrics · Neue Haas Grotesk body · GT Sectra on Executive briefing).
- [x] **Six-Signal Rule** — worker state chips draw only from `--sig-*`; divisional accents come from the 8-hue chart palette (Bible v2.1 §5.1 chart palette), used sparingly.
- [x] **Lineage Validation** — every worker card and every plan step exposes a `→ view evidence` and `→ open lineage graph` (Bible v2.1 §10.2); org chart hand-off edges are the lineage they represent.
- [x] **Empty-State Quality** — 6 authored states (§13): dormant division, off-shift, all-idle, awaiting-plan, worker-offline, plan-completed.
- [x] **Consistency** — reuses D1 §7.6 Worker card, D1 §7.5 Approval card (for HITL gates), D2 Timeline row, `<FacetBar>` (Bible §11.6), `<TimeWindowChip>` (Bible §7.13).
- [x] **Explainability** — every plan step reads *What · Why · What next* in Division voice (D2 Addendum); worker card reads *Who · Doing what · With what · Producing what*.
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice throughout; internal worker IDs Advanced-only.
- [x] **Context Never Lost (Bible v2.1 §1.4.4)** — selecting a worker on the org chart preserves the selection when navigating to Timeline / Approvals / Knowledge; time-window chip cascades to plan history.
- [x] **Purpose Before Status** — every Division section and every worker card answers *Why do I exist · What am I doing · What value do I produce · What happens next* in that order. State chips report *what is*; purpose copy reports *why it matters*.

---

## 1. Purpose

The Factory operates autonomously. The operator's job is to **observe an
intelligent organisation at work** — not to manage tasks, not to launch
runs, not to inspect Redis keys. This surface embodies that stance.

Two intertwined artefacts govern the module:

1. **Master Bot Dashboard** — the CEO surface. What the Factory is trying
   to accomplish right now, its current plan, and the last decisions
   it has made.
2. **AI Workforce Org Chart** — the organisation. Eight divisions, each
   with worker cards showing division-voice state.

Together they answer operator questions Q2 (*What is the Factory doing
right now?*) and Q3 (*What has AI accomplished?*) in a single scroll.

**Anti-goals** (what this surface must never become):

- A task-management UI (operators don't assign tasks).
- A Kubernetes / container dashboard (Layer 5 only).
- A monolithic diagnostic dump (that's Advanced).
- A mascot / avatar showcase (undermines premium positioning).

---

## 2. Placement & layout

The Factory module (`/c/factory`) opens with Master Bot at the top,
followed by the Workforce Org Chart, then Recent Cycles (history).
Standard shell chrome (LeftRail, TopTabBar, StatusRail, right rail
Timeline) remains persistent.

```
┌──────────────────────────────────────────────────────────────────┬────────┐
│  FACTORY  ·  Master Bot @v55                                     │        │
│                                                                  │        │
├──────────────────────────────────────────────────────────────────┤        │
│  MASTER BOT DASHBOARD                                            │  AI    │
│  (objective · plan contract · last decisions · handoffs)         │        │
│                                                                  │        │
├──────────────────────────────────────────────────────────────────┤ ACT.   │
│  AI WORKFORCE ORG CHART                                          │        │
│  (8 divisions · worker cards · division hand-off edges)          │  TIME  │
│                                                                  │        │
├──────────────────────────────────────────────────────────────────┤        │
│  RECENT CYCLES (last 20)                                         │        │
│                                                                  │        │
└──────────────────────────────────────────────────────────────────┴────────┘
```

- **Workstation** (≥ 1440 px): 3-column workforce grid; Master Bot as a
  hero panel spanning full width.
- **Tablet** (900–1439 px): 2-column workforce grid; Master Bot compacted.
- **Briefing** (≥ 1920 px cinema): Master Bot occupies 2/3, workforce
  reduces to a horizontal *division strip* summary.

**Shell-level extension.** The Master Bot chip appears in the header
next to the approvals chip on every module:

```
[ ● 4 approvals ]   [ ● master bot · optimising 3 candidates ]
```

Click either → jumps to the relevant surface with Context Never Lost
preserved (Bible v2.1 §1.4.4).

---

## 3. Master Bot Dashboard anatomy

The Master Bot is the CEO of an autonomous research firm. Its dashboard
answers four questions in order:

1. **Who am I?** — identity + posture
2. **What am I trying to accomplish?** — current objective
3. **How am I doing it?** — the plan contract (§4)
4. **What have I decided recently?** — last decisions (§6)

### 3.1 Identity strip (top row)

```
┌─────────────────────────────────────────────────────────────────────┐
│  MASTER BOT · @v55                             ● healthy · 4d 02:11 │
│  Coordinating Research · Mutation · Learning · Portfolio            │
└─────────────────────────────────────────────────────────────────────┘
```

- Version chip: mono, `--content-md`.
- Posture chip: `● healthy` / `◐ degraded` / `⨯ paused` / `⨯ compile-failed`,
  drawn from `--sig-*` tokens.
- Uptime: relative, mono, `--content-lo`.
- Subtitle: divisions actively coordinated *right now* (a live sentence,
  not a static label).

### 3.2 Objective panel (below identity)

```
┌─────────────────────────────────────────────────────────────────────┐
│  CURRENT OBJECTIVE                                                  │
│                                                                     │
│  Ship 3 verified strategies for FTMO-100k evaluation.              │
│  Target completion 4 h · ETA on-track                              │
│                                                                     │
│  [ pinned by operator · 2 h ago ]     [ change objective ▾ ]        │
└─────────────────────────────────────────────────────────────────────┘
```

- One-sentence objective in Division voice.
- Target completion + ETA chip (on-track / at-risk / off-track — colours
  from `--sig-*`).
- Provenance chip: who set the objective, when.
- `change objective ▾` opens the Objective Selector drawer (out of scope
  for Sprint 1 — Sprint 3).

### 3.3 Handoff strip

A signature-graphic strip below the objective panel shows the currently
active handoffs between divisions:

```
Research  →  Mutation  →  Validation  →  Certification  →  Portfolio → Master Bot
     ●            ●              ○                 ○               ○
```

- Filled `●` = currently producing an artefact for the next stage.
- Hollow `○` = queued.
- Edges animate a subtle 2-second directional light-pulse when active
  (Concept B ambient · respects `prefers-reduced-motion`).

---

## 4. Plan Contract surface (P21 codified)

The Plan is the Master Bot's public promise: an ordered list of steps
each with state, ETA, outcome and evidence. The operator reads the plan
top-to-bottom, in Division voice.

### 4.1 Plan step anatomy

```
CURRENT PLAN · @47
┌────────────────────────────────────────────────────────────────────┐
│ ✓  1. Research Division generated 5 EURUSD candidates              │
│                                              completed 12:14 · 4 min│
│                                              →  view evidence      │
├────────────────────────────────────────────────────────────────────┤
│ ✓  2. Validation Division ran 30-day walk-forward                  │
│                                              completed 12:22 · 8 min│
│                                              →  view evidence      │
├────────────────────────────────────────────────────────────────────┤
│ ▸  3. Mutation Division is optimising the top 3 candidates         │
│                                              running · worker-02   │
│                                              ETA 3 min             │
│                                              →  view live evidence │
├────────────────────────────────────────────────────────────────────┤
│ ○  4. Certification Division will check FTMO rules                 │
│                                              queued                │
├────────────────────────────────────────────────────────────────────┤
│ ⏸  5. Master Bot needs operator approval                           │
│                                              awaiting operator     │
│      "Approve promotion of top candidate to Portfolio."            │
│                                              →  open approval  →   │
├────────────────────────────────────────────────────────────────────┤
│ ○  6. Portfolio Division will add candidate to shortlist           │
│                                              queued                │
├────────────────────────────────────────────────────────────────────┤
│ ○  7. Master Bot will notify Execution Division                    │
│                                              queued                │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Step states (6 canonical)

| Icon | State | Meaning | Colour |
|------|---|---|---|
| `✓`  | **completed** | step finished successfully | `--sig-ok` |
| `▸`  | **running** | active right now | `--sig-info` + ambient pulse |
| `○`  | **queued** | not yet started | `--content-lo` (dormant grey) |
| `⏸`  | **awaiting operator (HITL gate)** | approval required to proceed | `--sig-warn` |
| `⨯`  | **failed** | step aborted | `--sig-crit` |
| `⤴`  | **rolled back** | previously completed but reverted | `--sig-advisory` |

### 4.3 HITL gate as in-plan node (P22 codified)

A `⏸` step is an approval **inside** the plan. When the plan reaches it:

- Master Bot pauses the plan.
- The Approval Center receives the request (per D3 §3 · Master Bot origin).
- The plan step shows the recommendation summary inline + a **cross-link**
  `→ open approval →` navigating to the specific card in Approval Center
  (Context Never Lost preserved — returning to the Factory module restores
  scroll and selection).
- Approving in the Center or expanding-and-approving in the Timeline (D2
  §5 Highlighted state) resolves the gate; plan advances to next step.

**Rule:** the plan is the source of truth. If a card is approved elsewhere
(Timeline expansion, Approval Center), the plan step updates within one
Timeline poll (200 ms medium tier), no reload required.

### 4.4 Simple vs Advanced Lens

**Simple:** step number · state · Division-voice sentence · outcome/ETA ·
optional evidence link.

**Advanced** additionally exposes below each step:
```
    [ walk-forward · 30 d ]   [ conf 0.87 ]   [ dur 8 min ]   [ worker-02 · research ]
```
— method / confidence / duration / worker sub-attribution chips
(mono, `--font-caption`, `--content-md`).

### 4.5 Plan history (Advanced-Lens only, below current plan)

```
PREVIOUS PLANS · scroll for older
▾  Plan #46 · completed 09:42 · 3 h 18 min · 2 candidates shipped
▾  Plan #45 · completed yesterday 22:11 · aborted at step 4 (Validation)
▾  Plan #44 · completed yesterday 18:03 · 1 candidate shipped
```

Click any plan → collapses the current plan and shows the historical one.
Time-window chip (Bible v2.1 §7.13) applies. Preserves Context Never Lost.

---

## 5. Workforce Org Chart (Signature Graphic G1)

Below the Master Bot Dashboard sits the org chart — the 8 divisions of
the AI workforce, each division a section with worker cards.

### 5.1 Divisions (extends D2 Addendum §4)

Eight divisions. Fixed. The operator sees the same eight everywhere.

| # | Division | Public name in copy | Master Bot's colour hue* |
|---|---|---|---|
| 1 | Research | **Research Division** | c0 `#4ea1f3` (sky) |
| 2 | Mutation | **Mutation Division** | c1 `#8b8ffb` (violet) |
| 3 | Validation | **Validation Division** | c2 `#3ddc84` (green) |
| 4 | Certification | **Certification Division** | c3 `#f0b429` (amber) |
| 5 | Portfolio | **Portfolio Division** | c5 `#5ecab5` (teal) |
| 6 | Execution | **Execution Division** | c7 `#b8935f` (gold) |
| 7 | Learning | **Learning Division** | c6 `#d17bff` (magenta · rare) |
| 8 | Knowledge | **Knowledge Base** | c4 `#ff5b5b` used as advisory-only tint |

*Divisional hue is used **only** as a 3-pixel top accent stroke on the
worker card, never as fill. Six-signal ceiling protected.

Two more entities live outside the eight but are legible in the org chart:

- **Master Bot** — pinned at top of the chart as the CEO node.
- **Governance** — pinned at the bottom as the watcher; not a division
  producing artefacts.
- **Maintenance / Monitoring** — auxiliary workers surfaced only in
  Advanced Lens.

### 5.2 Division section anatomy

Every division section opens with a **purpose header** answering the four
questions from §5.1.1 in Division voice.

```
┌─────────────────────────────────────────────────────────────────────┐
│  RESEARCH DIVISION                          ● 2 running · 1 idle    │
│                                                                     │
│  Why       Discovers, retrieves and validates external research     │
│            that could seed new trading strategies.                  │
│  Now       Coordinating on regime-detection research.               │
│  Produces  Candidate strategies + curated knowledge items.          │
│  Next      Handoff to Mutation Division once 3 candidates score     │
│            above the confidence threshold.                          │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│   │ worker-01    │  │ worker-02    │  │ worker-03    │              │
│   │ ● running    │  │ ● running    │  │ ○ idle       │              │
│   │              │  │              │  │              │              │
│   │  ...         │  │  ...         │  │  ...         │              │
│   └──────────────┘  └──────────────┘  └──────────────┘              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

Field style:
- Labels `Why · Now · Produces · Next` — `--font-caption` UPPERCASE
  spaced, `--content-lo`, mono-width column so labels align.
- Values — `--font-body-sm`, `--content-md`, Division voice.
- Purpose (`Why · Produces`) is *timeless* — it does not update on
  every poll. Subject (`Now · Next`) updates live.
- Under Advanced Lens, `Produces` adds the artefact-type chip
  (`[artefact: strategy]`, `[artefact: kb-item]`, etc.).

**Persona shortcuts:**
- Executive: `Why` + `Produces` shown; `Now` + `Next` collapsed to a
  single narrative sentence.
- Operations: all four visible (default).
- Research: `Why` shown once at module entry, then folded to a hoverable
  tooltip to save vertical space on the researcher's active surface.
- Developer: adds `[division: research]`, worker-count telemetry.

### 5.3 Worker card anatomy (extends D1 §7.6)

Every worker card follows Purpose Before Status (§5.1.1). Its permanent
purpose line answers *Why + Produces* in one sentence; below sit the
transient state, current subject and next handoff.

```
┌────────────────────────────────┐
│  research · worker-01          │  ← divisional caption, mono
│                                │
│  Retrieves and scores fresh    │  ← PURPOSE (timeless · Why + Produces)
│  regime-detection research.    │
│                                │
│  ● running                     │  ← STATE (transient)
│  idle → running · 3.4 min      │  ← state-history micro-line (P23)
│                                │
│  Now  scoring arxiv:2401.09883 │  ← SUBJECT (transient)
│                                │
│  Next handoff to Mutation once │  ← WHAT HAPPENS NEXT
│       score ≥ 0.70             │
│                                │
│  ──── last artefact ────       │
│  strat_bb_ema_rsi_v3           │
│  P validated                   │
│                                │
│  →  view evidence              │
│  →  lineage graph              │
│  📌  pin worker                │
└────────────────────────────────┘
```

**Reading order (top to bottom):** identity → purpose → state → subject
→ next → outcome → actions. This ordering is not decorative — it is the
Purpose Before Status principle rendered as layout.

**Fields:**

| Field | Simple | Advanced (adds) |
|---|---|---|
| Divisional caption | `research · worker-01` | + `pod-1a`, `p95 84 ms`, `restarts 0` |
| **Purpose (Why + Produces)** | 1 sentence, timeless, Division voice | + artefact-type chip |
| Current state chip | `● running` | + `since 12:24 UTC` |
| State-history micro-line (P23) | `idle → running · 3.4 min` | + full transition list expandable |
| **Now (Subject)** | one line, Division voice | + confidence, method chips |
| **Next (Handoff / transition)** | one line, Division voice | + ETA, downstream division chip |
| Last artefact | mono id + P/W/F/A chip | + provenance triple |
| Actions | `view evidence · lineage graph · pin worker` | + `open worker inbox`, `restart worker` (governance-gated) |

**Divisional accent:** 3 px top stroke in the division hue (§5.1).

**Idle worker rendering.** Idle workers keep their **Purpose** and
**Next** lines at full opacity — a resting worker still communicates
value. State + Subject dim to `--content-lo`. This is the essence of
Purpose Before Status — a paused worker is still a legible member of
the organisation.

### 5.4 Worker states (5 canonical)

| Icon | State | Ambient motion |
|------|---|---|
| `●` | **running** | 2 s ambient pulse on the chip (Concept B halo · Bible §5.4 luminance) |
| `○` | **idle** | none · card dims to `--content-lo` |
| `◐` | **degraded** | none · chip slow-blink 2 s cycle |
| `⨯` | **offline** | none · chip solid `--sig-crit` · card faded 20 % |
| `⏸` | **paused (Governance)** | none · chip `--sig-warn` |

### 5.5 Division hand-off edges (G1 signature motion)

Between division sections, subtle connecting edges show current
inter-divisional flow (which division is handing what to which).

- Rendered as a thin `--stroke-2` line from the *"last artefact"* row of
  one division to the *"current subject"* row of the next.
- Only rendered when actually flowing.
- Motion: 320 ms slow tier — light traces the line direction on hand-off
  event.
- No edge is drawn between divisions that are not currently coupled.
  A quiet org chart is a healthy resting org chart.

---

## 6. Last decisions log

Below the org chart, a compact reverse-chronological list of the last
6 decisions Master Bot has made. Each row is a Division-voice sentence
in the D2 Timeline pattern.

```
LAST DECISIONS
─────────────────────────────────────────────────────
[12:24]  Master Bot promoted EURUSD Breakout v3 to Portfolio candidacy.
                                                          →  view evidence
[12:16]  Master Bot rejected strat_bb_ema_rsi_v3 · Sharpe below 1.0.
                                                          →  view evidence
[12:12]  Master Bot asked Mutation Division to optimise top 3.
                                                          →  view live plan
[12:07]  Master Bot approved Learning Division's dedup threshold change.
                                                          →  view approval
... (last 6)
```

Under Advanced Lens each row adds `[method] [confidence] [duration]`
chips inline.

Click any row → opens the Timeline (D2) scrolled to and highlighting that
event. Context Never Lost: returning to Factory restores scroll +
selection.

---

## 7. Governance visibility (bottom of org chart)

```
┌─────────────────────────────────────────────────────────────────────┐
│  GOVERNANCE                                    ● 0 open advisories  │
│  Six hard rails · watching every artefact promotion                 │
│                                                                     │
│  ─── last 5 governance actions ────────────────────────────────      │
│  · promoted EURUSD Breakout v3 · trust_tier verified · 12:12         │
│  · flagged strat_donchian_atr_v2 for operator review · 09:42        │
│  · approved dedup threshold change · yesterday                       │
│  · [+ 2 more · view all]                                             │
└─────────────────────────────────────────────────────────────────────┘
```

Governance sits deliberately at the *bottom* — it watches, it does not
lead. Its role in the org chart is honesty, not authority.

---

## 8. Lineage & Pinned Preview integration

### 8.1 Lineage from a worker (Bible v2.1 §10.2)

Every worker card exposes `→ lineage graph`. Clicking opens the Lineage
Graph drawer scoped to that worker's produced artefacts. Ancestors show
the inputs the worker consumed; descendants show what its output fed
into.

### 8.2 Pinned Preview integration (Bible v2.1 §7.12)

Any worker card is pinnable. Pinning a worker adds a chip to the
workspace pins tray. From the tray:

- **Open Evidence Drawer** for the worker.
- **Compare 2 workers side by side** — a 2-up split showing their current
  state, plans, artefacts.

**Applicability:** operators use this to compare Research workers running
different research directions, or to compare Execution workers on
different brokers.

---

## 9. Facet grammar & Time-window

Consistent with Bible v2.1 §11.6 and §7.13, the Factory module carries:

```
[ All divisions ▾ ]   [ Worker state ▾ ]   [ Time-window: live ▸ ]   [ q ⌘K ]
```

- **All divisions ▾** — multi-select of the 8 divisions.
- **Worker state ▾** — running / idle / degraded / offline / paused.
- **Time-window** — cascades to plan history (§4.5), decisions log (§6),
  and (Sprint 2+) org chart historical state.
- **⌘K** — palette scoped to factory-actions.

Facet state persists per session and follows the operator into other
modules (Bible v2.1 §1.4.4).

---

## 10. Persona treatment

### 10.1 Executive (Concept-C dominant)

- Master Bot Dashboard is shown; the org chart is *collapsed* to a
  horizontal division-summary strip.
- No worker cards visible by default.
- Plan uses serif primary text (`GT Sectra`) on the top-level headline.
- No ambient pulse.
- Last decisions shown as narrative sentences only, no chips.

### 10.2 Operations (Concept-A default)

- Full anatomy §2 layout.
- All 8 divisions expanded.
- Ambient pulse on running workers.
- Advanced Lens available; default off.

### 10.3 Research (Concept-B dominant)

- Divisions filtered by default to Research, Mutation, Validation, Learning.
- Softer corners (14 px) on worker cards.
- Ambient sparkle around running workers (Concept-B luminance halo).
- Adds `→ knowledge graph` link on Research worker cards (opens G3 focused
  on that worker's research corpus).

### 10.4 Developer

- Advanced Lens auto-on.
- Adds Maintenance and Monitoring divisions (surfaced only in this mode).
- Worker card shows internal pod-name, container-id, worker-uuid — the
  L5 attribution otherwise hidden.
- Adds diagnostic actors from D2 §4 (`error`, `telemetry`, `env`) to the
  decisions log.

---

## 11. Motion physics

- **Plan step entry** — 200 ms fade + 6 px `translateY(-6)`, staggered
  40 ms with other steps.
- **Plan step state change** — 320 ms fade of the icon (Slow tier); the
  Division-voice sentence updates in-place with 120 ms crossfade.
- **Worker card enter** — 200 ms fade; on first mount, 40 ms per-card
  stagger inside a division section (Concept-B surfaces get a soft glow
  when running).
- **Ambient pulse (running worker only)** — 2 s ease-in-out infinite, 6 %
  scale, 15 % opacity variance. Never on idle / degraded / offline /
  paused cards.
- **Hand-off edge trace** — 320 ms directional light-pulse on hand-off
  event; no continuous animation.
- **Org chart reflow (division collapse / expand)** — 200 ms height
  animation; child cards enter with 40 ms stagger.
- **Approve action on HITL gate** — plan step transitions `⏸ → ✓` with
  320 ms icon crossfade; next step transitions `○ → ▸` immediately after.

Reduced-motion (`prefers-reduced-motion`): all motion collapses to
opacity fades only.

---

## 12. Accessibility

- Plan Contract rendered as `role="list"` with each step as `role="listitem"`
  and an `aria-label` composed of `{step number}. {state}. {sentence}`.
- Worker cards `role="article"` with `aria-labelledby` on the divisional
  caption.
- State chips have `aria-label` composed of `{state} · {duration}` (e.g.,
  `running · 3.4 min`).
- Keyboard: `↑/↓` navigates plan steps; `→` opens the highlighted step's
  evidence; `Enter` on a plan step opens Approval Center scoped to that
  step (HITL gates only).
- Focus ring 2 px `--sig-info`.
- Screen-reader announcement on plan step change: `"step {n} · now {state}
  · {headline}"` (debounced to ≤ 1 announcement per 3 s).
- Divisional hue accents also carry a text-glyph fallback for colour-blind
  operators.
- Motion respect `prefers-reduced-motion`.
- Every action has `data-testid` per Bible §17.

---

## 13. Empty / loading / error / dormant states

### 13.1 `awaiting-plan`
```
[ icon · sparkles ]

Master Bot has no active plan yet.
Set an objective to begin.

→  set objective   ·   view previous plans
```
Colour `--sig-dormant`.

### 13.2 `all-idle`
```
[ icon · moon ]

The Factory is at rest.
All 8 divisions healthy · no work in progress.

→  view scheduler   ·   view last plan
```

### 13.3 `dormant-division`
```
[ icon · shield · muted ]

DORMANT · Knowledge Base is gated by Phase C activation.
Retrieval workers appear once the Coherent UKIE Activation
plan reaches Phase C.

→  view activation plan
```
**Never red. Never offer Retry.**

### 13.4 `worker-offline`
```
worker card renders with:
  ⨯ offline · 12 min · restart pending
  →  view scheduler   ·   report issue
```
Chip `--sig-crit`; card faded 20 %.

### 13.5 `plan-completed`
```
[ icon · check ]

Plan #47 completed.
2 candidates shipped · 3 h 08 min · 0 rollbacks.

→  view outcome evidence   ·   plan history
```
Auto-shows for 8 s, then collapses into plan history.

### 13.6 `off-shift`
```
[ icon · pause ]

Governance has paused the Factory.
Reason: kill-posture armed · 4 h ago.

→  view kill posture   ·   view governance log
```
Chip `--sig-warn`.

---

## 14. Data contract (frontend expectation)

The Factory module composes data from existing backend endpoints. No new
backend endpoints required — Feature Freeze respected.

```ts
type MasterBotSnapshot = {
  version: string;                     // "@v55"
  posture: 'healthy' | 'degraded' | 'paused' | 'compile-failed';
  uptime_sec: number;
  objective: {
    id: string;
    headline: string;                  // Division voice
    target_completion: string;         // ISO
    eta_status: 'on-track' | 'at-risk' | 'off-track';
    pinned_by: string;
    pinned_at: string;
  };
  current_plan: Plan;
  plan_history: PlanSummary[];         // last 20
  handoffs: Handoff[];
  last_decisions: TimelineEvent[];     // 6 latest; see D2 §12
  divisions: Division[];               // 8 (+ Governance + optional Maintenance/Monitoring)
  governance: {
    open_advisories: number;
    recent_actions: TimelineEvent[];
  };
};

type Plan = {
  id: string;                          // "@47"
  steps: PlanStep[];
  started_at: string;
  target_completion?: string;
};

type PlanStep = {
  index: number;
  state: 'completed' | 'running' | 'queued' | 'awaiting-operator' | 'failed' | 'rolled-back';
  headline: string;                    // Division voice, single sentence
  division: DivisionName;
  worker_id?: string;                  // Advanced-Lens only
  completed_at?: string;
  duration_ms?: number;
  eta_ms?: number;
  evidence_ref?: string;
  approval_id?: string;                // when state = awaiting-operator (HITL gate)
  advanced?: {
    method?: string;
    confidence?: number;
    provenance?: { origin: string; trust_tier: string; signed_by: string };
  };
};

type Division = {
  name: DivisionName;                  // e.g., "Research Division"
  purpose_why: string;                 // timeless · Division voice · "Why do I exist"
  purpose_produces: string;            // timeless · Division voice · "What value do I produce"
  headline_now: string;                // transient · Division voice · what the division is doing right now
  headline_next: string;               // transient · Division voice · what happens next
  workers: Worker[];
};

type Worker = {
  id: string;                          // "worker-01"
  division: DivisionName;
  purpose: string;                     // timeless · Division voice · Why + Produces in one sentence
  state: 'running' | 'idle' | 'degraded' | 'offline' | 'paused';
  state_since: string;                 // ISO
  state_history_line: string;          // "idle → running · 3.4 min"
  current_subject?: {                  // "Now" — transient
    label: string;                     // Division voice
    href?: string;
  };
  next_handoff?: {                     // "Next" — transient
    label: string;                     // Division voice, e.g., "handoff to Mutation once score ≥ 0.70"
    downstream_division?: DivisionName;
    eta_ms?: number;
  };
  last_artefact?: {
    id: string;
    label: string;
    stage: 'P' | 'W' | 'F' | 'A' | 'I';
    href: string;
  };
  advanced?: {
    pod_id?: string;
    container_id?: string;
    p95_latency_ms?: number;
    restart_count?: number;
    transition_history?: Array<{ from: string; to: string; at: string }>;
  };
};

type Handoff = {
  from: DivisionName;
  to: DivisionName;
  active: boolean;
  artefact_ref?: string;
};
```

**Adapter** in `services/factory.js` normalises heterogeneous existing
endpoints into `MasterBotSnapshot`:

- `/api/master-bot/*` — objective, plan, decisions, posture.
- `/api/ai-workforce/*` — divisions + workers.
- `/api/factory-supervisor/notifications` — governance advisories.
- `/api/audit-log` — historical decisions (plan history, decisions log).

**Feature Freeze respected.** All adapter work is pure frontend.

---

## 15. Factory Replay compatibility

Every element in D4 accepts an optional `at: ISO` prop and honours the
time-window chip (Bible v2.1 §7.13) cascading from any surface:

- Plan Contract accepts `at` → renders the plan as it existed at that
  time (which step was running, which had completed, etc.).
- Worker card accepts `at` → renders the worker's state as of that time
  (idle / running / offline).
- Handoff strip accepts `at` → renders which handoffs were active then.
- Decisions log accepts `at` → renders decisions made *before* that time.

**Sprint N recipe:** Factory Replay page renders the Factory module with a
scrubber-controlled `at` prop. Every existing D4 component already
accepts it. Zero rebuild required.

---

## 16. Context Never Lost — D4 verification checklist

Per Bible v2.1 §1.4.4, the Factory module must preserve:

- [x] Selected worker (highlighted on Workforce Org Chart after navigating
      away and back).
- [x] Selected division filter (per-session).
- [x] Time-window chip cascades to Plan history + Decisions log.
- [x] Scroll position within the module.
- [x] Advanced Lens toggle.
- [x] Pinned Preview tray (persistent workspace-wide).
- [x] Navigation to Approval Center via HITL gate cross-link returns with
      selection intact.
- [x] Navigation to Timeline via decision-log row returns with selection
      intact.

---

## 17. Sprint 1 acceptance criteria (Master Bot slice)

Per Bible v2.1 §17 — Master Bot + Workforce ships only if:

- ✅ 15-item Design Principles Checklist confirmed (§0)
- ✅ Purpose Before Status (§5.1.1) rendered on every Division section and every worker card
- ✅ Master Bot Dashboard renders §3 anatomy end-to-end
- ✅ Plan Contract renders 6 canonical step states (§4.2)
- ✅ HITL gate cross-links to Approval Center (§4.3) and back with context preserved
- ✅ Workforce Org Chart renders 8 divisions + worker cards (§5)
- ✅ Worker card includes state-history micro-line (§5.3 · P23)
- ✅ Handoff strip animates only on actual hand-off events (§5.5)
- ✅ Governance section rendered at bottom (§7)
- ✅ Lineage Graph and Pinned Preview integrations wired (§8)
- ✅ `<FacetBar>` + `<TimeWindowChip>` used (§9 · Bible §11.6, §7.13)
- ✅ 6 empty/loading/error/dormant states authored (§13)
- ✅ All 4 persona treatments verified (§10)
- ✅ Motion physics (§11) — verified with `prefers-reduced-motion`
- ✅ A11y (§12) — axe-core passes; keyboard walk complete
- ✅ Adapter `services/factory.js` implemented (§14)
- ✅ Factory Replay reservations honoured (§15) — `at` prop on every component
- ✅ Context Never Lost verified (§16)
- ✅ Screenshot in workstation + tablet + briefing per persona
- ✅ `data-testid` on every interactive element

---

## 18. What D4 does NOT include

- Coded prototype — belongs to Sprint 2 (Master Bot dashboard is a
  Sprint 2 deliverable per Bible v2.1 Appendix B).
- Objective editor (`change objective ▾` UI) — Sprint 3.
- Restart-worker action (Advanced) — Sprint 4 (governance-gated).
- Historical Workforce Org Chart replay (worker state at time T) — Sprint N
  when Factory Replay ships (§15 reservation only).
- Full division copy library (headlines for every possible division state)
  — that's D7's job.
- Master Bot compile-detail surface (currently lives in NotificationDrawer
  via danger ribbon) — separate diagnostic module.

---

## 19. Next: D5 — Signature-graphic gallery

Per Bible v2.1 §25. D5 codifies G2 – G8:

- G2 Strategy Pipeline Ribbon
- G3 Knowledge Graph (shares implementation with Lineage Graph §10.2)
- G4 Market Coverage Heatmap
- G5 Execution Quality Constellation
- G6 Portfolio Risk Surface
- G7 Learning Evolution Timeline
- G8 Neural Sparkline Strip

Each with: purpose, data → visual mapping, degrade rules, interaction
spec, empty states, motion physics, Pinned Preview / Lineage Graph
integration where applicable.

Expected timeline: 3–4 days.

---

*End of D4 — Master Bot & Workforce Org Chart.*
*All 15 checklist items confirmed. Context Never Lost integrated. Bible
v2.1 deltas applied throughout. Awaiting your review before D5 begins.*

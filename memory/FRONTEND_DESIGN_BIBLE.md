# Strategy Factory — Frontend Design Bible v1.0

> **Canonical design document.** Every future frontend change is measured against this.
> **Status:** Draft v1.0 — awaiting operator sign-off before Sprint 1 begins.
> **Author:** Lead Product Architect / UX Architect / UI Designer / Operator Experience Designer.
> **Compiled:** 2026-07-20.
> **Companion documents:** `FRONTEND_AUDIT_AND_ROADMAP.md` (audit), `BACKEND_FEATURE_FREEZE.md`, `COHERENT_UKIE_ACTIVATION_PLAN.md`.
>
> **Reading order for new team members:** §1 → §2 → §5 → §7 → §12. Everything else is reference.

---

## Table of contents

1. Product philosophy
2. The six operator questions (north star)
3. Information architecture — five layers
4. Navigation hierarchy
5. Design system — foundations
6. Motion principles
7. Component library
8. Dashboard & module layouts
9. AI interaction patterns
10. Evidence visualization standards
11. Approval workflow
12. Master Bot & AI Workforce visualization
13. Data quality & infrastructure visualization
14. Notification philosophy
15. Empty / loading / error / dormant state standards
16. Responsiveness — desktop / tablet / briefing
17. Accessibility guidelines
18. Operator workflows (login → daily → approvals → admin)
19. Naming, iconography & copy standards
20. Extensibility & governance of this document

---

## 1. Product philosophy

Strategy Factory's frontend is not a CRUD interface. It is the **cockpit of an autonomous AI research and operations organization**. The operator's role is to *observe, understand, decide.* Not to manage. Not to click through wizards. Not to remember which page has which button.

**The operator should feel that the Factory is alive, intelligent, and working — even when they are not looking.**

Design bar-set:

| Reference | What we borrow | What we do NOT borrow |
|---|---|---|
| **Bloomberg Terminal** | high information density; keyboard-first; monospace numeric grids; small type; muted palette + accent colours for urgency | dated skeuomorphism; window-in-window overload |
| **TradingView** | live charts as first-class citizens; overlay evidence; scrubbable time | consumer-social features |
| **Tesla Mission Control** | multi-panel spatial layout; per-subsystem health as ambient telemetry; large digital typography | novelty flair |
| **SpaceX Mission Control** | mission timeline as central concept; nominal/warning/critical colour discipline; countdown clocks; narrative telemetry | manned-mission specificity |
| **Modern AI ops (Datadog / Vercel / Linear)** | fast keyboard nav; command palettes; narrative activity feeds; opinionated defaults | one-metric-per-screen sprawl |

Design *anti-patterns* — never do these:

- Purple/violet gradients on white backgrounds (AI-slop cliché)
- Centered layouts with equal spacing (feels marketing, not operational)
- Emoji as icons (undermines premium positioning)
- Rounded pastel dashboards (this is a mission-control cockpit, not a wellness app)
- Modal wizards with progress bars (operators run their own workflow)
- Full-page loading spinners (the Factory is autonomous; the UI is an observer)
- "Coming soon" placeholders (either build it or hide it)

**The frontend must feel significantly simpler than the backend architecture.** The backend has 701 routes across 25 modules. The operator should never see more than 8 top-level navigation entries.

---

## 2. The six operator questions (north star)

Every screen answers at least one:

1. **Is the system healthy?** — subsystem chips, uptime, provider states, kill posture
2. **What is the Factory doing right now?** — active cycles, running workers, current phase
3. **What has AI accomplished?** — narrative timeline; artefacts produced; knowledge grown
4. **What evidence supports those actions?** — traceable pipeline stages; per-artifact provenance
5. **What requires operator approval?** — unified queue; contextual "why", "risk", "revert"
6. **What needs my attention?** — critical/warn/advisory feed; danger ribbon; kill posture

**Rule:** if a screen can't be defended by pointing at one of these six questions, delete it (or move it to Layer 5).

---

## 3. Information architecture — five layers

Information exists in layers. Each screen is authored to a specific layer, and each layer has *fewer* consumers than the layer above.

| Layer | Purpose | Typical consumers | Time spent |
|---|---|---|---|
| **L1 · Mission Control** | Answers all six questions in one view | Every operator, every session | ~30 s per visit; hundreds of visits |
| **L2 · Operational workflows** | Perform a decision or configure a subsystem | Operator on-shift | ~2-10 min per task |
| **L3 · Evidence** | Prove/explore *why* an artifact exists | Operator preparing an approval or diagnosing an alert | ~30 s - 2 min |
| **L4 · Deep diagnostics** | Inspect subsystem internals when L1-L3 aren't enough | On-call during incident | Occasional |
| **L5 · Developer diagnostics** | Raw internals — queues, logs, indexes, env vars | Backend engineer only | Rare, incident-only |

**Design rule:** L1 → L3 pages are visible on the primary nav. L4 lives inside an *Advanced* drawer. L5 is invoked via `⌘K > developer > …` — never on the sidebar.

**Discovery rule:** the shortest path from L1 to any L3 evidence must be **≤ 3 clicks and ≤ 5 seconds**.

---

## 4. Navigation hierarchy

### 4.1 Two-vocabulary problem — the fix

The current shell has *two* nav vocabularies (LeftRail modules ≠ TopTabBar tabs). We consolidate to **one**:

- **LeftRail** = *modules* (Layer 1 & 2). Persistent. Icon + label.
- **TopTabBar** = *sections of the current module* (Layer 2 within). Contextual.
- **⌘K palette** = deep-jump to any module/section/action. Keyboard first.
- **Right rail** = *AI Activity Timeline* (persistent, collapsible). Never module-specific.
- **Header** = branding · posture pill · status rail · **approvals chip** · user menu.
- **Danger ribbon** = above header, only when armed.

### 4.2 Canonical 8-module nav

```
┌─────────────────────────────────────────────────────────────────────┐
│  ▶ MISSION CONTROL          Layer 1 — always the landing            │
│  ▶ RESEARCH                 Layer 2 — lab · generate · backtest    │
│  ▶ STRATEGIES               Layer 2 — explorer · library · compare  │
│  ▶ FACTORY                  Layer 2 — mutation · auto-factory · MB  │
│  ▶ PORTFOLIO                Layer 2 — builder · intelligence        │
│  ▶ EXECUTION                Layer 2 — brokers · paper · live        │
│  ▶ PROP FIRM                Layer 2 — catalogue · match · challenge │
│  ▶ APPROVALS   [ 4 ]        Layer 2 — unified queue (badge count)   │
├─────────────────────────────────────────────────────────────────────┤
│  ▷ MARKET DATA              Layer 3 — coverage · freshness · repair │
│  ▷ GOVERNANCE               Layer 3 — universe · symbols · rules    │
├─────────────────────────────────────────────────────────────────────┤
│  ⚙ ADVANCED                 Layer 4 — diagnostics · admin · audit   │
│  ⚙ DEVELOPER                Layer 5 — via ⌘K only                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Note the promotions:** Approvals becomes a **first-class module** (not scattered). AI Workforce is no longer a top-level module — it lives as *the persistent right rail* on every screen, plus a "workforce" section inside Factory.

### 4.3 URL scheme

- `/c/mission` — Mission Control (default landing)
- `/c/research/<section>` — Research module
- `/c/strategies/<section>` — Strategies module
- `/c/factory/<section>` — Factory module (mutation · auto · master-bot)
- `/c/portfolio/<section>`
- `/c/execution/<section>`
- `/c/propfirm/<section>`
- `/c/approvals[/<id>]` — approvals queue + drill-down
- `/c/market-data/<section>`
- `/c/governance/<section>`
- `/c/advanced/<section>` — Layer 4 diagnostics
- `⌘K` — palette for L5 developer views + all sub-sections + actions

Every URL is deep-linkable; every action can be triggered from the palette.

---

## 5. Design system — foundations

### 5.1 Palette

Dark-mode-first. Three roles: **surface** (never speaks), **content** (always speaks), **signal** (interrupts).

| Token | Hex | Usage |
|---|---|---|
| `--surface-0` | `#08090b` | app background |
| `--surface-1` | `#0f1114` | primary panels |
| `--surface-2` | `#161a1f` | elevated panels; hover states |
| `--surface-3` | `#1e2429` | dropdowns, modals |
| `--stroke-1` | `#212830` | subtle dividers |
| `--stroke-2` | `#2a333d` | active dividers, focus rings |
| `--content-hi` | `#e6edf3` | headings, primary metric values |
| `--content-md` | `#a7b1bd` | body copy, secondary metrics |
| `--content-lo` | `#5e6a78` | captions, disabled |
| `--content-inv` | `#08090b` | text on light accent |

Signal colours (SpaceX/Bloomberg discipline — mean *exactly* what they say):

| Token | Hex | Semantic |
|---|---|---|
| `--sig-ok` | `#3ddc84` | passed, healthy, nominal |
| `--sig-warn` | `#f0b429` | needs evidence, degraded |
| `--sig-crit` | `#ff5b5b` | failed, killed, alert |
| `--sig-advisory` | `#8b8ffb` | advisory-only; no action forced |
| `--sig-info` | `#4ea1f3` | information; live feed |
| `--sig-dormant` | `#5e6a78` | deliberately off / flag-gated |

**Never** introduce a new accent colour without deleting one. Six signals is the ceiling.

Chart palette (for data viz — separate from signal):

`#4ea1f3, #f0b429, #3ddc84, #ff5b5b, #8b8ffb, #ff8b3d, #5ecab5, #d17bff` — 8 tuned hues; use in this order; never introduce a 9th without swapping.

### 5.2 Typography

Two type families. That is all.

- **Display / monospace:** `JetBrains Mono` — used for metric values, module labels, code, timestamps, IDs.
- **Body / sans:** `Inter` … no wait — see anti-patterns. **Body / sans:** `Söhne` (paid) or `Manrope` (free fallback). *Never* Inter — too generic.

Type scale (rem):

| Token | Size | Line-height | Use |
|---|---|---|---|
| `--font-caption` | 0.6875 (11px) | 1.4 | lowercase labels, chip text, badges |
| `--font-body-sm` | 0.8125 (13px) | 1.5 | secondary copy |
| `--font-body` | 0.9375 (15px) | 1.55 | primary copy |
| `--font-metric-sm` | 1.125 (18px) | 1.2 | small KPI |
| `--font-metric` | 1.75 (28px) | 1.1 | primary KPI |
| `--font-metric-lg` | 2.5 (40px) | 1.0 | hero KPI (rare — Mission Control only) |
| `--font-h3` | 1.125 (18px) | 1.3 | section titles |
| `--font-h2` | 1.375 (22px) | 1.3 | page/module titles |
| `--font-h1` | 1.75 (28px) | 1.25 | rarely used (Mission Control only) |

Casing rules:
- Section titles: `Sentence case`
- Chip / caption text: `lowercase` (signature style — preserved from existing)
- Module labels in LeftRail: `UPPERCASE spaced` (Bloomberg-inspired)
- Metric labels above values: `UPPERCASE 10-11 px`
- Never Title Case — feels marketing

Numeric formatting:
- Always tabular-figures (CSS `font-variant-numeric: tabular-nums`).
- Timestamps: `YYYY-MM-DD HH:MM:SS` in mono, or `2 h ago` in body-sm.
- Percentages: 1 decimal by default (`91.4 %`), 0 decimals when displayed as sparkline label.
- Currency: `$12,340` (no cents unless intraday), tabular-nums.

### 5.3 Spacing

4-pt grid. Six defined step sizes; never invent a seventh.

| Token | Value | Use |
|---|---|---|
| `--space-1` | 4 px | intra-chip padding |
| `--space-2` | 8 px | chip-to-chip |
| `--space-3` | 12 px | card padding vertical |
| `--space-4` | 16 px | card padding horizontal |
| `--space-5` | 24 px | section vertical rhythm |
| `--space-6` | 40 px | module top-padding, hero rhythm |

**Density modes:**
- `--density-compact` (default) — Bloomberg operator posture
- `--density-cozy` — briefing posture; ~1.2× spacing multiplier
- `--density-cinema` — screen-in-lobby posture; ~1.6× multiplier

Toggle in header. Persist per-user in localStorage.

### 5.4 Iconography

**No emoji.** No exceptions.

- Primary icon set: `lucide-react` (already installed). Stroke width 1.5. Size default 16px.
- For signal chips: monospace **letter glyphs** (`P W F A I ●`) — preserves existing design vocabulary.
- For workers / bots: custom SVG glyph set (already exists in `command/Glyphs.jsx`) — extend, don't replace.
- Consistency: no icon appears on both LeftRail and inline copy for the same concept.

### 5.5 Corner radius

- `--radius-1` (6px) — chips, badges, inputs
- `--radius-2` (10px) — cards, dropdowns
- `--radius-3` (16px) — modals, drawers
- Never `radius-full` (pills) on structural elements. Reserve for signal chips only.

### 5.6 Elevation

Depth via **1-pixel stroke + subtle inner glow**, not drop shadows. Drop shadows feel consumer.

```css
.panel {
  background: var(--surface-1);
  border: 1px solid var(--stroke-1);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
}
.panel--elevated { background: var(--surface-2); border-color: var(--stroke-2); }
.panel--float    { /* modal-only */
  background: var(--surface-2);
  border: 1px solid var(--stroke-2);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.03);
}
```

### 5.7 Grid

12-column grid with a max content width of `1440 px`. Fluid below that. Never full-bleed except for the AI Activity Timeline right rail.

---

## 6. Motion principles

Every animation communicates state. No decorative motion.

### 6.1 Motion budget

- **Fast** — 120 ms · `cubic-bezier(0.4, 0, 0.2, 1)` · hover, focus, chip transitions
- **Medium** — 200 ms · `cubic-bezier(0.4, 0, 0.2, 1)` · panel expand/collapse, drawer slide
- **Slow** — 320 ms · `cubic-bezier(0.2, 0, 0, 1)` · module transition, modal enter/exit
- **Never** — > 400 ms · reserved for celebrations (there are none in this app)

Reduced-motion (media query `prefers-reduced-motion`): everything except opacity-only transitions is disabled.

### 6.2 State semantics

| State change | Motion |
|---|---|
| Idle → hover | 120 ms opacity/border shift; no scale |
| Focus | 120 ms outline glow; never movement |
| Loading (short) | shimmer skeleton, 1200 ms cycle |
| Loading (long) | narrative progress ("retrieving 3 candidates…") — text, not spinner |
| Data updated (live feed) | 200 ms fade-in from stroke-2 → surface — signals *"new"* without jarring |
| Alert armed | pulse on the ribbon (2 s cycle, low amplitude) |
| Kill posture triggered | full-screen 200 ms flash then held banner |

### 6.3 Library

- Use **Framer Motion** (`framer-motion` React package) for JS-driven sequences (timeline, drawers).
- Use **CSS transitions** for state changes (hover/focus/expand).
- Never mix — if a component uses Framer, that component owns *all* its motion.

### 6.4 Live-feed staggering

AI Activity Timeline entries enter with a 40 ms stagger, opacity 0 → 1, y-offset 6 → 0. Max 12 concurrent animations before it batches to a single fade to preserve frame rate.

---

## 7. Component library

Foundational primitives. Every module composes from these.

### 7.1 Chip

```
[● healthy]   [P passed]   [W needs evidence]   [dormant]
```

Attributes: `variant` (ok / warn / crit / advisory / info / dormant), `letter?` (`P W F A I`), `label`.
Size: 20px height default; 16px in dense grids.
State: hover reveals `data-testid` and tooltip with `why` copy.

### 7.2 Metric card

```
┌──────────────────────────┐
│ AI WORKFORCE             │
│                          │
│  91.4 %                  │  ← --font-metric
│  ▲ 2.1 vs 24h            │  ← delta, colour = ok/crit
│                          │
│  [P passed · 4 workers]  │  ← chips row
│                          │
│  ⤷ view evidence         │  ← always a link out
└──────────────────────────┘
```

Rule: **every metric card links to its evidence view**. No dead-end numbers.

### 7.3 Pipeline stage bar (Evidence-first)

```
Generated ─► Validated ─► Optimized ─► Certified ─► Knowledge stored ─► Portfolio candidate ─► Approved ─► Production
   ●             ●            ●             ○             ○                     ○                  ○           ○
```

Filled dot = complete; hollow = pending; red = failed. Hover any dot: mini-panel with timestamp, actor (which bot/human), evidence link.

### 7.4 Activity Row (Timeline)

```
[12:24]  [orchestrator]  Opened GPT-5 to score 3 candidates
                         confidence 0.87 · verdict: proceed to backtest
                         ↳ view evidence
```

Timestamp is monospace, mono-width. Actor chip is coloured by role (orchestrator/mutation/knowledge/execution/governance/…). Body is one sentence + one optional detail line + one link.

### 7.5 Approval Card

```
┌────────────────────────────────────────────────────────────┐
│  [META-LEARNING]  Recommendation #47                        │
│                                                             │
│  Suggest lowering `challenge_dedup_threshold` from 0.82     │
│  → 0.78 based on last 30 d retrieval hit-rate               │
│                                                             │
│  EVIDENCE                                                   │
│  · retrieval hit-rate: 61 % (target ≥ 70 %)                │
│  · false-dedup incidents in last 7 d: 4                    │
│  · confidence: 0.71 · trust_tier: verified                 │
│  ⤷ full evidence trail                                     │
│                                                             │
│  RISK                                                       │
│  · low — advisory-only path; revertible in one click       │
│                                                             │
│  [ Approve ]  [ Defer ]  [ Deny ]  [ Route to team ]        │
└────────────────────────────────────────────────────────────┘
```

Every approval has: **subject → recommendation → evidence → risk → four actions**. No exceptions.

### 7.6 Status rail

Six-chip bottom bar visible on Mission Control (existing). Extended semantics:

```
[● orch · healthy]  [● ingest · ready]  [● sched · failover-on]  [◐ llm · no key]  [● govern · governed]  [● kill · armed]
```

Hollow half-fill (◐) = degraded/attention. Solid = nominal. Empty ring (○) = dormant-by-design.

### 7.7 Worker card (AI Workforce)

Living-organization visual metaphor: each worker is a compact card in a grid.

```
┌──────────────────────────┐
│  RESEARCH · WORKER-01    │
│  ●  healthy              │
│                          │
│  running · candidate #47 │
│  since 12:24 · 3.4 min   │
│                          │
│  Last artifact:          │
│  strat_bb_ema_rsi_v3     │
│                          │
│  ⤷ open evidence         │
└──────────────────────────┘
```

Cards animate ambient (pulse subtly when running). Grouped by team: Research, Mutation, Learning, Knowledge, Execution, Governance, Maintenance, Monitoring (8 teams).

### 7.8 Drawer / modal

- Drawer = context-sensitive, slides from right, does not obscure right rail
- Modal = interruptive, use rarely (approvals confirmation, kill-posture arm/disarm)
- Both use `--surface-2` with `--stroke-2` border, 320 ms slow enter

### 7.9 Table

- Never full-page tables. If you need > 30 rows visible, use a virtualized list with sticky header.
- Column headers UPPERCASE 11px; values tabular-nums.
- Sortable columns get a discreet arrow; sorted column gets `--stroke-2` background on the header cell.

### 7.10 ⌘K palette

- Fuzzy match on module labels, section titles, action names, KB item IDs.
- Groups: `navigate`, `run`, `evidence`, `developer` (only visible in Advanced mode).
- Recent 5 always shown on empty query.
- Escape closes; Enter executes; ⇧Enter opens in a drawer (peek).

---

## 8. Dashboard & module layouts

### 8.1 Mission Control (L1 · landing)

```
┌───────────────────────────────────────────────────────────────────────────┐
│ [DANGER RIBBON]                                                            │
├────────────────────────────────────────────────────────────┬──────────────┤
│                                                            │              │
│  Q1 · HEALTH             Q6 · ATTENTION [3]                │              │
│  status rail (6)         top-3 items                       │              │
│                                                            │  AI ACTIVITY │
├─────────────────────────┬─────────────────────────────────┤   TIMELINE   │
│  Q2 · WHAT NOW           Q5 · APPROVALS [4]                │              │
│  factory phase           4 pending                         │  live feed   │
│  active workers (4)      grouped by module                 │  (right rail)│
│                                                            │              │
├─────────────────────────┴─────────────────────────────────┤              │
│  Q3 · ACCOMPLISHMENTS (last 24 h)                          │              │
│  6 tiles: strategies · mutations · validations · promotes ·│              │
│  KB items · execution obs.                                 │              │
├────────────────────────────────────────────────────────────┤              │
│  Q4 · EVIDENCE STREAM                                      │              │
│  latest 6 pipeline events, filterable by stage             │              │
├────────────────────────────────────────────────────────────┤              │
│                            STATUS RAIL                     │              │
└────────────────────────────────────────────────────────────┴──────────────┘
```

The Mission Control view is one scroll on 1440×900+. Below that scroll, nothing else — the page is *bounded*. If a user scrolls off the bottom of Mission Control, they've gone too far.

### 8.2 Research module

Left: **operator storyline** (Generate → Validate → Optimize → Certify). Right: **evidence pane**. Below: **history** (recent runs).

### 8.3 Strategies module

Explorer as primary. Every row has evidence chips inline: `origin · trust_tier · promote_events · learning_only`. Comparison and Saved live as tabs on the top rail of this module.

### 8.4 Factory module (mutation + auto-factory + master bot)

**Master Bot as CEO metaphor.** Top of module: Master Bot dashboard — objective, workflow, decisions, children status. Below: current cycles (grid of running mutations). Below: history.

### 8.5 Portfolio, Execution, Prop Firm

Each follows the same skeleton:

- Top strip: KPI cards (3-4)
- Left main: workflow surface
- Right: evidence + linked history
- Bottom: reservations accordion (Phase 13/14/15) collapsed by default

### 8.6 Approvals

Dedicated module:

```
┌──────────────────────────────────────────────┐
│  APPROVALS  [ Meta-Learning · 3 ]  [ Factory-Eval · 1 ]  [ Governance · 0 ] │
├──────────────────────────────────────────────┤
│  (list of approval cards, most-urgent first) │
│                                              │
│  Approval card                               │
│  Approval card                               │
│  Approval card                               │
└──────────────────────────────────────────────┘
```

Filters: `module`, `age`, `risk`. Bulk actions (`Approve all low-risk`) require explicit confirmation.

---

## 9. AI interaction patterns

### 9.1 The AI must appear alive

**Persistent right rail** on every screen (240 px wide, collapsible to a 40 px stripe).

Content: chronological AI Activity Timeline. New entries slide in at top with a 40 ms stagger.

Item types (each has its own chip colour + icon):

| Type | Icon | Chip colour | Sample copy |
|---|---|---|---|
| Research | `search` | info | "queried arxiv for 'mean-reversion regime detection' — 4 hits, 2 dedup" |
| Generation | `sparkles` | ok | "generated strategy `bb_ema_rsi_v3` — validated, score 0.71" |
| Backtesting | `bar-chart-2` | info | "ran 30-d walk-forward on 3 candidates — 2 passed" |
| Mutation | `git-branch` | info | "mutation cycle #47 opened — parent `bb_ema_rsi_v2`" |
| Knowledge | `book` | advisory | "knowledge item `arxiv:2401.09883` ingested — trust_tier `verified`" |
| Learning | `activity` | info | "meta-learning proposed dedup threshold 0.78 — see approvals" |
| Portfolio | `layers` | info | "portfolio candidate added — risk 0.4 %" |
| Execution | `terminal` | info | "execution obs. — EURUSD fill quality p95 = 1.2 pips" |
| Maintenance | `wrench` | dormant | "BI5 sweep completed — 0 gaps" |
| Approval | `flag` | warn | "approval requested — meta-learning #47" |

Every row is a link. Clicking navigates to L3 evidence. Never a modal.

### 9.2 Copilot / AI assistant

A **copilot pane** already exists in the shell (`CopilotPanel.jsx`). Extend, don't replace. Its role:

- Answer plain-English questions using the Emergent LLM key (when configured)
- Grounded exclusively in **evidence** — copilot cannot invent data; every answer cites at least one pipeline event or artifact
- Never initiates actions on the operator's behalf. Approvals are always explicit.

### 9.3 AI Workforce visualization (see §12.2)

---

## 10. Evidence visualization standards

**Never show "Completed."** Show the pipeline stage.

### 10.1 The eight canonical stages

```
Generated → Validated → Optimized → Certified → Knowledge stored → Portfolio candidate → Approved → Production
```

Every artefact has these 8 stages (subset may be N/A for some artefact types — display them as *skipped* not missing).

Rendered as a **pipeline stage bar** (§7.3) that appears:
- Inline in Strategy Explorer rows
- On every artefact detail page
- On approval cards (subset relevant to the recommendation)

### 10.2 Provenance triple

Every artefact carries a visible **provenance triple**:

```
[ origin: mutation_runner ]  [ trust_tier: verified ]  [ signed_by: master-bot@v55 ]
```

Chip colour = the trust axis it represents:
- `origin` = `advisory` (informational)
- `trust_tier` = `ok`/`warn`/`crit` based on level
- `signed_by` = `info`

Never show hash strings by default. Show them on hover / in evidence drawer.

### 10.3 Evidence drawer

Right-side drawer (600 px). Opens when the operator clicks any evidence link.

Sections:
1. **Subject** — the artefact this evidence supports
2. **Pipeline** — stage bar with per-stage timestamp + actor
3. **Inputs** — what data / knowledge fed this
4. **Outputs** — what artifacts resulted
5. **Confidence** — with method (e.g., "walk-forward Sharpe = 1.34 · p-value 0.03")
6. **Governance stamp** — trust_tier, license, hard rails ok/warn/crit
7. **Reversibility** — can this be rolled back? by whom? within what SLA?

Never JSON-dump. Never show internal IDs unprompted.

### 10.4 "Why" tooltip pattern

Any signal chip (P/W/F/A/I) gets a `Why?` tooltip on hover with:
- 1-sentence justification
- 1 link ("open evidence")

No jargon. If we have to explain a term, it doesn't belong on Layer 1.

---

## 11. Approval workflow

### 11.1 Unified queue (§4.2)

Single module `/c/approvals`. Never scattered.

### 11.2 Approval origin sources

| Source | Backend gate | Frontend surface |
|---|---|---|
| Meta-Learning recommendations | `/api/meta-learning/recommendations` (OBSERVE mode → `/approve` = 409 until wake) | Approval card, group "META-LEARNING" |
| Factory-Eval recommendations | `/api/factory-eval/recommendations` (OBSERVE) | Group "FACTORY-EVAL" |
| Governance advisory tags | `/api/knowledge/promote/{id}` dry-run | Group "GOVERNANCE" |
| Master Bot compile actions | current danger ribbon path | Group "MASTER-BOT" |
| Symbol Registry onboarding | `/api/symbol-registry/*` | Group "SYMBOL-REGISTRY" |
| Kill-posture arm/disarm | `/api/kill-posture/*` | Group "SAFETY" (always at top) |

### 11.3 Actions on an approval

Four actions always. In this order:

1. **Approve** — commits the recommendation; opens a confirmation modal iff risk > low
2. **Defer** — snooze for N hours (default 24); requires no confirmation
3. **Deny** — records the denial with a required 1-line rationale
4. **Route to team** — assigns to another operator (multi-operator future)

### 11.4 Post-approval

Every approval action produces an entry in AI Activity Timeline (`Approval` icon).
Every approval action generates a `/api/audit-log` entry (already exists backend-side).

### 11.5 Bulk actions

Only for `Approve all low-risk (X)`. Requires typing "APPROVE" to confirm. Never enabled for `Deny` or `Route`.

---

## 12. Master Bot & AI Workforce visualization

### 12.1 Master Bot — CEO of the Factory

Master Bot lives at the **top of the Factory module** as a dashboard.

```
┌──────────────────────────────────────────────────────────────┐
│  MASTER BOT · @v55                                            │
│  ●  healthy · uptime 4d 02:11                                 │
│                                                              │
│  CURRENT OBJECTIVE                                            │
│  Ship 3 verified strategies for FTMO-100k evaluation          │
│  (target completion: 4 h · ETA on-track)                     │
│                                                              │
│  CURRENT WORKFLOW                                             │
│  1. Generate 5 candidates ✓                                  │
│  2. Validate on 30-d walk-forward ✓                          │
│  3. Optimize top 3 → running (worker-02)                     │
│  4. Certify against FTMO rules — queued                      │
│  5. Route to Portfolio + Approvals                            │
│                                                              │
│  CHILDREN                                                     │
│  research-worker-01 ● · mutation-worker-02 ● · validate-03 ● │
│                                                              │
│  LAST DECISIONS                                               │
│  · rejected `strat_bb_ema_rsi_v3` (Sharpe < 1.0) — 8m ago   │
│  · promoted `strat_donchian_atr_v2` to Optimize — 22m ago   │
└──────────────────────────────────────────────────────────────┘
```

**Never show:** internal task IDs, Docker container names, Redis keys, queue depths. Those are Layer 5.

### 12.2 AI Workforce — living organization

Below Master Bot, an 8-team grid. Each team gets a section with worker cards (§7.7).

```
RESEARCH · 2 workers · 1 running
MUTATION · 3 workers · 1 running · 1 idle · 1 offline
LEARNING · 1 worker · idle
KNOWLEDGE · 1 worker · running (retrieval)
EXECUTION · 2 workers · both idle
GOVERNANCE · 1 worker · running (advisory pass)
MAINTENANCE · 1 worker · idle
MONITORING · always-on watcher
```

Worker cards animate ambient (2s subtle pulse when running). Idle workers dim to `--content-lo`. Offline workers get a `crit` chip.

Clicking any worker opens **evidence drawer** with its last 20 activity rows.

---

## 13. Data quality & infrastructure visualization

### 13.1 Market Data module

**Coverage grid** — the signature view:

```
Symbol / TF  1m       5m       15m      1h       4h       1d
──────────── ──────── ──────── ──────── ──────── ──────── ────────
EURUSD       ████████ ████████ ████████ ████████ ████████ ████████
GBPUSD       ████████ ████████ ████████ ██████░░ ████████ ████████
USDJPY       ████████ ████████ ████░░░░ ████░░░░ ████████ ████████
XAUUSD       ██░░░░░░ ████████ ████████ ████████ ████████ ████████
```

Each cell is a horizontal completeness bar. Hover reveals: last-tick timestamp, gaps count, freshness lag, auto-repair status.

Below the grid: **Timeline of recent BI5 sweeps** with pass/fail chips. Below: **Historical growth chart** (24-week KB size).

### 13.2 Infrastructure surface

**Layer 4 only.** Never on Layer 1.

Location: `/c/advanced/infrastructure`.

Content: CPU %, RAM %, storage, Docker container status, Redis stats, Mongo collection sizes, scheduler backlog, worker pool state.

Presentation: single dashboard, six 2-column cards. Same design language as Mission Control, but density is higher. Refresh cadence 5 s.

**Rule:** Mission Control mentions infrastructure only through the status rail (§7.6). Nothing more.

---

## 14. Notification philosophy

### 14.1 Three notification tiers

| Tier | Trigger | Delivery | Persistence |
|---|---|---|---|
| **Critical** | System-integrity threat (kill-posture, failed compile, invariant break) | Danger ribbon + persistent NotificationDrawer entry + optional email | Until acknowledged |
| **Warn** | Needs-evidence event; degradation | NotificationDrawer entry only | Auto-dismisses after 24 h |
| **Info** | Routine AI activity, completions | AI Activity Timeline entry only (not the Drawer) | Rolling — kept for last 500 |

### 14.2 The danger ribbon

**Exists only for Critical.** Never Warn. Never Info.

Copy pattern: `[GLYPH]  What happened · when · [ACTION LABEL]`

Example (currently live in prod):
```
DANGER  Master Bot compile failed · signing error · master-bot.compile · 1h ago  [ VIEW INBOX ]
```

Clicking `VIEW INBOX` opens the OperatorInboxDrawer at the relevant item.

### 14.3 Notification anti-patterns

- No browser push notifications by default (opt-in only, in Preferences)
- No toast pop-ups for routine events (they belong in the timeline)
- No red numbers on the module label unless action is required by the operator personally

### 14.4 Do-not-disturb

Header setting: **Focus mode**. Suppresses drawer entries for Warn/Info; Critical still fires. Operator sees `[● focus]` chip in header while active. Auto-expires at end of shift (configurable).

---

## 15. Empty / loading / error / dormant state standards

### 15.1 Empty state pattern

Never show `[]` or `No results`. Always:

```
┌──────────────────────────────────────────────┐
│                                              │
│   [ icon ]                                   │
│                                              │
│   No mutation cycles have run today.         │
│   Runners are healthy and waiting.           │
│                                              │
│   [ Run a cycle ]  ·  [ View last cycle ]    │
│                                              │
└──────────────────────────────────────────────┘
```

Rule: **one sentence of context + one primary action + one secondary link**. Never both actions the same colour.

### 15.2 Loading

- **< 300 ms** — no indicator (avoid flicker)
- **300 ms – 2 s** — inline skeleton with shimmer (`--surface-2` gradient)
- **> 2 s** — narrative progress: `"retrieving 3 candidates from arxiv…"` — text, not spinner
- **> 8 s** — offer to background: `"still working — you can navigate away and I'll notify when done."`

### 15.3 Error

Errors are informational, not scary. Copy pattern:

```
Something went wrong here.
The retrieval endpoint returned 503 (dormant — Phase D not yet activated).

[ Retry ]   [ Report ]   [ View logs (developer) ]
```

Never show a stack trace on Layer 1-3. Log it to `⌘K > developer > errors`.

### 15.4 Dormant state

Signature to Strategy Factory. Many endpoints are 503 by design during freeze.

```
┌──────────────────────────────────────────────┐
│  DORMANT · Phase D not yet activated         │
│                                              │
│  Connector fleet is intentionally offline    │
│  until the Coherent UKIE Activation plan     │
│  reaches Phase D. Backend is healthy.        │
│                                              │
│  [ View activation plan ]                    │
└──────────────────────────────────────────────┘
```

`dormant` colour (`--sig-dormant`, muted grey) — visually distinct from `error` (red).

**This is not a bug state. Do not colour it red. Do not offer Retry.**

---

## 16. Responsiveness

Three postures. Detected once at breakpoint, persisted per session.

| Posture | Breakpoint | Purpose | Density |
|---|---|---|---|
| **Workstation** | ≥ 1440 px | Full cockpit — operator at desk | compact |
| **Tablet** | 900-1439 px | Briefing / on-the-go | cozy |
| **Briefing** | ≥ 1920 px full-screen in lobby / TV | Read-only situational awareness | cinema |

Below 900 px: **read-only mode** (no forms, no drawers, no approvals). Operators shouldn't approve on phones — this is a mission-control tool.

### 16.1 Posture behaviour

| Posture | LeftRail | TopTabBar | Right rail | Mission Control panels |
|---|---|---|---|---|
| Workstation | full labels | full | expanded 240px | 4-column grid |
| Tablet | icons only | full | collapsed 40px stripe (tap to expand) | 2-column grid |
| Briefing | icons only, minimized | hidden | hidden (timeline promoted to bottom bar) | 1-column stack + hero KPI |
| Mobile (< 900) | drawer only | hidden | inline card in feed | single-column read-only |

### 16.2 Print

Print stylesheet already exists (`briefing-print.css`). Extend: every module gets a *print-mode digest* accessible via `⌘K > print current view`. Renders monochrome-ready page with:
- Header (title + timestamp)
- 3-5 KPIs
- 1 evidence table
- Signature block (operator name, timestamp)

---

## 17. Accessibility guidelines

**Target: WCAG 2.2 AA.** No exceptions.

- **Colour contrast** — every text/background pair ≥ 4.5:1; every large-text pair ≥ 3:1. Verified with automated `axe-core` in CI.
- **Focus order** — visible focus ring (2px `--sig-info` outline). Focus trap in modals/drawers.
- **Keyboard-first** — every action reachable via keyboard. ⌘K palette is the escape hatch.
- **Screen-reader labels** — every icon-only button has `aria-label`. Every chip has `aria-label` composed of variant + label.
- **Motion** — respect `prefers-reduced-motion`. Reduce all motion to opacity fades only.
- **Colour-blind safety** — never rely on colour alone. Signal chips always carry a **letter glyph** (`P W F A I`). Pipeline stages show fill state, not only colour.
- **Text sizing** — respect user zoom up to 200%. No fixed pixel heights on text containers.
- **Data-testid** — every interactive element gets a `data-testid` in `kebab-case` describing intent (`approve-recommendation-btn`, `activity-timeline-item-<id>`).

---

## 18. Operator workflows

### 18.1 Login (0-5 s)

1. AuthGate — email + password (or SSO in Phase 2)
2. Auto-redirect to `/c/mission`
3. Mission Control renders in < 800 ms (skeleton first, then progressive fill)

### 18.2 Morning routine (30-90 s)

1. Glance at status rail → Q1 answered
2. Glance at Attention feed → Q6 answered
3. Skim AI Activity Timeline last 6 h → Q3 answered
4. Approvals chip → count / age
5. Enter L2 only if any of the above surfaces requires deeper action

### 18.3 Approving a recommendation (< 60 s)

1. `⌘K > approvals` or click header chip `[ 4 approvals ]`
2. Card at top of queue
3. Read: subject → recommendation → evidence → risk
4. Optionally click "full evidence trail" (opens drawer)
5. Approve / Defer / Deny
6. Confirmation modal only if risk > low
7. Timeline records the action

### 18.4 Investigating an alert (60-180 s)

1. Danger ribbon → click → NotificationDrawer opens on the item
2. Item shows: what · when · which subsystem · evidence link
3. Click evidence link → drawer with pipeline + inputs + outputs
4. Choose: Acknowledge · Escalate · Diagnose (opens L4 Advanced)
5. Never leave the current module — everything is drawer-based

### 18.5 Running a research cycle (2-10 min)

1. Navigate `Research` module
2. Workspace view (unified lab)
3. Configure inputs → Generate
4. Watch pipeline stage bar advance in real time (from AI Activity Timeline)
5. Result appears in Explorer with evidence chips inline
6. If desired, approve for Portfolio candidacy (routes to Approvals)

### 18.6 End of shift (< 30 s)

1. Enable **Focus mode** = off (i.e., re-enable notifications for the next shift)
2. `⌘K > digest today` → prints/exports a briefing PDF for the log
3. Log out

---

## 19. Naming, iconography & copy standards

### 19.1 Module naming

Nouns, singular. `Research`, `Strategies`, `Factory`, `Portfolio`, `Execution`, `Prop firm`, `Approvals`, `Market data`, `Governance`, `Mission control`. Never verbs on the sidebar.

### 19.2 Action button naming

Verbs, first-person implicit. `Approve`, `Defer`, `Deny`, `Run cycle`, `Generate`, `Optimize`, `Export digest`. Never `Click here`, never `Submit`.

### 19.3 Copy voice

- **Confident** — the Factory is intelligent; the copy is too.
- **Terse** — Bloomberg discipline; every extra word is subtracted.
- **Numeric** — where a number exists, prefer the number.
- **Never anthropomorphic** — never `"I think"`, never `"we suggest"`. The AI is stated in third person (`meta-learning proposes …`).
- **Never marketing** — never `"powerful"`, never `"seamless"`, never `"unlock"`.

### 19.4 Terminology dictionary

Fixed vocabulary. If a term appears in code, it appears in UI with the same meaning:

| Term | Meaning | Never call it |
|---|---|---|
| Artefact | Any generated object (strategy, KB item, mutation) | "record", "item", "thing" |
| Cycle | One full pass of a workflow | "run", "job" (except in L5) |
| Approval | Operator decision required | "review", "sign-off" |
| Recommendation | System-proposed action requiring approval | "suggestion", "proposal" |
| Evidence | Traceable data supporting an artefact | "logs", "audit" (except in L4) |
| Kill posture | Emergency freeze state | "safe mode", "panic" |
| Provenance | Origin + trust_tier + signer triple | "metadata" |

Publish this list at `/c/help/glossary`. Copilot uses the same list.

### 19.5 Number formatting

- Currency: `$1,234` (no cents on Layer 1); `$1,234.56` on Layer 3
- Percent: `91.4 %` (1 dp default)
- Time: relative on Layer 1 (`4 h ago`); absolute on Layer 3 (`2026-07-20 09:14:58 UTC`)
- Delta: `▲ 2.1` or `▼ 0.4` — mono-arrow character

---

## 20. Extensibility & governance of this document

### 20.1 Change process

- **v-minor bump** (e.g., v1.0 → v1.1): additions that don't contradict existing rules — new component variants, new colour tokens, new module sections.
- **v-major bump** (v1.x → v2.0): rule reversals, palette overhaul, IA restructure. Requires operator sign-off + a change-summary appendix.

Every change lands as a PR against `/app/memory/FRONTEND_DESIGN_BIBLE.md` with:
- one-line rationale
- affected components
- migration plan for existing UI

### 20.2 Adding a new module — checklist

Before shipping:
- [ ] Does the module answer at least one of the six questions? (§2)
- [ ] Is it at Layer ≤ 3? If Layer 4-5, is it correctly placed under Advanced / ⌘K?
- [ ] Does the module use only the sanctioned colour tokens? (§5.1)
- [ ] Does every metric card link to evidence? (§7.2)
- [ ] Are empty / loading / error / dormant states authored? (§15)
- [ ] Do all interactive elements have `data-testid`? (§17)
- [ ] Screenshot at workstation / tablet / briefing postures?
- [ ] Reviewed against §19 terminology dictionary?

### 20.3 Adding a new colour / motion / typography token

Not allowed except by v-major change. Instead: find the closest existing token, or delete one you're replacing.

### 20.4 Retirement policy

If a module or component is superseded, add `@deprecated <since-version>` to its file header; keep it working for 2 minor versions before removal.

### 20.5 Design-vs-implementation boundary

This document defines *what*. Implementation details (which library, which CSS-in-JS approach, which state manager) live in a separate `FRONTEND_TECHNICAL_STANDARDS.md` — outside the Design Bible's scope.

---

## 21. Design principles (posters — memorise these)

1. **Evidence over completion.** Never `Completed`. Always the pipeline stage.
2. **Six questions per screen.** Or delete it.
3. **The AI is alive.** The right rail proves it, every minute.
4. **Density with air.** Bloomberg information · SpaceX discipline.
5. **Signal is sacred.** Six signal colours. Never a seventh.
6. **Layers, not tabs.** Operators live at Layer 1-3. Layer 5 is invisible until named.
7. **Master Bot is the CEO.** Every worker is under an org chart, not a queue.
8. **Approvals are the only UI-driven decision.** Everything else is observation.
9. **Empty is a state, not a bug.** Author it. Explain it. Offer an action.
10. **Keyboard first.** ⌘K wins every debate about buried features.

Print these posters and put them next to the workstation. They are the whole book compressed to a fridge magnet.

---

## Appendix A — Component migration checklist (for premium-repo integration)

When the premium frontend repo is connected, use this checklist per component:

- [ ] What is its Layer classification (§3)?
- [ ] Does it use the sanctioned palette + type + spacing tokens?
- [ ] Does it fit the eight-module nav (§4.2)?
- [ ] Does it break any of §21 principles?
- [ ] Is its evidence surface aligned with §10?
- [ ] Are its empty/loading/error states aligned with §15?
- [ ] Does it introduce a new colour/token? If yes — deny or swap.
- [ ] Does it produce noise on Layer 1?

A component is *approved for migration* only if all seven are ✅.

## Appendix B — Sprint 1 candidate scope (locked once approved)

Post-approval, Sprint 1 (2 weeks) should ship:

- Mission Control v1 (six-question layout, evidence stream)
- Nav vocabulary unification (Left = modules, Top = sections; delete the parallel labels)
- AI Activity Timeline v1 (right rail)
- Approvals module v1 (unified queue)
- Advanced/Simple posture toggle
- Narrative empty states across every module

Non-goals for Sprint 1: consolidation of Research/Factory/Diagnostics (Sprint 3); evidence columns in Explorer (Sprint 4); motion polish (Sprint 5).

## Appendix C — What is NOT in this Bible

- Backend architecture (see `/app/memory/PRD.md` + `BACKEND_FEATURE_FREEZE.md`)
- Deployment procedure (see `VPS_DEPLOYMENT_RUNBOOK.md`)
- Activation plan (see `COHERENT_UKIE_ACTIVATION_PLAN.md`)
- Testing standards (separate `FRONTEND_TESTING_STANDARDS.md` to be authored)
- Technical stack details (separate `FRONTEND_TECHNICAL_STANDARDS.md` to be authored)

---

*End of Frontend Design Bible v1.0 (draft).*
*Awaiting operator sign-off + premium-repo connection before Sprint 1 begins.*

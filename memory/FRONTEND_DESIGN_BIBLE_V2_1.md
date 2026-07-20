# Strategy Factory — Frontend Design Bible v2.1

> **Canonical design document.** Supersedes v1.0 (`FRONTEND_DESIGN_BIBLE.md`)
> and the v2.0 delta (`FRONTEND_DESIGN_BIBLE_V2_DELTA.md`) as the source of
> truth. Historical documents remain in the repo for reference only.
>
> **Approved:** 2026-07-20 (v1.0) · 2026-07-20 (v2.0 additions) · 2026-07-20 (v2.1 deltas).
> **Study source:** `DESIGN_INSPIRATION_STUDY.md` + `BIBLE_V2.1_DELTAS.md`.
>
> **Reading order:** §1 → §2 → §5 → §7 → §12. All other sections are reference.
>
> **Status:** Design phase active. No frontend code lands until D8 is
> approved. Backend Feature Freeze remains in effect.

---

## How v2.1 relates to v1.0 and v2.0

- **v1.0** established the twenty-one section architecture and the six operator questions.
- **v2.0 delta** added personalization modes, signature graphics, Copilot elevation, and the design-first workflow.
- **v2.1** — this document — folds in the fifteen Adopted patterns from the Design Inspiration Study (Feb 2026), the D3 Lineage-Graph patch, and the new **Context Never Lost** principle.

For sections **unchanged** since v1.0 or v2.0, this document contains an
authoritative pointer of the form:

> **Unchanged from v1.0 §X** — see `FRONTEND_DESIGN_BIBLE.md`.

For sections **new or changed in v2.1**, the full text is inlined here.

---

## Table of contents (v2.1 canonical numbering)

1. Product philosophy
2. The six operator questions
    - 2b. Bottom-up monitoring / top-down troubleshooting *(new v2.1)*
3. Information architecture — five layers
4. Navigation hierarchy
5. Design system — foundations
    - 5.4 Concept-C whitespace heuristic *(new v2.1)*
6. Motion principles
    - 6.3 Interaction latency budget *(new v2.1)*
7. Component library
    - 7.11 Widget trichotomy *(new v2.1)*
    - 7.12 Pinned Preview *(new v2.1)*
    - 7.13 Time-window chip *(new v2.1)*
8. Dashboard & module layouts
    - 8.7 Salience heuristic *(new v2.1)*
    - 8.8 Attention panel severity ordering *(new v2.1)*
9. AI interaction patterns
10. Evidence visualization standards
    - 10.2 Lineage Graph mode *(new v2.1)*
11. Approval workflow
    - 11.6 Facet grammar *(new v2.1)*
12. Master Bot & AI Workforce visualization
13. Data quality & infrastructure visualization
14. Notification philosophy
    - 14.5 Trailing highs / lows *(new v2.1)*
    - 14.6 Drill-through mandate *(new v2.1)*
    - 14.7 Permalink and export *(new v2.1)*
    - 14.8 Three-view toggle (Advanced) *(new v2.1)*
15. Empty / loading / error / dormant states
16. Responsiveness
17. Accessibility
18. Operator workflows
19. Naming, iconography & copy
    - 19.6 Everywhere-Actionable *(new v2.1)*
20. Extensibility & governance
21. Design principles poster (updated for v2.1)
22. Personalization modes *(from v2.0 §2)*
23. Signature graphics inventory *(from v2.0 §3)*
24. Copilot elevation *(from v2.0 §4)*
25. Design-first workflow *(from v2.0 §5)*

Appendix A · Component migration checklist
Appendix B · Sprint 1 candidate scope
Appendix C · What is NOT in this Bible
Appendix D · v2.1 changelog *(new)*

---

## §1 Product philosophy

Unchanged from v1.0 §1 — see `FRONTEND_DESIGN_BIBLE.md`.

### §1.4 Four foundational principles *(v2.1 formalises three from D1 §1 and adds a fourth)*

Every design decision is measured against these four principles.

#### 1.4.1 Invisible Luxury
Luxury comes from craftsmanship, not decoration. The operator should
notice how *effortless* the product feels, never how *flashy*. Every
motion, colour and micro-interaction earns its place. When in doubt, remove.

#### 1.4.2 Everything Connected
Every artefact carries complete lineage. Nothing exists in isolation.
Every card links back through the pipeline to its ancestry and forward
to its descendants. Codified in §10 (Evidence) and §10.2 (Lineage Graph).

#### 1.4.3 Progressive Disclosure
Simple mode stays clean. Advanced mode reveals depth *in place* — same
layouts, more chips, more optional panels — never a wholly new destination.

#### 1.4.4 Context Never Lost *(new v2.1)*

The application feels like **one continuous workspace**, not a collection of
independent pages. Operators never lose operational context when moving
between Mission Control, Timeline, Knowledge, Replay, Approvals, Portfolio,
Workforce, or any future module.

**What is preserved across navigation:**

| Context | Preserved when navigating away and back | Preserved across modules |
|---|---|---|
| Selected strategy / artefact | ✅ | ✅ (highlighted in every list it appears in) |
| Selected worker | ✅ | ✅ (highlighted on Workforce Org Chart when returning) |
| Filter chips (any `<FacetBar>`) | ✅ | ✅ (per-facet class shared across surfaces) |
| Time-window chip | ✅ | ✅ (a `last 7 d` selection follows the operator across surfaces where time is a dimension) |
| Evidence Drawer state | ✅ (drawer stays open when possible) | Restored when returning to same artefact |
| Advanced Lens toggle | ✅ | ✅ (session-persistent) |
| Persona mode (§22) | ✅ | ✅ |
| Density mode | ✅ | ✅ |
| Pinned Preview tray (§7.12) | ✅ | ✅ (pins survive every navigation) |
| Scroll position | ✅ | ✅ (best-effort per surface) |
| Navigation history | ⌘[ / ⌘] back-forward across a session | — |

**Implementation contract (for Sprint 1 architecture):**

- All context above lives in a single global **workspace state store**
  (Zustand / Redux — implementation-agnostic in Bible).
- State keys are URL-encodable — every context is deep-linkable via query
  parameters, so *reload preserves everything*.
- Navigation between modules is a **route change**, never a full page
  reload — the shell chrome (LeftRail, TopTabBar, StatusRail, right rail)
  never re-mounts.
- Cross-module highlight: if `?strategy=bb_ema_rsi_v3` is in the URL,
  every list that contains that strategy renders it with a 2 px
  `--sig-info` left border, no matter which module the operator is in.
- Cross-module time cascade: setting `?since=2026-06-01T00:00Z` applies
  to Timeline, Approvals, Workforce Org Chart history, Lineage Graph, and
  every chart tile simultaneously. (Foundation for Factory Replay, §16 v2.0.)

**Anti-patterns that violate Context Never Lost:**

- Full-page reloads on any user-initiated navigation.
- Modules with their own separate filter state that resets on entry.
- Losing the operator's selection after closing a drawer.
- Requiring the operator to re-select the time window after moving between
  Approvals and Timeline.
- Any "Welcome back!" screen or default-state redirect that erases the
  workspace posture.

**Rule of Reversibility:** any navigation an operator makes must be
reversible with a single keystroke (`Esc` / `⌘[`) with **zero loss of
selected context**.

---

## §2 The six operator questions

Unchanged from v1.0 §2 — see `FRONTEND_DESIGN_BIBLE.md`.

### §2b Bottom-up monitoring / top-down troubleshooting *(new v2.1 · P01)*

Two mental modes govern every screen:

- **Bottom-up monitoring** — in the normal state, the operator scans upward
  from atomic telemetry (status-rail chips, worker cards, artefact chips)
  to overall Factory posture. Nothing shouts; nominal state is glanceable
  at the base of the screen.
- **Top-down troubleshooting** — in the alert state, the operator drills
  downward from Attention feed → subsystem → evidence → root artefact.
  The direction inverts the moment attention is required.

Every screen supports both directions without navigation. Status rail
(bottom) supports monitoring; Attention panel + danger ribbon (top)
support troubleshooting. Neither is redundant with the other.

**Rule:** no critical decision path may require the operator to switch
between modules to complete a drill-down. Everything within a top-down
path is either in-place (Advanced Lens expansion, drawer) or one keystroke
away.

---

## §3 Information architecture — five layers

Unchanged from v1.0 §3.

---

## §4 Navigation hierarchy

Unchanged from v1.0 §4. Every URL is deep-linkable **and** carries the
Context Never Lost payload as query parameters (v2.1 §1.4.4).

---

## §5 Design system — foundations

### §5.1 Palette

Unchanged from D1 §3 (the Concept-D palette) — see
`D1_MISSION_CONTROL_VISUAL_BENCHMARK.md`.

### §5.2 Typography

Unchanged type-family choices from D1 §4 (Berkeley Mono · Neue Haas
Grotesk · GT Sectra).

**§5.2.1 Line length *(new v2.1 · P25)***

- Body copy: 60–75 characters per line. Never wider.
- Timeline narrative rows (D2 §3.1): 90 chars primary + 90 chars detail.
- Tooltips: 45–55 chars per line.
- Metric labels (UPPERCASE 11 px): 20–30 chars max.

Enforced by CSS `max-width` derived from character-width of the font at
each size, not by pixel guesses.

**§5.2.2 Scale ratio annotation *(new v2.1 · P26)***

The type scale (D1 §4.2) follows a **Minor-Third ratio (~1.15–1.22)**
between adjacent steps. Chosen for operator density: a strict 1.25
major-third would create too much size jump between chip labels and
body copy. Any future addition must respect this ratio; introducing a
size that violates it requires a v-major bump (§20.1).

### §5.3 Spacing

Unchanged 4-pt grid from v1.0 §5.3 (rejected 8-pt from UI/UX Pro Max —
operator density needs finer grid).

### §5.4 Concept-C whitespace heuristic *(new v2.1 · P27)*

If a Concept-C surface (Daily Briefing) *feels* like it has enough
whitespace, add another 50 %. This is a deliberate luxury signal —
restraint through generosity. Enforced via:

- `--space-7` (64 px) as the default section rhythm on Concept-C surfaces.
- `padding: var(--space-6) var(--space-7)` on Concept-C panels.

### §5.5 Iconography

Unchanged from v1.0 §5.4 (lucide-react · no emoji).

### §5.6 Corner radius

Unchanged from v1.0 §5.5.

### §5.7 Elevation

Unchanged from v1.0 §5.6 and D1 §5.3.

### §5.8 Grid

Unchanged from v1.0 §5.7 (12-column · 1440 px max).

---

## §6 Motion principles

### §6.1 Motion budget

Unchanged from v1.0 §6.1 (120 / 200 / 320 ms tiers · plus Editorial 400 ms
from D1 §6.1).

### §6.2 State semantics

Unchanged from v1.0 §6.2 and D1 §6.2.

### §6.3 Interaction latency budget *(new v2.1 · P14)*

Every operator interaction has a maximum acceptable latency. If we can't
hit it, we render an optimistic state.

| Action | Budget | Fallback if exceeded |
|---|---|---|
| Chip hover / focus | 16 ms | none — must be immediate |
| Filter apply (any `<FacetBar>`) | 100 ms | optimistic — show filtered result immediately, reconcile on server |
| Row selection | 100 ms | optimistic — draw the border first |
| Approve action | 300 ms | optimistic — remove card, spinner on side |
| Module navigation | 300 ms | skeleton for content, keep shell chrome mounted (v2.1 §1.4.4) |
| Chart re-render | 500 ms | skeleton then fade-in |
| Timeline stream push | 200 ms | already covered by §6.2 medium tier |

**Rule of Optimism.** The UI never waits on a state change the operator
initiated. Compute the intended state locally, render, then reconcile
with backend. On reconciliation failure, roll back visibly and show an
inline error (§15.3) — never a spinner-of-shame.

Reduced-motion (`prefers-reduced-motion`): optimistic behaviour continues;
only the transition animations are removed.

### §6.4 Library

Unchanged from v1.0 §6.3 (Framer Motion for JS-driven, CSS transitions
for state changes).

---

## §7 Component library

### §7.1 – §7.10

Unchanged from v1.0 §7.1 – §7.10 (Chip, Metric card, Pipeline stage bar,
Activity Row, Approval Card, Status rail, Worker card, Drawer / modal,
Table, ⌘K palette).

### §7.11 Widget trichotomy — dashboard tiles *(new v2.1 · P05, P08)*

Every dashboard tile is exactly one of three primitives. Never a fourth.

#### 7.11.1 Metric block

Single hero number + delta + evidence link. Reuses §7.2 anatomy (A / B / C
variants by concept — see D1 §7.2).

Size floor: 240 × 120 px workstation, 200 × 100 px tablet.

#### 7.11.2 Chart tile

A single chart (line / bar / sparkline / small-multiple), rendered per §14
(chart standards). Every chart tile carries:

- **Title** — Division voice (`Execution Division · fill quality (p95)`).
- **Trailing high/low annotations** (§14.5).
- **Time-window chip** — persistent, changeable in place (§7.13).
- **Drill-through** — click anywhere in the plot area opens the underlying
  table view (§7.11.3) scoped to the click's data slice (§14.6).
- **Export chip** — small `⇩ CSV / permalink / image` control, bottom-right
  of tile (§14.7).
- **Three-view toggle** — chart ↔ table ↔ list, Advanced Lens only (§14.8).

Size floor: 360 × 220 px workstation, 320 × 200 px tablet.

#### 7.11.3 Table tile

Dense, virtualised row list with column-header discipline (§7.9). Rules:

- Column-header row UPPERCASE 11 px caption.
- Values tabular-nums.
- Row hover reveals inline actions (Approve · Compare · Pin) — Everywhere-
  Actionable rule (§19.6).
- Row click opens the underlying artefact in Evidence Drawer (§10).
- Column sort discreet (arrow chevron); sorted column gets `--stroke-2`
  header background.

Size floor: 480 × 320 px workstation. **100 %-column-visibility rule** at
all postures — no horizontal scroll ever; collapse columns to Advanced
Lens instead.

#### 7.11.4 Tile-composition rules

- A dashboard is a set of tiles laid on a 12-column grid.
- No tile spans more than 8 columns.
- No tile is shorter than its size floor.
- No dashboard exceeds 12 tiles workstation / 6 tiles tablet / 4 tiles
  briefing. Median dashboard: 4–6 tiles.
- Every tile is drill-through capable. Zero dead-end tiles.
- Every tile is permalink-shareable.
- Every tile respects Context Never Lost (§1.4.4) — its filter state and
  time-window travel with the workspace.

#### 7.11.5 Persona defaults

- **Executive · Briefing.** ≤ 4 tiles; C-variant metric blocks dominant;
  chart tiles annotated (trailing highs + narrative caption).
- **Operations · Mission Control.** 6–8 tiles; A-variant metric blocks
  + chart tiles; table tiles reserved for Attention (§8.8) and
  Accomplishments row.
- **Research · Workspace.** 4–6 tiles; B-variant metric blocks + chart
  tiles + table tiles freely mixed.
- **Developer.** All views but with Advanced Lens auto-on.

### §7.12 Pinned Preview *(new v2.1 · P18)*

A first-class comparison affordance. Any artefact surface can expose a
`📌 pin` control. Pinned items live in a **global pins tray** adjacent to
the right rail (max 4 pins). Any pinned item can be:

- Opened in Evidence Drawer.
- Compared side-by-side with any other pin (renders a 2-up split).
- Cleared individually or all at once.

**Scope:** workspace-global, session-persistent — pins survive every
module navigation (Context Never Lost §1.4.4).

**Applicable surfaces (Sprint 1 subset):** Strategy Explorer rows,
Approval Cards (pin to defer without acting), Portfolio candidates,
Worker cards (from Workforce Org Chart).

**Full applicability (later Sprints):** every artefact with an Evidence
Drawer.

**Visual:** pinned item chip in tray shows Division voice label + type
icon.

**Motion:** 120 ms fade + border tint when pinned; pins tray slides in
200 ms when first pin arrives, then persists.

**Accessibility:** keyboard binding `⌘P` to pin the currently focused
row; tray reachable via ⌘K > pins.

### §7.13 Time-window chip *(new v2.1 · P12)*

A shared reusable control for any surface where time is a query dimension.
Appears in the header of the surface it scopes.

**States:**
- `live ▸` — real-time (default for Timeline, Approvals, Workforce)
- `last 1 h` / `last 24 h` / `last 7 d` / `last 30 d` — presets
- `custom …` — opens a range picker (workstation only)

**Style:** 24 px pill, `--font-caption`, `--sig-info` background at 10 %
alpha when non-default; hollow when `live ▸`.

**Consistency rule:** every surface using a time-window chip uses the
*same* preset labels — switching surfaces preserves the operator's mental
model. Component: `<TimeWindowChip>`.

**Cascade rule (Context Never Lost §1.4.4):** setting the chip on any
surface **cascades** to every other surface where time is a query
dimension. If the operator sets `last 7 d` on Timeline, Approvals renders
with the same window when opened.

**Currently used on:** Timeline (D2 §6.3). New usage (Sprint 1 targets):
Approvals age filter (D3 §4), Chart tiles (§7.11.2), Workforce Org Chart.

Factory Replay reservation (v2.0 §16): setting the chip to a past value
on any surface cascades to every surface — this is the flagship Replay
UX.

---

## §8 Dashboard & module layouts

### §8.1 – §8.6

Unchanged from v1.0 §8.1 – §8.6.

### §8.7 Salience heuristic — layout rule *(new v2.1 · P04)*

On any dashboard, tile size is *not* proportional to information volume;
it is proportional to **decision consequence**. A tile that requires
immediate operator judgement is larger than a tile that reports nominal
state.

**Practical rule.** On Mission Control (§8.1), the Attention panel and
the Approvals panel are always the largest tiles when their counts > 0.
When counts fall to 0, they shrink to metric-block size and cede real
estate to the Accomplishments row.

This is dynamic layout — implemented via container queries or a small
layout-rule engine, not by user drag-and-drop.

### §8.8 Attention panel severity ordering *(new v2.1 · P02)*

The Attention panel (Q6) orders items by **severity**, not by recency.

Order: `Critical (--sig-crit)` → `Warn (--sig-warn)` → `Advisory
(--sig-advisory)`.
Within a severity: ordered by age (oldest first — because oldest
unresolved is most important).

Panel shows top 3; overflow reads `+ 12 more · view all`.

**Anti-pattern** (never): most-recent-first ordering. That treats the
Attention feed as a chat; it isn't.

---

## §9 AI interaction patterns

Unchanged from v1.0 §9 and v2.0 §4 (Copilot elevation). See §24 of this
document.

---

## §10 Evidence visualization standards

### §10.1 Eight canonical stages

Unchanged from v1.0 §10.1.

### §10.2 Lineage Graph mode *(new v2.1 · P16, P17)*

The Lineage bar (D1 §10) shows one hop up and one hop down as a compact
strip. For deeper investigation, every artefact page and every Approval
Card exposes a `⇱ Lineage graph` affordance in the top-right of the
lineage bar.

Clicking opens the Lineage Graph in a full-width drawer covering the
right two-thirds of the viewport.

#### 10.2.1 Graph anatomy

- **Central node:** the current artefact, highlighted with 2 px
  `--sig-info` stroke.
- **Ancestors** flow left → right; each node is a chip with Division-voice
  label; edges show traversal type (`derived from`, `mutation of`,
  `promoted from`).
- **Descendants** flow right → left from the central node.
- Auto-arranged layout (never free-form; we control the algorithm).
- Grid: subtle 1 px `--stroke-1` background.

#### 10.2.2 Subgraph focus (dependency view)

Right-click any node → *"Show only this subgraph"* → rest of the graph
fades to `--content-lo` at 30 % alpha. Reveals only ancestors and
descendants of the selected node.

**D3 integration:** Approval Card `downstream` chip opens the graph in
`descendants-only` mode focused on the approval subject.

#### 10.2.3 Time-window integration

Respects the surface's time-window chip (§7.13). Setting the chip to a
past value renders the graph *as it existed at that time*. Factory Replay's
first-class experience (v2.0 §16 honoured).

#### 10.2.4 Actions from graph

- Click any node → opens that artefact's Evidence Drawer.
- Pin any node → adds to Pinned Preview tray (§7.12).
- Right-click → subgraph focus (§10.2.2).
- `Esc` → closes the drawer, returns to the surface with Context Never
  Lost (§1.4.4) preserved.

#### 10.2.5 Empty states

- **Root generation:** *"This artefact is a root generation. No ancestors
  recorded."* → `view generation evidence` · `close graph`
- **Replay-empty:** *"No lineage existed at the selected time. Try widening
  the time window."* → `expand window` · `return to live`

#### 10.2.6 Performance

- Max 3 edges per node visible at each zoom level (aggressive edge-bundling
  above).
- Max 200 nodes per graph (larger factories get paginated ancestry).
- Enter animation: 320 ms fade + 400 ms edge-draw stagger (respects
  `prefers-reduced-motion`).

---

## §11 Approval workflow

### §11.1 – §11.5

Unchanged from v1.0 §11.1 – §11.5 and refined in D3.

### §11.6 Facet grammar — architectural principle *(new v2.1 · P11)*

Every surface with a filter model uses the *same* facet grammar:

```
[ All ▾ ]  [ <primary facet> ▾ ]  [ <secondary facet> ▾ ]  [ Time-window ]  [ q ⌘K ]
```

Primary facets are per-surface; secondary facets are shared:
- `Risk` (low / medium / high)
- `Age` (aliased to time-window if not present)
- `Persona / Actor / Division` (context-sensitive label)

**Rule:** switching between surfaces preserves the operator's mental
model. The filter chip strip is a shared React component (`<FacetBar>`),
not a per-module reimplementation.

**Context Never Lost integration (§1.4.4):** the `<FacetBar>` state lives
in workspace state store. A facet selected on one surface follows the
operator to every surface where that facet is applicable.

---

## §12 Master Bot & AI Workforce visualization

Unchanged from v1.0 §12; **codified in detail in D4**
(`D4_MASTER_BOT_WORKFORCE.md`).

---

## §13 Data quality & infrastructure visualization

Unchanged from v1.0 §13.

---

## §14 Notification philosophy and chart standards

### §14.1 – §14.4 Notification philosophy

Unchanged from v1.0 §14.1 – §14.4.

### §14.5 Trailing highs / lows — chart annotation rule *(new v2.1 · P07)*

Every chart shows both the trailing high and trailing low of the visible
window as thin `--content-lo` reference lines with 11 px caption labels.

**Labels:** `high 91.4 % · 12 d ago` / `low 68.2 % · 3 d ago`.

Chart titles must never repeat these numbers — annotations are
self-standing.

### §14.6 Drill-through mandate *(new v2.1 · P08)*

Every chart tile is drill-through capable. Clicking anywhere in the plot
area opens a table view (§7.11.3) filtered to the click's data slice.

**Example:** clicking on the *Wednesday* bar of a weekly volume chart
opens a table filtered to Wednesday's rows.

### §14.7 Permalink and export *(new v2.1 · P09, P15)*

Every chart tile carries a small `⇩` chip bottom-right (opacity 0
default; 0.6 on tile hover; 1.0 on chip hover). Menu:

- `Copy permalink` — URL that renders exactly this tile with exactly this
  filter/time state.
- `Export CSV` — downloads the tile's dataset.
- `Copy as image` — PNG for briefings.

Every other L1–L3 evidence view is likewise permalink-shareable (§1.4.4
Context Never Lost implies URL-encodable state).

### §14.8 Three-view toggle *(new v2.1 · P10)*

When Advanced Lens is on, every chart tile shows a small `chart ▾` chip
in the top-right corner. Choices: `chart · table · list`. Same data,
three registers. Toggle persists per tile per session (§1.4.4).

---

## §15 Empty / loading / error / dormant states

Unchanged from v1.0 §15 and expanded in D1 §13.

New authored states will be added in D7 for:
- Lineage Graph empty (root generation, replay-empty) — §10.2.5.
- Pinned Preview empty — nothing pinned yet.
- Chart drill-through empty — no rows in slice.

---

## §16 Responsiveness

Unchanged from v1.0 §16.

---

## §17 Accessibility

Unchanged from v1.0 §17 (WCAG 2.2 AA).

---

## §18 Operator workflows

Unchanged from v1.0 §18. Every workflow now assumes Context Never Lost
(§1.4.4) — no explicit "return to previous state" step is needed because
context always survives.

---

## §19 Naming, iconography & copy

### §19.1 – §19.5

Unchanged from v1.0 §19.1 – §19.5 and refined by D2 Addendum
(Storytelling Copy Standard — Division voice).

### §19.6 Everywhere-Actionable *(new v2.1 · P13)*

Any row in any feed / table / list must expose the primary actions of
its underlying artefact inline. The operator never has to open the
artefact to act on it, except when the action requires additional
context.

**Examples:**
- Timeline row (`actor: approval`) → expand shows the full Approval Card
  with 4 actions inline (D3 §1.4).
- Strategy Explorer row → hover reveals `Compare · Pin · Route to
  Portfolio · View evidence` inline actions.
- Approval Center row → 4 actions always visible on card.
- Workforce Org Chart worker card → `View evidence · Pin worker` inline.

**Rule:** if the primary action for an artefact requires navigation to a
different module to complete, the design has failed. Fix in-place or
move the action inline.

---

## §20 Extensibility & governance

Unchanged from v1.0 §20.

**v-major bump policy** (§20.1) also applies to any change that would
violate the four foundational principles (§1.4) — Context Never Lost is
now among them.

---

## §21 Design principles poster (v2.1)

Print these; put them next to the workstation.

1. **Evidence over completion.** Never "Completed." Always the pipeline stage.
2. **Six questions per screen.** Or delete it.
3. **The AI is alive.** The right rail proves it, every minute.
4. **Density with air.** Bloomberg information · SpaceX discipline.
5. **Signal is sacred.** Six signal colours. Never a seventh.
6. **Layers, not tabs.** Operators live at Layer 1–3.
7. **Master Bot is the CEO.** Every worker is under an org chart.
8. **Approvals are the only UI-driven decision.** Everything else is observation.
9. **Empty is a state, not a bug.** Author it. Explain it. Offer an action.
10. **Keyboard first.** ⌘K wins every debate about buried features.
11. **Bottom-up monitoring · top-down troubleshooting.** *(new)*
12. **Everything drills through.** Zero dead-end tiles. *(new)*
13. **Context is never lost.** One continuous workspace. *(new)*
14. **Salience ∝ consequence.** The most important tile is the biggest. *(new)*
15. **The UI never waits.** Optimistic first, reconcile later. *(new)*

---

## §22 Personalization modes

Unchanged from v2.0 §2 · updated with Context Never Lost.

**v2.1 addendum:** every mode preserves **Decision Identity** — a
decision, approval, metric, or evidence object represents the same
underlying truth in every mode. Modes change emphasis, layout, wording
and density; they never alter the underlying values or meaning. See
D6 §8.1a for full spec.

Mode is orthogonal to posture (workstation / tablet / briefing) and
preserved across navigation (§1.4.4).

---

## §23 Signature graphics inventory

Unchanged from v2.0 §3.1. G1–G8 codification detailed in D5 (pending).

**v2.1 addendum:** G3 (Knowledge Graph) shares implementation with §10.2
(Lineage Graph mode) — one component, two uses. Pinned Preview (§7.12)
applies to G2, G3, G5, G6.

---

## §24 Copilot elevation

Unchanged from v2.0 §4.

**v2.1 addendum (P24):** under Advanced Lens, Copilot answers expose an
optional trace (retrieval → reasoning → citation) as an expandable panel
below the answer. Detailed in D6 (pending).

---

## §25 Design-first workflow

Unchanged from v2.0 §5.

**Status as of v2.1:**
- D0 Visual language ✅ (Concept D)
- D1 Mission Control benchmark ✅
- D2 AI Activity Timeline + Storytelling Addendum ✅
- D3 Approval Center ✅ (with v2.1 in-place patch applied)
- D4 Master Bot & Workforce Org Chart — **currently authoring**
- D5 Signature graphics gallery — pending
- D6 Personalization modes — pending
- D7 Empty / loading / error / dormant library — pending
- D8 Sprint 1 detailed plan — pending

---

## Appendix A · Component migration checklist

Unchanged from v1.0.

---

## Appendix B · Sprint 1 candidate scope

Updated for v2.1. Sprint 1 must ship:

1. **Widget trichotomy primitives** (§7.11) — highest-leverage delta.
2. **`<FacetBar>` shared component** (§11.6) — Timeline, Approvals,
   Mission Control tile filters.
3. **`<TimeWindowChip>`** (§7.13) — reusable control.
4. **Interaction latency budget enforcement** (§6.3) — optimistic UI on
   filter apply, row select, approve action.
5. **Chart tile anatomy** (§7.11.2 + §14.5–14.8) — trailing high/low,
   drill-through, permalink, export.
6. **Attention panel severity ordering** (§8.8).
7. **Workspace state store** (§1.4.4) — the foundation of Context Never
   Lost; a Sprint 1 architectural requirement.
8. **Deep-linkable URL scheme** carrying context payload (§4.3 + §1.4.4).

**Sprint 2 (non-goals for Sprint 1):**
- Lineage Graph mode (§10.2)
- Pinned Preview (§7.12)
- Master Bot Plan Contract surface (D4)
- Copilot trace-as-UI (§24)

---

## Appendix C · What is NOT in this Bible

Unchanged from v1.0.

---

## Appendix D · v2.1 changelog

**Added (15 patterns from `DESIGN_INSPIRATION_STUDY.md`):**

- §1.4.4 Context Never Lost (new fourth foundational principle)
- §2b Bottom-up / top-down IA rule
- §5.2.1 Line-length rule (60–75 chars)
- §5.2.2 Type-scale ratio annotation
- §5.4 Concept-C whitespace heuristic
- §6.3 Interaction latency budget
- §7.11 Widget trichotomy (largest addition)
- §7.12 Pinned Preview
- §7.13 Time-window chip
- §8.7 Salience heuristic
- §8.8 Attention panel severity ordering
- §10.2 Lineage Graph mode (second-largest addition)
- §11.6 Facet grammar
- §14.5–14.8 Chart standards (trailing high/low · drill-through · permalink · three-view toggle)
- §19.6 Everywhere-Actionable rule

**Patched:**
- D3 §2 downstream chip → clickable → opens Lineage Graph subgraph.
- D3 §13 acceptance criteria — added CNL + Lineage Graph rows.

**Superseded:**
- Bible v1.0 as canonical (still referenced for unchanged sections).
- Bible v2.0 delta (superseded — v2.0 additions folded into v2.1).

**Inviolate (untouched):**
- Six operator questions.
- Five-layer IA.
- Eight-module nav.
- Six-signal colour ceiling.
- 120 / 200 / 320 ms motion budget.
- 4-pt spacing grid.
- Danger ribbon reserved for Critical only.
- Copilot never acts, only observes.
- Terminology dictionary.
- Backend Feature Freeze.

---

*End of Frontend Design Bible v2.1.*
*Approved 2026-07-20. Governs D4 onward.*

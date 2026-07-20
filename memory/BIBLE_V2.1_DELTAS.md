# Bible v2.1 — Implementation-Ready Deltas

> Implementation reference. Every proposed change to
> `FRONTEND_DESIGN_BIBLE.md` (v1.0) and the D-series design documents,
> derived from `DESIGN_INSPIRATION_STUDY.md`.
>
> Every delta below is:
> - Rationale-linked (which study pattern justifies it).
> - Principle-linked (which of the three D1 principles it serves).
> - Reversal-safe (does *not* contradict any inviolate rule).
> - Scoped (in-place additions, not structural rewrites).
>
> **Nothing in this document takes effect until the operator approves it.**
> On approval, these deltas are folded into Bible v2.1 and the pending
> D-series documents.
>
> Prepared 2026-07-20. Companion: `DESIGN_INSPIRATION_STUDY.md`.

---

## Contents

1. Bible v1.0 additions (v2.1 folded numbering)
2. D1 additions
3. D2 — no changes proposed
4. D2 Addendum — no changes proposed
5. D3 — one in-place patch
6. D4 (pending) — deltas to bake in at authoring
7. D5 (pending) — deltas to bake in at authoring
8. D6 (pending) — deltas to bake in at authoring
9. D7 (pending) — deltas to bake in at authoring
10. D8 (pending) — deltas to bake in at authoring
11. Inviolate rules — untouched
12. Approval checklist

---

## 1. Bible v1.0 additions (v2.1 folded numbering)

Each delta below cites its **study pattern reference** (P##, per §2 of
`DESIGN_INSPIRATION_STUDY.md`) and the **D1 principle** it serves:
`IL = Invisible Luxury` · `EC = Everything Connected` · `PD = Progressive
Disclosure`.

### 1.1 New §2b — Bottom-up monitoring, top-down troubleshooting

*(P01 · IL · EC — insertion after Bible §2)*

Add a new subsection under §2 (six operator questions):

```
## 2b. Direction of information consumption

Two mental modes govern every screen:

- **Bottom-up monitoring.** In the normal state, the operator scans upward
  from atomic telemetry (status-rail chips, per-worker cards, per-artefact
  chips) to overall Factory posture. Nothing shouts; nominal state is
  glanceable at the base of the screen.
- **Top-down troubleshooting.** In the alert state, the operator drills
  downward from the Attention feed → subsystem → evidence → root artefact.
  The direction inverts the moment attention is required.

Every screen must support both directions without navigation. The
status-rail (bottom) supports monitoring; the Attention panel + danger
ribbon (top) support troubleshooting. Neither is redundant with the other.

Rule: no critical decision path may require the operator to switch between
modules to complete a drill-down. Everything within a top-down path is
either in-place (Advanced Lens expansion, drawer) or one keystroke away.
```

### 1.2 §4.4 — Line length (typography)

*(P25 · IL — append to Bible §4 / D1 §4)*

Add after §4.3 numeric formatting rules:

```
### 4.4 Line length

- Body copy: 60–75 characters per line. Never wider.
- Narrative rows in AI Activity Timeline (D2 §3.1): capped at 90 chars
  primary + 90 chars detail — tighter, because rows are consumed at speed.
- Tooltips: 45–55 chars per line — narrower again, for peripheral vision.
- Metric labels (UPPERCASE 11 px): 20–30 chars max — the language of chips.

Enforced by CSS `max-width` on text containers derived from character-width
of the font at each size, not by pixel guesses.
```

### 1.3 §4.5 — Type scale ratio annotation

*(P26 · IL — clarify D1 §4.2)*

Add above the type-scale table in D1 §4.2:

```
The type scale follows a Minor-Third ratio (~1.15–1.22) between adjacent
steps — chosen for operator density (a strict 1.25 major-third would
create too much size jump between chip labels and body copy). Any future
addition must respect the ratio; introducing a size that violates it
requires a v-major bump (Bible §20.1).
```

### 1.4 §5.1 — Concept-C 50 %-whitespace heuristic

*(P27 · IL — append to Bible §5.3 spacing / D1 §5.1)*

Add after the density-mode table:

```
Concept-C surface (Daily Briefing) whitespace heuristic:
if a Concept-C panel *feels* like it has enough whitespace, add another
50 %. This is a deliberate luxury signal — restraint through generosity.
Enforced via `--space-7` (64 px) as the *default* section rhythm on
Concept-C surfaces, and via `padding: var(--space-6) var(--space-7)` on
Concept-C panels (already spec'd in D1 §5.3 `.panel-c`).
```

### 1.5 §6.3 — Interaction latency budget

*(P14 · IL — new subsection in Bible §6)*

Add to §6 (Motion principles):

```
### 6.3 Interaction latency budget

Every operator interaction has a maximum acceptable latency. If we can't
hit it, we render an optimistic state.

| Action | Budget | Fallback if exceeded |
|---|---|---|
| Chip hover / focus | 16 ms | none — must be immediate |
| Filter apply | 100 ms | optimistic UI (show filtered result immediately, reconcile on server) |
| Row selection | 100 ms | optimistic — draw the border first |
| Approve action | 300 ms | optimistic — remove card, spinner on side |
| Module navigation | 300 ms | skeleton for content, keep chrome |
| Chart re-render | 500 ms | skeleton then fade-in |
| Timeline stream push | 200 ms | already covered (§6.2 medium tier) |

**Rule of optimism:** the UI never *waits* on a state change the operator
initiated. Compute the intended state locally, render, then reconcile with
backend. If reconciliation fails, roll back visibly and show an inline
error (Bible §15.3) — never a spinner-of-shame.

Reduced-motion (`prefers-reduced-motion`): optimistic behaviour continues;
only the transition animations are removed.
```

### 1.6 §7.11 — Widget trichotomy (new §7 primitive)

*(P05, P08 · IL · EC · PD — new subsection in Bible §7 / D1 §7)*

Add as a new §7 primitive — this is the largest single delta and defines
Strategy Factory's dashboard tile vocabulary:

```
### 7.11 Widget trichotomy (dashboard tiles)

Every dashboard tile is exactly one of three primitives. Never a fourth.

#### 7.11.1 Metric block

Single hero number + delta + evidence link.
Reuses §7.2 anatomy (A / B / C variants by concept).
Size floor: 240 × 120 px workstation, 200 × 100 px tablet.

#### 7.11.2 Chart tile

A single chart (line / bar / sparkline / small-multiple), rendered per
§14 (chart standards).
Every chart tile carries:
- **Title** — Division voice (`Execution Division · fill quality (p95)`).
- **Trailing high/low annotations** — every chart shows both.
- **Time window chip** — persistent, changeable in place (§7.13).
- **Drill-through** — click anywhere in the plot area → opens the
  underlying table view (§7.11.3) as a drawer scoped to the click location.
- **Export chip** — small `⇩ CSV / permalink` control, bottom-right of tile.
- **Three-view toggle (Advanced Lens only)** — chart ↔ table ↔ list.

Size floor: 360 × 220 px workstation, 320 × 200 px tablet.

#### 7.11.3 Table tile

A dense, virtualised row list with column-header discipline (§7.9).
Rules:
- Column-header row UPPERCASE 11 px caption.
- Values tabular-nums.
- Row hover reveals actions inline (Approve · Compare · Pin).
- Row click opens the underlying artefact in Evidence Drawer (§10).
- Column sort discreet (arrow chevron); sorted column stroke background.

Size floor: 480 × 320 px workstation; 100 %-column-visibility rule at all
postures (no horizontal scroll — collapse columns to Advanced Lens instead).

#### 7.11.4 Tile-composition rules

- A dashboard is a set of tiles laid on a 12-column grid.
- No tile spans more than 8 columns.
- No tile is shorter than the size floor above.
- No dashboard exceeds 12 tiles workstation / 6 tiles tablet / 4 tiles
  briefing. Median dashboard should have 4–6 tiles.
- Every tile is drill-through capable. Zero dead-end tiles.
- Every tile is permalink-shareable.

#### 7.11.5 Persona defaults

- **Executive · Briefing.** ≤ 4 tiles per view; C-variant metric blocks
  dominant; chart tiles annotated (trailing highs + narrative caption).
- **Operations · Mission Control.** 6–8 tiles; A-variant metric blocks
  + chart tiles; table tiles reserved for the Attention panel and the
  Accomplishments row.
- **Research · Workspace.** 4–6 tiles; B-variant metric blocks +
  chart tiles + table tiles freely mixed.
- **Developer.** All views but with Advanced Lens auto-on.
```

### 1.7 §7.12 — Pinned Preview (new primitive)

*(P18 · EC · PD — new subsection in Bible §7)*

```
### 7.12 Pinned Preview

A first-class comparison affordance. Any artefact surface can expose a
`📌 pin` control. Pinned items sit in a global right-rail-adjacent
"pin tray" (max 4 pins). Any pinned item can be:
- Opened in Evidence Drawer.
- Compared side-by-side with any other pin (renders a 2-up split).
- Cleared individually or all at once.

Pin scope: workspace-global, persistent per session; pins survive module
navigation.

Applicable surfaces (Sprint 1 subset): Strategy Explorer rows, Approval
Cards (pin to defer without acting), Portfolio candidates, Worker cards.
Full applicability (later Sprints): every artefact with an Evidence Drawer.

Visual: pinned item chip in tray shows Division voice label + type icon.
Motion: 120 ms fade + border tint when pinned; pins tray slides in 200 ms
when first pin arrives, persists.

Accessibility: keyboard binding `⌘P` to pin the currently focused row;
tray reachable via ⌘K > pins.
```

### 1.8 §7.13 — Time-window chip (reusable control)

*(P12 · EC — new subsection in Bible §7)*

```
### 7.13 Time-window chip

A shared, reusable control for any surface where time is a query
dimension. Appears in header of the surface it scopes.

States:
- `live ▸` — real-time (default for Timeline, Approvals)
- `last 1 h` / `last 24 h` / `last 7 d` / `last 30 d` — presets
- `custom …` — opens a range picker (workstation only)

Style: 24 px pill, `--font-caption`, `--sig-info` background at 10 %
alpha when non-default; hollow when `live ▸`.

Rule of Consistency: whichever surface uses a time-window chip must
respect the *same* preset labels, so switching surfaces preserves the
operator's mental model.

Currently used on: Timeline (D2 §6.3). New usage (Sprint 1 targets):
Approvals age filter (D3 §4), Chart tiles (§7.11.2).

Factory Replay reservation: setting the chip to a past value on any
surface eventually will *cascade* to every surface (§16 architectural
reservation).
```

### 1.9 §8.7 — Salience heuristic (Mission Control layout)

*(P04 · IL — append to Bible §8)*

```
### 8.7 Salience proportional to decision consequence

On any dashboard, tile size is *not* proportional to information volume;
it is proportional to *decision consequence*. A tile that requires
immediate operator judgement is larger than a tile that reports nominal
state.

Practical rule: on Mission Control (§8.1), the Attention panel and the
Approvals panel are always the largest tiles when their counts > 0. When
counts fall to 0, they shrink to metric-block size and cede real estate
to the Accomplishments row.

This is dynamic layout — implemented via container queries or a small
layout rule engine, not by user drag-and-drop.
```

### 1.10 §8.8 — Attention panel severity ordering

*(P02 · IL — append to Bible §8)*

```
### 8.8 Attention panel ordering

The Attention panel (Q6) orders items by *severity*, not by recency.

Order: `Critical (--sig-crit)` → `Warn (--sig-warn)` → `Advisory
(--sig-advisory)`. Within a severity, ordered by age (oldest first —
because oldest unresolved is most important).

The panel shows the top 3 items. Overflow reads `+ 12 more · view all`.

**Anti-pattern** (never do): most-recent-first ordering. That treats the
Attention feed as a chat; it isn't.
```

### 1.11 §10.2 — Lineage Graph mode (dual-view toggle)

*(P16, P17 · EC — new subsection in Bible §10)*

Add after §10 (Everything-Connected — the Lineage layer). This is the
second-largest single delta:

```
### 10.2 Lineage Graph mode

The Lineage bar (§10.1) shows one hop up and one hop down as a compact
strip. For deeper investigation, every artefact page and every Approval
Card exposes a *"Lineage graph ⇱"* affordance in the top-right of the
lineage bar. Clicking opens the Lineage Graph in a full-width drawer
covering the right two-thirds of the viewport.

#### 10.2.1 Graph anatomy

- **Central node:** the current artefact, highlighted with 2 px
  `--sig-info` stroke.
- **Ancestors** flow *left → right*: each node is a chip with Division
  voice label. Edges show the traversal type (`derived from`, `mutation
  of`, `promoted from`).
- **Descendants** flow *right → left* from the central node.
- Layout is auto-arranged (Palantir-inspired but constrained: never
  free-form; we control the algorithm).
- Grid: subtle 1 px `--stroke-1` background.

#### 10.2.2 Subgraph focus (dependency view)

Right-click any node → *"Show only this subgraph"* → the rest of the
graph fades to `--content-lo` at 30 % alpha. Reveals only ancestors and
descendants of the selected node.

#### 10.2.3 Time-window integration

The Lineage Graph respects the surface's time-window chip (§7.13). Setting
the chip to a past value renders the graph *as it existed at that time*.
This is Factory Replay's first-class experience (Bible §16 reservation
honoured).

#### 10.2.4 Actions from graph

- Click any node → opens that artefact's Evidence Drawer.
- Pin any node → adds to Pinned Preview tray (§7.12).
- Right-click → subgraph focus (§10.2.2).
- `Esc` → closes the drawer.

#### 10.2.5 Empty state

`No lineage available yet — this artefact is a root generation.`
`→ view generation evidence`

#### 10.2.6 Performance

- Rendered with 3 or fewer edges per node visible at each zoom level
  (aggressive edge-bundling above that).
- Max 200 nodes per graph (larger factories get paginated ancestry).
- Enter animation: 320 ms fade + a 400 ms edge-draw stagger (respects
  `prefers-reduced-motion`).
```

### 1.12 §11.6 — Facet grammar principle

*(P11 · PD · EC — append to Bible §11)*

Add after §11 approval workflow (or as a standalone architectural
principle in §5 foundations):

```
### 11.6 Facet grammar (architectural principle)

Every surface with a filter model uses the *same* facet grammar:

```
[ All ▾ ]  [ <primary facet> ▾ ]  [ <secondary facet> ▾ ]  [ Time-window ]  [ q ⌘K ]
```

Primary facets are per-surface; secondary facets are shared:
- `Risk` (low / medium / high)
- `Age` (aliased to time-window if not present)
- `Persona / Actor / Division` (context-sensitive label)

Rule: switching between surfaces preserves the operator's mental model.
The filter chip strip is a shared React component (`<FacetBar>`), not a
per-module reimplementation.
```

### 1.13 §14 additions — chart standards

*(P07, P09, P10, P15 · EC · PD — append to Bible §14)*

Add after §14 (chart standards):

```
### 14.5 Trailing highs / lows (annotation rule)

Every chart shows both the trailing high and trailing low of the visible
window as thin `--content-lo` reference lines with 11 px caption labels.
Labels format: `high 91.4 % · 12 d ago` / `low 68.2 % · 3 d ago`. Chart
titles must never repeat these numbers — the annotations are self-standing.

### 14.6 Drill-through mandate

Every chart tile is drill-through capable. Clicking anywhere in the plot
area opens a table view (§7.11.3) filtered to the click's data slice.
For example: clicking on the "Wednesday" bar of a weekly volume chart
opens a table filtered to Wednesday's rows.

### 14.7 Permalink and export

Every chart tile carries a small `⇩` chip bottom-right (opacity 0 default;
0.6 on tile hover; 1.0 on chip hover). Menu:

- `Copy permalink` — URL that renders exactly this tile with exactly this
  filter/time state.
- `Export CSV` — downloads the tile's dataset.
- `Copy as image` — PNG for briefings.

### 14.8 Three-view toggle (Advanced Lens)

When Advanced Lens is on, every chart tile shows a small `chart ▾` chip
in the top-right corner. Choices: `chart · table · list`. Same data, three
registers. Toggle persists per tile per session.
```

### 1.14 §19.6 — *Everywhere-Actionable* rule

*(P13 · EC · PD — append to Bible §19)*

Add:

```
### 19.6 Everywhere-Actionable

Any row in any feed / table / list must expose the primary actions of its
underlying artefact inline. The operator never has to open the artefact
to act on it, except when the action requires additional context.

Examples:
- Timeline row (`actor: approval`) → expand shows the full Approval Card
  with 4 actions inline (D3 §1.4).
- Strategy Explorer row → hover reveals `Compare · Pin · Route to
  Portfolio · View evidence` inline actions.
- Approval Center row (Center module) → 4 actions always visible on card.
- Workforce Org Chart worker card → `View evidence · Pin worker` inline.

Rule: if the primary action for an artefact requires navigation to a
different module to complete, the design has failed. Fix in-place or move
the action inline.
```

---

## 2. D1 additions

D1 already establishes the visual system in depth. Only annotations required:

### 2.1 D1 §4.2 — annotate the scale ratio

*(P26)*

Add one sentence above the type-scale table:

> The scale follows a Minor-Third ratio (~1.15–1.22) between adjacent
> steps — chosen for operator density; any future addition must respect
> the ratio.

### 2.2 D1 §7.2 C-variant — add `clamp()` for Briefing hero

*(P28)*

Replace the C-variant fixed-px hero:

```
    91.4 %                            ← --font-metric-hero (48 px light ivory)
```

With responsive:

```
    91.4 %                            ← clamp(2.5rem, 4vw, 3rem) light ivory
```

Update D1 §4.2 `--font-metric-hero` row: `clamp(2.5rem, 4vw, 3rem)`.

### 2.3 D1 §14 — add cross-references

Add a "See also" line under §14 pointing to Bible §14.5 – §14.8 (which now
carry the chart-standard deltas listed in §1.13 above).

---

## 3. D2 — no changes proposed

D2 (`D2_AI_ACTIVITY_TIMELINE.md`) and its addendum are unchanged.

The Timeline scrub (D2 §6.3) is *already* the Factory-Replay reservation
that Palantir's dependency-view and Linear's time-window chip inspired.
No delta needed.

---

## 4. D2 Addendum — no changes proposed

The Storytelling Copy Standard (D2 Addendum) is validated by every
inspiration source — Linear's terse voice, Palantir's ontology-first
naming, Mission Control's procedure-linked-alert copy discipline all
support the Division voice we've chosen. No delta needed.

---

## 5. D3 — one in-place patch

D3 (`D3_APPROVAL_CENTER.md`) is approved. One small in-place patch is
proposed — no structural change.

### 5.1 Patch D3 §2.1 field table (downstream field)

Current text:

> Downstream | one-line affected-artefact summary | + explicit counts and links

Patched text:

> Downstream | one-line affected-artefact summary. Chip label is
> **clickable** — click opens the Lineage Graph (Bible §10.2 · new)
> focused on this approval's subject in **descendants-only** mode. |
> + explicit counts and links | (Advanced Lens shows the count inline
> without opening the graph.)

### 5.2 Patch D3 §2 card ASCII

Add a hover-hint indicator on the `Will enter portfolio candidate pool`
line:

```
│  ── downstream ────────────────────────────────────────────── ─  │
│  Will enter portfolio candidate pool · risk 0.4 % max      →     │  ← clickable → subgraph
```

### 5.3 Patch D3 §13 acceptance criteria

Add one line to the acceptance criteria:

- ✅ Downstream chip opens Lineage Graph subgraph (Bible §10.2) in
  descendants-only mode.

---

## 6. D4 (pending) — deltas to bake in at authoring

When D4 (Master Bot & Workforce Org Chart) is drafted, incorporate:

### 6.1 Master Bot Plan Contract (P21)

The "CURRENT WORKFLOW" section in D1 §12.1 becomes a formal **Plan
Contract** surface with the following anatomy:

```
CURRENT PLAN · @47
1. Generate 5 candidates                ✓  completed 12:14
2. Validate on 30-d walk-forward        ✓  completed 12:22
3. Optimize top 3 → worker-02           ▸  running · ETA 3 min
4. Certify against FTMO rules           ○  queued
5. Route to Portfolio + Approvals       ⏸  awaiting operator (HITL gate)
```

Every step shows:
- state icon (✓ / ▸ / ○ / ⏸ / ⨯)
- Division-voice label
- outcome or ETA
- when in `⏸` state (HITL gate): explicit `→ open approval` link (P22)

### 6.2 HITL gate as in-plan node (P22)

`⏸` steps are approvals *inside* the plan. Their card in Approval Center
carries an `open in Master Bot plan` link — the two surfaces cross-link.

### 6.3 Worker state-history micro-line (P23)

Under each worker card's current-state chip:

```
┌────────────────────────────┐
│  research · worker-01      │
│  ● running                 │
│  idle → running · 3.4 min  │  ← NEW: state history micro-line
│                            │
│  candidate #47             │
│  ...                       │
└────────────────────────────┘
```

Shows the last state transition + duration. Advanced Lens expands to full
transition history (last 10 states).

### 6.4 Workforce Org Chart interactions

- Every worker card is pinnable (§7.12).
- Every worker card links to Lineage Graph (§10.2) filtered to that
  worker's produced artefacts.
- Hand-off animations use §6.2 slow tier (320 ms).

---

## 7. D5 (pending) — deltas to bake in

### 7.1 G3 Knowledge Graph implements §10.2 Lineage Graph mode

The G3 signature graphic (Knowledge Graph) shares its anatomy and
interactions with §10.2 (Lineage Graph mode). One implementation, two
uses.

### 7.2 Pinned Preview applies to G2, G3, G5, G6

Every applicable signature graphic exposes a `📌` control on hover.

### 7.3 Chart tiles across G-series follow §7.11.2

Every graphic that is a chart follows §7.11.2 anatomy — trailing high/low,
time-window chip, drill-through, permalink.

---

## 8. D6 (pending) — deltas to bake in

### 8.1 Copilot trace-as-UI (P24)

Under Advanced Lens, Copilot answers expose an optional trace:

```
COPILOT ANSWER
Research Division retrieved 6 arxiv papers on regime detection.

trace ▾
├─ retrieval (0.7 s) — arxiv corpus, k=6
├─ ranking (0.3 s) — trust-tier weighted
├─ synthesis (1.1 s) — GPT-5.2 with 4 citations
└─ evidence chips (4 references) →
```

Trace expands inline; each step is clickable to see its detail. Never on
Layer 1 by default.

### 8.2 Facet grammar (§11.6) codified as mode-agnostic

D6 §"Cross-mode consistency" adds: `<FacetBar>` is shared across
Executive · Operations · Research · Developer modes.

### 8.3 Per-mode default preset for time-window chip

- Executive: `last 24 h` (Briefing horizon)
- Operations: `live ▸`
- Research: `last 7 d`
- Developer: `live ▸`

---

## 9. D7 (pending) — deltas to bake in

Add authored states for:

### 9.1 Lineage Graph mode empty

```
[ icon · git-fork ]

This artefact is a root generation. No ancestors recorded.

→ view generation evidence   ·   close graph
```

### 9.2 Lineage Graph replay-empty

```
[ icon · rewind ]

No lineage existed at the selected time.
Try widening the time window.

→ expand window   ·   return to live
```

### 9.3 Pinned Preview empty

```
[ icon · pin ]

Nothing pinned yet.
Pin any artefact from the timeline, explorer, or approvals to compare.

→ open Strategy Explorer
```

### 9.4 Chart drill-through empty

```
[ icon · filter-x ]

No rows in this slice of the chart.
Try widening the time window.

→ expand window   ·   close drawer
```

---

## 10. D8 (pending) — deltas to bake in

### 10.1 Sprint 1 scope updates

Sprint 1 must ship:

1. **Widget trichotomy primitives** (§7.11 metric-block / chart-tile /
   table-tile) — highest-leverage Sprint 1 delta; unblocks Mission
   Control tiles.
2. **`<FacetBar>` shared component** (§11.6) — used across Timeline
   (D2 §8), Approvals (D3 §4), and Mission Control tile filters.
3. **Time-window chip** (§7.13) — reusable control.
4. **Interaction latency budget enforcement** (§6.3) — optimistic UI
   on filter apply, row select, approve action.
5. **Chart tile anatomy** (§7.11.2 + §14.5–14.8) — trailing high/low,
   drill-through, permalink, export.
6. **Attention panel severity ordering** (§8.8) — implementable in Sprint 1
   trivially.

### 10.2 Sprint 1 non-goals (deferred beyond Sprint 1)

- Lineage Graph mode (§10.2) — Sprint 2.
- Pinned Preview (§7.12) — Sprint 2.
- Copilot trace-as-UI (§8 above) — Sprint 3.
- Master Bot Plan Contract (§6 above) — Sprint 2 (with D4 spec).

### 10.3 Acceptance-criteria additions

D8 acceptance-criteria per component (D1 §17) must add:

- ✅ Widget trichotomy compliance (§7.11)
- ✅ Uses `<FacetBar>` if filterable (§11.6)
- ✅ Uses `<TimeWindowChip>` if time-scoped (§7.13)
- ✅ Meets interaction-latency budget (§6.3)
- ✅ Drill-through capable if data-bearing (§14.6)
- ✅ Permalink-shareable (§14.7)
- ✅ Renders in optimistic-UI mode when applicable (§6.3)

---

## 11. Inviolate rules — untouched

The following rules from Bible v1.0 + v2.0 are **not modified** by any
delta in this document:

- Six operator questions (§2).
- Five-layer information architecture (§3).
- Eight-module navigation (§4.2).
- Six-signal colour ceiling (§5.1).
- Motion budget durations — 120 / 200 / 320 ms (§6.1).
- 4-pt spacing grid (§5.3).
- Danger ribbon reserved for Critical only (§14.2).
- Copilot never acts, only observes (v2.0 §4).
- Emojis, purple gradients, pure white backgrounds — remain forbidden.
- Terminology dictionary (§19.4).
- Backend Feature Freeze (all deltas above are pure frontend).

---

## 12. Approval checklist

For operator approval to fold these into Bible v2.1 + the pending
D-documents:

- [ ] §1.1 — §2b Bottom-up / top-down IA rule
- [ ] §1.2 — §4.4 Line-length rule
- [ ] §1.3 — §4.5 Scale-ratio annotation
- [ ] §1.4 — §5.1 Concept-C 50 % whitespace
- [ ] §1.5 — §6.3 Interaction latency budget
- [ ] §1.6 — §7.11 Widget trichotomy (largest delta)
- [ ] §1.7 — §7.12 Pinned Preview
- [ ] §1.8 — §7.13 Time-window chip
- [ ] §1.9 — §8.7 Salience heuristic
- [ ] §1.10 — §8.8 Attention panel severity ordering
- [ ] §1.11 — §10.2 Lineage Graph mode (second-largest delta)
- [ ] §1.12 — §11.6 Facet grammar
- [ ] §1.13 — §14.5–14.8 Chart standards (four additions)
- [ ] §1.14 — §19.6 Everywhere-Actionable rule
- [ ] §2 — D1 annotations
- [ ] §5 — D3 in-place patch (downstream chip interactive)
- [ ] §6–§10 — D4/D5/D6/D7/D8 pending — bake in at authoring
- [ ] §11 — inviolate rules acknowledged unchanged

**On approval:**
1. Bible v1.0 becomes v2.1 with the §1 additions folded in.
2. D1 receives the §2 annotations.
3. D3 receives the §5 in-place patch.
4. D4 begins authoring with §6 deltas pre-baked.
5. The Design Inspiration Study becomes a permanent research reference.
6. Bible v2.1 delta document supersedes v2.0 delta (v2.0 additions carry
   forward untouched).

---

*End of Bible v2.1 Deltas.*
*Awaiting operator approval before Bible v2.1 fold-in and D4 authoring.*

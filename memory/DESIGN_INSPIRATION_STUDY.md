# Design Inspiration Study

> Permanent research reference. Six products studied as **inspiration only** —
> for interaction patterns, information architecture, workflow design and
> visual quality. No layouts copied. No branding borrowed. Strategy Factory
> remains recognizably itself.
>
> **Companion document:** `BIBLE_V2.1_DELTAS.md` — the implementation-ready
> deltas extracted from this study.
>
> **Governed by:** `FRONTEND_DESIGN_BIBLE.md` (v1.0) · `FRONTEND_DESIGN_BIBLE_V2_DELTA.md`
> (v2.0) · `D0_VISUAL_LANGUAGE_EXPLORATION.md` · `D1_MISSION_CONTROL_VISUAL_BENCHMARK.md`
> · `D2_AI_ACTIVITY_TIMELINE.md` · `D2_ADDENDUM_STORYTELLING_STANDARD.md` ·
> `D3_APPROVAL_CENTER.md`.
>
> **Prepared:** 2026-07-20 · Research window Jan 2025 – Feb 2026.

---

## 0. Guardrails & methodology

### 0.1 Guardrails (the "inspiration-only" contract)

1. **We study; we do not clone.** No layout is lifted. No colour is copied.
   No component is imitated one-for-one. If a screenshot of Strategy Factory
   could be confused with a screenshot of any studied product, the study has
   failed.
2. **Our Bible is the source of truth.** Concept D (50 % Mission Control /
   35 % AI Intelligence / 15 % Executive Luxury) governs every visual choice.
   The six operator questions, five-layer IA and six-signal ceiling are
   inviolate. This study can enrich them; it cannot replace them.
3. **Extractions must survive translation.** A pattern qualifies only if it
   strengthens Strategy Factory *in Strategy Factory's voice*. Anything that
   only works in the source product's brand identity is rejected.
4. **Nothing is adopted "because it's cool."** Every adoption is justified
   against one of the six operator questions or one of the three D1 principles
   (Invisible Luxury · Everything Connected · Progressive Disclosure).

### 0.2 Extraction lens (13 categories, per operator brief)

For each source we look through the same 13 lenses:

`widget composition` · `evidence-driven dashboards` · `drill-down interactions` ·
`relationship navigation` · `modular layouts` · `AI-first workflows` ·
`executive briefings` · `mission-control philosophy` · `premium typography` ·
`whitespace` · `information hierarchy` · `contextual actions` ·
`keyboard-first workflows`.

### 0.3 Scoring rubric

Every pattern is scored:

- **ADOPT** — genuine gap in our design; folds in without breaking identity.
- **ADAPT** — good idea, needs translation before it fits our voice.
- **REJECT** — either already covered by our Bible, or dilutes our identity.
- **DEFER** — valuable but out of scope for Sprint 1; moves to §7 backlog.

### 0.4 What this study explicitly is NOT

- Not a redesign proposal.
- Not a competitive analysis.
- Not a checklist of features to build.
- Not a licence to introduce a seventh signal colour, a new font family, or a
  parallel navigation vocabulary.

---

## 1. Product deep-dives

### 1.1 Mission Control (NASA MCC · SpaceX Dragon flight ops · CERN control rooms)

**Reference material (2025 window):** ESA/DLR SpaceOps-2025 paper on Columbus
STRATOS console UX, NASA Human-Factors publications on high-stakes interfaces,
independent recreations of Crew Dragon cockpit UI, published human-factors
literature on multi-screen decoupled telemetry pipelines.

**Philosophy in one sentence.** *The operator is a monitor, not a pilot. The
console reveals state; humans intervene by exception.* This is exactly the
posture Strategy Factory's operator adopts toward the autonomous AI workforce.

**Patterns extracted:**

1. **Bottom-up monitoring, top-down troubleshooting.** Operators scan
   subsystem health *upward* from atomic telemetry to overall status; when
   an anomaly appears, they drill *downward* from status into root evidence.
   Two directions, two mental modes, one layout. — *Documented in the
   Columbus STRATOS console paper.*

2. **Salient telemetry up-front; secondary state hidden.** The console
   dedicates screen real estate proportional to *decision consequence*, not
   to information volume. A pressure gauge for the crew module dominates
   the screen; internal firmware version numbers live behind a keystroke.

3. **Dark, high-contrast, colour-coded.** Long shifts demand dark surfaces
   and saturated but *disciplined* colour: red / yellow / green mean
   exactly one thing, always. No decorative colour anywhere.

4. **Multi-screen decoupled layout.** Real MCCs run *N* dedicated screens
   (SATMON telemetry, MCS commands, timelines, procedures, voice comms) —
   one physical surface per cognitive activity. Not multi-monitor for
   density; multi-monitor for *separation of concerns*.

5. **Minimalist critical controls.** The Dragon cockpit famously replaced
   thousands of switches with a handful of glass-panel buttons for the
   truly critical operations (deorbit, depress, manual). *Fewer, larger,
   deliberately hard-to-hit* — the opposite of consumer UI density.

6. **Bottom-of-loop escalation.** Any subsystem can raise its severity;
   the console surfaces the highest active severity, not the most recent
   event. This inverts the typical notification-feed model.

7. **Procedure-linked telemetry.** Every alert links to the *procedure*
   that resolves it. Alert without action-guidance is treated as a design
   defect.

**What to steal:**
- **Bottom-up monitoring, top-down troubleshooting** as a stated IA rule.
- **Severity-ranked attention** (not chronological) for the Attention panel.
- **Procedure-linked alerts** — every Critical must carry a `→ action` verb.
- **Salience proportional to decision consequence** as a layout heuristic.

**What NOT to steal:** multi-monitor separation (we're a single-viewport
product); tactile hardware minimalism (we're software); anything that
requires certified operator training.

**Verdict:** two ADOPT items (bottom-up/top-down rule; salience heuristic).
Two ADAPT items (severity ranking; procedure-linked alerts). One DEFER
(multi-viewport briefing wall — noted for future).

---

### 1.2 Linear Dashboards (v-2025 launch · July 2025 changelog)

**Reference material (2025 window):** Linear's July-2025 Dashboards
changelog, Linear Docs (`linear.app/docs/dashboards`), Linear's own
"Dashboards Best Practices" page (`linear.app/now/dashboards-best-practices`),
Linear Insights product page.

**Philosophy in one sentence.** *A dashboard is a composed view over Insights;
Insights are the primary object, dashboards are the second-order composition.*

**Patterns extracted:**

1. **Widget trichotomy.** Every tile is exactly one of three primitives:
   **single-number metric block**, **chart**, or **table**. That's it. No
   generic "widget" abstraction — three shapes, each with its own affordances.

2. **Purpose-per-dashboard discipline.** Linear's best-practices explicitly
   distinguish **Strategy dashboards** (few, long-term trend charts for
   leadership) from **Operations dashboards** (wide range of tactical
   metrics for on-shift work). Two dashboards, two typographies, two
   densities — same components underneath.

3. **Median workspace has 2 dashboards.** Deliberate scarcity — Linear
   actively discourages proliferation. The best-practices doc even quotes
   the median.

4. **Audience-tuned density.** Dense for *daily* consumers; annotated for
   *occasional* consumers. Same data, two treatments, chosen by author.

5. **Trailing highs and lows.** Charts show *context* — "highest value in
   trailing 90 d", "lowest value in trailing 7 d" — as annotations, not
   as separate tiles. A number in isolation is treated as a design defect.

6. **Drill-through as first-class.** Every tile opens the underlying
   Insights query; every Insights query opens the underlying issue list;
   every issue is directly actionable. Zero dead-end tiles.

7. **CSV + shareable link.** Every Insight is exportable + linkable —
   evidence *leaves* the app. This is a key institutional-memory pattern
   for regulated / audit-heavy workflows.

**What to steal:**
- **Widget trichotomy** — codify metric-block / chart-tile / table-tile as
  Strategy Factory's dashboard primitives (we currently have metric card
  and pipeline bar but no explicit vocabulary for the *dashboard* layer).
- **Strategy vs Operations dashboard split** — maps perfectly to
  Executive-persona Briefing vs Operations-persona Mission Control.
- **Trailing highs/lows** as chart-annotation standard (our D1 §14 is silent
  on this).
- **Drill-through mandate** — every tile → underlying evidence list.
- **Export / permalink** on every chart (evidence portability principle).

**What NOT to steal:** Linear's rounded soft borders (our Concept-A surfaces
lean sharper); Linear's warm brand colour (would require a new hue —
forbidden); Linear's tone of copy (marketing-adjacent; we are terser).

**Verdict:** five ADOPT items — this is the highest-density source.

---

### 1.3 Linear Insights (product-embedded analytics · 2024–2025)

**Reference material (2025 window):** Linear Insights product page,
Reddit community threads on evidence workflows, Linear blog posts on
information density.

**Philosophy in one sentence.** *Analytics is not a separate destination —
it's a lens over the underlying objects, always one keystroke from the work.*

**Patterns extracted:**

1. **Every query returns three views: chart · table · list.** The same data
   is *readable* as a shape (chart), a matrix (table), or an actionable
   feed (list). The operator chooses register.

2. **Slice-by is universal.** Any dimension can be a facet — assignee,
   status, priority, project, cycle. This is a *facet grammar*, not a
   collection of pre-baked reports.

3. **Time window is a first-class control.** Every insight carries a time
   window as a persistent chip (`last 7 d`, `last quarter`, `trailing 90 d`).
   Time is treated as a query dimension, not a page parameter.

4. **Result is actionable inline.** From an Insights table row, you assign
   the issue, change the status, comment — without navigating to the issue
   page. The report *is* the workspace.

5. **Sub-100 ms interaction budget.** Insights re-renders on filter change
   feel instant. Underneath: optimistic UI + client-side aggregation
   where possible.

6. **Share via link.** A URL fully encodes the query — the same URL renders
   the same insight for another operator. Evidence permalinks.

**What to steal:**
- **Three-view universality** — every dashboard tile can toggle
  chart ↔ table ↔ list (progressive disclosure of the same data).
- **Facet grammar** — reuse the same filter model across Mission Control,
  Approvals, Timeline, Strategy Explorer (we already do this partially in
  D2 §8 / D3 §4 — codify it).
- **Time-window chip** as a persistent control on any evidence surface
  (aligns with D2 §6.3 scrub reservation).
- **Actionable inline** — Strategy Explorer rows already support this;
  Approvals inline already supports this; extend to Timeline rows for
  Advanced Lens (`assign`, `route`, `defer` from a timeline row).
- **Permalink** — every evidence view is bookmarkable.

**What NOT to steal:** Linear's flat colour scheme (our signal ceiling is
tighter); Linear's cycle/velocity vocabulary (irrelevant to trading);
Linear's assignee-centric IA (we are AI-workforce-centric).

**Verdict:** four ADOPT items, one already-covered.

---

### 1.4 Palantir Foundry Quiver (analysis workspace · updated 2025)

**Reference material (2025 window):** Palantir Foundry official docs on
Quiver (`palantir.com/docs/foundry/quiver`), Quiver analysis-graph docs,
community posts on lineage exposure, YouTube walkthroughs.

**Philosophy in one sentence.** *Every analytic step is a first-class node
in a dependency graph; the workspace itself is your evidence trail.*

**Patterns extracted:**

1. **Dual-view toggle: Canvas ↔ Graph.** The same analysis renders as a
   *linear canvas* (widgets in reading order) or as a *dependency graph*
   (nodes and edges showing what feeds what). Toggle in the upper-right;
   both views are always available.

2. **Analysis lineage as evidence.** Every widget the operator adds
   auto-registers as a node in the graph. The graph *is* the audit trail
   — no separate export needed.

3. **Dependency view (subgraph focus).** Right-click any node → *"View
   dependencies"* isolates that node plus its ancestors and descendants
   only. Rest of graph fades. Perfect for auditing one artefact.

4. **Pinned previews.** Any node's output can be pinned as a floating
   preview; multiple pins let operators *compare* outputs side-by-side.

5. **Layout-nodes command.** A single keystroke re-lays-out the graph
   automatically when it gets messy — the operator never manually arranges.

6. **Analysis Contents sidebar.** Persistent left-side navigator lists every
   object / chart / transform in the analysis; click to focus.

7. **Ontology-first search.** Add a data object by *type name*; Quiver
   pre-populates the analysis from the ontology graph. Type-first, not
   filename-first.

8. **Two lineage scales.** Quiver has *analysis-level* lineage (within one
   Quiver); Foundry has *workflow-level* lineage (across pipelines). Two
   granularities, one mental model.

**What to steal:**
- **Dual-view toggle (linear ↔ graph)** — powerful lineage pattern. Our
  Lineage bar (D1 §10) currently only shows *one hop up + one hop down*.
  A "Graph" expansion would show the full ancestry / descendant tree of an
  artefact — same button, second view.
- **Dependency view / subgraph focus** — an operator viewing an approval
  should be able to click *"only show me what this affects"* to see the
  subgraph downstream. This is the *"affects: 12 strategies in Portfolio"*
  chip in our D3 §2 becoming interactive.
- **Pinned previews for comparison** — Strategy comparison and Portfolio
  candidate review both benefit from a *"pin this / pin that / compare"*
  affordance. Currently we spec `Strategies > Compare` as a tab; the
  pin-anywhere pattern lets operators build comparisons from any surface.
- **Analysis Contents sidebar** — a lightweight version could serve as
  the *"what's on this dashboard?"* navigator inside Mission Control when
  Advanced Lens is on.

**What NOT to steal:** Palantir's inherent visual density (screens filled
with tabular data + graphs simultaneously — overwhelming for our operator);
Foundry's ontology-first search UX (we don't have an operator-facing
ontology surface); Palantir's window-in-window overload (v1.0 §1 anti-pattern).

**Verdict:** three ADOPT items, one ADAPT (Pinned previews for our
Approval + Strategy comparison workflows).

---

### 1.5 Jorv AI (name unresolved · 2025 AI-agent orchestration heuristics)

**Reference material (2025 window):** Public sources on the exact name
"Jorv AI" are inconclusive (spelling likely off — could be Jove / Jovoc /
Jorve). Rather than fabricate, this section reads the *class* of product
the operator likely intended — modern **AI-agent orchestration platforms**
(LangGraph UIs, Temporal Web, CrewAI Studio, AutoGen Studio, Zylos, various
2025 orchestration frontends).

**Philosophy in one sentence.** *Autonomous agents are legible when their
plans, intermediate states and human-approval gates are surfaced as
first-class artefacts.*

**Patterns extracted (from the class, not from a single product):**

1. **Explicit plan surface.** Before running, the agent's *plan* (sequence
   of intended steps) is shown as an accepted contract. The operator can
   inspect *what will happen* before it happens.

2. **Human-in-the-loop gates as first-class objects.** Approval steps live
   *inside* the plan, not as external notifications. The plan literally
   pauses at the gate and shows *why* it paused.

3. **State machine visibility.** Every agent has a visible state
   (`planning · running · waiting · completed · errored`) and the surface
   *shows the state*, not just the last log line.

4. **Deterministic replay.** Every run is checkpointed; runs can be
   replayed exactly. This is the pattern our Bible already reserves as
   "Factory Replay."

5. **Trace as UI.** Traditional logging becomes an *interactive trace*
   with expandable steps, per-step evidence, per-step cost. The 2025
   pattern in LangSmith / LangGraph Studio.

6. **Cost + latency chips.** Each agent step carries `token cost` and
   `latency` chips inline — first-class citizens, not developer-only.

7. **Sub-agent handoffs shown as edges.** Multi-agent systems show
   agent-to-agent handoffs as visible transitions with a hand-off payload.

**What to steal:**
- **Explicit plan surface for Master Bot.** Our D1 §12.1 already shows
  "CURRENT WORKFLOW" as a checklist — codify that as *the plan contract*,
  editable-by-Master-Bot, observable-by-operator, with each step showing
  its *pre-flight expectations*.
- **HITL gate as an in-plan node.** When Master Bot's workflow reaches an
  approval step, the plan surface should show *"→ waiting on operator"*
  as its own step. Our Approval Center already receives the request;
  Master Bot dashboard should also *show that it is paused*.
- **State-machine visibility for every worker.** Each worker card in the
  Workforce Org Chart already has a state chip; add the *state history
  micro-line* (last N transitions) below the current state.
- **Trace-as-UI for the Copilot.** When Copilot answers, its trace
  (retrieval → reasoning → citation) should be optionally expandable —
  respects Copilot Never Invents rule.

**What NOT to steal:** DAG drag-and-drop workflow builders (operators
don't build workflows — Master Bot does); token-cost chips *by default* on
Layer 1 (dilutes the storytelling voice — Advanced Lens only); the
verbose "trace" aesthetic of LangSmith (looks developer-y).

**Verdict:** four ADAPT items (all require translation to Strategy Factory's
Division-voice / no-jargon-on-L1 standard). Zero direct ADOPTs.

---

### 1.6 UI/UX Pro Max (design-system-generator skill · 2025)

**Reference material (2025 window):** UI/UX Pro Max product page,
associated design-guideline sources cited (typography-master.com,
typography-2026 references), industry-standard 2025 typography rules
propagated across designer education.

**Philosophy in one sentence.** *Craftsmanship is the sum of many small
constraints — line-length, line-height, whitespace multipliers, contrast
ratios — applied with restraint.*

Note: UI/UX Pro Max is itself a generator, not a design; the *value* is in
the constraints it encodes.

**Patterns extracted:**

1. **60–75 character line length.** Body text is capped at 60–75 characters
   per line. Longer lines fatigue readers.

2. **1.5–1.6 line-height for body; 1.05–1.2 for headlines.** A tight rule,
   never violated.

3. **Scale ratios: 1.2 (Minor Third) or 1.25 (Major Third).** Type scales
   follow *musical intervals* — a discipline our current scale approximates
   but does not codify.

4. **"Add 50 % more whitespace" heuristic.** If a designer thinks the
   whitespace is *enough*, it isn't. Add half again.

5. **8-pt grid alignment.** Everything snaps to 8. (We already use a
   4-pt grid; this is our sanctioned tighter choice for operator density.)

6. **Body 16–18 px on desktop; 14–16 px on mobile.** A specific reading
   floor.

7. **Accessibility as constraint.** Contrast ratio checks (WCAG 2.2 AA
   minimum), ARIA labelling, touch-target minimums — baked into the
   generator's rules.

8. **`clamp(min, preferred, max)` for hero typography.** Modern responsive
   type without media queries.

**What to steal:**
- **60–75 char line-length rule** — our D1 §4 is silent on line length.
  Add it explicitly.
- **`clamp()` for hero metrics** on the Daily Briefing surface (C-variant).
  Our D1 §7.2 spec is fixed-px; a `clamp()` for the Briefing hero adds
  responsive luxury without breaking scale.
- **50 %-more-whitespace heuristic** for Concept-C surfaces specifically —
  align with `--space-7` (64 px) which we've already reserved for Briefing.
- **Explicit scale-ratio declaration** — our scale approximates ~1.15
  (11→13→15→17→18→22→28→32→40→48); we should *state* the ratio in D1 §4
  so future additions respect it.

**What NOT to steal:** the *generator* itself (we have hand-crafted
choices already — Berkeley Mono, Neue Haas Grotesk, GT Sectra — not
Google Fonts pairings); the *marketing tone* of the source (we are
terser than any templated system).

**Verdict:** four ADOPT items — all are typographic craft, all fold into
D1 §4 as clarifications rather than reversals.

---

## 2. Cross-reference matrix vs. our Bible & D-series

Each row: *does the pattern already exist in our specs?* If yes, cite where.
If no, propose an addition.

| # | Pattern | Source | Already covered? | Gap | Verdict |
|---|---|---|---|---|---|
| P01 | Bottom-up monitoring / top-down troubleshooting | Mission Control | Partially (implied by 5-layer IA §3) | Not stated as a rule | **ADOPT** — new §2b principle |
| P02 | Severity-ranked (not chronological) attention feed | Mission Control | Partially (Bible §14.1 tiers) | Attention panel ordering unspecified | **ADOPT** — clarify D1 §8.1 |
| P03 | Every Critical carries a procedure/action | Mission Control | Yes (Bible §14.2 danger-ribbon copy pattern) | — | ✅ already covered |
| P04 | Salience ∝ decision consequence | Mission Control | Partially (Bible §2 six questions) | Not codified as a layout heuristic | **ADOPT** — add to D1 §8 layout rules |
| P05 | Widget trichotomy (metric / chart / table) | Linear Dashboards | Partially (Bible §7 has cards; charts scattered) | No canonical dashboard-tile vocabulary | **ADOPT** — new §7.11 in Bible v2.1 |
| P06 | Strategy vs Operations dashboard split | Linear Dashboards | Yes (Bible §12 persona modes) | Mapping to Briefing vs Mission Control implicit | **ADOPT** — codify mapping in D1 §12 |
| P07 | Trailing highs / lows as chart annotation | Linear Dashboards | No | Charts show current value only | **ADOPT** — new §14.1 rule in Bible |
| P08 | Drill-through mandate on every tile | Linear Dashboards | Yes (Bible §7.2 "every metric card links to evidence") | Not extended to charts/tables | **ADOPT** — extend §7.2 to §7.11 (trichotomy) |
| P09 | Export / permalink on every chart | Linear Dashboards | Partially (Bible §16.2 print digest) | Not extended to charts | **ADOPT** — add to §14 chart standards |
| P10 | Three-view universality (chart ↔ table ↔ list) | Linear Insights | No | Fixed presentation per widget | **ADAPT** — Advanced-Lens toggle |
| P11 | Facet grammar (shared filter model across surfaces) | Linear Insights | Partially (D2 §8, D3 §4 share model) | Not stated as an architectural principle | **ADOPT** — new §11 in Bible v2.1 |
| P12 | Time-window chip as persistent control | Linear Insights | Yes (D2 §6.3 scrub) | Not extended beyond Timeline | **ADAPT** — extend to Approvals + charts |
| P13 | Actionable inline (from feed row) | Linear Insights | Partially (D3 Timeline expansion) | Not universal | **ADAPT** — codify as *Everywhere-Actionable* rule |
| P14 | Sub-100 ms interaction budget + optimistic UI | Linear / Linear Insights | No | No stated interaction-latency budget | **ADOPT** — new §6.3 in D1 |
| P15 | Permalink on every evidence view | Linear Insights | Partially (URL scheme in §4.3) | Not enforced for evidence drawers | **ADOPT** — clarify §4.3 |
| P16 | Dual-view toggle (linear ↔ graph) for lineage | Palantir Quiver | No | Lineage bar shows 1-hop only (D1 §10) | **ADOPT** — new §10.2 "Graph mode" |
| P17 | Subgraph focus (ancestors + descendants only) | Palantir Quiver | No | — | **ADOPT** — inside §10.2 |
| P18 | Pinned previews for comparison | Palantir Quiver | Partially (Strategies > Compare tab) | No pin-anywhere affordance | **ADAPT** — new §7.12 primitive |
| P19 | Auto-layout ("layout nodes") command | Palantir Quiver | N/A (we don't have free-form graphs) | — | REJECT — not applicable |
| P20 | Analysis Contents sidebar (dashboard navigator) | Palantir Quiver | No | — | **DEFER** — future §7.13 primitive |
| P21 | Explicit plan surface for Master Bot | AI-Orchestration class | Partially (D1 §12.1 "CURRENT WORKFLOW") | Not codified as a plan contract | **ADAPT** — codify in D4 spec |
| P22 | HITL gate as in-plan node | AI-Orchestration class | Partially (D3 approvals) | Not shown *inside* Master Bot dashboard | **ADAPT** — D4 spec addition |
| P23 | State-machine history micro-line | AI-Orchestration class | No | Worker card shows current state only | **ADOPT** — D4 anatomy addition |
| P24 | Trace-as-UI for Copilot answers | AI-Orchestration class | Partially (Bible v2.0 §4 Copilot Never Invents) | Expandable trace not spec'd | **ADAPT** — D6/D8 Copilot spec |
| P25 | 60–75 char line-length rule | UI/UX Pro Max | No | — | **ADOPT** — add to D1 §4 |
| P26 | Explicit scale-ratio declaration | UI/UX Pro Max | Partially (D1 §4.2 lists sizes) | Ratio unstated | **ADOPT** — annotate D1 §4.2 |
| P27 | 50 %-more-whitespace on Concept-C | UI/UX Pro Max | Partially (`--space-7` reserved) | Not codified as a rule | **ADOPT** — add to D1 §5.1 |
| P28 | `clamp()` for hero metrics on Briefing | UI/UX Pro Max | No | Fixed-px only | **ADOPT** — extend D1 §7.2 C-variant |
| P29 | 8-pt grid | UI/UX Pro Max | REJECT (we chose 4-pt) | — | REJECT — our density needs finer grid |
| P30 | Cost + latency chips per agent step | AI-Orchestration | Advanced-Lens only | — | ✅ already covered (D2 §3.2 Advanced) |

**Totals:** 15 ADOPT · 7 ADAPT · 5 already-covered · 2 REJECT · 1 DEFER.

---

## 3. Recommended deltas (Adopt / Adapt only)

Full implementation-ready deltas are captured in the companion document
`BIBLE_V2.1_DELTAS.md`. This section summarises the *shape* of the deltas so
the reader of this study understands the intent.

### 3.1 Bible v1.0 additions (v2.1 folded into v1.0 numbering)

| Delta | Location | Purpose |
|---|---|---|
| **§2b — Bottom-up / top-down IA rule** | new subsection after §2 | Codifies P01 |
| **§4.4 — Line-length rule (60–75 char)** | append to §4 | P25 |
| **§4.5 — Type scale ratio annotation** | append to §4 | P26 |
| **§5.1 — Concept-C 50%-whitespace heuristic** | append to §5.1 | P27 |
| **§6.3 — Interaction latency budget** | new subsection under §6 | P14 |
| **§7.11 — Widget trichotomy** (metric-block / chart-tile / table-tile) | new §7 primitive | P05, P08 |
| **§7.12 — Pinned Preview** | new §7 primitive | P18 |
| **§7.13 — Time-window chip** as reusable control | new §7 primitive | P12 |
| **§8.7 — Salience heuristic** | append to §8 | P04 |
| **§8.8 — Attention panel severity ordering** | append to §8 | P02 |
| **§10.2 — Lineage Graph mode** (dual-view toggle) | new §10 subsection | P16, P17 |
| **§11.6 — Facet grammar principle** | append to §11 | P11 |
| **§14 — Trailing highs/lows chart annotation** | append to §14 | P07 |
| **§14 — Chart drill-through + permalink + export** | append to §14 | P09, P15 |
| **§14 — Three-view toggle (chart ↔ table ↔ list)** | append to §14 (Advanced) | P10 |
| **§19.6 — *Everywhere-Actionable* rule** | append to §19 | P13 |

### 3.2 D1 additions

Small annotations to D1 §4 (scale ratio · line length) and D1 §7.2 (C-variant
gets `clamp()`). No structural rewrites.

### 3.3 D3 — genuine gap check

D3 as drafted already:
- Uses Division voice ✅
- Shows lineage (upstream/downstream) ✅
- Has all 4 canonical actions ✅
- Renders in header drawer + module + timeline expansion ✅ (dual-path invariant)

**One improvement worth patching in-place:** the *"downstream"* summary
currently reads *"Will enter portfolio candidate pool · risk 0.4 % max"*.
Under P16/P17 (Palantir dual-view), we can make *"affects: 12 strategies
in Portfolio"* into a **click-to-expand subgraph** — the operator sees
exactly which 12 strategies without leaving the card.

*Recommendation:* patch D3 §2.1 field table to note that "downstream" chip
opens Lineage Graph mode focused on the approval's subject. Small,
non-structural edit. Detailed in `BIBLE_V2.1_DELTAS.md` §5.

### 3.4 D4 (pending) — deltas to bake in from day one

D4 should incorporate:
- **Master Bot Plan Contract** surface (P21)
- **HITL gates visible as in-plan nodes** (P22)
- **Worker state-history micro-line** (P23)

D4 will be drafted after operator approval of this study, with these deltas
baked into the initial spec rather than patched later.

### 3.5 D5 (pending)

Signature graphic gallery already reserves the Lineage / Knowledge Graph
(G3). D5 will now explicitly incorporate the dual-view toggle (canvas ↔
graph) as G3's interaction pattern, and the Pinned Preview as a G3 + G5
interaction affordance.

### 3.6 D6 (pending) — Copilot trace-as-UI

D6 (Personalization modes) has a Copilot section. Add: *"When Advanced Lens
is on, Copilot answers expose an optional trace (retrieval → reasoning →
citation) as an expandable panel below the answer."* — P24 codified.

---

## 4. Rejected patterns (documented so we do not re-litigate)

| # | Pattern | Source | Reason for rejection |
|---|---|---|---|
| R1 | Purple/violet gradients on white background | AI-generation defaults | Anti-pattern in Bible §1; kills our identity |
| R2 | Multi-monitor briefing wall | Mission Control | Not applicable to a single-viewport product (Sprint N reservation) |
| R3 | Rounded soft borders (Linear aesthetic) | Linear | Concept-A surfaces intentionally sharper; softness reserved for Concept-B (D1 §5.2) |
| R4 | 8-pt grid | UI/UX Pro Max | 4-pt grid chosen for operator-density; 8-pt too coarse |
| R5 | Google Fonts pairings (generator output) | UI/UX Pro Max | We have hand-crafted choices (Berkeley Mono / Neue Haas Grotesk / GT Sectra) |
| R6 | Auto-layout free-form graphs (Quiver "layout nodes") | Palantir | We don't have free-form user-authored graphs; not applicable |
| R7 | DAG drag-and-drop workflow builder | AI-orchestration class | Master Bot builds workflows; operator observes, never authors |
| R8 | Token-cost chip on Layer 1 by default | AI-orchestration class | Dilutes Division-voice storytelling (D2 Addendum §2); Advanced-Lens only |
| R9 | Cartoon agent avatars (Jorv/AutoGen-style) | AI-orchestration class | Undermines premium positioning (Bible §1 anti-pattern) |
| R10 | LangSmith-style verbose trace as primary view | AI-orchestration class | Feels developer-y; belongs to Layer 5 or Advanced Lens only |
| R11 | Bloomberg's window-in-window overload | Bloomberg | Bible §1 explicit anti-pattern |
| R12 | Consumer typographic hero (`clamp(48px, 8vw, 96px)`) | UI/UX Pro Max default | Too large for our Mission Control cinema; adopt `clamp()` at *our* scale |
| R13 | Linear's cycle/velocity terminology | Linear | Irrelevant to trading; would fragment our terminology dictionary (§19.4) |
| R14 | Linear's Enterprise-only dashboard framing | Linear | We have no plan tiers; every persona sees Dashboards fitting their role |
| R15 | Palantir's ontology-first search UI | Palantir | We have no operator-facing ontology; internal-only concept |

**Rule:** if any of R1–R15 is proposed in a future PR, cite this list in the
rejection comment.

---

## 5. Identity guardrail — the recognisability test

Even after every §3 delta is applied, a screenshot of Strategy Factory must
still be recognisably *Strategy Factory*, not Linear, not Palantir, not a
mission-control clone. This section codifies the test.

### 5.1 Five recognisability heuristics

A screenshot passes if it satisfies **all five**:

1. **Division-voice text present.** At least one sentence on the visible
   surface reads in the D2-Addendum voice (*"Research Division generated
   …"* / *"Master Bot requests …"*). Not *"issue"*, not *"ticket"*, not
   *"agent-01"*.

2. **Cool-shifted near-black surface.** `--surface-0` in the range
   `#05070a` – `#0d1218`. Never white. Never warm ivory except on
   Concept-C hero surfaces (Daily Briefing only).

3. **Six-signal ceiling respected.** No colour on the visible surface
   outside the six `--sig-*` tokens (plus the 8-hue chart palette in
   charts only). No purple gradient. No Linear-orange. No Palantir-cyan.

4. **Mono numeric visible.** At least one number renders in Berkeley Mono
   with `tabular-nums`. If the entire visible surface is sans-numeric,
   it's not our product.

5. **Lineage or evidence link present.** At least one visible artefact
   surfaces its evidence trail (chip · pipeline stage · lineage bar ·
   *→ view evidence* link). No dead-end numbers.

### 5.2 Anti-test — five things a screenshot must NOT show

1. Purple / violet gradient on white background.
2. A row of colourful "agent" avatars.
3. A drag-and-drop workflow canvas.
4. A LangSmith-style verbose JSON trace as the primary panel.
5. A "click here" button, a "seamless" adjective, or a "welcome back!"
   greeting.

### 5.3 What makes Strategy Factory unmistakable

Even sharing DNA with the six studied products, we retain a distinct
identity because we combine three things *no single competitor combines*:

1. **Autonomous-organisation storytelling** (D2 Addendum) — the platform
   speaks like a company, not a system.
2. **Persona-per-concept visual register** (D1 §2) — Executive is Concept-C,
   Operations is Concept-A, Research is Concept-B, Developer is
   Concept-A + diagnostics-lens. Four visual registers, one identity.
3. **Six-signal ceiling** — the disciplined refusal to add a seventh
   colour, applied globally.

A first-time visitor should feel *this is a control room for a company
that happens to be AI*. That framing is unique.

---

## 6. Impact on pending D-documents

### 6.1 D3 — Approval Center (already drafted · under review)

- **Structural rewrite:** NO.
- **In-place patch:** YES, one — the *"downstream"* field on the card
  should be interactive (opens Lineage Graph mode focused on the approval
  subject). Detailed in `BIBLE_V2.1_DELTAS.md` §5.

### 6.2 D4 — Master Bot & Workforce Org Chart (pending)

- Bake in from day one:
  - Master Bot **Plan Contract** surface (P21).
  - HITL gates rendered as in-plan nodes (P22).
  - Worker state-history micro-line (P23).
  - Adjacent to Timeline (D2), Approval Center (D3), and future Lineage
    Graph mode (P16/P17).

### 6.3 D5 — Signature Graphics gallery (pending)

- G3 (Knowledge Graph) now explicitly implements the Lineage Graph mode
  dual-view toggle (P16).
- Add a new signature *interaction* (not graphic): **Pinned Preview**
  (P18). Applies to G2 (Pipeline Ribbon), G3 (Knowledge Graph), G5
  (Execution Constellation), G6 (Portfolio Surface).

### 6.4 D6 — Personalization modes (pending)

- Add Copilot trace-as-UI section (P24).
- Codify facet grammar (P11) as a mode-agnostic architectural principle.

### 6.5 D7 — Empty / loading / error / dormant states (pending)

- Add empty states for Lineage Graph mode (subgraph empty, replay-empty).
- Add empty state for Pinned Preview (nothing pinned yet).

### 6.6 D8 — Sprint 1 execution plan (pending)

- Incorporate all Bible v2.1 deltas into acceptance criteria.
- Prioritise Widget Trichotomy (§7.11) as a Sprint 1 primitive — it
  unblocks Mission Control's dashboard tiles.

---

## 7. Future Opportunity Backlog (not for Sprint 1)

Valuable ideas surfaced by the study that we intentionally defer. Each
entry captures enough context for a future planning session.

### 7.1 O1 — Multi-viewport Briefing Wall

- **Description.** A read-only mode designed for a lobby TV or a
  multi-monitor briefing wall. Cinema-density Concept-C, one operator
  question per screen, auto-rotates over ~90 s.
- **Inspiration source.** Mission Control (Columbus STRATOS, NASA MCC
  layouts).
- **Expected user value.** External stakeholders / trading-floor visibility
  / physical-presence storytelling.
- **Complexity.** Medium — reuses existing components in Cinema posture;
  new: rotation controller, per-screen route contract.
- **Recommended roadmap phase.** Sprint 6 or later.
- **Reason for deferring.** No physical multi-monitor requirement in
  Sprint 1; premature.

### 7.2 O2 — Real-time WebSocket telemetry stream

- **Description.** Replace polling in AI Activity Timeline + Status Rail
  with WebSocket push. Sub-100 ms end-to-end latency for state changes.
- **Inspiration source.** Mission Control (CDP StudioAPI, modern SCADA);
  Linear (sub-100 ms interaction budget).
- **Expected user value.** Timeline feels *alive* rather than *polled*;
  approval count updates without page interaction.
- **Complexity.** High — backend transport change (violates Feature Freeze
  in current form); frontend re-architecture of the timeline adapter.
- **Recommended roadmap phase.** Post-Feature-Freeze (Phase E+).
- **Reason for deferring.** Backend Feature Freeze respected; frontend
  today uses polling and remains within budget.

### 7.3 O3 — Analysis Contents sidebar (dashboard navigator)

- **Description.** Persistent left-side navigator on complex dashboards
  showing every tile in the current view as a clickable index.
- **Inspiration source.** Palantir Quiver.
- **Expected user value.** Fast intra-dashboard navigation; discoverability
  for new operators.
- **Complexity.** Low.
- **Recommended roadmap phase.** Sprint 5.
- **Reason for deferring.** Sprint 1 has ≤ 6 tiles per surface; a
  navigator adds no value until we exceed ~10.

### 7.4 O4 — Chart anomaly annotation

- **Description.** Charts auto-annotate anomalies (spikes, drops, regime
  changes) with a subtle pin + hoverable Division-voice explanation
  ("Volatility spike on 2026-06-14 followed by EURUSD Breakout v3 promotion").
- **Inspiration source.** Linear Insights (trailing context); mission-control
  procedure-linked alerts.
- **Expected user value.** Charts become self-explanatory; the operator
  never asks *"what happened here?"*.
- **Complexity.** Medium — requires an anomaly-detection service.
- **Recommended roadmap phase.** Sprint 4.
- **Reason for deferring.** Anomaly detection is backend-adjacent; not in
  Sprint 1 scope.

### 7.5 O5 — Insight → Approval one-click

- **Description.** From any chart insight (e.g. *"execution slippage
  trended +12 % on Broker X"*), one-click **"Route to Approvals"** creates
  a Governance-tier recommendation with the insight embedded as evidence.
- **Inspiration source.** Linear Insights (share-as-link); Palantir Quiver
  (pinned previews as evidence).
- **Expected user value.** Operators can escalate insights without leaving
  the chart.
- **Complexity.** Medium.
- **Recommended roadmap phase.** Sprint 5.
- **Reason for deferring.** Approval Center v1 (Sprint 1) focuses on
  system-generated approvals; operator-authored comes later.

### 7.6 O6 — Copilot trace deep-explorer

- **Description.** A dedicated `/c/copilot/traces` L4 surface where every
  Copilot answer's trace can be revisited, expanded, and used to seed
  further questions.
- **Inspiration source.** LangSmith, LangGraph Studio.
- **Expected user value.** Advanced auditability for operators reviewing
  AI-narrated activity.
- **Complexity.** Medium.
- **Recommended roadmap phase.** Sprint 6.
- **Reason for deferring.** In-line expandable trace (P24) sufficient for
  Sprint 1.

### 7.7 O7 — Ontology-informed search across artefacts

- **Description.** ⌘K palette gains a *"by type"* mode where operators
  search *by artefact type* (`strategy`, `KB item`, `worker`, `approval`)
  before narrowing by term.
- **Inspiration source.** Palantir Foundry ontology-first search.
- **Expected user value.** Faster discoverability across a large factory.
- **Complexity.** Low – Medium.
- **Recommended roadmap phase.** Sprint 3.
- **Reason for deferring.** Current ⌘K palette (Bible §7.10) already
  groups by verb; typed-search is an evolution not a revolution.

### 7.8 O8 — Time-window chip becomes global scrubber

- **Description.** Elevate the D2 §6.3 scrub to a *shell-level* control
  affecting every surface simultaneously (Timeline, Approvals, Workforce
  Org Chart, Charts). This is Factory Replay's UX target.
- **Inspiration source.** Palantir Quiver (dependency-view time
  navigation); Linear Insights (time-window as query dimension).
- **Expected user value.** True "rewind the factory" — the flagship
  Factory Replay experience.
- **Complexity.** High.
- **Recommended roadmap phase.** Post-Sprint-5 (Factory Replay milestone).
- **Reason for deferring.** Bible §16 and D1 §16 already reserve
  architectural room; the interaction ships when Replay ships.

### 7.9 O9 — Comparative chart overlays via Pinned Preview

- **Description.** Pin two strategies, two brokers, two time windows and
  overlay them on a shared chart automatically. Extension of P18.
- **Inspiration source.** Palantir Quiver pinned previews; TradingView
  overlays.
- **Expected user value.** Direct side-by-side comparison for research.
- **Complexity.** Medium.
- **Recommended roadmap phase.** Sprint 4.
- **Reason for deferring.** Sprint 1 ships Pinned Preview as a *card
  primitive* only; overlay math comes later.

### 7.10 O10 — Executive Briefing auto-narration

- **Description.** Concept-C Daily Briefing auto-generates a 5-sentence
  narrative from the last 24 h of activity, written in Division voice and
  citing 3–5 evidence chips.
- **Inspiration source.** Mission Control status briefings; Copilot
  workflow narration (C3 in Bible v2.0 §4.2).
- **Expected user value.** Executive persona gets a *written* briefing to
  read, not a dashboard to interpret.
- **Complexity.** Medium — depends on Copilot capability.
- **Recommended roadmap phase.** Sprint 5 (after Copilot C3 tier ships).
- **Reason for deferring.** Copilot C3 (workflow narration) is scheduled
  for Sprint 4; Executive auto-narration is the immediate next step.

---

## 8. Summary

- Six sources studied through 13 lenses; 30 patterns enumerated; 22 have
  design consequences for Strategy Factory.
- **15 ADOPT** items fold into Bible v2.1 as small, non-structural additions.
- **7 ADAPT** items require translation to Strategy Factory's voice.
- **5** items are already covered by our current specs.
- **2 REJECT** items are documented so we do not re-litigate.
- **10 DEFER** items form the Future Opportunity Backlog (§7).
- **D3 needs one small in-place patch** (make *"downstream"* chip
  interactive). Otherwise no D-doc rewrites.
- **D4 through D8 bake in the deltas** as they are drafted.
- **Our identity remains recognisably Strategy Factory** — the five
  recognisability heuristics (§5.1) hold under every proposed delta.

---

*End of Design Inspiration Study.*
*Companion: `BIBLE_V2.1_DELTAS.md` for the implementation-ready deltas.*
*Awaiting operator review before proceeding to D4.*

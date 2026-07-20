# D5 — Signature Graphic Gallery (G2 – G8)

> Codifies the seven graphics that, together with G1 (Workforce Org Chart,
> D4), form Strategy Factory's visual signature. **The objective is
> recognisability, not complexity.** Any one of these graphics, seen in
> isolation on a screenshot, must be identifiable as Strategy Factory.
>
> Layered on **Bible v2.1** (`FRONTEND_DESIGN_BIBLE_V2_1.md`). Uses
> §7.11 widget trichotomy, §7.12 Pinned Preview, §7.13 time-window,
> §10.2 Lineage Graph mode, §11.6 facet grammar, §14.5–14.8 chart
> standards, and D2 Addendum Division voice throughout.
>
> Prepared 2026-07-20.

---

## 0. Design Principles Checklist (16 items — permanent quality gate)

Every design deliverable must confirm all items. D5 confirms:

- [x] **Invisible Luxury** — every graphic reads as still-legible; ambient motion communicates state, never decorates.
- [x] **Everything Connected** — every graphic exposes its underlying artefacts; every node/cell/marker links to Evidence Drawer (§10) and Lineage Graph (§10.2).
- [x] **Progressive Disclosure** — Simple shows the graphic + Division-voice caption + 1 legend chip; Advanced adds method chips, confidence bands, and diagnostic overlays.
- [x] **Evidence First** — no graphic asserts a number without linking to the artefact behind it; every axis carries a `→ underlying table` drill-through.
- [x] **Persona Awareness** — Executive/Cinema uses the Concept-C treatment (still, generous whitespace, editorial captions); Operations uses Concept-A (dense, monospace labels, ambient pulse on live data); Research uses Concept-B (soft glow on active traversal); Developer sees raw diagnostic overlays.
- [x] **Mission Control First** — every graphic degrades to a compact tile representation for use on Mission Control (§7.11.2 chart-tile anatomy).
- [x] **Accessibility (WCAG 2.2 AA)** — colour-blind safe (letter/shape fallback on every hue); keyboard-navigable data points; screen-reader captions authored per graphic; `prefers-reduced-motion` collapses motion to fade only.
- [x] **Motion Discipline** — ambient motion allowed only where the underlying entity is *actively producing* data; motion budget from Bible §6.1 tiers.
- [x] **Design Token Compliance** — every colour drawn from Bible §5 tokens or the 8-hue chart palette.
- [x] **Six-Signal Rule** — no graphic introduces a new hue; every graphic uses only the sanctioned palette; a 9th chart hue requires a v-major bump (Bible §20.3).
- [x] **Lineage Validation** — every graphic exposes a `⇱ lineage graph` affordance where relevant; every drill-through preserves the operator's context (Bible §1.4.4).
- [x] **Empty-State Quality** — each of G2–G8 ships with authored empty / loading / error / dormant / replay-empty states (§9 per-graphic).
- [x] **Consistency** — every graphic wears the **Signature Frame** (§2) — this is the mechanism of recognisability.
- [x] **Explainability** — every graphic answers *What am I looking at · Why does it matter · Where does it come from · What can I do* in Division voice.
- [x] **Storytelling Copy Standard** — captions in Division voice; no jargon at L1; no acronyms without expansion.
- [x] **Context Never Lost (Bible §1.4.4)** — a graphic's filter chips, time-window and drill-through position survive navigation.
- [x] **Purpose Before Status (D4 §5.1.1)** — every graphic has a permanent one-line "Why this graphic exists" caption in addition to its live state summary.

---

## 1. Purpose of D5

D0 chose the visual language (Concept D). D1 codified the visual system.
D2 codified the timeline. D3 codified the decision surface. D4 codified
the organisation. **D5 codifies the visual moments that make Strategy
Factory memorable.**

**Success test.** A stakeholder viewing a single one of these graphics —
with the Strategy Factory brand cropped out — must still recognise the
product. This is the recognisability bar.

**Failure test.** If any graphic could be published in a Linear /
Palantir / Datadog / Vercel dashboard without looking out of place, it
has failed the D5 mandate.

**Recognisability is achieved through *pattern consistency*, not through
visual complexity.** A quiet graphic wearing the Signature Frame is more
recognisable than a busy graphic without it.

---

## 2. The Signature Frame (the mechanism of recognisability)

Every signature graphic (G1 – G8) wears the **Signature Frame** — a
shared visual grammar across all eight graphics. This is *the reason*
Strategy Factory graphics are recognisable in isolation.

### 2.1 The seven Signature Frame elements

```
┌────────────────────────────────────────────────────────────────────┐
│  ▬  RESEARCH DIVISION · KNOWLEDGE GRAPH                     ◐ live │  ← 1 · Frame Head
│  Why this exists: Reveals how our knowledge base has grown        │
│                   and which items other artefacts depend on.       │  ← 2 · Purpose caption
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                                                              │  │  ← 3 · Frame Body (the graphic itself)
│  │                    (the graphic)                             │  │
│  │                                                              │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Now  248 items indexed · 12 promoted in the last 24 h            │  ← 4 · Live-state caption
│                                                                    │
│  P verified  W needs-evidence  F failed  A advisory  · edge = promote│  ← 5 · Legend strip
│                                                                    │
│  ⇩ · ⇱ lineage · 📌 pin · [ chart ▾ ] · [ live ▸ ]                 │  ← 6 · Action rail
│                                                                    │
│  2026-07-20 12:24 UTC · master-bot@v55                             │  ← 7 · Provenance stamp
└────────────────────────────────────────────────────────────────────┘
     ▲
     3-pixel accent top-stroke in the graphic's divisional hue
```

**The seven elements, in order:**

1. **Frame Head** — a 3 px top accent stroke in the graphic's divisional
   hue (from the 8-hue chart palette, D4 §5.1). Left: a caret glyph `▬`
   (identical across all G-graphics). Then the graphic title in
   `--font-caption` UPPERCASE spaced with `Division · Graphic name`.
   Right: a live-state chip (`◐ live`, `● paused`, `○ dormant`).
2. **Purpose caption** — one line, timeless, Division voice, answering
   *"Why does this graphic exist?"* (D4 §5.1.1 principle applied to
   graphics). Uses `--font-body-sm` `--content-md`.
3. **Frame Body** — the graphic itself. `--surface-1` background;
   `--stroke-1` 1 px border; radius per Concept (A/B/C per Bible §5.6).
4. **Live-state caption** — transient one-line Division-voice summary of
   *what the graphic is showing right now*. Updates on data change.
5. **Legend strip** — hoverable chips, letter-glyph + colour, spelling
   out every visual encoding on the graphic. Colour-blind-safe by
   construction.
6. **Action rail** — a horizontal strip of standard affordances
   *in the same order every time*: export chip (`⇩`), lineage graph
   (`⇱`), pin (`📌`), three-view toggle (`chart ▾` — Advanced only),
   time-window chip (`live ▸`).
7. **Provenance stamp** — timestamp `YYYY-MM-DD HH:MM UTC` mono,
   `--content-lo`, `--font-caption`, followed by signer (typically
   `master-bot@vNN` or `governance`). Anchored bottom-left.

### 2.2 Why the Signature Frame works

- **Head + purpose + provenance** are typographic — they identify the
  product regardless of the graphic's data.
- **Action rail is spatially constant** — muscle memory works across
  every graphic (the export chip is always in the same place).
- **Legend strip enforces colour-blind fallback** and enforces the
  six-signal ceiling in one place.
- **Live-state caption** is the Storytelling Standard rendered inside
  a chart.

### 2.3 The Frame is inviolate

Every G-graphic wears all seven elements. Missing one is a design
defect. Adding a new element requires a v-major bump (Bible §20.3).

**Frame renders in every posture:**
- Workstation: full frame.
- Tablet: full frame with Purpose caption folded to a hover tooltip
  (the caret still shows).
- Briefing (Cinema): full frame with generous `--space-7` whitespace
  around the Body.
- Print: full frame monochrome; Live-state caption printed as the last
  ~observation.
- Tile (Mission Control): reduced frame — Head + Body + one-line
  combined Purpose/Live caption + Action rail (no legend strip);
  full frame appears on drill-through.

### 2.4 Retrofit to G1

D4's G1 (Workforce Org Chart) is retrofitted to wear the Signature
Frame in D8 Sprint 2 pass. Same seven elements. Minor edit noted here;
no D4 rewrite required.

---

## 3. Shared visual grammar (beyond the Frame)

Beyond the Frame, five recurring motifs bind the graphics together.

### 3.1 Filled / hollow / red-cross / grey-dash state alphabet

Every G-graphic uses the same four-symbol alphabet for state within
the graphic body:

| Glyph | Meaning |
|---|---|
| `●` | Active / complete / passed |
| `○` | Pending / queued / dormant |
| `⨯` | Failed / offline |
| `–` | N/A / skipped |

Never any other symbols to represent state.

### 3.2 Mono numeric labels

Every number rendered *inside* a graphic body is Berkeley Mono with
`tabular-nums`. Sans numerics appear only in captions.

### 3.3 Ambient pulse only for *active production*

Ambient motion (2 s Concept-B pulse, 6 % scale, 15 % opacity variance)
appears only on the specific visual element that represents *live
production of new data*. A knowledge-graph node currently being written
to pulses. An idle node does not. A knowledge-graph node representing
old data never pulses regardless of state.

### 3.4 Division voice tooltips

Every hover, every legend chip, every data-point tooltip is written in
Division voice (`Research Division · retrieved · 2 h ago`). No log-
style tooltips.

### 3.5 The 3-pixel divisional accent

Every graphic's Frame Head carries a 3-pixel top stroke in its
*divisional hue* (from the D4 §5.1 chart palette). The divisional hue
appears **only** in the accent stroke — never inside the graphic body.
The Frame does the identifying; the graphic does the informing.

---

## 4. G2 — Strategy Pipeline Ribbon

*Divisional hue: c3 amber `#f0b429` (all divisions contribute; amber signals passage)*

### 4.1 Purpose

The definitive answer to *"Where is this strategy in its life?"* Renders
the canonical eight pipeline stages (Bible §10.1) as a horizontal
ribbon of dots + labels.

Purpose caption: *"Shows how each strategy progresses through the eight
stages the Factory promises to complete."*

### 4.2 Data → visual mapping

Eight stages, one dot per stage:

```
Generated ─● Validated ─● Optimized ─● Certified ─○ Knowledge stored ─○ Portfolio candidate ─○ Approved ─○ Production
```

- Filled `●` = complete
- Hollow `○` = pending
- `⨯` = failed at this stage
- `–` = skipped (N/A for this artefact type)

**Signature elements that make G2 unmistakable:**

1. **Exactly eight stages, always in that order.** No product other than
   Strategy Factory has this exact taxonomy. The eight-stage order is
   itself a signature.
2. **The stage labels use Sentence case** (not UPPERCASE), whereas
   almost every other timeline in the industry uses caps. Deliberate.
3. **Connector lines are `─` (box-drawing horizontal)** — not arrows,
   not `→` — because the pipeline is a lineage, not a directive.
4. **The dot representing the *current* stage carries a subtle 2 s
   ambient pulse** — visible even at tile size.

### 4.3 Interaction

- **Click a stage dot** → opens Evidence Drawer scoped to that stage
  (per D1 §7.3 pipeline-stage bar).
- **Hover a stage** → tooltip: `Validation Division · walk-forward
  30 d · 12:22 · confidence 0.71`.
- **`⇱ lineage graph`** → opens Lineage Graph (Bible §10.2) focused on
  the strategy showing all ancestors and descendants of this artefact.
- **`📌 pin`** → adds this pipeline to the pins tray for comparison
  against another strategy's pipeline.

### 4.4 Motion

- Stage completion event → 320 ms slow crossfade from `○` to `●`; a
  120 ms flash on the connector line to the right, then rest.
- Active stage → 2 s ambient pulse on the dot (6 % scale, 15 % opacity).
- Failure → 200 ms crossfade `○ → ⨯`; connector to the right stays
  hollow.
- `prefers-reduced-motion` → all motion collapses to opacity fades.

### 4.5 Postures

| Posture | Height | Label treatment |
|---|---|---|
| Workstation | 24 px dots · 32 px total row | full labels |
| Tablet | 20 px dots | first-letter labels (`G · V · O · C · K · P · A · P`) |
| Briefing (Cinema) | 40 px dots · 48 px total | full labels + serif captions |
| Tile | 12 px dots · 16 px total | no labels; hover legend |
| Print | Monochrome; filled dots as `■`, hollow as `□`; connectors as `─`; failure as `⊠` |

### 4.6 Recognisability tests

- **The eight-stage order** — no other product has this taxonomy.
- **`─` box-drawing connectors** — not arrows.
- **Ambient pulse on the current stage** — signature Concept-B motion
  on an otherwise Concept-A graphic.

---

## 5. G3 — Knowledge Graph

*Divisional hue: c4 red `#ff5b5b` used only as advisory-tint on the frame accent*

### 5.1 Purpose

Reveals how the Knowledge Base has grown and which items other artefacts
depend on.

Purpose caption: *"Reveals how our knowledge base has grown and which
items other artefacts depend on."*

**G3 shares its implementation with §10.2 Lineage Graph mode** — one
component, two uses. When invoked as G3, the central node is the
Knowledge Base itself; when invoked as Lineage Graph, the central node
is a specific artefact.

### 5.2 Data → visual mapping

- **Node** = knowledge item.
- **Node ring colour** = trust tier (`--sig-ok verified`,
  `--sig-warn provisional`, `--sig-crit rejected`, `--sig-advisory
  advisory`).
- **Node size** = usage count (min 12 px, max 48 px; log-scaled).
- **Edge** = a promote-event, dedup-event, or contradiction-event.
- **Edge colour** = event type (from the same 4-colour palette above).
- **Edge weight** = number of events (1 px – 4 px).
- **Node label** = the item's Division-voice name (e.g., `regime-detection
  · arxiv:2401.09883`), rendered only on hover or Advanced Lens.

**Signature elements that make G3 unmistakable:**

1. **Force-directed but constrained** — layout is bounded to a
   fixed rectangle; nodes never drift into the caption area.
2. **The Trust-Tier ring** — every node has a `--sig-*` coloured ring,
   never a filled circle. Rings are the discriminator.
3. **Recently-traversed edges glow** — a promote-event that occurred in
   the last 5 min carries a fading luminance halo (`--glow-neural` at
   0.14 alpha, decaying over 30 s).
4. **Recognizably sparse.** No more than ~120 nodes visible at once
   (aggressive edge-bundling above that). This is Palantir-inspired
   but *deliberately less dense*.

### 5.3 Interaction

- **Click node** → Evidence Drawer for the item.
- **Right-click node** → subgraph focus (Bible §10.2.2 — ancestors +
  descendants only).
- **Pin node** → Pinned Preview tray.
- **Time-window chip** cascades — graph renders as of the chip's time.
- **Node hover** → tooltip in Division voice: `Knowledge Base ingested
  arxiv:2401.09883 on regime detection · trust_tier verified · promoted
  4 times`.
- **`Reset layout`** action in the action rail (recomputes force layout
  in 800 ms).

### 5.4 Motion

- Initial layout: force-directed settles over 800 ms (`prefers-reduced-motion`:
  static computed layout, no animation).
- New edge (promote event) enters with 320 ms line-draw + 30 s luminance
  decay on both endpoints and the edge.
- New node enters with 320 ms fade + 6 % pop.
- Pulse on nodes only when the underlying knowledge item is being
  actively written to (rare — indicates ingest in progress).

### 5.5 Postures

| Posture | Nodes visible |
|---|---|
| Workstation | up to 120 |
| Tablet | up to 60 (edge-bundled) |
| Briefing | up to 24 (heaviest-usage only) + narrative caption below |
| Tile | up to 12 nodes; no labels; count summary in caption |
| Print | static computed layout; monochrome; ring thickness distinguishes trust tier |

### 5.6 Recognisability tests

- **Trust-Tier rings** (colour on the ring, not the fill).
- **Bounded force-directed** — nodes never escape the box.
- **Luminance decay on recently-traversed edges** — a signature
  Concept-B motion at low intensity.
- **Division-voice hover tooltips** — never log-style.

---

## 6. G4 — Market Coverage Heatmap

*Divisional hue: c2 green `#3ddc84` (Maintenance division sustains coverage)*

### 6.1 Purpose

Answers *"Do we have the data we claim to have?"* The definitive
signature of data-quality integrity.

Purpose caption: *"Shows how completely we have covered each symbol
across every timeframe."*

### 6.2 Data → visual mapping

A grid: rows are symbols; columns are timeframes.

```
Symbol / TF   1m       5m       15m      1h       4h       1d
────────────  ───────  ───────  ───────  ───────  ───────  ───────
EURUSD        ███████  ███████  ███████  ███████  ███████  ███████
GBPUSD        ███████  ███████  ███████  ██████░  ███████  ███████
USDJPY        ███████  ███████  ████░░░  ████░░░  ███████  ███████
XAUUSD        ██░░░░░  ███████  ███████  ███████  ███████  ███████
BTCUSD        ███████  ███████  ███████  ░░░░░░░  ░░░░░░░  ░░░░░░░
```

- Each cell is a horizontal *completeness bar* (8-segment mini-bar).
- Segment filled `█` = data present; empty `░` = gap.
- Cell background subtly reflects overall completeness (mono greyscale;
  no colour except for critical gaps).
- **Critical gaps** (< 50 % completeness) get a red `⨯` glyph superimposed
  and a subtle `--sig-crit` outline.

**Signature elements that make G4 unmistakable:**

1. **The 8-segment mini-bar per cell.** Not a percentage number, not a
   sparkline — a *bar of literal box-drawing characters*. This is the
   most typographic heatmap in the industry.
2. **Monochrome except for gaps.** Colour appears only where it
   demands attention (Attention discipline).
3. **Symbol names in mono, left-aligned; TF headers in caption UPPERCASE.**
4. **Hover on a cell reveals a Division-voice narrative:** `Maintenance
   completed the last BI5 sweep for EURUSD·1m on 2026-07-20 12:14 UTC.
   Zero gaps.`

### 6.3 Interaction

- **Click cell** → Evidence Drawer with per-cell BI5 sweep history +
  gap-list + auto-repair status.
- **`⇩` export** → CSV of the whole matrix.
- **`⇱ lineage`** → not applicable on this graphic (no ancestry to
  render); Frame Action rail hides the `⇱` chip.
- **Time-window chip** → renders coverage as of past time (e.g., *"did
  we have full coverage a week ago?"*).

### 6.4 Motion

- Cell fill updates: 120 ms instant flash on the segment that changed.
- No ambient motion. This is a stillness-first graphic.
- Critical-gap `⨯` fades in over 320 ms when a gap is newly detected.

### 6.5 Postures

| Posture | Cells visible |
|---|---|
| Workstation | full matrix (all symbols × all TFs) |
| Tablet | scroll horizontally; sticky first column |
| Briefing | reduced matrix (top-20 symbols × 4 headline TFs) |
| Tile | single-line summary — `12 / 720 cells with gaps · 98.3 % coverage` |
| Print | box-drawing renders directly; ideal for printouts |

### 6.6 Recognisability tests

- **8-segment box-drawing cells** — no other product does this.
- **Monochrome + gap-red discipline.**
- **Symbol-in-mono / TF-in-caption alignment.**

---

## 7. G5 — Execution Quality Constellation

*Divisional hue: c6 gold `#b8935f` (Execution & broker relationships)*

### 7.1 Purpose

Answers *"How well are our brokers actually executing our orders?"*
A scatter plot of fill quality × slippage per broker, with ambient
sparkle on the most recent fills.

Purpose caption: *"Shows how well every broker executes our trades in
real time."*

### 7.2 Data → visual mapping

Scatter plot:

- **X-axis** — latency to fill (ms), log-scaled.
- **Y-axis** — slippage in pips.
- **Marker** — 6-pointed star, one per broker.
- **Marker colour** — broker-per-hue from the 8-hue chart palette.
- **Marker size** — trade size (log-scaled).
- **Reference lines** — target fill quality zone (dashed `--content-lo`),
  labelled `target: p95 ≤ 1.5 pips`.
- **Trailing high/low annotations** (Bible §14.5) on both axes.

**Signature elements that make G5 unmistakable:**

1. **6-pointed star markers** — not dots, not circles. This is the
   unusual choice that identifies G5.
2. **Ambient sparkle on the most recent fill** — the newest marker
   emits a soft `--glow-active` halo for 30 s after arrival, then
   settles.
3. **Constellation caption in Division voice** — `Execution Division
   observed 30 fills across 3 brokers. p95 fill quality 1.2 pips (target
   1.5).`
4. **The reference zone shaded at 4 % `--sig-ok` alpha** — the "good
   zone" you're aiming at.

### 7.3 Interaction

- **Click marker** → Evidence Drawer for the individual fill.
- **Click broker in legend** → filters constellation to that broker.
- **`📌 pin broker`** → compare two brokers side-by-side (Pinned Preview
  §7.12).
- **`⇱ lineage`** → not applicable (fills don't have ancestry in the
  strategy sense).
- **Time-window chip** → renders fills within the window.

### 7.4 Motion

- New fill arrives → marker enters with 200 ms fade + 30 s luminance
  decay on the `--glow-active` halo.
- Broker filter → 320 ms crossfade of non-selected markers to 30 %
  opacity.
- No ambient motion on rest.

### 7.5 Postures

| Posture | Behaviour |
|---|---|
| Workstation | full constellation, up to 500 markers |
| Tablet | last-hour markers only |
| Briefing | top-5 brokers only + narrative summary |
| Tile | one-star aggregate + `p95 1.2 pips` label |
| Print | monochrome; markers grade by size + a per-broker legend |

### 7.6 Recognisability tests

- **6-pointed star markers.**
- **Luminance-decay halo on the most recent fill.**
- **Target zone as shaded polygon.**

---

## 8. G6 — Portfolio Risk Surface

*Divisional hue: c1 violet `#8b8ffb` (rare application; Portfolio Division)*

### 8.1 Purpose

Answers *"How risky is our current portfolio, along which dimensions?"*
A signature "surface" plot (visually 2.5D but computed 2D) of
allocation × correlation × expected drawdown.

Purpose caption: *"Shows how correlated our portfolio positions are and
where drawdown risk concentrates."*

### 8.2 Data → visual mapping

Two-axis heatmap with a *depth cue*:

- **X-axis** — positions along the correlation spectrum (least → most
  correlated).
- **Y-axis** — positions along the allocation spectrum (smallest →
  largest allocation).
- **Cell fill** — expected 30-day drawdown, coloured by a two-hue
  gradient `c1 violet → c0 sky` (this is the **only** graphic that uses
  a colour gradient — deliberate signature).
- **Cell content** — one letter glyph in mono, denoting risk category
  (`L`, `M`, `H`) — colour-blind fallback.
- **Contour lines** — `--stroke-2` isopleths at 5 %, 10 %, 20 % drawdown
  thresholds; labelled at intersection with the border.

**Signature elements that make G6 unmistakable:**

1. **Violet → sky gradient** — the *only* graphic using a gradient.
   Instantly recognisable when placed among G2–G8.
2. **Contour lines with labelled thresholds** — a typographic feature
   uncommon in modern dashboards.
3. **Letter-glyph fallback in each cell** — colour-blind safe by
   construction.
4. **Rectangular, not polar.** No pie charts. No donuts. Ever.

### 8.3 Interaction

- **Click cell** → Evidence Drawer showing which positions occupy this
  cell + their historical drawdown paths.
- **`⇱ lineage`** → opens Lineage Graph focused on the position(s) in
  the clicked cell.
- **`📌 pin cell`** → compare cell states across time windows.
- **Time-window chip** → renders risk surface at past time.

### 8.4 Motion

- Cell update on portfolio change: 400 ms editorial tween (Bible §6.1
  Editorial tier).
- Contour lines re-render with 320 ms slow tier.
- No ambient motion.

### 8.5 Postures

| Posture | Behaviour |
|---|---|
| Workstation | full surface, ~10×10 grid |
| Tablet | 6×6 aggregated grid |
| Briefing | ~4×4 with narrative caption dominating |
| Tile | single-cell summary — "portfolio drawdown risk H · 12 % 30-d expected" |
| Print | high-fidelity monochrome contour map |

### 8.6 Recognisability tests

- **The violet → sky gradient** — the only signature graphic with a
  gradient fill.
- **Contour lines with labelled thresholds** — typographic detail
  uncommon elsewhere.

---

## 9. G7 — Learning Evolution Timeline

*Divisional hue: c6 magenta `#d17bff` (Learning Division)*

### 9.1 Purpose

Answers *"How has meta-learning shaped the Factory over time?"*
A horizontal, scrubbable timeline of Learning Division recommendations
with outcome markers.

Purpose caption: *"Shows how the Learning Division's recommendations
have changed the Factory over time."*

### 9.2 Data → visual mapping

A horizontal band divided by time bracket (day / week / month per
zoom):

- **Marker per recommendation** — small square, colour by outcome
  (`--sig-ok accepted`, `--sig-warn deferred`, `--sig-crit rejected`,
  `--sig-advisory partial`).
- **Marker size** — impact magnitude (small / medium / large).
- **Playhead** — a vertical `--sig-info` line indicating current time
  (or the scrub time).
- **Track above** — division-voice caption of each recommendation on
  hover.
- **Sparkline below** — running acceptance rate (%) with trailing
  high/low annotations (Bible §14.5).

**Signature elements that make G7 unmistakable:**

1. **Square markers, not dots** — visually distinct from G5's stars,
   G2's dots, G3's circles.
2. **Playhead is a 2 px vertical `--sig-info` line** — same style as
   the D2 Timeline scrub playhead.
3. **Acceptance-rate sparkline below the marker band** — a
   double-representation of the same data in two registers.

### 9.3 Interaction

- **Click marker** → Evidence Drawer for the recommendation and its
  outcome trail.
- **Drag playhead** → scrubs the timeline; all other surfaces
  respecting the time-window chip update in parallel (Bible §7.13
  cascade — Factory Replay).
- **`📌 pin recommendation`** → compare two recommendations.
- **Time-window chip** → controls the visible band.

### 9.4 Motion

- Playhead drop: 240 ms `cubic-bezier(0.16, 0.84, 0.44, 1)`.
- New recommendation marker: 200 ms fade + 6 px y-slide up.
- Acceptance-rate sparkline: 320 ms slow line-draw on entry;
  120 ms flash on data-point update.

### 9.5 Postures

| Posture | Behaviour |
|---|---|
| Workstation | full band + sparkline; scrubbable |
| Tablet | full band; sparkline collapsed to a small chip |
| Briefing | narrative summary of the last 10 recommendations |
| Tile | one-line summary + last outcome chip |
| Print | timeline printed monochrome; markers grade by size |

### 9.6 Recognisability tests

- **Square markers.**
- **`--sig-info` vertical playhead** — identical to D2 Timeline scrub.
- **Double representation (marker band + acceptance sparkline).**

---

## 10. G8 — Neural Sparkline Strip

*Divisional hue: none — this graphic sits at the shell footer and uses a per-subsystem hue*

### 10.1 Purpose

The **ambient pulse of the Factory.** Six sparklines — one per major
subsystem — continuously line-drawing. If the Factory is alive, this
strip is moving; if the Factory is at rest, the lines are flat.

Purpose caption: *"Shows the live pulse of every major subsystem — one
line each, always visible."*

### 10.2 Data → visual mapping

Six horizontal sparklines stacked in a 6-row × N-column strip:

```
orchestrator   ─────────────────────────────────────────────────
ingestion      ─────╱╲───────╱╲──────────────╱╲─────────────────
scheduler      ────────────────────────────────────────────────
llm            ─────────────────────────────────────────────────
governance     ─────────────────────────────────────────────────
kill posture   ─────────────────────────────────────────────────
```

- **X-axis** — time (last N minutes; 60 min default).
- **Y-axis** — subsystem-specific metric (rate of events; normalised).
- **Line colour** — subsystem-per-hue from the 8-hue chart palette
  (a rare deliberate use of chart hues *outside* a G-body — because
  G8 IS the subsystem row).
- **Sparkline stroke width** — 1 px (deliberately thin).
- **Recent activity** — the last 60 s of every sparkline carries a
  subtle luminance shimmer (Concept-B).

**Signature elements that make G8 unmistakable:**

1. **Exactly six lines, in a fixed order.** No other product has this
   six-subsystem taxonomy laid out this way.
2. **Row labels in lowercase caption** (`orchestrator`, `ingestion`,
   …) — the only signature graphic that uses lowercase row labels.
3. **1-pixel stroke** — the thinnest graphic in the gallery.
4. **Continuous ambient shimmer on the trailing 60 seconds** —
   Concept-B luminance at 0.10 alpha.
5. **Anchored to the Mission Control footer** — the operator sees G8
   below every panel on the landing page. Its permanent placement is
   itself part of its signature.

### 10.3 Interaction

- **Click a sparkline** → Evidence Drawer showing that subsystem's
  history + current chip.
- **Hover** → Division-voice tooltip: `Ingestion Division · 12 events
  in the last minute · nominal.`
- **`⇱ lineage`** → not applicable per subsystem strip.
- **Time-window chip** → adjusts the visible history horizon (default
  60 min).

### 10.4 Motion

- **Continuous line-draw cycle** — 1200 ms per full sparkline
  reveal (a subtle mask sweep from left to right that repeats
  indefinitely). This is G8's signature motion. Never on any other
  graphic.
- **Recent shimmer** — trailing 60 s at 0.10 luminance alpha, refreshed
  every 200 ms.
- **`prefers-reduced-motion`** → shimmer + line-draw cycle disabled;
  static sparklines only.

### 10.5 Postures

| Posture | Behaviour |
|---|---|
| Workstation | full 6-row strip below Mission Control panels |
| Tablet | full strip but shorter horizon (30 min) |
| Briefing | strip promoted to top-of-view narrow band + narrative caption |
| Tile | 1-row combined sparkline (single line, aggregated) |
| Print | 6 static sparklines; no shimmer |

### 10.6 Recognisability tests

- **Six-line taxonomy** in fixed order.
- **1-pixel stroke.**
- **Continuous line-draw sweep** — unique motion.
- **Lowercase labels.**
- **Ambient shimmer on trailing 60 s.**

---

## 11. Cross-graphic interaction matrix

| Interaction | G2 | G3 | G4 | G5 | G6 | G7 | G8 |
|---|---|---|---|---|---|---|---|
| Click → Evidence Drawer | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `⇱` Lineage Graph mode | ✅ | ✅ (same component) | – | – | ✅ | ✅ | – |
| `📌` Pinned Preview | ✅ | ✅ | – | ✅ | ✅ | ✅ | – |
| Time-window chip | – (per-artefact) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Three-view toggle (Advanced) | – | ✅ | ✅ | ✅ | ✅ | ✅ | – |
| Permalink + CSV export | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Ambient motion | pulse on active stage | pulse on active ingest | none | halo on latest fill | none | none | continuous shimmer |
| Signature Frame worn | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 12. Empty / loading / error / dormant / replay-empty states

Each graphic ships all five states, all wearing the Signature Frame
(with the Frame Body replaced by the state content).

Common patterns:

### 12.1 Empty (no data yet)

```
[ icon · muted grey ]

<Division voice explanation of why there is no data yet>.

→ <one primary action>   ·   <one secondary link>
```

Colour `--sig-dormant`. Never red.

### 12.2 Loading

- < 300 ms — no indicator.
- 300 ms – 2 s — shimmer skeleton in the Frame Body area.
- \> 2 s — narrative: `Rendering knowledge graph over 3 months of promote
  events…`

### 12.3 Error (backend unreachable)

```
[ icon · wifi-off ]

<Graphic name> could not be loaded.
Retrying every 8 seconds.

→ view logs · developer
```

Colour `--sig-warn`.

### 12.4 Dormant (feature-gated)

```
[ icon · shield · muted ]

DORMANT · <Graphic name> is gated by Phase X activation.
<Division voice explanation>.

→ view activation plan
```

**Never red. Never offer Retry.**

### 12.5 Replay-empty (scrub landed on empty window)

```
[ icon · rewind ]

<Graphic name> has no data at the selected time.

→ expand window   ·   return to live
```

---

## 13. Persona treatments

### 13.1 Executive · Concept-C

- Frame Head uses Serif for the Graphic name (GT Sectra); rest stays
  mono.
- Purpose caption uses serif italic — a rare luxury signal.
- Ambient motion disabled (except G8 line-draw sweep, kept as it
  represents the Factory's ongoing life).
- Density: cinema; Body enlarged; `--space-7` whitespace around.

### 13.2 Operations · Concept-A (default)

- Full Frame; mono everywhere.
- Ambient motion enabled per §11.
- Density: compact.

### 13.3 Research · Concept-B

- Softer corners (`--radius-3` 14 px on Frame Body).
- Luminance halos on active elements slightly amplified (0.16 alpha vs
  0.14 default).
- Density: cozy.

### 13.4 Developer

- Advanced Lens auto-on.
- Diagnostic overlays visible (e.g., G3 shows dedup thresholds, G4
  shows BI5 sweep telemetry, G5 shows raw fill payloads).
- Density: compact.

---

## 14. Data contract (frontend expectation)

All graphics are frontend-only compositions over existing backend
endpoints. **Zero new backend endpoints required.** Feature Freeze
respected.

Shared frame contract:

```ts
type SignatureFrame<T> = {
  graphic_id:      'G1'|'G2'|'G3'|'G4'|'G5'|'G6'|'G7'|'G8';
  division:        DivisionName;               // determines Frame Head accent hue
  title:           string;                     // "KNOWLEDGE GRAPH"
  purpose_caption: string;                     // Division voice, timeless
  live_state:      string;                     // Division voice, transient
  legend:          LegendEntry[];              // colour + letter + label
  action_rail:     ActionRailConfig;
  provenance:      { at: string; signer: string };
  body:            T;                          // per-graphic payload
  time_window:     TimeWindow;                 // shared
  filter_state?:   FacetState;                 // shared
};
```

Per-graphic body types (`GraphicG2Body`, `GraphicG3Body`, …) are
authored during Sprint 2/3 implementation and are omitted here (D5 is
design-first).

Adapter locations:
- `services/pipeline.js` — G2
- `services/knowledgeGraph.js` — G3 (shared with §10.2 Lineage Graph)
- `services/coverage.js` — G4
- `services/execution.js` — G5
- `services/portfolioRisk.js` — G6
- `services/learningEvolution.js` — G7
- `services/neuralPulse.js` — G8

---

## 15. Copy library seed (D7 owns the full library)

Purpose captions (locked from D5):

| # | Graphic | Purpose caption |
|---|---|---|
| G2 | Pipeline Ribbon | *Shows how each strategy progresses through the eight stages the Factory promises to complete.* |
| G3 | Knowledge Graph | *Reveals how our knowledge base has grown and which items other artefacts depend on.* |
| G4 | Coverage Heatmap | *Shows how completely we have covered each symbol across every timeframe.* |
| G5 | Execution Constellation | *Shows how well every broker executes our trades in real time.* |
| G6 | Risk Surface | *Shows how correlated our portfolio positions are and where drawdown risk concentrates.* |
| G7 | Learning Evolution | *Shows how the Learning Division's recommendations have changed the Factory over time.* |
| G8 | Neural Pulse Strip | *Shows the live pulse of every major subsystem — one line each, always visible.* |

Live-state captions (examples; fuller catalogue in D7):

- G2 · *"Currently at Optimize · Mutation Division working on candidate #47."*
- G3 · *"248 items indexed · 12 promoted in the last 24 h."*
- G4 · *"98.3 % coverage · 12 gaps out of 720 cells."*
- G5 · *"Execution Division observed 30 fills across 3 brokers · p95 1.2 pips."*
- G6 · *"Portfolio drawdown risk M · 8 % expected 30-d."*
- G7 · *"Learning Division: 24 recommendations · 18 accepted (75 %)."*
- G8 · *"All 6 subsystems nominal · orchestrator running 42 tasks."*

---

## 16. Recognisability audit — the isolation test

For each graphic, verify the recognisability by extracting a screenshot
of *just the Frame Body + Signature Frame* (no branding, no
surrounding UI) and asking:

**Can a first-time viewer identify this as Strategy Factory?**

Per graphic, the answer is *yes* because of:

| Graphic | Primary signature | Backup signature |
|---|---|---|
| G2 | Eight-stage taxonomy + `─` box-drawing | Sentence-case labels; current-stage pulse |
| G3 | Trust-Tier rings on nodes | Bounded force-directed; luminance-decay edges |
| G4 | 8-segment box-drawing cells | Monochrome + `⨯` red-gap discipline |
| G5 | 6-pointed star markers | Halo decay on latest fill; target-zone shading |
| G6 | Violet → sky gradient (the only gradient) | Contour lines with labelled thresholds |
| G7 | Square markers + `--sig-info` playhead | Double-track representation |
| G8 | Six 1-px sparklines + continuous sweep | Lowercase labels; shimmer on trailing 60 s |
| G1 | 3-pixel divisional accent + Division-voice purpose | Retrofit adopts full Signature Frame |

**The five recognisability heuristics from `DESIGN_INSPIRATION_STUDY.md`
§5.1** — Division voice · cool near-black surface · six-signal ceiling ·
mono numeric · lineage/evidence link — pass on every graphic here.

---

## 17. Sprint acceptance criteria (per graphic)

Each graphic ships only if:

- ✅ 16-item Design Principles Checklist confirmed (§0)
- ✅ Signature Frame worn — all 7 elements present (§2.1)
- ✅ Recognisability isolation test passes (§16)
- ✅ Renders 5 states (empty / loading / error / dormant / replay-empty · §12)
- ✅ Ambient motion respects §11 discipline (only where §11 says)
- ✅ `prefers-reduced-motion` verified — motion collapses to fade
- ✅ Colour-blind fallback — letter glyph or shape backup on every hue
- ✅ Keyboard navigable — every data point selectable via keyboard
- ✅ Screen-reader caption authored per graphic
- ✅ Persona treatments verified (Executive · Operations · Research · Developer · §13)
- ✅ Postures verified — workstation · tablet · briefing · tile · print · §11
- ✅ Adapter implemented — pure frontend, Feature Freeze respected (§14)
- ✅ Copy library seed applied (Purpose + example Live-state captions · §15)
- ✅ Context Never Lost — filter state, time-window, drill-through position survive navigation
- ✅ `data-testid` on every interactive element

---

## 18. Sprint prioritisation

Sprint 1 (Mission Control): the tile-representations of G2, G4, G8 are
required to compose Mission Control.

Sprint 2: full-fidelity G2, G4, G8; skeleton G1 wearing Signature Frame.

Sprint 3: G3 (with §10.2 Lineage Graph mode dual-implementation), G5, G7.

Sprint 4: G6 (last — the Portfolio Risk Surface requires the most data
and is Executive-oriented; can wait).

---

## 19. What D5 does NOT include

- Full copy library (D7 owns the ≥ 40-headline library covering every
  Division × every event type).
- Coded prototype (belongs to the Sprint implementing each graphic).
- Interactive Storybook (belongs to Sprint 1 kick-off).
- New backend endpoints (Feature Freeze — none required).
- New colour hues (six-signal ceiling remains inviolate).

---

## 20. Next: D6 — Personalization modes spec

Per Bible v2.1 §25. D6 codifies:

- Full per-mode specification of Executive · Operations · Research ·
  Developer.
- Landing-surface per mode (per Bible v2.1 §22).
- Copilot trace-as-UI treatment (Bible v2.1 §24 · P24).
- Facet grammar in each mode.
- Time-window defaults per mode.
- Density and posture combinations per mode.

Expected timeline: 2–3 days.

---

*End of D5 — Signature Graphic Gallery.*
*All 16 checklist items confirmed. Signature Frame codified as the
mechanism of recognisability. G1 retrofit noted. Bible v2.1, D4 Purpose
Before Status refinement, and Backend Feature Freeze all respected.*
*Awaiting your review before D6 begins.*

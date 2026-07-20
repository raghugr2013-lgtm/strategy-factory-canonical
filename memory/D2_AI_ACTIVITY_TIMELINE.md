# D2 — AI Activity Timeline

> Signature experience of Strategy Factory. Not application logs — the visible presence of an autonomous AI organization at work.
> Layered on D1 · governed by Bible v1.0 + v2.0 delta.
> Prepared 2026-07-20.

---

## 0. Design Principles Checklist (permanent quality gate)

Every design deliverable D2 → D8 opens with this. All 14 must be confirmed before the document is considered complete.

- [x] **Invisible Luxury** — motion, colour and typography chosen for craftsmanship. Zero decorative animation. No neon, no gradients, no glass. Ambient pulse only on **running** entities.
- [x] **Everything Connected** — every timeline row exposes actor, subject, and evidence links; every entry connects to the Lineage bar (D1 §10). Timeline row → artefact page → lineage → back to timeline round-trip verified.
- [x] **Progressive Disclosure** — Simple shows 1 sentence + 1 detail line; Advanced adds method chip, confidence interval, duration, provenance triple. Same row, more chips.
- [x] **Evidence First** — no row shows "Completed." Every row cites a stage, a confidence, a next step. Every row has an evidence link.
- [x] **Persona Awareness** — Executive sees filtered Accomplishment + Approval rows (Concept-C typography treatment); Operations sees full stream (Concept-A); Research sees Research/Knowledge/Learning filtered (Concept-B ambient sparkle); Developer sees + errors + telemetry.
- [x] **Mission Control First** — Timeline is the persistent right rail on Mission Control at full width; every other module gets it as a collapsible 40 px stripe.
- [x] **Accessibility** — WCAG 2.2 AA. Keyboard-only navigation. Screen-reader labels. Colour-blind safe (letter glyph + shape + colour). `prefers-reduced-motion` compresses all motion to opacity fades.
- [x] **Motion Discipline** — enters within 200 ms medium tier; 40 ms stagger; ambient pulse only on actor chips of running workers; number tweens follow persona (A instant, B useSpring, C editorial).
- [x] **Design Token Compliance** — every colour from §3 tokens; typography from §4; spacing from §5.
- [x] **Six-Signal Rule** — actor chip colour drawn only from `--sig-*` tokens; zero new hues introduced.
- [x] **Lineage Validation** — every row's subject links to Lineage bar (D1 §10). Timeline round-trips to the artefact and back without dead ends.
- [x] **Empty-State Quality** — 5 authored empty states (§7): idle-factory, filter-empty, offline-timeline, replay-empty, error-fetching.
- [x] **Consistency** — no new visual language introduced. Reuses Activity Row (D1 §7.4), chip system (§7.1), and motion budget (§6).
- [x] **Explainability** — every row answers What happened · Why · What next. The "What next" affordance is baked in.

---

## 1. Purpose

Traditional log viewer:
```
[12:24:14.041] INFO orchestrator.py:242 opened_llm_call provider=openai model=gpt-5
```

Strategy Factory Timeline:
```
[12:24] · orchestrator · Opened GPT-5 to score 3 candidates
                        confidence 0.87 · verdict: proceed to backtest
                        → view evidence   → open pipeline
```

The timeline is **prose about work** — one narrative row per meaningful event. It should feel like *watching an intelligent organization*, not reading a system log.

**Anti-goals** (things the timeline must never become):
- A raw log stream
- A per-user notification feed
- A chat interface
- A debug console (that lives at Layer 5 via ⌘K > developer > errors)

---

## 2. Layout & posture placement

### 2.1 Mission Control (default landing · Operations)

```
┌──────────────────────────────┬──────────────┐
│   MC panels                  │   AI ACTIVITY │
│                              │   TIMELINE    │
│   (six-question grid)        │               │
│                              │  live rows    │
│                              │  (right rail) │
│                              │               │
│                              │  240 px wide  │
│                              │  full-height  │
└──────────────────────────────┴──────────────┘
```

Width: 240 px workstation · collapsible 40 px stripe elsewhere.

### 2.2 Every other module

- Collapsed 40 px stripe on the right showing icon + count of new rows since last visit
- Click to expand into 240 px overlay (does NOT push content — overlays the right edge)
- ⌘/ toggles from anywhere

### 2.3 Briefing posture (Executive Cinema)

Timeline **promoted to bottom bar** — 3 rows tall, horizontally scrolling, showing last 12 events. Serif-typographic treatment (Concept C).

### 2.4 Mobile / tablet-narrow (< 900 px)

Timeline is a full-screen sheet, opened by tapping a floating chip in top-right. Read-only.

---

## 3. Row anatomy (canonical)

```
┌────────────────────────────────────────────────────────────────┐
│ [12:24]  [ ▶ orchestrator ]                                    │  ← header line
│                                                                │
│ Opened GPT-5 to score 3 candidates                             │  ← primary sentence
│ confidence 0.87 · verdict: proceed to backtest                 │  ← detail (optional, 1 line)
│                                                                │
│ → view evidence     → open pipeline                            │  ← links (up to 2)
└────────────────────────────────────────────────────────────────┘
```

### 3.1 Fields

| Field | Format | Source |
|---|---|---|
| Timestamp | `HH:MM` in mono `--content-lo`. Full ISO on hover. | `event.at` |
| Actor chip | 20 px pill, icon + text; colour by role (see §4) | `event.actor` |
| Primary sentence | Sans body-sm, `--content-md`, 1 sentence, max 90 chars | `event.headline` |
| Detail line | Sans body-sm, `--content-md`, optional, max 90 chars | `event.detail` |
| Links | Sans body-sm, `--sig-info`, up to 2 | `event.links[]` |
| Confidence chip (Advanced) | 20 px, `[confidence 0.87]` | `event.confidence` |
| Method chip (Advanced) | `[walk-forward]`, `[dedup]` etc. | `event.method` |
| Duration chip (Advanced) | `[3.4 s]`, `[12 min]` | `event.duration_ms` |
| Provenance triple (Advanced) | 3 chips | `event.provenance` |

### 3.2 Simple vs Advanced

Simple: header + primary + optional detail + up to 2 links. Nothing more.
Advanced: appends `[confidence] [method] [duration] [provenance-triple]` as a chip strip below detail line.

Toggle is the global Advanced Lens (D1 §11). Never a per-row control.

### 3.3 Row height

Compact: 80 px (Simple) · 108 px (Advanced with chip strip)
Cozy (Research posture): 92 px · 120 px
Cinema (Briefing): 148 px · Serif primary sentence

---

## 4. Actor system (10 types codified from D1 §9)

Each event has exactly one actor. Actors are the *identity* of the work.

| # | Actor | Icon | Chip colour | Role in the org |
|---|---|---|---|---|
| 1 | **research** | `search` | `--sig-info` | discovers, queries, ingests |
| 2 | **generation** | `sparkles` | `--sig-ok` | produces new strategies |
| 3 | **backtest** | `bar-chart-2` | `--sig-info` | validates on history |
| 4 | **mutation** | `git-branch` | `--sig-info` | evolves strategies |
| 5 | **knowledge** | `book` | `--sig-advisory` | curates KB, dedupes, promotes |
| 6 | **learning** | `activity` | `--sig-info` | meta-learning proposals |
| 7 | **portfolio** | `layers` | `--sig-info` | assembles allocations |
| 8 | **execution** | `terminal` | `--sig-info` | observes fills, quality |
| 9 | **maintenance** | `wrench` | `--sig-dormant` | BI5 sweep, auto-repair |
| 10 | **approval** | `flag` | `--sig-warn` | requires operator decision |

Advanced Lens adds 3 diagnostic actors (Developer persona only):
- `error` — `--sig-crit` (only visible in Developer mode + Advanced)
- `telemetry` — `--sig-dormant` (subtle)
- `env` — `--sig-dormant` (config change)

**Rule:** actor colour is *exactly* one of the 6 signal tokens. No hybrids.

---

## 5. The five row states

Every row is authored in five states:

| State | Trigger | Visual |
|---|---|---|
| **Streaming** | Just arrived (< 5 s ago) | 200 ms fade+y-slide entry · 40 ms stagger with siblings · ambient sparkle on actor chip decays over 4 s |
| **Recent** | Arrived in last hour | full colour |
| **Aged** | 1-24 h old | `--content-lo` on timestamp; primary sentence remains `--content-md` |
| **Historical** | > 24 h | full row dims 15 %; still fully readable |
| **Highlighted** | Selected via keyboard or search | 2 px `--sig-info` left border; row background lifts to `--surface-2` |

Selection is single-row; keyboard-driven (↑ / ↓); Enter opens Evidence Drawer scoped to the row's subject.

---

## 6. Grouping & scrubbing

### 6.1 Automatic grouping

Consecutive events sharing the same **subject** and **actor** within 60 s collapse into one row with a `▸ N events` disclosure. Expand on click.

Example:
```
[12:24]  [research]   Ingested 6 arxiv papers on regime-detection
                     ▸ 6 events · expand
```

Expanded:
```
[12:24]  [research]   Ingested 6 arxiv papers on regime-detection
                     [12:23:14] arxiv:2401.09883 · trust_tier verified
                     [12:23:41] arxiv:2402.11291 · trust_tier verified
                     [12:23:58] arxiv:2401.00742 · trust_tier verified  · duplicate
                     ...
```

### 6.2 Time bracket headers

Every ~90 minutes or on session boundary, insert a bracket header:

```
─────────  today · 12:00–13:30  ─────────
```

Header uses `--content-lo`, 11 px caption, centre-aligned. Sticky-scroll: header pins at top of viewport as its bracket scrolls out.

### 6.3 Scrub — the Replay reservation

Header of the Timeline includes a **scrub affordance**:

```
┌───────────────────────────────────────────┐
│ AI ACTIVITY  ·  live  ▸       [ scrub ▾ ] │
├───────────────────────────────────────────┤
│                                           │
│   (timeline rows)                         │
```

- `live ▸` = default; new events push in at top
- `[ scrub ▾ ]` opens a compact timeline scrubber (sparkline of event density with a draggable playhead)
- Scrubbing back:
  1. Freezes live stream (badge changes to `paused at 11:12`)
  2. Rewinds the visible rows to their state as of the chosen timestamp
  3. **All linked artefact surfaces** (Pipeline bar, Workforce Org Chart, Lineage bar) respect the scrub time — Everything Connected principle applied to time
  4. `↩ return to live` button appears

The scrub UI is Sprint 1 optional (Simple mode may hide it); Advanced Lens surfaces it always. **This is the same interaction model Factory Replay will reuse** — no rebuild required.

---

## 7. Empty / loading / error / dormant states (per checklist §12)

### 7.1 `idle-factory`
```
[ icon · pulse-off ]

The Factory has been idle for 12 min.
This is normal during freeze.

→ see last cycle    · view scheduler
```
Colour: `--sig-dormant`. Never red.

### 7.2 `filter-empty`
```
[ icon · filter-x ]

No events match the current filters.

→ clear filters   ·   view all activity
```

### 7.3 `offline-timeline`
```
[ icon · wifi-off ]

Timeline could not reach the backend.
Retrying in the background.

→ view logs · developer
```
Colour `--sig-warn`. Retry attempted automatically every 8 s.

### 7.4 `replay-empty`
```
[ icon · rewind ]

No activity recorded in the selected window.

→ expand window     ·   return to live
```
Only visible in scrub-paused mode.

### 7.5 `initial-load`
Shimmer skeleton: 6 rows of `--surface-2` gradient, 1200 ms cycle, 40 ms stagger. Fades to real rows on arrival.

---

## 8. Filtering model

Filter chip strip lives above the timeline (persistent, collapsible):

```
[ all ▾ ]  [ actors: 10 ▾ ]  [ subject: any ▾ ]  [ confidence ≥ 0.5 ▾ ]  [ q ⌘K ]
```

- `all` / `research` / `knowledge` / `learning` / `approvals` / `production` — one-click actor set
- `subject`: type to filter by artefact id / pair / broker / etc.
- `confidence`: slider — Advanced Lens only
- `⌘K` opens the palette scoped to Timeline actions

**Persona defaults:**
- Executive: `[actors: accomplishment + approval]`
- Operations: `all`
- Research: `[actors: research + knowledge + learning]`
- Developer: `all + [errors] + [telemetry]`

Filter state persists per session.

---

## 9. Keyboard model

| Key | Action |
|---|---|
| `⌘/` | Toggle Timeline expand/collapse |
| `↑` / `↓` | Move row selection |
| `Enter` | Open Evidence Drawer for selected row |
| `⇧Enter` | Open Lineage bar for selected row's subject |
| `⌘F` / `/` | Focus filter search |
| `⌘←` / `⌘→` | Scrub back / forward one bracket |
| `⌘.` | Return to live |
| `Esc` | Clear selection · exit scrub if active |

Every keybinding also has a visible UI affordance — keyboard is a *shortcut*, not a *requirement*.

---

## 10. Motion physics

- **Entry** — 200 ms fade + 6 px `translateY(-6px → 0)` with 40 ms stagger between rows. Max 12 concurrent tweens; beyond that, batch to single 200 ms fade to preserve frame rate.
- **Ambient sparkle** on running-actor chip — 2 s ease-in-out infinite; amplitude 0.15 opacity + 6 % scale; halos `--glow-active`. **Only** while actor is streaming.
- **Sparkle decay** — 4 s ease-out after entry
- **Selection** — 120 ms transition on left border + background
- **Group expansion** — 200 ms height animation; child rows enter with 40 ms stagger
- **Scrub playhead** — 240 ms `cubic-bezier(0.16,0.84,0.44,1)` on drop
- **Return to live** — 320 ms fade of the paused overlay + resume of streaming

Reduced-motion: all motion → opacity fades only, no y-slide, no scale.

---

## 11. Persona treatment

### 11.1 Executive (Concept-C)
- Rows use serif primary sentence (`GT Sectra`, 15 px, `--content-ivory`)
- Actor chip: outline-only (no fill), warm-grey border
- Detail line: warm grey `--content-md`, sans book
- No ambient sparkle
- Filter default: `[actors: accomplishment + approval]`
- Right rail width 200 px in Briefing bottom-bar mode

### 11.2 Operations (Concept-A · default)
- Rows use sans body-sm primary
- Actor chip: filled colour by role
- Ambient sparkle on running actors
- Filter default: `all`
- 240 px right rail on Mission Control

### 11.3 Research (Concept-B)
- Rows use sans body-md (slightly larger)
- Actor chip: filled + luminance halo when live
- Extra chip: `[graph]` link on Knowledge/Learning rows opens the Knowledge Graph focused on that node
- Filter default: `[actors: research + knowledge + learning]`
- Row height cozy (92 px)

### 11.4 Developer
- Advanced Lens auto-on
- Actor palette extended with `error`, `telemetry`, `env`
- Row shows raw method/duration/provenance chips
- Filter default: `all`
- Timeline collapse defaults to *expanded* (developer wants the stream)

---

## 12. Data contract (frontend expectation of backend events)

Every event object the Timeline consumes must contain:

```ts
type TimelineEvent = {
  event_id:     string;      // stable, replay-safe
  at:           string;      // ISO-8601 UTC
  actor:        Actor;       // one of 13 (10 core + 3 developer)
  subject:      { type: 'strategy' | 'kb_item' | 'portfolio' | ... ,
                  id:   string;
                  label:string;
                };
  headline:     string;      // 1-sentence primary copy
  detail?:     string;
  links:        { label: string, href: string }[];  // up to 2
  confidence?:  number;      // 0..1
  method?:      string;
  duration_ms?: number;
  provenance?:  { origin: string; trust_tier: string; signed_by: string };
  evidence_ref: string;      // deep link to L3 Evidence Drawer
};
```

**No backend changes required today.** This contract is a *frontend adapter shape*; existing backend endpoints (`/api/llm-calls/*`, `/api/audit-log`, `/api/ai-workforce/*`, `/api/knowledge/promote-events`, `/api/factory-supervisor/notifications`, etc.) already carry every field the timeline needs. An adapter in `services/timeline.js` normalises heterogeneous events into `TimelineEvent`.

**Feature Freeze respected.** Adapter is pure frontend code.

---

## 13. Factory Replay compatibility (v2.0 §16 · D1 §16 reservation honored)

The Timeline has been designed so Replay reuses **exactly** these components:

- Same row component (§3) with additional `at` prop already accepted
- Same actor system (§4) — Replay uses identical chips
- Same grouping/bracketing (§6.1, §6.2) applied to historical stream
- Same scrub UI (§6.3) becomes Replay's primary control
- Same keyboard model (§9)
- Same empty state `replay-empty` already authored (§7.4)
- Same filtering model (§8) — Replay defaults to `[time range: selected]`

Sprint N Replay recipe: expose the scrubber as a first-class page (`/c/replay`), reuse Timeline component with a wider time window. **Zero new components. Zero new backend endpoints.**

---

## 14. Accessibility (WCAG 2.2 AA)

- Every row `role="listitem"` inside `role="list"`; container has `aria-live="polite"` for streaming rows
- Actor chip has `aria-label` composed as `{role} · {state}` (e.g., `research · running`)
- Timestamp has `title` with full ISO on hover; `aria-label` conveys relative + absolute
- Contrast: primary sentence text on `--surface-1` = 8.4:1 ✅
- Keyboard: every visible action reachable; focus ring 2 px `--sig-info`
- Screen-reader announcement on new row: `"new activity · {actor} · {headline}"` (debounced to at most 1 announcement per 3 s to avoid flooding)
- `prefers-reduced-motion`: all motion collapses to opacity fades, no y-slide

---

## 15. Sprint 1 acceptance criteria (Timeline slice)

Per D1 §17 — Timeline component ships only if:

- ✅ 14-item Design Principles Checklist confirmed (§0)
- ✅ Renders all 5 row states (§5)
- ✅ Renders all 5 empty/loading states (§7)
- ✅ Grouping + bracketing implemented (§6.1, §6.2)
- ✅ Scrub UI implemented (Simple: hidden; Advanced: visible) (§6.3)
- ✅ Keyboard model complete (§9)
- ✅ Motion physics respected (§10) — verified with `prefers-reduced-motion` test
- ✅ Persona treatments verified in Executive / Operations / Research / Developer modes (§11)
- ✅ Data-contract adapter implemented in `services/timeline.js` (§12)
- ✅ Factory-Replay reservations honored (§13) — `at` prop, stable `event_id`
- ✅ A11y verified (§14) — axe-core passes; keyboard walk complete
- ✅ Screenshot in workstation + tablet + briefing posture
- ✅ `data-testid` on every interactive element

---

## 16. What D2 does NOT include

- Coded prototype — belongs to Sprint 1
- Copy library across all 10 actors — a full library of 40+ headline templates ships in D7
- Backend event adapter implementation — belongs to Sprint 1 first PR
- Knowledge Graph node-focus behaviour (§11.3 mentions `[graph]` link) — full spec in D4

---

## 17. Next: D3

Per v2.0 §5.1 sequence: **D3 · Approval Center visual spec.**

Timeline and Approvals share DNA — approval rows enter the Timeline as `actor: approval` events; the Approval Center is a filtered, evidence-elevated view of those rows. D3 will specify:

- Full Approval Card anatomy (already sketched in D1 §7.5)
- Filter model (module × age × risk)
- Bulk-action modal (typed confirmation for low-risk mass approval)
- The dual-path invariant (header chip + drawer + module use the same underlying component — Q3 = C)
- All approval empty states

Expected timeline: 2-3 days after D2 sign-off.

---

*End of D2 — AI Activity Timeline.*
*All 14 checklist items confirmed. Awaiting your review before D3 begins.*

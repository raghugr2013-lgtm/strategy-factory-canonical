# D1 — Mission Control Visual Benchmark

> The visual codification of Concept D (50 % Mission Control · 35 % AI Intelligence · 15 % Executive Luxury) for every surface in Strategy Factory.
> Governs Sprint 1 and every subsequent frontend deliverable.
> Layered on Design Bible v1.0 + v2.0 delta. Immutable rules from those documents carry forward.
> Prepared 2026-07-20.

---

## 1. Three principles (adopted 2026-07-20)

Above the six operator questions and the five-layer IA sit three new principles that govern *how* every surface behaves:

### 1.1 Invisible Luxury
Luxury comes from **craftsmanship**, not decoration. The operator should notice how *effortless* the product feels — never how *flashy*. Every motion, every colour, every micro-interaction must earn its place. When in doubt, remove.

### 1.2 Everything Is Connected
Every artefact — strategy, knowledge item, execution observation, learning event, approval, portfolio position — carries its **complete lineage**. Nothing exists in isolation. Every card links back through the 8-stage pipeline to its ancestry and forward to its descendants.

### 1.3 Progressive Disclosure
**Simple mode stays clean.** Advanced mode reveals depth *in place* — same layouts, more chips, more detail, more optional panels — never a wholly new destination. Diagnostics is a lens, not a place (v2.0 §6.2 Q2=B).

---

## 2. Persona-domain visual mapping

Concept D is not applied uniformly. Each surface leans toward the concept that fits its purpose. All three concepts share tokens (spacing, motion budget, signal ceiling, six questions) — the difference is *emphasis*.

| Domain | Persona | Concept lean | Landing surface | Density |
|---|---|---|---|---|
| Daily Briefing | Executive | **C · Luxury** dominant | `/c/briefing` | Cinema |
| Mission Control | Operations | **A · Mission Control** dominant | `/c/mission` (default) | Compact |
| Execution / Prop Firm | Operations | **A** dominant | `/c/execution`, `/c/propfirm` | Compact |
| Governance / Approvals | Operations + Governance | **A** dominant | `/c/approvals`, `/c/governance` | Compact |
| Research Workspace | Research | **B · AI Intelligence** dominant | `/c/research` | Compact |
| Knowledge / Learning | Research | **B** dominant | `/c/knowledge`, `/c/learning` | Compact |
| AI Workforce / Copilot | All | **B** dominant | right rail + `/c/factory/workforce` | Cozy |
| Management / Reports | Executive | **C** dominant | `/c/reports` | Cozy |

**Rule:** the shell chrome (LeftRail, TopTabBar, StatusRail, ⌘K) is **always Concept A** — the operator's tool must feel consistent under every module.

---

## 3. Final palette (Concept D merged)

### 3.1 Surfaces

```
--surface-0        #06090d      near-black anchor (A · slightly warm)
--surface-1        #0d1218      panels
--surface-2        #151b23      elevated panels
--surface-3        #1d242e      dropdowns / modals / palette
--stroke-1         #212832      subtle dividers
--stroke-2         #2d3744      active stroke / focus base
--stroke-hover     #3a4656      hover stroke
```

### 3.2 Content

```
--content-hi       #eef2f7      primary content (A)
--content-ivory    #f5eede      hero metric text (C · reserved for Briefing / Executive)
--content-md       #a4afbc      body
--content-lo       #566172      captions
--content-inv      #06090d      text on light accent
```

### 3.3 Signals (6-hue ceiling · immutable)

```
--sig-ok           #3ddc84      pass / healthy / nominal
--sig-warn         #f0b429      needs evidence / degraded
--sig-crit         #ff5b5b      failed / alert
--sig-advisory     #8b8ffb      advisory / info-only
--sig-info         #4ea1f3      active / live feed
--sig-dormant      #566172      deliberately off / flag-gated
```

### 3.4 Ambient luminance (B · used ONLY on active workers + running graphics)

```
--glow-neural      rgba(139, 143, 251, 0.14)     violet halo, subtle
--glow-active      rgba(78, 161, 243, 0.10)      sky halo, subtle
--glow-warn        rgba(240, 180, 41, 0.10)      amber halo
```

Rule: glow renders only when a subsystem is **actively running**. Never as decoration. Never on idle cards. Never on Concept-C surfaces.

### 3.5 Editorial accents (C · reserved)

```
--accent-gold      #b8935f      hero rule lines on Daily Briefing only
--accent-gold-mute #63513a      supporting warm-grey
```

### 3.6 Chart palette (8-hue · Concept-D biased)

Order matters — first chart series uses index 0, second uses 1, etc:

```
c0 = --sig-info      #4ea1f3     primary series
c1 = --sig-advisory  #8b8ffb     secondary (B bias)
c2 = --sig-ok        #3ddc84     positive
c3 = --sig-warn      #f0b429     warning
c4 = --sig-crit      #ff5b5b     negative
c5 =                 #5ecab5     teal
c6 =                 #d17bff     magenta (rare)
c7 = --accent-gold   #b8935f     editorial series (Concept C surfaces)
```

---

## 4. Typography system

### 4.1 Families

- **Mono:** `Berkeley Mono` primary; `JetBrains Mono` fallback. Used for: metrics, IDs, timestamps, chip letters, code, tabular numeric.
- **Sans display:** `Neue Haas Grotesk Display` primary; `Manrope` fallback. Used for: metric heroes on B-leaning surfaces, module titles.
- **Sans body:** `Neue Haas Grotesk Text` primary; `Manrope` fallback. Used for: narrative copy, activity rows, tooltips.
- **Serif (Concept-C only):** `GT Sectra` primary; `Playfair Display` fallback. Used exclusively for: Daily Briefing headings, Reports/Presentations hero titles.

**Ban:** Inter. Roboto. Arial. System sans.

### 4.2 Scale

| Token | Size (rem / px) | Line-h | Family | Weight | Casing | Concept |
|---|---|---|---|---|---|---|
| `--font-caption` | 0.6875 · 11 | 1.4 | Mono | 500 | UPPERCASE spaced | A/B |
| `--font-body-sm` | 0.8125 · 13 | 1.5 | Sans body | 400 | Sentence | All |
| `--font-body` | 0.9375 · 15 | 1.55 | Sans body | 400 | Sentence | All |
| `--font-body-md` | 1.0625 · 17 | 1.5 | Sans body | 400 | Sentence | B/C |
| `--font-metric-sm` | 1.125 · 18 | 1.2 | Mono | 500 | Tabular | A |
| `--font-metric` | 1.75 · 28 | 1.1 | Mono | 500 | Tabular | A |
| `--font-metric-lg` | 2.5 · 40 | 1.0 | Sans display | 400 | Tabular | B (Mission Control heroes) |
| `--font-metric-hero` | 3.0 · 48 | 1.0 | Sans display | 300 (light) | Tabular | C (Daily Briefing hero) |
| `--font-h3` | 1.125 · 18 | 1.3 | Sans display | 500 | Sentence | A/B |
| `--font-h2` | 1.375 · 22 | 1.3 | Sans display | 500 | Sentence | A/B |
| `--font-h1` | 1.75 · 28 | 1.25 | Sans display | 500 | Sentence | A/B |
| `--font-h1-serif` | 2.0 · 32 | 1.15 | Serif | 400 | Sentence | C only |

### 4.3 Numeric rules

- `font-variant-numeric: tabular-nums` on every numeric container.
- Percentages 1 dp default (`91.4 %`), 0 dp on sparkline labels.
- Currency `$1,234` on L1; `$1,234.56` on L3.
- Timestamps mono; relative on L1 (`4 h ago`) · absolute on L3 (`2026-07-20 09:14:58 UTC`).
- Delta: `▲ 2.1` `▼ 0.4` — mono arrow character, colour follows sign.

---

## 5. Spacing, radius, elevation

### 5.1 Spacing (4-pt grid · v1.0 preserved)

```
--space-1  4       intra-chip
--space-2  8       chip-to-chip
--space-3  12      card padding vertical
--space-4  16      card padding horizontal
--space-5  24      section rhythm (A/B default)
--space-6  40      module top-padding, hero rhythm
--space-7  64      Concept-C only (Daily Briefing whitespace)
```

Density mode multipliers:
- Compact: 1.0× (A / Operations default)
- Cozy: 1.2× (Cards on B surfaces)
- Cinema: 1.6× (Briefing / Reports · Concept C)

### 5.2 Radius

```
--radius-1  6       chips, badges, inputs (A/C shared)
--radius-2  10      cards on A surfaces
--radius-3  14      cards on B surfaces (softer)
--radius-4  16      modals, drawers
```

### 5.3 Elevation

Depth via **1-px stroke + inner highlight**. Drop shadows forbidden except modals.

```css
.panel-a { background: var(--surface-1); border: 1px solid var(--stroke-1);
           box-shadow: inset 0 1px 0 rgba(255,255,255,0.02); }
.panel-b { background: var(--surface-1); border: 1px solid var(--stroke-1);
           box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 0 0 0 var(--glow-neural);
           transition: box-shadow 200ms; }
.panel-b.is-active { box-shadow: inset 0 1px 0 rgba(255,255,255,0.03),
                                 0 0 24px 4px var(--glow-neural); }
.panel-c { background: var(--surface-1); border: none; padding: var(--space-6) var(--space-7); }
.panel-c[data-hero] { border-top: 1px solid var(--accent-gold); padding-top: var(--space-6); }
```

---

## 6. Motion direction

### 6.1 Budget (v1.0 preserved + Concept-C slower tier)

| Tier | Duration | Curve | Use |
|---|---|---|---|
| Fast | 120 ms | `cubic-bezier(0.4, 0, 0.2, 1)` | hover, focus, chip state |
| Medium | 200 ms | same | panel expand, drawer slide, timeline entry |
| Slow | 320 ms | `cubic-bezier(0.2, 0, 0, 1)` | module crossfade, modal |
| Editorial | 400 ms | `cubic-bezier(0.16, 0.84, 0.44, 1)` | Concept-C only — hero fades, number tweens |
| Ambient | 2000 ms cycle | `ease-in-out infinite` | Concept-B — active-worker pulse (6 % scale, 15 % opacity variance) |

### 6.2 State semantics

| Change | Motion |
|---|---|
| hover | 120 ms opacity/border only; **no scale** |
| focus | 120 ms outline glow (`--stroke-2` → `--sig-info`, 2 px) |
| loading < 300 ms | none — avoid flicker |
| loading 300 ms – 2 s | shimmer skeleton, 1200 ms cycle |
| loading > 2 s | narrative text: "retrieving 3 candidates from arxiv…" |
| new timeline entry | 200 ms fade + 6 px y-slide, 40 ms stagger |
| number update (A) | instant, 120 ms flash on background `--stroke-1` |
| number update (B) | 400 ms useSpring tween — number counts |
| number update (C) | 600 ms editorial tween — number etches |
| worker running (B) | 2 s ambient pulse (subtle) |
| kill posture arm | 200 ms flash + held banner |
| approval added | ambient chip badge count fades in over 320 ms |

Reduced-motion (media query): all motion collapses to opacity fades only.

---

## 7. Component library — canonical anatomy

### 7.1 Chip

```
[● healthy]      [P passed]      [W needs evidence]      [dormant]
20 px height (compact) / 24 px (cozy) / 28 px (cinema)
radius 999 px (fully rounded — signal only) OR 6 px (label chip)
Letter chips (P W F A I) ALWAYS carry a filled colour dot AND the letter — colour-blind safety
```

### 7.2 Metric card (three variants — pick by domain per §2)

**A-variant** — Mission Control default:
```
┌──────────────────────────────────┐
│ AI WORKFORCE                     │ ← --font-caption UPPERCASE
│                                  │
│  91.4 %                          │ ← --font-metric mono
│  ▲ 2.1  vs 24h                   │ ← --font-body-sm delta
│                                  │
│  [P passed · 4 workers]          │ ← chip row
│  ⤷ view evidence                 │ ← link (always)
└──────────────────────────────────┘
padding: 16px 16px · border 1px --stroke-1 · radius 10px
```

**B-variant** — Research / Knowledge / Learning:
```
┌──────────────────────────────────┐
│  ai workforce                    │ ← lowercase body-sm
│                                  │
│    91.4 %                        │ ← --font-metric-lg sans light
│    ▲ 2.1 vs 24h                  │
│                                  │
│  4 workers online                │ ← narrative, not chip
│  → view evidence                 │
└──────────────────────────────────┘
padding: 20px 20px · border 1px --stroke-1 · radius 14px · glow when active
```

**C-variant** — Daily Briefing / Reports hero:
```
─────────  gold rule 1px  ─────────

    91.4 %                            ← --font-metric-hero (48 px light ivory)
    AI Workforce                      ← --font-h1-serif (32 px serif, --content-md)

    4 workers online. 2 idle.         ← narrative sentence

    → open workforce
```

Every metric card in every variant **links to L3 evidence.** No dead-end numbers.

### 7.3 Pipeline stage bar (Everything-Connected principle)

```
Generated ─● Validated ─● Optimized ─● Certified ─○ Knowledge stored ─○ Portfolio candidate ─○ Approved ─○ Production
```

- Filled `●` = complete · Hollow `○` = pending · Red `⨯` = failed · Grey `–` = skipped (N/A)
- Hover any stage: pop-mini with `who · when · confidence · evidence link`
- Click any stage: opens Evidence Drawer scoped to that stage
- **Appears inline** in Explorer rows, on artefact pages, on Approval Cards (relevant subset), in Timeline expansions
- Height: 24 px compact / 32 px cozy / 48 px cinema

### 7.4 Activity row (AI Activity Timeline)

```
[12:24]  [orchestrator]   Opened GPT-5 to score 3 candidates
                          confidence 0.87 · verdict: proceed to backtest
                          → view evidence  · → open pipeline
```

- Timestamp: mono, 11 px, `--content-lo`, mono-width
- Actor chip: 20 px, colour by role (see §9 activity types)
- Body: sans body-sm, 1 sentence
- Detail: sans body-sm, `--content-md`, 1 optional line
- Links: 1 primary + up to 1 secondary
- Enter animation: 200 ms fade + 6 px y-slide + 40 ms stagger
- **B surface only** — ambient sparkle chip when actor is a bot (`--sig-advisory` at 60 % alpha)

### 7.5 Approval Card (Concept-A surface, but with B evidence chips)

```
┌───────────────────────────────────────────────────────────────┐
│  [META-LEARNING]      Recommendation #47                       │
│                                                                │
│  Suggest lowering `challenge_dedup_threshold` from 0.82 →      │
│  0.78 based on last 30 d retrieval hit-rate                    │
│                                                                │
│  ── EVIDENCE ────────────────────────────────────────────────  │
│  · retrieval hit-rate: 61 % (target ≥ 70 %)                    │
│  · false-dedup incidents in last 7 d: 4                        │
│  · confidence 0.71 · trust_tier verified                       │
│                                                                │
│  ── LINEAGE (Everything-Connected) ──────────────────────────  │
│  · derived from: retrieval-audit-2026-07-14                    │
│  · affects: 12 strategies in Portfolio                         │
│  → full evidence trail                                         │
│                                                                │
│  ── RISK · low ──────────────────────────────────────────────  │
│  advisory-only path · revertible in one click · SLA < 30s      │
│                                                                │
│  [ Approve ]   [ Defer ]   [ Deny ]   [ Route to team ]        │
└───────────────────────────────────────────────────────────────┘
```

Actions layout: primary left, tertiary right. Approve button uses `--sig-ok` fill only when risk == low; otherwise outline requiring explicit modal confirmation.

### 7.6 Worker card (Concept-B — Workforce Org Chart)

```
┌────────────────────────────┐
│  research · worker-01      │  ← caption, lowercase, mono
│  ● running                 │  ← chip
│                            │
│  candidate #47             │  ← narrative
│  since 12:24 · 3.4 min     │
│                            │
│  ──── last artefact ────   │
│  strat_bb_ema_rsi_v3       │  ← mono, --content-md
│  P validated               │  ← chip
│                            │
│  → open evidence           │
└────────────────────────────┘
```

Ambient pulse when running (Concept B). Halo `--glow-active` at low intensity. Idle workers dim to `--content-lo`. Offline workers show `crit` chip and lose halo.

### 7.7 Chip glossary (used across shell)

- `●` — actively running
- `◐` — degraded / partial
- `○` — idle / dormant by design
- `⨯` — failed / offline
- `P W F A I` — legend (Passed / Needs evidence / Failed / Advisory / Info)

### 7.8 Status rail (six-chip · Mission Control footer)

```
● orch healthy   ● ingest ready   ◐ sched failover   ◐ llm no-key   ● govern governed   ● kill armed
```

Never grows past six chips. If a new subsystem is added, either merge or replace.

---

## 8. Signature graphics gallery (G1–G8 · v2.0 §3.1 codified)

| # | Graphic | Concept lean | Motion | Colour scheme |
|---|---|---|---|---|
| G1 | Workforce Org Chart | B dominant | ambient pulse on running workers; 200 ms hand-off line trace | c0/c1/c2 for divisions; halos |
| G2 | Strategy Pipeline Ribbon | A dominant | none; stage transitions animate 200 ms | signal palette (ok/warn/crit) |
| G3 | Knowledge Graph | B dominant | force-directed layout settles over 800 ms on load; luminescent edges on recent traversal | trust-tier axis (`--sig-ok/warn/crit`), node size by usage |
| G4 | Market Coverage Heatmap | A dominant | none; cell fills update instantly | greyscale ramp + `--sig-crit` for gaps |
| G5 | Execution Quality Constellation | A/B blend | 300 ms tween on new data; ambient sparkle | broker-per-hue from chart palette |
| G6 | Portfolio Risk Surface | B dominant | 400 ms transition on regen | c0-c1 gradient (violet→sky), reserved for this graphic |
| G7 | Learning Evolution Timeline | B dominant | scrubbable; playhead animates 240 ms | outcome-per-hue |
| G8 | Neural Sparkline Strip | B dominant | continuous 1200 ms line-draw cycle | one colour per subsystem, muted |

All graphics: colour-blind safe (letter/marker fallback), degrade to still-image on Briefing print, respect `prefers-reduced-motion` (motion → no motion, static composition only).

---

## 9. AI Activity Timeline — 10 activity types (v2.0 §3.1 codified)

Persistent right rail. 240 px workstation · 40 px stripe tablet · promoted to bottom bar in Briefing posture.

| Type | Icon (lucide) | Actor chip colour | Sample copy |
|---|---|---|---|
| Research | `search` | `--sig-info` | "queried arxiv for 'mean-reversion regime' · 4 hits · 2 dedup" |
| Generation | `sparkles` | `--sig-ok` | "generated strategy bb_ema_rsi_v3 · validated · score 0.71" |
| Backtesting | `bar-chart-2` | `--sig-info` | "ran 30-d walk-forward on 3 candidates · 2 passed" |
| Mutation | `git-branch` | `--sig-info` | "mutation cycle #47 opened · parent bb_ema_rsi_v2" |
| Knowledge | `book` | `--sig-advisory` | "knowledge item arxiv:2401.09883 ingested · trust_tier verified" |
| Learning | `activity` | `--sig-info` | "meta-learning proposed dedup threshold 0.78 · see approvals" |
| Portfolio | `layers` | `--sig-info` | "portfolio candidate added · risk 0.4 %" |
| Execution | `terminal` | `--sig-info` | "execution observation · EURUSD fill quality p95 1.2 pips" |
| Maintenance | `wrench` | `--sig-dormant` | "BI5 sweep completed · 0 gaps" |
| Approval | `flag` | `--sig-warn` | "approval requested · meta-learning #47" |

Every row: 1 timestamp + 1 actor chip + 1 sentence + up to 2 evidence links + optional detail line. Enter motion 200 ms fade + 6 px y-slide, 40 ms stagger.

---

## 10. Everything-Connected — the Lineage layer

Every artefact carries a **lineage bar** below its title, showing where it came from and where it flowed:

```
Strategy: bb_ema_rsi_v3
────────  origin  ──────  parent  ─────  descendants  ──────
research-worker-01     mutation of      → 2 portfolio candidates
                       bb_ema_rsi_v2    → 1 approval pending
```

- Every named entity is a link.
- Every link opens either the referenced artefact OR the Evidence Drawer scoped to the traversal.
- Lineage bar height: 32 px · always present · never hidden

**Rule of Connection:** if an artefact appears on screen without a lineage bar, that surface has failed the Everything-Connected principle. It must be authored in.

---

## 11. Progressive Disclosure — the Advanced Lens

Toggle in header: `Simple · Advanced`. Persisted per user.

Effect of switching to Advanced (module-agnostic):

| Element | Simple | Advanced |
|---|---|---|
| Metric card | value + delta + 1 chip + evidence link | + provenance chips + confidence % + confidence interval sparkline |
| Approval card | subject + recommendation + risk + 4 actions | + full evidence trail inline + affected-artefact count + rollback SLA |
| Timeline row | 1 sentence + link | + method chip (e.g., "walk-forward") + p-value + duration |
| Status rail chip | `● orch healthy` | `● orch healthy · 42 tasks · p95 84 ms` |
| Right rail | 10 activity types | + 3 diagnostic types (`errors`, `telemetry`, `env`) |
| ⌘K palette | 4 groups (navigate/run/evidence/help) | + `developer` group (5th) |

**Never a wholly new page.** Advanced is a lens, not a place (Q2 = B).

---

## 12. Personalization modes (v2.0 §2 mapped to visual)

| Mode | Landing | Density | Concept-D emphasis on default landing | Right rail |
|---|---|---|---|---|
| Executive | `/c/briefing` | Cinema | **C 60 % · A 30 % · B 10 %** — serif hero titles, gold rule, ivory metrics, no ambient motion | Timeline compact, filtered to Accomplishments + Approvals |
| Operations (default) | `/c/mission` | Compact | **A 60 % · B 30 % · C 10 %** — mono metrics, dense grid, signal-first, subtle glow on running workers | Timeline full |
| Research | `/c/research` | Compact | **B 60 % · A 30 % · C 10 %** — softer corners, glow halos, neural org chart embedded | Timeline filtered to Research + Knowledge + Learning |
| Developer | `⌘K` open | Compact | **A 70 % · diagnostics-lens on 30 %** | Timeline filtered to errors + telemetry |

Shell chrome (LeftRail / TopTabBar / StatusRail) stays Concept-A in every mode — the tool is consistent.

---

## 13. Empty / loading / error / dormant state library

### 13.1 Empty (narrative, not zeros)

Template:
```
[ icon · lucide, 32 px, --content-lo ]

No <thing> yet.
<one-sentence context>.

[ primary action ]   ·   [ secondary link ]
```

Specimens:

- **Mission Control · no approvals** — "No approvals are waiting. The Factory is operating autonomously." · `open Approval Center →` · `view timeline`
- **Research · no strategies** — "No strategies have been generated yet. Start your first research cycle." · `Run cycle` · `open Explorer`
- **Timeline · no activity in last N min** — "The Factory has been idle for the last 12 min. This is normal during freeze." · `see last cycle` · `view scheduler`
- **Workforce · all dormant** — "8 divisions ready. No worker is currently active." · `view scheduler` · `open Copilot`
- **Approvals · zero** — "You're all caught up. No recommendations require your review." · `view recent approvals`
- **Portfolio · no candidates** — "No portfolio candidates yet. Approve strategies in Research to seed the portfolio." · `open Research`
- **Knowledge · empty KB** — "The Knowledge Base is dormant until Phase C activation. See the activation plan." · `view activation plan`
- **Execution · no observations** — "No execution observations have been recorded. This is expected before broker connections are live." · `open Prop Firm`

### 13.2 Loading

| Duration | Presentation |
|---|---|
| < 300 ms | no indicator (avoid flicker) |
| 300 ms – 2 s | shimmer skeleton (surface-1 → stroke-2 gradient, 1200 ms cycle) |
| > 2 s | narrative text: `retrieving 3 candidates from arxiv …` |
| > 8 s | offer background: `still working — you can navigate away and I'll notify when done` |

### 13.3 Error (informational, never scary)

```
Something didn't reach here.
<what · why in plain English>.

[ Retry ]   [ Report ]   [ View logs · developer ]
```

Never a stack trace on L1-L3. Never a red full-screen. The error card lives *in place* of the failed content, at that content's normal size.

### 13.4 Dormant (Strategy Factory signature)

```
[ icon · shield · muted grey ]

DORMANT · Phase D not yet activated
Connector fleet is intentionally offline until the Coherent
UKIE Activation plan reaches Phase D. Backend is healthy.

→ view activation plan
```

Colour: `--sig-dormant`. **Never red. Never offer Retry.** This is not an error — it's a design invariant.

---

## 14. Chart standards

- **Grids:** subtle. 1 px `--stroke-1`. Never darker.
- **Axis marks:** short (4 px), on the outside.
- **Legends:** 11 px caption, UPPERCASE, aligned right of chart.
- **Tooltips:** 200 ms fade-in, positioned at data point, mono-numeric.
- **Baselines:** always visible for delta charts; use `--content-lo`.
- **Zero suppression:** never suppress zero on a percentage axis; always on a currency axis if numbers are large.
- **Colour usage:** first series `c0`; deltas ok/crit only; never rainbow.
- **Animation on entry:** 320 ms slow curve line-draw. Never on data update (data updates flash 120 ms only).
- **Concept-C surfaces:** no grid; axis marks only; 2 px stroke; single accent hue.

---

## 15. Notification philosophy visualisation

| Tier | Visual home | Persistence | Visual treatment |
|---|---|---|---|
| Critical | Danger ribbon + NotificationDrawer + email opt-in | Until ack | 100 % ribbon width, `--sig-crit` background, 2 s low-amplitude pulse |
| Warn | NotificationDrawer only | Auto-dismiss 24 h | `--sig-warn` chip |
| Info | AI Activity Timeline only | Rolling last 500 | narrative row, no chip alert |

**Header approvals chip is a Warn-tier signal** — badge count only, no pulse, no colour flash. Only Critical earns visual urgency.

---

## 16. Factory Replay — architectural reservation

**Reserved for later phases.** Not in Sprint 1. But architecture must not preclude it.

**Concept:** the ability to *replay the Factory's activity over a selected time range* and understand how research evolved into production.

**Reservations for D-level design:**

- The **AI Activity Timeline** stores enough state to be time-scrubbable — every entry carries a stable `event_id`, `timestamp`, `actor`, `subject`, and `evidence_ref`.
- The **Strategy Pipeline Ribbon** is capable of showing state *as of* a given timestamp (not only current state) — pipeline stage bar accepts an optional `at` parameter.
- The **Workforce Org Chart** stores a per-worker time-series of `state ∈ {running, idle, offline}` — enough to replay the org's shifts.
- The **Approval Center** stores every action with `approved_at`, `approver`, `rationale`, `outcome_at`.
- The **Lineage bar** is queryable by time — "show me the lineage as of 3 days ago".

**Not reserved (not needed for replay):**

- No new backend endpoints needed — Feature Freeze respected.
- No new URL paths for now — Replay is a *lens over existing surfaces*, not a new destination.

**Sprint N recipe (future):** a scrubber lives in the shell footer; every visible timeline row / pipeline / worker / graph respects the scrub time. All existing components already accept `at` (see reservations above). No new content — just a new time coordinate applied to existing evidence.

---

## 17. Sprint 1 visual acceptance criteria

Every Sprint-1 component ships only if:

- ✅ Uses only tokens from §3
- ✅ Uses only typography from §4
- ✅ Follows spacing/radius/elevation from §5
- ✅ Respects motion budget from §6
- ✅ Composes exclusively from §7 primitives
- ✅ Carries a lineage bar if it's an artefact (§10)
- ✅ Renders correctly in Simple *and* Advanced (§11)
- ✅ Renders correctly in every persona mode (§12) — different emphasis, same tokens
- ✅ Has authored empty / loading / error / dormant states (§13)
- ✅ Has `data-testid` on every interactive element (v1.0 §17)
- ✅ Ships with a screenshot in workstation + tablet + briefing posture

---

## 18. D1 deliverable summary

D1 defines the visual language for:

- ✅ Mission Control anatomy (§7.2, §8, §9, §12, §13)
- ✅ Typography scale (§4)
- ✅ Card system (§7.2)
- ✅ Colour system (§3)
- ✅ Signature graphics catalogue (§8)
- ✅ AI Activity Timeline row + type table (§7.4, §9)
- ✅ Strategy Pipeline Ribbon (§7.3)
- ✅ AI Workforce visual system (§7.6, §8-G1)
- ✅ Approval Center card (§7.5)
- ✅ Data visualization standards (§14)
- ✅ Motion direction (§6)
- ✅ Empty state library (§13)
- ✅ Overall look-and-feel (§1, §2, §3-§7, §12)
- ✅ Three principles adopted (§1)
- ✅ Factory Replay reserved (§16)
- ✅ Sprint 1 acceptance criteria (§17)

---

## 19. What D1 does NOT do

- No coded prototype (coming in Sprint 1 as isolated Storybook pages once approved)
- No pixel-perfect Figma mockups (Markdown + ASCII remains source of truth; if you want visual fidelity, we'll produce coded prototypes as the review medium in Sprint 1 kick-off)
- No copy library beyond §13 specimens (fuller copy library is D7)
- No motion prototypes (D5 signature-graphic gallery specifies interactions concretely; motion prototypes come in Sprint 1)

---

## 20. Next steps

**Sequence to Sprint 1:**

1. You review D1. Approve, request revisions, or reject.
2. On approval, D2–D8 (per v2.0 §5.1) proceed:
   - **D2** — AI Activity Timeline interactive spec (row physics, filtering, scrub-affordance for future Replay)
   - **D3** — Approval Center visual spec (full states + bulk-action modal)
   - **D4** — Master Bot & Workforce Org Chart spec (G1 codification)
   - **D5** — Signature-graphic gallery deep-dive (G2–G8)
   - **D6** — Personalization modes spec
   - **D7** — Empty/loading/error/dormant pattern library (extends §13)
   - **D8** — Sprint 1 detailed plan
3. Only after D8 sign-off does Sprint 1 implementation begin.

**Expected timeline:** D2–D8 ≈ 8-12 working days. Craftsmanship over speed, as instructed.

---

*End of D1 — Mission Control Visual Benchmark.*
*Awaiting your review before D2 begins.*

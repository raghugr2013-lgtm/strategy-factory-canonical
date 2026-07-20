# D0 — Visual Language Exploration

> Three premium visual directions for Strategy Factory.
> **No IA changes.** All three respect the Design Bible v1.0 + v2.0 delta.
> **No code.** Selection determines the visual identity for D1 and every subsequent deliverable.
> After you pick, we can either commit to one or fuse strongest elements into a **Concept D — Merged Language**.
> Prepared 2026-07-20 · reference lens: modern operator tools + UI/UX Pro Max principles applied to a mission-control domain.

---

## How to read this document

Each concept is presented in the same 8-slot template so you can compare like-for-like:

1. **Mood** — the emotional register
2. **References** — what you'd feel it's inspired by
3. **Palette** — surfaces + content + signals
4. **Typography** — families + treatment
5. **Card / panel treatment** — how information is contained
6. **Signature graphic character** — how graphics feel
7. **Motion character** — how the platform "breathes"
8. **Mission Control sample** — ASCII mock so we compare identical content in three languages

Then trade-offs and what each concept sacrifices.

---

## Concept A — MISSION CONTROL

*Bloomberg terminal · SpaceX flight director · CERN control room*

### 1. Mood
Operational. Awake. Dense. **The Factory is running; you are here to observe and command.** Zero wasted pixels. High contrast. Every character earns its place.

### 2. References
- Bloomberg Terminal (density, tabular numbers, colour-coded state)
- SpaceX countdown clocks + telemetry HUDs
- Rauno Freiberg's tool interfaces (Linear, Vercel dashboards)
- Nasa Deep Space Network operator consoles
- Warp terminal typography

### 3. Palette

```
--surface-0    #05070a   near-black (deeper than v1.0)
--surface-1    #0b0e13   panels
--surface-2    #131820   elevated panels
--surface-3    #1b222c   dropdowns
--stroke-1     #1f2732   dividers
--stroke-2     #2c3644   active stroke, focus rings

--content-hi   #eef2f7   headings, metric values
--content-md   #a4afbc   body
--content-lo   #566172   captions

signals ────────────────────────────────
--sig-ok       #3ddc84   green (unchanged)
--sig-warn     #f0b429   amber
--sig-crit     #ff5b5b   red
--sig-advisory #8b8ffb   lilac
--sig-info     #4ea1f3   blue (accent bias)
--sig-dormant  #566172   grey
```

Character: **cool blue-black**, high contrast, saturated signals.

### 4. Typography

- **Display / metrics / headings:** `Berkeley Mono` (or `JetBrains Mono` fallback) — everything numeric is mono.
- **Body:** `Inter Display` (yes, exceptional case — Inter is defensible in the mission-control idiom).
- **Casing:** `UPPERCASE spaced` labels, `lowercase` chip text, `Sentence case` section titles.
- **Metric hero:** 32-40 px mono, tabular-nums, `--content-hi`.
- **Numeric everywhere:** all figures are tabular; alignment is sacred.

### 5. Card / panel treatment

- Rectangular. Sharp corners (radius 4-6 px maximum).
- 1 px stroke border, no drop shadows.
- Header row with UPPERCASE label + optional trailing chip.
- Inner content grid: label-column left · value-column right.
- Hover: stroke transitions `--stroke-1 → --stroke-2` in 120 ms.

### 6. Signature graphic character

- Grid-based. Everything snaps.
- Sparklines are 1-px stroke, no fill, mono line only.
- Constellation / scatter graphs use `+` markers, not dots.
- No gradients. No glow. No neon.
- Grid lines subtle: 1 px `--stroke-1`.

### 7. Motion character

- **Sparse.** Movement communicates state change only.
- Fast: 120 ms · Medium: 200 ms · Slow: 320 ms (v1.0 budget preserved).
- New timeline entries: 200 ms fade-in from `--stroke-2` → `--surface-1` (subtle "flash").
- Ambient: none. The screen sits still until something happens.

### 8. Mission Control sample

```
┌─────────────────────────────────────────────────────────────────────┐
│ DANGER ┃ Master Bot compile failed · signing error · 1h ago  [VIEW]│
├─────────────────────────────────────────────────────────────────────┤
│ STRATEGY FACTORY   BUILD 30.4    ⌘K              PROD  UP 4d 02:11 │
├─────────────────────────────────────────────────────────────────────┤
│ MISSION CONTROL                                                     │
├───────────────────────────────┬─────────────────────────────────────┤
│ HEALTH                        │ ATTENTION            [3]            │
│ ● orch    healthy             │ ● critical  Backend health unreach. │
│ ● ingest  ready               │ ● warn      Master Bot compile fail │
│ ◐ sched   dormant             │ ● advisory  1 KB item awaiting rev. │
│ ◐ llm     no key                                                    │
│ ● govern  governed            │                                     │
│ ● kill    armed               │                                     │
├───────────────────────────────┼─────────────────────────────────────┤
│ AI WORKFORCE                  │ PENDING APPROVALS    [4]            │
│                               │ META-LEARNING · 3                   │
│      no key                   │ FACTORY-EVAL   · 1                  │
│      configure provider       │ GOVERNANCE     · 0                  │
├───────────────────────────────┼─────────────────────────────────────┤
│ ACCOMPLISHMENTS · LAST 24 H                                         │
│ 0 STRATEGIES  0 MUTATIONS  0 VALIDATIONS  0 PROMOTES  0 KB  0 EXEC │
├─────────────────────────────────────────────────────────────────────┤
│ NEURAL SPARKLINE STRIP                                              │
│ orch  ────────────────────────────────────────────────────────────  │
│ ingest ───────────────────────────────────────────────────────────  │
│ sched ────────────────────────────────────────────────────────────  │
├─────────────────────────────────────────────────────────────────────┤
│ ● orch healthy  ● ingest ready  ◐ sched dormant  ◐ llm no key  ...  │
└─────────────────────────────────────────────────────────────────────┘
```

### Trade-offs
- **Best at:** density, operator familiarity, decisiveness, keyboard-first feel
- **Sacrifices:** approachability, first-impression wow, softer emotional moments
- **Best for:** operations personas, on-shift workflows, incident triage

---

## Concept B — AI INTELLIGENCE

*Anthropic / OpenAI research aesthetic · neural graphics · living data*

### 1. Mood
Alive. Thinking. **The platform is an intelligent organism.** Softer edges, subtle luminance, palpable "processing" feel. Beautiful *because* it reveals cognition.

### 2. References
- Anthropic Claude UI (subtle warm accents on near-black)
- OpenAI o1 research surfaces (thin luminance strokes)
- Perplexity Pro (thoughtful information layout)
- Vercel v0 (elegant density, subtle motion)
- Framer sites (motion as meaning)
- Origin OS / Rewind OS (living dashboards)

### 3. Palette

```
--surface-0    #0a0a0c   near-black warm
--surface-1    #14141a   panels warm-shifted
--surface-2    #1c1c26   elevated
--surface-3    #262632   dropdowns
--stroke-1     #24242e   dividers
--stroke-2     #363648   active stroke, focus glow

--content-hi   #f4f4f7   soft white
--content-md   #b0b0bd
--content-lo   #6e6e80

signals ────────────────────────────────
--sig-ok       #6ee7b7   mint (softer green)
--sig-warn     #fbbf6e   amber (warmer)
--sig-crit     #ff7676   coral (less aggressive)
--sig-advisory #a78bfa   violet (accent bias)
--sig-info     #7dd3fc   sky
--sig-dormant  #6e6e80   grey

luminance accents (Concept B unique) ───
--glow-neural  rgba(167,139,250,0.15)   subtle violet halo
--glow-active  rgba(125,211,252,0.10)   subtle sky halo
```

Character: **warm-shifted black**, violet-and-sky accent axis, softer signals, subtle luminance halos.

### 4. Typography

- **Display / metrics:** `Neue Haas Grotesk Display` (or `Manrope` fallback) — sans, tight leading. Numeric still tabular.
- **Mono (secondary, for code / IDs / timestamps):** `Berkeley Mono`.
- **Body:** `Neue Haas Grotesk Text` (or `Manrope`).
- Metric hero: 40 px sans, `--content-hi`, tight leading (1.0).
- Section titles: Sentence case, 22 px.
- Character: not-mono-first (unlike A). Numeric emphasis via *weight + size*, not monospace.

### 5. Card / panel treatment

- Softer corners (radius 10-16 px).
- **1 px inner stroke + very subtle outer glow** on hover (`--glow-neural`, 0.15 opacity, 8 px radius).
- Cards feel semi-transparent (background `--surface-1` at 90 % opacity over `--surface-0`).
- Empty cards get a subtle radial gradient centred on the meaning-icon.

### 6. Signature graphic character

- Line-based, curved.
- Sparklines have a 0.5-alpha fill under the line (subtle wash).
- Neural org chart: soft-edged nodes with `--glow-active` halos when active worker is running.
- Knowledge graph: force-directed with **luminescent edges** — brighter when recently traversed.
- Motion: **ambient pulsing** on running components (2 s cycle, 6 % scale, 15 % opacity variance).
- Colour: violet + sky as primary chart hues; keep the 8-hue palette but bias to those two.

### 7. Motion character

- **Persistent, calm.** The screen breathes.
- Ambient pulse on running workers (subtle — never distracting).
- Timeline entries: 320 ms slide-in from below + fade-in, staggered 40 ms.
- KPI number updates: 400 ms `useSpring`-style tween (Framer Motion) — the number *counts* to its new value.
- Hover reveals: 200 ms crossfade + luminance halo.

### 8. Mission Control sample

```
┌─────────────────────────────────────────────────────────────────────┐
│ ⚠ Master Bot compile failed · signing error · 1h ago     [ open → ]│
├─────────────────────────────────────────────────────────────────────┤
│ Strategy Factory · v30.4 · PROD                    admin@coinnike ▾ │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Mission Control                                                     │
├──────────────────────────────┬──────────────────────────────────────┤
│  Health                      │  Attention                  ● 3      │
│  ◉ orchestrator     healthy  │                                      │
│  ◉ ingestion        ready    │  critical                            │
│  ○ scheduler        dormant  │  Backend health unreachable          │
│  ○ llm              no key   │  network · 12:24 · inspect →         │
│  ◉ governance       ok       │                                      │
├──────────────────────────────┼──────────────────────────────────────┤
│  AI Workforce                │  Pending Approvals          4 open   │
│  ┌──────────┬──────────────┐ │                                      │
│  │  8       │  0 running   │ │  meta-learning · 3                   │
│  │  divisi. │  0 idle      │ │  factory-eval  · 1                   │
│  │          │  8 dormant   │ │  governance    · 0                   │
│  └──────────┴──────────────┘ │                                      │
├──────────────────────────────┴──────────────────────────────────────┤
│  Accomplishments · last 24 h                                        │
│                                                                     │
│  · · · · · ·                                                        │
│  strategies  mutations  validations  promotes  KB items  execution  │
│      0            0            0          0        0         0      │
│                                                                     │
│  ~~~~~~~~~~~~~~~~~~~~~~ neural pulse strip ~~~~~~~~~~~~~~~~~~~~~~~ │
├─────────────────────────────────────────────────────────────────────┤
│ ● orch  ● ingest  ○ sched  ○ llm  ● govern  ● kill                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Trade-offs
- **Best at:** feeling alive, first-impression premium, communicating "AI thinking"
- **Sacrifices:** raw density (fewer numbers per screen than A), slightly slower feel
- **Best for:** research personas, executive first-impressions, product demos

---

## Concept C — EXECUTIVE LUXURY

*Private-banking dashboard · Palantir Gotham · Bloomberg Portfolio*

### 1. Mood
Calm. Confident. **You have arrived; the work is under control.** Whitespace as luxury. Restraint as sophistication. Bespoke.

### 2. References
- Palantir Gotham (elegance under density)
- Stripe Sigma dashboards (refined data density)
- Robinhood Gold / Wealthfront (financial calm)
- Herman Miller product pages (typographic authority)
- The Financial Times digital edition
- Braun industrial design principles

### 3. Palette

```
--surface-0    #0d1015   deep charcoal (warmer than A, cooler than B)
--surface-1    #171b21   panels
--surface-2    #1f242c   elevated
--surface-3    #262d37   dropdowns
--stroke-1     #232830   dividers
--stroke-2     #333b46   active

--content-hi   #f5eede   IVORY (Concept C unique — off-white, not pure white)
--content-md   #a89f8a   warm grey
--content-lo   #625a48   muted warm

signals ────────────────────────────────
--sig-ok       #99b98a   sage
--sig-warn     #c9a355   brass
--sig-crit     #c76a5d   terracotta (not red)
--sig-advisory #7d8fa1   slate
--sig-info     #a89f8a   warm grey (info = subdued)
--sig-dormant  #625a48   warm mute

--accent-gold  #b8935f   editorial rule lines, dividers on hero KPIs
```

Character: **warm charcoal + ivory content + earthy signals**. No pure white, no pure black, no saturated colours. Editorial gold accent for rare hierarchy moments.

### 4. Typography

- **Display / headings:** `GT Sectra` or `Söhne Breit` (serif + geometric sans authority pairing) — headings only.
- **Metrics:** `Söhne Mono` — tabular, but weight is *light* (300), not medium.
- **Body:** `Söhne` (sans, book weight).
- Metric hero: 48 px, light weight, ivory. Numbers feel etched, not shouted.
- Section titles: Serif (`GT Sectra`) — a deliberate luxury signature.
- Uppercase only for the smallest labels (10-11 px, letter-spaced +0.08 em).

### 5. Card / panel treatment

- Radius: `--radius-1 6 px` — sharp but not brutal.
- **No stroke by default.** Panels defined by background contrast only (`--surface-1` on `--surface-0`).
- Divider: 1 px `--stroke-1` only where genuinely needed.
- Hero metric card gets a single 1 px `--accent-gold` top border — a rare rule line.
- Cards float in negative space (2× v1.0 padding).

### 6. Signature graphic character

- Editorial. Slow. Considered.
- Line charts: 2 px stroke, ivory, no fill.
- Grids sparse — often no visible grid, axis marks only.
- Neural org chart: hollow circles + thin lines, no glow.
- Colour used sparingly — a single accent hue per graphic, warm.
- Numbers dominate; visuals support.

### 7. Motion character

- **Rare and measured.**
- Fast: 120 ms · Medium: 240 ms (slightly slower than A/B — 20 ms of luxury) · Slow: 400 ms.
- No ambient motion. No pulse. Screen stays still.
- Enter animations: 240 ms fade only. Never slide, never scale.
- Number transitions: 600 ms slow tween — deliberate, weighted.

### 8. Mission Control sample

```
┌─────────────────────────────────────────────────────────────────────┐
│  ⌇  Master Bot compile failed  ·  1h ago                        →   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│    STRATEGY  FACTORY                        PROD  ·  4d  02:11      │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│    Mission Control                                                  │
│                                                                     │
│    ─────────────────────────  gold-rule  ────────────────────────   │
│                                                                     │
│                                                                     │
│    HEALTH                          ATTENTION                        │
│                                                                     │
│    orchestrator      healthy       critical   Backend unreachable   │
│    ingestion         ready         advisory   1 KB item awaiting    │
│    scheduler         dormant                                         │
│    llm               no key                                          │
│                                                                     │
│                                                                     │
│    WHAT AI ACCOMPLISHED  ·  LAST 24 HOURS                           │
│                                                                     │
│         0                0                0                0        │
│    strategies      mutations      validations      promotes         │
│                                                                     │
│                                                                     │
│    PENDING APPROVALS                                                │
│                                                                     │
│    4 open  ·  3 meta-learning  ·  1 factory-eval                    │
│                                                                     │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│   ● orch    ● ingest    ○ sched    ○ llm    ● govern    ● kill      │
└─────────────────────────────────────────────────────────────────────┘
```

### Trade-offs
- **Best at:** stakeholder demos, executive briefings, "this platform is expensive and considered", trust-building
- **Sacrifices:** density, immediate operational speed, mono-numeric shorthand
- **Best for:** Executive persona landing, quarterly reviews, external presentations

---

## Head-to-head comparison

| Attribute | A · Mission Control | B · AI Intelligence | C · Executive Luxury |
|---|---|---|---|
| Feel | Awake | Alive | Composed |
| Density | Maximum | High | Considered |
| Numeric emphasis | Mono-heavy | Sans + tabular | Light-weight tabular |
| Palette temperature | Cool | Warm | Warm |
| Corners | Sharp (4-6 px) | Soft (10-16 px) | Sharp (6 px) |
| Ambient motion | None | Persistent pulse | None |
| Signal saturation | High | Softened | Earthy |
| Whitespace | Minimal | Moderate | Generous |
| First-impression wow | Medium | High | Highest (for exec) |
| Operator productivity | Highest | High | Medium |
| Demo appeal | Medium | High | Highest |
| Distinctive vs the market | High (feels like a real tool) | High (feels like a research lab) | Highest (feels like private banking) |

---

## My design recommendation

**Concept D — Merged Language:** take **A's density + B's AI-alive character + C's editorial restraint.** Specifically:

- **Foundation:** Concept A palette (cool-shifted black + high-contrast signals) — the operator-first anchor
- **Overlay:** Concept B ambient motion (subtle pulse on active workers, luminance halos on running graphics, breathing sparkline strip) — proves the AI is alive
- **Selective luxury:** Concept C typographic authority on Mission Control HERO metrics only (48 px light sans over a subtle gold rule) — the arrival moment
- **Everything else:** Concept A defaults — mono metrics, dense cards, sharp corners, keyboard-first

This gives the platform three registers, each fit for purpose:
- **Executive persona lands on Daily Briefing** → Concept C treatment dominates (calm, sparse, luxurious). *This is the first-impression surface for stakeholders.*
- **Operations persona lands on Mission Control** → Concept A dominates with B's ambient pulse on active workers. *The tool.*
- **Research persona lands on Research Workspace** → Concept B dominates (neural graphics, knowledge graph animation, thought-in-progress feel). *The lab.*

Persona-aware landing (Q1 = B) makes this natural: each persona meets the platform in the visual register that fits them best, without fragmenting the design language — because all three registers share tokens (spacing, motion budget, signal ceiling, six operator questions).

---

## Three questions to unlock D1

**Q-A.** Do you accept Concept D (merged) as the direction? Or would you prefer a single concept (A / B / C)?

**Q-B.** If Concept D: what proportion? My default recommendation: 60 % A · 25 % B · 15 % C. But you may want more C (executive polish) or more B (AI showmanship).

**Q-C.** Any concept you want to *rule out* entirely so I don't waste D1 effort blending it?

---

## What's NOT in D0

- No code (as instructed)
- No new IA (locked in Bible v1.0 + v2.0)
- No selection made — the choice is yours
- No mockup images — ASCII only; visual mockups arrive in D1 once the language is chosen
- No motion prototypes — belong in D1 as coded storybook examples once concept is locked

---

*End of D0.*
*Awaiting your answers to Q-A / Q-B / Q-C before D1 begins.*

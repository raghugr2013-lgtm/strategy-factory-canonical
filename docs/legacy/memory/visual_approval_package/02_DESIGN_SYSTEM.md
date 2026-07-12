# 02 · Design System (Binance/Bybit dark trading terminal)

> Values extracted verbatim from old 1-vCPU `src/index.css` + `src/styles/theme.js`.
> Confirmed against operator brief: "Binance information density, Bybit styling quality, dark theme, dense tables, compact KPI cards, professional trading workstation feel."

---

## 1 · Color tokens (DARK — sole canvas, no light parity)

Per operator decision: **dark mode is the only operator-facing theme.** All light-theme code paths are removed. References for institutional quality: Binance, Bybit, TradingView, Quantower, cTrader.

CSS variables exposed as RGB triplets so Tailwind utilities support opacity (`bg-surface-card/50`).

```css
:root {
  /* Base surfaces — deep institutional palette */
  --surface-deep:     #060809;          /* darkest — page rails */
  --surface-main:     #0B0E11;          /* page bg */
  --surface-card:     #15191E;          /* sections / containers */
  --surface-elevated: #1E2329;          /* raised inner blocks */
  --surface-raised:   #2B3139;          /* table headers · selected states */
  --surface-sunken:   #080C11;          /* inputs · logs · wells */

  /* Binance gold — restrained, never glare */
  --accent-primary:       #F0B90B;
  --accent-primary-dim:   #CA9A08;
  --accent-primary-soft:  rgba(240, 185, 11, 0.10);
  --accent-primary-line:  rgba(240, 185, 11, 0.45);

  /* Secondary accents */
  --accent-cyan:    #03A9F4;          /* future / informational (used for cTrader-future slots) */
  --accent-purple:  #8B5CF6;          /* AI / Copilot / advisory */

  /* Borders — 4 levels of separation */
  --border-hairline: #1A1F25;
  --border-subtle:   #2B3139;
  --border-muted:    #374151;
  --border-strong:   #4B5563;

  /* Text — 5 levels of hierarchy */
  --text-display:   #FFFFFF;            /* hero numerals · page titles */
  --text-primary:   #EAECEF;            /* body */
  --text-secondary: #848E9C;            /* labels */
  --text-muted:     #5E6673;            /* captions */
  --text-faint:     #404750;            /* disabled */

  /* Semantic */
  --color-success:      #0ECB81;        /* all profit / OK */
  --color-success-soft: rgba(14, 203, 129, 0.10);
  --color-danger:       #F6465D;        /* all loss / fail */
  --color-danger-soft:  rgba(246, 70, 93, 0.10);
  --color-warning:      #F0B90B;
  --color-info:         #03A9F4;

  /* Elevation system (replaces ad-hoc box-shadow) */
  --shadow-elev-1: 0 1px 0 rgba(255,255,255,0.025) inset, 0 1px 2px rgba(0,0,0,0.4);
  --shadow-elev-2: 0 1px 0 rgba(255,255,255,0.025) inset, 0 4px 12px rgba(0,0,0,0.35);
  --shadow-elev-3: 0 1px 0 rgba(255,255,255,0.03) inset, 0 12px 32px -8px rgba(0,0,0,0.55);
  --shadow-gold-glow: 0 0 0 1px rgba(240,185,11,0.32), 0 8px 24px -8px rgba(240,185,11,0.32);

  --radius-sm: 4px;
  --radius:    8px;
  --radius-lg: 12px;

  color-scheme: dark;
}
```

### ❌ Light theme — removed

The previous `[data-theme="light"]` block is **deleted from the design system.** The `ThemeToggle` button in the topbar is **removed** (it becomes a no-op control and is excised in M0). DEV-RC1 blockers RC1-1 (light contrast cluster) and RC1-2 (overlay light-mode bleed) **evaporate** — they cannot fail if there is no light theme.

Operator value of this constraint: the design team can spend 100 % of motion / contrast / depth effort on a single canvas, matching the institutional density of Binance / Bybit / TradingView / Quantower / cTrader.

---

## 2 · Typography

| Role | Family | Source |
|---|---|---|
| Body / UI | `Inter` (400/500/600/700) | Google Fonts |
| Mono / data / log lines | `JetBrains Mono` (400/500/600/700) | Google Fonts |
| Display / headings | `Manrope` (500/600/700/800) | Google Fonts |

```css
body {
  font-family: 'Inter', sans-serif;
  letter-spacing: -0.005em;
  font-feature-settings: 'cv11', 'ss01', 'tnum';  /* always tabular numerals */
}
.font-mono, table, td, th { font-variant-numeric: tabular-nums; }
```

Sizes (utility opt-in):

| Class | Size | Use |
|---|---|---|
| `.metric-primary` | **18 px / 700** | KPI hero numbers (e.g. equity, balance, win-rate) |
| `.metric-secondary` | 14 px / 500 / `text-secondary` | KPI sub-values |
| `.metric-label` | 12 px / 500 / uppercase / `text-muted` / `tracking-[0.08em]` | KPI label above number |
| `.section-label` | 10 px / mono / uppercase / `tracking-[0.14em]` | tiny section dividers |
| h1 | 18 px / 700 / `-0.012em` |  |
| h2/h3 | 16 px / 600 / `-0.008em` |  |
| Tab buttons | 12 px (`text-xs`) / 500 |  |
| Brand | 18 px / 700 (`text-lg font-bold`) |  |
| Right-cluster controls | 10 px / mono |  |

---

## 3 · Spacing & layout

* **Max content width:** `1600px` (`max-w-[1600px] mx-auto`)
* **Page gutter:** `p-4 md:p-6`
* **Topbar height:** `h-14` (56 px) sticky, `backdrop-blur-md`, `border-b`
* **Section gap (default):** `gap-4 md:gap-6` (16 → 24 px)
* **Card padding (default):** `p-4` (16 px); KPI tiles `p-3` (12 px)
* **Section radius:** `--radius: 10px` (`rounded-md` 6 px = chips; `rounded-xl` 12 px = cards)

### 3.1 Density mode (`[data-density="compact"]`)

All paddings shrink by **~40 %**, gaps shrink to `0.2–0.5 rem`, font scales down (table cells 0.72 rem, h1 16 px, h2 14 px). Toggled by `DensityToggle` button in topbar. The mode is the **defining feature of the trading-terminal feel** and is preserved verbatim from old `index.css` LL 519–581.

---

## 4 · Component primitives (utility classes)

All defined in old `src/index.css` `@layer components`. Names + intent only — visual spec follows.

| Class | What it is | Usage |
|---|---|---|
| `.card-premium` | The dark gray card with subtle inset highlight + bottom drop-shadow. **`rounded-xl border border-border-subtle bg-surface-card`** | Every section container |
| `.card-premium-hover` | Adds hover→`border-border-muted` + `bg-surface-elevated` | Interactive cards |
| `.btn-primary` | **Binance gold** filled button. `bg-accent-primary text-#0B0E11 border-accent-primary/60`. On hover: `filter:brightness(1.08)` + `0 6px 20px -6px rgba(F0B90B,0.35)` glow. | Primary CTAs |
| `.btn-primary-lg` | + `text-sm px-5 py-2.5` | Major CTAs |
| `.btn-secondary` | Violet `#6C5CE7` tint variant | Secondary CTAs |
| `.btn-ghost` | Transparent border, `text-secondary`, hover→bg-elevated | Toolbar buttons |
| `.section-label` | 10 px mono uppercase muted label | Section subtitles |
| `.log-line` | mono row, 11 px, surface-sunken background, subtle border | Log streams |
| `.log-line-success` / `-warn` / `-error` | semantic-tinted variants |  |
| `.step-chip` / `.step-chip-active` / `.step-chip-done` | The 3-step Execution flow chips | ExecutionDashboard top strip |
| `.empty-state` | Centered card with circle icon + title + sub | Empty tables / lists |
| `.alloc-bar` | Tiny gradient progress bar — width via `--alloc` CSS var (0..1) | Portfolio allocation tables |
| `.pl-profit` / `.pl-loss` | Tabular semantic colors | All PnL columns |

---

## 5 · Tables (the heart of the workstation)

Defined globally in old `index.css` LL 374–432 — **applied universally** without per-component edits. This is what gives the workstation its Bybit/Binance density.

```css
thead tr  { position: sticky; top: 0; z-index: 2; }
thead th  {
  background: rgb(var(--surface-elevated));
  color: rgb(var(--text-secondary));
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.68rem;   /* ~11px */
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgb(var(--border-subtle));
}
tbody td  {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid rgb(var(--border-subtle) / 0.6);
  font-size: 0.78rem;   /* ~12.5px */
}
tbody tr  { transition: background-color 120ms ease; }
tbody tr:hover  { background: rgba(240,185,11,0.06); }  /* gold wash */
tbody tr:nth-child(even) { background: rgba(255,255,255,0.015); }

/* Numbers always right-aligned + tabular */
td.num, td.number, td.numeric, th.num, th.number { text-align: right; font-variant-numeric: tabular-nums; }
tbody td:last-child.font-mono { text-align: right; }
```

**Result:** rows ~28 px tall, hover with subtle gold wash, sticky headers when scrolled, alternating-row striping at `rgba(255,255,255,0.015)`. Identical visual feel to Binance trade history and Bybit positions table.

---

## 6 · Topbar anatomy (locked layout)

Sourced from old `App.js` LL 207–273.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ⚡ AI Strategy Factory  [v10]   Dashboard  Execution  Auto Factory  Monitoring  Paper Exec  Trade…  More ▾ │
│                                                                          [Trader] [Theme] [Density] [admin@strategy…] [Sign out] ● Online │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Height: 56 px (`h-14`), `bg-surface-card/90 backdrop-blur-md border-b border-border-subtle`, sticky-top.
- LEFT: brand `⚡ AI Strategy Factory` + version chip `v10`. Brand never shrinks.
- CENTER: `.navbar-menu` — flex-1, min-width:0, scrolls horizontally when too narrow.
- RIGHT: `.navbar-right` — flex-shrink:0. Order: Clear-session (when N>0) · `TraderModeButton` · `ThemeToggle` · `DensityToggle` · auth badge · Sign out · Online dot.

**Active tab style:** `bg-accent-primary-soft text-accent-primary border border-accent-primary/30`.
**Inactive:** `text-zinc-400 hover:text-zinc-200 hover:bg-surface-elevated border-transparent`.
**Tab font:** `text-xs font-medium rounded-md px-2 lg:px-2.5 xl:px-3 py-1.5`.

---

## 7 · Status-rail (bottom of viewport — NEW)

Carried over from the current command-shell — the only NEW chrome element added to the old layout. Pinned to the bottom edge (`fixed bottom-0 inset-x-0 h-7`).

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│ orch:idle  ingest:ok  sched:on  llm:off  gov:ok  kill: OK    │  ⌘K  ⌘J  ⌘⌥N  ⌘.  ? │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

- Height: 28 px, `bg-surface-sunken/95 backdrop-blur border-t border-border-subtle text-[10px] font-mono`.
- LEFT: 6 system dots from `/api/orchestrator/heartbeat` + `/api/monitoring/status`.
- RIGHT: shortcut hints for the 5 global overlays (see §05).

---

## 8 · Iconography

* **Phosphor Icons** (`@phosphor-icons/react`) — used in old codebase for brand mark, NavMoreMenu (`CaretDown`, `Check`), AuthGate (`SignOut`, `UserCircle`).
* **Lucide React** — used in old phase9 ExecutionDashboard (`Factory`, `Briefcase`, `Play`, `ArrowRight`).

Both kept. Phosphor for chrome/badges (weight="bold"|"fill"), Lucide for inline content icons (16/18px).

---

## 9 · Motion

* Standard transitions: `transition-colors duration-150` on hover / active.
* Card hover lift: `transform: translateY(-2px)` + `box-shadow` step-up, `200ms ease`. **Disabled in compact-density mode** (focus over flourish).
* Number changes: no animation — instant snap (trader expectation).
* Page transitions: none (single SPA mounts).

---

## 10 · Accessibility constants (preserved from current)

* `:focus-visible` outline: `2px solid rgb(var(--accent-primary) / 0.65)` + `outline-offset: 2px`.
* All modals: `role="dialog"` + `aria-modal="true"` + `aria-labelledby`.
* Focus trap on Command Palette, Notification Drawer, Copilot, Inspector.
* `aria-live="polite"` on notification region.
* All tab buttons have `data-testid="nav-tab-<id>"`.
* `prefers-reduced-motion` honoured (current `asf-u4-a11y.css`).

— End of DESIGN SYSTEM —

# Strategy Factory — UI/UX Master Design Specification v1.0

**Document status:** CANONICAL. Every future UI implementation must conform to this specification. Deviations require an approved design update.

**Product identity:** Mission Control for an Autonomous AI Hedge Fund.

**Design mantra:** *Living Intelligence.* The system is always thinking; the interface should convey that ambient, purposeful activity without demanding attention.

---

## Section 1 — Vision & Design Philosophy

Strategy Factory operates continuously and autonomously: research, strategy generation, backtesting, portfolio adaptation, market observation, execution, and closed learning all happen without human intervention. The operator's role shifts from doing to **supervising** — approving, intervening, and steering.

The UI must reflect that shift. It is not a tool the operator drives; it is a control room that shows the operator what the factory is thinking, why, and with what confidence.

Design principles, in priority order:

1. **Truth before decoration.** Every visual element must carry information. If a chart, gradient, or animation does not tell the operator something they need to know, it does not ship.
2. **Progressive disclosure.** Surface headline signals first; expand only on operator intent. No dashboard should be exhausting on first glance.
3. **Explainability everywhere.** Every automatic decision the factory makes must be one click away from a full audit chain (Phase F outcome events → market intelligence → execution attribution → knowledge). No black boxes.
4. **Performance is a design feature.** All motion is GPU-accelerated (transform / opacity only); no layout thrash; no unnecessary re-renders; sub-16ms interaction budget.
5. **Ambient over decorative.** Motion communicates system state — a heart-beat, a data stream, a settling animation on a new signal. Motion is never gratuitous.
6. **Institutional but alive.** The aesthetic pulls from Bloomberg's information density, Linear's typographic precision, Figma's spatial calm, Apple's material craft, and Binance's professional data density — but the composite feel is Strategy Factory's alone.
7. **Backend independence.** The frontend consumes stable API contracts. Presentation may evolve; contracts stay backwards compatible.

---

## Section 2 — Product Identity

* **Product name:** Strategy Factory
* **Codename:** *Atlas* — the mission-control layer that holds up the factory beneath it.
* **Voice:** Precise, calm, confident. No exclamation marks, no marketing language, no anthropomorphic AI cuteness.
* **Iconography:** Structural — nodes, edges, layers, flows. Never mascots.
* **Wordmark:** *STRATEGY FACTORY* in an institutional monospaced display (JetBrains Mono or IBM Plex Mono).
* **Signature motif:** The **Factory Pipeline** — a horizontal 7-stage flow (Research → Generate → Backtest → Validate → Rank → Deploy → Learn) that appears throughout the product as a visual metaphor and status indicator.

---

## Section 3 — Information Architecture

Top-level regions, ordered by operator frequency of use:

1. **Mission Control** — one-screen overview (default landing)
2. **Factory Pipeline** — live view of the 7-stage automated flow
3. **Trading Brain** — Phase F decisions, weight matrix, allocation shifts
4. **Market Intelligence** — Phase G observations + structural changes
5. **Execution Intelligence** — Phase H orders, fills, positions, attribution
6. **Portfolio** — Phase D allocations, health, rebuild history
7. **Strategy Explorer** — searchable strategy catalog
8. **AI Workforce** — provider health, budgets, throughput
9. **Knowledge Graph** — cross-signal explainability navigator
10. **Analytics & Reports** — historical performance, factory ROI
11. **System Health** — orchestrator, capacity, providers, integrations
12. **Administration** — users, roles, feature flags, keys
13. **Timeline** — global chronological event stream
14. **Search Everywhere** — command-palette style universal search

Each region is a "workspace" — a dedicated URL space with its own sub-navigation, breadcrumbs, and persistent side rail.

Every workspace surface is deep-linkable and shareable. Every table row and every chart marker is a link.

---

## Section 4 — Navigation System

### 4.1 Primary chrome

* **Global top bar** (48px):
  * Left: Strategy Factory wordmark + workspace breadcrumb
  * Center: **Search Everywhere** input (⌘K trigger)
  * Right: notification bell, AI assistant toggle, operator avatar
* **Left rail** (56px collapsed / 220px expanded):
  * Icon column of the 14 workspaces
  * Hover pops out a labelled preview; click activates
  * Bottom of rail: environment indicator (Preview / Staging / VPS), factory-heartbeat pulse
* **Workspace sub-nav** (variable): appears as second-level chrome inside each workspace
* **Right rail** (opt-in, 320px): context panel — AI Assistant, notifications timeline, activity ticker

### 4.2 Command palette (⌘K)

* Fuzzy search across every entity: strategies, decisions, orders, fills, positions, structural changes, knowledge nodes.
* Command actions: "Pause strategy X", "Refresh market intelligence for EURUSD", "Open outcome event", "Jump to timeline range".
* Palette is keyboard-first; every entry has a shortcut hint on hover.

### 4.3 Breadcrumb + back-stack

Every workspace maintains a per-session back-stack. `⌘[` and `⌘]` navigate. Breadcrumbs are clickable and include the entity ID (short-form) so operators can share a URL that resolves to the same state.

### 4.4 Progressive disclosure levels

Each workspace has three depth levels:

1. **Overview** — one screen, no scrolling, headline signals only
2. **Focus** — one entity (strategy, order, position, change), full detail, all cross-links
3. **Deep dive** — audit chain / knowledge graph, timeline correlated, raw journal

---

## Section 5 — Mission Control Dashboard

The default landing page. One screen. No scroll.

### 5.1 Zones

```
┌───────────────────────────────────────────────────────────────┐
│  HERO METRICS                                                 │
│  ▸ Portfolio value  ▸ 24h realised  ▸ Live drawdown           │
│  ▸ Active strategies ▸ Master Bot health ▸ AI budget spent    │
├───────────────────────────────────────────────────────────────┤
│  FACTORY PIPELINE (live 7-stage flow)                         │
│  Research → Generate → Backtest → Validate → Rank → Deploy → Learn│
├──────────────────────────┬────────────────────────────────────┤
│  RECENT DECISIONS        │  MARKET SNAPSHOT                   │
│  (brain + market + risk) │  (regime, confidence, changes)     │
├──────────────────────────┼────────────────────────────────────┤
│  EXECUTION FEED          │  KNOWLEDGE PULSE                   │
│  (fills, health, latency)│  (new lessons, top movers)         │
└──────────────────────────┴────────────────────────────────────┘
```

### 5.2 Hero metric cards

* Value + delta + sparkline + subtle heartbeat when data is fresh
* Long-press (or click) → drills into the source workspace
* Colour is data-driven only: green/red for direction, amber for attention
* Never uses colour for aesthetic

### 5.3 Recent Decisions rail

Chronological list of the last 20 factory decisions, each rendered as one row:

`[icon] 12:42:03  BRAIN  strategy_ab12  PAUSE  "regime shift → mean_reversion"  ▸ explain`

* Icon indicates category (brain / market / execution / risk / knowledge)
* Reason column is a compact human-readable string, always sourced from the outcome event
* "explain" opens the Focus view for that decision with full audit chain

---

## Section 6 — Factory Pipeline

The signature module. A horizontal flow of 7 stages:

`Research → Generate → Backtest → Validate → Rank → Deploy → Learn`

### 6.1 Visual grammar

* Each stage is a rounded card with:
  * **Live throughput** (rows/min or decisions/min)
  * **Queue depth** (in-flight items)
  * **Health pip** (green / amber / red)
  * **Sparkline** (throughput last 60 min)
* Connections between stages are **live streamlines** — thin animated lines whose speed encodes throughput
* Hovering a stage reveals in-flight items; clicking opens the stage detail

### 6.2 Stage detail

Each stage's detail view exposes:

* Current queue with per-item ETA
* Historical throughput chart (24h)
* Latest decisions in this stage
* Configuration (env-driven; read-only unless admin)
* Orchestrator context: capacity headroom, priority, dependency status

### 6.3 Animation

* Streamlines flow left-to-right at a speed proportional to throughput
* Under peak load, streamlines glow slightly (opacity, not colour)
* Under stall (queue depth > threshold), streamlines pulse amber
* Under fault, streamlines dashed red and the stage card shows a compact error surface

---

## Section 7 — Dashboard Modules

Reusable modules that recur across workspaces:

| Module | Purpose |
|---|---|
| `MetricCard` | Single KPI + delta + sparkline + drill-in |
| `DecisionRow` | One outcome_events row rendered inline |
| `PipelineFragment` | Compact 3-stage strip usable in sidebars |
| `WeightMatrix` | Phase F brain weights heatmap |
| `RegimePanel` | Current regime + confidence + next transition |
| `HealthPip` | 8×8 dot indicator with 5 states |
| `TimelineStrip` | Horizontal event ribbon over a time range |
| `ExplainChain` | Vertical audit chain viewer |
| `KnowledgeNode` | One node from the knowledge graph, hover-expands |
| `AttributionCard` | brain_decision ↔ fill ↔ realised_pnl summary |

All modules share the design tokens defined in Section 28.

---

## Section 8 — AI Workforce UI

Renders provider health, budgets, throughput, and current work assignments.

* **Provider grid**: one card per provider (Claude Sonnet, Gemini Nano Banana, GPT-5.2, etc.) with status, latency p95, spend today, spend month, budget remaining
* **Work queue**: active jobs with model / provider / cost estimate / ETA
* **Failure ledger**: last N provider failures with retry outcome
* **Budget forecast**: monthly burn extrapolated from current rate; amber when >80% of budget

Actions available: pause a provider, reroute traffic, adjust budget ceiling (admin only).

---

## Section 9 — Strategy Explorer

Searchable, filterable catalog of every strategy the factory has ever generated.

### 9.1 List view

* Virtualised infinite scroll (10k+ rows)
* Columns: hash (short), style, current status, confidence, PF (recent / long), max DD, allocation, last decision
* Filter chips: status (active/paused/retired), style, pair, session, regime fit
* Sort: score_now, PF, DD, age

### 9.2 Focus view

* Header: hash, style, human-readable label, status pill
* Left column: allocation history, decision history (brain + portfolio)
* Right column: current signals, market context, recent attributions
* Bottom: outcome events timeline + knowledge links

---

## Section 10 — Trading Brain Workspace

Central view for Phase F decisions.

### 10.1 Overview

* Master Bot composition (Tier 1/2/3 strategies)
* Latest brain decisions (last 100)
* Score-now vs score-next scatterplot
* Weight matrix heatmap (Phase F scoring components)

### 10.2 Decision Focus

* Full BrainSignals dump (all Phase G MI fields visible when opted in)
* Score breakdown per component (regime_fit, confidence, recent_pf, ...)
* Action rationale + evidence dict rendered as key-value pairs
* Cross-links: portfolio impact, market context, execution outcome

### 10.3 Weight editor (admin)

* Sliders for every `BRAIN_W_*` env
* "Preview effect" mode: replays last 24h of decisions with the new weights (uses `MemoryLedgerBackend` for zero-risk sandbox)
* Commit requires admin + reason field

---

## Section 11 — Market Intelligence Workspace

Phase G observatory.

### 11.1 Overview

* Universe grid: one row per (pair, timeframe) with:
  * market_confidence, regime_confidence, opportunity_score, risk_environment
  * Active structural changes count
* World-clock strip showing session (asian/london/ny/overlap)

### 11.2 Pair Focus

* Rolling MarketState windows (24h/7d/30d)
* 8-observer breakdown (trend duration, volatility dynamics, breakout quality, reversal, session, liquidity, correlation, style)
* Structural changes timeline for this pair
* Correlation heatmap vs the rest of the universe

### 11.3 Structural Changes Timeline

* Global chronological list of every `structural_change` event
* Filter by change type (volatility_regime_shift, correlation_breakdown, etc.)
* Each row expands to show the evidence + method + delta

---

## Section 12 — Execution Intelligence Workspace

Phase H control room.

### 12.1 Overview

* Broker Health pill (colour + score_5m/60m/24h)
* Open positions table (pair, side, qty, entry, unrealised, live P&L bar)
* Live fill ticker (rightmost strip, auto-scroll)
* Today's execution quality summary (score, latency p95, slippage p95)

### 12.2 Orders Focus

Full order lifecycle view for one `request_id`:

* State timeline: PENDING → SENT → WORKING → PARTIAL* → FILLED / REJECTED / CANCELLED
* Every fill listed with price, qty, slippage, latency
* Linked brain_decision (audit chain)
* Journal excerpts

### 12.3 Broker Health Focus

* Rolling 5m / 1h / 24h score charts
* Disconnect history
* Reject / requote breakdown
* Session refresh log (OAuth cadence)
* Kill switch state + last operator action

### 12.4 Execution Attribution

Per-strategy view:

* `predicted_score` vs `realised_execution_score` scatterplot
* `delta_predicted_realised` histogram
* Realised PnL vs slippage correlation
* Top over-/under-performing brain decisions

### 12.5 Risk Recommendations panel

Q3-safe: **recommend-only**. Every risk breach shows the recommended action (pause / reduce / halt_new_opens) with a manual **Apply** button. Emergency liquidation is never automatic; the button explicitly says "Cancel working orders" and requires operator confirmation.

---

## Section 13 — Portfolio Workspace

Phase D adaptive portfolio.

* Current allocation pie + Tier-1/2/3 badges
* Health metrics (Sharpe, DD, correlation)
* Rebuild history (why + what changed)
* Manual overrides (admin) with audit trail

---

## Section 14 — Knowledge Graph

Interactive graph of decisions, outcomes, and lessons.

* Nodes: strategies, decisions, structural changes, market states, fills, attributions
* Edges: causal / temporal / correlational
* Force-directed layout by default; timeline layout on toggle
* Click any node to open its Focus view
* Filter: by workspace, date range, entity type
* Uses WebGL rendering (regl / pixi) for performance at 10k+ nodes

---

## Section 15 — Analytics & Reports

* Factory ROI: research spend vs realised alpha
* AI spend efficiency: cost per successful decision
* Phase-by-phase health scorecards
* Downloadable PDF/CSV reports (via a report worker; operator-triggered)

---

## Section 16 — System Health

* Orchestrator task grid: every registered task, cadence, last run, next run, health
* Capacity dashboard: CPU / RAM headroom, task backlog, AI provider throughput
* Integrations: cTrader connection, MongoDB, provider status
* Container / process supervisor state (read-only mirror of supervisorctl status)

---

## Section 17 — Administration

* Users & roles (RBAC)
* Feature flags (every `*_ENABLED` env, with descriptions + toggle + audit log)
* Secrets vault (rotate API keys)
* Backup / restore controls
* Rollback drill runbook links

---

## Section 18 — Search Everywhere (⌘K)

Universal command palette.

* Backend: unified search endpoint that fans out to strategies, decisions, orders, positions, structural changes, knowledge nodes, and API-config
* Ranking: exact ID > entity type match > fuzzy semantic
* Actions inline: hitting Enter on a strategy row shows quick actions (Pause, Boost, Explain, Open focus)
* Recent + Pinned sections at the top of the palette

---

## Section 19 — AI Assistant

Optional right-rail companion. Consumes the platform's provider abstraction (no Emergent LLM key).

* Grounded on the local knowledge graph + outcome events; will not hallucinate about strategy IDs
* Explain mode: "Why did strategy X get paused?" → returns audit chain narrative
* Diagnostic mode: "What's dragging Sharpe today?" → structured report with cross-links
* Never takes destructive actions; recommendations only
* Voice input opt-in (Phase III)

---

## Section 20 — Notifications

* Persistent bell in top bar; count badge for unread
* Three severity tiers: **info** (ambient), **attention** (soft chime), **critical** (persistent modal)
* Every notification links to the source outcome_event
* Do-not-disturb schedule (per operator)
* Digest email/SMS (opt-in)

---

## Section 21 — Timeline

Global chronological event ribbon.

* Zoomable (minute → day → week)
* Filter by category (brain / market / execution / risk / knowledge)
* Selection surfaces a Focus view without leaving the timeline
* Export slice as PDF for compliance

---

## Section 22 — Motion Design System

### 22.1 Duration & easing

| Interaction | Duration | Easing |
|---|---|---|
| Micro (hover, focus) | 120ms | cubic-bezier(.2,0,0,1) |
| Standard (panel, modal) | 220ms | cubic-bezier(.32,.72,0,1) |
| Emphasized (page transition) | 380ms | cubic-bezier(.16,1,.3,1) |
| Ambient (heartbeat, streamline) | 1800-2400ms | linear or sinusoidal |

### 22.2 Choreography rules

* At most 3 simultaneous motion vectors on a single screen
* Layout-affecting animation is never chained with fill/opacity animation
* Prefer `transform` + `opacity` — never animate `width`, `height`, `top`, `left`
* All motion respects `prefers-reduced-motion`; ambient motion collapses to a static state

### 22.3 Signature motions

* **Heartbeat** — one-pulse opacity ripple every 2.4s on live indicators
* **Streamline** — 60fps GPU-driven translateX loop over pipeline edges
* **Settle** — new signals slide-in with translateY(4px) → 0 + opacity 0 → 1 over 180ms
* **Explain expand** — Focus view opens with a shared-element transform (row → detail card)

---

## Section 23 — Micro-interactions

* Hover states are ≤120ms opacity/scale, never colour changes on data-carrying elements
* Focus rings are 2px, 4px offset, brand-accent — visible in both themes
* Clickable rows show a soft left-border on hover (2px accent)
* Table cells with copy-to-clipboard action reveal a subtle icon on hover
* Every destructive action requires a 500ms hold-to-confirm (mobile-safe)

---

## Section 24 — Sound Design

Opt-in. Off by default. Persisted per operator.

| Event | Sound | Duration |
|---|---|---|
| Fill received | Soft "click" | 80ms |
| Structural change detected | Muted bell | 220ms |
| Risk breach recommendation | Two-tone chime | 320ms |
| Kill switch engaged | Persistent low tone (once) | 600ms |
| Factory milestone (e.g. new master bot) | Warm swell | 480ms |

All sounds mastered to -18 LUFS. No sound is triggered more than once per 3s (throttled).

---

## Section 25 — Color System

### 25.1 Base palette (dark theme — default)

* `--bg-0` `#08090B` — canvas
* `--bg-1` `#0F1114` — surface
* `--bg-2` `#181B21` — elevated surface
* `--bg-3` `#242830` — hover / active surface
* `--stroke-1` `#2E333C` — hairline
* `--stroke-2` `#3A404A` — divider
* `--text-1` `#E6EAF2` — primary
* `--text-2` `#A5AEC0` — secondary
* `--text-3` `#6C7382` — tertiary
* `--accent-1` `#5FE6C1` — brand mint (data-neutral positive)
* `--accent-2` `#7C9EFF` — brand blue (info)
* `--pos` `#3DDC97` — positive
* `--neg` `#F0616A` — negative
* `--warn` `#F3B25E` — attention

### 25.2 Light theme

Symmetric inversion of `--bg-*` and `--text-*`, warmer accents (`--accent-1` shifts to `#00A883`), same data colours.

### 25.3 Rules

* Data colours never appear on chrome
* Chrome colours never appear on data
* Gradients are limited to ambient effects (aurora background, streamline glow) — never on buttons

---

## Section 26 — Typography

* **Display** — IBM Plex Sans (700, 600) — headlines only
* **Body** — Inter (500, 400) — everything else
* **Mono** — JetBrains Mono (500, 400) — IDs, code, numbers with dense precision

Scale (rem, 4-point grid):

| Token | Size | Line-height |
|---|---|---|
| `--fs-xs` | 0.75 | 1.2 |
| `--fs-sm` | 0.875 | 1.35 |
| `--fs-md` | 1.00 | 1.5 |
| `--fs-lg` | 1.125 | 1.5 |
| `--fs-xl` | 1.5 | 1.4 |
| `--fs-2xl` | 2.0 | 1.3 |
| `--fs-3xl` | 2.75 | 1.2 |

Numeric columns use mono variants of Inter (`font-variant-numeric: tabular-nums`) for perfect column alignment.

---

## Section 27 — Component Library

Component roster (all built on Shadcn primitives, wrapped in Strategy Factory design tokens):

* Layout: `AppShell`, `WorkspaceHeader`, `SideRail`, `RightRail`, `PageGrid`
* Data display: `MetricCard`, `SparkChart`, `AreaChart`, `HeatmapMatrix`, `WeightMatrix`, `TimelineStrip`, `PipelineFlow`
* Tables: `DataTable` (virtualised), `DecisionTable`, `OrderTable`, `AttributionTable`
* Forms: `Slider`, `Toggle`, `Select`, `NumberInput`, `HoldToConfirm`
* Feedback: `Toast`, `Notification`, `HealthPip`, `StatusPill`, `AuditChain`
* Overlays: `Modal`, `Drawer`, `CommandPalette`, `Tooltip`
* Charts: `RegimeChart`, `CorrelationHeatmap`, `PnLChart`, `ExecutionQualityChart`
* Special: `KnowledgeGraphCanvas` (WebGL), `AmbientStreamline`, `Heartbeat`

Every component:
* Ships a Storybook entry
* Has a design-token audit (no raw colour / spacing values)
* Has `data-testid` per interactive element (project rule)

---

## Section 28 — Design Tokens

Token file at `frontend/src/design/tokens.css` (future):

```
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-pill: 999px;
  --shadow-1: 0 1px 2px rgba(0,0,0,.24);
  --shadow-2: 0 6px 24px rgba(0,0,0,.32);
  --z-nav: 40;
  --z-overlay: 60;
  --z-modal: 80;
  --z-toast: 100;
  --dur-micro: 120ms;
  --dur-std: 220ms;
  --dur-emph: 380ms;
  --ease-std: cubic-bezier(.32,.72,0,1);
  --ease-emph: cubic-bezier(.16,1,.3,1);
}
```

All colours and typography from Sections 25–26 are also tokens.

---

## Section 29 — Accessibility

* WCAG 2.2 AA baseline; AAA where feasible
* All interactive elements keyboard-reachable; visible focus rings
* Every icon has an accessible label
* Colour is never the sole information carrier (icons + text back every semantic colour)
* Respects `prefers-reduced-motion` — collapses ambient motion to static
* Supports screen readers via aria-live regions on decision feed and notifications
* Font size preferences honoured (via rem-based scale)
* All charts have a text-mode alternative

---

## Section 30 — Performance Budget

| Metric | Budget |
|---|---|
| Time to first contentful paint | ≤1.0s (VPS local network) |
| Time to interactive | ≤1.8s |
| Interaction latency (p95) | ≤80ms |
| Frame rate on ambient motion | ≥55fps |
| JS bundle initial | ≤180 KB gz |
| CSS initial | ≤40 KB gz |
| WebSocket subscription overhead | ≤2% CPU on M-class laptop |
| Memory ceiling on Mission Control | ≤120 MB heap |

Enforced via Lighthouse CI gates + bundle-size CI gates.

---

## Section 31 — Desktop Layout

* Optimised for 1440px+ displays; scales up to 4K
* Two-column layout on Focus views, three-column on Mission Control
* Sticky top bar + left rail; content area scrolls independently
* Right rail is optional and remembered per operator

---

## Section 32 — Tablet Layout

* Optimised for 1024×1366 (iPad Pro landscape)
* Left rail auto-collapses to icons; expands on hover / long-press
* Right rail collapses into a slide-in drawer
* Touch targets ≥44×44

---

## Section 33 — Mobile Monitoring Mode

Mobile is **read-only** in v1.0. Operators can monitor, be notified, and review — but cannot submit or edit.

* Single-column stacked layout
* Bottom-tab primary nav (Mission / Pipeline / Execution / Notifications / Search)
* Hero metrics as a swipeable carousel
* Timeline is the primary content area
* Push notifications integrated with the browser Notification API (opt-in)

Write actions redirect to the desktop app with a QR-code deep link.

---

## Section 34 — Future Enhancements

Deferred to post-v1.0 UI:

* **Live paper-trading sandbox** — bring `PaperBrokerAdapter` into the UI so operators can dry-run strategy changes visually
* **Storyboard mode** — chronological rewind of a chosen decision, replaying the audit chain step-by-step with visual annotations
* **Multi-monitor arrangement** — persistable window layouts across displays
* **Voice input for AI assistant** — via Whisper on-device
* **Public API playground** — Swagger-like explorer bound to the deployed backend
* **Compliance export bundle** — one click produces a complete audit archive for a chosen date range
* **Theme designer** — accessible custom themes (subject to brand guardrails)
* **Real-time collaboration** — multi-operator presence markers, comment threads on decisions
* **Mobile write mode** — biometric-gated approvals for critical actions (kill switch, admin toggles)

---

## Appendix A — UI Implementation Roadmap

Once backend Phase H completes and the operator authorises frontend work, implementation proceeds module-by-module against this spec, in this order:

1. AppShell + tokens + typography + top bar + left rail
2. Mission Control
3. Factory Pipeline
4. Execution Intelligence workspace
5. Trading Brain workspace
6. Market Intelligence workspace
7. Portfolio workspace
8. Strategy Explorer
9. Timeline
10. Knowledge Graph
11. AI Workforce, Analytics, System Health, Administration
12. Search Everywhere, AI Assistant, Notifications
13. Mobile monitoring mode
14. Accessibility hardening + performance CI gates

Each module has its own PR-scoped design review against this spec.

---

## Appendix B — Change control

Any deviation from this specification must be documented in `docs/UI_UX_DESIGN_UPDATES/` with:

* Problem statement
* Proposed change (with sketches / screenshots)
* Impact on token / component / motion system
* Operator sign-off

Silent divergence is not permitted. This document is the frontend's constitution.


---

## Appendix C — Phase I Meta-Learning module (2026-02-16 addendum)

### Purpose

Give the operator a dedicated workspace to inspect the meta-learning
engine's evaluations, ranked recommendations, applied overrides, and
mode history. Read-only in OBSERVE mode; gains approve/reject/revert
actions in RECOMMEND and AUTONOMOUS modes.

### Route + navigation

* Route: `/workspace/meta-learning`
* Nav rail: below **Knowledge Graph**, above **Factory Self-Eval** (P1)
* Icon: `brain-circuit` (Lucide)
* Mode chip in top-right of workspace header: `OBSERVE | RECOMMEND | AUTONOMOUS | DISABLED`

### Layout — desktop (≥1440px)

Two-column primary layout:

**Left column (60%)** — `PendingRecommendationsRail`
* Card list, one per recommendation, sorted by ranker_score DESC.
* Each card shows:
  * Target env key (mono, small)
  * Surface pill (brain_weight / brain_threshold / market_weight / execution_gate / confidence_calibration / style_regime_matrix)
  * Current → Proposed value (with directional arrow, colour-coded by delta sign)
  * Confidence bar (0..1, gradient)
  * Risk band chip (green / amber / red — Material 900-tone borders on dark theme)
  * Severity chip (info / low / med / high)
  * Rationale one-liner
  * Evidence link "3 samples" → drawer
  * Actions: **Approve** / **Reject** / **Details** (Approve returns 409 toast in OBSERVE mode; button remains disabled with tooltip explaining mode gate.)
* Cards are keyboard-navigable via `↑↓`; Enter opens details drawer.

**Right column (40%)** — `MetaLearningInsightsPanel`
* Top: KPI grid
  * `Mode` (chip)
  * `Cycles today` (int)
  * `Evaluations today` (int)
  * `Recommendations pending` (int)
  * `Applications today` (int, expected 0 in OBSERVE)
* Middle: `ReliabilityChart`
  * Confidence-calibration reliability curve: x = mean confidence per bin, y = mean realised (mapped to 0..1). Ideal line = y=x. Deviations highlighted.
  * Data source: `GET /api/meta-learning/evaluations?surface=confidence_calibration&limit=1` → parse `evidence.bin_reliability`.
* Bottom: `StyleRegimeMiscalibrationHeatmap`
  * 6 styles × 4 regimes = 24 cells.
  * Cell colour = miscalibration magnitude (blue = under-predicted, red = over-predicted).
  * Hover → cell details (n_samples, mean_expected, mean_realised).
  * Data source: `GET /api/meta-learning/evaluations?surface=style_regime_matrix`.

### Layout — tablet (768–1439px)

Stacked: PendingRecommendationsRail on top (full-width, cards scroll horizontally with snap), InsightsPanel below. Reliability chart + heatmap side-by-side, stack under 640px.

### Layout — mobile (<768px)

Single column. Recommendations show 1 card at a time with swipe-navigate. Details drawer opens full-screen. Approve/reject actions require the mode chip to display RECOMMEND or AUTONOMOUS explicitly, plus a confirm modal.

### Details drawer

Right-slide drawer, 480px wide.

**Sections:**

1. **Summary** — everything from the card, larger.
2. **Evidence chain** — sequence of outcome_event links:
   * Evaluation → linked outcome_event ID
   * Cycle → cycle_id from `meta_learning_cycle_start`
   * Sample outcome_events (up to 10) with brief metadata
   * Every link opens the Explainability Explorer at that event.
3. **Metrics** — full `metrics` block (Pearson, Spearman, mean gap, etc.) rendered as a labeled JSON table.
4. **Guardrails** — max_delta_per_tick, class_caps applicable, whitelist membership.
5. **Actions** — Approve / Reject / Revert (if applied). Each action requires a modal with:
   * The exact env var / target
   * Preview of new value
   * "This is <mode> mode — action is <permitted|blocked>" banner
   * Confirm CTA

### Motion

* Rail cards fade+slide in 120ms, staggered 30ms.
* Reliability curve line draws left-to-right 400ms after first render.
* Heatmap cells fade in row-by-row 200ms.
* Mode chip pulses when mode changes (2s glow + 1s fade).
* Approve/reject buttons: press → 150ms scale-down, release → snap-back.

### Sound

* Approval confirm → soft "click-tick" 40ms.
* Rejection confirm → longer "click-thunk" 70ms.
* Mode transition → chime (150ms, C5 sine + envelope).
* All sounds respect `SOUND_ENABLED` user setting (default off).

### Data-testids (mandatory)

* `meta-learning-workspace-root`
* `meta-learning-mode-chip`
* `meta-learning-pending-rail`
* `meta-learning-rec-card-{recommendation_id}`
* `meta-learning-rec-approve-{recommendation_id}`
* `meta-learning-rec-reject-{recommendation_id}`
* `meta-learning-rec-details-{recommendation_id}`
* `meta-learning-reliability-chart`
* `meta-learning-style-regime-heatmap`
* `meta-learning-kpi-{mode|cycles|evals|pending|applied}`
* `meta-learning-drawer-close`

### Accessibility

* Every card is a `<button role="listitem">` inside a `role="list"` rail.
* Focus ring: `outline: 2px solid var(--focus-cyan)` at all times when tab-navigated.
* Announcements: mode changes announced via `aria-live="polite"` on the mode chip.
* Colour is never the sole conveyor of information — every risk band pairs a colour with a text label + icon.
* Contrast: all text ≥ WCAG AA on the dark theme. Approve/reject buttons ≥ WCAG AAA.

### Performance budget

* Initial workspace paint: ≤ 250ms after data fetch.
* Recommendation list virtualised — 60fps scroll at 500+ items.
* Reliability chart re-renders debounced 100ms on data change.
* Details drawer lazy-loads evidence outcome_events on open (paginated 20 at a time).

### Empty states

* **No evaluations yet**: illustration + "Meta-learning is warming up. Recommendations will appear once <MIN_SAMPLES> decisions have been observed."
* **No pending recommendations**: "All clear. The factory's meta-parameters are considered well-calibrated in the current window."
* **Disabled mode**: "Meta-learning is disabled. Set META_LEARNING_MODE=observe to activate observations."

### Interaction guidelines

* Never permit rapid-fire approve — after each approve, disable the next Approve button for 500ms and show a small progress ring.
* Rejected recommendations remain visible for 24h with a `Rejected · <reason>` chip, then auto-hide (still queryable via history endpoint).
* Applied recommendations show in a `RecentApplicationsRail` below KPI grid — click to see Application → Override → Journal chain.
* Every operator action writes a client-side journal entry with timestamp + operator email (queryable via audit logs).

### Explainability integration

Every card exposes a "Trace" link that opens the **Explainability Explorer** filtered to the recommendation's evidence chain. From there the operator can walk:

```
meta_learning_recommendation
  → meta_learning_evaluation
    → brain_decision (one per sample)
      → execution_realised (twin of the brain_decision)
        → execution_attribution
          → position_id → fills → journal
```

Every link is an outcome_event ID. Every hop is one Mongo find.

### Change control

Any UI change to this workspace must land as an appendix here first,
with operator sign-off, before code implementation begins.


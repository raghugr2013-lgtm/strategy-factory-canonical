# 09 · Operator Lifecycle Architecture

> **Binding safeguard.** Locked 2026-06-11 by operator before M0.
> The restored workstation must be a **guided 10-step lifecycle**, not a
> beautiful collection of disconnected screens. Every major screen must show
> Previous · Current · Next. The workstation must guide operators forward.

---

## 1 · The 10-step operator lifecycle (locked)

```
  ① Market Data  →  ② Generate  →  ③ Mutate  →  ④ Validate  →  ⑤ Select
       ↓
  ⑥ Portfolio  →  ⑦ Master Bot  →  ⑧ Trade Runner  →  ⑨ Monitoring  →  ⑩ Deployment
```

| # | Step | Operator question answered | Primary tab | Sub-state |
|--:|---|---|---|---|
| 1 | **Market Data** | "Do I have clean BID + BI5 + Spread data ready?" | `data` | Manual / Automated / Archive sub-tabs |
| 2 | **Generate** | "Run a new cohort and let the factory produce candidate strategies." | `auto-factory` | Cohort progress · All bucket |
| 3 | **Mutate** | "Generate descendant variants of promising candidates." | `auto-factory` | Lineage view · ancestry chips |
| 4 | **Validate** | "HTF parity · Trade parity · Walk-forward · Monte-Carlo gates." | `auto-factory` | Validated bucket sub-tab |
| 5 | **Select** | "Filter the validated pool down to deployable strategies." | `auto-select` | Single screen |
| 6 | **Portfolio** | "Compose a bundle of selected strategies with allocation + correlation discipline." | `portfolio-builder` | Builder / Panel sub-tabs |
| 7 | **Master Bot** | "Compile the bundle to a `.cbotpack` and push to the runner." | `auto-factory` (compile accordion) + `monitoring` (Cluster fleet) | Master Bot Compile + Master Bot Fleet |
| 8 | **Trade Runner** | "Run the master bot live (or paper) and watch positions / PnL." | `trade-runner` | Primary operational screen |
| 9 | **Monitoring** | "Fleet · backend · alerts · cluster health while bots run." | `monitoring` | 4 sub-tabs (Runtime · Soak · Compute · Cluster) |
| 10 | **Deployment** | "Audit deployment readiness; close the loop back to Market Data." | `monitoring` → Cluster + Dashboard readiness card | Deployment Influence card |

After step 10 the loop **closes back to step 1** — Market Data freshness drives the next generation cohort. The Dashboard sits *above* the loop as **Mission Control**.

---

## 2 · Screen-role hierarchy

Per operator decision, exactly **5 primary screens** + everything else is **secondary**.

| Role | Tab | Reason |
|---|---|---|
| **Mission Control** | `dashboard` | Always-return-to-home. Surfaces the state of all 10 lifecycle steps at once. Carries the live ticker + readiness cards + governance + live pipeline tail. |
| **Primary research screen** | `auto-factory` | Steps 2 + 3 + 4 (Generate, Mutate, Validate). Most operator time during exploration. |
| **Primary data screen** | `data` | Step 1. Without good data, every downstream step fails. |
| **Primary operational screen** | `trade-runner` | Step 8. Where strategies meet real (or paper) capital. |
| **Primary infrastructure screen** | `monitoring` | Steps 9 + 10. Live health, fleet, deployment audit. |

| Tab | Role | Lifecycle stake |
|---|---|---|
| `paper-exec` | secondary | step 4-ish (replay validation) |
| `portfolio-builder` | secondary | step 6 |
| `explorer` | secondary | step-agnostic research lookup |
| `auto-select` | secondary | step 5 |
| `admin-users` | secondary | governance / system administration |
| `workspace` (More ▾) | secondary | step 2-4 individual-strategy lab |
| `pipeline` / `live` / `optimization` / `saved` / `prop-firms` (More ▾) | secondary | drill-downs |

**Role-rule:** secondary screens render with the same Lifecycle Rail as the primaries — but their visual hierarchy is denser (single-column content, no hero KPI strip) so they read as *focused tools*, not *destinations*.

---

## 3 · Lifecycle Rail component (NEW chrome)

> Renders directly under the topbar on every primary + secondary screen.
> Height: 38 px. Sticky below the topbar (so it stays in view when content scrolls).

### 3.1 Anatomy

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ① Market Data → ② Generate → ③ Mutate → ④ Validate → ⑤ Select → ⑥ Portfolio →    │
│ ⑦ Master Bot → ⑧ Trade Runner → ⑨ Monitoring → ⑩ Deployment                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Step states

| State | Treatment | Use |
|---|---|---|
| `done` | white circle, light grey label | step that the operator has already completed in this session OR earlier steps in the chain |
| `current` | **gold filled circle**, **gold label**, gold underline, slight glow | the step that this screen represents |
| `next` | cyan circle, cyan label, dashed cyan underline | the immediately-following step (forward momentum indicator) |
| `future` | hairline-bordered circle, muted label | steps further down the chain |
| `hub` | (Dashboard only) — no step is marked current; all 10 render as `next`-tone, clickable | Dashboard's special Mission-Control state |

### 3.3 Per-screen rail state map

| Screen | Done | Current | Next | Future |
|---|---|---|---|---|
| `dashboard` | — | — (hub state) | — | — |
| `data` (Market Data) | — | **1 Market Data** | 2 Generate | 3-10 |
| `auto-factory` | 1 | **2 Generate** (cohort-active) | 5 Select | 3-4, 6-10 |
| (Auto Factory → Validated sub-tab) | 1, 2, 3 | **4 Validate** | 5 Select | 6-10 |
| `auto-select` | 1, 2, 3, 4 | **5 Select** | 6 Portfolio | 7-10 |
| `portfolio-builder` | 1-5 | **6 Portfolio** | 7 Master Bot | 8-10 |
| (Auto Factory → Compile accordion) | 1-6 | **7 Master Bot** | 8 Trade Runner | 9-10 |
| `trade-runner` | 1-7 | **8 Trade Runner** | 9 Monitoring | 10 |
| `monitoring` | 1-8 | **9 Monitoring** | 10 Deployment | — |
| (Monitoring → Cluster sub-tab) | 1-9 | **10 Deployment** | (loop) 1 Market Data | — |
| `explorer` (secondary research tool) | — | (no current) | (contextual to the strategy you opened) | — |

### 3.4 Behaviour

- Every pill is clickable → routes to that step's primary tab + sub-state.
- Keyboard navigation: `[ / ]` moves to previous/next step.
- The rail is responsive — at narrow viewports it collapses to a `Prev ← Current → Next` 3-pill mode (handheld posture).

### 3.5 Future-phase insertion footnote

The rail logic preserves slots for **⑤a Strategy Dossier (Phase 13) · ⑤b Automated Valuation (Phase 14) · ⑤c Marketplace (Phase 15)** between current Step ⑤ Select and Step ⑥ Portfolio. The pill list in the restoration ships with the locked 10 pills only; the 3 future pills are documented in `10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md` and append at Phase 13 landing without re-laying out the rail.

---

## 4 · Per-screen "Next →" CTA (page-head right)

In addition to the global rail, each screen carries an in-content CTA in the page-head right area:

```
                                          ┌─────────────────────────┐
                                          │ Next: 5 · Select   →    │
                                          └─────────────────────────┘
```

Visual: a 1-row inline button with the step number + label + arrow. Gold accent on hover. Sits next to the existing page-action buttons (e.g., "Run sweep ▶", "Promote (3) ▶"). Per-screen examples:

| Screen | Page-head Next-CTA label | Target |
|---|---|---|
| Dashboard | (no Next-CTA — it's the hub) | — |
| Market Data | Next: ② Generate strategies → | `auto-factory` |
| Auto Factory | Next: ⑤ Select for deployment → | `auto-select` |
| (Auto Factory → Compile) | Next: ⑧ Trade Runner → | `trade-runner` |
| Auto Select | Next: ⑥ Build portfolio → | `portfolio-builder` |
| Portfolio | Next: ⑦ Compile Master Bot → | `auto-factory` (compile accordion) |
| Trade Runner | Next: ⑨ Monitor fleet → | `monitoring` |
| Monitoring | Next: ⑩ Audit deployment → | `monitoring` (Cluster) — OR loop back to ① Market Data |
| Explorer | (contextual, e.g., "Add to ⑥ Portfolio →") | `portfolio-builder` |

The CTA is **gold-emphasised on the next-action button**, NOT on the page's primary CTA (which is the in-screen action like "Promote selected ▶"). This avoids competing emphasis — the screen's primary action is still primary; the Next-CTA is a quiet but always-visible forward arrow.

---

## 5 · Dashboard as Mission Control

The Dashboard does NOT carry a "current step" marker on the Lifecycle Rail — it sits above the journey. Its role is to surface the **state of every lifecycle step at once**.

The Dashboard layout already reflects this (see `mockups/dashboard.html`), but a re-housing of the existing right-rail cards now ties cleanly to the 10 lifecycle steps:

| Dashboard card | Lifecycle step it summarises |
|---|---|
| Ticker strip | ① Market Data freshness (per-pair last-tick + change %) |
| Strategy roster table | ② Generate / ③ Mutate (recent additions) + ④ Validate (status chip) |
| Auto Mutation card | ③ Mutate (in-flight count) |
| Multi-Cycle Runner | ② Generate (cycle progress) |
| Strategy roster `deployment-ready` chip count | ⑤ Select state |
| (existing — not yet on Dashboard) Bundle preview card | ⑥ Portfolio |
| Master Bot Fleet preview | ⑦ Master Bot |
| Open positions card (NEW for Dashboard) | ⑧ Trade Runner |
| Fleet & Compute card | ⑨ Monitoring |
| Deployment Readiness card | ⑩ Deployment |

A minor Dashboard upgrade in M2 will add a small "**Bundle preview**" card + an "**Open positions**" card on the right rail so that **all 10 steps are surfaced on Mission Control at a glance.**

---

## 6 · Acceptance gates (per phase)

Implementation cannot advance past each milestone unless these gates pass:

| Phase | Gate |
|---|---|
| **M0** | (none — token-only) |
| **M1** | Lifecycle Rail mounted in `CommandShell` and present on every routed page; per-screen state map honoured |
| **M2** | All 5 primary screens (Dashboard, Auto Factory, Trade Runner, Monitoring, Market Data) render the rail in the correct state and carry the Next-CTA in the page head |
| **M3** | All secondary screens carry the rail + Next-CTA |
| **M4** | (no additional lifecycle work) |
| **M5** | Smoke probe asserts: (a) Rail rendered on every screen (data-testid="lifecycle-rail"); (b) Current pill matches per-screen state map; (c) Next-CTA mounted (or hub state on Dashboard); (d) Keyboard `[`/`]` navigation works |

Effort: **+1 dev-day total** absorbed into M1 (rail component) + M2 (per-screen wiring) + M5 (smoke probe). No change to total ~9.5 d budget — the lifecycle hook displaces 1 day of "polish" from M5.

---

## 7 · Lifecycle Rail vs Top Tab Bar (clarification — they coexist)

The top tab bar (CORE 11 + MORE 6) is **structural** — it tells you *where* the workstation is organised.
The Lifecycle Rail is **directional** — it tells you *where you are in the journey* and *where to go next*.

They are orthogonal. A power operator can click any top tab at any time (random-access). A new operator can follow the Lifecycle Rail step by step (linear). Both work.

— End of OPERATOR LIFECYCLE ARCHITECTURE —

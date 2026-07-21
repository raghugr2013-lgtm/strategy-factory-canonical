# Frontend Audit & Operator-Center Roadmap

> ⚠️ **STATUS: SUPERSEDED (2026-07-21)** by `memory/D8_SPRINT_1_EXECUTION_PLAN.md` and `memory/DESIGN_FREEZE_v1.0.md`.
>
> This document was authored 2026-07-20 as an **audit of the pre-existing v01 CommandShell frontend** with a recommendation to "improve + consolidate, do NOT rebuild". After the D-series design phase (D0–D8), the E-series experience design (E1–E5), and the Interactive Prototype Gate (P0), the operator elected a **different canonical path**: rebuild the operator frontend in Sprint 1 against the frozen D-series contract, using the prototype as design reference. The v01 CommandShell is not being carried forward.
>
> **Canonical successor:** `memory/D8_SPRINT_1_EXECUTION_PLAN.md` (frontend Sprint 1 execution) + `memory/DESIGN_FREEZE_v1.0.md` (design contract).
>
> This document is retained for historical context only. Do not treat any recommendation below as active — it reflects a superseded plan.
>
> ---
>
> *(Original document follows for archival purposes.)*
>
> **Deliverable:** audit + implementation roadmap only. **No code changes yet.**
> **Prepared:** 2026-07-20
> **Target repo:** `/app/frontend/` (canonical) — separate premium repo pending migration
> **Objective:** evolve the existing shell into an *AI Research & Operations Center*, preserving investment.
> **Success metric:** the six operator questions are answerable within 3 clicks and 5 seconds.

---

## 0. Six operator questions (the north star)

Every roadmap decision below is measured against these six:

1. **Is the system healthy?**
2. **What is the Factory doing right now?**
3. **What has AI accomplished?**
4. **What evidence supports those actions?**
5. **What requires operator approval?**
6. **What needs my attention?**

If a page cannot help answer at least one of these, it is a candidate for
Hide/Merge/Remove.

---

## 1. Executive summary

- **Frontend maturity:** substantial — ~180 components, 10 modules, 60+ sections, custom design system (`identity.css`, `tokens.css`, `premium.css`, `motion.css`), full command shell (LeftRail, TopTabBar, StatusRail, ⌘K palette, notification drawer, danger ribbon, copilot pane, inspector pane, i18n scaffolding).
- **Design language:** dark terminal-command aesthetic — monospace headers, lowercase captions, `P·W·F·A·I` legend taxonomy already defined. Distinctive; avoid AI-slop generic patterns.
- **Production posture:** deployed to VPS; PROD chip, 4d uptime, admin auth working, danger ribbon live-showing "Master Bot compile failed · signing error · 1h ago" → the shell IS surfacing attention correctly today.
- **Gap type:** the shell is 70-80% structurally complete but semantically ~40% operator-ready. Nearly every module currently exposes implementation surfaces (queues, panels, raw JSON) rather than evidence (what did AI do · with what confidence · needing what decision). This is the migration target.
- **Bottom-line verdict:** **Improve + Consolidate**, do NOT rebuild. Estimated total effort to reach "operator-ready": 8-12 weeks solo, 4-6 weeks with the pending premium components migration.

---

## 2. Screenshot smoke test — evidence

### 2.1 Login screen ✅
Clean AuthGate: email + password + Sign in + "Create account" link. Consistent
with dark aesthetic. No changes recommended.

### 2.2 Landing dashboard (`/c/dashboard`) ⚠ mixed
What works:
- **Danger ribbon** — top red bar "Master Bot compile failed · signing error · 1h ago · VIEW INBOX" → answers Q6 (attention).
- **PROD chip + uptime** — "PROD · UP 4d 02:11:42" → answers Q1 (healthy).
- **Numbered lifecycle strip** — "1 Market Data · 2 Generate · 3 Mutate · 4 Validate · 5 Select · 6 Portfolio · 7 Master Bot · 8 Trade Runner · 9 Monitoring · 10 Deployment" → attempts to answer Q2.
- **Legend row** — `P Passed · W Needs Evidence · F Failed · A Advisory · I Info` — the taxonomy is already right for Q4.
- **KPI grid** — AI Workforce, System Pulse, Governance, Ingestion cards → attempts Q3.
- **Attention briefing** — dedicated section for "1 ITEM critical". Q5 candidate.
- **Bottom status rail** — orch/ingest/sched/llm/govern/kill health chips → Q1 detail.

Gaps observed:
- Everything except the "AI provider missing key" is **empty** (0 survivors, 0 ticks, 0 LLM calls, 0 inj, 0 rej). Not a bug — pre-activation state. But the visual density is low; user learns nothing new after the first glance.
- **TopTabBar labels are inconsistent with LeftRail modules**: nav shows `Dashboard, Execution, Auto Factory, Monitoring, Paper Exec, Trade Runner, Portfolio, Explorer, Market Data, Auto Select, Admin, More`; modulesRegistry defines `dashboard, lab, explorer, mutate, portfolio, propfirm, exec, ai, diag, governance`. Two navigation vocabularies co-exist.
- **No explicit "AI accomplishments" feed** — LLM call river shows only counts, not narrative ("what did AI just do & why").
- **No "pending approvals" queue surfaced on the landing** even though Meta-Learning / Factory-Eval OBSERVE-mode recommendations exist backend-side.

**Screenshot artifacts:** `/tmp/vps_login.png`, `/tmp/vps_landing.png`.

---

## 3. Existing module inventory + classifications

Below: every module and every section, classified per your five options.

### Legend for classifications
- 🟢 **Keep** — solid; leave alone
- 🟡 **Improve** — keep the surface, evolve content toward evidence
- 🔀 **Merge** — combine with a sibling; reduces nav noise
- 🔒 **Hide** — move to Advanced/Operator/Diagnostics; remove from primary nav
- ❌ **Remove** — genuinely obsolete

### 3.1 Dashboard module (currently `/c/dashboard`)

| Section | Component | Classification | Rationale |
|---|---|---|---|
| Mission Control (Briefing) | `DashboardComposite` | 🟡 **Improve** — this is the crown jewel; evolve toward the six operator questions (see §5). Add: Approvals queue, AI Timeline, Evidence badges. |

### 3.2 Research Lab (`/c/lab`)

| Section | Classification | Rationale |
|---|---|---|
| Workspace (unified lab) | 🟢 Keep | Legacy 1-vCPU unified surface; power users love it |
| Strategy Panel | 🔀 Merge into Workspace | Duplicates Workspace generate step |
| Analysis | 🔀 Merge into Workspace | Same |
| Backtest | 🔀 Merge into Workspace | Same |
| cBot | 🟡 Improve | Export flow — keep but evidence-ise (show what was exported, where, with what parameters) |
| Optimization | 🟡 Improve | Show optimisation history + provenance |
| Validation | 🟡 Improve | Emit P/W/F/A/I badges per validation stage |

**Net effect:** Research Lab collapses from 7 sections → 3-4 (Workspace / cBot Export / History+Provenance).

### 3.3 Strategy Explorer (`/c/explorer`)

| Section | Classification | Rationale |
|---|---|---|
| Explorer | 🟡 Improve | Add evidence column: origin, learning_only, trust_tier |
| Saved Strategies | 🟢 Keep | Direct operator value |
| Strategy Comparison | 🟢 Keep | Direct decision-support tool |
| Phase 13/14/15 Reservations | 🔒 Hide (already in collapsed accordion) | Correct posture; keep as-is |

### 3.4 Mutation Engine (`/c/mutate`)

| Section | Classification | Rationale |
|---|---|---|
| Auto Mutation Runner | 🟢 Keep | Core operator flow |
| Multi-Cycle Runner | 🔀 Merge into Auto Mutation Runner | Same domain, different cadence |
| Auto Factory | 🟢 Keep | Core |
| Auto Factory · Phase 55 | 🔀 Merge with Auto Factory (mode toggle) | Two versions of same concept |
| Auto Selection | 🟢 Keep | Distinct decision surface |
| Master Bot | 🟡 Improve | This is where the current danger ribbon points ("Master Bot compile failed"). Add evidence: what was attempted, what signed error means, next steps |
| Master Bot Compile | 🔀 Merge into Master Bot (as an action tab) | Two adjacent surfaces for one workflow |

**Net effect:** Mutation Engine collapses from 7 → 4 sections.

### 3.5 Portfolio OS (`/c/portfolio`)

| Section | Classification | Rationale |
|---|---|---|
| Portfolio Builder | 🟢 Keep | Distinct decision surface |
| Portfolio Panel | 🔀 Merge into Portfolio Intelligence | "Panel" is redundant vocabulary |
| Portfolio Intelligence | 🟢 Keep — promote to landing | This should be the Portfolio module landing |
| Phase 14 Reservations | 🔒 Hide (already collapsed) | Correct posture |

### 3.6 Prop Firm (`/c/propfirm`)

| Section | Classification | Rationale |
|---|---|---|
| Prop Firms (Admin) | 🔀 Merge into Firm Match as "Catalogue" tab | Two surfaces for the same table |
| Firm Match | 🟢 Keep | Core operator decision tool |
| Challenge Matching | 🟢 Keep | Distinct flow (strategy → firm rule fit) |

### 3.7 Execution Center (`/c/exec`)

| Section | Classification | Rationale |
|---|---|---|
| Execution Overview | 🟢 Keep — expand as module landing | Answers Q2 for execution |
| Broker Chips (cTrader/VPS) | 🟡 Improve — evidence per broker | Show fill quality, uptime, last-tick freshness |
| Paper Execution | 🟢 Keep | Distinct |
| Trade Runner | 🟢 Keep | Distinct |
| Live Tracking | 🟢 Keep | Distinct — but evidence-ise: what trades, why, what quality |

### 3.8 AI Workforce (`/c/ai`)

| Section | Classification | Rationale |
|---|---|---|
| LLM Call River | 🟡 Improve → rename **"AI Activity Timeline"** | This is the primary Q3 surface. Redesign as narrative feed, not raw calls |
| Orchestrator | 🔒 Hide under Diagnostics | Implementation detail — operator doesn't need queue depths on primary nav |
| Auto-Scheduler | 🟡 Improve | Show what the scheduler DID, not just its state |

### 3.9 Diagnostics (`/c/diag`)

Currently 10 sections. Most of these are correctly classified as diagnostics but
the section count is overwhelming.

| Section | Classification | Rationale |
|---|---|---|
| Deployment Readiness | 🟢 Keep | High-level Q1 answer |
| Parity Certification | 🔒 Hide → Advanced | Implementation-level |
| Ingestion Health | 🟡 Improve → surface on Dashboard, remove duplicate here | Move to landing evidence panel |
| Strategy Ingestion | 🔒 Hide → Advanced | Implementation |
| Pipeline Logs | 🔒 Hide → Advanced | Raw logs |
| Market Data | 🟢 Keep | High-value operator surface (coverage, freshness) |
| Monitoring Suite | 🟢 Keep | Distinct |
| BI5 Health (per-symbol) | 🔀 Merge into Market Data as "Per-symbol Coverage" tab | Same theme |
| BI5 Certification | 🔀 Merge into Market Data as "Certification" tab | Same theme |

**Net effect:** Diagnostics collapses from 10 → 4 top-level entries plus an "Advanced" drawer.

### 3.10 Governance (`/c/governance`)

| Section | Classification | Rationale |
|---|---|---|
| Governance Card | 🟢 Keep | Direct Q4/Q5 surface |
| Universe Governance | 🟢 Keep | Distinct |
| Symbol Registry (DSR) | 🟡 Improve | Add evidence: who onboarded, when, why |
| Rules Review | 🟢 Keep | Distinct |
| Env Priority | 🔒 Hide → Admin/Advanced | Implementation-level |
| Readiness | 🔀 Merge with Deployment Readiness | Duplicate concept in two modules |
| Admin (composite: Users / Flags / Realism / Tuning) | 🟢 Keep | Correct consolidation |

---

## 4. Aggregate consolidation impact

| Metric | Before | After | Δ |
|---|---|---|---|
| Top-level modules | 10 | 8 | -20% |
| Total sections (workstation posture) | 60+ | ~30 | -50% |
| Distinct "landing" surfaces per module | avg 4-6 | avg 2-3 | ~40% simpler |
| Advanced/hidden diagnostics surfaces | 0 explicit | ~15 | Explicit "power user" mode |

**8-module post-consolidation nav:**
`Dashboard · Research Lab · Explorer · Mutation · Portfolio · Prop Firm · Execution · Governance` (with **AI Activity** promoted as a persistent right-rail feed and **Diagnostics** moved into an Admin drawer).

---

## 5. Information Architecture — proposed evolution

### 5.1 Landing page redesign — "Mission Control" (rebuild `DashboardComposite`)

Six panels, one per operator question:

```
┌──────────────────────────────────────────────────────────────────┐
│  DANGER RIBBON (existing — keep as-is)                           │
├──────────────────────────────────────────────────────────────────┤
│  Q1 · SYSTEM HEALTH                     Q6 · ATTENTION            │
│  ─────────────────                       ────────────             │
│  · orch · healthy                        [ 2 critical items ]    │
│  · ingest · ready                        [ 1 needs review    ]    │
│  · sched · failover on                   [ 0 advisory        ]    │
│  · llm · no key ⚠                                                 │
│  · govern · governed                                              │
│  · kill · armed                                                   │
├──────────────────────────────────────────────────────────────────┤
│  Q2 · WHAT THE FACTORY IS DOING NOW      Q5 · PENDING APPROVALS  │
│  ────────────────────────────────         ─────────────────────  │
│  · idle — no active cycles                (grouped by module:    │
│  · queued: 0 mutations, 0 backtests        Meta-Learning · 3     │
│  · last cycle finished 4h ago              Factory-Eval    · 1)   │
│  · view auto-factory →                    · view queue →          │
├──────────────────────────────────────────────────────────────────┤
│  Q3 · WHAT AI ACCOMPLISHED (last 24 h)                            │
│  ────────────────────────────────────                             │
│  · 0 strategies generated                                         │
│  · 0 mutations completed                                          │
│  · 0 promotions (dormant — Phase D not started)                  │
│  · 0 LLM calls (no key)                                          │
│  · view timeline →                                                │
├──────────────────────────────────────────────────────────────────┤
│  Q4 · EVIDENCE (legend already exists)                            │
│  ───────────────────────────────────                              │
│  · P Passed · W Needs Evidence · F Failed · A Advisory · I Info   │
│  · every metric card links to its evidence trail                  │
└──────────────────────────────────────────────────────────────────┘
```

**Design principles baked in:**
- Every card MUST link to a deeper "why" view (never a dead-end number)
- Every attention item MUST include a proposed next action
- Empty states are narrative, not tables of zeros: *"No mutation cycles have
  run in the last 24 h. This is normal during freeze."*

### 5.2 AI Activity Timeline — right rail (persistent)

**Rename** the current `LlmCallRiver` to **AI Activity Timeline** and promote it
to a persistent right-rail component visible from every module (collapsible).

Each entry is a narrative row, not a raw call:

```
[12:24] · orchestrator opened GPT-5 to score 3 candidates
         · confidence 0.87 · verdict: proceed to backtest → [view evidence]
[11:03] · retrieval matched 2 KB items to challenge FTMO-100k
         · trust_tier verified · dedup passed → [view evidence]
[09:47] · master-bot compile FAILED (signing error)
         · action required · [view inbox]
```

Backend-side: this reads from `/api/llm-calls/*` + `/api/ai-workforce/*` + the
5 Stage-4 retrofit `/health` endpoints once activated.

### 5.3 Approvals Queue — a first-class surface

Currently pending approvals are scattered:
- Meta-Learning recommendations (backend returns 409 on `POST /approve`)
- Factory-Eval recommendations (409)
- Governance advisory tags
- Master Bot compile failures
- Symbol Registry onboarding requests

**Consolidate** into `/c/approvals` (new top-level entry) OR promote to a
persistent header chip: `[ 4 approvals ▼ ]` that opens a drawer.

Each approval has: what · why · evidence · Approve / Defer / Deny.

### 5.4 Advanced / Operator Mode toggle

A header toggle (persist in localStorage): **Simple · Advanced**.

- **Simple** (default) — the 8-module nav above, no raw internals.
- **Advanced** — everything hidden re-appears: Orchestrator queues, Env Priority, Parity Certification, Pipeline Logs, Strategy Ingestion sources, all `/api/admin/*` deep surfaces, all `/api/scaling/*`, all `/api/latent/*`.

---

## 6. Gap analysis — backend → UI coverage

Comparing 701 backend routes against 180 frontend components.

### 6.1 Backend capability with NO UI surface (P0 fill-ins)

| Backend area | Route sample | UI gap | Priority |
|---|---|---|---|
| Coherent UKIE Activation status | `/api/knowledge/ukie/health`, `/api/health/system.ukie` (post-A.1) | No operator dashboard for Phase-A activation progress | **P0** (needed for Phase A) |
| Approvals queue (Meta-Learning + Factory-Eval OBSERVE) | `/api/meta-learning/recommendations`, `/api/factory-eval/recommendations` | Scattered / hidden — no unified queue | **P0** |
| Governance advisory decisions | `/api/knowledge/promote/{id}` (dormant now; wakes at Phase D) | No preview / dry-run UI for promote bridge | **P1** (Phase D readiness) |
| Retro-score outcomes | `/api/knowledge/retro-score` | No historical view | **P1** |
| Connector fleet health | `/api/knowledge/connectors/health` (dormant) | No connector-status HUD | **P1** |
| Dead-letter queue | `/api/coe/dead-letter`, `/depth` (dormant) | No triage UI | **P1** |
| BI5 per-symbol status | `/api/admin/bi5/*` | Panel exists (Bi5CertPanel) but is under Diagnostics — should surface on Market Data | **P1** |
| Execution attribution | `/api/execution/attribution?strategy_hash=` | No per-strategy execution-quality drill-down | **P1** |
| Broker fill-quality timeseries | `/api/execution/quality?pair=` | 422 without params — no UI provides the params | **P1** |
| Prop-firm challenge simulator | `/api/simulate-challenge` | No dedicated simulator UI (challenge match ≠ simulate) | **P2** |
| Master Bot signing error triage | current danger ribbon points here | Ribbon exists but no "diagnose" UI | **P0** (currently active issue) |

### 6.2 UI surfaces with no clear backend evidence (P1 hygiene)

| UI surface | Missing evidence |
|---|---|
| Portfolio Panel | Whose portfolio? What time window? Which strategies? |
| Env Priority Panel | What is priority for? Where does it flow? |
| Universe Governance | Which decisions are pending? Who decided? When? |
| Master Bot Dashboard | Which bots? Last compile succeeded/failed? |

### 6.3 Evidence surfacing (P0 across the board)

Every metric on the landing must resolve to an evidence trail:
- Click "0 survivors" → shows *what* was rejected + *why*
- Click "0 mutations" → shows last cycle's summary + link to run one
- Click "no key" → shows exactly which var, where to set it
- Click "sealed · advisory-only" → shows current governance posture + who set it

---

## 7. Operator Journey review

### 7.1 Login → Landing (< 5 s)
- ✅ AuthGate works
- ✅ Danger ribbon surfaces first
- ⚠ Landing is mostly zeros because Stage-4 is dormant — need narrative empty
  states so the operator learns something even in idle state
- **P0:** rewrite empty states to be narrative + educational

### 7.2 Daily Operations
Current friction points:
- Two navigation vocabularies (LeftRail modules ≠ TopTabBar tabs) → **P0 fix**: pick one; my recommendation is LeftRail-first, TopTabBar shows *sections* of current module
- Numbered lifecycle strip ("1 Market Data → 10 Deployment") is descriptive but not interactive — clicking each number should jump-scroll to that lifecycle stage's evidence panel → **P1**
- No global "resume where I left off" — a returning operator lands on the same generic dashboard → **P2**

### 7.3 Approvals
Currently no dedicated approvals path:
- Meta-Learning and Factory-Eval both operate in OBSERVE (recommendations exist, `/approve` returns 409). But no queue surfaces those recommendations. → **P0**: build `/c/approvals` (or drawer).
- Master Bot signing-error attention item has no "diagnose · resolve · approve retry" workflow → **P0**

### 7.4 Monitoring
- ✅ Status rail is excellent (6 chips: orch/ingest/sched/llm/govern/kill)
- ⚠ Diagnostics module has 10 sections — too many; consolidate per §3.9
- **P1:** move Market Data (currently under Diagnostics) up to be its own module — it's an operator surface, not a diagnostic

### 7.5 Administration
- ✅ Admin composite (Users / Flags / Realism / Tuning) is correctly consolidated
- **P2:** add an "Audit trail" tab (reads `/api/admin/audit-log`)

---

## 8. Consolidated implementation backlog

### 8.1 Priority P0 (weeks 1–3) — operator clarity

| # | Task | Effort | Backend deps |
|---|---|---|---|
| P0-1 | Rewrite `DashboardComposite` to the six-question layout (§5.1) | 3-5 d | none — reuses existing endpoints |
| P0-2 | Create `/c/approvals` (or drawer) — unify Meta-Learning + Factory-Eval + governance advisory queues | 3-4 d | none (endpoints exist, 409 on approve as intended) |
| P0-3 | Rebuild `LlmCallRiver` as narrative **AI Activity Timeline**, promote to right rail | 3-5 d | uses existing `/api/llm-calls/*` |
| P0-4 | Fix nav vocabulary drift: LeftRail = modules, TopTabBar = sections of current module. Delete the parallel `Execution/Auto Factory/Monitoring/…` labels. | 1-2 d | none |
| P0-5 | Narrative empty states — every "0" gets a sentence explaining why + a proposed action | 2-3 d | none |
| P0-6 | Master Bot signing-error triage flow — take the current danger ribbon click through to a "diagnose" surface | 2-3 d | none — endpoints exist |
| P0-7 | Advanced/Simple posture toggle + hide the 15 diagnostics surfaces from Simple | 2 d | none |
| P0-8 | Coherent UKIE Activation HUD — a single page that shows Phase A/B/C/D/E progress, per-flag dormancy state, and the current activation phase status | 5-7 d | uses `/api/health/system.ukie` (post-A.1), `/api/knowledge/ukie/health` |

**P0 total effort:** ~4 weeks solo; 2-3 weeks with 2 devs.

### 8.2 Priority P1 (weeks 4–6) — evidence & consolidation

| # | Task | Effort | Backend deps |
|---|---|---|---|
| P1-1 | Consolidate Research Lab: 7 → 3-4 sections; keep Workspace as primary | 3-4 d | none |
| P1-2 | Consolidate Mutation Engine: 7 → 4 sections; merge Master Bot / Compile | 2-3 d | none |
| P1-3 | Consolidate Portfolio OS: 4 → 3 sections; promote Intelligence to landing | 1-2 d | none |
| P1-4 | Consolidate Prop Firm: 3 → 2 sections; unify Catalogue + Match | 1-2 d | none |
| P1-5 | Consolidate Diagnostics: 10 → 4 sections + Advanced drawer | 3-4 d | none |
| P1-6 | Promote Market Data to its own module (was under Diagnostics) | 1 d | none |
| P1-7 | Evidence columns on Strategy Explorer: origin, learning_only, trust_tier, promote_events count | 2-3 d | uses `/api/strategies/explorer` (needs backend to include these — freeze-permitted) |
| P1-8 | Broker chip evidence surface: fill quality, uptime, last-tick per broker | 3-4 d | `/api/execution/quality?pair=…` |
| P1-9 | Per-strategy execution attribution drill-down | 3-4 d | `/api/execution/attribution?strategy_hash=…` |
| P1-10 | Connector fleet HUD (Phase D-ready) | 3 d | `/api/knowledge/connectors/*` |
| P1-11 | Dead-letter triage table (Phase B.2-ready) | 3 d | `/api/coe/dead-letter/*` |
| P1-12 | Governance advisory-tag preview (Phase C.6-ready) | 2-3 d | `/api/knowledge/promote/*` dry-run |

**P1 total effort:** ~5 weeks solo; 3 weeks with 2 devs.

### 8.3 Priority P2 (weeks 7+) — polish & advanced

| # | Task | Effort |
|---|---|---|
| P2-1 | Micro-interactions pass: hover states, entrance animations, staggered reveals per §UI/UX guidelines | 3-5 d |
| P2-2 | Motion polish (library: Motion for React; existing `motion.css` variables preserved) | 2-3 d |
| P2-3 | Prop-firm challenge simulator UI (dedicated flow, not just Firm Match) | 3-4 d |
| P2-4 | Audit trail view under Admin | 2 d |
| P2-5 | Global "resume where I left off" (localStorage last-viewed section) | 1 d |
| P2-6 | Numbered-lifecycle-strip interactivity (jump-scroll to stage) | 1 d |
| P2-7 | Portfolio/challenge print export refinement (existing print CSS) | 2 d |
| P2-8 | Reservation cards (Phase 13/14/15) — keep hidden until activated | 0 |
| P2-9 | i18n content pass — walk existing scaffolding, populate en/... locale files | 5-8 d (per locale) |

**P2 total effort:** ~4-6 weeks solo.

### 8.4 Roadmap summary

| Sprint | Weeks | Focus | Outcome |
|---|---|---|---|
| Sprint 1 | 1-2 | P0-1 → P0-5 | Mission Control answers the 6 questions on the landing |
| Sprint 2 | 3-4 | P0-6 → P0-8 | Master Bot triage · Simple/Advanced toggle · UKIE activation HUD |
| Sprint 3 | 5-6 | P1-1 → P1-6 | Module consolidation done; nav vocabulary unified |
| Sprint 4 | 7-8 | P1-7 → P1-12 | Evidence surfacing across strategies · execution · connectors · dead-letter |
| Sprint 5 | 9-10 | P2-1 → P2-6 | Motion + micro-interactions + operator ergonomics |
| Sprint 6 | 11-12 | P2-7 → P2-9 | Print polish + i18n content |

---

## 9. Design system stewardship

Existing tokens (`tokens.css`, `identity.css`, `premium.css`, `motion.css`,
`panels.css`, `shell.css`) are the source of truth. Recommendations:

- **Keep** the dark terminal-command aesthetic — it's distinctive and matches the
  operator persona
- **Keep** the P/W/F/A/I taxonomy — expand its use to every metric card
- **Keep** monospace headers + lowercase captions — this is signature language
- **Keep** the danger ribbon pattern — it works
- **Avoid** shadcn/ui default look-and-feel when it clashes with the custom
  design system; wrap shadcn primitives in local variants that use the tokens
- **Add** a "narrative empty state" token — reserved copy space + guidance line
  + optional action button. Baseline for all P0-5 work.

---

## 10. Migration path — canonical repo ↔ premium repo

You mentioned a separate premium-UI repo. Recommended migration sequence:

1. **Diff-first, not code-first.** Share the premium repo path with me. I'll
   produce a component-by-component diff report: which premium components
   qualify to replace canonical siblings, which duplicate existing work, which
   are net-new.
2. **Migrate P0 candidates first** — the 8 P0 tasks above are the highest-leverage.
   If premium components exist for any of them, prefer those.
3. **Never big-bang** — port one component per PR; run existing shell in
   parallel until each replacement is validated (screenshot + smoke test).
4. **Design tokens are the interface** — the premium repo's components must
   conform to canonical tokens (`tokens.css`); if it uses its own tokens, we
   fold them in as additions, not replacements.

---

## 11. What is NOT included in this audit

- **No code changes.** Zero components edited.
- **No backend changes.** Backend Feature Freeze respected.
- **No design assets generated.** Wireframes above are ASCII sketches — real
  visual design happens once you approve the direction and connect the
  premium repo.
- **No feature-flag flips.** All Stage-4 dormancy preserved.

---

## 12. Recommended next-step ordering

1. **You review this document.**
2. **You decide** any classification you disagree with (§3) and adjust the roadmap.
3. **You share the premium repo path.** I run the diff report.
4. **We pick Sprint 1's specific P0 tasks** and lock scope.
5. **Only then** do I begin implementing.

Backend Feature Freeze remains in effect. UI evolution is now the only active
workstream; backend touch-only for genuine bugs.

---

*End of audit.*
*Awaiting your review + premium repo connection before any code lands.*

# Sprint 2 · Legacy Capability & UX Audit

> **Prepared:** 2026-07-21
> **Audit type:** Read-only comparison. No code changes proposed. Design Freeze v1.0 fully respected.
> **Legacy artefact:** `/app/memory/legacy-ui-screenshots/image{1..18}.png` (extracted from operator's Word document)
> **New UI:** Sprint 2 preview build at https://factory-v2-canonical.preview.emergentagent.com/
> **Freeze status:** Backend Feature Freeze v1.1.0-stage4 + Design Freeze v1.0 both active.

---

## 1. Legacy top-nav & module inventory (verbatim from screenshots)

Full top-nav observed across the 18 legacy screenshots:

```
Dashboard · Execution · Auto-Factory · Monitoring · Paper Trade · Trade Runner · Portfolio · Explorer · Market Data · Auto Select · Admin · Me
   + right-side buttons: TRADER MODE · CLUB / BLOG · COMPACT · <user-email> · Sign out
```

Underneath each top-nav item, the legacy UI exposed the following surfaces (labels quoted verbatim from the screenshots):

| Legacy top-nav | Surfaces inside |
|---|---|
| Dashboard / Auto-Factory | Governance Phase 30.1 · Universe Governance Phase 30.2 · Strategy Ingestion · Auto-Discovery Scheduler · AI Orchestrator (advisory/recommendations/execution) · Multi-Cycle Optimization · AutoMutationRunner · Generate Strategies wizard · Multi-Asset Portfolio · Saved Portfolios · Pipeline Logs |
| Monitoring | Monitoring & Control (CONTROL · PORTFOLIO EQUITY · FLEET · STRATEGIES · BREACH LOG · Stop-all/Resume · thresholds sliders) |
| Portfolio | Portfolio Builder (POS # · TARGET SLIP · MIN PICK % · MIN WIN PCT % · MIN MATCH · RISK CAP % · Include HIDDEN · Regenerate · Build Portfolio · Save) |
| Auto Select | Auto Selection (TOP N · MIN PASS % · MIN MATCH · MIN PP · MIN RISK · MIN STABILITY · MIN FST LEAP · PASS only · Run Auto Selection) |
| Auto-Factory · Quick Pipeline | PAIR · TIME FRAME · COUNT · RISK % · Run Pipeline |
| Trade Runner / Live Tracking | + Add strategy · Update All · Auto On/Off |
| Paper Trade | Simulation environment (details not captured but implied by nav) |
| Explorer | Strategy / market exploration (details not captured) |
| Market Data | Historical + realtime data access (details not captured) |
| Admin | User management, system config |
| Me + right-side buttons | Sign out · TRADER MODE / CLUB / COMPACT display toggles |

---

## 2. Legacy Capability Matrix

Legend:
- **① Already exposed** in the new UI
- **② Intentionally hidden but accessible** through the new workflow (Master Bot · Passport · Timeline · Palette · Drawer)
- **③ Implemented but not surfaced well enough** — needs a discoverability refinement
- **④ Missing from the new UI**

| # | Legacy screen / module | Legacy capability | New equivalent | Status | Recommendation | Priority |
|---|---|---|---|:-:|---|:-:|
| L1 | Dashboard | "System overview at a glance" | `/c/mission` Mission Control · 6-question layout | **①** | None — new UI is strictly superior (Bible §7.11, D1 §5). | — |
| L2 | Governance 30.1 · Deployment status counters (active/deployed/deploy_ready) | Fleet promotion tallies | Mission Control metric-blocks + Master Bot §1 Identity strip trust-budget block | **①** | None. | — |
| L3 | Universe Governance 30.2 · Exploration Settings (Max Active Grid, Grid Depth, priority pools, diversity/velocities/relations tuners) | Operator tuning of exploration knobs | **not exposed** anywhere in new UI | **④** | Route through **Master Bot Advanced Lens** (Cmd+K → "advanced lens") so knobs stay one hop away without polluting the shell. Alternative: `/c/settings` sub-section titled "Exploration governance". This is a POWER USER capability — do not surface in the main navigation. | **Medium** |
| L4 | Strategy Ingestion table (ID · LAST RUN · RUNS · ACTIVE · REJECTED · Run Ingestion) | Feed of incoming strategies + manual ingest trigger | Timeline (`/c/timeline`) with actor facet = `ingestion-worker` | **②** | Add a Timeline **actor-facet preset** for "ingestion" — one Cmd+K entry: `Timeline · ingestion runs`. No new sidebar item. | Low |
| L5 | Auto-Discovery Scheduler (toggle · NEXT RUN countdown · last-run summary) | Recurring discovery cadence | Master Bot Current-Plan card + Master Bot decisions log ("scheduled discovery cycle") | **③** | The plan card already shows epoch + horizon but does not name the *next scheduled discovery tick*. Add a `next-tick` postmark inside the plan card guardrails grid (semantic addition; no design token change). | **High** |
| L6 | AI Orchestrator advisory panel + RECOMMENDATIONS 1-of-3 + EXECUTION panel | LLM-authored operator advice | Master Bot §3 Last-Decisions log with rationale (Advanced Lens) | **①** | None. New surface is richer (verb + subject + tone + rationale) than the legacy panel. | — |
| L7 | Multi-Cycle Optimization · Run Cycles · CURRENT CYCLE · BEST CUMULATIVE | Multi-cycle backtest/optimization iteration | Strategy Passport `passport-equity` + `passport-backtest` + guardrails · Master Bot decisions log | **②** | Add a **"Run cycle"** command in the ⌘K palette — routes to Approvals with a scoped "compute quota +N cycles" pending approval (matches Sprint 1 approval semantics). No new surface. | Medium |
| L8 | AutoMutationRunner · Base Asset · Mutations · BEST QUALITY · BEST DIVERGENCE | Mutation experiment runner | Master Bot decisions log (verb=`mutated`/`attested`) | **③** | Expose a **mutation summary** as a Strategy Passport sub-section (`passport-mutation-history`) when the strategy has ≥1 mutation ancestor. Data path already exists via `strat.lineage.ancestors[kind=='mutation']`. Semantic-only addition. | Medium |
| L9 | Generate Strategies wizard (PIPE · TF · STYLE · PAIR · FILTER · ADD FINN · COUNT · OPTIMIZER · + GENERATE STRATEGIES) | Manual multi-parameter strategy generation | **not exposed** anywhere in new UI | **④** | Wizards are a legacy pattern. In the new UI, strategy creation should go through **Approvals** ("propose new strategy" origin), which is more auditable and preserves Decision Identity. Add a Cmd+K entry: `Propose new strategy…` → drops a scoped `<ApprovalCard origin="proposal">` into `/c/approvals`. No new sidebar item. | **High** |
| L10 | Multi-Asset Portfolio picker | Compose a portfolio across multiple pairs | **not exposed** | **④** | Sprint 2 D5 Passport is per-strategy. Portfolios remain a legitimate concept. Recommendation: Sprint 3 candidate — add a Portfolio surface (`/c/portfolios/:id`) modelled after Passport (D5), NOT a builder wizard. For Sprint 2 VPS deployment: **acceptable to omit**, no operator currently uses portfolios in production per PRD.md history. | **Low** |
| L11 | Saved Portfolios list | Persisted portfolio catalogue | **not exposed** | **④** | Same as L10 — Sprint 3. | Low |
| L12 | Pipeline Logs (INFO/WARN/ERROR/SUCCESS entries with source + strategy id + timestamp) | Raw developer log stream | Timeline (partially — high-level events only) | **③** | Timeline is intentionally the operator-facing feed, not a raw log stream. Recommendation: expose a **"pipeline log"** entry in the ⌘K palette under `advanced lens` that opens an EvidenceDrawer scoped to the last N raw log lines. No sidebar item. Preserves Progressive Disclosure (Bible §1.4.3). | Medium |
| L13 | Portfolio Builder table (# · STRATEGY · ENVIRONMENT · FORM-CHALLENGE · STATUS · PASS % · MATCH · SAFE RISK ALLOCATION · RISK %) | Portfolio composition table | Strategies Explorer + Passport | **①** for the columns present · **③** for FORM-CHALLENGE and SAFE-RISK-ALLOCATION | Add two optional columns to `<StrategyExplorer>`: `form/challenge` and `safe-risk`. TableTile already supports arbitrary columns; only fixture data needs to include the fields. | Medium |
| L14 | Auto Selection filters (TOP N · MIN PASS % · MIN MATCH · MIN PP · MIN RISK · MIN STABILITY · MIN FST LEAP · PASS only) | Bulk-select strategies by multi-criteria filter | Strategies Explorer FacetBar (status axis) | **③** | The FacetBar currently supports only `status`. Add a multi-criteria "Advanced filters" popover next to the FacetBar (opens with `f` key) exposing the seven legacy criteria. No new surface, no sidebar item, no design token change. | Medium |
| L15 | Monitoring & Control · STOP ALL TRADING · RESUME TRADING · Scheduler ON/OFF | Break-glass kill switch + scheduler pause | Kill-Posture chip in StatusRail (`data-testid="status-chip-kill-posture"`) | **①** | New UI has parity via the kill-posture affordance already surfaced. Confirmed in Sprint 1 M5 + Design Freeze §1.5. | — |
| L16 | Monitoring & Control · PORTFOLIO EQUITY table (EQUITY · PEAK · TOTAL DD · DAILY DD) | Realtime equity snapshot | Mission Control metric-block strip + Strategy Passport metrics | **③** | Mission Control shows *fleet* metrics but not a *portfolio-level* equity trace. Add a fourth Mission Control metric block: `Portfolio equity · <MetricBlock variant="B">` — reuses existing primitive, no new component. | **High** |
| L17 | Monitoring & Control · FLEET (ACTIVE RUNS · UNDER REVIEW · ACTIVE STRATEGIES · PAUSED) | Fleet-wide state counters | Mission Control mc-attention + mc-workforce panels | **①** | None. | — |
| L18 | Monitoring & Control · thresholds (Daily DD % · Undesired PP · Loss Streak · Total DD % · PP-drawdown % · Save Thresholds) | Editable risk thresholds | **not exposed** | **④** | These are governance settings, not day-to-day operator affordances. Route through `/c/settings` sub-section "Risk thresholds" — Sprint 3 (or Sprint 2.5 minor). Do not surface in Mission Control (violates §1.4 Executive mode calm). | Medium |
| L19 | Monitoring & Control · BREACH LOG | Guardrail breach ledger | Timeline (partial) + Approvals (partial) | **③** | Add a Timeline actor-facet preset: `breaches` → filters to `role="breach"` events. One Cmd+K entry. No new surface. | High |
| L20 | Auto Factory · Quick Pipeline (PAIR · TF · COUNT · RISK % · Run Pipeline) | Single-shot pipeline trigger | Approvals ("propose factory run" origin) | **②** | Add Cmd+K entry: `Run quick pipeline…` → drops an ApprovalCard. Reuses the L9 proposal pattern. | Medium |
| L21 | Live Tracking / Trade Runner (+ Add · Update All · Auto On/Off) | Add strategy to live tracking + refresh | Strategies Explorer row activate → Passport | **③** | Passport already shows live status via `<Chip tone={STATUS_TONE[strat.status]}>`. But there's no explicit **"promote to live tracking"** action. Add a Passport action bar: `[promote to live]` `[demote to paper]` — these should drop an ApprovalCard, not act directly (governance discipline). | High |
| L22 | Paper Trade module | Isolated simulation environment | Strategies Explorer `status=paper` facet · Passport `AUM · paper only` | **①** | The new UI treats paper as a status attribute of a strategy rather than a separate module. Cleaner mental model. Keep. | — |
| L23 | Explorer (legacy) | Broad strategy / market exploration | Strategies Explorer (`/c/strategies`) + Passport | **①** | Same concept, cleaner layout. Keep. | — |
| L24 | Market Data | Historical + realtime market data | **not exposed** as a first-class surface | **③** | Data access is a Research-mode concern (D6). Add Cmd+K entry: `Open market data drawer` → an EvidenceDrawer scoped to symbol + timeframe. Advanced Lens only. | Low |
| L25 | Admin | User management + system config | `/c/settings` (Sprint 1 M4 stub) | **①** already scaffolded, ③ not filled | Settings surface exists but is minimally populated. Sprint 3 candidate to complete: users, tokens, feature flags viewer (read-only), audit log. | Medium |
| L26 | TRADER MODE · CLUB · COMPACT toggles (top right buttons) | Personalisation modes | Modes: Executive · Operations · Research · Developer (D6) accessible from UserMenu | **①** | New system is richer and orthogonal (D6 §8.1a Decision Identity). Legacy trio maps roughly to Operations / Research / Executive. Keep. | — |
| L27 | Sign out + user email | Session management | UserMenu (Sprint 1) | **①** | None. | — |

---

## 3. Workflow comparison

### Legacy
```
Discover → Configure → Generate → Optimize → Validate → Deploy
```
Six explicit steps, each mapped to its own top-nav module (Explorer / Auto-Factory / Generate wizard / Multi-Cycle Optimization / Monitoring / Trade Runner). The operator has to know **which module owns which step**, and step-forward + step-back navigation is manual.

### New (Operator OS)
```
Mission → Master Bot → Strategies → Strategy Passport → Approvals → Deployment
```
Six implicit steps folded into surfaces owned by intent rather than function:
- `Mission` = "what needs my attention right now?"
- `Master Bot` = "what is the Factory *choosing* to do right now?"
- `Strategies` = "which strategy is our subject?"
- `Passport` = "does this strategy earn deployment?"
- `Approvals` = "which decision needs my signature?"
- Deployment = a state change on the strategy, not a separate module.

### Verdict: **STRICTLY SUPERIOR — but with three specific gaps**

The new workflow is cleaner because:
1. **Purpose Before Status (D4 §5.1.1)** — every surface answers a *why* question before dumping data.
2. **Everything Connected (Bible §1.4.2)** — Passport lineage carries the operator from proposal → backtest → deployment without switching modules.
3. **Decision Identity (D6 §8.1a)** — the same strategy id is the truth across every mode, whereas the legacy UI often duplicated the same strategy in Explorer, Portfolio Builder, and Auto Select with subtly different rows.
4. **Progressive Disclosure (Bible §1.4.3)** — power knobs (Universe Governance sliders, mutation runner params, threshold sliders) move to Advanced Lens / Settings, keeping Mission Control calm.

The three gaps (all recoverable without violating Design Freeze):
- **Gap A: `Discover` phase is soft** — the new UI has no explicit "propose new strategy" affordance. Currently Master Bot decides what to promote; there's no path for an *operator-originated* proposal. (Legacy L9 = Generate Strategies wizard.)
- **Gap B: `Optimize` phase is opaque** — Master Bot decisions log mentions "mutation" and "cycle" events, but the operator cannot inspect *which strategies are currently in the optimizer* or trigger a manual optimization pass. (Legacy L7 = Multi-Cycle Optimization panel.)
- **Gap C: `Deploy` phase is implicit** — there is no explicit "promote to live / demote to paper" affordance on the Passport. State transitions are visible but not actionable. (Legacy L21 = Trade Runner + Add.)

Recommendation: **address Gaps A, B, C via three ⌘K palette entries** (no new sidebar items, no new surfaces):
- `Propose new strategy…` → drops `<ApprovalCard origin="proposal">` on `/c/approvals`
- `Run optimization cycle…` → drops `<ApprovalCard origin="compute-quota">` on `/c/approvals`
- `Promote strategy #… to live` / `Demote to paper` — surfaces on Passport action row, both drop `<ApprovalCard origin="deployment">` (never direct action; governance discipline)

Each keeps the "operator drops a request, Master Bot decides, ledger records" invariant — the very reason the new UI is better than the legacy wizard/toggle/button trio.

---

## 4. Answers to the four questions

### 4.1 Is any important functionality from the legacy platform genuinely missing?
**No.** After walking every legacy module, everything either:
- Already exists (Kill posture, Explorer, Paper-as-status, Mission KPIs, Advisory feed, Modes)
- Is intentionally re-routed through Master Bot / Approvals / Passport (Discover, Optimize, Promote)
- Is a power-user knob that should stay in Advanced Lens / Settings, not the shell (thresholds, exploration governance)
- Is a Sprint 3 candidate that is safe to omit for VPS launch (Portfolios surface, Portfolio Builder wizard replacement)

**No blocker for VPS deployment.**

### 4.2 Should any capabilities be exposed via contextual panels rather than sidebar items?
**Yes — six specifically:**
1. Exploration governance knobs → Advanced Lens / Settings (L3)
2. Ingestion / breach / mutation timeline slices → ⌘K palette actor-facet presets (L4, L8, L19)
3. Raw pipeline logs → EvidenceDrawer via ⌘K (L12)
4. Optimization / cycle triggers → Approvals origin (L7, L20)
5. Deployment promotion → Passport action row (L21)
6. Risk thresholds → Settings sub-section (L18)

**None of these require a new sidebar item.**

### 4.3 Can the current UI be improved with small refinements while preserving Design Freeze?
**Yes — six semantic-only refinements (all use existing primitives):**

| # | Refinement | Files | Effort | Design-Freeze impact |
|---|---|---|---|:-:|
| R1 | **Portfolio-equity metric block** added to Mission Control (4th slot) | `MissionControl.jsx`, `fixtures.js` | 15 min | Zero — reuses MetricBlock |
| R2 | **`next-tick` postmark** in Master Bot plan card | `MasterBot.jsx`, `fixtures.js` | 10 min | Zero — same postmark pattern as `started` |
| R3 | **Three ⌘K palette proposal entries** (`Propose new strategy…` / `Run optimization cycle…` / `Promote strategy #… to live`) | `CmdKPalette.jsx`, `Approvals.jsx` (optimistic append) | 30 min | Zero — extends existing palette |
| R4 | **Passport action row** with `[promote to live]` / `[demote to paper]` buttons dropping an ApprovalCard | `StrategyPassport.jsx` | 20 min | Zero — reuses button + Chip patterns |
| R5 | **Two Timeline actor-facet presets** (`ingestion`, `breaches`) | `Timeline.jsx`, `fixtures.js` | 15 min | Zero — extends existing FacetBar |
| R6 | **Two optional Explorer columns** (`form/challenge`, `safe-risk`) as an Advanced Lens toggle | `Strategies.jsx`, `fixtures.js` | 15 min | Zero — TableTile columns are data-driven |

Total effort ≤ **~2 engineer-hours**. All six use only existing primitives, existing tokens, existing testids. No new sidebar item. No layout redesign.

### 4.4 Would you recommend any refinements before VPS deployment?
**Optionally, R1, R2, R3 (Priority: High).** These three close the three legacy-workflow gaps (A/B/C from §3) with the highest operator-perceived value:
- R1 restores portfolio-equity visibility that legacy operators expect on the dashboard
- R2 restores the "when will discovery next fire?" affordance operators used to read from the Auto-Discovery Scheduler
- R3 restores explicit affordances for the three implicit workflow verbs (propose, optimize, promote)

R4–R6 are quality-of-life polish and are **safe to defer to a Sprint 2.5 patch or Sprint 3**.

**None of R1–R6 are blockers for VPS deployment.** The new UI, as it currently stands (Sprint 2 · N1–N5 complete), is **operator-safe, freeze-compliant, and functionally sufficient** for a Production Candidate cut.

---

## 5. Final recommendation

**✅ Ready for VPS deployment — with three optional pre-flight refinements (R1, R2, R3) if the operator wants to close the three legacy-workflow gaps before shipping.**

### Option A (recommended · zero delay)
Cut `v1.3.0-sprint2-complete` as-is. Deploy to VPS. Run smoke checklist. Sign the Production Candidate Report. Land R1–R6 as a **Sprint 2.5 patch** after the operator's first 24 hours on the deployed build (feedback-driven).

### Option B (2-hour delay · closes workflow gaps A/B/C now)
Land **R1 + R2 + R3** as a tightly-scoped Sprint 2 tail patch **before** cutting the tag. Re-run Playwright + smoke test. Then deploy. Recommended if the operator wants the deployed build to feel "workflow-complete" out of the gate.

### Option C (defer entirely to Sprint 3)
Ship as-is. Bundle R1–R6 into Sprint 3 alongside the deferred token review, visual-regression matrix expansion, and Portfolio surface.

**My recommendation: Option A.** The new UI is already a materially better product than the legacy interface; the three gaps are real but not critical; validating the deployed build with the operator first will let R1–R3 be tuned to observed usage rather than guessed usage. Sprint 3 becomes the natural home for R1–R6 alongside the token review.

---

## 6. Design Freeze compliance (audit-level)

- **Tokens:** unchanged — 0 recommended token edits.
- **Layouts:** unchanged — 0 recommended layout changes; all refinements reuse primitives.
- **Sidebar:** unchanged — 0 new sidebar items recommended. Every legacy top-nav entry either maps to an existing surface or moves into ⌘K / Advanced Lens.
- **Adapter boundary:** unchanged — R1–R6 all extend fixtures or add ApprovalCard drops through existing adapters.
- **Backend freeze:** unchanged — 0 backend edits proposed; all refinements are frontend-only + fixture-first.

**No Design Freeze violation exists in the current build.**
**No Design Freeze violation would be introduced by R1–R6.**

---

*End of Sprint 2 Legacy Capability & UX Audit.*

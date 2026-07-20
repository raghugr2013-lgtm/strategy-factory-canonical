# E1 — Strategy Experience

> The end-to-end journey of **one strategy** from generation through
> validation, optimization, certification, portfolio candidacy,
> production, and eventual retirement. Every surface the strategy
> touches, every actor that acts on it, every operator moment along
> the way.
>
> **This is Strategy Factory's central experience.** All other journeys
> (Auth, First-Time, Daily, Cross-Module) exist to support this one.
>
> Layered on **Bible v2.1** (`FRONTEND_DESIGN_BIBLE_V2_1.md`). Uses D2
> Timeline, D3 Approval Center, D4 Master Bot & Workforce, D5 Signature
> Graphics, D6 Personalization Modes, D7 State Library, D8 Sprint plan.
>
> Prepared 2026-07-20. First E-series deliverable per operator
> sequencing (D8 §13.6).

---

## 0. Design Principles Checklist (18 items — permanent quality gate)

E1 confirms:

- [x] **Invisible Luxury** — the strategy's lifetime is *narrated*, not manifested through celebratory chrome. A strategy reaching production is a Timeline row, not a fireworks display.
- [x] **Everything Connected** — every stage of the journey exposes lineage back to genesis; a strategy in Production still surfaces its Generation evidence one click away.
- [x] **Progressive Disclosure** — the operator sees the *storyline* of a strategy at Layer 1–3; provenance triples, method chips, and diagnostic overlays appear only under Advanced Lens.
- [x] **Evidence First** — no stage transition happens without evidence citation; even *rejection* carries evidence.
- [x] **Persona Awareness** — Executive sees a strategy's *outcome*; Operations sees its *current stage*; Research sees its *lineage*; Developer sees its *provenance triples*.
- [x] **Mission Control First** — Mission Control's Attention panel and Pipeline column both reference strategies; a strategy needing operator judgement surfaces there before anywhere else.
- [x] **Accessibility (WCAG 2.2 AA)** — every stage transition announces via screen-reader; keyboard-navigable from any surface to any other.
- [x] **Motion Discipline** — stage transitions animate with Bible §6.1 tiers; no motion for the sake of drama.
- [x] **Design Token Compliance** — every stage's chip colour drawn from `--sig-*` tokens.
- [x] **Six-Signal Rule** — the eight pipeline stages use only P/W/F/A/I letter glyphs with `--sig-*` fills; no ninth glyph.
- [x] **Lineage Validation** — every stage exposes `→ lineage graph` and every artefact ancestor is one hop away in the Lineage bar (Bible §10.1).
- [x] **Empty-State Quality** — journey-specific empty states authored (§7); every failure path has a legible destination.
- [x] **Consistency** — every stage renders via the same primitive vocabulary (PipelineStageBar · MetricBlock · ActivityRow · ApprovalCard); no per-stage components.
- [x] **Explainability** — every stage answers *What is it · Why is it here · What happens next · What can I do*.
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice narrates every stage transition; no `strategy #47 moved to state=validated`.
- [x] **Context Never Lost (Bible §1.4.4)** — a strategy the operator investigates remains highlighted across Mission Control, Timeline, Approvals, Portfolio, Factory, Explorer.
- [x] **State Memory (Bible §1.4.5)** — returning to an investigation restores the exact scroll, expanded panels, drawer state.
- [x] **Purpose Before Status (D4 §5.1.1)** — every strategy card leads with *what it does* before *what stage it's in*.
- [x] **Decision Identity (D6 §8.1a)** — the strategy's confidence, risk, evidence set, lineage are byte-identical across all four modes.

---

## 1. Purpose

Strategy Factory exists to *create, evaluate, govern, deploy, and
retire* strategies. Every other capability (Knowledge Base, Learning
Division, Governance rails, Portfolio Division) exists in service of
this lifecycle.

E1 codifies:

1. **The canonical stages** a strategy passes through (§2).
2. **The journey map** — how a single strategy travels those stages
   (§3).
3. **The per-stage surface reference** — where in the product the
   strategy appears, how it looks, what operators can do (§4–§11).
4. **The failure paths** — rollback, rejection, contradiction, drift
   (§12).
5. **The mode-specific perspectives** — how E/O/R/D see the same
   strategy differently while its identity remains invariant (§13).
6. **The copy library** — Division-voice narrative for every stage
   transition (§14).
7. **The data contract** — the canonical Strategy object and its
   presentation across surfaces (§15).

**Anti-goals**:

- Not a task-management flow (operators don't move strategies through
  stages; the Factory does).
- Not a manual pipeline (there is no "click to advance to next stage"
  button).
- Not a Kanban board.
- Not a wizard.

---

## 2. The strategy lifecycle — 8 canonical stages + 2 terminals

The strategy passes through **eight canonical stages** (Bible §10.1)
plus **two terminal states** (Retired, Failed). This taxonomy is
inviolate; no additions without a v-major bump.

```
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
   │  Generated  │  ─▶  │  Validated  │  ─▶  │  Optimized  │  ─▶  │  Certified  │
   └─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
                                                                          │
                                                                          ▼
   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────────┐
   │   Retired   │  ◀─  │ Production  │  ◀─  │  Approved   │  ◀─  │ Portfolio       │
   └─────────────┘      └─────────────┘      └─────────────┘      │ candidate       │
                                                                   └─────────────────┘
                                                                          │
                                                                          ▲
                                                                   Knowledge stored
```

Plus the failure terminal:

```
   at ANY stage:  Failed   (evidence carried forward; strategy inspectable but inert)
```

### 2.1 Canonical stage taxonomy

| # | Stage | Owner Division | Duration typical | HITL gate? |
|---|---|---|---|---|
| 1 | **Generated** | Research | seconds | no |
| 2 | **Validated** | Validation | minutes–hours | no |
| 3 | **Optimized** | Mutation | hours | no |
| 4 | **Certified** | Certification | seconds | no |
| 5 | **Knowledge stored** | Knowledge | seconds (concurrent) | no |
| 6 | **Portfolio candidate** | Portfolio | passive | no |
| 7 | **Approved** | Master Bot + **Operator (HITL)** | operator decision | **YES — the promotion gate** |
| 8 | **Production** | Execution | ongoing | no |
| — | **Retired** | Learning proposes + Operator approves | operator decision | **YES — the retirement gate** |
| — | **Failed** | any Division | terminal on failure | no (post-mortem is optional) |

### 2.2 Two HITL gates — the only operator-decision moments

The lifecycle has **exactly two operator-decision moments**:

1. **The promotion gate** (Stage 6 → 7). Master Bot recommends
   promotion of a Portfolio candidate to Production. The operator
   approves, defers, denies, or routes to reviewer. This is the single
   most important operator moment in the product.
2. **The retirement gate** (Stage 8 → Retired). Learning Division
   proposes retirement of a Production strategy due to drift, loss,
   contradiction, or ranking-fall. The operator approves, defers,
   denies, or routes to reviewer.

**No other stage transition requires operator action.** The Factory
runs its own pipeline; the operator judges only the two gates above.

This is the emotional core of the Strategy Experience: **operators
observe autonomy; they decide only at the two moments the Factory
cannot decide for itself.**

---

## 3. Journey map — one strategy, from birth to retirement

```
DAY 0                                                                         DAY N

┌──────────────────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● Generated                                                                     │
│     Research Division retrieved regime-detection paper.                          │
│     Master Bot spawned worker-01 to score it against seed corpus.                │
│     candidate #47 born at 12:14 UTC.                                             │
│                                                                                  │
│         │  (seconds)                                                             │
│         ▼                                                                        │
│  ● Validated                                                                     │
│     Validation Division ran 30-day walk-forward.                                 │
│     Sharpe 1.14 · max drawdown 8.2 % · win-rate 54 %.                            │
│     Passed gate: confidence 0.71 ≥ threshold 0.60.                               │
│                                                                                  │
│         │  (minutes–hours)                                                       │
│         ▼                                                                        │
│  ● Optimized                                                                     │
│     Mutation Division optimised parameters over 3 seed variations.               │
│     Best variant: EMA-20 / RSI-2 / BB-14. Sharpe 1.31.                           │
│                                                                                  │
│         │  (hours)                                                               │
│         ▼                                                                        │
│  ● Certified                                                                     │
│     Certification Division checked FTMO-100k rules.                              │
│     Passed: max daily loss ≤ 5 %, max drawdown ≤ 10 %.                           │
│                                                                                  │
│         │  (seconds)                                                             │
│         ▼                                                                        │
│  ● Knowledge stored (concurrent with Certified)                                  │
│     Knowledge Base indexed provenance + method + parameters.                     │
│     Trust tier: provisional (pending Production evidence).                       │
│                                                                                  │
│         │                                                                        │
│         ▼                                                                        │
│  ● Portfolio candidate                                                           │
│     Portfolio Division added candidate #47 to shortlist.                         │
│     Correlation vs current portfolio: 0.32 (acceptable).                         │
│                                                                                  │
│         │  (passive — awaiting Master Bot recommendation)                        │
│         ▼                                                                        │
│  ⏸ Approved (HITL gate #1 — the promotion gate)                                  │
│     Master Bot requests: "Approve promotion of candidate #47 to Production?"    │
│     Operator reviews evidence · approves at 15:42 UTC.                           │
│     Approval Card resolves; Timeline records the decision.                       │
│                                                                                  │
│         │  (operator action)                                                     │
│         ▼                                                                        │
│  ● Production                                                                    │
│     Execution Division activates strategy across matched brokers.                │
│     First 24 h: 12 fills, p95 fill quality 1.1 pips.                             │
│     Learning Division watches for drift.                                         │
│                                                                                  │
│         │  (ongoing — days, weeks, months)                                       │
│         ▼                                                                        │
│  ⏸ Retired (HITL gate #2 — the retirement gate)                                  │
│     Learning Division proposes retirement.                                       │
│     Reason: 14-day rolling Sharpe fell below 0.6 (drift detected).              │
│     Operator reviews evidence · approves retirement at N+28d.                    │
│                                                                                  │
│         │  (operator action)                                                     │
│         ▼                                                                        │
│  ○ Retired                                                                       │
│     Execution Division stops the strategy on all brokers.                        │
│     Knowledge Base retains lineage forever (immutable).                          │
│     Learning Division ingests the retirement evidence into its corpus.          │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Total duration for a healthy strategy:** Day 0 (Generation) → Day 4
(Approved) → Day N (Retired, N = 30–365 typical).

**Duration variance:** the Factory can produce a strategy end-to-end in
under 4 hours in optimal conditions; in cautious modes, Stages 2–4 can
extend to days.

---

## 4. Actors and Divisions per stage

Each stage has a **primary Division** (does the work), one or more
**observing Divisions** (may raise flags), and **surface responsibility**
(where the operator sees the stage).

| Stage | Primary | Observing | Surface |
|---|---|---|---|
| Generated | Research | Knowledge (dedup) | Timeline row + Explorer entry |
| Validated | Validation | Governance (hard rails) | Timeline row + PipelineStageBar update |
| Optimized | Mutation | Validation (re-check) | Timeline row + PipelineStageBar update |
| Certified | Certification | Governance | Timeline row + PipelineStageBar update |
| Knowledge stored | Knowledge | Learning | Timeline row + Knowledge Graph edge (G3) |
| Portfolio candidate | Portfolio | Governance (correlation limit) | Portfolio module + PipelineStageBar update |
| **Approved (HITL)** | Master Bot + Operator | Governance | Approval Center + Timeline highlighted row + Mission Control Attention |
| Production | Execution | Learning, Governance | Execution module + Portfolio Risk Surface (G6) |
| **Retired (HITL)** | Learning + Operator | Governance | Approval Center + Timeline highlighted row |

---

## 5. Stage-by-stage deep-dive

Each subsection follows the same pattern:
- **Entry condition** — what event promotes to this stage
- **What happens** — actions the Division takes
- **Surface where the strategy appears**
- **Copy specimen** — Division-voice narrative
- **Operator affordances** — what the operator can do at this stage
- **Failure paths** — how this stage can fail; where the strategy goes
- **Exit condition** — what promotes to next stage

### 5.1 Stage 1 · Generated

**Entry.** A generation event fires — either Master Bot's plan step
("Generate 5 EURUSD candidates") or Research Division's continuous
retrieval-and-synthesis loop.

**What happens.** Research Division spawns a worker; worker composes a
strategy definition from seeds (methods · parameters · symbol · TF ·
risk envelope). Strategy record created with a Berkeley-Mono id
(`strat_bb_ema_rsi_v3` — meaningful mnemonic, never a UUID at L1).

**Surface where visible:**

- **Timeline** (right rail): new activity row —
  *"Research Division generated candidate #47 · EURUSD 5m breakout."*
- **Explorer** (`/c/strategies`): entry appears; PipelineStageBar shows
  first dot filled `●` + others hollow `○`.
- **Master Bot Dashboard** (`/c/factory`): if generation was
  plan-driven, plan step ticks to `✓`.

**Copy specimen** (Timeline row · Simple):
```
[12:14]  Research Division generated candidate #47 · EURUSD 5m breakout.
                                                          →  view evidence
```

Advanced Lens adds:
```
   [method: retrieval + synthesis]  [conf: 0.68]  [worker: research-01]  [dur: 3.4 s]
```

**Operator affordances at this stage:**

- View the strategy in Explorer.
- Pin the strategy to compare with peers.
- Open Evidence Drawer for the generation lineage.
- No approval required.
- No manual promotion.

**Failure paths:**

- **Duplicate detected** — Knowledge Base flags near-duplicate; strategy
  transitions to `Failed` with reason `duplicate of strat_...`.
  Copy: *"Research Division discarded candidate #47 as a near-duplicate
  of strat_bb_ema_rsi_v2."* — Timeline records; strategy inspectable in
  Explorer with `⨯` glyph.
- **Generation error** — worker fails; strategy transitions to
  `Failed` with reason `generation_error`.

**Exit condition.** Passes Knowledge dedup + governance rails
(basic checks); auto-advances to Validated.

### 5.2 Stage 2 · Validated

**Entry.** Validation Division picks up any Generated strategy that
passed dedup.

**What happens.** Validation Division runs walk-forward tests
(typically 30-day rolling window across the last N periods).
Computes: Sharpe · max drawdown · win-rate · profit factor · trade
count · latency-to-fill p95. Governance hard rails check (violates
FTMO? violates house risk envelope?).

**Surface where visible:**

- **Timeline row:** *"Validation Division ran 30-day walk-forward on
  candidate #47 · Sharpe 1.14."*
- **Explorer:** PipelineStageBar advances — second dot filled.
- **Master Bot Dashboard:** plan step ticks if plan-driven.

**Copy specimen:**
```
[12:22]  Validation Division ran 30-day walk-forward on candidate #47.
         Sharpe 1.14 · drawdown 8.2 % · confidence 0.71.
                                                          →  view evidence
```

**Operator affordances:**

- View backtest evidence (equity curve, per-trade PnL, drawdown chart).
- Pin the strategy for comparison.
- Explorer detail page shows validation metrics.
- No approval required.

**Failure paths:**

- **Fails Sharpe threshold** (< 0.60 default) — transitions to `Failed`
  with reason `sharpe_below_threshold_0.42`.
  Copy: *"Validation Division rejected candidate #47 · Sharpe 0.42 below
  threshold 0.60."*
- **Hard-rail violation** — Governance intervenes; transitions to
  `Failed` with reason `hard_rail_max_dd_11%`.
  Copy carries `--sig-crit` tint on this row (single instance of red in
  the lifecycle otherwise).

**Exit condition.** Passes all validation metrics + Governance rails →
Optimized.

### 5.3 Stage 3 · Optimized

**Entry.** Validated strategies auto-queue for Mutation Division.

**What happens.** Mutation Division generates parameter variations
(3–7 typical); each variant is re-validated; best variant selected;
strategy record updates with optimised parameters.

**Surface where visible:**

- **Timeline row:** *"Mutation Division optimised candidate #47 over 5
  parameter variants. Best variant: EMA-20 / RSI-2 / BB-14 · Sharpe
  1.31."*
- **Explorer:** third dot filled; parameter chip strip visible under
  Advanced Lens.
- **Master Bot Dashboard:** plan step ticks.

**Copy specimen:**
```
[13:04]  Mutation Division optimised candidate #47 over 5 variants.
         Best: EMA-20 / RSI-2 / BB-14 · Sharpe 1.31 (+15 %).
                                                          →  view evidence
```

**Operator affordances:**

- View before/after comparison (pin the pre-Mutation state via Pinned
  Preview from an earlier moment; Sprint 2+).
- View parameter search-space explored (Advanced Lens).
- No approval required.

**Failure paths:**

- **Optimization diverges** (Sharpe of best variant < validated
  version) — Mutation Division falls back to Validated parameters;
  Timeline: *"Mutation Division kept validated parameters for
  candidate #47 · no variant outperformed."* Not a failure; a legitimate
  outcome.
- **Compute budget exhausted** — Mutation Division stops; strategy
  proceeds with best-of-explored variants; Timeline notes the
  budget-exhaustion.

**Exit condition.** Auto-advances to Certified.

### 5.4 Stage 4 · Certified

**Entry.** Optimised strategy queues for Certification.

**What happens.** Certification Division runs rule-set-specific checks
(FTMO-100k, MyForexFunds, house rules) — determines *which* rule-sets
the strategy is *eligible* for. Multiple certifications possible in
parallel (a strategy may certify for FTMO but not for MyForexFunds).

**Surface where visible:**

- **Timeline row:** *"Certification Division certified candidate #47
  for FTMO-100k · rejected for MyForexFunds (max daily loss risk)."*
- **Explorer:** fourth dot filled + certification chips visible.
- **Prop Firm module:** strategy appears in the FTMO-100k eligible
  list.

**Copy specimen:**
```
[13:07]  Certification Division certified candidate #47 for FTMO-100k.
         Rejected for MyForexFunds · max daily loss risk 6.1 %.
                                                          →  view evidence
```

**Operator affordances:**

- View which prop firms the strategy is eligible for.
- View the specific rule that failed if any.
- No approval required.

**Failure paths:**

- **Zero rule-sets pass** — strategy transitions to `Failed` with reason
  `no_prop_firm_eligible`.
- **Ambiguous rule interpretation** — Governance Advisory raised;
  strategy holds at Certified pending Governance clarification (this is
  rare; usually resolved automatically).

**Exit condition.** At least one rule-set passes → advances to
Knowledge storage + Portfolio candidate (concurrent).

### 5.5 Stage 5 · Knowledge stored (concurrent with Certified)

**Entry.** Any Certified strategy auto-stores its provenance in the
Knowledge Base.

**What happens.** Knowledge Base creates an immutable record:
provenance triple (`origin`, `trust_tier`, `signed_by`), full lineage
back to Generation, all validation and optimization evidence,
certification results. Trust tier assigned `provisional` (pending
Production evidence).

**Surface where visible:**

- **Timeline row:** *"Knowledge Base indexed candidate #47 · trust tier
  provisional."*
- **Knowledge Graph** (G3, Sprint 3): a new node appears with a
  `provisional` amber ring.
- **Explorer:** fifth dot filled.

**Copy specimen:**
```
[13:07]  Knowledge Base indexed candidate #47 · trust tier provisional.
                                                          →  view lineage
```

**Operator affordances:**

- View lineage back to Generation (Lineage bar Sprint 1; Graph mode
  Sprint 2).
- No approval required.

**Failure paths:**

- **Contradiction detected** — Knowledge Base finds this strategy
  contradicts an existing `verified`-tier record; Governance Advisory
  raised. This is rare; usually indicates a Learning-Division insight
  is stale.

**Exit condition.** Auto-advances (Portfolio candidate is a parallel
transition, not sequential).

### 5.6 Stage 6 · Portfolio candidate

**Entry.** Any Certified strategy is eligible; Portfolio Division adds
it to the candidate pool.

**What happens.** Portfolio Division computes correlation of this
strategy against the current live portfolio; assigns a portfolio-fit
score; awaits Master Bot's promotion recommendation.

**Surface where visible:**

- **Timeline row:** *"Portfolio Division added candidate #47 to the
  shortlist · correlation 0.32."*
- **Portfolio module:** entry in the candidates table.
- **Explorer:** sixth dot filled.
- **Master Bot Dashboard:** if plan includes promotion, plan step
  advances to "awaiting operator" (HITL gate imminent).

**Copy specimen:**
```
[13:08]  Portfolio Division added candidate #47 to the shortlist.
         Correlation vs live portfolio 0.32.
                                                          →  view portfolio fit
```

**Operator affordances:**

- View Portfolio Risk Surface (G6, Sprint 4) with candidate marked.
- Pin the candidate.
- View correlation matrix (Advanced Lens).
- No approval yet — candidate is passive until Master Bot recommends
  promotion.

**Failure paths:**

- **Correlation limit exceeded** (default > 0.85) — Portfolio Division
  demotes back to Certified with reason `correlation_too_high_0.91`;
  strategy remains available for future portfolio consideration.
- **Portfolio full** — candidate holds indefinitely; no failure state;
  Master Bot decides whom to swap.

**Exit condition.** Master Bot generates a promotion recommendation →
Approval Center receives it → HITL gate opens.

### 5.7 Stage 7 · **Approved** — the promotion gate (HITL #1)

**This is the emotional core of the product.**

**Entry.** Master Bot decides to promote a Portfolio candidate. A
recommendation is generated with:
- Confidence score
- Risk classification (low / medium / high)
- Rollback SLA (target seconds if rolled back post-promotion)
- Full evidence link
- Full lineage

The recommendation lands in Approval Center; Master Bot pauses its
plan; the danger ribbon does NOT fire (this is not a critical alert);
the header approvals chip increments; a Timeline row appears.

**Surface where visible:**

- **Approval Center** (`/c/approvals`): full Approval Card per D3 §2.
- **Header approvals chip:** `[ ● 1 approval ]` (or count total).
- **Timeline row:** *"Master Bot requests: approve promotion of
  candidate #47 to Production."* (highlighted row per D2 §5).
- **Master Bot Dashboard:** plan step in `⏸` state with cross-link to
  the approval.
- **Mission Control Attention panel:** severity `advisory` (if risk
  = low) or `warn` (if risk = medium/high).
- **Explorer:** seventh dot in the PipelineStageBar renders in `⏸`
  state (awaiting decision).

**Approval Card specimen** (per D3 §2):

```
┌────────────────────────────────────────────────────────────────────┐
│  MASTER BOT                                    RISK: MEDIUM       │
│                                                                    │
│  Approve promotion of candidate #47 to Production                  │
│                                                                    │
│  ── recommendation ────────────────────────────────────────       │
│  EURUSD 5m breakout · EMA-20 / RSI-2 / BB-14                       │
│  Backtest Sharpe 1.31 · walk-forward Sharpe 1.14 · dd 8.2 %        │
│                                                                    │
│  ── upstream ──────────────────────────────────────────────       │
│  Research Division · candidate #47 · 2 h ago                       │
│  Validation Division · confidence 0.71 · 30-d walk-forward         │
│                                                                    │
│  ── downstream ────────────────────────────────────────── ─       │
│  Will enter Production on 3 FTMO-100k accounts · risk 0.4 % max→  │
│                                                                    │
│  ── actions ────────────────────────────────────────────────      │
│  [ Approve ]   [ Defer ]   [ Deny with reason ]   [ Route ]        │
│                                                                    │
│  Rollback SLA: < 30 s if reverted within 24 h                      │
└────────────────────────────────────────────────────────────────────┘
```

**Operator affordances** (4 canonical actions per D3):

1. **Approve** → Master Bot commits promotion; strategy transitions to
   Production; Timeline row updates *"Operator approved promotion of
   candidate #47."*
2. **Defer** → snooze for N hours; approval stays open; Timeline row
   *"Operator deferred approval for 4 h."*
3. **Deny with reason** → Master Bot records the denial; strategy
   returns to Portfolio candidate (may be re-recommended later);
   Timeline row *"Operator denied promotion of candidate #47 · reason:
   correlation risk."*
4. **Route** → forwards to a reviewer (Sprint 3+ for multi-user);
   Sprint 1 has this action grayed out with tooltip *"Reviewer routing
   arrives in Sprint 3."*

**Everywhere-Actionable rule** (Bible §19.6): the operator can approve
directly from:
- The Approval Card in Approval Center (canonical location).
- The Timeline row via expansion (D3 §1.4 dual-path).
- The header approvals chip drawer (compact card).
- The Master Bot Dashboard plan step (cross-link opens Approval Center
  focused on this card).
- The Mission Control Attention panel (drawer opens Approval Center).

**All five paths commit the same action against the same object with
byte-identical result** (Decision Identity, D6 §8.1a).

**Copy specimen for the approval Timeline row after action** (D2 §5):
```
[15:42]  Operator approved promotion of candidate #47 to Production.
                                                          →  view outcome
```

**Failure paths:**

- **Commit fails** — Master Bot cannot promote (subsystem error);
  Approval Center shows `ap-error-action-failed` (D7 §10.5); no state
  change; retry available.
- **Operator denies** — strategy returns to Portfolio candidate
  (Stage 6); Timeline records denial reason as permanent evidence.
- **Rollback within 24 h** — operator invokes rollback; strategy
  transitions back to Portfolio candidate; Timeline records
  *"Operator rolled back promotion of candidate #47."*

**Exit condition.** Approve action commits → Stage 8 Production.

### 5.8 Stage 8 · Production

**Entry.** Operator approves at HITL gate #1.

**What happens.** Execution Division activates the strategy on all
matched broker accounts. Learning Division begins watching (rolling
Sharpe, rolling drawdown, fill quality). Governance rails monitor
kill-posture triggers.

**Surface where visible:**

- **Timeline row:** *"Execution Division activated strategy #47 on 3
  FTMO-100k accounts. First fill at 15:44."*
- **Execution module** (`/c/execution`): live strategy card visible.
- **Portfolio module:** now a live position, not a candidate.
- **Master Bot Dashboard:** plan step ticks to `✓` (final step of the
  plan, if this was the promoted-candidate plan).
- **Explorer:** eighth dot filled; PipelineStageBar all `●`.
- **G5 Execution Constellation** (Sprint 3): fills arrive as 6-pointed
  stars.
- **G6 Portfolio Risk Surface** (Sprint 4): allocation re-computes.

**Copy specimen** (post-promotion Timeline row):
```
[15:44]  Execution Division activated candidate #47 on 3 accounts.
         First fill at 15:44 · slippage 0.4 pips.
                                                          →  view broker detail
```

**Operator affordances:**

- View live P&L in Execution / Portfolio.
- View fill quality in G5 Execution Constellation.
- View Learning Division's rolling metrics.
- **Manual pause** available via Governance module (kill posture is
  the emergency stop; per-strategy pause is a governance-gated flow
  reserved for later Sprints).
- Pin the strategy for continuous observation.

**Failure paths:**

- **Broker disconnects** — Execution Division pauses observations on
  that broker; Timeline row `exec-error-broker-unreachable`; other
  brokers continue.
- **Kill posture armed** — all Production strategies pause immediately
  (danger ribbon fires); Timeline records the pause reason.
- **Drift detected** (rolling Sharpe falls below floor) — Learning
  Division escalates to Retirement gate (Stage 8 → Retired transition
  begins).

**Exit condition.** Learning Division proposes retirement OR operator
manually retires (via Governance, reserved). → HITL gate #2.

### 5.9 Stage 9 · **Retired** — the retirement gate (HITL #2)

**Entry.** Learning Division detects drift, loss, contradiction, or
ranking-fall. Composes a retirement recommendation and routes to
Approval Center.

**Reasons for retirement** (Learning Division authors the recommendation
copy in Division voice):

- *"14-day rolling Sharpe fell below 0.6 · drift detected."*
- *"Max drawdown crossed operator-set floor · 12.3 % vs limit 10 %."*
- *"Contradiction detected: Learning Division's rule change invalidates
  this strategy's premise."*
- *"Ranked below 50th percentile in the portfolio · demotion candidate."*

**Surface where visible:**

- **Approval Center:** full Approval Card (per D3 §2) with `origin =
  learning`, source = Learning Division.
- **Timeline row:** *"Learning Division proposes retiring strategy #47
  · reason: 14-day Sharpe 0.42."* (highlighted per D2 §5).
- **Header approvals chip.**
- **Mission Control Attention panel** (severity: `warn` typical).

**Approval Card specimen:**

```
┌────────────────────────────────────────────────────────────────────┐
│  LEARNING DIVISION                             RISK: MEDIUM       │
│                                                                    │
│  Retire strategy #47                                               │
│                                                                    │
│  ── recommendation ────────────────────────────────────────       │
│  14-day rolling Sharpe fell to 0.42 (below 0.60 floor).            │
│  Cumulative drawdown 9.8 % · approaching operator limit 10 %.      │
│                                                                    │
│  ── upstream ──────────────────────────────────────────────       │
│  Production strategy #47 · active 28 days · 342 trades             │
│  Learning Division · daily rolling metrics                         │
│                                                                    │
│  ── downstream ────────────────────────────────────────── ─       │
│  Will stop on all brokers · release 0.4 % allocation for reuse  →  │
│                                                                    │
│  ── actions ────────────────────────────────────────────────      │
│  [ Approve ]   [ Defer ]   [ Deny with reason ]   [ Route ]        │
│                                                                    │
│  Rollback SLA: none · retirement is terminal                       │
└────────────────────────────────────────────────────────────────────┘
```

**Operator affordances** (same 4 canonical actions):

1. **Approve** → Execution Division stops the strategy on all brokers;
   strategy transitions to Retired (terminal).
2. **Defer** → snooze; Learning Division continues monitoring;
   retirement re-proposed if metrics don't recover.
3. **Deny with reason** → strategy continues in Production; Learning
   Division notes the operator's rationale (feeds into Learning's
   meta-training).
4. **Route** → Sprint 3+.

**Copy specimen after retirement:**
```
[Day N+28 · 11:04]  Operator approved retirement of strategy #47.
                     Execution Division stopped on 3 brokers · final PnL +$247.
                     Knowledge Base retains lineage.
                                                          →  view outcome
```

**Failure paths:**

- **Rollback the retirement** — Sprint N+; the retirement is treated
  as a governance action, not a strategy change; rollback = re-approve
  a new Production promotion using the same strategy's parameters.

**Exit condition.** Retired = terminal. Knowledge Base retains lineage
forever (immutable). Learning Division ingests the full lifecycle as
training evidence.

### 5.10 Terminal · Failed

At any pre-Production stage, a strategy can transition to `Failed`.
This is not an error state; it is a legitimate lifecycle terminal.

**Reasons** (each surfaces as its own copy specimen):

- `duplicate_of_<id>` — Knowledge dedup
- `sharpe_below_threshold_<n>` — Validation reject
- `hard_rail_violation_<rule>` — Governance reject
- `no_prop_firm_eligible` — Certification zero-passes
- `optimization_diverged` — Mutation fallback (soft-fail; strategy still
  inspectable)
- `contradiction_detected` — Knowledge Base flags contradiction with
  higher-tier record

**Surface where visible:**

- **Explorer:** strategy shows `⨯` on the failing stage's dot in
  PipelineStageBar; all subsequent dots grey `–`.
- **Timeline:** row records the failure with the reason chip.
- **Knowledge Base:** failed strategies are retained (lineage matters;
  post-mortem needs the record).

**Operator affordances:**

- View the failure evidence.
- Pin the failed strategy for reference.
- **No re-run action** at Sprint 1 (would be a governance-gated flow;
  Sprint N+ if ever). The Factory generates new strategies; failed
  ones stay failed.

---

## 6. Cross-cutting mechanisms per stage

Beyond the linear lifecycle, several mechanisms operate across stages.

### 6.1 Lineage — always accessible

Every strategy carries **complete lineage** (Bible §10) from Generation
forward. At every stage, the Lineage bar (Sprint 1) shows one hop up +
one hop down; the Lineage Graph mode (Sprint 2, Bible §10.2) shows
the full ancestor/descendant tree.

**Rule:** lineage is a truth (Decision Identity, D6 §8.1a) — the same
lineage renders identically across all four modes.

### 6.2 Pinned Preview — comparison across stages

Sprint 2 delivers Pinned Preview (Bible §7.12). Operators can pin two
strategies (or one strategy at two moments in its lifecycle) and
compare 2-up:

- Compare two candidate strategies before promotion.
- Compare a strategy pre- and post-Mutation.
- Compare a Production strategy with a portfolio peer.

### 6.3 Timeline — the narrative spine

Every stage transition emits a Timeline row (D2 §3). The Timeline is
the **narrative spine** of the strategy's life. Filtering the Timeline
by `strategy = <id>` produces the strategy's complete story in
Division voice — a signature Strategy Factory experience.

Sprint 1 delivers: filter Timeline by strategy via URL param
`?strategy=<id>` → Timeline shows only that strategy's rows in
chronological order.

### 6.4 Mission Control — surfaces the strategy under judgement

The strategy the operator most needs to judge (HITL gate open) surfaces
on Mission Control's Attention panel (Q6). Salience heuristic
(Bible §8.7): if the strategy's approval is `high` risk, the
Attention panel enlarges to demand attention.

### 6.5 Copilot — narrates on demand

Under Copilot (Bible §24), an operator can ask *"What's the story of
strategy #47?"* and receive a Division-voice narrative summary. Copilot
Never Invents — it cites Timeline events and evidence chips only.

**Sprint 3+** — trace-as-UI shows retrieval + reasoning under Advanced
Lens.

### 6.6 Knowledge Graph (G3) — visualise lineage across strategies

Sprint 3 delivers G3 (D5 §5). A strategy's lineage renders as a subgraph
within the wider Knowledge Graph — showing which knowledge items seeded
it, which peers share its parameters, which descendants it spawned.

---

## 7. Journey-specific empty states

Beyond D7's per-module empty states, the strategy journey has its own
authored states:

### 7.1 `strat-empty-no-strategies`
```
Icon        sparkles
Headline    Research Division has generated no strategies yet.
Purpose     Start your first research cycle to begin the lifecycle.
Actions     open Research · view activation plan
```

### 7.2 `strat-empty-none-in-portfolio-candidates`
```
Icon        layers
Headline    No strategies are in the Portfolio candidate pool.
Purpose     Certified strategies land here awaiting Master Bot's
            promotion recommendation.
Actions     view Certified strategies · view Explorer
```

### 7.3 `strat-empty-no-production-strategies`
```
Icon        pin
Headline    No strategies are currently in Production.
Purpose     This is expected during freeze.
Actions     view activation plan · view Portfolio candidates
```

### 7.4 `strat-detail-loading`
```
> 2 s:  Retrieving strategy #47 evidence across 8 lifecycle stages...
```

### 7.5 `strat-detail-error`
```
Icon        alert-triangle
Headline    Strategy detail could not be loaded.
Purpose     Retrying every 8 seconds.
Actions     view logs · developer
```

### 7.6 `strat-detail-failed-strategy` (informational, not error)
```
Icon        x-circle · muted
Headline    Strategy #47 is failed at Validation.
Purpose     Sharpe 0.42 below threshold 0.60. Retained for post-mortem.
Actions     view failure evidence · view Explorer
```
Colour `--sig-crit` on the icon only; body copy remains neutral. This
is a legible failure, not a scream.

---

## 8. Failure paths — the taxonomy

E1 codifies **7 failure paths** across the strategy lifecycle. Each
has a copy pattern, a landing surface, and an operator affordance.

| Path | Stage | Reason | Landing | Affordance |
|---|---|---|---|---|
| **F1 duplicate** | Stage 1 | Knowledge dedup | Explorer + Timeline | view dedup evidence |
| **F2 sharpe-below-threshold** | Stage 2 | Validation reject | Explorer + Timeline | view backtest |
| **F3 hard-rail-violation** | Stage 2 or 3 | Governance reject | Explorer + Timeline + Governance | view rule |
| **F4 no-prop-firm-eligible** | Stage 4 | Certification zero-passes | Explorer + Timeline | view certification detail |
| **F5 correlation-too-high** | Stage 6 | Portfolio reject | Explorer + Timeline + Portfolio | view correlation matrix |
| **F6 rollback-post-approval** | Post-Stage 7 | Operator rollback | Timeline + Approval Center | none — action already taken |
| **F7 retirement-approved** | Post-Stage 8 | Operator retirement | Timeline + Portfolio | view lineage |

Each path is *legible*, *inspectable*, and *reversible only via a
new lifecycle* (a rejected strategy doesn't "re-try"; the Factory
generates fresh candidates).

---

## 9. Mode-specific perspectives

The same strategy, viewed by four operators in four modes. Decision
Identity holds — every operator sees the same underlying object.

### 9.1 Executive perspective

Sees strategies as **outcomes**: 
- On `/c/briefing`: *"3 strategies reached Production yesterday. 2
  are contributing +0.4 % to portfolio return this week."*
- On Approval Center: only high-risk approvals surface by default
  (D6 §4.4 filter default: `risk = medium | high`).
- On strategy detail: PipelineStageBar visible; upstream stages
  collapsed to a narrative summary.

### 9.2 Operations perspective (default)

Sees strategies **as they move**: 
- On `/c/mission`: current-in-flight strategies visible in Attention
  panel + Approvals panel + Pipeline column.
- On strategy detail: full PipelineStageBar; every stage's evidence
  one click away.

### 9.3 Research perspective

Sees strategies **as lineage**:
- On `/c/research`: Explorer prominent; Knowledge Graph (G3) surfaces
  the strategy's ancestry and descendants.
- On strategy detail: Advanced Lens on by default; method chips
  visible.
- Copilot companion panel discusses the strategy's research lineage.

### 9.4 Developer perspective

Sees strategies **as provenance**:
- Every timeline row shows worker-id / method / duration / latency
  chips.
- Strategy detail includes the provenance triple everywhere.
- Failed strategies show the specific reason code.

**Decision Identity check:** in all four modes, the strategy's
confidence score, risk classification, lineage set, and approval state
are byte-identical.

---

## 10. Copy specimen library (Strategy Experience subset of D7)

The following Division-voice narrative library covers every stage
transition and every failure path. All specimens obey D7 §22 cadence
rules (≤ 90 chars, ≤ 4 lines).

### 10.1 Stage transitions (happy path)

| Stage | Copy |
|---|---|
| Generated | *"Research Division generated candidate #<id> · <symbol> <TF> <method>."* |
| Validated | *"Validation Division ran <window>-day walk-forward on candidate #<id> · Sharpe <n>."* |
| Optimized | *"Mutation Division optimised candidate #<id> over <n> variants. Best: <method> · Sharpe <n> (<±%>)."* |
| Certified | *"Certification Division certified candidate #<id> for <prop-firms>."* |
| Knowledge stored | *"Knowledge Base indexed candidate #<id> · trust tier <tier>."* |
| Portfolio candidate | *"Portfolio Division added candidate #<id> to the shortlist · correlation <n>."* |
| Approved (Timeline row) | *"Master Bot requests: approve promotion of candidate #<id> to Production."* |
| Approved (post-decision) | *"Operator approved promotion of candidate #<id> to Production."* |
| Production activated | *"Execution Division activated candidate #<id> on <n> <account-types>. First fill at <time>."* |
| Retired (Timeline row) | *"Learning Division proposes retiring strategy #<id> · reason: <reason>."* |
| Retired (post-decision) | *"Operator approved retirement of strategy #<id>. Execution Division stopped on <n> brokers."* |

### 10.2 Failure paths

| Path | Copy |
|---|---|
| F1 duplicate | *"Research Division discarded candidate #<id> as a near-duplicate of <parent-id>."* |
| F2 sharpe-below | *"Validation Division rejected candidate #<id> · Sharpe <n> below threshold <t>."* |
| F3 hard-rail | *"Governance blocked candidate #<id> · <rule> violated."* |
| F4 no-prop-firm | *"Certification Division found no eligible prop firm for candidate #<id>."* |
| F5 correlation | *"Portfolio Division demoted candidate #<id> · correlation <n> exceeds ceiling <c>."* |
| F6 rollback | *"Operator rolled back promotion of strategy #<id> · reason: <reason>."* |
| F7 retirement | *"Operator approved retirement of strategy #<id> · reason: <reason>."* |

### 10.3 Post-mortem summary (Copilot-generated · Sprint 3+)

*"Strategy #47 lived for 28 days. Generated by Research Division on
2026-06-22 from arxiv:2401.09883. Validated with Sharpe 1.14, optimised
to 1.31, certified for FTMO-100k. Promoted 2026-06-24; 342 trades
across 3 brokers; retired 2026-07-20 after 14-day Sharpe fell to 0.42.
Final PnL +$247."*

---

## 11. Data contract (frontend expectation · Feature Freeze respected)

The canonical `Strategy` object is composed by an adapter over
existing backend endpoints. **No new backend endpoints.**

```ts
type Strategy = {
  id: string;                              // "strat_bb_ema_rsi_v3"
  purpose_headline: string;                // Division voice · timeless · e.g. "EURUSD 5m breakout"
  symbol: string;
  timeframe: string;
  methods: string[];                       // e.g. ["EMA-20", "RSI-2", "BB-14"]
  current_stage: PipelineStage;            // one of the 8+2 canonical stages
  status: 'active' | 'failed' | 'retired' | 'in-progress';
  lifecycle: {
    generated_at: string;
    validated_at?: string;
    optimized_at?: string;
    certified_at?: string;
    knowledge_stored_at?: string;
    portfolio_candidate_at?: string;
    approved_at?: string;
    production_activated_at?: string;
    retired_at?: string;
    failed_at?: string;
    failure_reason?: string;
  };
  validation?: {
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    profit_factor: number;
    confidence: number;
    trade_count: number;
  };
  optimization?: {
    variants_explored: number;
    best_parameters: Record<string, unknown>;
    improvement_pct: number;
  };
  certification?: {
    eligible_prop_firms: string[];         // e.g. ["FTMO-100k"]
    rejected_prop_firms: Array<{ firm: string; reason: string }>;
  };
  knowledge?: {
    trust_tier: 'provisional' | 'verified' | 'rejected' | 'advisory';
    provenance: { origin: string; signed_by: string };
  };
  portfolio?: {
    candidate_since?: string;
    correlation_vs_live: number;
    fit_score: number;
  };
  production?: {
    activated_brokers: string[];
    trade_count: number;
    live_sharpe: number;
    live_drawdown: number;
    fill_quality_p95_pips: number;
  };
  lineage: {
    ancestors: LineageNode[];              // one hop for Sprint 1
    descendants: LineageNode[];
  };
  approvals?: Array<{ id: string; state: string; opened_at: string }>;
  advanced?: {
    worker_id?: string;
    method_chip?: string;
    provenance_triple: { origin: string; trust_tier: string; signed_by: string };
    duration_by_stage_ms: Record<string, number>;
  };
};
```

**Adapter location:** `services/strategy.js` — normalises data from:
- `/api/strategies/*` (existing)
- `/api/knowledge/*` (existing)
- `/api/portfolio/*` (existing)
- `/api/execution/*` (existing)
- `/api/master-bot/*` (existing)
- `/api/audit-log` (Timeline events)

Composes canonical `Strategy` object. Feature Freeze respected.

---

## 12. Journey verification checklist

For Sprint 1 acceptance of the Strategy Experience:

- ✅ 18-item Design Principles Checklist confirmed (§0)
- ✅ Every stage (§5) renders end-to-end in the shipped surfaces (Timeline · Explorer · Approval Center · Master Bot Dashboard · Mission Control)
- ✅ Both HITL gates (Stage 7 promotion · Stage 9 retirement) commit round-trip
- ✅ Everywhere-Actionable rule holds for the promotion approval (5 paths all commit identically)
- ✅ Lineage bar (Bible §10.1) renders one hop up + one hop down on every strategy detail
- ✅ Timeline filter by strategy (`?strategy=<id>`) shows chronological narrative
- ✅ Cross-module strategy highlighting works (Bible §1.4.4 CNL)
- ✅ Every failure path (§8) is inspectable in Explorer
- ✅ Every copy specimen (§10) matches Division-voice standard
- ✅ Every stage transition emits a Timeline row (D2 §3)
- ✅ Every stage exposes evidence link
- ✅ Decision Identity — swap between 4 modes on the same strategy: confidence, risk, evidence set, lineage byte-identical
- ✅ State Memory — return to a strategy investigation restores scroll, expanded panels, drawer
- ✅ Purpose Before Status — every strategy card leads with `purpose_headline` before `current_stage`
- ✅ Copy library (§10) applied across all shipped Timeline rows
- ✅ Sprint 1 non-goals honoured — Lineage Graph mode, Pinned Preview, G3/G5/G6/G7 all deferred to Sprint 2+

---

## 13. What E1 does NOT include

- Bulk-strategy operations (bulk approve · bulk retire) — belongs to
  D3 §5.2 (already covered) + Sprint 2 governance workflow.
- Multi-user reviewer routing — Sprint 3 auth.
- Strategy authoring by hand — the operator does not create
  strategies; the Factory does. This is a permanent product boundary.
- Strategy diff / edit UI — strategies are immutable after Generation;
  Mutation Division produces variants, but each variant is a new
  strategy record.
- Prop firm claim / challenge match orchestration — that's a downstream
  workflow (Prop Firm module) related to but distinct from the
  strategy lifecycle.
- Sound / haptic feedback — no audio or vibration in this product.

---

## 14. Next: E2 — Authentication Experience

Per D8 §13.6 (operator-directed sequencing 2026-07-20).

E2 will codify:

- First-login flow (SSO / password / invite / recovery).
- Session lifecycle and expiry recovery.
- Multi-mode users (assignment, switching, permissions).
- Logout and session cleanup.
- Kill-posture visibility during authentication.
- Auth-state impact on Context Never Lost (does un-auth clear
  workspace?).
- Auth-state impact on State Memory (do sessions persist across
  logouts?).

Expected timeline: 2 days.

---

*End of E1 — Strategy Experience.*

*All 18 checklist items confirmed. Strategy lifecycle codified end-to-
end. Two HITL gates identified as the emotional core. Everywhere-
Actionable rule verified for the promotion gate. Bible v2.1 · D2–D7 ·
Backend Feature Freeze all respected.*

*Awaiting operator review before authoring E2.*

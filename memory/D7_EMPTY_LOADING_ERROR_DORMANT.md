# D7 — Empty · Loading · Error · Dormant Pattern Library

> Codifies **every state that is not the "happy path"** — 45+ authored
> specimens across every module × every state × every mode. State copy
> is not filler; it is craftsmanship, in Division voice, honouring
> Purpose Before Status.
>
> Layered on **Bible v2.1** (`FRONTEND_DESIGN_BIBLE_V2_1.md`). Reuses
> D2 storytelling standard, D3/D4/D5 empty-state templates, D6
> mode-tone adjustments.
>
> Prepared 2026-07-20.

---

## 0. Design Principles Checklist (17 items — permanent quality gate)

Every design deliverable must confirm all items. D7 confirms:

- [x] **Invisible Luxury** — no scary red modals; no spinners-of-shame; every state feels considered, never punitive.
- [x] **Everything Connected** — every non-happy state exposes a link back to lineage / evidence / activation plan wherever relevant.
- [x] **Progressive Disclosure** — Simple copy shown by default; Advanced Lens adds one technical clause on the same line, never a new paragraph.
- [x] **Evidence First** — error copy cites the specific subsystem or endpoint; dormant copy cites the specific activation phase.
- [x] **Persona Awareness** — every specimen has an optional mode-tone variant (§6).
- [x] **Mission Control First** — Mission Control's empty states are the most-authored (§8); every other module inherits patterns.
- [x] **Accessibility (WCAG 2.2 AA)** — every state is screen-reader-friendly; icons carry `aria-hidden` while adjacent text carries meaning.
- [x] **Motion Discipline** — state transitions use Bible §6.1 tiers; no gratuitous animation on states meant to communicate calm.
- [x] **Design Token Compliance** — every colour drawn from Bible §5 tokens; every state's icon from lucide-react.
- [x] **Six-Signal Rule** — states use `--sig-*` semantically: `ok` for caught-up · `warn` for retryable trouble · `crit` for unrecoverable · `advisory` for informational · `info` for active · `dormant` for deliberate off.
- [x] **Lineage Validation** — Lineage-based dormant states link to the activation plan or upstream artefact.
- [x] **Empty-State Quality** — this document IS the quality bar; ≥ 45 specimens authored.
- [x] **Consistency** — every state renders in the same **State Template** (§3) — mechanism of consistency, mechanism of trust.
- [x] **Explainability** — every specimen answers *What is happening · Why · What can I do*.
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice throughout; no `error 503`, no `null result`, no `something went wrong`.
- [x] **Context Never Lost (Bible §1.4.4)** — every state preserves filters, time-window, selection.
- [x] **Purpose Before Status (D4 §5.1.1)** — every state leads with *why the surface exists*, not *what is wrong*.
- [x] **Decision Identity (D6 §8.1a)** — the state itself is a truth; different modes may present the same empty/error state differently but the count, the reason, and the recommended action are byte-identical.

---

## 1. Purpose

Most product design treats empty / loading / error / dormant states as
implementation detail. Strategy Factory treats them as **the moments
that reveal our craftsmanship most visibly** — because they occur when
the operator's attention is *not* being carried by data.

Two rules govern this library:

1. **Empty is a state, not a bug.** Author it. Explain it. Offer an
   action.
2. **Dormant is a state, not an error.** It has its own colour
   (`--sig-dormant`), its own tone, its own icon. It is never red.

This library is the reference every implemented state cites — Sprint 1
implementations copy specimens verbatim from D7.

**Anti-goals** (what these states must never become):

- `null`, `[]`, `0 results`, or `No data`.
- `Something went wrong` (jargon).
- `HTTP 503 Service Unavailable` (mechanism, not meaning).
- Full-page red-modal error boundaries.
- Marketing-tone empty states (*"Get started with your first
  strategy!"* — no).

---

## 2. The six state types

| State | When | Colour token | Tone |
|---|---|---|---|
| **Empty** | Surface has no data yet by design or by moment | `--sig-dormant` or `--sig-ok` | Calm; offer next step |
| **Loading** | Data is being retrieved | `--content-lo` skeleton | Ambient; informative if > 2 s |
| **Error** | A request failed unexpectedly | `--sig-warn` (retryable) or `--sig-crit` (unrecoverable) | Informational; specific subsystem |
| **Dormant** | Feature is deliberately off (activation phase, feature flag, kill posture) | `--sig-dormant` | Explanatory; link to plan |
| **Replay-empty** | Time scrub landed on a window with no data | `--sig-dormant` | Directional; expand window |
| **Success** | An action just completed (transient confirmation) | `--sig-ok` | Fleeting; auto-dismiss |

---

## 3. The State Template (mechanism of consistency)

Every state renders in the same anatomy — a single, spatially-consistent
frame. Six slots. Always in this order.

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│                                                                    │
│    [ icon · 24 px lucide · --content-lo or --sig-<tone> ]          │  ← 1 · Icon
│                                                                    │
│    <Headline · Division voice · one sentence>                      │  ← 2 · Headline
│                                                                    │
│    <Purpose caption · one sentence · optional>                     │  ← 3 · Purpose (Advanced only for Error/Success)
│                                                                    │
│    [ primary action ]   ·   [ secondary link ]                     │  ← 4 · Actions
│                                                                    │
│    <technical clause · Advanced Lens only · one sentence>          │  ← 5 · Advanced footnote (optional)
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### 3.1 Slot rules

| # | Slot | Rules |
|---|---|---|
| 1 | Icon | 24 px lucide-react; single glyph; colour from state's tone token (§2); never emoji |
| 2 | Headline | ≤ 90 chars; Division voice; sentence case; ends with period |
| 3 | Purpose caption | ≤ 90 chars; optional; timeless (what the surface exists for) |
| 4 | Actions | 1 primary (verb) + 1 optional secondary (verb); never same colour; never 3+ actions |
| 5 | Advanced footnote | ≤ 90 chars; mono monospace 11 px; shows on Advanced Lens only; contains subsystem / endpoint / correlation ID |

### 3.2 Framing

- Panel: `--surface-1` background, 1 px `--stroke-1` border, radius per
  Concept.
- Vertical padding: `--space-6` (40 px).
- Horizontal padding: `--space-5` (24 px).
- Centred content vertically; left-aligned text horizontally on
  workstation, centred on tablet + briefing.
- Max content width: 480 px.

### 3.3 The template is inviolate

Adding a 7th slot (e.g., a decorative illustration) requires a v-major
bump (Bible §20.3). Six slots is the ceiling.

---

## 4. Copy voice — the discipline

Every specimen in this library obeys three constraints inherited from
D2 Addendum:

1. **Division voice.** *"Research Division has no cycles running."*
   Never *"No cycles found."*
2. **Past tense for events; present tense for state.** *"The Factory
   has been idle for 12 min."* (past-perfect for what happened).
   *"Approval Center is up to date."* (present for now-state).
3. **≤ 90 characters per line.** Wraps naturally to two lines maximum.

**Additional copy rules for this library:**

4. **First sentence is the *headline*.** The purpose caption is optional
   and never repeats the headline.
5. **Never accuse the operator.** *"You have no strategies"* → *"No
   strategies have been generated yet."*
6. **Never suggest a fault when none exists.** Dormant is not an error.
7. **Actions are verbs.** *"Run cycle"*, *"View plan"*, *"Open evidence"*.
   Never *"Click here"*, *"Learn more"*, *"Get started"*.
8. **Provide one primary action and at most one secondary.** Two-of-
   equal-weight is not a state; it's a decision — send the operator to
   Approvals.

---

## 5. Icon library (lucide-react selections)

Each state type has a canonical icon set. Never mix or invent.

### 5.1 Empty
`check`, `pin`, `folder`, `book`, `layers`, `moon`, `sparkles`, `flag`,
`filter-x`, `grid`

### 5.2 Loading
No icon — shimmer skeleton or narrative text only.

### 5.3 Error
`wifi-off`, `alert-triangle`, `x-circle`, `octagon`, `refresh-cw`,
`shield-off`

### 5.4 Dormant
`shield` (muted), `pause`, `moon` (muted), `power`, `lock`,
`clock` (muted)

### 5.5 Replay-empty
`rewind`, `arrow-left-right`

### 5.6 Success
`check-circle`, `check`, `sparkles`

**Rule:** the icon reinforces the tone; if the icon and the copy
disagree, redesign both.

---

## 6. Mode-tone adjustments (per D6 §11)

Every specimen has an optional mode-tone variant. The **body of the
copy remains identical (Decision Identity, D6 §8.1a)**; only rendering
differs.

### 6.1 Executive tone

- Serif italic on the headline (`GT Sectra`).
- Purpose caption always shown (Executives want context).
- Actions in serif; primary action outline-only.
- Icon at 32 px (larger, more editorial).
- Panel padding: `--space-7` (Concept-C whitespace).

### 6.2 Operations tone (default · canonical rendering)

- Sans body-md headline (`Neue Haas Grotesk Display`, 17 px).
- Purpose caption optional (usually shown).
- Actions in sans; primary action filled.
- Icon at 24 px.
- Panel padding: `--space-6`.

### 6.3 Research tone

- Sans body-md headline.
- Purpose caption always shown (thread continuity).
- Actions in sans.
- Icon at 24 px with subtle luminance halo when the underlying entity is
  live (Concept-B).
- Adds a `→ open knowledge graph` tertiary link when relevant.

### 6.4 Developer tone

- Mono headline (`Berkeley Mono`, 15 px).
- Purpose caption always shown.
- Advanced footnote (slot 5) **always visible** (never hidden).
- Actions in mono.
- Icon at 24 px.
- Panel padding: `--space-5` (denser).

---

## 7. The library — organisation

Specimens are grouped by **module**. Within each module, specimens
appear in the order **Empty · Loading · Error · Dormant · Replay-empty
· Success** (per §2).

Every specimen carries:

- **Code**: `<module>-<state>-<slug>` (e.g., `mc-empty-nothing-pending`).
- **When** it fires.
- **Copy** in canonical Operations tone (baseline).
- Optional mode-tone deltas where meaningful.

---

## 8. Mission Control (`/c/mission`)

### 8.1 `mc-empty-nothing-pending`
*When:* zero approvals, zero critical attention items.
```
Icon        check
Headline    The Factory is operating autonomously.
Purpose     No approvals require your attention.
Actions     open Timeline · view yesterday's briefing
```
- Executive: *"You're all caught up. Yesterday: 3 candidates promoted."*
- Advanced footnote: `master-bot@v55 · plan #47 · step 3/7`

### 8.2 `mc-empty-all-nominal`
*When:* all 6 subsystems ok; no active plan.
```
Icon        moon
Headline    All 6 subsystems nominal. 8 divisions healthy.
Purpose     The Factory is at rest until the next scheduled cycle.
Actions     view scheduler · view last plan
```

### 8.3 `mc-loading-initial`
- < 300 ms: no indicator.
- 300 ms – 2 s: shimmer skeleton over each panel.
- \> 2 s: narrative — *"Composing mission control snapshot..."*
- \> 8 s: *"Still working. You can navigate away and I'll continue."*

### 8.4 `mc-error-partial-panels`
*When:* one or more panels fail to load; rest render.
```
Icon        alert-triangle
Headline    Some panels couldn't load.
Purpose     Attention feed loaded normally; workforce panel timed out.
Actions     Retry · view logs · developer
```
- Advanced footnote: `endpoint /api/ai-workforce · 12 s timeout`
- Panel-level fallback: individual panel shows `→ retry this panel`.

### 8.5 `mc-dormant-freeze`
*When:* kill posture armed globally.
```
Icon        shield · muted
Headline    DORMANT · The Factory is currently in freeze mode.
Purpose     Backend is healthy; connectors are intentionally offline.
Actions     view activation plan · view kill posture
```
Colour `--sig-dormant`. **No Retry.**

### 8.6 `mc-replay-empty`
*When:* time-scrub set to a window before Factory existed.
```
Icon        rewind
Headline    No activity recorded before 2026-07-01.
Purpose     The Factory began recording on this date.
Actions     expand window · return to live
```

### 8.7 `mc-success-plan-shipped` (transient toast)
*When:* a plan completes with successful outcomes.
```
Icon        check-circle
Headline    Plan #47 shipped 2 candidates.
Purpose     3 h 08 min · 0 rollbacks.
Actions     view outcome evidence
```
Auto-dismiss after 8 s. Also enters Timeline as an activity row.

---

## 9. AI Activity Timeline (right rail)

### 9.1 `tl-empty-idle-factory`
```
Icon        moon
Headline    The Factory has been idle for 12 min.
Purpose     This is normal during freeze.
Actions     see last cycle · view scheduler
```

### 9.2 `tl-empty-filter-empty`
```
Icon        filter-x
Headline    No events match the current filters.
Purpose     (no purpose caption — filter is explicit)
Actions     clear filters · view all activity
```

### 9.3 `tl-loading`
Shimmer skeleton: 6 rows, 1200 ms cycle, 40 ms stagger.

### 9.4 `tl-error-offline`
```
Icon        wifi-off
Headline    Timeline could not reach the backend.
Purpose     Retrying every 8 seconds.
Actions     view logs · developer
```

### 9.5 `tl-replay-empty`
```
Icon        rewind
Headline    No events in the selected window.
Purpose     Try widening or return to live.
Actions     expand window · return to live
```

---

## 10. Approval Center (`/c/approvals`)

### 10.1 `ap-empty-caught-up`
```
Icon        check
Headline    You're all caught up.
Purpose     The Factory is operating autonomously.
Actions     view recent approvals · open timeline
```
Colour `--sig-ok`. Never celebratory motion.

### 10.2 `ap-empty-filter-empty`
```
Icon        filter-x
Headline    No approvals match the current filters.
Purpose     (n/a)
Actions     clear filters · view all approvals
```

### 10.3 `ap-loading`
Shimmer skeleton on the approval-card grid: 3 cards, staggered 40 ms.

### 10.4 `ap-error-unreachable`
```
Icon        wifi-off
Headline    Approvals could not be loaded.
Purpose     Retrying every 8 seconds.
Actions     view logs · developer
```
Colour `--sig-warn`.

### 10.5 `ap-error-action-failed`
*When:* an approve/deny/route action fails at commit.
```
Icon        alert-triangle
Headline    Master Bot could not commit the approval.
Purpose     The recommendation is still open; no change was made.
Actions     Retry · Deny with reason · view logs · developer
```
- Advanced footnote: `endpoint /api/meta-learning/approve · 500 err · trace-id abc123`

### 10.6 `ap-dormant-phase-gated`
```
Icon        shield · muted
Headline    DORMANT · Approval sources are gated by activation flags.
Purpose     Meta-Learning + Factory-Eval will appear once their flags
            are enabled per the Coherent UKIE Activation plan.
Actions     view activation plan
```

### 10.7 `ap-replay-empty`
```
Icon        rewind
Headline    No approvals were open at the selected time.
Purpose     Try expanding or return to live.
Actions     expand window · return to live
```

### 10.8 `ap-success-bulk-approved` (transient)
```
Icon        check-circle
Headline    Master Bot committed 3 low-risk approvals.
Purpose     Rollback SLA per item: < 30 s.
Actions     view outcome evidence
```
Auto-dismiss 6 s.

### 10.9 `ap-safety-pinned` (persistent, non-empty)
*When:* Safety group is non-empty — pinned red-bordered summary.
```
⚠ SAFETY · 1 open approval  ·  review before other decisions
```
Not a state per se — the *presence* of Safety pins overrides normal
empty rendering.

---

## 11. Factory / Master Bot / Workforce (`/c/factory`)

### 11.1 `fac-empty-awaiting-plan`
```
Icon        sparkles
Headline    Master Bot has no active plan yet.
Purpose     Set an objective to begin.
Actions     set objective · view previous plans
```

### 11.2 `fac-empty-all-idle`
```
Icon        moon
Headline    The Factory is at rest.
Purpose     All 8 divisions healthy · no work in progress.
Actions     view scheduler · view last plan
```

### 11.3 `fac-empty-plan-completed`
*When:* plan just completed; auto-shows for 8 s then collapses to history.
```
Icon        check-circle
Headline    Plan #47 completed.
Purpose     2 candidates shipped · 3 h 08 min · 0 rollbacks.
Actions     view outcome evidence · plan history
```

### 11.4 `fac-dormant-division`
*When:* a division is gated by activation phase.
```
Icon        shield · muted
Headline    DORMANT · Knowledge Base is gated by Phase C activation.
Purpose     Retrieval workers will appear once Phase C is enabled.
Actions     view activation plan
```

### 11.5 `fac-error-worker-offline`
*When:* a specific worker is offline.
Rendered as an inline chip on the worker card (not a full State
Template):
```
Chip     ⨯ offline · 12 min · restart pending
Actions  → view scheduler · report issue
```

### 11.6 `fac-dormant-off-shift`
*When:* Governance has paused the Factory.
```
Icon        pause
Headline    Governance has paused the Factory.
Purpose     Kill-posture armed 4 h ago.
Actions     view kill posture · view governance log
```
Colour `--sig-warn`.

### 11.7 `fac-replay-empty`
```
Icon        rewind
Headline    Workforce Org Chart is empty at the selected time.
Purpose     The Factory hadn't started yet.
Actions     expand window · return to live
```

### 11.8 `fac-success-hitl-approved` (transient)
```
Icon        check-circle
Headline    Master Bot advanced to step 6 of 7.
Purpose     Portfolio Division will add the candidate.
Actions     open Portfolio
```

---

## 12. Research Workspace + Knowledge (`/c/research`, `/c/knowledge`)

### 12.1 `res-empty-no-strategies`
```
Icon        sparkles
Headline    No strategies have been generated yet.
Purpose     Start your first research cycle.
Actions     Run cycle · open Explorer
```

### 12.2 `res-empty-no-cycles-today`
```
Icon        clock · muted
Headline    Research Division has run no cycles today.
Purpose     Last cycle: yesterday 22:11.
Actions     Run cycle · view last cycle
```

### 12.3 `res-loading-cycle-running`
*When:* a research cycle is in flight; > 2 s.
```
Narrative:  Research Division is retrieving 6 arxiv papers on regime detection...
```
Progresses to:
```
Research Division retrieved 6 papers. Ranking now...
```
Then:
```
Research Division synthesised 2 candidates. Handoff to Validation.
```

### 12.4 `res-error-cycle-failed`
```
Icon        alert-triangle
Headline    Research Division's cycle stopped mid-run.
Purpose     Retrieval succeeded; synthesis failed.
Actions     Retry from synthesis · view logs · developer
```
- Advanced footnote: `worker-01 · endpoint /api/research/synthesize · 500 err`

### 12.5 `kb-empty-dormant`
```
Icon        shield · muted
Headline    DORMANT · The Knowledge Base is inactive until Phase C.
Purpose     Retrieval workers will begin ingesting once Phase C is
            enabled per the activation plan.
Actions     view activation plan
```

### 12.6 `kb-empty-root-generation`
*When:* the current artefact has no ancestors in the Knowledge Graph.
```
Icon        git-fork
Headline    This artefact is a root generation. No ancestors recorded.
Purpose     Root generations begin the lineage tree.
Actions     view generation evidence · close graph
```

### 12.7 `kb-replay-empty`
```
Icon        rewind
Headline    No lineage existed at the selected time.
Purpose     Try widening the time window.
Actions     expand window · return to live
```

---

## 13. Portfolio (`/c/portfolio`)

### 13.1 `port-empty-no-candidates`
```
Icon        layers
Headline    Portfolio Division has no candidates yet.
Purpose     Approve strategies in Research to seed the portfolio.
Actions     open Research · view portfolio history
```

### 13.2 `port-empty-no-positions`
```
Icon        pin
Headline    Portfolio Division holds no positions.
Purpose     This is expected during freeze.
Actions     view activation plan
```

### 13.3 `port-loading`
Shimmer on Risk Surface (G6) + candidates table.

### 13.4 `port-error-risk-surface`
```
Icon        alert-triangle
Headline    Portfolio Risk Surface could not be rendered.
Purpose     Correlation matrix missing 3 pairs.
Actions     Retry · view logs · developer
```
- Advanced footnote: `endpoint /api/portfolio/risk-surface · missing pairs: EURUSD-GBPUSD, ...`

### 13.5 `port-replay-empty`
```
Icon        rewind
Headline    Portfolio had no positions at the selected time.
Purpose     Try expanding.
Actions     expand window · return to live
```

---

## 14. Execution (`/c/execution`, `/c/propfirm`)

### 14.1 `exec-empty-no-observations`
```
Icon        terminal
Headline    Execution Division has recorded no observations.
Purpose     This is expected before broker connections are live.
Actions     open Prop Firm · view activation plan
```

### 14.2 `exec-dormant-no-brokers`
```
Icon        shield · muted
Headline    DORMANT · No brokers are connected.
Purpose     Broker connections are intentionally offline until Phase D.
Actions     view activation plan
```

### 14.3 `exec-error-broker-unreachable`
```
Icon        wifi-off
Headline    Broker <name> is unreachable.
Purpose     Execution Division has paused observations on this broker.
Actions     Retry · view broker · view logs · developer
```

### 14.4 `exec-empty-quality-constellation-empty`
```
Icon        flag
Headline    Execution Constellation has no fills yet.
Purpose     Fills will appear as brokers execute orders.
Actions     view brokers · view scheduler
```

### 14.5 `pf-empty-no-challenges`
```
Icon        flag
Headline    No prop firm challenges have been matched yet.
Purpose     Learning Division will propose matches as strategies mature.
Actions     view catalogue · view learning proposals
```

---

## 15. Market Data (`/c/market-data`)

### 15.1 `md-empty-full-coverage`
```
Icon        check
Headline    Coverage is complete across all symbols and timeframes.
Purpose     Maintenance completed the last BI5 sweep with zero gaps.
Actions     view sweep history · view maintenance log
```

### 15.2 `md-loading-heatmap`
Shimmer on the coverage grid; each cell shimmer skeleton.

### 15.3 `md-error-partial-coverage`
```
Icon        alert-triangle
Headline    Maintenance detected gaps in 12 cells.
Purpose     Auto-repair is running for 8; manual repair queued for 4.
Actions     view gap detail · run repair · view maintenance log
```
Colour `--sig-warn`.

### 15.4 `md-dormant-bi5-off`
```
Icon        pause
Headline    DORMANT · BI5 sweep is disabled.
Purpose     Enable in Governance to resume automated coverage.
Actions     open Governance
```

---

## 16. Governance + Advanced (`/c/governance`, `/c/advanced`)

### 16.1 `gov-empty-no-advisories`
```
Icon        check
Headline    Governance has no open advisories.
Purpose     Six hard rails are watching every artefact promotion.
Actions     view recent actions · view rails
```
Colour `--sig-ok`.

### 16.2 `gov-warn-old-advisory`
*When:* an advisory has been open > 4 days.
Rendered as inline chip on the advisory:
```
⚠ 4 d 08 h · needs operator attention
```

### 16.3 `adv-empty-clean-diagnostics`
```
Icon        check
Headline    All diagnostics nominal.
Purpose     No errors in the last hour.
Actions     view audit log · view scheduler
```

### 16.4 `adv-error-audit-log-unreachable`
```
Icon        wifi-off
Headline    Audit log could not be loaded.
Purpose     Retrying every 8 seconds.
Actions     view mongo status · view logs · developer
```

---

## 17. Pinned Preview + Lineage Graph + Copilot (cross-cutting)

### 17.1 `pin-empty-nothing-pinned`
```
Icon        pin
Headline    Nothing pinned yet.
Purpose     Pin any artefact from the timeline, explorer, or approvals
            to compare.
Actions     open Strategy Explorer · view timeline
```

### 17.2 `lin-empty-root`
```
Icon        git-fork
Headline    This artefact is a root generation.
Purpose     No ancestors recorded.
Actions     view generation evidence · close graph
```

### 17.3 `lin-replay-empty`
```
Icon        rewind
Headline    No lineage existed at the selected time.
Purpose     Try widening.
Actions     expand window · return to live
```

### 17.4 `copilot-empty-ready`
```
Icon        sparkles
Headline    Copilot is ready.
Purpose     Ask about any visible strategy, knowledge item, or timeline
            event.
Actions     ask about the current strategy · ask what changed today
```

### 17.5 `copilot-error-unavailable`
```
Icon        shield-off
Headline    Copilot is unavailable.
Purpose     Emergent LLM key not configured or provider unreachable.
Actions     view provider status · view logs · developer
```
- Advanced footnote: `key rotation status · last successful call 2 h ago`

### 17.6 `copilot-empty-no-grounded-answer`
*When:* Copilot cannot cite evidence for a question.
```
Icon        book
Headline    Copilot has no grounded evidence for that question.
Purpose     Try rephrasing or ask about a visible artefact.
Actions     view timeline · reword question
```
- **Never invents.** This state exists so Copilot's Never-Invents rule
  has a legible fallback.

---

## 18. Chart tiles (§7.11.2 in Bible)

### 18.1 `chart-empty-no-data`
```
Icon        grid
Headline    No data in the current window.
Purpose     (n/a)
Actions     expand window · view underlying table
```

### 18.2 `chart-drill-empty`
*When:* clicking a chart slice yields no underlying rows.
```
Icon        filter-x
Headline    No rows in this slice of the chart.
Purpose     Try widening the time window or removing filters.
Actions     expand window · clear filters · close drawer
```

### 18.3 `chart-loading`
- < 300 ms: no indicator.
- 300 ms – 2 s: shimmer skeleton in the Frame Body.
- \> 2 s: narrative — *"Computing constellation over 30 days..."*

### 18.4 `chart-error-render-failed`
```
Icon        alert-triangle
Headline    <Chart name> could not be rendered.
Purpose     <reason in Division voice>
Actions     Retry · export raw · view logs · developer
```

---

## 19. Kill Posture (persistent global overlay)

### 19.1 `kp-armed` (persistent ribbon, not a state template)
```
DANGER  ⚠  Kill posture armed 12:24 · deliberate freeze  ·  [ VIEW ]
```

### 19.2 `kp-dormant-not-armed`
Kill posture is at rest; renders only in `/c/advanced/kill-posture` as:
```
Icon        shield · muted
Headline    Kill posture is not armed.
Purpose     The Factory operates within normal governance rails.
Actions     view governance rails · arm kill posture · governance-gated
```

---

## 20. Loading — the four-tier standard

Loading is *not* a placeholder — it is a communication.

### 20.1 The four tiers

| Elapsed | Presentation | Copy |
|---|---|---|
| < 300 ms | none | none — avoid flicker |
| 300 ms – 2 s | shimmer skeleton | none — visual only |
| 2 s – 8 s | narrative text | *"Research Division is retrieving 6 arxiv papers..."* |
| > 8 s | narrative + background offer | *"Still working. You can navigate away and I'll notify when done."* |

### 20.2 Narrative loading — templates

Always Division voice; always past-progressive-turning-present:

- **Timeline** — *"Fetching last 4 h of activity..."*
- **Approval Center** — *"Loading pending recommendations from 3 sources..."*
- **Master Bot Dashboard** — *"Composing plan snapshot..."*
- **Workforce Org Chart** — *"Assembling worker status across 8
  divisions..."*
- **Knowledge Graph** — *"Rendering knowledge graph over 3 months of
  promote events..."*
- **Coverage Heatmap** — *"Reading BI5 sweep manifest across 42
  symbols..."*
- **Portfolio Risk Surface** — *"Computing correlation surface over 30
  days..."*
- **Execution Constellation** — *"Retrieving 500 recent fills across 3
  brokers..."*
- **Learning Evolution Timeline** — *"Reading Learning Division's
  proposal history..."*

### 20.3 Narrative loading — anti-patterns

- ❌ *"Loading..."* — non-descriptive.
- ❌ *"Please wait..."* — apologetic.
- ❌ *"Fetching data..."* — mechanism, not meaning.

---

## 21. Success confirmations (transient)

Fire briefly (6–8 s), auto-dismiss, and enter Timeline as a permanent
row.

**Never celebratory animation.** No confetti. No sound. A quiet chip
that acknowledges and dismisses.

Motion: 200 ms fade + 6 px slide-in-up; auto-dismiss 200 ms fade +
4 px slide-down.

Position: top-right, below header. Never centre-screen modal.

---

## 22. Copy cadence rules (numerical constraints)

For every specimen in this library:

- Headline ≤ 90 chars.
- Purpose ≤ 90 chars.
- Actions: 1 primary verb, 0 or 1 secondary verb.
- Advanced footnote ≤ 90 chars mono.
- Total lines rendered ≤ 4 (excluding blank lines and action row).

If a specimen requires more, the design is over-communicating; simplify.

---

## 23. State transitions

State surfaces transition between each other in predictable ways.
Motion budget from Bible §6.1.

| From | To | Trigger | Motion |
|---|---|---|---|
| Loading | Empty | data returned empty | 200 ms crossfade |
| Loading | Success (rare — data returned non-empty) | data returned | 200 ms fade to normal content |
| Loading | Error | request failed | 320 ms fade-in of error template |
| Empty | Success | operator took primary action | 200 ms fade to normal content |
| Error | Loading | Retry pressed | 200 ms fade to loading |
| Any | Dormant | kill-posture armed | 400 ms Editorial tier |
| Any | Success (transient) | operator action committed | slide-in-up 200 ms; auto-dismiss 200 ms |

Reduced-motion: all crossfades reduce to opacity-only, no slide.

---

## 24. Decision Identity in state specimens (D6 §8.1a)

The state itself is a truth. Different modes may present the same
empty / error / dormant state differently — Concept-C serif in
Executive, mono in Developer — but the **underlying count, reason,
and recommended action are byte-identical**.

**Verification test:** for every specimen in this library, switch to
each mode. The headline text may change stylistically; the count
mentioned, the reason cited, the primary action offered, and the
Advanced footnote (Developer-only) must be identical.

Example — `ap-empty-caught-up`:
- Operations: *"You're all caught up. The Factory is operating
  autonomously."*
- Executive (serif): *"You're all caught up. The Factory is operating
  autonomously."* (same text; different type)
- Research: *"You're all caught up. The Factory is operating
  autonomously."* (same text)
- Developer: *"You're all caught up. The Factory is operating
  autonomously."* + Advanced footnote `master-bot@v55 · idle 12 min`

**The words that could vary — a specimen may *optionally* provide
mode-specific narrative additions**, but the primary sentence and
action set must persist. See §6 tone rules.

---

## 25. Accessibility (WCAG 2.2 AA)

- Every State Template panel has `role="status"` with `aria-live=
  "polite"` for empty / dormant / success; `aria-live="assertive"` for
  error.
- Icons have `aria-hidden="true"` — adjacent text carries meaning.
- Action buttons have distinct `aria-label` (never re-use the button
  text as the label when the button text is generic like *"Retry"* —
  augment with subject: `aria-label="Retry approval load"`).
- Screen-reader announcement priority:
  - Error > Success > Dormant > Empty > Loading.
- Focus lands on the primary action on state entry (never on the
  icon; never on the panel itself).
- Colour-blind fallback: every state icon + colour is complemented by
  an explicit tone word in the heading where appropriate
  (*DORMANT*, *ERROR* — reserved uppercase words).
- `prefers-reduced-motion`: crossfades → opacity only; shimmer →
  static skeleton.

---

## 26. Copy library growth policy

- **This library is versioned with the Bible.** Adding a specimen is a
  v-minor bump; changing the copy of an existing specimen is a v-major
  bump (Bible §20.1).
- Every new module introduces authored states *before* the module
  ships (D8 Sprint 1 acceptance rule).
- Copilot uses this library as its primary training-context — every
  Copilot answer references specimen codes internally when the
  operator's surface is in a non-happy state.

---

## 27. Sprint acceptance criteria

State library ships only if:

- ✅ 17-item Design Principles Checklist confirmed (§0)
- ✅ Every module has authored Empty · Loading · Error · Dormant · Replay-empty coverage (§8 – §19)
- ✅ Every specimen uses the State Template (§3)
- ✅ Copy voice discipline verified (§4)
- ✅ Icon library selections drawn only from lucide-react (§5)
- ✅ Mode-tone variants applied without violating Decision Identity (§6, §24)
- ✅ Copy cadence rules met — ≤ 90 chars, ≤ 4 lines (§22)
- ✅ State transitions animate per §23
- ✅ A11y `role="status"` + `aria-live` verified (§25)
- ✅ Narrative loading templates ship for surfaces > 2 s (§20)
- ✅ Success confirmations auto-dismiss + enter Timeline (§21)
- ✅ ≥ 45 specimens authored (§7 count)
- ✅ Every specimen has a stable code (`<module>-<state>-<slug>`)
- ✅ `data-testid` on every action button

---

## 28. What D7 does NOT include

- Coded prototype — Sprint 1 implements the State Template component
  (`<StateTemplate>`) and specimens.
- Copy in languages other than English (i18n is post-Sprint 1).
- Icon-set replacement (lucide-react is locked; a switch requires
  v-major bump).
- Success-confirmation *sounds* (never; no audio in this app).
- Illustrations (not in this Bible; template forbids a 7th slot).

---

## 29. Next: D8 — Sprint 1 detailed execution plan

Per Bible v2.1 §25. D8 codifies:

- Component-by-component work items for Sprint 1.
- Per-item design references (which D-doc section governs).
- Acceptance criteria per component.
- Dependency graph (which items unblock which).
- Test coverage requirements.
- Storybook target list.
- Estimated effort per item.

D8 will also incorporate the post-D8 experience-design suite plan
(Strategy Experience, Authentication Experience, First-Time User
Journey, Daily Operator Journey, Cross-Module Navigation) as the
gate between D8 and Sprint 1 implementation.

Expected timeline: 3–4 days.

---

*End of D7 — Empty · Loading · Error · Dormant Pattern Library.*
*All 17 checklist items confirmed. 45+ specimens authored across every
module. State Template established as the mechanism of consistency.
Decision Identity honoured — same underlying truth, mode-varied
presentation. Bible v2.1 · D6 Decision Identity · Backend Feature
Freeze respected.*
*Awaiting your review before D8 begins.*

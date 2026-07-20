# D6 — Personalization Modes Spec

> Codifies the four personas — **Executive · Operations · Research ·
> Developer** — as first-class *modes* that reshape the shell without
> fragmenting the design language. One product, four registers, one
> identity.
>
> Layered on **Bible v2.1** (`FRONTEND_DESIGN_BIBLE_V2_1.md`). Bible
> v2.1 §22 introduces the modes; D6 authors them in depth.
>
> Governed by Concept D (D0 · D1). Reuses D2 Timeline, D3 Approval
> Center, D4 Master Bot & Workforce, D5 Signature Frame. Adds Copilot
> trace-as-UI under Advanced Lens (Bible v2.1 §24 · P24).
>
> Prepared 2026-07-20.

---

## 0. Design Principles Checklist (16 items — permanent quality gate)

Every design deliverable must confirm all items. D6 confirms:

- [x] **Invisible Luxury** — mode differentiation achieved through *restraint* on non-relevant surfaces, not through added decoration. An Executive-mode surface is *quieter* than Operations, not louder.
- [x] **Everything Connected** — every mode preserves lineage links; changing mode never severs an artefact's ancestry visibility.
- [x] **Progressive Disclosure** — mode is orthogonal to Advanced Lens; a Developer in Simple sees fewer chips than an Operator in Advanced.
- [x] **Evidence First** — every mode retains the "no dead-end numbers" rule; Executive mode does not hide evidence, it *narrates* it.
- [x] **Persona Awareness** — this is D6's core mandate; explicitly authored per §4 – §7.
- [x] **Mission Control First** — Operations mode's landing is Mission Control; every other mode is one keystroke (`⌘M`) away from it.
- [x] **Accessibility** — WCAG 2.2 AA in every mode; screen-reader announcements consistent; keyboard-first preserved.
- [x] **Motion Discipline** — motion budget is identical across modes; motion *density* differs (Executive: quiet · Research: alive · Operations: alert · Developer: signal-only).
- [x] **Design Token Compliance** — every mode uses only Bible v2.1 §5 tokens; no mode-specific token additions.
- [x] **Six-Signal Rule** — the six signal hues carry the same meaning in every mode; a red critical is red for Executive as it is for Operations.
- [x] **Lineage Validation** — Lineage Graph (Bible §10.2), Pinned Preview (§7.12), time-window cascade (§7.13) available in every mode.
- [x] **Empty-State Quality** — mode-specific empty states authored (§4.7, §5.7, §6.7, §7.7); no generic fallback.
- [x] **Consistency** — shell chrome (LeftRail, TopTabBar, StatusRail, right rail) is **always Concept-A** in every mode. The tool is consistent under the register.
- [x] **Explainability** — mode changes are visible: the header chip shows the current mode; a subtle status-rail entry notes when mode changes.
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice is used in every mode; Executive adds serif emphasis; Developer adds Advanced chips without changing the underlying sentence.
- [x] **Context Never Lost (Bible v2.1 §1.4.4)** — switching mode preserves every selection, filter, time-window, pinned item, scroll position, and Advanced Lens state.
- [x] **Purpose Before Status (D4 §5.1.1)** — every mode-specific screen still leads with purpose captions before state chips.
- [x] **Decision Identity (§8.3 · new invariant)** — every decision, approval, metric, or evidence object represents the same underlying truth in every mode. Presentation differs. Truth does not.

---

## 1. Purpose

Strategy Factory serves four distinct consumers whose relationship with
the Factory is fundamentally different:

- **Executive** — reads outcomes; makes strategic decisions; short
  sessions; low-context; needs briefings, not diagnostics.
- **Operations** — on-shift; runs the workflow; monitors nominal state;
  triages exceptions; needs the full cockpit.
- **Research** — investigates strategies, knowledge, learning; long
  sessions; deep focus; needs the lab.
- **Developer** — debugs the system; escalates on incidents; needs
  L4–L5 diagnostics that everyone else must not see.

**One codebase. Four registers. One identity.** Modes are the
mechanism that lets a single product feel *purpose-built* for each
consumer without fragmenting the design language.

**Anti-goals** (what modes must never become):

- Separate applications with parallel component trees.
- Feature flagging (modes do not gate *functionality*; they gate
  *emphasis*).
- A settings dungeon of toggles (mode is one selector, one keystroke).
- A "beginner vs. expert" hierarchy (the four personas are peers).

---

## 2. The four modes at a glance

| Mode | Consumer | Landing surface | Concept-D emphasis | Density | Right rail | Ambient motion |
|---|---|---|---|---|---|---|
| **Executive** | Founder / stakeholder | `/c/briefing` | **C 60 · A 30 · B 10** | Cinema | Timeline compact, filtered to Accomplishments + Approvals | none (except G8 heartbeat) |
| **Operations** *(default)* | On-shift operator | `/c/mission` | **A 60 · B 30 · C 10** | Compact | Timeline full | Pulse on running workers · G8 continuous |
| **Research** | Analyst | `/c/research` | **B 60 · A 30 · C 10** | Cozy | Timeline filtered to Research + Knowledge + Learning | Neural glow on active nodes/edges |
| **Developer** | Backend engineer | ⌘K open · then `/c/advanced` | **A 70 · diagnostics-lens 30** | Compact | Timeline filtered to errors + telemetry + env | Signal-only motion (no ambience) |

**Every mode preserves:**
- Six-signal palette
- Terminology dictionary (Bible §19.4)
- Division voice (D2 Addendum)
- Signature Frame on every G-graphic (D5 §2)
- Backend Feature Freeze compliance

---

## 3. Mode switching mechanics

### 3.1 The mode selector

Lives in the header, next to the persona chip:

```
┌────────────────────────────────────────────────────────────────────┐
│ Strategy Factory   [ ● 4 approvals ]   [ mode · operations ▾ ]  ⌘K│
└────────────────────────────────────────────────────────────────────┘
```

- Chip renders `[ mode · <current> ▾ ]` in `--font-caption` UPPERCASE.
- Colour: `--content-md` default; matches operator's current mode.
- Click / `⌘M` → opens the Mode Switcher popover.

```
┌──────────────────────────────────┐
│  Switch mode                      │
│                                   │
│  ●  Executive                     │
│  ●  Operations  (current)         │
│  ●  Research                      │
│  ●  Developer                     │
│                                   │
│  Advanced Lens · off              │
│  Density · compact ▾              │
│                                   │
│  ─── keyboard ──────────           │
│  ⌘M           switch mode          │
│  ⌘⇧A         toggle Advanced       │
│                                   │
└──────────────────────────────────┘
```

### 3.2 Switching behaviour

Mode change is **not** a page reload. The shell:

1. Fades the surface content to 50 % opacity over 100 ms.
2. Re-lays-out to the new mode's grid, applies the new concept
   emphasis, and reveals content at full opacity over 100 ms.
3. Total elapsed time: 200 ms (Bible §6.1 medium tier).

**Preserved across switch** (Bible §1.4.4 Context Never Lost):
- Selected strategy / artefact
- Selected worker
- Every filter chip (`<FacetBar>` state)
- Time-window chip
- Pinned Preview tray
- Advanced Lens toggle
- Density
- Evidence Drawer state
- Scroll position (best-effort per surface)
- URL (query parameters update to reflect new mode's default filters
  only where the operator's own filter is unset)

**What actually changes on mode switch:**
- Landing surface if `⌘M` was pressed at `/c/<default-for-old-mode>` —
  otherwise the operator stays on the same page.
- Concept emphasis on the current surface (Concept-A / B / C rendering).
- Filters *if the operator had accepted the mode's defaults*.
- Copilot tone (§11).
- Right rail contents (Timeline filter).

### 3.3 Persistence

- Mode persists **per user** in localStorage (`strategyFactory.mode`).
- First-time login sets the default from the invitation / SSO claim,
  or falls back to Operations.
- No cookies. No server state (per Backend Feature Freeze).

### 3.4 Cross-user considerations

A user can be assigned multiple modes; the selector shows all
authorised modes. Assignment happens via `/c/advanced/users` (out of
scope for Sprint 1). Sprint 1 default: every user has all four modes
available.

### 3.5 Kill posture overrides mode

Regardless of mode, if the kill posture is armed, the danger ribbon
fires and the current surface reveals kill-posture context.
**Executive mode does not suppress critical alerts.** Modes gate
emphasis, never safety.

---

## 4. Executive mode

*"You have arrived; the work is under control."*

### 4.1 Consumer & goals

- **Consumer:** founder, stakeholder, external reviewer, board.
- **Session length:** 30 seconds to 3 minutes.
- **Goal:** understand *outcomes and posture*, decide *whether the
  Factory needs their attention*, then leave.
- **Not the goal:** operate anything, diagnose anything, browse
  anything.

### 4.2 Landing surface — `/c/briefing`

A **new dedicated surface** authored in Concept C (Executive Luxury).
Structure:

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│  Daily briefing                                                    │
│  2026-07-20 · Tuesday · 09:14 UTC                                 │
│                                                                    │
│  ─────────── gold rule (1 px --accent-gold) ─────────────         │
│                                                                    │
│                                                                    │
│    91.4 %                          ← --font-metric-hero (48 px light ivory)
│    AI Workforce                    ← --font-h1-serif (32 px GT Sectra)
│                                                                    │
│    4 workers online. 2 idle. All divisions nominal.               │
│                                                                    │
│                                                                    │
│    ─── Yesterday ────────────────────────────────────────         │
│                                                                    │
│    Master Bot completed 3 plans. 2 candidate strategies            │
│    reached Portfolio candidacy. Learning Division                  │
│    accepted 6 of 8 recommendations.                                │
│                                                                    │
│    → open full timeline                                            │
│                                                                    │
│                                                                    │
│    ─── Pending your attention ───────────────────────────         │
│                                                                    │
│    3 approvals require your review.                                │
│    1 governance advisory has been open for 4 days.                │
│                                                                    │
│    → open Approval Center                                          │
│                                                                    │
│                                                                    │
│    ─── System posture ───────────────────────────────────         │
│                                                                    │
│    All 6 subsystems nominal.                                       │
│    Kill posture armed (deliberate freeze).                         │
│                                                                    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Layout rules:**
- ≤ 4 tiles visible (Bible §7.11 persona defaults).
- Whitespace: `--space-7` (Bible §5.4 Concept-C 50 % rule).
- Serif headings (GT Sectra) on section titles only.
- Metric hero uses `clamp(2.5rem, 4vw, 3rem)` light ivory (Bible §5.2.2).
- Every narrative paragraph is ≤ 3 sentences.
- No ambient motion; the surface is *still*.
- G8 Neural Pulse strip absent from Briefing landing (it is Ops-first).

### 4.3 Executive treatment across the shell

When Executive mode is active, every module the operator visits
receives the Concept-C treatment on its **top strip**, while retaining
the underlying components.

| Element | Executive treatment |
|---|---|
| Header chip | Same as other modes but with the `[ mode · executive ]` chip |
| LeftRail | Concept-A (consistent), but with `Advanced` + `Developer` items hidden |
| TopTabBar | Concept-A (consistent) |
| Right rail | Timeline collapsed to a 40 px stripe by default; opened rail is compact (200 px) and filtered to `[actors: accomplishment + approval]` |
| Approval Card | Serif primary sentence; other content unchanged |
| Master Bot header | Fully visible (executives care about progress); Plan Contract collapsed to a summary |
| Workforce Org Chart | Collapsed to a horizontal division-summary strip (D4 §10.1) |
| Signature graphics | Full Frame with serif title in Frame Head; motion disabled except G8 heartbeat |
| Danger ribbon | Fires as normal — no suppression |

### 4.4 Filters and defaults

- **Facet defaults** (any `<FacetBar>` on any surface):
  - Approvals: `risk = medium | high` (executives don't triage low-risk)
  - Timeline: `actors = accomplishment + approval`
  - Charts: no additional facets applied
- **Time-window default:** `last 24 h` (Briefing horizon).
- **Advanced Lens:** off by default; toggling shows narrative additions
  (never engineering chips).

### 4.5 Copilot in Executive mode

- Copilot ambient anchor visible at top-right.
- On open, Copilot greets with a **daily narrative** (Bible v2.1 §24
  Copilot capability C3 · Sprint 4+):
  *"Yesterday the Factory generated 5 candidates and promoted 2.
  Learning Division proposed 3 improvements — you approved 2, deferred
  1. All subsystems remain nominal."*
- Answers use full-sentence prose, not chip-strip decoration.
- **Advanced Lens trace-as-UI** (Bible v2.1 §24 · P24): disabled by
  default in Executive; enabling Advanced reveals the trace panel below
  each answer, but the language remains narrative.

### 4.6 Keyboard shortcuts (Executive-specific)

- `⌘⇧D` — jump to `/c/briefing`
- `⌘⇧A` — toggle Advanced Lens (narrative additions)
- `⌘M` — mode selector

### 4.7 Empty states (Executive)

- **Nothing to review** — *"You're all caught up. The Factory has no
  decisions pending your attention. → view yesterday's briefing"*
- **All nominal** — *"All 6 subsystems nominal. 8 divisions healthy.
  → view timeline"*
- **Awaiting activation** — *"The Factory is currently in freeze mode
  (Phase D not yet activated). → view activation plan"*

Colours: `--sig-ok` or `--sig-dormant`. Never red.

### 4.8 Executive mode does NOT:

- Show worker cards by default (they're for Operations).
- Show G8 Neural Pulse strip on landing (it's for Operations).
- Expose the ⌘K `developer` group.
- Show any raw ID, hash, or provenance triple by default.
- Show cost / latency / token-count chips (belongs to Developer).
- Auto-refresh at sub-second cadence (300 ms is fine — the surface
  isn't a mission critical console for this consumer).

---

## 5. Operations mode (default)

*"The Factory is running; you are here to observe and command."*

### 5.1 Consumer & goals

- **Consumer:** on-shift operator, factory supervisor, primary user.
- **Session length:** 30 minutes to 8 hours.
- **Goal:** monitor nominal state; triage exceptions; approve
  recommendations; understand what the Factory is doing.
- **Persona is the design's centre of gravity.** When in doubt,
  Operations wins.

### 5.2 Landing surface — `/c/mission`

Mission Control per Bible v2.1 §8.1 and D1 §8.1. Full six-question
layout, all panels visible, right rail expanded (240 px), G8 Neural
Pulse strip at the footer.

Everything about Mission Control renders in Concept A with Concept B
ambient pulse on running workers.

### 5.3 Operations treatment across the shell

The **default rendering** for every other module — Research, Approvals,
Portfolio, Execution, Factory, Prop Firm, Market Data, Governance,
Advanced — is authored assuming Operations mode. This is our *canonical
rendering*.

- Right rail: Timeline full, filter default `all`.
- LeftRail: full labels, all 10 primary modules visible (Approvals,
  Market Data, Governance included).
- Advanced module accessible via LeftRail; Developer via ⌘K only.
- Kill-posture arm/disarm control visible in status rail on hover.

### 5.4 Filters and defaults

- **Facet defaults:** no additional facets applied on any surface.
- **Time-window default:** `live ▸` on every time-scoped surface.
- **Advanced Lens:** off by default.

### 5.5 Copilot in Operations mode

- Ambient anchor visible top-right.
- On open, Copilot greets with a **status recap**:
  *"Master Bot is on plan #47 · step 3 of 7. Mutation Division is
  optimising the top 3 candidates. 3 approvals pending your review."*
- Answers use Division-voice sentences with chips for confidence /
  method under Advanced Lens.
- Every answer cites at least one Timeline event or artefact (Bible §24
  Copilot-Never-Invents rule).

### 5.6 Keyboard shortcuts (Operations)

- `⌘M` — mode selector
- `⌘A` — Approval Center
- `⌘/` — toggle Timeline expand/collapse
- `⌘⇧A` — toggle Advanced Lens
- `⌘P` — pin currently focused row
- `⌘K` — palette
- `Esc` — universal back / close drawer

### 5.7 Empty states (Operations)

Per Bible §15 and D2 §7 · D3 §8 · D4 §13 · D5 §12 — Operations mode is
the canonical rendering, so no new empty states are authored here. All
mode-neutral empty states apply.

### 5.8 Operations mode does NOT:

- Show the Concept-C editorial serif treatment (except on Briefing if
  accessed).
- Auto-open the ⌘K `developer` group.
- Show raw pod / container IDs.
- Show environment variables or feature flags.

---

## 6. Research mode

*"The lab. Deep focus. Following the thread."*

### 6.1 Consumer & goals

- **Consumer:** research analyst, quant.
- **Session length:** 1 – 4 hours (typical).
- **Goal:** explore strategies, knowledge, learning; investigate why a
  strategy behaved as it did; propose ideas.
- **Not the goal:** approve production actions (that belongs to
  Operations); build workflows (Master Bot does that).

### 6.2 Landing surface — `/c/research`

The Research Workspace per D1 §8.2 and Bible v2.1 §8. Structure:

```
┌────────────────────────────────────────────────────────────────────┐
│  Research Workspace                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Left main:  Operator storyline                                    │
│  ── Generate → Validate → Optimize → Certify workflow surface ──   │
│                                                                    │
│  Right pane: Evidence — currently-focused artefact                 │
│                                                                    │
│  Bottom:     Recent research history (last 20 cycles)              │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

- Concept B dominates — softer corners (14 px), luminance halos on
  active elements, ambient sparkle on running workers.
- G3 Knowledge Graph promoted to a first-class tile alongside recent
  history.

### 6.3 Research treatment across the shell

| Element | Research treatment |
|---|---|
| Right rail | Timeline filtered to `research + knowledge + learning + generation + backtest + mutation` |
| LeftRail | Full — Research pinned at top; Approvals visible; Prop Firm and Execution demoted (still visible) |
| Header | Adds a `[ knowledge graph ]` chip in the header for quick access to G3 |
| Workforce Org Chart | Divisions filtered by default to `Research + Mutation + Validation + Learning + Knowledge` |
| Approval Card | Corners softer (14 px); ambient glow *not* applied (approvals are decisions, not living work) |
| Signature graphics | Full ambient motion (Concept-B); G3 promoted; G6 hidden by default |
| Copilot | Persistent side panel option — 320 px right side companion for the session |

### 6.4 Filters and defaults

- **Facet defaults:**
  - Approvals: `modules = learning + evaluation`
  - Timeline: `actors = research + knowledge + learning + generation + backtest + mutation`
  - Workforce: `divisions = Research + Mutation + Validation + Learning + Knowledge`
- **Time-window default:** `last 7 d` (Research horizon).
- **Advanced Lens:** on by default (Research analysts want the chips).

### 6.5 Copilot in Research mode

- **Companion mode** — Copilot can dock as a persistent 320 px right
  panel via `⌘/`. In Research mode this is the default posture on
  wide viewports.
- On open, Copilot greets with **the current research thread**:
  *"You were investigating regime-detection strategies. Research
  Division retrieved 6 new arxiv papers overnight; 2 passed dedup."*
- Answers automatically expose the **trace panel** under Advanced
  Lens (Bible v2.1 §24 · P24 codified):

```
COPILOT · Research Division retrieved 6 arxiv papers on regime detection.

trace ▾
├─ retrieval    (0.7 s)   arxiv corpus · k=6 · knowledge base filter
├─ ranking      (0.3 s)   trust-tier weighted · dedup at 0.78
├─ synthesis    (1.1 s)   GPT-5.2 with 4 citations
└─ evidence     4 references
     · arxiv:2401.09883  →
     · arxiv:2402.11291  →
     · arxiv:2401.00742  →
     · arxiv:2403.10884  →
```

- Trace steps are clickable; each step shows a per-step summary.
- Trace never invents; if the Copilot cannot cite a source, it says so.
- Trace styling: mono step labels, Division-voice summaries.

### 6.6 Keyboard shortcuts (Research)

- `⌘M` — mode selector
- `⌘G` — jump to Knowledge Graph (G3)
- `⌘/` — dock / undock Copilot companion
- `⌘R` — new research cycle
- `⌘⇧E` — export current investigation as an evidence permalink

### 6.7 Empty states (Research)

- **No research yet** — *"No research cycles have run today. Start your
  first investigation. → Run cycle · view knowledge graph"*
- **Empty knowledge graph** — *"The Knowledge Base is dormant until
  Phase C activation. → view activation plan"* (dormant, not error)
- **Copilot uninitialised** — *"Copilot is ready. Ask about any
  visible strategy, knowledge item, or timeline event."*

### 6.8 Research mode does NOT:

- Show Prop Firm module as a primary destination.
- Auto-open the ⌘K `developer` group.
- Suppress ambient motion (Research *wants* the aliveness — Concept B
  is dominant here).
- Show G8 Neural Pulse strip on landing (it's Operations-first).

---

## 7. Developer mode

*"Diagnose the machine. Confirm nothing is drifting."*

### 7.1 Consumer & goals

- **Consumer:** backend engineer, on-call, incident responder.
- **Session length:** minutes (nominal) to hours (during incident).
- **Goal:** verify subsystem health; inspect internals; correlate
  errors to Timeline events; escalate or resolve.
- **Not the goal:** editing configuration on the fly (that requires
  a governance-gated flow in Advanced).

### 7.2 Landing surface

Developer mode is unusual: its default *"landing"* is not a page — it
is the ⌘K palette **pre-opened** to the `developer` group, allowing
the engineer to jump immediately to what they need.

```
┌──────────────────────────────────────┐
│  ⌘K                                   │
│  ┌────────────────────────────────┐  │
│  │ Search actions, modules, IDs... │  │
│  └────────────────────────────────┘  │
│                                       │
│  DEVELOPER                            │
│    ▸ health · subsystems              │
│    ▸ scheduler · queues               │
│    ▸ errors · last 100                │
│    ▸ audit log                        │
│    ▸ feature flags                    │
│    ▸ env vars                         │
│                                       │
│  RECENT                               │
│    · errors · last 100                │
│    · scheduler                        │
│                                       │
│  NAVIGATE                             │
│    ▸ mission control                  │
│    ▸ ...                              │
└──────────────────────────────────────┘
```

If the engineer closes the palette without selecting, the previously
visited page renders (falling back to Mission Control on first login).

### 7.3 Developer treatment across the shell

| Element | Developer treatment |
|---|---|
| Advanced Lens | Auto-on (all Advanced chips visible everywhere) |
| Right rail | Timeline filter includes `error + telemetry + env` (D2 §4 developer actors) |
| LeftRail | Adds `Advanced` at full priority; also shows `Developer` sub-items under Advanced |
| Timeline row | Full method / duration / provenance chip strip visible on every row |
| Master Bot Plan | Every step shows `[worker-id]` `[method]` `[duration]` `[latency]` chips |
| Worker card | Shows internal pod-id, container-id, worker-uuid, restart count, p95 latency |
| Signature graphics | Diagnostic overlays enabled (G3 shows dedup thresholds; G4 shows BI5 sweep telemetry; G5 shows raw fill payloads) |
| Approval Card | Shows `[method chip]` `[confidence]` `[rollback SLA seconds]` |
| Copilot | Answers include full trace-as-UI expanded by default; token / latency chips visible |
| Header | Adds `[ ● alerts N ]` chip (auto-refreshing) |
| Status rail | Extended — chip per subsystem shows p95 latency inline: `● orch · 42 tasks · p95 84 ms` |

### 7.4 Filters and defaults

- **Facet defaults:**
  - Timeline: `all + errors + telemetry`
  - Approvals: `all`
  - Governance: `all` (developers watch this too)
- **Time-window default:** `live ▸`.
- **Advanced Lens:** on (always — cannot be turned off in Developer
  mode; it's the mode's identity).
- **Timeline collapse:** defaults to expanded (developers want the
  stream).

### 7.5 Copilot in Developer mode

- Ambient anchor visible.
- On open, Copilot greets with **the last error**:
  *"Two errors in the last hour. Both from the `governance` subsystem
  — hard-rail cache miss on strategy retrieval. Trace attached."*
- Trace-as-UI expanded by default (Bible v2.1 §24 · P24).
- Each trace step exposes token / latency / cost chips inline
  (Advanced-Lens-visible everywhere; this is the only mode where these
  chips appear by default).

### 7.6 Keyboard shortcuts (Developer)

- `⌘M` — mode selector
- `⌘K` — palette (opens to `developer` group)
- `⌘⇧E` — errors · last 100
- `⌘⇧S` — scheduler / queues
- `⌘⇧F` — feature flags
- `⌘⇧L` — audit log

### 7.7 Empty states (Developer)

- **No errors** — *"No errors in the selected window. All subsystems
  reporting nominal. → view audit log"* (`--sig-ok`)
- **No telemetry** — *"Telemetry pipeline has not emitted events yet.
  This is expected during freeze. → view feature flags"* (`--sig-dormant`)
- **Scheduler empty** — *"Scheduler queues are empty. No tasks in
  flight. → view worker pool state"*
- **Feature flags absent** — *"No feature flags are toggleable in this
  environment. → view env"*

### 7.8 Developer mode does NOT:

- Change the underlying components — every affordance is an Advanced-
  Lens chip addition, not a component swap.
- Suppress kill posture (it fires here as everywhere else).
- Break Division voice — developers still see `Research Division
  retrieved …` in the Timeline; the trace beneath *adds* the
  engineering chips.
- Introduce a new colour hue.

---

## 8. Cross-mode consistency (what stays constant regardless)

### 8.1 The invariants

- Shell chrome (LeftRail, TopTabBar, StatusRail, right rail) is
  **always Concept-A** — the tool is consistent under the register.
- Six-signal palette applies identically.
- Terminology dictionary (Bible §19.4) applies identically.
- Division voice (D2 Addendum) applies identically.
- Motion budget durations (Bible §6.1) apply identically.
- Danger ribbon fires in every mode.
- Kill posture is visible in every mode.
- Every approval action has the same 4 verbs in the same order
  (D3 §6).
- Signature Frame (D5 §2) worn by every G-graphic in every mode.
- Backend Feature Freeze applies identically.

### 8.1a Decision Identity — the truth invariant

Adopted 2026-07-20 as a permanent invariant alongside Context Never Lost.

**Principle.** A decision, approval, metric, or evidence object must
always represent the **same underlying truth** in every personalization
mode. Modes may change emphasis, layout, wording, and density, but they
must never alter the underlying values or meaning.

**What is inviolate across modes:**

| Object | Truth that must not shift |
|---|---|
| Approval | `approval_id`, `origin`, `risk` (low/med/high), `evidence_ref`, `rollback_sla_sec`, `actions[]`, `submitted_at`, `submitted_by` |
| Metric | numeric value, unit, computation method, source endpoint |
| Evidence | pipeline stage, confidence, method, provenance triple, lineage |
| Recommendation | recommendation text, affected artefacts, risk classification |
| Worker state | current state chip, state-history line, current subject |
| Plan step | state icon (`✓ ▸ ○ ⏸ ⨯ ⤴`), Division-voice sentence, HITL gate identity |
| Lineage | ancestors + descendants set, edge types, traversal timestamps |
| Signal chip | letter glyph + colour + underlying data source |
| Provenance | origin, trust_tier, signed_by |
| Timestamp | ISO UTC value on hover (presentation may relative-format) |

**What modes MAY alter:**

- Typography (serif vs mono vs sans).
- Density and spacing.
- Which fields are visible at first glance (chip-strip visibility).
- Narrative wording around a number (e.g., "confidence 0.87" vs "high
  confidence at 0.87" vs "high").
- Density of ambient motion.
- Which surface is the landing.
- Which chips get promoted to the top card row.

**What modes MUST NOT alter:**

- The underlying `0.87` confidence value.
- The `low/medium/high` risk classification.
- The set of evidence items linked to an artefact.
- The approval identity, its recommendation, or its downstream effect.
- The count of pending approvals, workers online, or open advisories.
- The letter-glyph on any signal chip (`P W F A I`).
- The Division voice attribution.
- The ordering rule of the Attention panel (severity, then age — §8.8
  in Bible).
- The eight pipeline stages, in their canonical order.

**Anti-patterns that violate Decision Identity:**

- ❌ Rounding a metric differently per mode (e.g., `91.4 %` in Ops but
  `91 %` in Executive). Presentation of significant figures follows a
  single rule (Bible §19.5); mode does not.
- ❌ Hiding a piece of evidence in one mode that is visible in another
  as a *filter* rather than as a *lens*. Progressive disclosure hides
  detail behind Advanced Lens — the underlying evidence set is
  unchanged.
- ❌ Reclassifying a `medium` risk as `low` because the current mode
  filters it out. Filters change *what is shown*; they never change
  *what is true*.
- ❌ Renaming the `dedup threshold` metric to *"deduplication sensitivity"*
  in Executive mode. Terminology dictionary (Bible §19.4) is
  mode-invariant.
- ❌ Executive mode reporting "3 approvals pending" while Operations
  mode reports 4. The count is a truth, not a preference.

**Verification test (per Sprint acceptance):**

Take any artefact / approval / metric visible in one mode. Switch to
another mode. The identity, count, classification, and lineage must be
byte-identical. Only rendering may differ.

**Rule of Reversibility:** presenting the same object in every mode
must round-trip — the exact same operator, seeing the exact same
object across all four modes, arrives at the same understanding of
*what it is* (even if the *rendering* moves their attention differently).

**Interaction with Advanced Lens.** Advanced Lens is a lens, not a
filter (Bible §11 · D1 §11). Toggling Advanced Lens reveals additional
chips (method, confidence, provenance) but never changes the underlying
truth. Executive-Advanced-off and Executive-Advanced-on show the *same*
approval with the *same* recommendation; Advanced-on just adds chips.

**Implementation contract (Sprint 1 architecture):**

- Every domain object has a single canonical shape (see D3 §7 `Approval`,
  D4 §14 `MasterBotSnapshot`, D2 §12 `TimelineEvent`, D5 §14
  `SignatureFrame<T>`).
- Mode-specific rendering happens at the **presentation layer only** —
  components accept the canonical object plus a `mode` prop.
- No mode-conditional business logic — no `if (mode === 'executive')
  round(value, 0)`.
- Adapters (`services/*.js`) produce canonical objects; components
  present them.
- Selectors are mode-agnostic — `selectPendingApprovals()` returns the
  same set regardless of mode; only the display component decides which
  to prioritise or annotate.

---

## 8.2 What differs — a single table

| Property | Executive | Operations | Research | Developer |
|---|---|---|---|---|
| Concept-D emphasis | C60 · A30 · B10 | A60 · B30 · C10 | B60 · A30 · C10 | A70 · Diag30 |
| Density | Cinema | Compact | Cozy | Compact |
| Ambient motion | none (G8 heartbeat only) | Concept-B pulse on active | Concept-B glow amplified | signal-only |
| Right rail default | 40 px stripe | 240 px full | 320 px Copilot-companion option | 240 px + diagnostic actors |
| Timeline filter | accomplishment + approval | all | research + knowledge + learning + gen + backtest + mut | all + errors + telemetry + env |
| Time-window default | last 24 h | live ▸ | last 7 d | live ▸ |
| Advanced Lens default | off | off | on | on (locked) |
| Copilot posture | ambient anchor | ambient anchor | companion panel (320 px) | ambient anchor + trace-open |
| Approval risk-filter | medium + high | all | learning + evaluation | all + governance |
| Landing surface | `/c/briefing` | `/c/mission` | `/c/research` | ⌘K palette open |
| Corner radius (cards) | 6 px | 10 px | 14 px | 10 px |
| Font emphasis | Serif on titles | Mono on numbers | Sans on prose | Mono on IDs |
| Whitespace | `--space-7` | `--space-5` | `--space-6` | `--space-5` |
| Hidden LeftRail items | Advanced, Developer | Developer | Prop Firm, Execution (demoted, not hidden) | none |
| G8 Neural Pulse on landing | no | yes | no | yes |

---

## 9. Facet grammar per mode (Bible §11.6)

The `<FacetBar>` component (Bible §11.6) is shared across all modes.
Each mode provides *default filter values*; the operator can override
at any time; overrides persist across mode switches (Context Never Lost).

```
[ All ▾ ]   [ <primary> ▾ ]   [ <secondary> ▾ ]   [ Time-window ]   [ q ⌘K ]
```

Default overrides per mode:

| Surface | Executive | Operations | Research | Developer |
|---|---|---|---|---|
| Approvals | risk ≥ medium | none | modules = learning + evaluation | all + governance |
| Timeline | actors = accomp + approval | none | actors = research + knowledge + learning + gen + backtest + mut | all + errors + telemetry + env |
| Workforce | divisions collapsed | all divisions | Research + Mutation + Validation + Learning + Knowledge | all + Maintenance + Monitoring |
| Charts | none | none | none | + diagnostic overlays |
| Strategies | none | none | none | + provenance triple visible |

**Rule:** operator overrides always win. Mode defaults apply only
when the operator has not set a value.

---

## 10. Time-window defaults per mode (Bible §7.13)

| Mode | Default | Rationale |
|---|---|---|
| Executive | `last 24 h` | Briefing horizon |
| Operations | `live ▸` | On-shift monitoring |
| Research | `last 7 d` | Research thread continuity |
| Developer | `live ▸` | Incident response |

Cascade rule (Bible §7.13): once the operator sets a time window on any
surface, that value cascades to every other time-scoped surface. Mode
default applies only on entry.

---

## 11. Copilot per mode (Bible §24 · P24 codified)

### 11.1 The Copilot contract (all modes)

- **Copilot never acts.** It observes and explains. Approvals, runs,
  and mutations require explicit operator action.
- **Copilot never invents.** Every answer cites at least one Timeline
  event or artefact.
- **Copilot honours Division voice.** Responses read as narrative
  Division-voice sentences.

### 11.2 Per-mode differences

| Property | Executive | Operations | Research | Developer |
|---|---|---|---|---|
| Anchor | top-right ambient | top-right ambient | top-right ambient + companion option | top-right ambient |
| Opening greeting | narrative recap | status recap | current thread | last error |
| Trace-as-UI (P24) | Advanced-Lens-only, prose | Advanced-Lens-only, chips | on by default under Advanced | on by default, chips + latency |
| Language emphasis | narrative prose | Division-voice sentences | Division-voice + method chips | Division-voice + full engineering chips |
| Cost / latency chips | hidden | Advanced-Lens-only | Advanced-Lens-only | on by default |
| Response length | 2 – 4 sentences | 1 – 2 sentences | 3 – 6 sentences (thread continuity) | 1 – 2 sentences + trace |
| Session memory scope | current session narrative | current step | full research thread | last N errors + last incident |

### 11.3 Trace-as-UI anatomy (P24 — same across modes)

```
COPILOT ANSWER

Research Division retrieved 6 arxiv papers on regime detection.

trace ▾    (visible on Advanced Lens; auto-expanded in Research + Developer)
├─ retrieval     0.7 s    arxiv corpus · k=6
├─ ranking       0.3 s    trust-tier weighted
├─ synthesis     1.1 s    GPT-5.2 · 4 citations
└─ evidence      4 refs   arxiv:2401.09883, arxiv:2402.11291, …
```

- Trace steps clickable → each opens Evidence Drawer scoped to the
  step's data.
- Trace never renders on Layer 1 unless Advanced Lens is on.
- Trace styling: mono step labels, Division-voice summaries, right-
  aligned duration.

### 11.4 Copilot never renders

- A "typing…" animation (undermines premium positioning; use text-based
  progress instead).
- An avatar (Bible §1 anti-pattern).
- A "How can I help?" prompt (undermines Division voice; Copilot opens
  with a *fact*, not a *question*).
- A rating widget (feedback happens through governance, not through
  thumbs-up-thumbs-down).

---

## 12. Landing surface per mode

| Mode | Landing URL | Default posture |
|---|---|---|
| Executive | `/c/briefing` | Cinema · Concept-C |
| Operations | `/c/mission` | Compact · Concept-A |
| Research | `/c/research` | Cozy · Concept-B |
| Developer | ⌘K palette (developer group) then fallback to last visited | Compact · Concept-A + Advanced |

Deep-linking overrides landing: navigating to any URL directly always
respects the URL, regardless of mode. Mode determines only the
*default* landing on plain login.

---

## 13. Persona-to-mode mapping (assignment)

- Modes are **not** roles or permissions. Any authenticated user can be
  assigned any subset of modes.
- Default mode assignment on first login:
  1. From SSO / invitation claim if present.
  2. Otherwise **Operations**.
- Multi-mode users see all their available modes in the switcher.
- Mode assignment is edited in `/c/advanced/users` (out of Sprint 1
  scope; Sprint 3 target).

**Rule:** mode is *how* the operator sees the product, not *what* they
are allowed to do. Authorisation is orthogonal to mode.

---

## 14. Mode × posture matrix

Mode is orthogonal to posture (workstation / tablet / briefing). The
combinations produce distinct experiences:

| Mode | Workstation | Tablet | Briefing (Cinema) |
|---|---|---|---|
| Executive | full Concept-C on Briefing | narrative-collapsed Briefing | signature *Executive briefing wall* — most editorial rendering |
| Operations | full cockpit | 2-column MC | Operations briefing wall (metric-block + G8 dominant) |
| Research | full Workspace | 2-col Workspace | Research narrative summary — a "poster" of the current thread |
| Developer | full palette + diagnostics | read-only diagnostics | Developer briefing (rare — most incidents happen at workstation) |

**Below 900 px** (mobile): every mode collapses to read-only mode
regardless (per Bible §16). No approvals on phones.

---

## 15. Motion physics (per mode)

Motion *budget* is identical (Bible §6.1). Motion *density* differs:

| Mode | Ambient motion | Transition motion | Number tween |
|---|---|---|---|
| Executive | none (G8 heartbeat only) | 400 ms Editorial tier | 600 ms editorial (numbers *etch*) |
| Operations | 2 s pulse on running workers · G8 continuous | 200 ms medium tier | instant + 120 ms flash |
| Research | Concept-B luminance amplified on active nodes/edges | 320 ms slow tier + 40 ms stagger | 400 ms useSpring (numbers *count*) |
| Developer | signal-only (motion only when an error arrives) | 120 ms fast tier (efficiency) | instant |

`prefers-reduced-motion` collapses to opacity-only in every mode.

---

## 16. Accessibility (mode-consistent)

- WCAG 2.2 AA on every mode.
- Screen-reader announces mode changes: *"switched to Research mode"*
  (debounced to at most 1 per 3 s).
- Every mode-specific element has `aria-label` including the mode name
  where the label is mode-dependent.
- Focus ring 2 px `--sig-info` in every mode.
- Keyboard-first preserved: `⌘M` opens the mode switcher; the switcher
  is fully keyboard-navigable.
- Colour-blind fallback: mode chip carries both colour and text
  (`[ mode · operations ]`) — never colour alone.

---

## 17. Data contract (frontend expectation)

Mode state is a single field in the workspace state store (Bible
v2.1 §1.4.4):

```ts
type WorkspaceState = {
  mode: 'executive' | 'operations' | 'research' | 'developer';
  advanced_lens: boolean;
  density: 'compact' | 'cozy' | 'cinema';
  // ...rest of Context Never Lost fields
};
```

Mode is:
- Persisted in `localStorage` under `strategyFactory.mode`.
- Set via `WorkspaceState.setMode(newMode)` — triggers the 200 ms
  crossfade + surface re-layout.
- Not sent to backend (Feature Freeze — no server state).

Advanced Lens interaction: setting `mode = 'developer'` forces
`advanced_lens = true` and locks it; unlocking requires switching to
another mode first.

Mode-conditional rendering in components: prefer *props-driven*
conditional over branching:

```jsx
// Preferred
<MetricCard variant={conceptFor(mode)} density={densityFor(mode)} />

// Avoid
{mode === 'executive' ? <MetricCardC/> : <MetricCardA/>}
```

The **`conceptFor(mode)`** and **`densityFor(mode)`** helpers make
mode-mapping declarative and testable.

**Feature Freeze respected.** All logic is frontend-only.

---

## 18. Factory Replay compatibility

Mode is orthogonal to Factory Replay (Bible §16). When Replay is
active:

- Executive sees a narrative *"as of"* on the Briefing.
- Operations sees Mission Control state as of the scrub time.
- Research sees the Knowledge Graph and Timeline as of the scrub time.
- Developer sees historical errors and telemetry as of the scrub time.

The same underlying `at` prop cascade applies (Bible §7.13, §10.2.3);
mode adjusts only rendering, never time.

---

## 19. Sprint acceptance criteria

Personalization Modes ship only if:

- ✅ 16-item Design Principles Checklist confirmed (§0)
- ✅ Mode selector component works via click + `⌘M`
- ✅ Mode change is a 200 ms crossfade — no page reload
- ✅ Context Never Lost verified across every mode transition (Bible §1.4.4)
- ✅ `/c/briefing` renders per §4.2 (Executive · Concept-C)
- ✅ `/c/mission` renders per §5.2 (Operations · Concept-A · default)
- ✅ `/c/research` renders per §6.2 (Research · Concept-B)
- ✅ Developer palette-first landing per §7.2
- ✅ Every mode preserves the six invariants (§8.1)
- ✅ Mode-specific filter defaults applied only when operator has not overridden
- ✅ Copilot per-mode behaviour verified (§11)
- ✅ Trace-as-UI (P24) renders per mode rules (§11.3)
- ✅ Mode × posture matrix verified (§14)
- ✅ Mode-specific empty states authored (§4.7, §5.7, §6.7, §7.7)
- ✅ A11y — mode change announced; keyboard-navigable switcher (§16)
- ✅ Mode persists in localStorage
- ✅ Kill posture fires in every mode (§3.5)
- ✅ Decision Identity verified — swap between all 4 modes on the same approval / metric / lineage; underlying values byte-identical (§8.1a)
- ✅ Advanced Lens forced-on in Developer mode (§17)
- ✅ Screenshot per mode × per posture (12 screenshots for archive)
- ✅ `data-testid` on mode selector, every mode option, every mode-specific chip

---

## 20. What D6 does NOT include

- Coded prototype (Sprint 2 implements mode switcher).
- Full copy library — mode-specific narrative variations belong to D7.
- SSO claim → mode mapping (Sprint 3 admin feature).
- Multi-user mode assignment UI (Sprint 3).
- The full Executive Briefing auto-narration (Bible v2.1 §7 backlog
  O10 — Sprint 5 · post-Copilot C3).

---

## 21. Next: D7 — Empty / loading / error / dormant pattern library

Per Bible v2.1 §25. D7 codifies:

- 40+ authored copy specimens across every module × every state ×
  every mode.
- Empty-state icon library (from lucide-react).
- Loading-state narrative templates by duration.
- Error-state templates by tier (info · warn · critical).
- Dormant-state templates by activation phase.
- Replay-empty templates.
- Mode-specific tone adjustments per empty state.

Expected timeline: 2–3 days.

---

## 22. Note on post-D8 experience design suite

Per operator instruction (2026-07-20): after D8 completion, before
Sprint 1 implementation begins, an experience-design suite will be
authored covering:

- **Strategy Experience** — end-to-end journey from generation to
  production
- **Authentication Experience** — first login through session lifecycle
- **First-Time User Journey** — the moment-zero experience per mode
- **Daily Operator Journey** — the routine-shift experience
- **Cross-Module Navigation** — the graph of intra-workspace transitions

D6 lays the foundation for these — modes will be a lens over every
journey. This is noted here so D7 and D8 author their contents with
that suite in mind (empty states will need mode × journey variants;
Sprint 1 plan will sequence accordingly).

---

*End of D6 — Personalization Modes.*
*All 16 checklist items confirmed. Four modes codified with cross-mode
consistency guaranteed. Copilot trace-as-UI (P24) integrated. Bible
v2.1 · D4 Purpose Before Status · D5 Signature Frame · Backend Feature
Freeze all respected.*
*Awaiting your review before D7 begins.*

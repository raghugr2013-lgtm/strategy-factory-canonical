# Frontend Design Bible v2.0 — Delta

> **Layered on top of v1.0** (approved 2026-07-20). Only additions/refinements below.
> **Governing philosophy:** design first, refine second, implement third. Craftsmanship > speed.
> **No implementation begins** until every design artefact in §5 is signed off.

---

## 1. Mandate change

v1.0 was a plan to *evolve* the existing shell into an operator centre.
v2.0 is a plan to *design* the best AI Research & Operations platform available.

The Bible is our **foundation, not our limitation.** Any Bible rule can be
challenged if a better solution emerges — but the six operator questions
(§2 in v1.0) and the five-layer IA (§3 in v1.0) are inviolate.

---

## 2. Personalization modes (NEW — supersedes v1.0 §5.3 density-only)

Persona-driven workspace modes. One toggle in the header. Persist per-user.

| Mode | Consumer | Default landing | Density | Right rail | Hidden elements |
|---|---|---|---|---|---|
| **Executive** | Founder / stakeholder | Mission Control (read-only) | Cinema | Timeline (compact) | All L4/L5; Approvals unless > 0 |
| **Operations** (default) | On-shift operator | Mission Control (full) | Compact | Timeline (full) | L5 only |
| **Research** | Analyst | Research module (Workspace) | Compact | Timeline filtered to Research/Knowledge/Learning events | Prop firm, execution unless flagged |
| **Developer** | Backend engineer | ⌘K prompt open | Compact | Timeline filtered to errors/telemetry | Nothing hidden — L4 + L5 fully visible |

Mode is orthogonal to posture (workstation / tablet / briefing). A tablet-Executive is different from a workstation-Executive.

**Rule:** switching mode never reloads the page — the shell smoothly re-lays out with 200 ms crossfade.

---

## 3. Signature graphics — the "AI made this platform" moments (NEW)

These are the surfaces that a first-time visitor will remember. Each must be **explanatory, not decorative.** Each must be beautiful *because* it clarifies meaning.

### 3.1 Signature graphic inventory

| # | Graphic | Purpose | Location | Data source |
|---|---|---|---|---|
| G1 | **AI Workforce Org Chart** | 8 divisions × workers as living cards, ambient pulse when active, connecting lines showing hand-offs | Factory module top; also embedded on Mission Control Q3 tile expand | `/api/ai-workforce/*` + 5 retrofit `/health` |
| G2 | **Strategy Pipeline Ribbon** | 8-stage pipeline visualisation with real-time artifact position | Every artifact page; also as a summary strip on Mission Control | derived from strategy state + promote/retro events |
| G3 | **Knowledge Graph** | Force-directed graph of KB items, colour by trust_tier, size by usage count, edges by promote_events | Knowledge module landing (post-C.1 activation) | `/api/knowledge/query`, `/api/knowledge/promote-events` |
| G4 | **Market Coverage Heatmap** | Symbol × TF grid with per-cell completeness bar + gap markers | Market Data module signature view | `/api/admin/bi5/*` |
| G5 | **Execution Quality Constellation** | Scatter: fill quality × slippage × latency per broker, animated per-tick | Execution module landing | `/api/execution/quality`, `/api/execution/attribution` |
| G6 | **Portfolio Risk Surface** | 3D-lookalike surface plot: allocation × correlation × drawdown | Portfolio Intelligence | `/api/portfolio/*` |
| G7 | **Learning Evolution Timeline** | Meta-Learning recommendations over time, colour by outcome, size by impact | Meta-Learning section (Advanced) | `/api/meta-learning/*` |
| G8 | **Neural Activity Sparkline strip** | Ambient — 6 sparklines representing 6 subsystems, live-updating | Mission Control footer, between panels and status rail | derived from `/api/health/system` retrofit blocks |

### 3.2 Design principles for signature graphics

- **Meaning ≥ aesthetic.** Every colour, every line, every animation must carry information.
- **Static-first legibility.** The graphic must be readable as a still frame — motion is ornament, not carrier.
- **Same palette.** No graphic introduces a new colour. All chart colours come from the 8-hue chart palette in v1.0 §5.1.
- **Responsive fidelity.** Every graphic degrades gracefully: rich on workstation, essential on tablet, static-image on briefing/print.
- **Explainable in one sentence.** If the operator can't explain what a graphic shows in one sentence, redesign it.

---

## 4. AI Copilot — from panel to operating-system layer (EXPAND v1.0 §9.2)

The current `CopilotPanel.jsx` is a chat surface. v2.0 elevates it to a **first-class shell layer** that is context-aware, evidence-aware, and workflow-aware.

### 4.1 Copilot as ambient layer

- Persistent floating anchor in the top-right of every screen (small, muted).
- One click / `⌘/` opens the Copilot drawer.
- The drawer knows: current module, current artifact in focus, last 6 timeline events, active approvals count.
- Copilot answers reference this context by default: "*based on the strategy you're currently viewing*", not "*please give me the strategy id*".

### 4.2 Copilot capabilities (progressive)

| Tier | Capability | Ships |
|---|---|---|
| C1 | Grounded Q&A — answer questions about currently visible data with evidence citations | Sprint 2 |
| C2 | Explain-this — click any KPI, worker, chip → "explain in plain English" from Copilot with evidence | Sprint 3 |
| C3 | Workflow narration — Copilot describes what the Factory did in the last N minutes in prose | Sprint 4 |
| C4 | Semantic search — natural language across artifacts, timeline, approvals | Sprint 5 |
| C5 | Never — action initiation. Copilot never approves, never runs a cycle, never mutates state. | — |

C5 is a hard rule. Copilot observes and explains. It never acts.

### 4.3 Copilot never invents

- Every answer cites at least one timeline event or artifact.
- Every citation is a hoverable chip that reveals the source event.
- If Copilot doesn't have grounded evidence, it says so — never speculates.

---

## 5. Design-first workflow (NEW)

Before any code lands in Sprint 1, we produce these design artefacts. Each is a distinct deliverable requiring your sign-off.

### 5.1 Deliverable sequence

| # | Deliverable | Format | Sign-off gate |
|---|---|---|---|
| **D1** | **Mission Control high-fidelity wireframe** | ASCII + labelled component annotations in a single Markdown doc | Approves the six-panel layout + status rail + right rail placement |
| **D2** | **AI Activity Timeline visual spec** | Interaction spec + row anatomy + 10 activity type samples + motion rules | Approves the timeline experience |
| **D3** | **Approval Center visual spec** | Card anatomy + filter model + bulk-action semantics + confirmation modal spec | Approves the unified queue |
| **D4** | **Master Bot & Workforce Org Chart visual spec** (G1) | Layout + card anatomy + ambient motion rules + interaction spec | Approves the CEO metaphor |
| **D5** | **Signature-graphic gallery** (G2–G8) | Per-graphic spec: purpose + data → visual mapping + degrade rules + interaction | Approves the graphics catalogue |
| **D6** | **Personalization modes spec** | Per-mode landing / density / rail-content / hidden-elements table | Approves the persona model |
| **D7** | **Empty / loading / error / dormant state pattern library** | 30-40 authored copy specimens across every module | Approves the narrative-state discipline |
| **D8** | **Sprint 1 detailed plan** | Component-by-component work items with per-item design reference | Locks Sprint 1 scope |

Each deliverable takes 1-3 days. Total design phase before Sprint 1: **~2 weeks**.

### 5.2 Design phase ritual

For each deliverable:

1. I draft the spec.
2. You review and either **approve**, **request revisions**, or **reject**.
3. On approval, the spec becomes canonical — its rules bind implementation.
4. On rejection, the underlying design question is captured for a re-attempt with new constraints.

No code is written during the design phase. Craftsmanship discipline: we do not implement what we do not first understand.

### 5.3 Design tooling

Given constraints (no Figma access from this pod), design specs will use:

- **ASCII wireframes** for layout (fast, precise, review-in-terminal).
- **Structured Markdown tables** for component anatomy, colour tokens, motion rules.
- **Interactive prototypes** later in Sprint 1 — coded once the spec is signed off. Each spec compiles to an isolated Storybook-like page for interaction review.

If you have Figma / Sketch access and want richer visuals, we can supplement — but the source of truth remains the Markdown spec (so it stays in git alongside code).

---

## 6. Challenges I want to raise now (before D1 starts)

Per your instruction to challenge everything, three architectural questions worth resolving before D1:

### 6.1 Should Mission Control be the landing, or a discipline?

**Two options:**

- **Option A (v1.0 default)** — Mission Control is the landing. Every login opens it.
- **Option B** — Landing is *persona-aware*. Executive lands on a Mission Briefing view (5-second read); Operations lands on Mission Control (full); Research lands on Research Workspace; Developer lands on ⌘K.

**My recommendation: Option B.** It makes the platform feel intelligent from the first pixel. Different personas need different first-moments. Mission Control remains the *hero* view — always one keystroke away — but it's not always the landing.

### 6.2 Should Diagnostics be its own module or a mode?

**Two options:**

- **Option A (v1.0 default)** — Diagnostics moves into an Advanced drawer.
- **Option B** — Diagnostics becomes an **Advanced posture**, not a module. Toggling `Advanced` overlays diagnostic chips on every existing module rather than a separate destination.

**My recommendation: Option B.** It matches the "layers not tabs" principle. Diagnostics is a *lens*, not a place.

### 6.3 Should Approvals live in the header or as a module?

**Two options:**

- **Option A (v1.0 default)** — First-class module at `/c/approvals`.
- **Option B** — Persistent header chip that opens a right-side drawer.
- **Option C (new)** — **Both.** Chip in header for glanceability (count + one-click drawer). Full module at `/c/approvals` for triage. Drawer and module render the same components; the module is just the drawer at full width.

**My recommendation: Option C.** Approvals is critical enough to deserve both discovery paths.

---

## 7. What v2.0 does NOT change from v1.0

- Six operator questions ✅ inviolate
- Five-layer IA ✅ inviolate
- Colour palette (6 signals) ✅ ceiling preserved
- Typography (mono + Manrope/Söhne) ✅ preserved
- Motion budget (3 durations only) ✅ preserved
- Spacing grid (4-pt) ✅ preserved
- Danger ribbon reserved for Critical only ✅ preserved
- Evidence-first over completion ✅ preserved
- Copilot as observer, never actor ✅ preserved

---

## 8. Immediate next step

I recommend we spend the next 2 weeks purely on **D1 → D8** in the order listed in §5.1. No code lands in that window.

To start, I need your steer on three questions:

**Q1.** Approve v2.0 additions in §2 (personalization modes) and §3 (signature graphics) and §4 (Copilot elevation)? Or push back on any of them?

**Q2.** Which of the three §6 challenges do you want to resolve now, and how?
- §6.1 landing: A or B?
- §6.2 diagnostics: A or B?
- §6.3 approvals: A or B or C?

**Q3.** Should I begin **D1 (Mission Control wireframe)** first, or would you rather I begin with **D4 (Master Bot & Workforce Org Chart)** — the most visually differentiating spec — to establish the visual bar early?

Once you answer these three, I begin the first deliverable. No code, no shell mutations, no premature commitment. Just design work in Markdown, reviewable in git, on the way to the best AI Research & Operations platform available.

---

## Appendix A — Bible version history

- **v1.0** (2026-07-20) — approved. Original architecture: 21 sections + 3 appendices.
- **v2.0 delta** (2026-07-20) — this document. Layers personalization modes, signature graphics, Copilot elevation, design-first workflow, and three architectural challenges.

Full merged Bible v2.0 will be produced once the three §8 questions are answered — v1.0 rules that remain unchanged simply carry forward.

---

*End of v2.0 delta.*
*Awaiting operator answers to §8 Q1, Q2, Q3 before design phase begins.*

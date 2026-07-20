# E3 — First-Time User Journey

> The *moment-zero* experience — how a first-time operator learns the
> product without wizards, tours, tooltips, or onboarding modals. The
> product teaches itself through the same components it operates with.
>
> **No wizards.** No "Take a tour" buttons. No "Welcome to Strategy
> Factory!" cards. No modal overlay walkthroughs. The empty state IS
> the teacher; the Copilot IS the guide; the ⌘K palette IS the map.
>
> Layered on Bible v2.1, D6 modes, D7 State Template, E1 Strategy
> Experience, E2 Auth Experience (including Trust Before Credentials).
>
> Prepared 2026-07-20. Third E-series deliverable per D8 §13.6.

---

## 0. Design Principles Checklist (19 items — permanent quality gate)

E3 confirms:

- [x] **Invisible Luxury** — no onboarding modals; the first frame post-auth is the working product, not a marketing preamble.
- [x] **Everything Connected** — first-time operators discover navigation through the shell chrome; every visible element leads somewhere.
- [x] **Progressive Disclosure** — Advanced Lens off by default for first-time Executive/Operations/Research; on for Developer per D6 §7.4.
- [x] **Evidence First** — first-time empty states cite the *specific* activation phase or feature flag that would populate them; no vague "no data" copy.
- [x] **Persona Awareness** — first-time experience differs by claimed mode; §4 authors per-mode moment-zero.
- [x] **Mission Control First** — Operations first-time landing is `/c/mission`; other modes per D6 §12.
- [x] **Accessibility (WCAG 2.2 AA)** — screen-reader announces the landing state; keyboard-first (⌘K discovery hint auto-focuses).
- [x] **Motion Discipline** — the landing crossfade is 400 ms Editorial; no additional first-time-only animations.
- [x] **Design Token Compliance** — first-time surfaces reuse the same tokens; no first-time-only styles.
- [x] **Six-Signal Rule** — first-time empty states use `--sig-dormant` / `--sig-ok` primarily; never `--sig-crit`.
- [x] **Lineage Validation** — every first-time empty state that mentions a domain concept (Approval, Timeline, Master Bot) links to that concept's canonical surface.
- [x] **Empty-State Quality** — this journey IS the empty-state journey; every specimen from D7 that renders on a fresh Factory shows.
- [x] **Consistency** — first-time uses identical primitives to daily operation; no first-time-only components.
- [x] **Explainability** — every first-time surface answers *"What am I looking at · why is it empty · what happens next"*.
- [x] **Storytelling Copy Standard (D2 Addendum)** — first-time copy is Division voice: *"The Factory is at rest until the next scheduled cycle."* not *"No data yet — click here to get started!"*.
- [x] **Context Never Lost (Bible §1.4.4)** — a first-time user has no prior context; the mode default becomes their starting context.
- [x] **State Memory (Bible §1.4.5)** — a first-time user has no State Memory to restore; every surface reads its slice on entry and finds it empty; that empty is the state.
- [x] **Purpose Before Status (D4 §5.1.1)** — every first-time surface leads with *why the surface exists*, not *what is missing*.
- [x] **Decision Identity (D6 §8.1a)** — a first-time user seeing the same object across modes sees byte-identical underlying truth; only rendering differs.
- [x] **Trust Before Credentials (E2 §9)** — the first-time user has already seen the pre-auth shell; post-auth builds on that trust rather than restarting from zero.

---

## 1. Purpose

Most products treat first-time-user onboarding as a *chore-you-must-
complete-before-you-can-use-the-product*: a wizard, a series of
overlays, a video tour, a checklist. Strategy Factory rejects this
entirely. **The product's own components are the pedagogy.**

**E3 codifies:**

1. **What a first-time operator sees on landing** — per mode.
2. **Why the empty states already teach.**
3. **The four discoverability affordances** — Copilot, ⌘K palette,
   empty-state actions, keyboard-shortcut HUD.
4. **The first meaningful action** — how each mode's operator arrives
   at their first *"I understand this product"* moment.
5. **How Advanced Lens introduces itself** — without a modal.

**Anti-goals:**

- Modal onboarding overlays.
- "Take a tour" buttons.
- Progress bars ("2 of 5 steps to get started").
- Feature-highlight tooltips ("Did you know you can pin any card?").
- Empty checklists to complete.
- Confetti or celebratory animations on first anything.
- Sample data seeded into the operator's workspace.
- Any modal that prevents accessing the shell before dismissal.

---

## 2. The moment-zero problem

**When an operator lands post-auth for the first time, three things
are true simultaneously:**

1. **The Factory may already be doing things.** If Master Bot is
   running a plan, an existing operator arriving anew sees that plan
   live.
2. **The operator has no personal history in this workspace.** No
   pinned items, no saved filters, no scroll positions, no drafts.
3. **The operator does not yet know the product.** Every affordance
   is unfamiliar.

**All three must be respected simultaneously.** The design must:
- Show the Factory *as it actually is right now* (never mock data).
- Not pretend the operator has history they don't have.
- Not teach through modals; teach through the working product.

---

## 3. The four first-time archetypes (by claimed mode)

Each mode's first-time operator is a different persona with a
different question in their head:

| Mode | First-time archetype | Their unstated question |
|---|---|---|
| **Executive** | Stakeholder previewing the platform | *"Is my Factory healthy?"* |
| **Operations** *(default)* | On-shift operator receiving handoff | *"What is happening right now?"* |
| **Research** | Analyst opening the lab | *"What has the Factory learned so far?"* |
| **Developer** | Engineer opening the machine | *"Is everything working?"* |

The first-time journey per mode answers exactly that unstated
question. Nothing more.

---

## 4. Per-mode moment-zero — what a first-time operator sees

### 4.1 First-time Executive · lands on `/c/briefing` (Sprint 3+) or `/c/mission` fallback

Sprint 1 fallback: Executive first-time lands on `/c/mission` with
Concept-C overlay treatment (D6 §4.3).

Sprint 3+ target: full `/c/briefing` surface (D6 §4.2).

**What renders on Sprint 1 fallback for a first-time Executive:**

```
┌────────────────────────────────────────────────────────────────────┐
│  Mission Control                                                   │
│                                                                    │
│    91.4 %                                                          │
│    AI Workforce nominal · 4 workers online                         │
│                                                                    │
│    You are viewing Mission Control in Executive mode.              │
│    The full daily briefing surface arrives in Sprint 3.            │
│                                                                    │
│    → view Approval Center  ·  → open Timeline                      │
│                                                                    │
│    ─── Kill posture ─────────────────────────────                  │
│    ● armed · deliberate freeze                                     │
│                                                                    │
│    ─── System posture ───────────────────────────                  │
│    6 of 6 subsystems nominal                                       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

The Executive's unstated question (*"Is my Factory healthy?"*) is
answered in the first frame: **workforce %, posture, kill posture,
subsystems**. No further exploration required for the base answer.

**The "why the surface is empty of activity"** — if the Factory is
in kill posture (freeze), the Executive sees that immediately. Not an
error; not a scary red screen; a calm dormant chip explaining the
deliberate freeze.

### 4.2 First-time Operations · lands on `/c/mission`

Mission Control renders per Bible §8.1 with authored empty states
where the Factory has no data yet:

- **Attention panel** (Q6): renders `mc-empty-nothing-pending` (D7 §8.1)
  or the real attention item if kill-posture-related.
- **Approvals panel**: renders `ap-empty-caught-up` (D7 §10.1) — *"You're
  all caught up. The Factory is operating autonomously."*
- **Pipeline column**: renders `strat-empty-none-in-portfolio-candidates`
  (E1 §7.2) — *"No strategies are in the Portfolio candidate pool."*
- **Master Bot chip in header**: shows `MASTER BOT · @v55 · idle` (or
  the real state).
- **G8 Neural Pulse strip** at footer: real live sparklines (or
  dormant patterns if subsystems are gated).
- **Right rail Timeline**: renders `tl-empty-idle-factory` (D7 §9.1)
  — *"The Factory has been idle for 12 min. This is normal during
  freeze."*

**The Operations operator's unstated question** (*"What is happening
right now?"*) is answered by the aggregate of these panels reading
their true current state. If the Factory is truly idle, the panels say
so calmly and coherently.

### 4.3 First-time Research · lands on `/c/research` (Sprint 3+) or `/c/mission` fallback

Sprint 1 fallback: `/c/mission` with Research-mode treatment
(D6 §6.3).

Sprint 3+ target: full Research Workspace (D6 §6.2).

**What renders on Sprint 1 fallback for a first-time Research operator:**

Mission Control with:
- LeftRail with Research pinned at top.
- Right rail Timeline filtered by default to Research + Knowledge + Learning
  actors.
- If the Factory has generated any strategies: they appear in the
  Timeline as `Research Division generated candidate #<id>` rows.
- If no strategies exist yet: `res-empty-no-strategies` (D7 §12.1) —
  *"No strategies have been generated yet. Start your first research
  cycle."*
- Copilot companion panel *is* docked (Research posture default).

**The Research operator's unstated question** (*"What has the Factory
learned so far?"*) is answered by the Timeline + Copilot's opening
message.

### 4.4 First-time Developer · lands on ⌘K palette pre-opened

Per D6 §7.2, Developer mode's first-time landing is the ⌘K palette
open to the `developer` group.

**What a first-time Developer sees:**

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
│  NAVIGATE                             │
│    ▸ mission control                  │
│    ▸ approvals                        │
│    ▸ factory                          │
│    ▸ strategies                       │
└──────────────────────────────────────┘
```

If the developer dismisses the palette (Esc), they land on Mission
Control with Advanced Lens on and status rail extended showing
per-subsystem p95 latency chips.

**The Developer's unstated question** (*"Is everything working?"*) is
answered by two chips visible immediately: subsystems status rail and
audit-log recency.

---

## 5. Onboarding-without-wizards — the four mechanisms

The product teaches itself through **four discoverability affordances**,
all of which exist in the product post-onboarding too. First-time is
simply the *first time these affordances fire*.

### 5.1 Empty states as the primary teacher (D7)

Every empty state that renders on a fresh Factory carries:

- A **headline** in Division voice explaining what the surface exists
  for (Purpose Before Status).
- A **purpose caption** answering *"Why is this empty?"*
- A **primary action** to move toward populating the surface.

Example — a first-time operator on `/c/approvals` sees:
```
[ icon · check ]

You're all caught up.
The Factory is operating autonomously.

→ view recent approvals   ·   open timeline
```

This tells the operator: *the surface exists to hold approvals; there
are none right now; the Factory doesn't need me to do anything; here's
how to look at what has happened*. All in 4 rendered lines.

**This is the primary onboarding mechanism** — no separate content
required.

### 5.2 Copilot as guide (Bible §24)

Copilot is present in every mode from first login. On first Copilot
open, Copilot greets with a **mode-specific factual statement about
the Factory** — not a question, not a menu, not a greeting.

Per mode, Copilot's first-open greeting:

- **Executive:** *"The Factory has 4 workers online, 2 subsystems in
  dormant activation phases, and 3 approvals in the last 24 hours.
  Kill posture is armed."*
- **Operations:** *"Master Bot is idle. 6 of 6 subsystems nominal.
  Last activity was the kill posture arm event 2 h ago."*
- **Research:** *"Research Division has generated 0 candidate
  strategies. Knowledge Base is dormant until Phase C activation."*
- **Developer:** *"0 errors in the last hour. All 6 subsystems
  reporting nominal. Audit log last written 2 h ago."*

**Copilot never introduces itself.** No *"Hi, I'm Copilot!"* — Division
voice, factual, immediate.

**Copilot's answer to *"How do I use this?"*** is not scripted; it's
answered from the D-series design library (via Copilot's grounded
retrieval). Copilot Never Invents — if it can't answer, it says so
(D7 §17.6 specimen).

### 5.3 ⌘K palette as the map

The ⌘K palette is the *sitemap* of the product. First-time operators
discover ⌘K via a **subtle persistent hint** in the header until
first-successful-⌘K-use:

```
Header shows:  [ ⌘K  →  find anything ]
                (--content-lo, --font-caption, right side)
```

- On first ⌘K press: hint dismisses; **State Memory** records that
  this operator has discovered ⌘K; hint never returns.
- The palette itself is unmodified — same as the ordinary palette.
  No first-time-only content.

**Hint dismissal is silent.** No confetti. The operator's second look
at the header simply notices it's gone; that's the acknowledgement.

### 5.4 Signature Frame legend as first-touch legend

The first time an operator hovers any signature graphic (G1–G8) in
their session, a **subtle legend expansion** briefly appears
identifying the graphic's encoding. After the first hover, hovers
render the standard legend strip (D5 §2.1 element #5) inline.

**Rule:** the first-hover expansion is a **soft** 200 ms fade-in of
the legend at slightly larger size; auto-fades to normal after 2 s.
Never a tooltip modal. Never a "Learn more" link. Just a moment of
recognition.

---

## 6. The first meaningful action (per persona)

Every first-time operator, per mode, has an **implicit first meaningful
action** — the moment they realise they understand the product.

### 6.1 Executive · first meaningful action

**Reading the workforce percentage on the header, then opening
Approval Center to see there are 0 pending.** This is when they
understand: *the Factory runs itself; I judge only exceptions.*

**Design supports this by:**
- Making the header workforce chip visible from first frame.
- Making the approvals chip visible with 0 count.
- Approval Center empty state explicitly stating *"The Factory is
  operating autonomously."*

### 6.2 Operations · first meaningful action

**Watching a Timeline event stream in from the right rail (if the
Factory is active) or reading `tl-empty-idle-factory` (if it's not).**
This is when they understand: *the Timeline is the narrative spine;
everything else is a lens over it.*

**Design supports this by:**
- Right rail Timeline visible from first frame.
- Real events streaming in with `⟶ new` badges (D2 §5) if any occur.
- Idle-state copy that reads calmly instead of alarmingly.

### 6.3 Research · first meaningful action

**Asking Copilot a question about the Knowledge Base and receiving a
grounded answer with citations.** This is when they understand: *this
is a lab; the Copilot is a research assistant; the Timeline records
my thread.*

**Design supports this by:**
- Copilot companion panel docked by default (D6 §6.5).
- Copilot's first response citing at least one Timeline event or KB
  item.
- Trace-as-UI available under Advanced Lens (P24) to satisfy the
  analyst's *"how did you know that?"* curiosity.

### 6.4 Developer · first meaningful action

**Opening the audit log or errors-last-100 view from the palette,
seeing zero errors, then closing the palette.** This is when they
understand: *I have direct L4/L5 access from ⌘K; the product is a
diagnostic tool for me, not just a UI.*

**Design supports this by:**
- Palette opens to developer group on first-arrival.
- Sub-items visible at rest.
- Every developer action returns to the operator's active surface, not
  a wall-of-diagnostics page.

---

## 7. Advanced Lens self-introduction

Advanced Lens (Bible §11) is not introduced through a modal or a
first-time toast. Its discovery is *earned* through the presence of
Advanced-Lens-eligible chips on cards.

**First-time cue:** every card with Advanced-Lens extensions carries a
subtle `⋯ +N more` chip in the top-right corner when Advanced Lens is
off. Hovering that chip reveals a tooltip: *"Turn on Advanced Lens
(⌘⇧A) to reveal method chips."*

- The tooltip renders **once per surface per session**.
- After first-⌘⇧A-use, the tooltip never renders again for this
  operator on any surface.
- If the operator dismisses without using ⌘⇧A, the `⋯ +N more` chip
  remains visible but the tooltip stops appearing after 3 hover events.

**Rule:** the chip is the discoverability; the tooltip is the
first-time hint; ⌘⇧A is the persistent affordance.

---

## 8. State Memory & CNL on first visit

### 8.1 State Memory (Bible §1.4.5) on moment-zero

**A first-time operator has no State Memory to restore.** Every
surface's `useSurfaceState()` (D8 §3.2) reads its slice and finds it
empty. That is the state:

- Scroll positions default to top.
- Panels default to expanded.
- Tabs default to their surface's first tab.
- Drawers default to closed.

**No first-time-only defaults exist.** The default state is the same
default that applies whenever a surface has no memory.

### 8.2 CNL (Bible §1.4.4) on moment-zero

**A first-time operator has default CNL fields:**

- Mode: from user record's `default_mode` (or `operations`).
- Advanced Lens: off (except Developer, on-locked).
- Density: mode-default (compact for Operations, cozy for Research,
  etc.).
- Filters: no operator override → mode defaults apply (D6 §9).
- Time-window: mode default (D6 §10).
- Selected artefact: none.
- Pinned Preview tray: empty.

**All defaults are the *same* defaults returning operators experience
if their sessionStorage has cleared.** First-time is not a special
case; it's simply the case where localStorage is fresh.

### 8.3 The first-time operator "graduates" invisibly

There is **no marker** of an operator ceasing to be first-time. State
Memory accumulates naturally; ⌘K hint dismisses after first use;
Advanced Lens tooltip suppresses after first ⌘⇧A. Each affordance
graduates independently and silently.

**Rule of Silent Graduation.** The operator should never notice they
"completed onboarding". They should notice, over the first few
sessions, that the product is quieter and more familiar. That's the
metric.

---

## 9. First-time-specific empty state additions (extend D7)

E3 introduces **five first-time-specific specimens** that extend D7:

### 9.1 `ft-empty-first-visit-approvals`

*When:* first-time operator lands on `/c/approvals` and has never
seen an approval before, and the Factory has 0 pending.

```
Icon        check
Headline    You're all caught up.
Purpose     The Factory is operating autonomously.
            Approvals appear here when Master Bot or Learning Division
            recommends a promotion or retirement.
Actions     view recent approvals · open Timeline
```

Note: purpose caption is **longer** for first-time — 2 sentences
instead of 1. Once the operator has seen at least 1 approval in their
session, the specimen collapses to the standard `ap-empty-caught-up`
(D7 §10.1). This is the *only* first-time-specific specimen
difference — the elongated purpose sentence.

### 9.2 `ft-empty-first-visit-mission-idle`

*When:* first-time operator lands on `/c/mission` and Factory is
idle.

```
Icon        moon
Headline    The Factory is at rest.
Purpose     All 8 divisions healthy · no work in progress.
            Mission Control shows live activity as the Factory runs.
Actions     view scheduler · view last plan · open ⌘K
```

### 9.3 `ft-empty-first-visit-timeline`

*When:* first-time operator sees the Timeline for the first time in
a session, and no events have streamed in.

```
Icon        moon
Headline    The Timeline is quiet.
Purpose     Every activity across the 8 divisions appears here as it
            happens. Filter with ⌘/ or clear filters to see everything.
Actions     open scheduler · see last cycle
```

### 9.4 `ft-hint-cmdk`

*When:* first-time operator's session has not yet used ⌘K.

Rendered in the header (right side, `--font-caption` UPPERCASE,
`--content-lo`):

```
⌘K  →  find anything
```

Non-modal. Non-interactive-as-tooltip. Once ⌘K is used, this hint
vanishes silently.

### 9.5 `ft-hint-advanced-lens`

*When:* first-time operator hovers a card with Advanced-Lens
extensions, `⌘⇧A` has never been used.

Rendered as an inline tooltip on the `⋯ +N more` chip (§7):

```
Turn on Advanced Lens (⌘⇧A) to reveal method chips.
```

Auto-dismisses after 3 s. Renders once per surface per session, or
until ⌘⇧A is used.

---

## 10. Copy library

Locked at E3 approval. Applied through the specimens in §9.

### 10.1 Copilot first-open greetings (§5.2)

- Executive: *"The Factory has <n> workers online, <n> subsystems in
  dormant activation phases, and <n> approvals in the last 24 hours.
  Kill posture is <state>."*
- Operations: *"Master Bot is <state>. <n> of 6 subsystems nominal.
  Last activity was <event> at <time>."*
- Research: *"Research Division has generated <n> candidate
  strategies. Knowledge Base is <state>."*
- Developer: *"<n> errors in the last hour. <n> of 6 subsystems
  reporting nominal. Audit log last written <at>."*

### 10.2 First-time Timeline events (Advanced-Lens only)

Timeline records first-time markers *only for Advanced-Lens
observers*. Layer 1 timeline stays clean:

- *"Operator signed in for the first time."*
- *"Operator discovered ⌘K palette."*
- *"Operator turned on Advanced Lens for the first time."*
- *"Operator opened Copilot for the first time."*

These do not appear at Layer 1 (Bible §3). They exist for governance
audit trail only.

---

## 11. Failure paths — the first-time-specific failures

| Path | Trigger | Handling |
|---|---|---|
| FT1 factory-not-yet-configured | First-time user; Factory has never activated any phase | Landing shows dormant-state Mission Control per D7 dormant specimens; no error |
| FT2 kill-posture-armed-on-arrival | Factory is in kill posture | Danger ribbon fires in the landing crossfade (E2 §9); no first-time-specific handling |
| FT3 mode-assignment-empty | User record has 0 modes assigned (misconfig) | Fall back to operations; alert admin via governance-log (Sprint 3+); Sprint 1: operations is the safe default |
| FT4 Copilot-unavailable-on-first-visit | Emergent LLM key not configured | Copilot ambient anchor shows `copilot-error-unavailable` (D7 §17.5); no first-time-specific handling |
| FT5 no-strategies-no-timeline-no-approvals | Absolutely fresh Factory | Every panel shows its authored dormant state; no error; the calm empty is the state |

**Rule:** none of these paths is treated as a *first-time-specific
error*. They are the product's normal state; first-time simply happens
to intersect them.

---

## 12. Accessibility on moment-zero

- On landing, focus lands on the primary content region (`main`) with
  `tabindex="-1"` and `aria-labelledby="<surface-title>"`.
- Screen-reader announcement on landing:
  *"Mission Control · Operations mode · no approvals require your
  attention."*
- The ⌘K hint has `aria-hidden="false"` and is announced as a
  region: *"Keyboard shortcut hint: press command K to find anything."*
- The Advanced Lens `⋯ +N more` chip has `aria-label="More detail
  available via Advanced Lens (Command Shift A)"`.
- All first-time specimens (§9) respect the D7 State Template
  a11y contract.

---

## 13. Data contract (frontend-only · Feature Freeze respected)

E3 requires **no new backend endpoints and no new state fields**.

**First-time detection:** an operator is first-time when their
`localStorage.strategyFactory.hasVisited === undefined`. On first
successful auth landing, set `hasVisited = <ISO timestamp>`. This
flag is:

- localStorage-based (survives across sessions).
- Not synchronised across devices (each device is independently
  first-time).
- Never sent to backend.
- Cleared on logout only if the operator explicitly *"forgets device"*
  (Sprint 3+ feature; not in Sprint 1).

**Hint dismissal keys** in localStorage:

- `strategyFactory.hint.cmdkUsed: boolean`
- `strategyFactory.hint.advancedLensUsed: boolean`
- `strategyFactory.hint.copilotOpened: boolean`
- `strategyFactory.hint.signatureFrameHovered: boolean` (per graphic:
  `strategyFactory.hint.signatureFrameHovered.G3: boolean`, etc.)

Each is set silently on first use of the corresponding affordance.

**Total localStorage footprint added by first-time:** ~200 bytes
per operator per device.

---

## 14. Sprint 1 acceptance criteria

First-Time Journey ships only if:

- ✅ 19-item Design Principles Checklist confirmed (§0)
- ✅ Post-auth landing per D6 §12 (mode-specific)
- ✅ First-time detection via `hasVisited` localStorage flag (§13)
- ✅ ⌘K hint renders on first-time session; dismisses on first ⌘K use (§5.3)
- ✅ Advanced-Lens tooltip renders on eligible chip hover; dismisses on first ⌘⇧A use (§7)
- ✅ Signature-Frame first-hover expansion renders once per graphic per session (§5.4)
- ✅ First-time empty states from §9 render on eligible surfaces
- ✅ Copilot first-open greeting matches mode-specific specimen (§5.2)
- ✅ No wizards / modals / progress bars / "Take a tour" affordances
- ✅ No confetti / celebratory animation on any first-time action
- ✅ No sample data seeded into workspace
- ✅ Silent Graduation verified — hint dismissals happen without user acknowledgement
- ✅ Screen-reader announcement on landing verified (§12)
- ✅ CNL + State Memory defaults applied per §8
- ✅ Kill-posture behaviour on first-time visit tested (§11 FT2)
- ✅ Decision Identity — first-time user seeing an object across modes sees byte-identical truth
- ✅ Trust Before Credentials (E2 §9) coherence — first-time landing feels like continuation of pre-auth trust
- ✅ `data-testid` on every first-time-specific element (hints, tooltips)

---

## 15. What E3 does NOT include

- Product tour / walkthrough.
- Video overlay.
- "Getting started" checklist page.
- Progress bar on onboarding.
- Trigger-based tooltips beyond the two authored ones (⌘K, ⌘⇧A).
- Confirmation modals on first any-action.
- Sample / seeded fake data in the operator's workspace.
- Any first-time-specific icon set.
- A "First-time user" mode chip.
- Onboarding email flows (out of scope; adjacent admin workflow).

---

## 16. Next: E4 — Daily Operator Journey

Per D8 §13.6 (operator-directed sequencing).

E4 will codify the *routine on-shift experience* — the flow of a
daily operator across a normal shift:

- Morning login → glance at Mission Control.
- Triage attention items.
- Approve / defer / deny recommendations.
- Investigate one strategy in depth.
- Handoff to next shift.
- End-of-shift review.

The choreography of a shift, mapped against the six operator questions
and the primary surfaces.

Expected timeline: 2 days.

---

*End of E3 — First-Time User Journey.*

*All 19 checklist items confirmed. First-time onboarding codified as
the natural state of the working product, taught by empty states,
guided by Copilot, mapped by ⌘K, discovered through Advanced-Lens
chips. No wizards. No modals. Silent Graduation. Bible v2.1 · D6 · D7
· E1 · E2 · Backend Feature Freeze all respected.*

*Awaiting operator review before authoring E4.*

# E4 — Daily Operator Journey

> The choreography of a routine on-shift day. How an operator arrives,
> orients, triages, judges, investigates, hands off. Not a script —
> a rhythm. The design supports both burst-triage-and-return and
> long-focus-investigate patterns, seamlessly.
>
> Layered on Bible v2.1, D2 Timeline, D3 Approvals, D4 Master Bot, D6
> modes, D7 states, E1 Strategy Experience (Passport), E2 Auth, E3
> First-Time (Silent Graduation + Progressive Confidence).
>
> Prepared 2026-07-20. Fourth E-series deliverable per D8 §13.6.

---

## 0. Design Principles Checklist (20 items — permanent quality gate)

E4 confirms:

- [x] **Invisible Luxury** — the routine shift feels effortless because every micro-transition is polished, not because features are added.
- [x] **Everything Connected** — a day's investigation follows lineage across surfaces without navigating away from context.
- [x] **Progressive Disclosure** — the operator moves between Simple and Advanced Lens throughout the day as investigation depth changes.
- [x] **Evidence First** — every triage decision cites the evidence backing the recommendation.
- [x] **Persona Awareness** — Operations is E4's centre of gravity; other modes' daily flows codified in §11.
- [x] **Mission Control First** — the routine shift returns to Mission Control after every deep-dive; it is the operator's home base.
- [x] **Accessibility (WCAG 2.2 AA)** — every hourly interaction is keyboard-reachable; screen-reader announcements do not accumulate to disruptive noise.
- [x] **Motion Discipline** — ambient motion budget respects a full 8-hour shift without visual fatigue.
- [x] **Design Token Compliance** — the shift uses only Bible v2.1 tokens.
- [x] **Six-Signal Rule** — signal chips appear at the same tone all day; late-shift red does not mean something different from morning red.
- [x] **Lineage Validation** — every investigation surfaces lineage; Rule of Return means the operator can always find their way back.
- [x] **Empty-State Quality** — during quiet periods, the empty states carry the operator through calm without alarm.
- [x] **Consistency** — the same primitives serve the morning glance and the end-of-shift review.
- [x] **Explainability** — every operator action has a clear reason surfaced *before* the action is committed.
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice sustains all day.
- [x] **Context Never Lost (Bible §1.4.4)** — mid-shift mode-switch, deep-dive, or interruption preserves the operator's investigation state.
- [x] **State Memory (Bible §1.4.5)** — returning to a surface after 3 h away restores the operator's exact vantage point.
- [x] **Purpose Before Status (D4 §5.1.1)** — every worker card, approval, and strategy card the operator interacts with leads with purpose.
- [x] **Decision Identity (D6 §8.1a)** — every artefact preserves its truth across mode-switches within the same shift.
- [x] **Trust Before Credentials (E2 §9)** — post-shift return to the login screen preserves the trust established over the shift.
- [x] **Progressive Confidence (E3 §8.4)** — meaningful daily milestones surface in the same voice as ordinary events; the shift is not gamified.

---

## 1. Purpose

Strategy Factory operates continuously; operators do not.
Operators arrive to a Factory that has been running (or resting)
without them and leave one that continues (or continues to rest) after
them. **E4 codifies how a shift feels** — from morning arrival through
end-of-shift review, and every micro-transition in between.

**E4 codifies:**

1. **The four movements of a shift** — arrival, triage, deep-dive,
   handover.
2. **The rhythm** — how burst and focus alternate.
3. **Where the operator returns to between actions** — Mission Control
   as home base.
4. **How the design sustains an 8-hour session** — motion budget,
   attention discipline, notification cadence.
5. **How handover to the next shift is designed** without an explicit
   handoff surface — because Timeline is the handoff.

**Anti-goals:**

- A "task list" or "daily agenda" surface.
- Reminders / notifications for routine actions.
- A "productivity dashboard" for the operator's own performance.
- Any suggestion that the operator has quotas or KPIs.
- End-of-shift checklists.
- "Time-tracking" of any kind.

---

## 2. The four movements of a shift

A routine shift has **four movements**. They are not sequential; they
interleave throughout the day. The design must support all four
simultaneously.

| Movement | What it is | Duration in a typical shift |
|---|---|---|
| **Arrival** | Login, glance, orient | ~5 min |
| **Triage** | Scan Attention · Approvals · Timeline; act on exceptions | 3–6 bursts, 5–15 min each |
| **Deep-dive** | Investigate a specific strategy / worker / knowledge item | 15–60 min per session, 1–3 per shift |
| **Handover** | Wrap current thread; leave Timeline legible for next operator | ~10 min at end |

A shift may have 30 triage bursts and 0 deep-dives (busy day) or 1
deep-dive and 3 triage bursts (research day). The rhythm is
operator-led.

---

## 3. Movement 1 · Arrival (morning · post-auth)

### 3.1 The first 60 seconds

Post-auth, the operator lands on Mission Control (Operations mode).
The first 60 seconds are the *orient* moment. Design supports it by
making three answers immediately visible without any interaction:

1. **What is the Factory's posture?** — StatusRail (6 chips) at footer.
2. **What needs my attention?** — Attention panel (Q6) at Mission
   Control.
3. **What has happened since I was last here?** — Timeline right rail,
   showing events since the operator's last recorded session.

**No action required in the first 60 s.** The operator reads; the
product tells.

### 3.2 The "since you were away" recap

Timeline right rail on arrival scrolls to the last event **at or
before** the operator's previous logout timestamp — showing an
implicit *"here's where you left"* marker without ceremony.

A subtle divider renders in Timeline:

```
[actor]  event
[actor]  event
    ─── ── you signed out here · 22:41 yesterday ── ─
[actor]  event
[actor]  event
[actor]  event  ← latest
```

Divider colour `--content-lo`; caption `--font-caption`. Fades on any
scroll or user interaction. **No modal.** No summary card.

Under Advanced Lens, the divider shows a small `→ narrate the delta`
chip that opens Copilot with a request: *"Summarise what happened
between 22:41 yesterday and now."*

### 3.3 Kill posture on arrival

If kill posture is armed, danger ribbon fires in the landing crossfade
(E2 §9.4). The operator's first frame carries the ribbon — trust is
built by never surprising them.

### 3.4 The morning does NOT include

- A "Good morning, admin!" greeting.
- A summary modal.
- A "Yesterday you approved N recommendations" callout.
- Any progress bar suggesting overnight work.
- Motion effects beyond the standard landing 400 ms crossfade.

---

## 4. Movement 2 · Triage (throughout shift)

Triage is the operator's *primary rhythm*. A burst begins when a
Timeline event, Attention item, or approvals-chip increment catches
the operator's eye.

### 4.1 A triage burst · anatomy

```
1. Timeline event arrives                (200 ms slide-in from top of right rail)
   OR Attention panel updates            (400 ms editorial re-order)
   OR approvals chip increments          (120 ms count flash)

2. Operator glances at Attention/Approvals column.

3. Operator opens the item — three paths (Everywhere-Actionable, E1 §5.7):
   a. Click Approval Card in Approval Center
   b. Expand Timeline row inline (D3 §1.4)
   c. Click approvals-chip drawer

4. Operator reads recommendation + evidence.

5. Operator commits action — 4 canonical verbs (D3 §6):
   [ Approve ]   [ Defer ]   [ Deny with reason ]   [ Route ]

6. Optimistic UI removes card (§6.3); Timeline records the decision
   in Division voice; approvals chip decrements; Mission Control
   Attention panel re-orders per severity (§8.8).

7. Operator returns to Mission Control (or stays in Approval Center
   if more items are pending).
```

**A single triage burst is typically 30 s to 3 min.**

### 4.2 The Attention panel severity discipline

Attention items are ordered by severity, not by recency (Bible §8.8).
An operator scanning down the panel encounters Critical first, then
Warn, then Advisory. Within a severity, the *oldest* unresolved item
appears first — because oldest-unresolved is most important.

**This discipline is what makes triage feel calm.** The operator
never has to hunt; the top of the panel is always the item that
matters most.

### 4.3 Optimistic-UI in triage

Every triage action commits optimistically (Bible §6.3):

- Approve → card slides out; spinner on side (never on card); confirms
  within 300 ms.
- Defer → card sinks to bottom of queue with `deferred until <t>` chip.
- Deny → drawer opens for reason capture; on submit, card slides out.
- Route → drawer opens for reviewer selection (Sprint 3+).

**Rollback discipline (D3 §5.3):** if the backend fails, the card
returns to its original position with an inline error toast (D7
`ap-error-action-failed`). Never a spinner-of-shame; never a card
frozen in "processing" state.

### 4.4 The bulk-approve safety pattern (D3 §5.2)

If the queue has ≥ 3 low-risk approvals from the same source, the
operator sees a discreet *"Approve all N ▾"* chip above the queue.
Click reveals a confirmation drawer listing the items. This is the
only place Strategy Factory has a bulk action, deliberately gated by
an explicit review-list confirmation.

**Safety-tagged approvals never appear in bulk-approve.** They must be
handled individually.

### 4.5 Triage during focus

Sometimes an operator is mid-deep-dive when a triage item arrives.
Design behaviour:

- **Approvals-chip in header updates silently** — count increments;
  no toast, no sound.
- **Timeline right rail** streams the event; if the operator is
  focused on a Passport / Timeline scroll, the new event appears at
  the top with the `⟶ new` badge (D2 §5).
- **Danger ribbon fires only for Critical** — never for routine
  approvals.

**Rule of Interrupt Frugality.** The Factory interrupts the operator
only when the item's severity crosses the *Critical* threshold. All
other events accumulate silently; the operator returns to them at
their next natural break.

---

## 5. Movement 3 · Deep-dive (per shift, 1–3 times)

Deep-dives are the operator's *slow work*. An investigation of one
strategy, one worker, one knowledge item — pursued for 15–60 minutes.

### 5.1 A deep-dive · anatomy

```
1. Operator sees an artefact worth investigating:
   · a strategy Timeline row
   · a worker with a state anomaly
   · a knowledge item with new contradictions

2. Click → opens the artefact's canonical detail page:
   · Strategy → Strategy Passport (E1 §6.7)
   · Worker → future Worker Passport (Sprint N+)
   · Knowledge item → Knowledge Detail (Sprint 3+ with G3)

3. Operator explores the 11 sections of the Passport (E1 §6.7.1).

4. Operator may:
   · Pin the artefact (Bible §7.12)
   · Compare with peer via Pinned Preview (Sprint 2+)
   · Open Lineage Graph (Bible §10.2) (Sprint 2+)
   · Filter Timeline right rail to this artefact (?strategy=<id>)
   · Ask Copilot about the artefact

5. Operator may switch modes mid-deep-dive:
   · Executive → for a briefing view of the Passport
   · Research → for a deeper knowledge angle
   · Developer → for provenance triple + worker attribution
   Decision Identity holds; the artefact's truth remains byte-identical.

6. Operator returns to Mission Control:
   · via ⌘M
   · via LeftRail Mission Control click
   · via Esc key (closes any open drawers first)
   State Memory preserves the deep-dive vantage point for later return.
```

**A deep-dive can last hours.** The design must not fatigue.

### 5.2 The "return to home base" mechanism

At any moment during a deep-dive, `Esc` behaves as:

1. First press: closes any open drawer (Evidence Drawer, Approval
   drawer, filter drawer).
2. Second press: closes any open Lineage Graph or full-viewport
   overlay.
3. Third press: returns to Mission Control while preserving all
   deep-dive State Memory.

**Rule of Reversibility (Bible §1.4.4):** three Esc keystrokes always
return home; State Memory ensures the deep-dive is exactly where the
operator left it if they return.

### 5.3 Copilot as the deep-dive companion

During deep-dives, Copilot's presence increases utility:

- In **Operations mode**, ambient anchor at top-right; the operator
  opens it on demand.
- In **Research mode**, Copilot companion panel is docked by default
  (D6 §6.5) — always visible without interfering.

Copilot's answers cite Timeline events + Passport sections; it never
invents; trace-as-UI available under Advanced Lens for the operator to
audit reasoning (Bible §24).

### 5.4 Handoff between deep-dive and triage

The most important design moment in a shift: an operator mid-deep-dive
gets pulled into a triage burst.

**Design behaviour:**

- Operator sees the approvals-chip increment; decides to triage.
- Operator opens Approval Center (⌘A or clicks chip).
- **The deep-dive surface stays in State Memory** — same URL, same
  scroll, same drawers, same pins.
- Operator triages the approval.
- Operator returns to the deep-dive surface via ⌘[ (back) or
  navigating back through URL.
- **Everything is exactly where it was.** Investigation resumes.

**Rule of Continuity Across Triage.** A triage burst *interrupts* a
deep-dive without *breaking* it. State Memory + CNL are what make this
feel effortless.

---

## 6. Movement 4 · Handover (end-of-shift)

Strategy Factory does not have an explicit handoff surface — because
**Timeline is the handoff**. Every action the operator has taken today
is legibly recorded in Division voice on the Timeline. The next shift
inherits the Timeline; therefore they inherit the operator's day.

### 6.1 The end-of-shift ritual (invented by the operator; supported by design)

Design does not prescribe an end-of-shift ritual. Different operators
develop different habits. Design must support the most common ones:

1. **The scrub-back.** Operator sets Timeline time-window chip to
   `last 24 h`, scrolls up from bottom; confirms all their actions are
   recorded, all approvals are resolved.

2. **The pin-cleanup.** Operator reviews Pinned Preview tray; unpins
   items they no longer need to compare (Sprint 2+).

3. **The last glance at Mission Control.** Return to `/c/mission` via
   ⌘M; verify Attention panel + Approvals panel + Master Bot posture.

4. **Logout.** `⌘L` — session closes; clean-desk behaviour (E2 §7.2)
   clears the sessionStorage.

### 6.2 What the design provides for handover

Because Timeline is the handoff, the design provides:

- **Persistent Division-voice narrative** of every action (D2 §5).
- **Actor filters** on Timeline — the next operator can filter to
  `[actor: approval]` to see all decisions.
- **Time-window chip** — the next operator can jump to "last 8 h" to
  see the exiting operator's shift.
- **Copilot narrative summary on request** — *"Summarise what
  happened during the last shift."* — Copilot cites Timeline events
  from the last 8 h.

### 6.3 What the design does NOT provide

- No "end shift" button.
- No hand-off form the operator must fill.
- No mandatory review checklist.
- No "leaving-notes-for-next-shift" surface.
- No shift-summary email (out of scope).

**Rule of Timeline as Handoff.** If the outgoing operator's decisions
are not legibly on the Timeline in Division voice, the Storytelling
Standard has failed — not the handoff.

---

## 7. Rhythm & interleaving

A shift interleaves the four movements freely:

```
09:00  ARRIVAL          (5 min)
09:05  TRIAGE burst 1   (2 min — 3 approvals, all low-risk, bulk-approved)
09:07  MISSION CONTROL glance
09:15  TRIAGE burst 2   (4 min — 1 medium-risk approval, individually reviewed)
09:19  MISSION CONTROL glance
09:22  DEEP-DIVE 1      (35 min — investigating a strategy anomaly reported by Learning)
09:57  TRIAGE interrupt (3 min — critical severity approval; danger ribbon fires)
10:00  Return to DEEP-DIVE 1 (State Memory restores exact vantage point) (18 min)
10:18  MISSION CONTROL glance
...
16:45  DEEP-DIVE 2      (22 min — reading a Copilot-summarised research thread)
17:07  TRIAGE burst 12  (4 min)
17:11  END-OF-SHIFT     (scrub-back · pin-cleanup · last glance)
17:15  LOGOUT           (⌘L)
```

The rhythm is the operator's. The design supports **fluid alternation**
between triage bursts and deep-dives without state loss, without
context switch friction.

---

## 8. Design support for an 8-hour session

Some design choices are quiet but load-bearing for the routine
long-shift experience:

### 8.1 Motion budget for the whole day

Bible §6.1 motion tiers are not just per-interaction; they aggregate
across a shift. Rules:

- **Ambient pulse** (2 s, 6 % scale) — only on running workers. If the
  Factory has 8 running workers all day, the operator's peripheral
  vision has 8 pulses ambient throughout. This is intentional; it
  reads as *aliveness*, not as *strobing*. Verified via 8-hour
  perception test.
- **G8 Neural Pulse strip** — continuous 1200 ms line-draw sweep. Same
  rule: it reads as *heartbeat*, not as *distraction*.
- **`prefers-reduced-motion`** — all ambient motion collapses to
  opacity fades. Operators with reduced-motion set have a completely
  still shift.

### 8.2 Attention discipline

- **Interrupt frugality** (§4.5) — only Critical severity fires the
  danger ribbon. Everything else accumulates silently.
- **Toast frugality** — max 1 toast on-screen at a time. Second toast
  dismisses the first with a 200 ms fade.
- **Sound** — never.
- **Notification permission requests** — never (not a browser-native
  notification product for Sprint 1).

### 8.3 Colour discipline sustains eyestrain floor

- Six-signal ceiling (Bible §5.1) — no colour drift over the day.
- Cool-shifted `--surface-0` dark background — verified for 8-hour
  contrast comfort.
- **Advanced Lens toggle** — some operators run Advanced all day;
  design must remain legible with all chips visible.

### 8.4 Keyboard shortcuts for repetition

The operator repeats ~30 approvals per shift. Design ensures these
never require mouse:

- `⌘A` → Approval Center
- `↑ / ↓` → navigate cards
- `A` → Approve highlighted
- `D` → Deny with reason (opens drawer)
- `F` → Defer (snooze)
- `R` → Route (Sprint 3+)
- `Esc` → close any drawer
- `⌘/` → toggle Timeline expand
- `⌘M` → mode switcher (rare mid-shift)
- `⌘K` → palette

Under Advanced Lens, `?` shows the full keyboard HUD (Bible §7.10).

---

## 9. Copilot on shift

Copilot's role during a shift is that of a **silent expert on the
Factory** — available on demand, never intrusive.

### 9.1 Copilot triggering patterns during a shift

- **On demand** — operator asks a question.
- **On investigation** — operator opens a Passport; Copilot's ambient
  anchor shows a subtle "ask about this strategy" hint that fades if
  ignored.
- **Never proactive** — Copilot never fires a message the operator did
  not request. It observes; it does not narrate unless asked.

### 9.2 Copilot workload discipline

An operator asking Copilot 50 times per shift should not accrue any
UX regression:

- **Every answer cites at least one event / artefact.**
- **Trace-as-UI (P24)** available under Advanced Lens for the
  operator to audit reasoning.
- **Never invents.** If Copilot has no grounded evidence, it says so
  (D7 §17.6).
- **Response time** ≤ 8 s target; if exceeding, narrative loading
  applies (D7 §20).

### 9.3 Copilot memory across a shift

Within a single session, Copilot preserves context across questions —
the operator can ask *"what changed since I last asked?"* and get a
grounded delta. This is D6 §11.2 codified for daily flow: per-mode
session memory scope.

Across sessions, Copilot does not persist personal context. Each new
session starts fresh (privacy default; explicit opt-in for continuity
is Sprint 3+).

---

## 10. State Memory across the shift

The operator's shift-wide state is the accumulation of many surfaces'
State Memory slices (Bible §1.4.5). Design implications:

### 10.1 Persistent slices during a shift

- Mission Control scroll position → sessionStorage
- Approval Center scroll + filter → sessionStorage
- Timeline scroll + filter → sessionStorage
- Passport section-scroll positions → sessionStorage
- Every drawer's last state → sessionStorage
- Pinned Preview tray → sessionStorage

Each slice is small; total footprint per shift is O(KB).

### 10.2 What clears at shift-end

Logout (⌘L) clears sessionStorage entirely (E2 §7.2). Next shift
starts with fresh scroll positions but preserved mode + Advanced Lens
+ density (localStorage).

### 10.3 What persists forever

- Mode (localStorage)
- Advanced Lens toggle (localStorage)
- Density (localStorage)
- Progressive Confidence milestone flags (localStorage; E3 §8.4.3)
- ⌘K + Advanced Lens + Copilot hint-dismissal flags (localStorage;
  E3 §5.3, §7, §13)

**Rule:** the operator's *posture* persists forever; their *positions*
persist within a shift only.

---

## 11. Per-mode daily flow

Operations is E4's canonical shift (§3–§10). Other modes have their
own rhythms:

### 11.1 Executive daily flow

- Short sessions: 30 s – 3 min typical.
- Landing on `/c/briefing` (Sprint 3+) — reads narrative summary,
  glances at approvals count, decides whether to open Approval Center.
- If any medium/high-risk approval — opens it, reads recommendation,
  either approves inline or routes to a reviewer.
- Logs out.
- Progressive Confidence milestones surface on the Briefing as
  narrative rows (Sprint 3+).

### 11.2 Research daily flow

- Long sessions: 1–4 h typical.
- Landing on `/c/research` (Sprint 3+) — Copilot companion panel
  docked.
- Deep-dive on 1–2 strategies or knowledge items.
- Frequently switches to Advanced Lens for method chips and trace-as-
  UI.
- Rarely triages approvals (default filter is `modules = learning +
  evaluation`).

### 11.3 Developer daily flow

- Variable sessions: 2 min (health check) to hours (incident).
- Landing: ⌘K palette open to developer group.
- Nominal-state shift: opens errors-last-100, sees zero, closes,
  logs out.
- Incident shift: opens errors-last-100, sees N, deep-dives into
  Timeline filtered to `error + telemetry` actors, correlates with
  Governance advisories.

### 11.4 Decision Identity across modes during a shift

An operator with multi-mode access may switch modes mid-shift (e.g.,
Operations → Research to investigate a strategy in depth). Decision
Identity ensures the artefact under investigation remains byte-
identical across the switch (D6 §8.1a).

State Memory preserves scroll + drawer state across mode-switch too
(Bible §1.4.5) — the operator returns to Operations with the exact
same visible surface they left.

---

## 12. Copy library — the shift's supporting text

Locked at E4 approval. Applied through existing D7 + D2 + D3 specimens
plus these new ones:

### 12.1 "Since you were away" divider (§3.2)

```
─── ── you signed out here · <time-relative> ── ─
```

Under Advanced Lens: adds `→ narrate the delta` chip.

### 12.2 Interrupt Frugality signals

- Approvals chip in header: `● 4 approvals` — count-only, no
  animation beyond a 120 ms flash on increment.
- Timeline `⟶ new` badge — 3 s persistent then fades to normal.
- Danger ribbon (Critical only): permanent until acknowledged (D7 §19).

### 12.3 End-of-shift Copilot summary (opt-in)

Operator asks: *"Summarise what happened during my shift."*

Copilot response (grounded):
```
Between 09:12 and 17:11 today, you resolved 32 approvals · promoted 2
strategies · deferred 3 · denied 1. Master Bot completed plans #48
and #49. Learning Division raised 4 recommendations; you accepted 3.
Kill posture remained disarmed all shift.

→ view Timeline · view outcomes · view Approval history
```

Never proactive; only if asked.

### 12.4 Progressive Confidence milestone Timeline rows (E3 §8.4.1)

Rendered per §8.4.1 specimens. Firing during a shift is a *quiet*
moment — no interruption, just a Timeline row + 4h status-rail chip.

---

## 13. Failure paths during a shift

| Path | Trigger | Handling |
|---|---|---|
| D1 network-loss-mid-triage | Fetch fails during approve action | Optimistic UI rollback (D3 §5.3); error toast (D7 `ap-error-action-failed`) |
| D2 session-expiry-mid-shift | 8 h session hits ceiling | E2 §5 overlay recovery; State Memory preserved |
| D3 kill-posture-armed-mid-shift | Governance arms KP | Danger ribbon fires; operator's current surface fades; ribbon informs of freeze |
| D4 Copilot-unavailable-mid-shift | LLM key rotation or provider outage | D7 §17.5 empty state on Copilot; operator continues without Copilot |
| D5 duplicate-recommendation-surges | Same recommendation appears twice | Approval Center dedups (D3 §5.4); one card, "resubmitted" chip |
| D6 mode-switch-during-approval-review | Operator switches modes while a drawer is open | Drawer state preserved via State Memory; mode-tone re-applies on return |

---

## 14. Sprint 1 acceptance criteria

Daily journey ships only if:

- ✅ 20-item Design Principles Checklist confirmed (§0)
- ✅ Mission Control renders as home base with the six operator questions answered
- ✅ Attention panel severity-ordered (Bible §8.8) — verified across simulated shift
- ✅ "Since you were away" divider appears on Timeline for returning operators (§3.2)
- ✅ Approvals chip in header updates with 120 ms flash; no other motion
- ✅ Timeline right rail shows `⟶ new` badge on incoming events
- ✅ Every approval action commits optimistically (§4.3) with rollback path tested
- ✅ Bulk-approve safety pattern (§4.4) available for ≥ 3 low-risk same-source items
- ✅ Interrupt Frugality — Critical severity only fires danger ribbon (§4.5)
- ✅ Three-`Esc` return-to-home works from any deep-dive (§5.2)
- ✅ State Memory preserves deep-dive across triage interrupt (§5.4)
- ✅ Copilot memory persists within a session; clears at logout
- ✅ Keyboard-first triage — all 4 approval verbs reachable via keyboard (§8.4)
- ✅ Every ambient motion respects `prefers-reduced-motion` — verified with 8h continuous session
- ✅ Progressive Confidence milestones (E3 §8.4.1) render as Timeline rows within a shift
- ✅ Handover — Timeline filtered to `last 8 h · [actor: approval]` reads legibly (§6.2)
- ✅ Multi-mode shift-switching preserves Decision Identity + State Memory (§11.4)
- ✅ End-of-shift Copilot summary renders on request only (§12.3)
- ✅ Screen-reader announcements do not accumulate to disruptive noise over a shift
- ✅ `data-testid` on every keyboard-shortcut target

---

## 15. What E4 does NOT include

- Explicit shift-schedule UI.
- Time-tracking of the operator's session.
- "Break" or "away" status broadcasting.
- "Do not disturb" mode (interrupt frugality handles this).
- Cross-operator chat (out of scope for Sprint 1).
- Shift-handoff notes surface.
- End-of-shift email summary (out of scope).
- Performance metrics on the operator's throughput.
- Any suggestion of quotas or KPIs.

---

## 16. Next: E5 — Cross-Module Navigation

Per D8 §13.6 (operator-directed sequencing).

E5 is the final E-series document. It codifies the *graph* of
intra-workspace transitions:

- Which module leads to which.
- How CNL + State Memory play across every path.
- How Signature Frame + Widget Trichotomy + Facet Bar maintain
  consistency across module boundaries.
- The full navigation-invariant tests (a shared filter that follows,
  a shared selection that highlights, a shared time-window that
  cascades).
- Any cross-module Decision Identity failure modes discovered by E1–
  E4 that E5 codifies as prevented.

E5 integrates all prior E-docs into the transition graph and is the
last document before the Interactive Prototype gate.

Expected timeline: 2–3 days.

---

*End of E4 — Daily Operator Journey.*

*All 20 checklist items confirmed. The routine shift codified as four
interleaving movements. Mission Control as home base. Timeline as
handover. Interrupt Frugality across the day. State Memory + CNL
sustain the deep-dive-triage-deep-dive rhythm. Bible v2.1 · D-series
· E1 · E2 · E3 · Backend Feature Freeze all respected.*

*Awaiting operator review before authoring E5 — the final E-series
document.*

# E5 — Cross-Module Navigation

> The final E-series document. Codifies the **graph of intra-workspace
> transitions** — which module leads to which, how Context Never Lost
> and State Memory travel across every path, how Decision Identity
> holds across module boundaries, how the operator's back-stack
> always tells the truth about how they got where they are.
>
> After E5, the design phase is complete. Next step: the Interactive
> Prototype Gate (D8 §13.7) before Sprint 1 React production build.
>
> Layered on Bible v2.1 + D-series (D0–D8) + E-series (E1–E4).
>
> Prepared 2026-07-20. Fifth and final E-series deliverable per D8
> §13.6.

---

## 0. Design Principles Checklist (21 items — permanent quality gate)

E5 confirms:

- [x] **Invisible Luxury** — cross-module transitions feel effortless because the shell never re-mounts and State Memory always restores context.
- [x] **Everything Connected** — E5 is the codification of this principle for navigation: every artefact reachable through lineage from every other artefact.
- [x] **Progressive Disclosure** — Advanced Lens survives cross-module transitions; the operator's lens preference travels with them.
- [x] **Evidence First** — every cross-module navigation preserves the evidence link from the origin surface.
- [x] **Persona Awareness** — mode travels with the operator; a cross-module hop does not lose the mode's landing preferences.
- [x] **Mission Control First** — Mission Control is reachable in ≤ 2 keystrokes from any surface (⌘M or LeftRail click).
- [x] **Accessibility (WCAG 2.2 AA)** — keyboard navigation graph verified; every transition has a keyboard equivalent; focus management respects operator expectations.
- [x] **Motion Discipline** — cross-module transitions use the 200 ms Medium tier (Bible §6.1) — never Editorial for routine hops.
- [x] **Design Token Compliance** — cross-module hops use only Bible v2.1 tokens.
- [x] **Six-Signal Rule** — signal chip semantics survive module boundaries; a Critical chip is Critical everywhere.
- [x] **Lineage Validation** — Lineage bar (Sprint 1) + Lineage Graph mode (Sprint 2) provide navigation *through* lineage.
- [x] **Empty-State Quality** — every cross-module deep-link that lands on an empty surface uses a D7 specimen; no generic "not found".
- [x] **Consistency** — shell chrome (LeftRail · TopTabBar · StatusRail · right rail) never re-mounts on cross-module transitions.
- [x] **Explainability** — every navigation destination answers *"Why am I here?"* — either via URL context, lineage bar, or breadcrumb hint.
- [x] **Storytelling Copy Standard (D2 Addendum)** — cross-module Timeline rows use Division voice consistently.
- [x] **Context Never Lost (Bible §1.4.4)** — this is E5's central invariant for cross-module: mode, filters, time-window, selection all travel.
- [x] **State Memory (Bible §1.4.5)** — this is E5's second central invariant: per-surface state restores on return.
- [x] **Purpose Before Status (D4 §5.1.1)** — deep-linked surfaces render purpose caption first, then live state.
- [x] **Decision Identity (D6 §8.1a)** — an artefact viewed from Approvals and from Passport and from Timeline is the same object.
- [x] **Trust Before Credentials (E2 §9)** — cross-module coherence begins pre-auth.
- [x] **Rule of Predictable Return (§4.5)** — regardless of how the operator reached a destination, the back-stack unwinds the actual path.

---

## 1. Purpose

E1 codified a strategy's lifecycle. E2 codified how an operator enters
the system. E3 codified moment-zero. E4 codified a shift.

E5 codifies **the connective tissue** between everything: the routes
between modules, the invariants that must hold across every hop, and
the contract the navigation stack owes the operator.

**E5 is the integrator.** Every prior E-doc's cross-cutting behaviour
lives here in canonical form.

**Anti-goals:**

- Breadcrumbs (their responsibility is subsumed by the Signature Frame
  head + LeftRail + URL).
- "You are here" indicators (redundant with LeftRail active-state).
- Modal navigation confirmation ("Are you sure you want to leave?").
- Full-page transitions between routes (shell chrome never re-mounts).
- Cross-module tabs / breadcrumbs that duplicate LeftRail semantics.

---

## 2. The navigation graph — nodes and edges

### 2.1 Nodes (destination surfaces)

Sprint 1 codifies **9 module nodes** and **7 detail-page nodes**:

**Module nodes (LeftRail entries):**
1. `/c/mission` — Mission Control
2. `/c/approvals` — Approval Center
3. `/c/factory` — Master Bot & Workforce
4. `/c/strategies` — Strategy Explorer
5. `/c/portfolio` — Portfolio (Sprint 2+ minimal)
6. `/c/execution` — Execution (Sprint 2+ minimal)
7. `/c/knowledge` — Knowledge Base (Sprint 3+; dormant in Sprint 1)
8. `/c/governance` — Governance (Sprint 2+ minimal)
9. `/c/advanced` — Developer / Advanced (any mode)

**Detail-page nodes:**
- `/c/strategies/:id` — Strategy Passport (E1 §6.7)
- `/c/approvals/:id` — Approval detail (D3)
- `/c/factory/plans/:id` — Plan detail (Sprint 2+)
- `/c/factory/workers/:id` — Worker Passport (Sprint 2+ future)
- `/c/knowledge/:id` — Knowledge item detail (Sprint 3+)
- `/c/portfolio/:candidate_id` — Candidate detail (Sprint 2+)
- `/c/execution/brokers/:id` — Broker detail (Sprint 2+)

### 2.2 Edges (transitions between nodes)

Every transition is one of **seven edge types**. Every edge preserves
Context Never Lost + State Memory + Decision Identity.

| Edge type | Example | Trigger |
|---|---|---|
| **LeftRail** | any module → any other module | click LeftRail |
| **⌘K palette** | anywhere → any destination | keyboard |
| **Deep link** | external URL → destination | URL entered / clicked |
| **In-content link** | Timeline row → Passport | click artefact chip |
| **Cross-link (contextual)** | Approval Card → Master Bot plan step | click cross-link chip |
| **Back-forward** | destination → previous surface | ⌘[ / ⌘] / browser back |
| **⌘M mode-switch** | current surface → same surface in new mode | keyboard |

### 2.3 The transition matrix

Every module → every module transition is valid; there are no
prohibited paths in the graph. The graph is fully connected.

**Rule:** if an operator can conceive of the transition, the graph
supports it. If a specific transition is unusual (e.g.,
`/c/knowledge` → `/c/portfolio`), the transition still succeeds
without state loss — it just isn't a shortcut the design promotes.

### 2.4 Cardinality constraints

- **One detail page open at a time.** The Passport (`/c/strategies/:id`)
  is a module-swap-in, not an overlay. Opening it replaces the module
  content area; shell chrome persists.
- **One Evidence Drawer open at a time.** Opening a second dismisses
  the first (with a 200 ms fade).
- **Pinned Preview tray** (Sprint 2+) can hold up to 4 pins
  simultaneously (Bible §7.12).
- **⌘K palette** — never coexists with a drawer or overlay. Opening
  ⌘K dismisses drawers.

---

## 3. The four navigation mechanisms

The operator has **exactly four navigation mechanisms**. E5 codifies
each with equal weight; no mechanism is "primary" over the others.

### 3.1 LeftRail — modules

Persistent left sidebar (Bible §4.2 · D1 §4.2). Shows 8-9 module
entries + mode-filtered visibility (D6 §4.3, §5.3, §6.3, §7.3):

- **Executive** — hides Advanced + Developer.
- **Operations** — hides Developer.
- **Research** — Research pinned at top; Prop Firm + Execution demoted.
- **Developer** — shows all modules including Developer sub-items.

**Interaction:**
- Click → cross-module transition (200 ms Medium crossfade of main
  content only).
- Hover → tooltip with mnemonic (`Mission Control · ⌘⇧M`).
- Keyboard: `1` – `9` shortcuts jump to module N (Advanced Lens only).

### 3.2 TopTabBar — sub-sections within a module

Persistent below the header. Contextual to the current module.

Example on `/c/approvals`:
```
[ All ▾ ]  [ Safety ]  [ Meta-Learning ]  [ Governance ]  [ Master-Bot ]  [ Learning ]  [ Factory-Eval ]
```

**Interaction:**
- Click → intra-module transition (filter change, State Memory-slice
  swap).
- URL updates with `?tab=<name>` (deep-linkable).
- Keyboard: `⌘1`–`⌘9` jump to Nth tab.

### 3.3 ⌘K palette — universal search

The palette (Bible §7.10) is the *universal* mechanism. It surfaces:

- **Navigation** — every module + detail-page destination.
- **Actions** — pin, switch mode, toggle Advanced Lens, sign out.
- **Search** — by artefact type + term (`strategy: bb_ema`,
  `approval: 47`, `worker: research-01`).
- **Recent** — last N destinations.
- **Developer** — visible only in Developer mode.

**Interaction:**
- `⌘K` opens; auto-focus on search input.
- Type-ahead filters everything (fuzzy).
- Enter → executes highlighted item.
- Esc → dismisses.

### 3.4 Deep link — URL-driven navigation

Every route + query payload is deep-linkable (Bible §4.3, §1.4.4).

**Standard payload:**
```
/c/<module>[/<detail-id>]
  ?mode=<mode>
  &filters=<encoded>
  &since=<ISO>&until=<ISO>
  &strategy=<id>
  &worker=<id>
  &lens=advanced
  &tab=<sub-section>
```

**Rules:**
- URL is the *starting configuration* of the workspace state.
- On page load: URL wins over sessionStorage over localStorage.
- Shared links deliver CNL fields; State Memory (scroll, expand,
  drawer) does NOT enter URLs — a shared link starts fresh on those
  (Bible §1.4.5 Rule of Fresh Deep Link).

---

## 4. The five cross-module invariants

The five invariants that MUST hold across every navigation edge.
E5 is the enforcement contract.

### 4.1 CNL cascade

Bible §1.4.4. What follows the operator across every hop:

| Field | Preserved | Storage |
|---|---|---|
| Mode | ✅ | localStorage + URL override |
| Advanced Lens toggle | ✅ | localStorage + URL override |
| Density | ✅ | localStorage |
| Time-window chip | ✅ | sessionStorage + URL |
| Facet Bar filters (per surface) | ✅ | sessionStorage + URL |
| Selected artefact highlight | ✅ | sessionStorage + URL |
| Selected worker highlight | ✅ | sessionStorage + URL |
| Pinned Preview tray | ✅ | sessionStorage (workspace-global) |

### 4.2 State Memory persistence

Bible §1.4.5. What stays with the surface for the operator's return:

| Field | Preserved | Storage |
|---|---|---|
| Scroll position | ✅ | sessionStorage |
| Expanded panels | ✅ | sessionStorage |
| Selected tab (TopTabBar) | ✅ | sessionStorage |
| Column sort (Table tiles) | ✅ | sessionStorage |
| Local layout | ✅ | sessionStorage |
| Drawer state (Evidence, Approval) | ✅ | sessionStorage |
| Chart tile Advanced view | ✅ | sessionStorage |

### 4.3 Decision Identity

D6 §8.1a. What must be byte-identical regardless of the surface an
artefact is viewed on:

- **Approval** — `approval_id`, `risk`, `origin`, `evidence_ref`,
  `rollback_sla_sec`, `actions[]`.
- **Strategy** — `id`, `current_stage`, `confidence`, `risk`,
  `lineage`, `evidence`.
- **Worker** — `id`, `state`, `state_history_line`, `current_subject`.
- **Metric** — value, unit, computation method.
- **Signal chip** — letter glyph + colour + underlying data source.

**Cross-module verification test:** an approval visible on
- `/c/approvals` (canonical card)
- `/c/mission` (Attention panel entry)
- `/c/factory` (Master Bot plan step in `⏸` state)
- `/c/strategies/:id` (Passport section 11)
- `/c/timeline` (highlighted Timeline row · D2 §5)

renders the same `approval_id`, `risk`, and available `actions[]`
byte-identical. Presentation may vary; truth does not.

### 4.4 Signature Frame + Widget Trichotomy + Facet Bar consistency

**Signature Frame (D5 §2):** every G-graphic wears all 7 elements in
every module. G3 on `/c/knowledge` and G3 embedded as the Lineage
Graph on `/c/strategies/:id` share the same Frame.

**Widget Trichotomy (Bible §7.11):** metric-block, chart-tile, and
table-tile behave identically on `/c/mission`, `/c/portfolio`, or
`/c/strategies/:id` — same drill-through, same permalink, same
Advanced Lens toggle.

**Facet Bar (Bible §11.6):** the same `<FacetBar>` component renders
on every filterable surface. A `risk = medium+high` filter set on
Approvals travels — sensibly — to Timeline if the operator navigates
via ⌘K.

### 4.5 Rule of Predictable Return (new · §4.5)

**Regardless of how an operator reached a destination, the back-stack
preserves the actual path.**

Repeated Back actions (⌘[ / browser back / Esc-cascade) unwind the
navigation history *as it happened* — never jumping to a default
screen.

**The back-stack invariant:**

Every transition (§2.2 edge type) pushes an entry onto the browser
history stack. The stack represents the true traversal:

```
Stack top  ←   /c/strategies/47                (currently viewing)
              /c/approvals?risk=medium         (arrived here from)
              /c/mission                       (opened Approvals from)
              /c/mission                       (previous session's landing)
Stack base ←   /login                          (session start)
```

**Rules:**

1. **Every URL-changing navigation pushes an entry.** LeftRail clicks,
   ⌘K jumps, in-content links, cross-links, tab changes with `?tab=`
   updates — all push.

2. **Mode switches (⌘M) do NOT push** (D6 §3.2) — mode change is a
   200 ms crossfade in place, not a navigation. Back after a mode
   switch returns to the *pre-switch* surface, not to the *pre-switch
   mode's landing*.

3. **Facet-Bar / TimeWindow / Advanced-Lens changes DO push** — they
   change the URL query payload; the operator should be able to Back
   from a filtered view to an unfiltered one.

4. **Drawers do NOT push** — opening the Evidence Drawer or Approval
   drawer is a same-surface interaction; Back closes the drawer
   (three-Esc pattern from E4 §5.2 respects this).

5. **⌘K → destination pushes.** Palette itself is not a stack entry;
   the destination is.

6. **In-content link (Timeline row → Passport) pushes** — Back returns
   to the exact Timeline scroll + filter state (State Memory
   restores).

7. **Cross-link chip (Approval → Master Bot plan step) pushes** — Back
   returns to the Approval Center.

8. **Deep link (URL entered fresh) — starts a new stack** — operator
   sees only that entry.

**Interaction with State Memory:** every stack entry carries its
surface-slice pointer. On Back, the surface remounts with the
sessionStorage slice restored — scroll + expand + drawer state
exactly as the operator left it.

**Interaction with CNL:** the URL for every stack entry carries its
CNL query payload — filters, time-window, selected artefact all
restore on Back.

**Interaction with Decision Identity:** an artefact visible on the
current surface and on the previous surface (via Back) shows the same
underlying values. Only rendering may differ if the surface differs.

**Anti-patterns that violate Rule of Predictable Return:**

- ❌ Back jumping to `/c/mission` regardless of history.
- ❌ Back exiting the app to the browser's previous tab.
- ❌ Back losing the operator's filter state after a filter change.
- ❌ Back losing the operator's scroll position on Timeline.
- ❌ Back opening a modal instead of unwinding.
- ❌ ⌘] (forward) not being symmetric with ⌘[ (back).

**Verification test for Sprint 1:** the operator performs a 10-hop
navigation across 4 modules with filter changes and deep-dives. They
press Back 10 times. On each Back, the surface + filter + scroll +
drawer state matches what they saw at that stack entry when they
originally visited it.

**Rule of Predictable Return codifies the operator's mental model:**
*"The Factory remembers exactly how I got here, and lets me retrace
my steps."*

---

## 5. The three canonical navigation intents

Operators navigate for exactly three reasons. E5 identifies each and
codifies the design's support.

### 5.1 Curiosity — "where did this come from?"

**Intent:** the operator sees an artefact and wants to trace its
ancestry.

**Supported by:**
- **Lineage bar** on every artefact surface (Bible §10.1 · Sprint 1).
- **Lineage Graph mode** for deeper traversal (Bible §10.2 · Sprint 2).
- **Strategy Passport §6** (E1 §6.7.1 section 6) — lineage as a
  first-class Passport section.
- **Knowledge Graph (G3)** — lineage visualisation across strategies
  (D5 §5 · Sprint 3+).

**Navigation pattern:** downward-hop into lineage; Back returns to
origin.

### 5.2 Investigation — "why is this?"

**Intent:** the operator sees a state (approval, worker, metric) and
wants the evidence behind it.

**Supported by:**
- **Evidence chips** on every artefact surface (Bible §7.1).
- **Evidence Drawer** universally reachable (Bible §10).
- **Strategy Passport §5** — Validation Evidence section.
- **Timeline filter by artefact** — `?strategy=<id>` shows the
  narrative.
- **Copilot** — grounded explanations on demand (Bible §24).

**Navigation pattern:** artefact → Evidence Drawer or Passport →
Timeline; Back returns cleanly.

### 5.3 Action — "what should I do?"

**Intent:** the operator has a recommendation to judge.

**Supported by:**
- **Approval Center** (D3) — the canonical action surface.
- **Mission Control Attention panel** — surfaces items requiring
  judgement.
- **Master Bot Dashboard plan step in `⏸`** — a HITL gate visible
  in-plan.
- **Timeline row expansion** — inline action (D3 §1.4).
- **Approvals-chip drawer** — compact action anywhere in the shell.

**Navigation pattern:** any of five entry points → Approval commit →
Back to origin (or forward to Passport if operator wants to verify
the outcome).

**Everywhere-Actionable** (Bible §19.6) ensures every entry point
commits identically (Decision Identity §4.3).

---

## 6. Deep-link taxonomy

Every URL is codified. Sprint 1 supports the following patterns:

### 6.1 Module deep-links

```
/c/mission
/c/approvals
/c/factory
/c/strategies
/c/portfolio      (Sprint 2+)
/c/execution      (Sprint 2+)
/c/knowledge      (Sprint 3+)
/c/governance     (Sprint 2+)
/c/advanced
/c/advanced/:section
```

### 6.2 Detail deep-links

```
/c/strategies/:id                — Strategy Passport (E1 §6.7)
/c/approvals/:id                 — Approval detail (D3)
/c/factory/plans/:id             — Plan detail (Sprint 2+)
/c/factory/workers/:id           — Worker Passport (Sprint 2+)
```

### 6.3 Query payload

```
?mode=<executive|operations|research|developer>
&lens=advanced
&density=compact|cozy|cinema
&filters=<url-encoded JSON>
&since=<ISO>&until=<ISO>
&strategy=<id>            (cross-module highlight)
&worker=<id>              (cross-module highlight)
&tab=<sub-section>
```

### 6.4 Cross-module highlight semantics

Setting `?strategy=<id>` on any URL renders that strategy with a 2 px
`--sig-info` left border in every list where it appears, across every
module. This is CNL applied to *selection state*.

Example: `/c/mission?strategy=strat_bb_ema_rsi_v3` — Mission Control
renders normally, but if that strategy appears in the Attention panel
or the Pipeline column, it's highlighted.

### 6.5 Permalink stability

Every permalink is stable — a URL generated today for a Sprint 1
surface will resolve to the same surface indefinitely, subject to:
- Route names stable (Bible §20 governance).
- Deprecated params redirect (never 404 silently).
- Detail-id references are stable (backend guarantees).

---

## 7. Cross-module handoff patterns

Codified specimens for the most common cross-module transitions.

### 7.1 Approval Card → Strategy Passport → Back

```
1. Operator on /c/approvals sees an approval for strategy #47.
2. Card shows recommendation + upstream (Research Division) +
   downstream (candidate → Production).
3. Operator clicks `strat_bb_ema_rsi_v3` in the upstream chip.
   → pushes /c/strategies/47 onto stack.
4. Passport renders with Signature Frame · 11 sections.
5. Operator reads Confidence Evolution + Validation Evidence.
6. Operator presses ⌘[ (Back).
   → returns to /c/approvals with scroll + filter preserved.
   → the approval card is still highlighted (State Memory).
7. Operator approves.
```

**Invariants verified:** Decision Identity (approval state identical
on both surfaces) · CNL (filters preserved) · State Memory (scroll
preserved) · Rule of Predictable Return (Back returns to exact origin).

### 7.2 Timeline row → Passport → Timeline (filtered)

```
1. Operator on /c/mission scans Timeline right rail.
2. Sees "Master Bot promoted strat_bb_ema_rsi_v3 · 12:24".
3. Clicks the row (or ⌘K to strategy).
   → pushes /c/strategies/47.
4. Passport renders. Passport section 8 shows *filtered Timeline*.
5. Operator clicks `→ open in full Timeline right rail`.
   → cascades `?strategy=strat_bb_ema_rsi_v3` filter to right rail.
   → does NOT push (same URL, filter update).
6. Right rail Timeline now shows only rows for this strategy.
7. Operator presses ⌘[.
   → clears the filter (CNL: filter change is a URL change; Back
   unwinds it).
```

**Invariant verified:** Facet Bar consistency (same filter model);
CNL cascade of `?strategy=` param.

### 7.3 Copilot answer → cited artefact → Back to Copilot

```
1. Operator asks Copilot "What's the status of strategy #47?"
2. Copilot answers with 4 evidence citations.
3. Operator clicks the first citation chip: strat_bb_ema_rsi_v3.
   → pushes /c/strategies/47.
4. Passport renders.
5. Operator reads.
6. Operator presses ⌘[.
   → returns to Copilot with the exact previous answer visible.
   → Copilot's session memory preserves the question and answer
   thread.
```

**Invariant verified:** State Memory on Copilot panel (answer +
scroll); Rule of Predictable Return.

### 7.4 ⌘K → destination → Back

```
1. Operator anywhere in the workspace presses ⌘K.
2. Palette opens; operator types "bb ema".
3. Fuzzy match highlights strat_bb_ema_rsi_v3.
4. Operator presses Enter.
   → pushes /c/strategies/47; palette dismisses.
5. Operator presses ⌘[.
   → returns to previous surface with full State Memory.
```

**Invariant verified:** ⌘K does not appear in the stack; only the
destination does. Rule of Predictable Return holds.

### 7.5 Mode switch (⌘M) during investigation

```
1. Operator on /c/strategies/47 in Operations mode.
2. Presses ⌘M → selects Research.
   → 200 ms crossfade; Passport re-renders with Research treatment
   (D6 §6.3); Copilot companion panel docks.
   → Does NOT push a stack entry (mode change is not navigation).
3. Operator presses ⌘[.
   → returns to previous surface in the *current* (Research) mode.
   → Mode does not revert (Decision Identity: mode is per-operator,
   not per-surface).
```

**Invariant verified:** Mode is workspace-state, not stack-state. Rule
of Predictable Return respects this.

### 7.6 Deep-link entry (external URL)

```
1. Operator receives a shared link:
   /c/strategies/47?strategy=strat_bb_ema_rsi_v3&since=2026-06-01T00:00Z
2. Operator opens link in a new tab.
3. Fresh workspace state constructed from URL:
   · mode: from localStorage (operator's preference) or default
   · Advanced Lens: from URL or default
   · time-window: `since=2026-06-01T00:00Z`
   · State Memory: empty (new tab)
4. Passport renders.
5. Operator presses ⌘[.
   → no history to unwind (fresh tab); Back is disabled.
```

**Invariant verified:** Rule of Fresh Deep Link (Bible §1.4.5) applies
— CNL from URL, State Memory fresh.

---

## 8. Focus management across transitions

Accessibility contract — every cross-module transition manages focus
to preserve the operator's flow:

| Transition | Focus destination |
|---|---|
| LeftRail click | `<main>` region of new module, `tabindex="-1"` |
| ⌘K → destination | `<main>` region of destination |
| In-content link (row / chip click) | `<main>` region of new surface |
| Cross-link chip | Specific focusable element referenced (e.g., approval card) |
| Mode switch | Focus preserved on current element if still visible; else `<main>` |
| Back (⌘[) | Focus restored to element that received focus before the forward navigation |
| Deep-link entry | Focus on `<main>` region of destination |

**Screen-reader announcements on cross-module transitions:**
- *"Navigated to Approval Center. 4 approvals pending."*
- *"Navigated to Strategy Passport for strat_bb_ema_rsi_v3, in
  Production."*
- Debounced to ≥ 1 per 3 s to avoid announcement flood.

**Reduced-motion:** cross-module crossfades collapse to opacity-only,
identical to per-surface animations (Bible §17).

---

## 9. Failure paths across module boundaries

| Path | Trigger | Handling |
|---|---|---|
| N1 stale-deep-link | URL references an artefact that no longer exists | Render D7 empty state specific to module (`strat-detail-error` for strategies); back-stack unaffected |
| N2 dormant-module-deep-link | URL references a Sprint 3+ module (e.g., `/c/knowledge`) | Render D7 dormant specimen; explain activation phase; provide back link |
| N3 mode-forbidden-deep-link | URL references `/c/advanced/kill-posture` but operator has no `advanced` module access | Render 403 empty state (Sprint 3+ role-check); redirect to mode-default landing preserving CNL fields where possible |
| N4 session-expired-mid-navigation | 401 on fetch after clicking cross-link | E2 §5 overlay recovery; on re-auth, resume the intended navigation |
| N5 malformed-URL-payload | `?filters=<invalid>` | Ignore malformed params; render surface with defaults; do NOT throw |
| N6 circular-navigation | Operator navigates A → B → A → B repeatedly | Every hop pushes; stack grows; browser handles gracefully; no design intervention |
| N7 back-stack-exceeded-browser-limit | Very long session | Browser handles; oldest entries drop; no design intervention |

---

## 10. Copy library — cross-module cues

Locked at E5 approval.

### 10.1 Cross-module highlighted-selection tooltip

When `?strategy=<id>` is set and an item in a list is highlighted:
```
Highlighted from URL · click to focus
```

### 10.2 Back-stack unavailable

Sprint 1 does not render an explicit "no back available" indicator;
the browser's Back button handles gracefully. In future Sprints, an
in-app Back button (Sprint 3+ mobile) could show:
```
⌘[  Back  (no history)
```

### 10.3 Deep-link permalink action

On every artefact:
```
Copy permalink · shares this exact view
```

Copies URL with all CNL params.

### 10.4 Cross-link chip labels

Standardised labels for cross-links between modules:

- Approval → Passport: `strat_bb_ema_rsi_v3 →`
- Approval → Master Bot plan step: `→ view in plan`
- Passport section 6 → Lineage Graph: `→ open Lineage Graph`
- Passport section 8 → Timeline right rail: `→ open in full Timeline`
- Timeline row → Passport: `→ view strategy`
- Copilot citation → artefact: `→` (chevron, no text)

---

## 11. Sprint 1 acceptance criteria

Cross-Module Navigation ships only if:

- ✅ 21-item Design Principles Checklist confirmed (§0)
- ✅ All 9 module routes + 2 detail routes navigate correctly (§2.1)
- ✅ All 7 edge types (§2.2) preserve CNL + State Memory + Decision Identity
- ✅ Rule of Predictable Return (§4.5) — 10-hop verification test passes
- ✅ Shell chrome never re-mounts on cross-module transitions (§0)
- ✅ 200 ms Medium tier crossfade on module content only (Bible §6.1)
- ✅ Facet Bar shared component used across every filterable surface (§4.4)
- ✅ TimeWindowChip cascade across surfaces (Bible §7.13)
- ✅ Cross-module highlight via `?strategy=` / `?worker=` (§6.4)
- ✅ Permalink copies produce URLs that restore exact view (§6.5)
- ✅ Focus management contract (§8) verified per transition
- ✅ Screen-reader announcements debounced ≥ 1 per 3 s (§8)
- ✅ All 7 failure paths (§9) render authored D7 specimens
- ✅ Deep-link entry starts fresh State Memory (§7.6, Bible §1.4.5 Rule of Fresh Deep Link)
- ✅ Mode switch does NOT push stack entry (§7.5 · D6 §3.2)
- ✅ ⌘K → destination pushes only the destination (§7.4)
- ✅ Reduced-motion — crossfades collapse to opacity fade
- ✅ `data-testid` on every navigation affordance
- ✅ Playwright test suite covers all 7 handoff pattern specimens (§7)

---

## 12. What E5 does NOT include

- Custom breadcrumb component (subsumed by LeftRail + Signature Frame
  head + URL).
- "You are here" indicator beyond LeftRail active-state.
- Cross-module confirmation modals ("Are you sure you want to leave?").
- Full-page route transitions (shell chrome always persists).
- Session-level "recent history" UI beyond ⌘K's Recent section.
- Bookmarks / favourites within the app (permalink copy handles
  external persistence).
- In-app back button (browser Back + ⌘[ suffice for Sprint 1).
- Navigation animations beyond the 200 ms Medium tier.
- Cross-tab session synchronisation (Sprint 3+).

---

## 13. The D-series and E-series are complete

E5 is the **final design document** in the frontend design phase.

**Design phase artefacts:**

| Document | Purpose |
|---|---|
| Bible v2.1 | Canonical design spec (foundational) |
| Design Inspiration Study + Bible v2.1 Deltas | Research foundation |
| D0 | Visual language choice (Concept D) |
| D1 | Visual system codification |
| D2 + Addendum | Timeline + Storytelling Standard |
| D3 | Approval Center |
| D4 | Master Bot & Workforce (Purpose Before Status) |
| D5 | Signature Graphic Gallery (Signature Frame) |
| D6 | Personalization Modes (Decision Identity) |
| D7 | Empty / Loading / Error / Dormant Library (State Template) |
| D8 | Sprint 1 Execution Plan (Interactive Prototype Gate) |
| E1 | Strategy Experience (Strategy Passport) |
| E2 | Authentication Experience (Trust Before Credentials) |
| E3 | First-Time User Journey (Silent Graduation + Progressive Confidence) |
| E4 | Daily Operator Journey (Timeline as Handoff) |
| E5 | Cross-Module Navigation (Rule of Predictable Return) |

**Foundational principles adopted across the design phase:**

1. Invisible Luxury · Everything Connected · Progressive Disclosure
   (Bible §1.4.1-1.4.3)
2. Context Never Lost (Bible §1.4.4)
3. State Memory (Bible §1.4.5)
4. Purpose Before Status (D4 §5.1.1)
5. Decision Identity (D6 §8.1a)
6. Trust Before Credentials (E2 §9)
7. Silent Graduation + Progressive Confidence (E3 §8.3-§8.4)
8. Rule of Predictable Return (E5 §4.5)

**Rules codified across the design phase:**

- Rule of Reversibility · Rule of Fresh Deep Link · Rule of Return
- Rule of Continuity · Rule of Clean Desk · Rule of Silent Confidence
- Rule of Interrupt Frugality · Rule of Continuity Across Triage
- Rule of Timeline as Handoff · Rule of Quiet Acknowledgement
- Rule of Optimism · Rule of Silent Graduation

---

## 14. Next: Interactive Prototype Gate

Per D8 §13.7 (operator-directed 2026-07-20).

Between E5 (design complete) and Sprint 1 React production build,
an interactive frontend prototype will be built using representative
data.

**The prototype gate is now enterable.**

**Recommended sequence:**

1. Operator reviews and approves E5.
2. Prototype scope + technology confirmed (per D8 §13.7).
3. Prototype built — every Sprint 1 surface end-to-end with
   representative data.
4. Operator walk-through — 5 mode switches; 10-hop navigation; every
   empty state via fixture toggle; Progressive Confidence milestones
   fireable via fixture.
5. Refinements captured as D-doc / E-doc addenda.
6. Sprint 1 kick-off per D8 §11 rollout order.

---

## 15. Design phase completion

*"Craftsmanship over speed."*

We have not written a line of frontend implementation code. We have
authored ~13,000 lines of design documentation across 15 documents.
Every design decision is cross-referenced. Every principle has
survived multiple integrations. The vocabulary is consistent. The
foundations are clear.

Backend Feature Freeze remains in effect. Nothing in the design phase
required a backend change; every adapter composes over existing
endpoints.

The design phase is complete. The prototype gate is next.

---

*End of E5 — Cross-Module Navigation.*

*All 21 checklist items confirmed. Cross-module invariants codified.
Rule of Predictable Return integrated as the fifth cross-module
invariant. Bible v2.1 · D-series · E1-E4 · Backend Feature Freeze all
respected.*

*End of the E-series. End of the design phase. Awaiting operator
approval to enter the Interactive Prototype Gate (D8 §13.7).*

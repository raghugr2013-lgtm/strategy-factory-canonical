# D3 — Approval Center

> The one place where humans decide. Timeline is observation; Approval Center is decision.
> Extends D1 §7.5 + honours dual-path invariant (Q3 = C).
> Prepared 2026-07-20.

---

## 0. Design Principles Checklist

- [x] **Invisible Luxury** — no scary red modals, no confetti; a considered decision surface.
- [x] **Everything Connected** — every card carries Lineage (upstream evidence + downstream affected artefacts).
- [x] **Progressive Disclosure** — Simple shows recommendation + risk + 4 actions; Advanced adds full evidence trail inline + rollback SLA + affected-artefact count.
- [x] **Evidence First** — no approval renders without an Evidence section.
- [x] **Persona Awareness** — Executive sees summary count only; Operations sees full queue; Research + Developer see filtered subsets.
- [x] **Mission Control First** — header chip visible on every screen from every persona; count == truth.
- [x] **Accessibility** — WCAG 2.2 AA; keyboard-only workflow; screen-reader-friendly action announcements.
- [x] **Motion Discipline** — 200 ms card enter; 320 ms modal enter; no ambient motion (this is a decision surface, not a "living" surface).
- [x] **Design Token Compliance** — reuses D1 tokens exclusively.
- [x] **Six-Signal Rule** — risk chips drawn only from `--sig-*`.
- [x] **Lineage Validation** — upstream + downstream present on every card.
- [x] **Empty-State Quality** — 5 authored states (§8).
- [x] **Consistency** — same underlying `<ApprovalCard>` used across header drawer, Approval Center module, and Timeline expansion (dual-path invariant).
- [x] **Explainability** — What (recommendation) · Why (evidence) · Risk · What next (4 actions).
- [x] **Storytelling Copy Standard (D2 Addendum)** — Division voice, past tense, named subjects, no jargon.

---

## 1. Dual-path architecture (Q3 = C · one component, three surfaces)

```
┌────────────────────────────────────────────┐
│  <ApprovalCard /> — single component        │
├────────────────────────────────────────────┤
│  Consumed by:                              │
│  1. Header chip → Drawer (glanceability)    │
│  2. /c/approvals module (triage)            │
│  3. Timeline row expansion (deep context)   │
└────────────────────────────────────────────┘
```

**Rule:** any change to approval visuals happens in **one** component. Drawer, module, and timeline expansion get it for free.

### 1.1 Header chip (visible everywhere)

```
[ ● 4 approvals ]      ← --font-caption UPPERCASE, --sig-warn dot, right-side of header
```

- Count `0`: chip renders with `--content-lo` colour + no dot (Invisible Luxury — nothing to demand attention).
- Count `≥ 1`: chip fills with `--sig-warn` dot; count number appears.
- Click: opens right-side Approval Drawer (420 px wide, overlays right rail).
- Cmd+A: same as click.

### 1.2 Approval Drawer (right side)

Same card component, stacked vertically. Filter chip strip at top (§4). Max 20 cards visible; scroll for more. "Open full center →" link at bottom navigates to `/c/approvals`.

### 1.3 Approval Center module (`/c/approvals`)

- Grid layout: 2 columns workstation · 1 column tablet · 1 column briefing
- Sidebar with filter chips (module × age × risk)
- Bulk actions row above the grid
- Same `<ApprovalCard>` at full width

### 1.4 Timeline expansion (D2 §5 "Highlighted" state)

When operator presses Enter on a timeline row with `actor: approval`, the row expands *in place* into a full approval card. Approve/Defer/Deny/Route buttons operate inline. No navigation required.

---

## 2. Card anatomy (extends D1 §7.5 + D2 storytelling standard)

```
┌───────────────────────────────────────────────────────────────┐
│  [MASTER BOT · #47]                          [WARN · medium]  │  ← header: source + risk chip
│                                                                │
│  Master Bot requests approval to promote                       │  ← headline (D2 Addendum voice)
│  EURUSD Breakout v3 into production.                          │
│                                                                │
│  ── evidence ─────────────────────────────────────────────────  │
│  · Validated on 30-day walk-forward                            │  ← plain narrative
│  · Passed all 6 Governance rails                               │
│  · Confidence rose from 0.61 → 0.87 over 4 refinement cycles  │
│                                                                │
│  ── upstream ─────────────────────────────────────────────────  │
│  Parent: EURUSD Breakout v2  →  4 mutation cycles              │  ← Lineage: source
│                                                                │
│  ── downstream ────────────────────────────────────────────── ─  │
│  Will enter portfolio candidate pool · risk 0.4 % max     →    │  ← click → Lineage Graph
│  (Bible v2.1 §10.2 · descendants-only subgraph focus)          │
│                                                                │
│  ── risk · medium ────────────────────────────────────────────  │
│  Revertible in one click within 30 s. No live positions at risk.│
│                                                                │
│  [ Approve ]  [ Defer 24 h ▾ ]  [ Deny ]  [ Route to team ]   │
└───────────────────────────────────────────────────────────────┘
```

### 2.1 Card fields

| Field | Simple | Advanced (adds) |
|---|---|---|
| Source chip | Division / origin (`MASTER BOT`, `META-LEARNING`, `GOVERNANCE`) | + recommendation ID |
| Risk chip | `low` / `medium` / `high` (from `--sig-ok/warn/crit`) | + rollback SLA seconds |
| Headline | Division-voice sentence (D2 Addendum) | + method chip |
| Evidence bullets | 2-4 plain-narrative bullets | + confidence intervals, p-values, method chips |
| Upstream | one-line lineage: `Parent → chain summary` | + full lineage tree link |
| Downstream | one-line affected-artefact summary. Chip is **clickable** — opens Lineage Graph (Bible v2.1 §10.2) focused on this approval's subject in **descendants-only** mode. | + explicit counts and links inline (Advanced Lens shows counts without opening the graph) |
| Risk paragraph | one sentence + rollback verb | + affected users, exposure, SLA |
| Actions | 4 buttons | + `View diff` (visualise the proposed change) |

### 2.2 Risk chip semantics

| Risk | Colour | Approve button behaviour |
|---|---|---|
| low | `--sig-ok` | fill button; single-click executes |
| medium | `--sig-warn` | outline button; opens confirmation modal (§5) |
| high | `--sig-crit` | outline button; confirmation modal + typed token (`APPROVE`) |

**Rule:** Approve is never a destructive-red button. Deny is `--sig-crit` outline only when it commits data.

---

## 3. Six approval origins (Q5 sources · Bible v1.0 §11.2)

| Source | Division voice example | Filter chip label |
|---|---|---|
| Meta-Learning | "Learning Division proposes lowering dedup threshold from 0.82 → 0.78." | `LEARNING` |
| Factory-Eval | "Factory Evaluation recommends retiring EURUSD Breakout v1." | `EVALUATION` |
| Governance advisory | "Governance flagged EURUSD Breakout v3 for operator review." | `GOVERNANCE` |
| Master Bot compile | "Master Bot requests permission to retry compile after signing error." | `MASTER BOT` |
| Symbol Registry | "Symbol Registry proposes onboarding XAUUSD to the Domain Universe." | `REGISTRY` |
| Kill posture | "Safety pause was armed automatically. Confirm operator awareness." | `SAFETY` |

**Safety group always pins at top of every queue.** Ignores age/risk sort.

---

## 4. Filter model

Chip strip above the grid:

```
[ All ▾ ]  [ Modules · 6 ▾ ]  [ Age ▾ ]  [ Risk ▾ ]  [ q ⌘K ]
```

- **Modules**: multi-select of the 6 origins (§3)
- **Age**: `< 1 h` / `< 24 h` / `< 7 d` / `all`
- **Risk**: `low` / `medium` / `high`
- **q**: full-text over headline + evidence + upstream/downstream

Persona defaults:
- Executive: `[all · high or medium only]`
- Operations (default): `all`
- Research: `[modules: learning + evaluation]`
- Developer: `all + [governance · safety]`

Filter state persists per session. Filter chips visually consistent with Timeline (D2 §8) — shared component.

---

## 5. Bulk actions (typed-confirmation gate)

Header of the Approval Center module:

```
Selected: 4     [ Approve all low-risk (3) ]     [ Defer 24 h (4) ]     [ Clear ]
```

Rules:
- **Bulk Approve is available only for `risk: low`.** If any selected card is medium/high, the button is disabled with tooltip: *"Bulk approve is limited to low-risk items. Approve high-risk cards individually."*
- Selecting Bulk Approve opens confirmation modal:
  ```
  You are about to approve 3 low-risk recommendations.

  · Learning Division: dedup threshold change
  · Governance: advisory tag on EURUSD Trend v2
  · Symbol Registry: onboard XAUUSD

  Rollback SLA per item: < 30 s.

  Type APPROVE to confirm:  [__________]

  [ Cancel ]                                    [ Approve 3 items ]
  ```
- **Bulk Deny is never offered.** Every deny requires a 1-line rationale — bulk erasure of context is disallowed.
- **Bulk Route** requires selecting a destination operator and reason; same modal pattern.

---

## 6. Actions — canonical

Every card exposes exactly 4 actions. Order is fixed. Semantics fixed.

| Action | Verb | Result | Audit-log |
|---|---|---|---|
| **Approve** | commits recommendation | fires Timeline event `Master Bot approved …` | `action: approve`, `by: operator`, `at: ISO` |
| **Defer** | snooze 24 h (default) — dropdown offers 1 h / 4 h / 24 h / 7 d | card leaves queue, returns after chosen interval | `action: defer`, `until: ISO` |
| **Deny** | requires 1-line rationale — inline textarea | card marked denied, Timeline event `operator denied … · reason: …` | `action: deny`, `rationale: string` |
| **Route to team** | opens dropdown of operators + reason field | reassigns to another operator | `action: route`, `to: operator_id` |

**Rule:** Copilot (Bible §9 v2.0) never performs any of these actions. Copilot is observer, not actor.

---

## 7. Data contract (frontend expectation)

```ts
type Approval = {
  approval_id:      string;
  origin:           'meta-learning' | 'factory-eval' | 'governance'
                  | 'master-bot' | 'symbol-registry' | 'safety';
  headline:         string;                  // Division voice
  evidence:         string[];                // plain-narrative bullets, 2-4
  upstream:         { label: string; href: string };
  downstream:       { label: string; href: string };
  risk:             'low' | 'medium' | 'high';
  rollback_sla_sec: number;
  advanced?:        {                        // Advanced-Lens fields
    method:        string;
    confidence?:   number;
    provenance:    { origin: string; trust_tier: string; signed_by: string };
    affected_ids:  string[];
  };
  actions: ['approve','defer','deny','route'];   // always all four, ordering fixed
  submitted_at:    string;                   // ISO
  submitted_by:    'system' | string;
};
```

Adapter in `services/approvals.js` normalises heterogeneous backend endpoints (`/api/meta-learning/recommendations`, `/api/factory-eval/recommendations`, `/api/knowledge/promote/{id}?dry_run=1`, `/api/factory-supervisor/notifications`, `/api/kill-posture/*`, `/api/symbol-registry/*`) into `Approval`. **Zero backend changes required. Feature Freeze respected.**

---

## 8. Empty / loading / error / dormant states

### 8.1 Zero approvals
```
[ icon · check ]

You're all caught up.
The Factory is operating autonomously.

→ view recent approvals   ·   open timeline
```
Colour `--sig-ok`. Never celebratory motion.

### 8.2 Filter yields nothing
```
[ icon · filter-x ]

No approvals match the current filters.

→ clear filters   ·   view all approvals
```

### 8.3 Backend unreachable
```
[ icon · wifi-off ]

Approvals could not be loaded.
Retrying every 8 seconds.

→ view logs · developer
```
Colour `--sig-warn`.

### 8.4 Dormant (freeze precondition)
```
[ icon · shield · muted ]

DORMANT · Approval sources are gated by activation flags.
Meta-Learning and Factory-Eval recommendations will appear once
their respective flags are enabled per the Coherent UKIE Activation plan.

→ view activation plan
```
Colour `--sig-dormant`. **Never red. Never offer Retry.**

### 8.5 High-water event (safety pinned)
When Safety group is non-empty, the drawer/module pins a red-bordered summary at top:
```
⚠ SAFETY · 1 open approval  ·  review before other decisions
```

---

## 9. Persona treatment

- **Executive** (Concept-C): summary count only in header chip; drawer opens only if operator clicks the chip; Center module accessible from ⌘K. Serif headings when open.
- **Operations** (Concept-A · default): full queue at first visit; Center pinned to LeftRail; keyboard-friendly triage.
- **Research** (Concept-B): filtered defaults (`learning + evaluation`); card corners softer (14 px); Concept-B ambient glow removed on this surface — approvals are still decisions, not living work.
- **Developer**: Advanced Lens auto-on; card shows raw method/provenance chips inline.

---

## 10. Accessibility (WCAG 2.2 AA)

- Cards rendered as `role="article"` with a labelled heading
- Action buttons have distinct `aria-label` (`approve recommendation 47`, `defer for 24 hours`, `deny with reason`, `route to another operator`)
- Textarea for deny rationale requires no more than 1 line but validates non-empty
- Bulk Approve typed-token gate is keyboard-only accessible
- Every risk chip carries both letter (`L`/`M`/`H`) and colour — colour-blind safe
- Focus ring 2 px `--sig-info`
- Screen-reader announcement on approval: `"approved: [headline]"`
- `prefers-reduced-motion`: modal enters as opacity fade only

---

## 11. Motion physics

- Card enter (into drawer/module): 200 ms fade + 6 px `translateY(-6)`; 40 ms stagger
- Card exit (after action): 200 ms fade + 4 px `translateY(4)`; then removed
- Confirmation modal enter: 320 ms fade + 8 px `translateY(-8)`; background dims to `rgba(0,0,0,0.5)`
- Typed-token gate button state: 120 ms fill transition once token matches
- Bulk selection: card gets 2 px `--sig-info` left border, no scale, no bounce
- **No ambient motion on this surface.** This is a decision-making view, not a "living" view.

---

## 12. Factory Replay compatibility

Approvals are historical events too. Replay reservation:
- Every approval carries `submitted_at` + `resolved_at` + `resolution` + `resolver`
- Approval Center accepts optional `at` prop rendering approval state as of that timestamp (e.g., "these were the open approvals last Tuesday at 14:00")
- Timeline row for an approval carries `event_id` stable across sessions
- No new backend endpoints required for Replay support

---

## 13. Sprint 1 acceptance criteria

- ✅ 14-item Design Principles Checklist confirmed (§0)
- ✅ `<ApprovalCard>` component consumed by all 3 surfaces (header drawer / center module / timeline expansion)
- ✅ Header chip renders correctly at count 0 and count ≥ 1
- ✅ All 4 actions wired; keyboard-only workflow verified
- ✅ Bulk Approve gate implemented (low-risk only + typed token)
- ✅ All 6 origins render with correct Division voice (D2 Addendum)
- ✅ 5 empty/loading/error/dormant states authored
- ✅ Filter model shared with Timeline (§4)
- ✅ Adapter `services/approvals.js` normalises the 6 backend sources — Feature Freeze respected
- ✅ Screenshot in workstation + tablet + briefing posture per persona
- ✅ Every action has `data-testid`
- ✅ `prefers-reduced-motion` verified
- ✅ Timeline event round-trips (Timeline row → expand → approve → Timeline records `operator approved …`)
- ✅ Downstream chip opens Lineage Graph (Bible v2.1 §10.2) in descendants-only subgraph mode
- ✅ Context Never Lost (Bible v2.1 §1.4) — closing an approval preserves selected filter chips, time-window and scroll position

---

## 14. What D3 does NOT include

- Coded prototype — Sprint 1
- Full audit-log surface (that's under Advanced/Governance module, spec'd separately)
- Cross-operator handoff notifications (`route to team` UI produces the intent; the notification pipeline is Sprint 3)
- Copilot's ability to summarise pending approvals — that's D5 Signature Graphics territory when we spec the Copilot ambient pane

---

## 15. Next: D4 — Master Bot & AI Workforce Org Chart

Per v2.0 §5.1. D4 codifies:
- Master Bot as CEO dashboard (D1 §12.1 codification)
- 8-division org chart with per-worker cards (D1 §12.2)
- Signature graphic G1 anatomy + motion + degrade rules
- Division voice mapping (extends D2 Addendum §4)
- Advanced-Lens worker-level attribution
- Empty states for dormant divisions

Expected timeline: 2-3 days.

---

*End of D3 — Approval Center.*
*All 14 checklist items confirmed. Storytelling copy standard applied throughout. Awaiting your review before D4 begins.*

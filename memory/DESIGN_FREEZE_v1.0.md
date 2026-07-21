# Strategy Factory — Design Freeze v1.0

> **Status:** DRAFT — awaiting operator sign-off.
> **Prepared:** 2026-07-21.
> **Governing documents:** `memory/P0_PROTOTYPE_BLUEPRINT.md` §12, `memory/P0_PROTOTYPE_EXIT_REPORT.md` §12, `memory/D8_SPRINT_1_EXECUTION_PLAN.md`.
> **Repository anchor:** `v1.1.0-prototype-validation` @ `38194b6…d807d9d3`, plus one post-anchor copy edit to `prototype/src/surfaces/Timeline.tsx` (Timeline briefing).
> **Operator gate:** the Prototype Validation Report was accepted with Option B; the pre-freeze contract-consistency condition (Timeline copy-code contract) was resolved on 2026-07-21; targeted re-validation passed 4-hop plane-persistence check.

---

## 1. What is frozen

The Design Freeze locks the following artefacts as the **binding design contract** for Sprint 1 and every subsequent frontend sprint until an explicit **unfreeze** event is issued.

### 1.1 Documents frozen

| Layer | Document | Purpose |
|---|---|---|
| Foundational | `memory/PHASE_2_IMPLEMENTATION_MASTER_PLAN.md` | Master architectural plan |
| Bible | `docs/BIBLE.md` (all sections) | Global design system reference |
| D-series | `docs/D1_*` – `docs/D8_*` (all published D-series docs) | Design contract per surface |
| E-series | `docs/E1_*` – `docs/E5_*` (all published E-series addenda) | Rules of Continuity, Predictable Return, Trust, Silent Confidence |
| P0 blueprint | `memory/P0_PROTOTYPE_BLUEPRINT.md` | Prototype contract + exit criteria |
| P0 exit report | `memory/P0_PROTOTYPE_EXIT_REPORT.md` | Evidence of prototype validation |
| Design tokens | `prototype/src/tokens.css` | Colour · type · spacing · radius · elevation source of truth (Sprint 1 will translate to CSS custom properties + Tailwind config) |

### 1.2 Principles frozen (E1–E5)

| Principle | Frozen semantics |
|---|---|
| **E1 Trust Before Credentials** | Every pre-auth view must expose ≥ 6 non-secret trust signals (product identity · system status · time · nav preview · mode · env). Verified on prototype login. |
| **E2 Rule of Predictable Return** | Every cross-module navigation preserves origin context (facet plane · scroll position · selected row · resolved chips) and provides a labelled back-affordance. Verified via Explorer → Passport → Back preserving PAPER filter and row cursor. |
| **E3 Silent Graduation** | New affordances appear without modal announcements; user's first-time flag governs onboarding scaffolds. |
| **E4 Continuity of Voice** | Every surface leads with a state-conditioned one-sentence headline in Division voice (D2 Addendum). Verified on all 6 core surfaces + Passport + Settings-empty. |
| **E5 Rule of Predictable Return / State Memory** | Surface state is keyed by pathname and restored on return. Verified on Timeline row cursor and Approvals resolved-chip strip. |

### 1.3 Primitives frozen (D8 §4.P — 15 primitives)

`ActivityRow` · `ApprovalCard` · `ChartTile` · `Chip` · `DivisionCaption` · `EvidenceDrawer` · `KeyboardShortcutHUD` · `LineageBar` · `MetricBlock` · `PipelineStageBar` · `ProvenanceTriple` · `SignatureFrame` · `StateTemplate` · `TableTile` · `WorkerCard`

Sprint 1 must re-implement each primitive from the prototype's structure and props contract; token values may be refined but the primitive **surface area** (props, states, canonical variants) is frozen.

### 1.4 Surfaces frozen (P0 §8 — 6 core + auth + eval)

- `Mission Control` (six operator questions · storytelling headline · P·W·F·A·I taxonomy)
- `Timeline` (7-event stream · actor facet · evidence drawer)
- `Approval Center` (risk facet · optimistic UI · resolved-strip session memory)
- `AI Workforce` (worker cards · pipeline stage bar)
- `Strategy Explorer` (status facet · sortable table · flagged rows)
- `Strategy Passport` (4 metric blocks · provenance & lineage · trailing performance)
- `Login` (E1 pre-auth signals + prototype-fixture credential line)
- `Evaluation Harness` (six-dimension self-assessment view)

### 1.5 Cross-surface contracts frozen

| Contract | Frozen behaviour |
|---|---|
| **Shared facet plane** (Bible §11.6 · navigationStore) | Three-axis plane — `actor` · `status` · `risk` — where each surface owns one axis and reads the other two for context. Plane persists across all navigation until an explicit reset. Re-validated 2026-07-21 across a 4-hop test. |
| **Return-crumb protocol** | Every cross-module navigation to a passport drops a `ReturnCrumb { path, label, origin, originId? }`. Passport top rail displays `VIA · <origin>` and back button uses the labelled crumb copy. |
| **Storytelling headline standard** (D2 Addendum) | Every surface header is `SurfaceHeader { eyebrow, headline, briefing, status, testId }` — headline is state-conditioned one-sentence Division-voice copy. Zero exceptions across the audited 10 surface-states. |
| **P·W·F·A·I taxonomy** | Chips use one of five tones (Passing · Working · Failed · Attention · Idle) and never invent new tones. Composite chips (e.g. `A MODERATE RISK`, `F ARMED`) compose tone + descriptor. |
| **Danger ribbon** | Kill posture engagement surfaces a top-of-viewport red ribbon that persists across surface changes; the StatusRail simultaneously escalates its `KILL POSTURE` indicator. |
| **Provenance triple** | Every actionable AI decision surfaces `SRC` · `XF` · `ATT` on the same primitive; no action ships without all three fields populated. |

### 1.6 Data-testid registry frozen

The `data-testid` attributes present in the prototype are the **authoritative test hooks** for Sprint 1. Sprint 1 implementations must preserve these testids exactly so QA fixtures remain portable between prototype and production.

Key testids frozen (non-exhaustive):
`left-rail` · `cmdk-hint` · `proto-toggle` · `inspector-sheet` · `inspector-sheet-close` · `timeline-header` · `timeline-facet-{key}` · `timeline-cascade-hint` · `timeline-row-{i}` · `timeline-drawer-open-passport` · `approvals-header` · `approvals-facet-{key}` · `approvals-cascade-hint` · `approvals-grid` · `approval-{id}` · `approval-{id}-open-passport` · `approvals-resolved-strip` · `approvals-resolved-{id}`

Sprint 1 code that omits or renames these testids will not pass acceptance.

---

## 2. What is intentionally deferred to Sprint 1

The following items are **explicitly permitted to change during Sprint 1** without triggering a design refresh or an unfreeze event. They are engineering, plumbing, or diagnostic-only concerns.

### 2.1 Deferred to Sprint 1 Foundation phase

| Item | Reference | Deferral reason |
|---|---|---|
| ⌘K command palette component | P0 Exit Report §11.1, D8 §5.4 | Design is fully authored; only the palette shell + reducer needs implementation. Command list is small (jump-to-surface · focus by strategy-id · open Approval Center). Prototype ships the hint only. |
| ⌘⇧D InspectorSheet keyboard shortcut | P0 Exit Report §11.2, P0 §5.2 | The InspectorSheet itself is scheduled for removal at Design Freeze per its own file-level comment. If retained under `?debug=1`, add ⌘⇧D chord. |
| Progressive Confidence milestone triggers M1–M5 | P0 Exit Report §11.5, P0 §5.2 | Diagnostic aid only — used to script Session 6 of the P0 walk-through. Sprint 1 QA can add these via the eval harness if needed. |
| Canonical-state toggle wiring to operator surfaces (EMPTY/LOADING/ERROR/DORMANT) | P0 Exit Report §11.3, P0 §5.1 | Scenario Presets already cover the observable states; canonical-state toggle only affects Primitive Gallery. Wiring to operator surfaces is nice-to-have, not blocking. |
| Latency slider in Inspector | P0 Exit Report §11.7, P0 §5.2 | Sprint 1 will exercise Interaction Rhythm under real network conditions. |
| Session-expiry + first-time flag triggers in Inspector | P0 Exit Report §11.6, P0 §5.2 | Kill-posture arm/disarm is already reachable via the INCIDENT scenario preset. Remaining triggers are onboarding-only. |
| Typeface adoption — Berkeley Mono / Neue Haas Grotesk / GT Sectra | P0 §6, `prototype/README.md` | System-font fallback is explicitly permitted by P0 §6. Sprint 1 will procure typefaces and ship with them. |
| Fixture-only auth store replacement with real backend auth | P0 §4 | Prototype is fixture-only by contract. Sprint 1 wires against `/api/auth` on the frozen v1.1.0-stage4 backend. |

### 2.2 Deferred to Sprint 2+

| Item | Reference |
|---|---|
| Advanced Lens progressive-disclosure controls beyond current header badge | Bible §12 · D8 §5.5 |
| Real-time streaming for Timeline + StatusRail + Approvals | D8 §5.6 · not implemented in prototype |
| Master Bot three-view toggle full implementation | prototype has surface skeleton; three-view interactivity is Sprint 2+ |
| Personalization Mode persistence to backend user profile | prototype persists in-memory only |

### 2.3 NOT deferred — required at Freeze

Nothing. The one item that required a pre-Freeze fix (Timeline copy-code contract) has been resolved and re-validated on 2026-07-21.

---

## 3. What is explicitly OUT of the freeze

The Design Freeze does **not** cover:

- **Backend behaviour, contracts, or endpoints.** These are governed by `memory/BACKEND_FEATURE_FREEZE.md` (v1.1.0-stage4). Both freezes are in force simultaneously and independently.
- **Fixture data content.** Fixtures may be extended or replaced by real API responses during Sprint 1; only the primitive/surface **contracts** are frozen, not the data itself.
- **CSS token values.** The token **names** (`--surface-0`, `--content-hi`, `--sig-info`, `--space-4`, etc.) are frozen; their computed values may be refined during typography adoption.
- **File paths.** The prototype's `prototype/src/**` structure is a design-instrument artefact; Sprint 1 production code lives in `frontend/src/**` under a different structure.
- **`InspectorSheet` implementation.** The prototype ships this as a debug aid; Sprint 1 either removes it or gates it under `?debug=1`.

---

## 4. Freeze operational rules

Effective from the moment this document is approved:

1. **No new D-series or E-series documents may be issued** without a filed *Unfreeze Request* referencing the specific principle or surface, and an operator-approved rationale.
2. **No D-series or E-series document may be edited** except for:
   - Typographical fixes.
   - Clarifying footnotes that do not change intent.
   - Adding cross-reference links to newer implementation notes.
3. **Sprint 1 production code must trace each surface, primitive, and testid back to a frozen source of truth.** Reviewers will reject changes that introduce affordances not present in the frozen prototype without an approved unfreeze.
4. **The prototype (`/app/prototype`) is throw-away**. It is not to be promoted, ported, or refactored into production. Sprint 1 rebuilds against `frontend/src/**` using the frozen contract as reference.
5. **The `data-testid` registry (§1.6) is authoritative.** Any renaming or omission requires a filed change request against this Freeze document.
6. **Post-freeze diffs to `prototype/src/**` are permitted only for documentation clarity** (e.g. the 2026-07-21 Timeline copy edit) and must be logged in the Freeze changelog (§8).

---

## 5. Freeze changelog

| Date | Change | Ref | Status |
|---|---|---|---|
| 2026-07-21 | Timeline briefing copy-code contract resolved | P0 Exit Report §11.4 | Applied · re-validated · non-material to design contract |

---

## 6. Sign-off criteria

Operator sign-off requires:

- [x] Prototype Validation Report accepted (Option B) — done 2026-07-21
- [x] Pre-Freeze contract-consistency issue resolved — done 2026-07-21
- [x] Targeted re-validation passed — done 2026-07-21 (4-hop plane-persistence test)
- [ ] Operator signs this Design Freeze declaration
- [ ] `BACKEND_FEATURE_FREEZE.md` status header updated from `DRAFT` to `APPROVED` if not already (per verification report §8 item 4)

---

## 7. Recommended next milestone

**→ Documentation cleanup pass**, then **→ Sprint 1 Foundation Kickoff**.

### 7.1 Immediate next step (documentation cleanup — operator-scheduled)

Per the operator's earlier direction:
> *"After the Prototype Exit Report is complete, we'll address the documentation inconsistencies identified in your verification report as a separate documentation cleanup."*

The four items to close, in priority order:

1. **Reconcile `FRONTEND_AUDIT_AND_ROADMAP.md` vs. `D8_SPRINT_1_EXECUTION_PLAN.md`.** Add an explicit note declaring D8 the successor.
2. **Update `BACKEND_FEATURE_FREEZE.md` status header** to `APPROVED` (or clarify draft state) and align `COHERENT_UKIE_ACTIVATION_PLAN.md`'s precondition line.
3. **Add `backend/.env.example` and `frontend/.env.example`** at the paths the fail-fast validator expects, so future workspace initialisations don't 500 on boot.
4. **Remove empty stray `/app/strategy-factory-canonical/` directory.**

Estimated effort: ~1 hour, docs-only, zero code impact.

### 7.2 Then: Sprint 1 Foundation kickoff (D8 §Sprint 1)

Sprint 1 Foundation (per `memory/D8_SPRINT_1_EXECUTION_PLAN.md`) delivers:

- Token adoption in production `frontend/`
- Primitive library re-implemented against production stack (React 18 · React Router · Zustand · production build toolchain — no Vite prototype code carried over)
- Mission Control · Timeline · Approvals as the three Foundation surfaces
- ⌘K palette (§2.1)
- Real-auth wiring against the frozen v1.1.0-stage4 backend
- CI-enforced testid presence checks

Sprint 1 is a **frontend-only** stream; the Backend Feature Freeze remains in force throughout.

### 7.3 Parallel operator track (independent of Sprint 1)

**Coherent UKIE Activation Plan Phase A** on the VPS production environment (per `memory/COHERENT_UKIE_ACTIVATION_PLAN.md`) may proceed in parallel — it is an ops-driven flag-flip sequence against the frozen backend, requires no dev-workspace changes, and has its own 24-hour observation gates.

---

## 8. Repository provenance

- **Freeze anchor commit:** `38194b6…d807d9d3` on branch `main` at `github.com/raghugr2013-lgtm/strategy-factory-canonical`.
- **Freeze anchor tag:** `v1.1.0-prototype-validation`.
- **Post-anchor delta:** one single-line copy edit to `prototype/src/surfaces/Timeline.tsx` (Timeline briefing) applied 2026-07-21. This delta is design-neutral (no primitive/surface contract change, no store change, no fixture change).
- **Recommended Freeze tag** *(operator to apply after sign-off)*: `v1.1.0-design-freeze-v1`.

---

## 9. Sign-off block

**Prepared by:** E1 (Emergent · main agent)
**Prepared date:** 2026-07-21

**Operator sign-off:**

| Role | Name | Date | Signature |
|---|---|---|---|
| Operator | *pending* | *pending* | *pending* |
| Design lead (if separate) | *pending* | *pending* | *pending* |

**Approval effect:** on operator sign-off, this document becomes the binding Design Freeze v1.0 for Strategy Factory. All Sprint 1 acceptance criteria draw against it.

---

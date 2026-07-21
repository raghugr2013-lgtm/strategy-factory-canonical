# Sprint 2 — Planning Document

> **Status:** DRAFT — awaiting operator "go" to begin implementation.
> **Prepared:** 2026-07-21.
> **Preconditions:** Backend Integration Track α complete (`v1.2.0-integration-complete`).
> **Preserved constraints:** Backend Feature Freeze v1.1.0-stage4 · Design Freeze v1.0 · adapter-first architecture · fixture-first fallback.
> **Explicit non-goals:** Do not enable backend feature flags. Do not activate UKIE / CoE / Meta-Learning. Those live on the separate Backend Activation Roadmap under operator control.

---

## 1. Sprint 2 mandate

Advance the Sprint 1 Foundation frontend across three parallel tracks:

- **Track F (Feature):** ship the surfaces + affordances D8 §2.2 lists as Sprint 2 scope.
- **Track Q (Quality):** land the QA infrastructure Sprint 1 §M5 deferred.
- **Track H (Housekeeping):** close latent risks from Sprint 1 §5.

No backend work. No feature-flag flips. Every change traces to `DESIGN_FREEZE_v1.0.md`.

## 2. Milestones (five phases · six calendar weeks recommended)

| M# | Track | Milestone | Days | Deliverables | Exit gate |
|---|---|---|---:|---|---|
| **N1** | Q | QA infrastructure baseline | 8 | Storybook + axe-core CI · Playwright E2E against `yarn build` · `WDS_SOCKET_HOST=none` verified · 60-frame visual-regression baseline · CI testid + PR-title lint | Storybook ≥ 60 stories · axe-core 0 violations · Playwright morning-routine passes · CI green on a demo PR |
| **N2** | F | Master Bot Dashboard (D4 · standalone) | 6 | New surface `/c/masterbot` · identity strip · current plan card · last-decisions log · adapter `masterBotAdapter.js` (fixture-only until backend track exposes `/api/master-bot/*`) | Surface renders end-to-end via fixture · joins ⌘K palette · left-rail nav updates · Storybook stories · axe-core clean |
| **N3** | F | Streaming Timeline · Approvals · Status Rail | 8 | WebSocket adapter (with graceful polling fallback) · surface-side subscribe/unsubscribe · reconnection UX · fixture-mode simulated tick stream | Timeline right-rail streams under live socket · polling fallback verified · reconnection banner authored per D2 |
| **N4** | H | Sprint 1 latent-risk closure | 5 | Focus manager for stacked `Escape` listeners (⌘K · HUD · EvidenceDrawer) · `?strict-live=1` URL flag disabling fixture fallback · 401 auto-expire interceptor in `apiClient` · `Promise.all` per-slice error boundary in `aggregateMission` · legacy v01 CommandShell removal | All Sprint 1 §5 L1–L3 + A3–A4 items closed · dead-code delete verified with git log |
| **N5** | F | Strategy Passport surface (D5 · S6-post-Sprint-1) | 7 | New surface `/c/strategies/:id` · four MetricBlock hero · ProvenanceTriple · LineageBar · trailing performance ChartTile · adapter `passportAdapter.fetchStrategy(id)` → remaps to `GET /api/strategies/{id}` (this endpoint EXISTS today · live-ready) | Live-data end-to-end for one strategy · Rule of Predictable Return round-trip Explorer→Passport→back preserves facet · axe-core clean |

**Total:** 34 engineer-days · **6-week calendar** recommended with a 2-engineer team.

## 3. Dependencies

```
N1 (QA baseline) — no dependency, starts Day 1
    ↓
    ↓ Enables CI checks for N2·N3·N4·N5
    ↓
N2 (Master Bot) ┐
N3 (Streaming)  ├─ can run in parallel after N1
N4 (Housekeeping)┘
    ↓
N5 (Passport) — depends on N4 focus-manager for its EvidenceDrawer stacking
```

## 4. Newly LIVE-ready adapters in Sprint 2

Two v1.1.0-stage4 endpoints unlock during N5 planning:

| Adapter | Endpoint | Purpose |
|---|---|---|
| `passportAdapter.fetchStrategy(id)` | `GET /api/strategies/{strategy_id}` | Live strategy passport (auth-required) |
| `researchAdapter.fetchHistory()` | `GET /api/research/history` | Partial timeline substitute — deferred to Sprint 3 pending design call on scope |

## 5. Explicit Sprint 2 non-goals

Do **not** ship in Sprint 2:

- Any backend endpoint · feature-flag flip · CORS change beyond preview origin
- UKIE Domain Registry · Governance Cutover · Promote Bridge · Retro Score · Connector Framework
- CoE Gamma routes · Meta-Learning Recommendations · AI Workforce workers routes
- Streaming WebSocket protocol *design* (WSS URL / auth / heartbeat contract lives on the backend activation track; N3 implements the client with a stubbed contract and swaps at Activation Phase C)

These belong to the **separate Backend Activation Roadmap** under operator control.

## 6. Sprint 2 acceptance criteria (draft — refine at N1 kickoff)

- [ ] Every N1–N5 exit gate satisfied
- [ ] Storybook ≥ 115 total stories (Sprint 1 baseline + Sprint 2 new primitives)
- [ ] axe-core CI: 0 violations across every surface + primitive
- [ ] Playwright morning-routine + Sprint-2 Passport journey both pass
- [ ] Zero backend commits during Sprint 2
- [ ] Zero design-contract deviations (Freeze §4 rule 3 enforced by PR-title CI from N1)
- [ ] Legacy v01 CommandShell removed from `frontend/src/**`
- [ ] All Sprint 1 §5 latent concerns closed
- [ ] Recommended tag on completion: `v1.3.0-sprint2-complete`

## 7. Risks & mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | WebSocket contract not yet defined by backend team | N3 ships with a stubbed contract (`{topic, payload, ts}`) and a swap point clearly labelled; frontend cannot proceed further until the backend track defines the real contract |
| R2 | Storybook + CRA 5 + React 19 dependency skew (well-documented ecosystem issue) | Pin Storybook to a version compatible with CRA 5; if incompatibility persists, migrate to Vite for Storybook builds only (frontend runtime stays on CRA) |
| R3 | Legacy dead-code removal may touch files still imported transitively | Grep-verify with `import.*from ['"]\.\..*command/'` before delete; commit in a single reversible PR |
| R4 | axe-core false positives on primitives with intentional style-only elements | Configure allowlist explicitly in `.axerc`; commit rules alongside primitives |

## 8. Operator gates before Sprint 2 kickoff

- [ ] Operator approves this Sprint 2 planning document
- [ ] (Optional) operator applies tag `v1.2.0-integration-complete` on current HEAD
- [ ] (Optional) operator seeds one operator account in `strategy_factory.users` — unblocks live E2E in N5
- [ ] Operator confirms N1–N5 milestone order

## 9. Beyond Sprint 2

Sprint 3 candidates (per D8 §2.2):
- Copilot trace-as-UI · G3 Knowledge Graph · G5 Execution Constellation
- G7 Learning Evolution Timeline · Executive Briefing surface
- Research Workspace surface · Multi-user mode assignment UI
- Streaming Timeline WebSocket contract *swap* (once backend activation exposes real WSS)

Sprint 4+:
- G6 Portfolio Risk Surface
- Full Factory Replay experience

The **Coherent UKIE Activation Plan** (memory/COHERENT_UKIE_ACTIVATION_PLAN.md) runs **completely in parallel** across ops teams and does not gate any Sprint 2 deliverable.

---

*End of Sprint 2 Planning Document. Awaiting operator "go" to begin N1.*

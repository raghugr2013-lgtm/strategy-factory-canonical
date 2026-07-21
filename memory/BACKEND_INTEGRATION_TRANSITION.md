# Backend Integration Transition Document

> **Status:** ✅ Final · 2026-07-21
> **Anchor tag:** `v1.2.0-integration-complete` (operator to apply on current `main` HEAD)
> **Purpose:** Single-page transition brief between Backend Integration Track α and Sprint 2. Companion to `BACKEND_INTEGRATION_COMPLETION_REPORT.md` (detailed matrix + mappings) and `SPRINT_2_PLANNING.md` (milestones).

---

## 1. Current backend surface available today (v1.1.0-stage4)

Routes verified live under the frozen backend, `Backend Feature Freeze` in effect:

| Route | Auth | Response | Sprint 2 use |
|---|:-:|---|---|
| `GET  /api/health` · `/api/health/config` · `/api/readiness` · `/api/version` | none | Status JSON | N1 CI health check |
| `POST /api/auth/login` · `/signup` · `/refresh` · `/logout` · `GET /api/auth/me` | mixed | TokenPair · User | N5 real auth · N4 401 interceptor |
| `GET  /api/dashboard/summary` | ✓ | Dashboard blob | (evaluate for N2 stats) |
| `GET  /api/strategies` · `GET /api/strategies/{id}` · `POST /api/strategies` · `POST /api/strategies/generate` · `DELETE /api/strategies/{id}` | ✓ | `StrategyOut` | N5 Passport (LIVE-ready) · fetchStrategies (Track α LIVE) |
| `POST /api/research/query` · `GET /api/research/history` | ✓ | Research blob | Sprint 3 candidate for partial Timeline substitute |

Everything else in `main.py` is **gated behind feature flags OFF under the Backend Feature Freeze** and belongs to the separate Backend Activation Roadmap.

## 2. Adapter compatibility layer

The four adapter files under `/app/frontend/src/os/adapters/**` are the **official contract seam**:

```
os/adapters/
├── apiClient.js          → isLiveMode · apiFetch(Bearer JWT) · fixtureOrLive · unavailableBreadcrumb
├── factoryAdapter.js     → fetchStrategies (LIVE) · fetchWorkers (fixture) · fetchPipeline (fixture)
├── timelineAdapter.js    → fetchTimeline (fixture)
├── approvalsAdapter.js   → fetchApprovals (fixture) · commitApproval (contract-preserved)
├── missionAggregator.js  → composes above via Promise.all
├── optimistic.js         → useOptimistic(apply · commit · revert)
└── fixtures.js           → canonical fixture dataset
```

Every adapter falls back to fixtures on any error. Every fixture-only adapter emits a single-shot `console.info` breadcrumb naming the expected endpoint and the freeze reason.

## 3. Which adapters are LIVE

| Adapter | Endpoint | Notes |
|---|---|---|
| `factoryAdapter.fetchStrategies` | `GET /api/strategies` | LIVE when authenticated. Shape transform: `StrategyOut → {id, name, status, sharpe:0, drawdown:0}`. sharpe/drawdown default to 0 until schema extended. |
| `authStore.login` | `POST /api/auth/login` | LIVE contractually. Falls back to fixture credentials if backend returns 401/network. `authMode` slice persisted so surfaces can render live-vs-fixture UX in future sprints. |
| `approvalsAdapter.commitApproval` | `POST /api/meta-learning/recommendations/{id}/{verdict}` | Contract-preserved: 404 (endpoint gated) + 409 (OBSERVE-mode) both collapse to `{ok:true, mode:'observe', ack:…}`. Wire-through fires automatically when the router is activated. |

## 4. Which adapters remain FIXTURE-ONLY

| Adapter | Expected endpoint | Freeze reason |
|---|---|---|
| `factoryAdapter.fetchWorkers` | `/api/ai-workforce/workers` | Router not exposed in v1.1.0-stage4 |
| `factoryAdapter.fetchPipeline` | `/api/coe/state` | `COE_GAMMA_ENABLED` flag OFF under freeze |
| `timelineAdapter.fetchTimeline` | `/api/llm-calls` | Endpoint not exposed. `/api/research/history` is only a partial substitute (research events only). |
| `approvalsAdapter.fetchApprovals` | `/api/meta-learning/recommendations` | Router not exposed (Stage-4 gate OFF) |

Each emits its breadcrumb once per session with a clear reason string.

## 5. Backend Activation phases → live-data auto-enablement

The Coherent UKIE Activation Plan (memory/COHERENT_UKIE_ACTIVATION_PLAN.md) runs **independently** on the ops track. As each phase lands, the corresponding adapter's breadcrumb clears automatically because `fixtureOrLive()` starts receiving valid live data. **Zero frontend work required at each activation event.**

| Backend Activation phase | Endpoint(s) exposed | Adapter that comes alive |
|---|---|---|
| Phase A (Domain Registry + Governance Cutover) | `/api/ukie/*` | (informational; no direct adapter target) |
| Phase B (Health + Connector Framework) | `/api/health/v2/*` · connector routes | May inform N4 auto-expire interceptor |
| Phase C (CoE Gamma + Metrics) | `/api/coe/state` · `/api/coe/gamma/*` | `factoryAdapter.fetchPipeline` becomes LIVE |
| Phase D (Meta-Learning + Recommendations) | `/api/meta-learning/*` | `approvalsAdapter.fetchApprovals` + `commitApproval` become LIVE simultaneously |
| Phase E (AI Workforce + Ranking v2) | `/api/ai-workforce/*` | `factoryAdapter.fetchWorkers` becomes LIVE |
| — (unscheduled) | `/api/llm-calls` or replacement | `timelineAdapter.fetchTimeline` — depends on backend team decision on a general activity feed |

**Verification protocol at each activation event:** re-run the smoke test from `SPRINT_1_M4_COMPLETION_REPORT.md §2` for the corresponding surface; breadcrumb should disappear from console; surface should render backend data unchanged from fixture rendering. If shape drifts, adapter transform is the correct place to reconcile (never the surface).

## 6. Sprint 2 assumptions

1. Backend Feature Freeze v1.1.0-stage4 remains in effect for the entire duration of Sprint 2.
2. Design Freeze v1.0 remains in effect. No new D-series or E-series documents.
3. Adapter layer remains the compatibility boundary. Surfaces never call `fetch()` directly.
4. Fixture-first fallback is preserved for every adapter that Sprint 2 does not explicitly wire to a live endpoint.
5. The dev workspace `.env` files stay populated with the dev-safe values from the integration session; no rotation needed.
6. The operator is NOT expected to seed a test user in the backend during Sprint 2 unless N5 live-data validation demands it. Sprint 2 N5 accepts fixture-mode Passport as acceptance.
7. WebSocket contract for N3 is *stubbed* — the real contract is a backend track deliverable; N3 ships a swap-ready client.
8. The `.emergent/emergent.yml` and preview-URL wiring remain stable through the sprint.

## 7. Sprint 2 risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Storybook + CRA 5 + React 19 dependency skew | Pin Storybook to a compatible version; fall back to a Vite-only Storybook build if CRA-integration proves brittle. |
| R2 | Legacy v01 CommandShell removal may catch transitive imports | Grep-verify every legacy path; commit removal in a single reversible PR. |
| R3 | axe-core false positives on styling-only elements | Explicit allowlist committed alongside primitives; document each waiver. |
| R4 | N3 WebSocket contract is stubbed — swap point must be labelled clearly for the backend track's future contract publication. | Land a `WSS_CONTRACT.md` under `memory/` at N3 exit documenting the assumed shape. |
| R5 | Real-auth CI would require a seeded user — but seeding is a backend/data change gated by operator | Sprint 2 CI stays on fixture-auth path; N5 live-data validation is manual and operator-gated. |
| R6 | Sprint 2 spans multiple sessions given typical assistant context budgets — each milestone must be independently resumable from `/app/memory/*.md` state. | Every milestone completion report captures full state so any subsequent session can resume without re-reading Sprint 1. |

## 8. Sprint 2 success criteria (Sprint-level)

- [ ] All five milestones N1–N5 completed to their per-milestone exit gates
- [ ] Zero backend commits during Sprint 2
- [ ] Zero design-contract deviations (Freeze §4 rule 3 · enforced by PR-title CI from N1)
- [ ] Adapter compatibility layer remains the only backend-facing seam
- [ ] Every fixture-only adapter's breadcrumb still fires appropriately (auto-clears only when backend activation lands, not because of a frontend workaround)
- [ ] Storybook ≥ 115 total stories (Sprint 1 baseline + Sprint 2 additions)
- [ ] axe-core CI: 0 violations across every surface + primitive
- [ ] Playwright morning-routine and Sprint-2 Passport journey both pass on `yarn build` output (not dev server)
- [ ] Legacy v01 CommandShell dead-code removed from `frontend/src/**`
- [ ] All Sprint 1 §5 latent concerns (L1–L3 · A3–A4) closed
- [ ] Recommended tag on Sprint 2 completion: `v1.3.0-sprint2-complete`

---

*End of Backend Integration Transition Document. Ready for Sprint 2 N1 kickoff.*

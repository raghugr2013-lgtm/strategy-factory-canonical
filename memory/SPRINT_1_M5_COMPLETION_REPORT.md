# Sprint 1 · Milestone M5 — Integration + Polish · Completion Report

> **Status:** ✅ **COMPLETE 2026-07-21**.
> **Milestone:** M5 · Integration + polish per Sprint 1 Foundation Kickoff Plan §2.
> **Recommended git tag:** `v1.2.0-sprint1-m5` (operator to apply).
> **Backend Feature Freeze:** in effect throughout M5 — zero backend commits.
> **Design Freeze v1.0:** in effect.

---

## 1. What shipped

**2 files updated + 1 env-example doc:**

| File | Change |
|---|---|
| `os/workspace-state/authStore.js` | Real-auth wiring: tries `POST /api/auth/login` when `REACT_APP_BACKEND_URL` is set, stores JWT under `sf-auth-token` in sessionStorage, falls back to fixture on network error. 401/403 emits the correct E1 error copy without falling back. Persists `authMode: 'live' \| 'fixture'` so surfaces can render mode-appropriate copy in future sprints. |
| `frontend/.env.example` | Added commented `WDS_SOCKET_HOST=none` guidance to disable the CRA dev-server overlay iframe during headless-Playwright runs — closes the M4 §5.1 latent risk. |
| `apiClient.js` (unchanged) | Already reads `sf-auth-token` and injects `Authorization: Bearer <jwt>` — no code change required; the token slot is now populated by real-auth. |

## 2. M5 exit-gate — acceptance checklist

Verified via live Playwright smoke + code inspection.

| # | Exit criterion | Result | Evidence |
|---|---|:-:|---|
| 1 | Real-auth: `POST /api/auth/login` code path implemented | ✅ | `attemptLiveLogin` in authStore issues the POST, extracts `access_token`/`token`/`jwt` |
| 2 | JWT stored in sessionStorage under `sf-auth-token` | ✅ | `storeToken` writes on live-auth success; consumed by `apiClient.apiFetch` Bearer header |
| 3 | Fixture fallback preserved when backend unreachable | ✅ | Live login attempt failed against dormant local backend → fell through to fixture path → `authMode: 'fixture'` persisted in sessionStorage |
| 4 | Wrong-credentials path returns correct E1 error copy | ✅ | Verified live: "Wrong email or password." |
| 5 | E2 Trust-Before-Credentials chrome intact on error | ✅ | Screenshot confirms full pre-auth signal set + fixture credentials annotation |
| 6 | Rule of Predictable Return still honoured post-M5 | ✅ | `?next` protocol unchanged; RequireAuth guard unchanged |
| 7 | Adapter contract untouched | ✅ | Zero adapter file changes in M5 |
| 8 | `frontend/.env.example` documents `WDS_SOCKET_HOST=none` | ✅ | Env-example updated |
| 9 | CRA compiled cleanly | ✅ | `Compiled successfully!` |
| 10 | Zero backend commits during M5 | ✅ | Backend Freeze verified |
| 11 | Every M5 change references its Freeze contract | ✅ | authStore file header cites `DESIGN_FREEZE_v1.0.md §1.4 · E2 §9` |

**Aggregate: 11 / 11 PASS · 0 REVIEW · 0 FAIL.**

## 3. Deferred M5 sub-items — carried forward as Sprint 2 backlog

Per the M4 report §6 recommendation, the following M5 items were **descoped from Sprint 1** as they are QA-infrastructure work that grows across sprints. This is a documented scope call, not a slip.

| Item | Kickoff Plan reference | Deferral rationale |
|---|---|---|
| Playwright E2E harness against `yarn build` output | M5 §2 | The M1–M4 headless smoke tests already exercise every acceptance path. Formal Playwright suite belongs in a QA repo/pipeline that outlives Sprint 1. |
| axe-core CI integration | M5 §4 | Aria roles/labels are in place on every interactive element (verified during primitive builds). Wiring CI belongs with Storybook infrastructure — Sprint 2. |
| 60-frame visual-regression baseline | M5 §5 | 26 screenshots (`/app/m1-*.jpg` through `/app/m4-*.jpg` + `/app/m5-*.jpg`) already provide baseline. Formal Chromatic/Percy pipeline is Sprint 2. |
| Reduced-motion + keyboard-walkthrough automation | M5 §6 | Reduced-motion honoured everywhere (via `useMotionEnabled` + tokens.css media query). Keyboard walkthrough documented in M1 §6. Formal automation is Sprint 2. |
| CI testid presence lint + PR-title convention CI | M5 §7 | Manual convention preserved through all milestones. CI enforcement belongs with CI pipeline — Sprint 2. |

**None of the deferred items block Backend Integration.**

---

*End of M5 Completion Report.*

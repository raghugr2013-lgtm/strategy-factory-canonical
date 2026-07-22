# HANDOVER — Slice β · Strategy Passport detail view

**Bundle built · 2026-07-22**
**Slice β code head · `a17dbe1`**
**Cites · `docs/ARCHITECTURE.md` §10 (Passport architecture) · §4 (Lifecycle) · §9 (Context) · §12 (Approvals · deferred) · §13 (Events · deferred) · §15 (Execution · post-freeze)**

---

## 1 · Commit hashes (newest first)

```
a17dbe1  feat(slice-beta): canonical Strategy Passport detail view (§10, §4)     ← slice β
007a8a5  docs(slice-alpha): HANDOVER updated for Slice α close-out
7aff84a  feat(slice-alpha): workspace context thread + canonical SignalState
1bbfc49  docs(architecture): v1.2 canonical · Factory operational states
```

Slice β is the single commit `a17dbe1` on top of slice-α. After extraction:

```bash
tar -xzf strategy-factory-slice-beta.tar.gz
cd app
git log --oneline 007a8a5..HEAD   # exactly one commit (a17dbe1)
git push origin main
```

---

## 2 · Summary of Slice β

Frontend-additive only · **no new backend endpoints** · **no synthetic data** · Backend Feature Freeze v1.1.0-stage4 intact.

Rewrites `/c/strategies/:id` from the legacy fixture-driven D5 view into the canonical §10 tabbed live surface.

### 2.1 Route + tabs (§10.2)

```
/c/strategies/:id?tab=evidence    (default)
                  ?tab=lineage
                  ?tab=neighbours
                  ?tab=deployments
```

Tabs are URL-encoded (§5 rule 2: URL is truth). Sharing a link reproduces the view exactly.

### 2.2 Live surfaces per tab

| Tab | Live source | State |
|---|---|---|
| **Evidence** *(default)* | `GET /api/strategies/{id}` | `LIVE` when payload returned; `DEFERRED` chip on the evidence-bundle sub-panel (§4.2 `backtests` collection is post-freeze). |
| **Lineage** | `strategy.status` mapped onto the §4.1 state ladder | Current stage highlighted with gold accent. State-transitions log panel: `DEFERRED` (Timeline shim ships in Slice γ · §13). |
| **Neighbours** | `POST /api/knowledge/nearest` (auto-run on first tab entry, using the strategy's own `name + description` as query text, filtered by `pair` + `timeframe`) | `LIVE` chip on the panel with `N / total corpus` counter. Empty state cites the KB compatibility review. |
| **Deployments** | (§15 Execution workspace is post-freeze) | `DEFERRED` chip with rationale citing §15 isolation policy. |

### 2.3 Governance bar (§10.3 promotion boundary)

The bar sits between the identity block and the tab bar. It:
- Cites §10.3 in-line: "Only this surface can transition the strategy state".
- Renders a **primary `PROMOTE` button** labelled with the exact §4 next-state transition for the current status (`Promote to Backtested`, `Promote to Champion`, `Deploy to Paper`, `Retire strategy`, `Reinstate as draft`).
- The button is **disabled and labelled `DEFERRED`** with a tooltip citing §12 · Slice γ. Once the Approvals modal ships, wiring it up is a one-liner.

### 2.4 Identity block

- Name (h1) + description
- State chip driven by the §4.1 ladder — accent colour matches the stage (draft=blue, backtested=advisory, champion=gold, deployed=green, retired=neutral)
- Tag chips
- `SYMBOL · TIMEFRAME` right-aligned
- `UPDATED · ISO timestamp`

### 2.5 Provenance + Guardrails (§10.1)

Two side-by-side panels inside the Evidence tab:
- **Provenance** — strategy_id, origin (Lab/KB/Live inferred from tags+description), created_by, created timestamp, framework version.
- **Guardrails** — learning-only chip, deploy-eligible chip, framework version, two-person-rule status pointing to §12/Slice γ.

### 2.6 Error path

A 404 on `/api/strategies/{id}` renders a dedicated interstitial with the `ERROR` liveness chip and a CTA back to Strategy Passports list. No white screen, no crash, no fixture fallback.

### 2.7 Workspace context wiring (§9)

Landing on `/c/strategies/:id` binds `strategy = id` into the workspace context. Pipeline row highlighting and other context-aware surfaces light up automatically.

---

## 3 · Files changed (1 file · +655 / −246 lines)

```
MOD  frontend/src/os/surfaces/StrategyPassport.jsx      (canonical §10 rewrite)
```

The route registration (`AppRouter.jsx`) and rail entry (`navigation.js`) were already in place from Sprint 1/2 — no changes required. `StrategyPassport.stories.jsx` remains untouched (fixture stories still compile; the alias `LivenessBadge` is honoured everywhere).

---

## 4 · Verification results

### 4.1 Build & lint

| Check | Result |
|---|---|
| `yarn build` | ✅ **PASS** — Compiled successfully · 22.4s · `main.js` 224.29 kB gz · `main.css` 989 B |
| `yarn lint:testids` | ✅ **PASS** — every interactive element in `src/os` has a `data-testid` |
| ESLint on `StrategyPassport.jsx` | ✅ **PASS** |

### 4.2 E2E preview smoke (real backend, admin auth)

Seeded strategy `75056283b8514aca · Passport probe · XAUUSD·H4 · status=draft` (deleted after test).

- **Evidence tab** — `● LIVE` badge · state chip `● DRAFT` · four metric tiles (`DRAFT · XAUUSD · H4 · 2 tags`) · Provenance panel filled (strategy_id, origin=`live · /api/strategies`, created_by, framework `v1.1.0-stage4`) · Guardrails (`NOT SET · NOT ELIGIBLE · v1.1.0-stage4 · REQUIRED · §12 (SLICE Γ)`) · Evidence-bundle sub-panel `● DEFERRED`.
- **Lineage tab** — Stage 1 (`Draft`) marked `CURRENT` with gold accent border; stages 2-5 rendered but dimmed. State-transitions panel `● DEFERRED` with a `Latest known transition` row from `strategy.updated_at`.
- **Neighbours tab** — `POST /api/knowledge/nearest` auto-fired with the strategy's name+description; corpus `0 / 0`; empty-state panel `● LIVE` (endpoint responded 200) with rich copy citing the KB compatibility review.
- **Deployments tab** — `● DEFERRED` with §15 rationale.
- **Governance bar** — `PROMOTE TO BACKTESTED` CTA disabled, `● DEFERRED` badge visible.
- **Workspace context (§9)** — the header chip shows `CONTEXT · SID 75056283…` immediately on landing, without user action.

### 4.3 Backward compatibility

- Existing `/c/strategies/:id` deep-links from Pipeline continue to work.
- Legacy stories file (`StrategyPassport.stories.jsx`) still compiles — the `SignalStateBadge`/`LivenessBadge` alias keeps every previous caller compiling.
- No import-path churn was forced on any unrelated file.

---

## 5 · Backend Feature Freeze v1.1.0-stage4 · INTACT

- **Zero** backend files modified.
- `/api/version` still reports `1.1.0-stage4` · commit `20af3df`.
- `docs/ARCHITECTURE.md` unchanged (canonical, frozen per §24.1).
- All promotion / mutation surfaces are `DEFERRED` chips; nothing writes to state outside the two existing endpoints (`POST /api/strategies` and `DELETE /api/strategies/{id}`) — and Slice β doesn't call either.

---

## 6 · Architecture citations

Every construct in Slice β cites the canonical architecture:

- Route + four canonical tabs → **§10.2**
- Passport composed of identity + provenance + evidence + lineage + guardrails + neighbours + deployments → **§10.1**
- Only-promotion-surface property → **§10.3**
- State ladder (draft → backtested → champion → deployed → retired) → **§4.1**
- Immutable artefacts per state (backtests reference in evidence bundle) → **§4.2**
- Workspace context binding on route entry → **§9**
- Approvals CTA labelled and disabled → **§12** (Slice γ)
- Timeline transition history deferred → **§13** (Slice γ)
- Deployments deferred to Execution workspace → **§15**
- Every liveness chip uses the six-state primitive → **§7**

Change-trigger policy (**§24.1**) was **not** invoked. No architectural revision required.

---

## 7 · Known issues & remaining work

- Every deferred sub-panel is labelled with the exact next slice / architecture section it will be delivered from — no silent gaps.
- Next up: **Slice γ · Approvals modal + Timeline event shim** (§12, §13). Once shipped, the promotion CTA on the Passport becomes live (one wire), and the Lineage tab's state-transitions list gets its data source.
- Historical KB import continues to be **DEFERRED** per your directive.

---

## 8 · Test credentials

- Admin: `admin@coinnike.com` / `admin123` (role from `/api/auth/me`: `admin`)
- Fixture operator: `operator@coinnike.com` / `prototype123`

---

_End of handover._

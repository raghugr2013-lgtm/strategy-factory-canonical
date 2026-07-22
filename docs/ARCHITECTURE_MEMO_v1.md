# Strategy Factory — Architecture Memo v1.1

_Version · v1.1 · draft for review_
_Author · Main Agent (E1)_
_Date · 2026-07-22_
_Status · under review — **no code changes** until this memo is signed off_
_Scope · long-term architectural shape of the AI Strategy Factory as a coherent product_

> **Objective.** Validate that the product architecture will scale before we continue implementation. Not a UI redesign. Not a spec. A north-star document that every future slice can be measured against.

### Revision log

- **v1.1** (this revision) — added §18 AI Factory Services Architecture, §19 Factory Event Flow, §20 Autonomy Boundaries, §21 Roadmap Alignment. Renumbered the tail. Broadens the memo from "frontend IA" to a factory-wide architectural blueprint.
- **v1.0** — original 17-section memo covering Operator OS + Engineering Workspace information architecture, personas, primitives, patterns, execution workspace, portfolio placement, factory lifecycle, and simplification recommendations.

---

## 0 · What we are building

The Strategy Factory is **not** a "trading dashboard". It is an **operator-driven AI factory** whose job is to turn raw market data into deployable, monitored, deprecable trading strategies — with a paper trail for every promotion, demotion, and money-touching action.

Three verbs describe everything the product does:
- **Compose** — turn intent (natural language, sweep parameters, KB matches) into a candidate.
- **Evidence** — earn or fail trust via deterministic, replayable checks.
- **Deploy** — attach money (paper first, then live) and never lose sight of what changed.

Everything else is scaffolding.

---

## 1 · Operator OS information architecture

### 1.1 Definition

**Operator OS** is the top-level shell the human sits inside. It is *not* a product mode ("operator vs engineer"). It is the single, always-on interface. What differs is *which surfaces are elevated*, *which are role-gated*, and *which risky actions require approval*.

### 1.2 Three-column mental model

The OS is organised in three permanent regions, always visible, never rearranged by the user:

| Region | Purpose | Analogy |
|---|---|---|
| **Left rail** | Navigation across surface groups (Mission Control · Engineering · Admin · [future] Execution) | Finder sidebar |
| **Main canvas** | The current surface — one at a time, no MDI, no tabs | Editor window |
| **Right context strip** *(future)* | Workspace context, freshness, recent activity, agent chat | Inspector |

The right strip is deliberately deferred until Theme A (Workspace context thread) lands.

### 1.3 Nav groups (long-term)

```
MISSION CONTROL          — operator-facing situational awareness
    Command                 · daily driver (approvals, alerts, kill switch)
    Strategy Passports      · deployable/deployed strategies as first-class objects
    Timeline                · immutable audit ledger
    Research                · natural-language questions against the corpus
    Cycles                  · optimization cycles + outcomes (post-freeze)

ENGINEERING              — engineer-facing capability map
    Market Data             · which venues we hear from
    Coverage                · which (symbol × timeframe × window) tuples we can trust
    Datasets                · shape/health of persisted raw data
    Strategy Lab            · authoring
    Strategy Pipeline       · lineage (drafts → deployed)
    Optimization            · sweep queues + cycle history (post-freeze launcher)
    Validation              · evidence ledger
    Portfolio               · portfolio-level composition + limits
    Prop Firms              · firm-specific rulebooks + certifications (post-freeze)
    Deployments             · running processes + kill topology (post-freeze)

EXECUTION [future]       — money-touching operations (post-freeze)
    Broker Connections
    Paper Trading
    Live Deployments
    Positions & Fills

ADMIN                    — role-gated
    Users
    Integrations
    Logs
    Settings
```

Everything above `EXECUTION` is safe under the current freeze. `EXECUTION` waits for the freeze to lift.

### 1.4 What must be true of every surface

- Has a canonical `SignalState` (see §7).
- Reads from a live endpoint OR is explicitly labelled `DEFERRED` with the endpoint it's waiting for.
- Renders the real interface even when empty. Placeholders are a bug.
- Has a `data-testid` on every interactive element.
- Fits the workspace context thread (see §9). If the operator has selected `XAUUSD · H4`, the surface reflects that filter.
- Has a "related routes" footer that names 2–3 adjacent surfaces by function, not by nav label.

### 1.5 What must never be true of any surface

- Blocks the operator with a full-screen modal for information they didn't request.
- Mixes real and synthetic data in the same view.
- Uses colour as the only signal (accessibility floor).
- Has a "coming soon" screen — either it's a surface or it's not in the rail.

---

## 2 · Engineering Workspace information architecture

Engineering is where the Factory earns its credibility. It exists to answer, in order:

1. **What data can the Factory trust?** → Market Data · Coverage · Datasets
2. **What candidates does the Factory have?** → Strategy Lab · Strategy Pipeline
3. **What has the Factory learned about them?** → Optimization · Validation
4. **What does the Factory intend to run?** → Portfolio · Prop Firms · Deployments

That ordering is the workspace. It is not accidental. Rail order matches it. Every operator learns the workspace by walking it left-to-right, top-to-bottom, once.

### 2.1 Engineering as a state machine

Each strategy transits the workspace as a sequence of stages, not a hierarchy of pages:

```
              Coverage OK ────────────────────────────────────────┐
                                                                    ▼
   ┌────────┐    ┌───────────┐    ┌──────────┐   ┌────────┐   ┌───────────┐
   │ COMPOSE│───▶│ OPTIMIZE  │───▶│ VALIDATE │──▶│ PROMOTE│──▶│  DEPLOY   │
   │  (Lab) │    │ (sweeps)  │    │(evidence)│   │(pipeline│  │(exec ws)  │
   └────────┘    └───────────┘    └──────────┘   │ stages) │  └───────────┘
                                                  └─────────┘
```

Every stage has: **inputs · one gate · one artefact**. Every gate is human-approved (Approvals pattern, §14) once we lift the freeze.

### 2.2 The five roles a surface can play

Reduce cognitive load by classifying surfaces before we build them:

| Role | Verb | Example surfaces |
|---|---|---|
| **Ledger** | *"what happened"* | Timeline · Validation · Passports |
| **Inventory** | *"what exists"* | Coverage · Datasets · Pipeline · Portfolio |
| **Composer** | *"what should exist"* | Strategy Lab · Optimization launcher |
| **Monitor** | *"what is happening right now"* | Command · Deployments · Paper Trading |
| **Registry** | *"who/what is allowed"* | Prop Firms · Users · Integrations |

A surface that plays two roles is a redesign candidate. Coverage is currently trying to be Inventory + Monitor (health block) — it works because the health block is small, but we should watch it.

---

## 3 · End-to-end operator workflow

The single workflow every operator lives inside, described as a linear day:

1. **Sign in.** Header shows role, auth-mode, freshness. Any active alert is a red pulse on `Command`.
2. **Open Command.** Approvals queue first. Kill switch second. Alerts third. Everything else is deferred until (1)–(3) are empty.
3. **Investigate.** Something needs a look — click through to Timeline, Passport, or Engineering surface. The workspace context (§9) picks up the strategy id.
4. **Compose.** Engineer opens Strategy Lab, composes a draft, saves. Draft appears in Pipeline (Stage 1) *without* the operator having to navigate — a subtle toast confirms.
5. **Optimize** *(post-freeze)*. Launcher runs a sweep, sends cycle to Optimization. Result becomes a Passport candidate.
6. **Validate.** Evidence ledger updates. Guardrail chips clear or block.
7. **Approve.** Approvals modal. Two-person rule for anything touching money.
8. **Promote.** Pipeline stage transitions. Timeline records the who/when/what.
9. **Deploy** *(post-freeze)*. Execution workspace mounts the strategy on a broker connection.
10. **Monitor.** Command surfaces live cycle events. Passport reflects performance in near-real-time.
11. **Deprecate.** Every promotion has a matching retire path. Same pattern.

The workflow is a loop, not a funnel. Deprecated strategies inform the next composition.

---

## 4 · End-to-end strategy lifecycle

The strategy is the atomic unit of the Factory. It has a **lineage** that survives every stage transition.

### 4.1 States

```
draft ─▶ backtested ─▶ champion ─▶ deployed ─▶ retired
   │          │            │           │
   └── failed_validation ──┴─── revoked ┘
```

- **draft** — persisted by Strategy Lab. Learning only. No deploy eligibility.
- **backtested** — has at least one deterministic replay result attached.
- **champion** — has earned membership in a canonical family (KB) OR passes the current-framework Passport gate. This is the *only* state where "canonical hash + evidence bundle" is complete.
- **deployed** — attached to a broker connection (paper or live). Money is at risk *if and only if* the connection is `live`.
- **retired** — no longer eligible for deploy. May still be studied.

Two failure states short-circuit the ladder: `failed_validation` (evidence rejected) and `revoked` (deploy privileges withdrawn — human decision).

### 4.2 Immutable artefacts per state

| State | Artefact | Stored where |
|---|---|---|
| draft | CNL text · pair · timeframe · style | `strategies` |
| backtested | replay hash + p&l series | `backtests` (future) |
| champion | canonical hash + KB family reference | `strategy_kb_champions` |
| deployed | deployment envelope · connection ref | `deployments` (future) |
| retired | reason · attester · timestamp | `strategies` (append to history) |

Every state transition writes an event (§13). No transition is silent.

### 4.3 Historical KB compatibility (deferred)

The historical corpus in `strategy_knowledge_base` predates the state machine and is `learning_only=true` by contract. Migration into the canonical pipeline requires:
- A per-family compatibility check against the current CNL schema.
- A framework-version tag (`framework_version="v1.1.0-stage4"` at minimum).
- A one-way promotion path: KB champion → `strategies` draft (never the reverse).
- A guardrail that prevents accidental deploy-eligibility.

**Recommendation:** do not import until Passport architecture (§10) is in place. Passport IS the promotion boundary.

---

## 5 · Navigation philosophy

Five hard rules. If a rule is broken, the surface is wrong.

1. **One surface at a time.** No tabs, no split panes, no MDI. Cognitive load compounds; the OS shouldn't.
2. **URL is truth.** Every user-visible state — surface, pair, timeframe, strategy id, filter — is in the URL. Sharing a link reproduces the view exactly.
3. **Left rail never moves.** Groups can be collapsed, entries can be role-gated, but position is stable. Operators build muscle memory in weeks.
4. **Related routes over dropdowns.** Every surface footer has 2–3 pills pointing at adjacent surfaces by function. This replaces the temptation to build "index" pages.
5. **Command Palette for everything else.** Long-tail navigation is a keyboard problem, not a chrome problem. See §11.

The absent sixth rule: **no breadcrumb trails**. Breadcrumbs suggest hierarchy where the workspace is actually a state machine. Related-routes pills carry that job better.

---

## 6 · User personas

The three real personas the Factory serves:

### 6.1 Operator (day-to-day)

- **Job:** keep the Factory safe. Approve, halt, investigate.
- **Where they live:** Mission Control (95%). Occasionally opens Passport or Pipeline.
- **Tolerance:** low for noise; expects a calm surface.
- **Superpower:** kill switch, approvals, incident triage.
- **Role in RBAC:** `operator` (default).

### 6.2 Engineer (weekly)

- **Job:** grow the Factory's capability. Compose, sweep, validate.
- **Where they live:** Engineering Workspace.
- **Tolerance:** high for detail; expects deep artefacts.
- **Superpower:** Strategy Lab, Optimization, KB query.
- **Role in RBAC:** `researcher` or `developer`.

### 6.3 Administrator (rare)

- **Job:** keep the Factory well-configured. Onboard operators, rotate secrets, review logs.
- **Where they live:** Admin group + occasional Command deep-dives.
- **Tolerance:** irrelevant — administrator sessions are short and audited.
- **Superpower:** role assignment, integration secrets, log egress.
- **Role in RBAC:** `admin`.

**Deliberately absent personas:**
- "Trader" — not a persona. The Factory is not a discretionary trading tool.
- "Researcher scientist" — collapsed into Engineer for v1.
- "Compliance" — served by Timeline read-only role in v2.

### 6.4 Persona × Surface elevation matrix

```
                Operator   Engineer   Administrator
Mission Ctrl    primary    secondary  secondary
Engineering     secondary  primary    tertiary
Execution*      primary    tertiary   tertiary
Admin           hidden     hidden     primary
```

The rail *shows* everything each role can access. **Elevation** decides which surface loads at sign-in.

---

## 7 · Canonical SignalState vocabulary

Every "how live / how trusted is this?" indicator across the product uses **one** taxonomy. Six states, no more.

| State | Meaning | Colour token | Example |
|---|---|---|---|
| `LIVE` | Endpoint responded, payload is meaningful, data is current | `sig-ok` (green) | Coverage with 87 symbols and CTS health 92 |
| `PARTIAL` | Endpoint responded 200, but data is sparse or preliminary | `sig-warn` (amber) | Datasets on a fresh install |
| `DEFERRED` | The capability exists in the roadmap but its endpoint is not yet live under the current freeze | `sig-advisory` (blue-grey) | Optimization launcher |
| `GATED` | Endpoint exists but caller lacks the role, or a feature flag is off | `sig-dormant` (neutral) | `/api/admin/*` for a non-admin |
| `EMPTY` | Endpoint responded 200 with an empty collection AND the collection is expected to fill within normal operation | `sig-dormant` | Champion families before KB import |
| `ERROR` | Network failure, 5xx, or unexpected schema | `sig-crit` (red) | Coverage on backend down |

**Chip anatomy** (identical everywhere):

```
[ • STATE_LABEL ]     title = short human reason
```

**Rules:**
- A surface has one **page-level** SignalState (worst of its panels).
- Each panel has one **panel-level** SignalState.
- Metric tiles do *not* have SignalStates; they use the tone accents.
- Every non-LIVE state must carry a `reason` string. No naked amber chips.

**Renaming plan:** current `PARTIAL LIVE` → `PARTIAL`. Current `GATED` unchanged. New: `DEFERRED`, `EMPTY`. Existing `LIVE`/`ERROR` unchanged.

---

## 8 · Global freshness model

Today: each surface has its own `Refresh` button and `Updated · HH:MM Z` timestamp. The operator cannot tell across surfaces whether they're comparing stale numbers.

**Target model:**

1. **One tick loop** in the shell (30s default; configurable per surface).
2. **Header freshness pill** — always visible, shows the age of the *oldest* surface currently mounted and a global manual `Refresh all` button.
3. **Per-surface refresh** remains, but is opt-in for surfaces with expensive payloads.
4. **Auto-refresh on window focus** after the shell has been backgrounded > 60s.
5. **Freshness tokens:**
   - Fresh (< 60s): no chip.
   - Stale (60s – 5m): amber "STALE · Nm".
   - Very stale (> 5m): red "VERY STALE".

**Not a WebSocket.** WebSocket is a separate concern (§14).

**Why this scales:** as Portfolio + Deployments arrive, "are we looking at last-minute data?" becomes a safety question, not a nicety.

---

## 9 · Workspace context model

The single largest UX unlock we're not yet using.

### 9.1 Definition

A **workspace context** is a small, URL-encoded state that every surface honours as an *implicit filter*.

```
context = {
  pair:      "XAUUSD",       // optional
  timeframe: "H4",           // optional
  strategy:  "84d32cc1...",  // optional
  cycle:     null,           // future: optimization cycle id
}
```

Encoded as URL query, e.g. `/c/engineering/coverage?pair=XAUUSD&tf=H4`.

### 9.2 Behaviour

- Strategy Lab's pair/timeframe selectors *initialise from* and *write to* the context.
- Coverage, Datasets, Market Data auto-filter by the context.
- Pipeline highlights the row matching `strategy` (if any) and scrolls into view.
- Passport view IS a full context: opening a Passport sets all four fields.
- Command Palette displays context in its footer.

### 9.3 Where context lives

- **Source of truth:** URL query string (react-router).
- **Cache:** `useWorkspaceContext()` hook backed by a zustand store — read-only mirror.
- **Reset:** header "×" chip clears the context (and the URL) with one click.

### 9.4 What context is NOT

- Not authentication state (that lives in `authStore`).
- Not filter state internal to a surface (e.g. Pipeline's active stage).
- Not persisted across sessions (sessionStorage only). Every day starts fresh.

**Why this scales:** every future surface inherits filter behaviour for free. Portfolio, Cycles, Deployments — all just read the context.

---

## 10 · Strategy Passport architecture

The Passport is the **primary noun** of the AI Factory. Every other surface is a lens onto Passports.

### 10.1 Passport = strategy + evidence + lineage

A Passport is a *view*, not a table. It composes:

- **Identity** — id, name, canonical hash (if any), current state, symbol, timeframe.
- **Provenance** — origin (Strategy Lab / KB import / Optimization cycle), attester, timestamp.
- **Evidence bundle** — the artefacts required for the current state (see §4.2).
- **Lineage** — the ordered list of state transitions with attesters.
- **Guardrails** — `learning_only`, `deploy_eligible`, `framework_version`.
- **Neighbours** — top-k nearest historical strategies from the KB.
- **Deployments** *(post-freeze)* — active broker connections carrying this strategy.

### 10.2 Passport route

```
/c/strategies/:id
    ?tab=evidence  (default)  · tab=lineage · tab=neighbours · tab=deployments
```

Tabs are the only place the OS allows tabs — because a Passport is *one object*, not a collection of surfaces.

### 10.3 Passport promotion boundary

**The Passport is the only surface that can promote a strategy.** Every other surface can *view* state; only the Passport (via the Approvals pattern) can *change* it. This is a structural safety property.

### 10.4 KB import strategy

- KB champion → creates a Passport with state `champion` **and** `learning_only=true`.
- Guardrail chip is permanent.
- No `deployed` transition is allowed until a fresh Passport gate under the current framework version passes.
- Timeline records the import as a distinct actor (`KB_IMPORT`).

---

## 11 · Command Palette vision

Not a search box. The keyboard-driven **command surface** for power users.

### 11.1 Three sections

```
1. JUMP TO SURFACE          — every rail entry, aliased
2. JUMP TO OBJECT           — recent Passports, recent cycles, recent gaps
3. RUN COMMAND              — refresh all · sign out · toggle theme · [future] approve · [future] kill
```

### 11.2 Behaviour

- Bound to `⌘K` / `Ctrl+K`.
- Overlays canvas without blocking rail.
- Escape closes without state change.
- Fuzzy match with recency + role weighting.
- Every entry has a `data-testid` and a keyboard shortcut hint.

### 11.3 What it must never do

- Execute money-touching actions without going through the Approvals pattern (§14).
- Show suggestions the operator cannot access.
- Persist history in localStorage (privacy floor).

---

## 12 · Approvals / confirmation pattern

A single, systemic pattern for every risky action. Not per-surface confirm dialogs.

### 12.1 Anatomy

```
┌────────────────────────────────────────┐
│  APPROVE · promote to champion         │
│  Strategy · XAUUSD H4 Momentum · 84d3… │
│  Actor    · admin@coinnike.com         │
│  Reason   · [required field]           │
│                                         │
│  This will:                             │
│   • transition state draft → champion   │
│   • write timeline event               │
│   • notify approvers                   │
│                                         │
│  [ CANCEL ]         [ CONFIRM ⌘⏎ ]      │
└────────────────────────────────────────┘
```

### 12.2 Rules

- Every mutation that changes state, deploys money, or grants privileges goes through the modal.
- Every approval writes a **timeline event** with actor, action, target, reason, timestamp, and (post-freeze) cryptographic attestation.
- Two-person rule *(post-freeze)*: money-touching actions require a second admin approval within N minutes.
- Cancel is default focus. Confirm requires `⌘⏎` (keyboard-first, thumb-off-mouse).

**Why now, under freeze:** the pattern is UX, not backend. Build it dark, wire it to the two mutations we already have (`POST /api/strategies`, delete strategy), and it's ready the day the freeze lifts.

---

## 13 · Event vocabulary

Every user-visible action is an **event** with a canonical name and a fixed shape. The event log is the ground truth for Timeline, alerts, and future notification.

### 13.1 Naming convention

```
<actor>_<object>_<verb>_[<qualifier>]
```

Examples:
- `operator_strategy_promoted_to_champion`
- `engineer_strategy_composed`
- `system_coverage_backfill_started`
- `admin_user_role_updated`
- `kb_family_imported`
- `walkthrough_started` · `walkthrough_completed` · `walkthrough_skipped` *(already implemented)*

### 13.2 Event shape

```json
{
  "event_id": "<uuid>",
  "event_name": "operator_strategy_promoted_to_champion",
  "actor": { "email": "…", "role": "…", "session_id": "…" },
  "object": { "type": "strategy", "id": "…", "hash": "…" },
  "context": { "pair": "…", "timeframe": "…", "cycle_id": null },
  "reason": "…",              // when human-authored
  "ts": "2026-07-22T…Z",
  "source": "operator-os",    // or 'system', 'kb-import', 'agent'
  "framework_version": "v1.1.0-stage4"
}
```

### 13.3 Where events live

- **Emit** — frontend calls a single `emitEvent()` shim; backend writes to `timeline_events`.
- **Read** — Timeline surface consumes filtered/paginated event stream.
- **Retain** — indefinite; timeline is compliance-relevant.

### 13.4 Constraints

- Event names are **immutable** once shipped. Rename → new name, not migration.
- No PII in `object` or `context`. Actor identity is separated so it can be redacted.
- No arbitrary payload. If new metadata is needed, a schema migration is required.

---

## 14 · Future WebSocket / live-update model

Freshness (§8) is a polling model. Live-update is a *push* model — used sparingly, for surfaces that need sub-second signal.

### 14.1 What deserves a WebSocket

- `Command` — active alerts, live cycle events, kill-switch state.
- `Deployments` *(post-freeze)* — running-process status, fills.
- `Optimization` *(post-freeze)* — sweep progress.
- `Timeline` — new events appended live.

### 14.2 What does not

- Coverage, Datasets, Pipeline, Passports (state transitions push, not the whole object).
- Any surface that hasn't proven it needs sub-second freshness.

### 14.3 Contract

- One WSS endpoint: `/ws/stream`.
- Server sends **event envelopes** identical in shape to §13.2, prefixed with a stream marker.
- Client filters by `actor`, `object.type`, `event_name`.
- Ping/pong every 20s; reconnect with jittered backoff.

### 14.4 Frontend model

- One `wsClient` singleton owns the socket.
- Zustand slices subscribe to filtered streams; components re-render.
- No component talks to the socket directly.

**Why now, in a memo:** the event vocabulary (§13) is designed so it can serve *both* the polling surfaces and the WSS future without a rewrite.

---

## 15 · Execution workspace (post-freeze)

The money-touching group. Deliberately isolated from Engineering to prevent workflow bleed.

### 15.1 Surfaces

| Surface | Answers |
|---|---|
| **Broker Connections** | Which brokers are known · credentials · handshake status |
| **Paper Trading** | Which strategies are paper-deployed · fills · p&l |
| **Live Deployments** | Which strategies are live-deployed · fills · risk envelope |
| **Positions & Fills** | Point-in-time position ledger across all connections |

### 15.2 Rules

- Every entry into Execution shows an **elevated header banner**: "You are viewing money-touching operations."
- Every action in Execution triggers the Approvals pattern (§12), no exceptions.
- The Kill Switch is available *from every surface in this group* (and from Command).
- Deployments require an active Passport in state `champion` with a green Passport gate.
- Paper Trading is the mandatory intermediate state — no strategy jumps directly from champion to live.

### 15.3 What Execution is not

- Not a broker terminal. There is no discretionary "buy 1 lot" button. Ever.
- Not a P&L dashboard for humans to eyeball — Command surfaces alerts; Portfolio owns aggregate view.

---

## 16 · Portfolio placement

Portfolio is currently under Engineering. That's provisional.

### 16.1 Two candidate placements

| Placement | Argument |
|---|---|
| **Engineering** | Portfolio is *composition* — deciding which strategies work together. That's engineering. |
| **Execution** | Portfolio is *risk allocation* — deciding how much money each strategy gets. That's money. |

### 16.2 Recommendation

Split it. Two surfaces:

- **`Engineering / Portfolio Composition`** — which strategies are compatible (correlation, drawdown overlap, style diversity). Read-only under freeze.
- **`Execution / Portfolio Allocation`** — how much capital each deployed strategy runs. Post-freeze.

The current placeholder becomes Composition. Allocation waits.

---

## 17 · AI Factory lifecycle — from Market Data to Live Deployment

The single diagram every operator should have memorised:

```
                  ┌─────────────────────┐
                  │  MARKET DATA        │  venues we hear from
                  └─────────┬───────────┘
                            │
                  ┌─────────▼───────────┐
                  │  COVERAGE           │  what we can trust
                  └─────────┬───────────┘
                            │
                  ┌─────────▼───────────┐
                  │  DATASETS           │  what we've persisted
                  └─────────┬───────────┘
                            │
                            │ (data foundation complete)
                            │
                  ┌─────────▼───────────┐
                  │  STRATEGY LAB       │  compose a candidate
                  └─────────┬───────────┘
                            │  status=draft
                  ┌─────────▼───────────┐
                  │  OPTIMIZATION       │  sweep the parameter space
                  └─────────┬───────────┘
                            │  status=backtested
                  ┌─────────▼───────────┐
                  │  VALIDATION         │  earn the evidence bundle
                  └─────────┬───────────┘
                            │  passes Passport gate
                  ┌─────────▼───────────┐
                  │  STRATEGY PASSPORT  │  the deployable object
                  └─────────┬───────────┘
                            │  approve · promote
                  ┌─────────▼───────────┐
                  │  PAPER TRADING      │  no-real-money soak
                  └─────────┬───────────┘
                            │  approve · promote
                  ┌─────────▼───────────┐
                  │  LIVE DEPLOYMENT    │  money at risk
                  └─────────┬───────────┘
                            │
                  ┌─────────▼───────────┐
                  │  MONITOR · COMMAND  │  alerts · kill · deprecate
                  └─────────────────────┘

Cross-cutting:
   TIMELINE       — everything writes here
   PORTFOLIO      — composition + allocation across all deployed
   PROP FIRMS     — rulebook attestations
   KB (learning)  — historical corpus, learning-only
   AGENT (v2)     — conversational front to any of the above
```

Every gate is a human approval. Every arrow is a timeline event. The KB feeds Strategy Lab (nearest neighbours) but never feeds Deployment directly.

---

## 18 · AI Factory services architecture

The Factory is composed of **autonomous services** — each with a single responsibility, an explicit contract, and a clear boundary. Some are already implemented; some are latent; some are post-freeze. The architecture is the same regardless.

### 18.1 Service catalogue

Fourteen services. Each row is deliberately small; contracts are what matter, not implementations.

| # | Service | Responsibility |
|---|---|---|
| S01 | **Ingestion**            | Pull raw ticks/bars from external venues; normalise timestamps and instrument names. |
| S02 | **Coverage**             | Compute and publish the "what we can trust" matrix (symbol × timeframe × window × tier). |
| S03 | **Storage**              | Persist canonical M1 rows, aggregated caches, and gap enumeration. |
| S04 | **Composition (Lab)**    | Turn CNL / sweep parameters / KB matches into deterministic draft candidates. |
| S05 | **Optimization Engine**  | Execute parameter sweeps; produce cycle records with reproducible seeds. |
| S06 | **Validation Engine**    | Run deterministic backtests; produce evidence bundles with replay hashes. |
| S07 | **Passport Registry**    | Compute canonical hashes; evaluate promotion gates; own lineage transitions. |
| S08 | **Knowledge Base (KB)**  | Store historical strategies; expose nearest-neighbour and family aggregations; learning-only. |
| S09 | **Portfolio Composer**   | Score strategy compatibility (correlation, drawdown overlap, style diversity). |
| S10 | **Risk Governor**        | Own position-sizing envelopes, drawdown limits, kill-switch state, prop-firm rules. |
| S11 | **Execution Gateway**    | Adapters to broker APIs (paper first, then live); route orders; report fills. |
| S12 | **Monitor / Alerting**   | Aggregate signal from all services; raise alerts; expose freshness. |
| S13 | **Timeline (event bus)** | Append-only event log; source of truth for audit + replay. |
| S14 | **Meta-Learning**        | Long-loop retrospection on deployed outcomes; drift detection; feed recommendations back to Composition. |

Two future services carried on this map but deliberately not counted in v1:
- **Agent** (v2) — conversational front-end over any service. Requires a stable event vocabulary before it is safe to build.
- **Attestor** (post-Passport-v2) — cryptographically signs promotion events. Non-repudiation.

### 18.2 Inputs / outputs per service

Every service exposes exactly two contracts: what it *consumes* and what it *produces*. If a proposed capability doesn't fit, it belongs in a new service.

| # | Service | Consumes | Produces (events · artefacts) |
|---|---|---|---|
| S01 | Ingestion         | venue websockets/REST · credentials | `market_data_tick_received` · raw rows to Storage |
| S02 | Coverage          | Storage rows · verification runs    | `coverage_tier_updated` · Coverage payload (already live: `GET /api/data/coverage`) |
| S03 | Storage           | Ingestion writes · cache aggregates | `dataset_row_written` · `gap_detected` · persisted canonical rows |
| S04 | Composition (Lab) | CNL text · pair · TF · style · KB neighbours | `strategy_composed` · draft strategy row (live today: `POST /api/strategies/generate` + `POST /api/strategies`) |
| S05 | Optimization      | Passport registry (candidates) · Coverage (data availability) · Risk envelope | `cycle_launched` · `cycle_progress` · `cycle_completed` · cycle record |
| S06 | Validation        | Cycle record · fresh replay data    | `evidence_bundle_generated` · `validation_verdict` · evidence artefact hash |
| S07 | Passport Registry | Strategy row · evidence bundle · human approval | `passport_created` · `passport_gate_evaluated` · `strategy_promoted` · `strategy_retired` · immutable Passport document |
| S08 | KB                | Historical corpus · CNL matcher     | `kb_nearest_returned` · `kb_family_imported` · KB view (live today: `GET /api/knowledge/*`) |
| S09 | Portfolio Composer| Passport registry (state=champion+) · fill history | `portfolio_recomposed` · composition report |
| S10 | Risk Governor     | Portfolio composition · live drawdowns · prop-firm rulebook | `risk_envelope_updated` · `kill_switch_engaged` · `risk_violation_detected` |
| S11 | Execution Gateway | Deployment intent · broker credentials · Risk envelope | `deployment_created` · `order_placed` · `fill_received` · `deployment_halted` |
| S12 | Monitor           | All event streams · freshness ticks | `alert_raised` · `alert_cleared` · aggregate health payload |
| S13 | Timeline          | Every emitted event                 | `timeline_appended` · queryable event stream |
| S14 | Meta-Learning     | Timeline · Portfolio outcomes · KB corpus | `retro_report_generated` · `drift_detected` · recommendation payload fed back to Composition |

### 18.3 Relationships — the service dependency graph

The graph is deliberately layered. Higher layers may depend on lower layers; the reverse is forbidden.

```
Layer 5  (LEARN)                 ┌────────────────────┐
                                  │   Meta-Learning    │ ◀── learns from every layer below
                                  └─────────┬──────────┘
Layer 4  (EXECUTE)                          │
                                            ▼
                     ┌──────────┐   ┌──────────────┐   ┌──────────────┐
                     │Portfolio │──▶│ Risk Governor│──▶│  Execution   │
                     │ Composer │   └──────────────┘   │   Gateway    │
                     └────┬─────┘                       └──────────────┘
Layer 3  (VALIDATE)       │
                          │
                     ┌────▼──────────┐
                     │   Passport    │
                     │   Registry    │
                     └───┬───┬───────┘
                         │   │
                         │   └────────────┐
                         ▼                ▼
                  ┌────────────┐   ┌─────────────┐
                  │ Validation │   │Optimization │
                  │   Engine   │   │   Engine    │
                  └─────┬──────┘   └──────┬──────┘
Layer 2  (COMPOSE)      │                 │
                        └────────┬────────┘
                                 ▼
                         ┌──────────────┐         ┌──────────────┐
                         │ Composition  │ ◀───────│   KB (S08)   │
                         │    (Lab)     │         └──────────────┘
                         └──────┬───────┘
Layer 1  (DATA)                 │
                                │
                         ┌──────▼────────┐
                         │   Coverage    │
                         └──────┬────────┘
                                │
                         ┌──────▼────────┐        ┌──────────────┐
                         │    Storage    │ ◀──────│  Ingestion   │
                         └───────────────┘        └──────────────┘

Cross-cutting:
   Timeline (S13)   — every service emits into it
   Monitor  (S12)   — subscribes to every service
```

**Invariants** (violate any of these, the architecture is broken):

1. **Ingestion never talks to Composition.** Data must flow through Coverage first — no undocumented shortcut symbols.
2. **KB never talks to Execution.** Historical corpus is `learning_only=true` forever; it can only reach live deployment via a fresh Passport gate.
3. **Composition never talks to Execution.** Draft candidates are not deployable — Passport Registry is the only bridge.
4. **Risk Governor is on the critical path for every order.** No Execution call bypasses it, ever.
5. **Meta-Learning has no write access downstream.** It emits `recommendation payload` events; Composition decides whether to act on them.
6. **Timeline is append-only.** No service ever rewrites an event.

### 18.4 Interface conventions

Every service exposes:
- A **read contract** (HTTP GET / WSS subscription) for its outputs.
- A **write contract** (HTTP POST) for its explicit intake — **plus** an implicit intake via event subscriptions.
- A **health endpoint** feeding Monitor.
- An **event emitter** that writes to Timeline synchronously with the persisted state change.

No service exposes raw database rows. Every payload is a versioned DTO owned by the service.

---

## 19 · Factory event flow

The Factory as a set of connected event streams. This is §17 (lifecycle) redrawn from the *events* perspective — the same story a Timeline reader would reconstruct.

### 19.1 The trunk flow (data → deployment)

```
      venues                            operator          admin
        │                                  │                │
        ▼                                  ▼                ▼
  [S01 Ingestion]                    [S04 Lab]        [Approvals]
        │                                  │                │
        │ market_data_tick_received       │strategy_composed│promotion_requested
        ▼                                  ▼                │
  [S03 Storage] ─── gap_detected ──▶ [S07 Passport]         │
        │                                  │                │
        │ dataset_row_written              │passport_created│
        ▼                                  ▼                │
  [S02 Coverage] ─── coverage_tier_updated ─────────────┐   │
                                            │           │   │
                                            ▼           ▼   ▼
                                     [S05 Optimization] [S06 Validation]
                                            │                 │
                        cycle_completed◀────┘                 │
                                            │  evidence_bundle_generated
                                            ▼                 │
                                     [S07 Passport gate evaluated]
                                            │
                                strategy_promoted (state → champion)
                                            │
                                            ▼
                                     [S09 Portfolio Composer]
                                            │
                                     portfolio_recomposed
                                            │
                                            ▼
                                     [S10 Risk Governor]
                                            │
                                     risk_envelope_updated
                                            │
                                            ▼
                                     [S11 Execution Gateway]
                                            │  (paper → live gated by human)
                                     deployment_created
                                            │
                                            ▼
                                        fills, p&l
                                            │
                                            ▼
                                     [S12 Monitor] ─── alert_raised (if breach)
                                            │
                                            ▼
                                       [S13 Timeline]  ◀── every event above
                                            │
                                            ▼
                                     [S14 Meta-Learning]
                                            │
                                     retro_report_generated · drift_detected
                                            │
                                            └──────────▶ back to [S04 Lab]
                                                         (recommendations only)
```

### 19.2 Read-side event flows

The trunk flow is write-side. Read-side consumers subscribe to filtered streams:

- **Command surface** subscribes to `alert_raised`, `alert_cleared`, `kill_switch_engaged`, `promotion_requested`.
- **Timeline surface** subscribes to `timeline_appended` (all events).
- **Passport surface** subscribes to events matching a target `object.id`.
- **Meta-Learning** subscribes to the whole event stream (batch, not live).
- **Monitor** subscribes to every service's health emitter.

### 19.3 Event categories

Every event falls into one of six categories (used for filtering, colour-coding, and retention policy):

| Category | Example | Retention |
|---|---|---|
| **Data**       | `market_data_tick_received`, `dataset_row_written` | 90d |
| **Composition**| `strategy_composed`, `kb_nearest_returned` | indefinite |
| **Evaluation** | `cycle_completed`, `evidence_bundle_generated`, `passport_gate_evaluated` | indefinite |
| **Governance** | `promotion_requested`, `strategy_promoted`, `strategy_retired`, `risk_envelope_updated` | indefinite (compliance) |
| **Execution**  | `deployment_created`, `order_placed`, `fill_received`, `kill_switch_engaged` | indefinite (compliance) |
| **Learning**   | `retro_report_generated`, `drift_detected` | indefinite |

Data events are voluminous and can be aged out. Everything above that line is compliance-relevant and retained indefinitely.

### 19.4 Loop-back edges (deliberately explicit)

Three edges make the Factory a *learning* system rather than a pipeline:

1. **Coverage → Validation** — data quality changes can invalidate previously-valid evidence; validation must re-run when the tier degrades.
2. **Meta-Learning → Composition** — retro reports surface as recommendation payloads inside Strategy Lab (e.g. "avoid mean-reversion on XAUUSD in the last N days · drift detected").
3. **Execution → Portfolio Composer** — live fills and drawdowns reshape composition scores; composition is not static.

Each loop-back is *event-driven*, not RPC. No service polls another; they subscribe to Timeline.

---

## 20 · Autonomy boundaries

The single most important governance property of the Factory: **who is allowed to decide what, and how does that widen over time?**

### 20.1 Three-tier taxonomy

Every action in the Factory belongs to exactly one tier:

| Tier | Definition | Who acts | Audit path |
|---|---|---|---|
| **H · Human decision**        | A human must click Approve. No automation of the decision itself. | Operator or Admin | Timeline records actor, reason, timestamp |
| **R · Recommendation-only**   | Automation surfaces a proposal. A human reviews and clicks accept/reject. | Automation proposes; human accepts | Timeline records both the proposal and the accept/reject |
| **A · Fully autonomous**      | Happens without human intervention, within a pre-approved envelope. Human retains veto/kill. | Automation | Timeline records the autonomous action + envelope reference |

Every autonomous action must have a **veto path** (kill switch or targeted revoke) reachable within 3 seconds from any surface.

### 20.2 Action inventory with initial tier assignments

| Action | v1 tier | Notes |
|---|---|---|
| Ingest data from a venue                       | A | Well-bounded, safe. |
| Persist a normalised row                       | A | Deterministic. |
| Detect a data gap                              | A | Deterministic. |
| Backfill a gap                                 | R | Recommendation initially — bandwidth cost + provider throttling. |
| Compose a strategy draft                       | H | The engineer types it (or approves a Meta-Learning suggestion). |
| Save a draft                                   | H | Explicit save button. |
| Launch an optimization cycle                   | H | Engineer-initiated. Cost + noise. |
| Run a validation replay                        | R | Recommendation with one-click confirm — cheap, deterministic. |
| Compute a canonical hash                       | A | Pure function. |
| Evaluate a Passport gate                       | A | Deterministic given inputs; gates are declarative. |
| Promote to `champion`                          | H | Human decision, Approvals modal. |
| Promote to paper deployment                    | H | Human decision, Approvals modal. |
| Promote to live deployment                     | H | Human decision, Approvals modal · two-person rule. |
| Retire a strategy                              | H | Human decision. |
| Route an order to a broker                     | A | Only inside an approved deployment envelope. |
| Auto-halt on drawdown breach                   | A | Risk Governor autonomous. |
| Auto-halt on connection loss                   | A | Risk Governor autonomous. |
| Adjust position sizing within envelope         | A | Bounded by Risk Governor. |
| Adjust position sizing beyond envelope         | H | Human decision. |
| Emit a Meta-Learning recommendation            | A | Never mutates state — always surfaces. |
| Import a KB family into `strategies`           | H | Human decision, permanent `learning_only=true`. |
| Rotate an admin secret                         | H | Human decision. |

### 20.3 Roadmap evolution of autonomy

Autonomy widens **only** as evidence accumulates. Four phases:

**Phase α (LEARNING) — current freeze.**
- Everything Human. The Factory is under supervised training wheels.
- The only autonomous work is deterministic data plumbing (Ingestion, Storage, Coverage calculation, canonical hashing).
- **Objective:** build the trust vocabulary. Timeline, Passport, Approvals.

**Phase β (ASSISTED) — post-freeze, ~6 months.**
- Data operations remain autonomous.
- Validation runs become recommendation-only (one-click accept).
- Optimization cycles remain human-initiated.
- Deployment decisions remain human.
- **New:** Risk Governor gains autonomous kill authority (drawdown / connection breach).
- **Objective:** prove that recommendation-only reduces engineer toil without introducing risk.

**Phase γ (GUIDED AUTONOMY) — ~12–18 months.**
- Strategy composition graduates: Meta-Learning proposals surface as recommendations that a lightweight approval can accept and route to the Lab.
- Optimization cycles graduate: cadence-based (e.g. weekly) auto-launch under a pre-approved envelope; results still require human promotion.
- Deployment to *paper* graduates to recommendation-only (paper is bounded-risk).
- Live deployment remains Human (two-person rule).
- **New:** portfolio rebalancing becomes recommendation-only within Composition envelopes.

**Phase δ (SUPERVISED AUTONOMY) — long term.**
- Live deployment inside a strict envelope becomes Autonomous (with prominent kill).
- Portfolio rebalancing inside envelope becomes Autonomous.
- Retirement of underperforming strategies becomes Autonomous.
- Humans retain: envelope authorship, kill switch, retrospective review, and any action outside an envelope.

**Non-graduation guarantees.** Some actions never graduate above Human, by architectural policy:

- Envelope authorship (who can carry how much money).
- KB → live-deployment promotion.
- Admin actions (role changes, secret rotation, integration approval).
- Two-person-rule actions once written into policy.

### 20.4 Implementation implications for the OS

- Every action in the OS is tagged `H / R / A`.
- The Approvals modal (§12) is the H channel.
- The Command surface (Mission Control) is the R channel — it queues proposals for review.
- Autonomous actions (`A`) appear in Timeline with a `source=system` actor and an `envelope_id`.
- A **veto surface** is available from Command (and Command Palette): "revoke envelope · halt strategy · engage kill switch".

---

## 21 · Roadmap alignment · how the architecture supports each phase without redesign

The claim of this memo is that the architecture defined in §0–§20 already accommodates Phase α through Phase δ **without structural change**. Each phase is an *extension*, not a rewrite. This section maps that claim to concrete primitives.

### 21.1 Phase α (LEARNING · current)

Everything required is already defined:

- Layered service graph (§18.3): only Layers 1–2 are populated in the frozen backend. Layers 3–5 are latent.
- SignalState taxonomy (§7) already includes `DEFERRED` for capabilities that are architecturally accounted for but not yet available.
- Event vocabulary (§13) already emits walkthrough events; every future event follows the same shape.

**What the current frozen backend needs to support Phase α:** nothing new. It already does.

### 21.2 Phase β (ASSISTED · post-freeze)

Adds: Recommendation channel · autonomous Risk Governor kill · one-click validation.

Architectural primitives that make this drop-in:

- **Approvals modal** (§12) already differentiates "confirm" from "propose"; recommendation-only actions land in the same modal with pre-filled fields.
- **Autonomy tier tag** (§20.1) is attached to every action at design time; upgrading validation from H to R changes a tag, not a code path.
- **Risk Governor as its own service** (§18, S10) means autonomous kill authority lives in the correct place — no new coupling between broker gateway and UI.
- **Command surface** already has an alerts + approvals queue slot; recommendations feed the same queue.

**What we need to add:** the `RecommendationCard` primitive (one component). No architectural change.

### 21.3 Phase γ (GUIDED AUTONOMY)

Adds: Meta-Learning as a first-class producer · cadence-based optimization · paper-deployment recommendation.

Architectural primitives:

- **Meta-Learning is already S14** in the service catalogue — it consumes Timeline and produces recommendation events. No new subscription mechanism needed.
- **Envelope authorship as a Human-non-graduating action** (§20.3) means we do not have to add a new authorisation model; we extend the existing Approvals modal with envelope fields.
- **Cadence-based optimization** is a scheduler concern on Optimization Engine (S05). The scheduler emits `cycle_launched` events indistinguishable from human-launched ones — same Timeline entry shape, only `actor.source=system`.
- **Paper-first hard rule** is enforced at Passport gate evaluation (S07), not in the UI. Deployment intent to `live` without a paper predecessor is rejected by the Registry.

**What we need to add:** the `EnvelopeAuthoringModal`. No architectural change.

### 21.4 Phase δ (SUPERVISED AUTONOMY)

Adds: autonomous live deployment inside envelope · autonomous portfolio rebalance · autonomous retirement.

Architectural primitives:

- **Envelope model** is defined at Phase γ; Phase δ increases its coverage, not its shape.
- **Kill-switch as first-class primitive** (§18 recommendations) means the veto path is already wired.
- **Portfolio Composer (S09) + Risk Governor (S10)** cleanly separate "what should exist" from "how much money it gets" — the split we already committed to in §16.
- **Timeline retention policy** (§19.3) already treats Governance and Execution events as indefinite; compliance dossiers are just filtered exports.

**What we need to add:** the `EnvelopeMonitor` surface (a specialised Passport tab) and per-envelope autonomy metrics. No architectural change.

### 21.5 Non-roadmap events the architecture also survives

- **Multi-broker parity** — Execution Gateway (S11) is a boundary layer; adding a broker is a new adapter, not a new service.
- **Multi-tenant Factory** — services are contract-only; tenants become an actor attribute in Timeline. No cross-cutting rewrite.
- **Agent (v2)** — S00-like insertion between the operator and every service, subscribing to Timeline and emitting proposals into the recommendation queue. It becomes another producer, not a redesign.
- **Regulator-facing exports** — Timeline retention + immutability already provide the substrate; export is a query, not a schema.

### 21.6 What could still require redesign (honest list)

Not everything is future-proof. Three categories where a v2 memo will be needed:

1. **Cross-asset portfolio composition** at scale (thousands of strategies) may require breaking S09 into `Composer` + `ScoringWorker` + `ScheduledRecomposer`. Boundary of S09 stays; internals change.
2. **Real-time WSS at high fan-out** may require a broker-side pub/sub (Redis Streams / NATS) instead of the single `/ws/stream` in §14. The event vocabulary survives; the transport layer changes.
3. **Non-JSON-RPC integrations** (FIX protocol, exchange-specific binary feeds) may require S01 (Ingestion) to accept plug-in adapters with a formal contract. The service boundary is intact; the adapter model is new.

These are known unknowns. They are not architectural bugs — they are legitimate v2 territory.

---

## 22 · Recommendations · simplify without losing depth

Six principles for keeping the operator experience calm while the Factory grows.

1. **One primary action per surface.** Coverage has `Refresh`. Strategy Lab has `Compose`. Passport has `Approve`. Anything beyond one primary action is a signal to split the surface.
2. **Progressive disclosure by role, not by user preference.** The engineer sees more chips, more percentiles, more IDs. The operator sees the headline and one path forward. Same URL, different density — driven by role.
3. **Ledger over dashboard.** When forced to choose, prefer surfaces that show *"what happened, in order"* over *"what's the number now"*. Ledgers scale; dashboards balloon.
4. **Kill switch is one keypress.** From any surface. Reachable from Command Palette. Confirmable in < 3 seconds. This is the ultimate operator affordance.
5. **Every empty state is a teaching moment.** The current-slice empty states (e.g. Datasets "Awaiting first ingestion tick") already do this — codify it as a system, not per-surface polish.
6. **Two-way transparency.** Every event visible to the operator is visible to the engineer, and vice versa. No "expert modes" that hide state; role differences are about *elevation*, not *concealment*.

---

## 23 · Decision log — what this memo commits us to

If you sign this off, these become non-negotiable design axes:

**Frontend / information architecture**
- ✅ **URL is truth** for every user-visible state.
- ✅ Six-state canonical **`SignalState`** — no more ad-hoc labels.
- ✅ **Passport is the only promotion surface** — no side-doors.
- ✅ **Kill switch is a first-class primitive**, accessible from anywhere.
- ✅ **Approvals modal is one component**, wired to every state-changing mutation.
- ✅ **Workspace context is URL-scoped**, session-lived, and honoured by every surface.
- ✅ **Portfolio splits into Composition (Engineering) + Allocation (Execution)**.
- ✅ **Freshness is one global tick loop**, WebSocket is opt-in per critical surface.

**Factory architecture**
- ✅ **Fourteen services** in the catalogue; new capabilities become services, not features.
- ✅ **Layered service graph** — Layer N never depends on Layer N+1.
- ✅ **Six architectural invariants** (Ingestion↛Composition, KB↛Execution, Composition↛Execution, Risk Governor on-path, Meta-Learning read-only downstream, Timeline append-only) — architectural bugs if violated.
- ✅ **Event vocabulary is versioned and immutable** — new names, not migrations.
- ✅ **Six event categories** with declared retention policies; Governance/Execution/Learning are indefinite.
- ✅ **Loop-back edges are event-driven**, not RPC — Meta-Learning never mutates downstream state.

**Governance / autonomy**
- ✅ **Three-tier autonomy taxonomy** (H · R · A) applied to every action at design time.
- ✅ **Every autonomous action has a veto path** reachable in ≤ 3 seconds.
- ✅ **Non-graduation set** (envelope authorship, KB→live promotion, admin actions, two-person-rule actions) never leaves Human tier.
- ✅ **Autonomy widens on evidence**, not on schedule — phases α → β → γ → δ are gated by proof.
- ✅ **Execution workspace is isolated** from Engineering by group and by banner.
- ✅ **Historical KB import goes through Passport** with permanent `learning_only=true`.
- ✅ **Backend Feature Freeze v1.1.0-stage4 remains intact** until Execution capabilities are needed.

---

## 24 · Proposed next slices (post-review)

**Slice A · Workspace context thread + SignalState primitive.** Foundational. Small backend impact (none). Every future surface inherits both.

**Slice B · Strategy Passport detail view.** Closes the biggest workflow loop we currently have open (Strategy Lab → Passport → Pipeline).

**Slice C · Approvals pattern + Event vocabulary shim.** Prepares the ground for Execution. Frontend-only; zero backend change; can be wired to existing mutations for real-world exercise.

Everything in this memo is subordinate to your review. If any section is wrong, please push back — this is the document the next twelve months of work will be measured against.

---

_End of memo._

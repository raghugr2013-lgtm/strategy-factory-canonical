# Operational Dashboard — Mockup
### Text-based layout prior to implementation (Sub-stage 2.κ or 3.α)

> **Status:** mockup only — no implementation.
> Requested by operator on 2026-02-19.
> Priority order (per operator directive): platform health → coverage → gaps
> → CTS cache → provider sync → queue → budget → historical trends.
> Focus: operator visibility and health status, not UI styling.

---

## 1. Design principle

> **A single glance should answer: is anything broken, degraded, or
> requiring intervention? If yes, exactly where and what action?**

Every panel below leads with an operator-actionable status indicator
(`OK` / `DEGRADED` / `CRITICAL` / `NEEDS REVIEW`) and, when non-OK,
names the closed-enum `action_required` from the Universal Health
Contract. Numbers come second.

---

## 2. Overall page layout (top to bottom)

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  STRATEGY FACTORY — OPERATIONAL STATUS                        [Last refresh: 15s] │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [1] PLATFORM HEALTH                                    (highest-priority panel)  │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [2] MARKET DATA COVERAGE                                                         │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [3] GAP SUMMARY                                                                  │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [4] CTS CACHE STATUS                                                             │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [5] PROVIDER SYNCHRONIZATION                                                     │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [6] QUEUE HEALTH                                                                 │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [7] BUDGET HEALTH                                                                │
├───────────────────────────────────────────────────────────────────────────────────┤
│  [8] HISTORICAL TRENDS  (last 24h / 7d / 30d selectable)                          │
└───────────────────────────────────────────────────────────────────────────────────┘
```

Panels 1–7 are always visible; panel 8 is collapsible and expanded on demand.

---

## 3. Panel details (mockup with representative data)

### [1] Platform Health — the answer panel

```
┌─ PLATFORM HEALTH ────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK        Platform Health Score: 96                                           │
│                                                                                  │
│  Subsystems:                                                                     │
│      ● COE                  100      ● VIE                  100                  │
│      ● CTS                  100      ● Meta-Learning         92                  │
│      ● Market Intel.        100      ● Execution             98                  │
│      ● Portfolio            100      ● Factory-Eval          95                  │
│      ● UKIE                  n/a  (not yet enabled)                              │
│                                                                                  │
│  Action Required: none                                                           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Degraded example:**
```
┌─ PLATFORM HEALTH ────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ⚠ DEGRADED  Platform Health Score: 72                                           │
│                                                                                  │
│  Subsystems (2 degraded):                                                        │
│      ● COE                  100      ○ VIE                   45  ← degraded      │
│      ● CTS                   88      ● Meta-Learning         92                  │
│                                                                                  │
│  Action Required:                                                                │
│      VIE  →  operator_review    reason: circuits_open=2/3                        │
│      CTS  →  operator_review    reason: cache miss ratio > 20% last 15m          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Colour legend: `●` green (OK) / `○` amber (degraded) / `✕` red (critical) /
`◉` recovering.

**Data sources:** `GET /api/health/system`, `platform_health_score`,
each subsystem's `HealthSnapshot`.

### [2] Market Data Coverage

```
┌─ MARKET DATA COVERAGE ───────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK                  Coverage Completeness: 99.87%      Canonical Mode: M1     │
│                                                                                  │
│  20 symbols   19 canonical (m1)   1 native_tf   120,345,678 M1 rows total        │
│                                                                                  │
│  Worst-covered symbols (< 99% completeness):                                     │
│                                                                                  │
│    Symbol      Completeness    First bar        Last bar         M1 rows         │
│    ──────    ──────────────   ──────────────   ──────────────   ─────────        │
│    ○ AUDCAD       98.42%      2010-03-15 UTC   2026-02-19 UTC   8,092,441        │
│    ○ NZDCHF       98.71%      2010-03-15 UTC   2026-02-19 UTC   8,116,003        │
│    (17 more at ≥ 99%)                                                            │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Data source:** `GET /api/data/coverage` (locked contract).

### [3] Gap Summary

```
┌─ GAP SUMMARY ────────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ⚠ WARNING     Gaps in last 30 days: 47                                          │
│                                                                                  │
│  By severity:                                                                    │
│      Governance review:  0                                                       │
│      Warning:            3                                                       │
│      Informational:     44                                                       │
│                                                                                  │
│  Recent significant gaps:                                                        │
│                                                                                  │
│    Symbol   TF   Start                  Duration   Severity     Provider status  │
│    ──────  ────  ──────────────────    ────────   ──────────  ─────────────────  │
│    EURUSD  1m    2026-02-14 22:03 UTC   4 min      warning     confirmed_absent  │
│    GBPUSD  1m    2026-02-13 21:58 UTC   2 min      informational   session_gap   │
│                                                                                  │
│  Action Required: none  (all gaps below `governance_review` threshold)           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Data source:** `GET /api/data/coverage?include=gaps`.

### [4] CTS Cache Status

```
┌─ CTS CACHE STATUS ───────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK                     Cache Hit Ratio (1h): 94.7%                            │
│                                                                                  │
│  Buckets (3-axis: symbol|tf|month):                                              │
│      Fresh:      1,413   ○ Stale:  3    ○ Missing: 24                            │
│      Total:      1,440                     Bytes:   ~500 MB                      │
│                                                                                  │
│  Aggregation latency (last 1h):                                                  │
│      p50:  15 ms   p95:  78 ms   p99: 210 ms                                     │
│                                                                                  │
│  Recent activity:                                                                │
│      Invalidations (1h):  12    Rebuilds (1h):  4                                │
│                                                                                  │
│  Data quality states (buckets):                                                  │
│      ok: 1,436   degraded: 4   reconstructed: 0   stale: 3   unknown: 0          │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Data source:** `GET /api/data/coverage?include=cache`,
`GET /api/coe/metrics` (Prometheus).

### [5] Provider Synchronization

```
┌─ PROVIDER SYNCHRONIZATION ───────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK        All provider sources current                                        │
│                                                                                  │
│    Source              Last sync         Rows fetched     Failures    Rate limit │
│    ─────────────   ────────────────    ─────────────   ─────────    ────────── │
│    dukascopy/bid    2026-02-19 14:15    324 rows         0           ok         │
│    dukascopy/bi5    2026-02-19 14:10    2,187 ticks      0           ok         │
│                                                                                  │
│  Provider-native HTF verification:                                               │
│      Last diff:  2026-02-01           Tier:  informational                       │
│      Next diff:  2026-03-01                                                      │
│                                                                                  │
│  BID ↔ BI5 cross-source consistency:                                             │
│      Last check:  2026-02-01          Tier:  informational   Divergence: 0.12%   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### [6] Queue Health

```
┌─ QUEUE HEALTH ───────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK       Pressure band: normal      Total enqueued: 4      In-flight: 3       │
│                                                                                  │
│    Class            P0     P1     P2   Reservation   In-flight                   │
│    ──────────────  ───   ────   ────  ───────────   ─────────                    │
│    execution         0      0      0        2            1                       │
│    api_hot           0      0      0        2            0                       │
│    market_data       0      1      0        1            1                       │
│    backtest          0      2      0        1            1                       │
│    mutation          0      0      1        1            0                       │
│    knowledge         0      0      0        0            0                       │
│    factory_cycle     0      0      0        0            0                       │
│    ...                                                                           │
│                                                                                  │
│  Queue latency (submit → dispatch, 1h):  p50: 8 ms   p95: 45 ms   p99: 128 ms    │
│                                                                                  │
│  Recent dead-letter items: 0                                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### [7] Budget Health

```
┌─ BUDGET HEALTH ──────────────────────────────────────────────────────────────────┐
│                                                                                  │
│  ● OK      Daily headroom: 92%      Monthly headroom: 87%                        │
│                                                                                  │
│    Provider     Calls (today)   USD spent    Daily cap    Circuit                │
│    ──────────  ─────────────   ─────────   ──────────   ──────                   │
│    anthropic         142         $1.28        $12.00     closed                  │
│    openai             38         $0.42         $8.00     closed                  │
│    gemini             22         $0.10         $2.50     closed                  │
│    deepseek            0         $0.00         $1.00     closed                  │
│    groq                0         $0.00         $1.00     closed                  │
│    kimi                0         $0.00         $0.50     closed                  │
│                                                                                  │
│  Total spent today: $1.80   /   $25.00 daily cap                                 │
│  Persistence:    ● loaded (last save 27s ago)                                    │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### [8] Historical Trends (collapsible)

```
┌─ HISTORICAL TRENDS ──────────────────────────────────  [1h] [24h] [7d] [30d]  ── ┐
│                                                                                  │
│  Platform Health Score (24h)         ▁▂▃▂▃▃▄▄▅▄▅▆▆▇█▇█▇█▇█                       │
│  CTS Cache Hit Ratio  (24h)          ▄▅▅▆▇▇█████████████████                     │
│  Queue P0 Latency p95 (24h)          █▇▆▅▄▄▃▃▂▂▂▁▁▁▁▁▁▁▁▁▁                       │
│  Coverage Completeness (24h)         ██████████████████████                      │
│  Budget spent (24h cumul.)           ▁▁▁▁▂▂▂▂▃▃▃▄▄▄▅▅▅▆▆▆▆                       │
│  Provider circuit-open events (24h)  0                                           │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Sparklines rendered from `/api/coe/metrics` (Prometheus scrape via Grafana)
or from a small `metrics_history` collection populated on-demand.

---

## 4. Escalation logic (dashboard-driven alerts)

The dashboard renders `action_required` visibly, but Alertmanager
routes the same signals into notifications:

| Condition | Alert level | Channel |
|---|---|---|
| Any subsystem `state=critical` | Page immediately | ops on-call |
| `platform_health_score < 60` | Page | ops on-call |
| Any subsystem `state=degraded` for > 15 min | Warning ticket | ops queue |
| Coverage completeness < 99% | Warning ticket | data team |
| Gap severity `governance_review` recorded | Warning ticket | data team + operator |
| Budget headroom < 10% (daily) | Warning ticket | operator |
| Provider circuit `open` > 5 min | Warning ticket | ops queue |
| CTS cache hit ratio < 70% (1h) | Info ticket | data team |
| Queue P0 p95 latency > 500 ms sustained 15 min | Warning ticket | ops queue |

Thresholds ARE operator-tunable via env variables in the
`PLATFORM_ALERT_*` family. No thresholds are enforced code-side —
they are configuration.

---

## 5. Access model (per operator directive)

| Role | Panels visible | Actions |
|---|---|---|
| **Admin** | All 8 panels | Read + control endpoints (rebuild cache, invalidate, reset budget, cancel job) |
| **Researcher** | Panels 1, 2, 3, 4 (read-only) + 8 (trends) | Read only |
| **Anonymous** | None | Denied |

Read scope for researcher includes: platform health, coverage,
gaps, CTS cache status. Write endpoints (`POST /api/cts/cache/rebuild`,
`POST /api/coe/reservations/*`, `POST /api/coe/dead-letter/*`) remain
admin-only.

---

## 6. Refresh discipline

- Panels 1–7: auto-refresh every 15 s (soft, cached with `ETag`)
- Panel 8: on-demand (initial render skipped until expanded)
- Rate limit: dashboard endpoints capped at 20 req/min per user
- Prometheus scrape: separate endpoint, 5 s cadence, no auth (or bearer scrape token)

---

## 7. Data sources per panel

| Panel | Endpoints consumed |
|---|---|
| 1 Platform Health | `GET /api/health/system`, `GET /api/health/<subsystem>` |
| 2 Coverage | `GET /api/data/coverage?include=summary,symbols` |
| 3 Gaps | `GET /api/data/coverage?include=gaps` |
| 4 CTS Cache | `GET /api/data/coverage?include=cache`, `GET /api/coe/metrics` |
| 5 Provider | `GET /api/data/coverage?include=provider` |
| 6 Queue | `GET /api/coe/state`, `GET /api/coe/metrics` |
| 7 Budget | `GET /api/health/vie`, `GET /api/coe/metrics` |
| 8 Trends | `GET /api/coe/metrics` (via Grafana scrape) |

**Every endpoint listed above exists at end of Stage 2** — no new
endpoints required for the dashboard MVP.

---

## 8. Open questions

1. **Colour palette:** operator preference on green/amber/red intensity? Recommend **restrained** (avoid the "dashboard Christmas tree" effect).
2. **Sparkline data retention:** how far back — 24h always available, 7d/30d compressed? Recommend Prometheus retention (Grafana handles).
3. **Native TF instruments** (per `canonical_mode="native_tf"`) — surface them explicitly in panel [2] or fold into "worst-covered"? Recommend explicit small subsection.
4. **Mobile-friendly?** Recommend read-only mobile view showing panels 1 + 7 + escalations only.
5. **Dashboard hosting:** Grafana (rich, external) or embedded in the Strategy Factory frontend? Recommend **Grafana for ops** + a lightweight embedded status widget in the frontend.

---

## 9. Sign-off

Pending operator approval. On approval:
- Implementation lands as either Sub-stage 2.λ (post-Validation-Gate-2) or Stage 3.α depending on Grafana vs embedded decision (§8.5)
- Coverage / metrics endpoints already live behind flags — dashboard is a consumer, not a producer

*Reviewed against:* `COVERAGE_API_CONTRACT_PREVIEW.md`,
`PHASE_2_CONSOLIDATED_REVIEW.md §5.1` (Universal Health Contract),
`PHASE_2D_COMPUTE_ORCHESTRATION_REVIEW.md §1.8`
(pressure bands + reservations).

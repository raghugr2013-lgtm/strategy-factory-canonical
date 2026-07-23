# ROADMAP — POST-FORK PRIORITY ORDER
**Last updated:** 2026-02 (pre-migration audit phase)
**Operating mode:** Architectural blueprints first → operator approval → implementation. No exports yet. No migration code changes yet.
**Discipline:** Additive only. Sealed surfaces (G2 scheduler, IR transpiler, lifecycle engine, governance_universe authority) untouched.

---

## 0. CANONICAL IDENTITY MANDATE

All future ASF subsystems MUST use the corrected identity hierarchy:

```
Strategy Instance (fingerprint)
   ↓
Validated Archetype  (mode of WF strategy_type — NOT mutation_type label)
   ↓
Family               (canonical_family_key = sha1(archetype + pair + tf + frozen_params_sig))
   ↓
Edge                 (edge_id = (archetype, semantic_tag))
   ↓
Portfolio            (curated multi-family bundle, ≥2 distinct edges)
   ↓
Master Bot           (executable composite of one portfolio)
```

Per-subsystem key contract (full table in `/app/memory/ASF_CANONICAL_IDENTITY_MODEL.md` §4):

| Subsystem | Primary Key |
|---|---|
| Family Dedup | `canonical_family_key` |
| Quality Score (v2) | `fingerprint` rolled to family |
| Evidence Score | `canonical_family_key` |
| Trust Score | `canonical_family_key` (edge-borrowable) |
| Portfolio Builder | `canonical_family_key` (≥2 distinct edges) |
| Master Bot Builder | `portfolio_id` |
| Marketplace | `canonical_family_key` (best fingerprint spotlight) |
| Strategy Dossier | `canonical_family_key` |
| Pass Probability v2 | `(canonical_family_key, firm_slug)` |
| Factory Supervisor | `edge_id` for coverage planning |

**Legacy `strategy_text` / `mutation_type` labels are retained as `legacy_label` audit-trail only.** They are NOT identity keys.

---

## 1. CURRENT PRIORITY ORDER

| # | Item | Status | Document |
|---|---|---|---|
| 1 | 🔴 DSR Activation (DSR-1 → DSR-3) | **Blueprint ready; awaits implementation approval** | `DSR_ARCHITECTURAL_BLUEPRINT.md` |
| 2 | 🔴 BI5 Recovery R1 (B-1, B-2, B-9 + health) | **Blueprint ready; awaits implementation approval** | `BI5_R1_ARCHITECTURAL_BLUEPRINT.md` |
| 3 | 🟡 BI5 Recovery R2 | Planned (TBD scope) | — |
| 4 | 🟡 BI5 Recovery R3 | Planned (TBD scope) | — |
| 5 | 🟢 Migration Exports (1-vCPU → bundle) | Audit complete; export commands awaiting operator decree | `MIGRATION_EXPORT_PLAN.md`, `DOWNLOAD_MANIFEST.md` |
| 6 | 🟢 Import into 12-vCPU | Plan ready | (target pod) |
| 7 | 🟢 Post-Import Pipeline (re-score / re-rank / re-portfolio / re-masterbot) | Plan ready | `POST_IMPORT_PIPELINE.md` |

> **Note:** DSR + BI5 R1 are *independent of migration exports*. They proceed in parallel and do not block each other.

---

## 2. DSR ACTIVATION — DSR-1 → DSR-3

See `/app/memory/DSR_ARCHITECTURAL_BLUEPRINT.md` for full spec.

| Phase | Deliverable | Acceptance |
|---|---|---|
| **DSR-1** | Operator Symbol Registry UI + CRUD + seed endpoint | UI works; scheduler still uses hard-coded `SYMBOL_CONFIG` (flag off) |
| **DSR-2** | Scheduler consumes registry (flag on) | Adding a symbol via UI flows into scheduler within one tick |
| **DSR-3** | Dynamic universe + shadow audit | Symbol onboarding end-to-end with NO code changes |

Subsystem flow once DSR-3 ships:
```
operator-add → Market Data → BI5 → Auto Factory → Validation → Explorer → Portfolio → Marketplace
                                                                                       ↑
                                                          all gated by canonical_family_key (post-rescoring)
```

Anti-drift constraints retained:
- `governance_universe.pairs` remains the final authority on what runs autonomously.
- `AUTONOMOUS_DISCOVERY_ENABLED` and `auto_replace_enabled` default off.
- No symbol auto-promotes from `shadow → active`; operator decree required.

---

## 3. BI5 RECOVERY R1 — B-1, B-2, B-9 + Health

See `/app/memory/BI5_R1_ARCHITECTURAL_BLUEPRINT.md` for full spec.

| Item | Deliverable | Acceptance |
|---|---|---|
| **B-1** | `run_bi5_ingest` dispatcher + semaphore + token-bucket | Scheduler routes through dispatcher; per-run entry in `bi5_ingest_log` |
| **B-2** | UI BI5 source propagation (per-symbol source, lookback, test endpoint) | Operator can switch sources via UI; next tick honours change |
| **B-9** | Historical backfill (multi-month, resumable, throttled) | 12-month backfill survives container restart |
| **+ Health** | `bi5_health` collection + alert transitions + `BI5HealthPanel.jsx` | Status transitions correctly across `healthy/degraded/failing/dormant` |

Approved baselines:
- 30-day default lookback (operator-tunable per symbol)
- All eligible symbols (those in `symbol_registry` with `bi5.enabled=true`)
- Extended `bi5_ingest_log` schema (per-run summary in addition to per-file entries)
- Per-symbol BI5 health tracking (separate collection, status thresholds defined)
- BI5 Health monitoring surface (dashboard tile + drill-down drawer)

---

## 4. BI5 RECOVERY R2 / R3 (planned, scope TBD)

Placeholder entries — to be defined after R1 ships. Likely candidates (subject to operator confirmation):
- **R2:** BID↔BI5 temporal alignment validator (already partially present in `incremental_updater.py`) promoted to first-class observability with operator-facing alerts.
- **R3:** Multi-source BI5 provider fallback (Dukascopy → manual → API_X).

---

## 5. MIGRATION EXPORTS (Item 5)

Awaiting operator decree to execute the export commands in `DOWNLOAD_MANIFEST.md §3`. Audit suite complete:

- `LEGACY_STRATEGY_INVENTORY.md` — 140-row inventory
- `SURVIVOR_CLASSIFICATION.md` — Elite/Strong/Average/Experimental/Deprecated buckets
- `SURVIVOR_RESCORING_PREVIEW.md` — fundamentals-only re-scoring forecast
- `LINEAGE_DEDUP_AUDIT.md` — 34 logical families
- `F03_REGIME_ANALYSIS.md` — bimodality root cause
- `VALIDATED_ARCHETYPE_INVENTORY.md` — 100 % systemic drift discovery + 15 corrected families
- `ASF_CANONICAL_IDENTITY_MODEL.md` — identity hierarchy + per-subsystem keys
- `MIGRATION_COMPATIBILITY_AUDIT.md` — per-subsystem compatibility
- `DISCOVERY_GAP_REPORT.md` — what exists, what's missing
- `POST_IMPORT_PIPELINE.md` — 9-stage re-hydration plan
- `MIGRATION_EXPORT_PLAN.md` — two-track export
- `DOWNLOAD_MANIFEST.md` — final manifest + import instructions

Export gate: operator confirms tier classification, `--drop` vs merge strategy, code-track inclusion, and API-key readiness on target. No commands run until decree.

---

## 6. IMPORT (Item 6) & POST-IMPORT PIPELINE (Item 7)

Both ready in `POST_IMPORT_PIPELINE.md`. On import the target pod MUST:

1. Add additive schema fields (`validated_archetype`, `canonical_family_key` cache, `archetype_drift_flag`).
2. Run derivation pass for all imported rows.
3. Build `edges` curator collection (Layer 3 of identity model).
4. Re-key Family Dedup → Portfolio Builder → Master Bot → Marketplace / Dossier → Quality / Evidence / Trust.
5. Do NOT enable autonomous loops until POST_IMPORT_PIPELINE Stage 8 completes and operator decree is given.

---

## 7. DEFERRED / BACKLOG (NOT in current priority order)

- BI5-1 → BI5-6 (Execution Realism — gated on cBot survivor data)
- EG-2 → EG-6 (Ecosystem Exploration Governance — gated on stable survivor cadence)
- Phase 31+: Portfolio Intelligence, Causal Edge Attribution, Anti-correlation Mutation Pressure, Live Shadow Execution, Online Demotion Gates
- Auto-maintenance failure observability gap (NOW partly absorbed into BI5 R1 Health Monitoring)
- LLM token/cost tracking into `audit_log` (deferred from Phase 30.3)
- Post-deployment rate-limit / 409-conflict stabilization audit findings (pending operator decision)

---

## 8. INVARIANTS THAT GOVERN EVERY ITEM

1. **Additive only.** Sealed surfaces (G2 scheduler, IR transpiler, lifecycle engine, governance_universe authority) are not modified.
2. **Reversible.** Every change can be turned off via flag.
3. **Trust-gated.** Autonomy never self-promotes; operator decrees terminal transitions.
4. **Identity-honest.** Use `validated_archetype` and `canonical_family_key`, never `strategy_text` / `mutation_type` labels.
5. **Anti-drift.** Each new feature flagged with a default-off mode that reverts to legacy behaviour.

---

## 9. SIGNAL CHAIN (for the operator's mental model)

```
Operator decree
   ↓
Blueprint approved (this document + companions)
   ↓
Implementation (per-phase, additive, reversible)
   ↓
Acceptance check per phase (curl + UI + log inspection)
   ↓
Phase sealed (added to PRD.md)
   ↓
Next priority item begins
```

No phase is started until the previous phase's acceptance check passes (per-item, not per-roadmap-step).

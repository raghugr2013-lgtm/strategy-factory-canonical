# BI5_R2_IMPLEMENTATION_PLAN.md

**Document class:** Implementation plan for BI5 Recovery R2 (Path A1 Step 2) — **AWAITING OPERATOR REVIEW before any code is written.**
**Date:** 2026-06-12
**Scope (locked in PRD §6):** B-4 auto-payload builder + Sunday 03:00 UTC `certify_strategy` sweep · B-5 Master Bot ranker consumes `bi5_cert.certification_verdict` + `slippage_score` · B-8 lifecycle + UI surfacing of certification verdicts. Estimated ≈3–4 d.
**Constraints:** no strategy import · no FS/Auto-Learning/Notification-Center activation · no Phase 13/14/15 reordering.

---

## 0. What R2 builds on (verified live, post-Step-1)

| Already shipped (no work needed) | Evidence |
|---|---|
| `certify_strategy()` orchestrator (pure, BID↔BI5 firewalled, early-fail trail: DATA_CERT_MISSING / NOT_PASS / MISSING_FILLS / MISSING_SIGNALS) | `engines/bi5_certification.py` |
| All 8 certification API endpoints incl. `POST /api/bi5-cert/certify-strategy` + stats/list/latest | `api/bi5_certification.py` |
| Phase-1 evaluators: tick_validator (PASS ≥ 0.90 / WARN ≥ 0.75) · spread_analyzer · slippage_model · execution_simulator | engines tree |
| Persistence: `bi5_strategy_certifications` + `bi5_data_certification` stores (idempotent upserts) | persistence_adapters |
| **Data certifications now real** — Step 1 ingest produced per-symbol `bi5_data_certification` verdicts from the restored archive | Step 1 evidence report |
| Master Bot ranker already projects `bi5_cert` field and runs a persisted-weight config with zero-weight future hooks | `master_bot_ranker.py` L191, DEFAULT_WEIGHTS |
| Scheduler infrastructure (auto_scheduler cadence machinery + monitoring snapshot) | `engines/auto_scheduler.py` |

## 1. B-4 — Auto-payload builder + weekly sweep (≈1.5–2 d)

**New:** `engines/bi5_cert_sweep.py`
1. **Eligibility query** — strategies from `strategy_library` whose `pair` has a current `bi5_data_certification` verdict = PASS (others are skipped with a logged `DATA_CERT_NOT_PASS` precheck, not even built).
2. **Payload builder** — constructs `StrategyCertRequest` per strategy:
   - `fills` + `signals`: sourced from the strategy's most recent backtest artifacts (`validation_report` trades) and, when present, paper-run fills (`paper_runs`); strategies with neither produce honest `MISSING_FILLS` early-fail records (by design — the audit trail shows *why* a strategy is uncertified).
   - `ticks`: loaded from the restored archive for the data-cert window (`BI5TickArchive.read` + `decode_bi5_hour`).
   - `stability_score`: passed through from validation output (never derived — contract).
   - cost assumptions: per-symbol calibration table defaults (existing `execution_realism` defaults).
3. **Sweep runner** — sequential, budget-capped (`max_strategies` per run, default 200), idempotent (cert store upserts keyed per strategy), full per-strategy result log to `bi5_cert_sweep_log`.
4. **Scheduling** — register a weekly cadence job (Sunday 03:00 UTC) via the existing auto_scheduler machinery + a manual trigger endpoint `POST /api/bi5-cert/sweep` (operator-initiated runs; needed because waiting for Sunday is operationally silly during validation).

**Acceptance:** sweep on the current (empty) library completes cleanly with `processed=0`; unit tests cover payload building from fixture strategies (fills present / missing / pair without data-cert).

## 2. B-5 — Ranker weight wiring (≈0.5 d)

**Edit:** `engines/master_bot_ranker.py`
1. Add two signals to the weighted formula, following the existing zero-weight-hook pattern:
   - `bi5_cert_verdict` → normalised {PASS: 1.0, WARN: 0.5, FAIL/early-fail: 0.0, absent: 0.0}
   - `bi5_slippage_score` → cert record's slippage subscore (already 0..1)
2. Default active weights rebalanced (proposal, tunable via the persisted weights doc): `deploy_score 0.50 · bi5_cert_verdict 0.07 · bi5_slippage 0.03` + existing actives renormalised to Σ=1.0. Weight changes go through the existing `config_key=default` persisted doc → operator-auditable, reversible without code.
3. Clamp + out-of-range guard identical to existing signals (corruption-proofing comment in module header honoured).

**Acceptance:** unit test — candidate with PASS cert outranks identical candidate without cert; weights doc round-trips; absent-cert candidates rank exactly as today when weights are 0 (backwards-compat proof), then with default weights applied.

## 3. B-8 — Lifecycle + UI surfacing (≈1 d)

1. **Lifecycle:** sweep writes `cert_passed` / `cert_warn` / `cert_failed(reason)` events into the existing strategy lifecycle event stream (additive event types; no state-machine changes).
2. **UI — new `diag` section `bi5-cert`** (pre-named slot in `FINAL_NAVIGATION_MAP.md` §5):
   - Data-certification table: per-symbol verdict · composite score · window · computed_at (reads `GET /api/bi5-cert/data-certifications`).
   - Strategy-certification table: latest sweep results (verdict, subscores, early-fail reason) + sweep stats strip (reads `/certifications` + `/certifications/stats`).
   - "Run sweep now" button → `POST /api/bi5-cert/sweep` (admin role).
   - Registered in `modulesRegistry.js` (1 section line) + ⌘K palette "Sections" entry — same recipe as Challenge Matching.
3. **BI5 Health panel:** add a per-symbol "data cert" verdict chip column (single extra field join — the health endpoint already has the per-symbol row loop).

**Acceptance:** screenshot of `diag#bi5-cert` showing the 4 real data-cert verdicts from Step 1; testing agent flow: open panel → trigger sweep → see `processed=0` (empty library) result row.

## 4. Sequencing, testing, rollback

| Order | Why |
|---|---|
| B-4 first | produces the records everything else consumes |
| B-8 second | surfaces those records (operator can SEE the sweep work before it influences ranking) |
| B-5 last | ranking influence only after verdicts are visible + reviewed |

- **Testing:** pytest unit suites per engine change (`/app/backend/tests/`), then one testing-agent pass (backend sweep endpoints + frontend `bi5-cert` panel + ranker regression).
- **Rollback:** B-4/B-8 are additive (new module + new section). B-5 rolls back by zeroing the two weights in the persisted doc — no code revert needed.
- **No flags flipped:** R2 runs on existing always-on machinery; the sweep is scheduler-cadence + manual trigger, not a dormant-system activation.

## 5. Out of scope (explicitly)

R3 items (B-3 tick-replay loader, B-6 simulate_fills at paper runtime, B-7 Trade Runner consolidation) — post-import per Path A1 · strategy import · Dukascopy gap backfill for US100/BTCUSD/ETHUSD (separate decision after the import dry-run).

**Status: PLAN — awaiting operator review.**

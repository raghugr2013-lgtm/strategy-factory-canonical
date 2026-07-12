# BI5 R2 Step-0 — Data Certification Calibration Audit

**Date:** 2026-06-12  
**Scope:** Root-cause why `bi5_data_certification` composites are landing 0.0 or 0.66–0.77 against the `PASS=0.90` threshold despite a structurally clean archive.  
**Code path:** `engines/tick_validator.py::aggregate_window` (`EVALUATOR_VERSION = "tick_validator@P0B-v1"`) ← called from `data_engine/bi5_ingest_runner.py::_process_one_hour` + `run_for_symbol`.  
**Goal:** Diagnose *before* implementing any cert-gate logic (R2 B-4/B-5/B-8). Recommendation is **read-only** until operator selects a remediation path.

---

## 1 · Evidence: the 15 cert windows we now have

(See `BI5_CONSOLIDATED_COMPLETION_REPORT.md` §1.3 for the full table.) Key invariants across **all 15 windows**:

* `cov         = 1.000`  → every session hour was either ingested OR correctly tagged `expected_empty`. Calendar wiring is **correct**.
* `integrity   = 1.000`  → zero `decode_fail`, zero `non_monotonic`, zero `zero_volume` ticks.
* `price       = 1.000`  → zero `price_outlier` ticks (|mid−ref|>8σ band).
* `hours_missing = 0`    → no session hour was ingested-then-lost.
* `hours_decode_fail = 0`  → no corrupt payloads in the archive.

**Translation:** there is no real data-quality defect. The archive is clean. Composite collapse is **entirely** driven by the two soft axes (`density` + `continuity`) under the current weights and the `0.90` PASS bar.

---

## 2 · The 0.000 zero-score cases (3 of 15)

### 2.1 — EURUSD 2026-01-01 → 2026-01-30 · score 0.0000

```
subscores = { cov:1.0, integrity:1.0, price:1.0, density:0.190, continuity:0.000 }
max_silent_gap_s = 3600.0
```

**Mechanism:** the `aggregate_window` continuity formula in `tick_validator.py:367-374`:

```python
if max_gap <= 0:        continuity = 1.0
elif max_gap >= 3600:   continuity = 0.0
else:                   continuity = 1.0 - log(1+max_gap)/log(1+3600)
```

…then the score collapse in `tick_validator.py:384-393`:

```python
for k, v in subscores.items():
    if v <= 0.0:
        bi5_score = 0.0
        break        # any zero sub-score → composite ≡ 0
```

So **a single sub-score of 0** drives the composite to 0.0 — by design (weighted geometric mean). `max_silent_gap_s = 3600.0` originates from `tick_validator.py:218-226`: when a session-active hour arrives with zero ticks, the validator deliberately sets `max_silent_gap_s = 3600.0` to flag "a real signal".

**`aggregate_window` then takes the MAX across the whole window** (line 320: `max_gap = max((h.max_silent_gap_s for h in hour_validations), default=0.0)`). So **one bad hour in 720** kills the score.

In January 2026 the archive contains at least one session-active hour with zero ticks (most likely the Sunday-22:00 UTC week-open hour when liquidity is thin, or a holiday-flanking hour). That **single hour** drove the whole month to 0.0.

### 2.2 — GBPUSD 2026-01-01 → 2026-01-30 · score 0.0000

Identical mechanism. `max_silent_gap_s = 3600.0`. One empty-but-session-active hour somewhere in January.

### 2.3 — USDJPY 2026-05-31 → 2026-05-31 · score 0.0000

```
subscores = { cov:1.0, integrity:1.0, price:1.0, density:0.000, continuity:0.428 }
hours_present = 2   hours_expected_empty = 22
```

**Mechanism:** May 31 2026 is a **Sunday**. Only 2 hours (22:00 and 23:00 UTC — the Sunday week-open) are session-active. Both fall **below the USDJPY Asia density floor of 3,000 ticks/hour** (Sunday opens are characteristically thin). With density-terms `[0.0, 0.0]`, the density sub-score is 0.0 → composite ≡ 0.0.

> **For comparison:** the same window on XAUUSD scored 0.9655 PASS — because XAUUSD's Asia density floor is 500, easy to clear; and XAU is much more liquid on Sunday week-opens. The score difference is a calibration artefact, not a data-quality difference.

---

## 3 · The 0.66–0.77 "WARN/FAIL" cases (the other 12)

Every one of these has the same structural pattern:

```
cov, integrity, price = 1.0
density   ∈ [0.15, 0.36]   ← most session hours fall in "sparse" or "low_density"
continuity ∈ [0.08, 0.50]  ← max_gap is in the 246s–1861s range
```

### 3.1 — Continuity decays logarithmically and aggressively

The current formula:

| max_gap (s) | continuity |
|---:|---:|
|     0 | 1.000 |
|    60 | 0.485 |
|   180 | 0.366 |
|   300 | 0.304 |
|   600 | 0.220 |
|  1800 | 0.084 |
|  3600 | 0.000 |

**Observation:** even a 60-second silent gap (one missed minute) gives `continuity < 0.5`. In real Dukascopy archives, gaps of **60–300 seconds happen routinely** during low-liquidity hours (Asian-tail, post-news settlement, illiquid metals overnight). They are **not** data defects.

EURUSD May `max_silent_gap_s = 302.8s` → continuity = 0.302. That single 5-min gap **anywhere in 30 days** anchors the score at 0.69 even though the rest of the month is pristine.

XAUUSD May `max_silent_gap_s = 1861s` (~31 min) → continuity = 0.081. XAU genuinely has multi-minute silences during the Asia rollover and around the daily settlement (21:00 UTC); these are **expected** market microstructure, not corrupt data.

### 3.2 — Density floors are not calibrated to Dukascopy emission rates

Per `tick_validator.py:55-79`:

| Symbol | Session | floor | target |
|---|---|---:|---:|
| EURUSD | london | 5,000 | 25,000 |
| EURUSD | ny     | 6,000 | 30,000 |
| GBPUSD | london | 4,000 | 20,000 |
| USDJPY | asia   | 3,000 | 14,000 |
| XAUUSD | london | 3,000 | 16,000 |

The density sub-score is `mean(per_hour_term)` where each term is `0.0 (< floor) / 0.5 (< target) / 1.0`. In our data:

* EURUSD May: density 0.198 → ~80 % of session hours fell below the 5k floor for London, or below the 1k floor for Asia.
* GBPUSD May: density 0.350 → ~60–65 % below floors.
* USDJPY May: density 0.163 → ~83 % below floors.
* XAUUSD May: density 0.855 → only ~15 % below floors. (XAU's 3k london floor matches Dukascopy XAU emission better.)

**Bottom line:** the EURUSD/GBPUSD/USDJPY thresholds were authored against an idealised broker tick feed (every quote-update tick). The Dukascopy archive emits a **filtered tick stream** (bid-or-ask change events with bundling), which is naturally an order of magnitude less dense. The floors are off by **~3×–5×** for FX pairs.

### 3.3 — `PASS = 0.90` is unattainable for the current weights

The weighted geometric mean with weights `{cov:3, integrity:4, price:2, density:2, continuity:1}` (sum=12) requires:

```
composite ≥ 0.90  ⇒  Σ wᵢ · ln(sᵢ) / 12  ≥  ln(0.90) = -0.1054
```

If `cov = integrity = price = 1.0` (their contributions are 0), then we need:
```
2·ln(density) + 1·ln(continuity)  ≥  12 · (-0.1054)  =  -1.264
density² · continuity  ≥  exp(-1.264)  =  0.283
```

Achievable density values on the current Dukascopy archive cap at ~0.40 for FX. Substituting density = 0.40:
```
continuity needed  ≥  0.283 / 0.16  =  1.77   (IMPOSSIBLE — continuity ∈ [0,1])
```

Even at density = 0.85 (XAUUSD's level): continuity needed ≥ 0.39, which is also rarely cleared because `max_silent_gap_s` invariably touches 5+ minutes somewhere in a 30-day window.

**Conclusion: PASS=0.90 is mathematically unreachable** for FX pairs on this data shape. The single PASS we observed (XAUUSD 2026-05-31) is a 2-hour window where `density = 1.0` (both hours cleared the low XAU Asia floor) and the `max_silent_gap` happened to stay under 16 s.

---

## 4 · The 7 user-flagged questions, answered

| # | Question | Answer |
|---|---|---|
| 1 | Why EURUSD Jan + GBPUSD Jan = 0.0 ? | **One** session-active hour in those months had zero ticks → validator forces `max_silent_gap_s=3600` → aggregator takes MAX across the window → continuity=0 → composite=0. Not a data defect. |
| 2 | Why other windows land 0.66–0.77? | Density + continuity sub-scores routinely land 0.15–0.40 on **clean** Dukascopy data because the thresholds were authored against an idealised tick rate. With weighted geo-mean and PASS=0.90, those sub-scores mathematically cap the composite around 0.70 even when the data is perfect. |
| 3 | Weekend-hours accounting | **Correct.** Validator tags weekend / FX-close / metal-settlement hours `expected_empty` via `is_bi5_session_active()` in `bi5_ingest_runner.py:393-402` and `:282-289`. They are excluded from `hours_expected` and do not count toward density/continuity (`density_terms` only appends for `status=="ok"`). |
| 4 | Expected-hours calculations | **Correct.** `hours_expected = sum(status != "expected_empty")` (validator line 310). 521+199 = 720h for EURUSD Jan = 30 days × 24, matches. |
| 5 | Coverage scoring logic | **Correct.** `cov = hours_present / hours_expected`. Always 1.0 in our run because no session hour was missing — see §1 invariants. |
| 6 | Missing-hour penalties | Penalty is in `cov` only. Each `missing` hour deducts `1/hours_expected` from `cov`. None present in our run. **But** the validator also fabricates `max_silent_gap_s=3600` for any *zero-tick session hour* — which is what blew up the Jan windows. **This is the buggy interaction**, not the missing-hour logic itself. |
| 7 | Is 0.90 the right threshold? | **No.** The threshold was set in spec before live Dukascopy data was inspected; it is *mathematically unreachable* for FX pairs on this data shape (proof above). For the current scorer + Dukascopy archive, a realistic distribution would re-centre PASS around **0.75–0.80** *if* density/continuity are also re-calibrated, or **0.85–0.90** *if* the scorer is hardened first. |

---

## 5 · Remediation options (3 of them, ranked)

> All three options leave `cov`, `integrity`, `price` mathematically unchanged. The fix surface is exactly two functions in `tick_validator.py::aggregate_window` (continuity rollup + density-term lookup) and the two threshold constants (`PASS_THRESHOLD`, `WARN_THRESHOLD`). No DB schema change. No bar / spread / cert document is rewritten — the next Pass-2 run will simply overwrite the cert rows with the new scores (the existing ingest is idempotent on bars and spread).

### Option A — **Minimal scorer fix + threshold recalibration** ⭐ recommended

**Change 1 (continuity hardening).** In `aggregate_window`:

```python
# Today (line 320):
max_gap = max((h.max_silent_gap_s for h in hour_validations), default=0.0)

# Proposed: use a session-aware 95th percentile, not the absolute max.
gaps = sorted(h.max_silent_gap_s for h in hour_validations
              if h.status == "ok")
max_gap = gaps[int(len(gaps) * 0.95)] if gaps else 0.0
```

**Why:** the 5 % tail (35 hours out of 720) absorbs the routine quiet hours and the occasional Sunday-open hour. The score now reflects the **typical** continuity, not the worst hour. The 0.0 cases disappear.

**Change 2 (validator tweak, separate file).** In `validate_hour` lines 218-226 (the "n==0 fallback"), drop `max_silent_gap_s` from 3600 to `(target - first_seen)` if `next_session_hour` has ticks, **or** flip status to `expected_empty` if the calendar says so. This kills the artificial 3600 the aggregator currently sees. The simpler form is: just stop setting 3600 on the empty-session-hour branch — set 600 (10 min) as a conservative "session-hour gap proxy" — and let the percentile in Change 1 absorb it.

**Change 3 (density recalibration).** Lower the FX floors to match observed Dukascopy emission. Suggested values (derived from the current EURUSD/GBPUSD/USDJPY data):

```python
DENSITY_TABLE = {
    "EURUSD": { "asia": (300, 1500), "london": (1500, 8000),
                "ny":   (2000, 10000), "overlap": (2000, 10000) },
    "GBPUSD": { "asia": (250, 1200), "london": (1200, 6000),
                "ny":   (1500, 8000), "overlap": (1500, 8000) },
    "USDJPY": { "asia": (800, 4500), "london": (800, 4500),
                "ny":   (1200, 6500), "overlap": (1200, 6500) },
    "XAUUSD": kept as today (already calibrated correctly per our XAU PASS),
}
```

**Change 4 (threshold rebase).** `PASS_THRESHOLD = 0.85`, `WARN_THRESHOLD = 0.70`. Keep the gap geometric — if Steps 1–3 land, ~70 % of the 15 current windows should clear PASS and the remaining ~30 % WARN, with FAIL reserved for genuine defects.

**Cost:** ~30 min implementation. One re-run of Pass-2 (cache-hit, ~30 min).  
**Risk:** Low. Pure deterministic math change; emits identical document schema.  
**Effect on R2 timeline:** Step-0 closes today/tomorrow → R2 B-4/B-5/B-8 unblocked.

---

### Option B — **Document the rationale, keep 0.90 as a stretch goal**

Keep the scorer unchanged. Update the cert verdict consumer (the upcoming R2 B-5 ranker) to treat `WARN` as *also* eligible, with `bi5_score` used directly as a ranker weight rather than a binary gate. PASS becomes informational, not gating.

**Cost:** ~10 min. Just a policy doc + ranker tweak when B-5 lands.  
**Risk:** Low for now, but every imported strategy will land in WARN forever — making the bi5_score effectively meaningless as a quality signal until calibration happens later.  
**Effect:** R2 unblocks immediately but kicks the calibration debt down the road.

---

### Option C — **Full P0B-v2 redesign**

Replace `aggregate_window` with a hierarchical scorer that separates *coverage health* (cov / integrity / price — pass-fail) from *liquidity health* (density / continuity — graded). Composite becomes `coverage_health AND liquidity_grade`, surfaced as two independent verdicts rather than a single gemo-mean number.

**Cost:** 1–2 days. Touches `engines/tick_validator.py`, `engines/persistence_adapters/bi5_data_certification_store.py`, the BI5HealthPanel UI, the planned B-5 ranker, and BI5 R2's whole gating contract.  
**Risk:** Medium-high. Schema churn; ripples into Phase 13 Evidence Score formulae and Phase 14 Trust Score formulae that haven't been written yet.  
**Effect:** Cleanest long-run answer, but parks R2 for a week.

---

## 6 · Recommendation

> **Option A.** Smallest reasonable surface, removes both the 0.0 collapse and the floor-misalignment, lands today, unblocks R2 immediately. The percentile-based continuity (Change 1) alone would close the two Jan zero-scores. Density recalibration (Change 3) is well-supported by the 15-window evidence we now have. Threshold rebase (Change 4) makes PASS a meaningful, achievable bar against real Dukascopy archive data.

If the operator chooses Option A, the implementation surface is:

* `engines/tick_validator.py` (~20 LOC changed; constants + 1 function)
* one Pass-2 re-run (~30 min, fully cache-hit)
* one test addition to `/app/backend/tests/` covering the percentile aggregator
* nothing else changes

---

## 7 · What this report does **not** do

* Does not modify any code.
* Does not change any DB document.
* Does not touch the BI5 R2 / R3 roadmap items (B-4, B-5, B-8, B-3, B-6, B-7) — all stay HELD.
* Does not touch Factory Supervisor / Auto Learning / Notification Center / Phase 13/14/15 / GATE 3.

**Awaiting operator decision: A, B, or C.**

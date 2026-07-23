# ASF CANONICAL IDENTITY MODEL
**Goal:** Define the correct identity hierarchy for the future ASF (AI Strategy Factory) on the 12-vCPU deployment, and prescribe which key each subsystem must use.
**Source of evidence:** F03_REGIME_ANALYSIS.md (single-family bimodality), VALIDATED_ARCHETYPE_INVENTORY.md (universal 100 % drift across 140 specimens), LINEAGE_DEDUP_AUDIT.md (label-based family taxonomy fails dedup).
**Discipline:** Architectural recommendation. No code changes. No DB mutations. No exports.

---

## 1. MOTIVATION

The 1-vCPU deployment exposed a systemic identity-collision:

- `strategy_text` / `mutation_type` / `parameters` describe the **base strategy** fed into the mutation engine.
- `validation_report.walk_forward.windows[*].strategy_type` and `frozen_params` describe the **strategy actually validated**.
- **100 % of 140 specimens drift** between the two. The validated archetype is the only honest signal of *what was traded*.

If any newer ASF subsystem (Master Bot, Marketplace, Quality v2, Evidence, Trust, Portfolio, Dossier) keys off the *labelled* strategy, it will:
- Conflate edges that should be separated (F03 Branches A and B).
- Separate edges that should be unified (F01's 20 "Base + RSI Confirmation" specimens that all validate as momentum, mixed with "Base without RSI" and "Base + Volatility Filter" specimens that also validate as momentum).
- Mis-rank the survivor pool, misseed Master Bots, misweight portfolio correlation, and mislist marketplace candidates.

The fix is structural: **a layered identity hierarchy with a clear canonical key per layer, and a per-subsystem key contract.**

---

## 2. THE PROPOSED IDENTITY HIERARCHY

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Layer 0  · STRATEGY INSTANCE  (1 per row in strategy_library)          │
│            Identity: `fingerprint`                                       │
│            Purpose : The atomic recorded specimen.                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 1  · VALIDATED ARCHETYPE  (broad category)                        │
│            Identity: `validated_archetype` ∈ {breakout, mean_reversion,  │
│                       momentum, trend_following, scalping, …}            │
│            Purpose : The "kind of trading" the optimizer froze.          │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 2  · FAMILY  (archetype + market + params)                        │
│            Identity: canonical_family_key =                              │
│                       (validated_archetype, pair, timeframe,             │
│                        normalized_frozen_params_signature)               │
│            Purpose : The dedup key. Collapses sibling runs.              │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 3  · EDGE  (cross-market, cross-timeframe abstraction)            │
│            Identity: `edge_id` = (validated_archetype, semantic_tag)     │
│            Purpose : The thesis. Same edge expressed across multiple     │
│                       (pair, timeframe) families.                        │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 4  · PORTFOLIO  (curated set of families)                         │
│            Identity: `portfolio_id` (operator or builder-assigned)       │
│            Purpose : Diversified bundle of families with                 │
│                       correlation-aware weighting.                       │
├─────────────────────────────────────────────────────────────────────────┤
│  Layer 5  · MASTER BOT  (executable composite of a portfolio)            │
│            Identity: `master_bot_id`                                     │
│            Purpose : The deployment unit. One MB per portfolio.          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. PRECISE KEY DEFINITIONS

### 3.1 Strategy Instance (Layer 0)
```python
strategy_instance_id = fingerprint   # already on strategy_library
```
- Per-run, per-validation specimen.
- Carries: `validation_report`, `strategy_text` (base), `parameters` (base), recorded metrics.
- **NOT** used as a dedup key.

### 3.2 Validated Archetype (Layer 1)
```python
validated_archetype = mode(validation_report.walk_forward.windows[*].strategy_type)
# Allowed values (extensible): breakout, mean_reversion, momentum,
# trend_following, scalping, channel_breakout, range_fade, ...
```
- Window-mode (140/140 on this pod are unanimous, so mode = any window's value).
- **Persisted as a first-class field** on `strategy_library` (additive schema change on target).
- Drift detection: if WF windows disagree on the archetype, flag `archetype_drift=true`.

### 3.3 Canonical Family Key (Layer 2)
```python
canonical_family_key = sha1(
    validated_archetype
    + ":" + pair
    + ":" + timeframe
    + ":" + normalized_frozen_params_signature
)

normalized_frozen_params_signature =
    sha1(
      sort_keys(round_values(
        average_or_mode(
          [w.frozen_params for w in walk_forward.windows]
        )
      ))
    )
```
- Groups truly-equivalent siblings (same archetype, same market, same validated parameter region).
- On the 1-vCPU pod data, this collapses **140 → ~15–20 canonical families** (cf. VALIDATED_ARCHETYPE_INVENTORY §3).
- F03 Branch A and Branch B → **different keys** (different `frozen_params` signatures even before archetype tie-breaks them).

### 3.4 Edge ID (Layer 3)
```python
edge_id = (validated_archetype, semantic_tag)
# semantic_tag is operator- or auto-curated:
#   ("breakout", "session_range") | ("breakout", "atr_volatility")
#   ("mean_reversion", "rsi_oscillator") | ("mean_reversion", "bollinger_fade")
#   ("momentum", "rsi_confirmation") | ...
```
- One edge can span multiple families (cross-pair, cross-timeframe).
- On this pod: ~5–8 edges, e.g.,
  - (breakout, session_range)
  - (breakout, atr_volatility)
  - (breakout, generic_perturbation) ← absorbs the F03 Branch A discovery
  - (mean_reversion, rsi_oscillator)
  - (momentum, rsi_confirmation_filter)
  - (trend_following, dual_ema)
  - (scalping, tight_sl_dual_ema)
- The `semantic_tag` is **not** auto-derivable from the WF report — it is curated by the analyst (or LLM-assisted curator) based on the family's `frozen_params` shape.

### 3.5 Portfolio ID (Layer 4)
```python
portfolio_id = uuid4()    # assigned by Portfolio Builder
```
- A portfolio is a *set* of `canonical_family_key`s with weights, drawn from at least 2 different `edge_id`s for diversification.
- Carries: correlation matrix (computed from family-level equity curves), allocation vector, rebalance cadence.

### 3.6 Master Bot ID (Layer 5)
```python
master_bot_id = uuid4()   # assigned by Master Bot Builder
```
- Executable unit. References exactly one `portfolio_id`.
- Carries: live-shadow promotion state, exposure caps, demotion gates.

---

## 4. PER-SUBSYSTEM KEY CONTRACT

This is the table the user requested — which key each subsystem **must** use.

| # | Subsystem | Primary Key | Secondary Index | Rationale |
|---|---|---|---|---|
| 1 | **Family Dedup** | `canonical_family_key` (Layer 2) | `validated_archetype + pair + tf` | Only this key collapses true siblings. `strategy_text`/`mutation_type` produce 100 % drift. |
| 2 | **Quality Score (v2)** | `fingerprint` (Layer 0) | rolled up to `canonical_family_key` for family-quality aggregation | Per-specimen score; family-level aggregate is the input to Family Dedup. |
| 3 | **Evidence Score** | `canonical_family_key` (Layer 2) | family history rollup over `validated_archetype` | Evidence is a *longitudinal property of the family*, not of a single specimen. Using `fingerprint` here would under-count evidence by ignoring siblings. |
| 4 | **Trust Score** | `canonical_family_key` (Layer 2) | `edge_id` (Layer 3) for cross-market trust transfer | Trust is composite (Quality + Evidence + OOS discipline) and must aggregate at family level. Cross-family trust can borrow from same-edge families. |
| 5 | **Portfolio Builder** | `canonical_family_key` (Layer 2) | `edge_id` (Layer 3) for diversification constraints | Builds correlation-aware bundles. Must dedupe siblings first; must enforce ≥ 2 distinct `edge_id`s. |
| 6 | **Master Bot Builder** | `portfolio_id` (Layer 4) | references `canonical_family_key`s | A Master Bot wraps one portfolio. Family-level composition is its content. |
| 7 | **Marketplace** | `canonical_family_key` (Layer 2) | best specimen by Trust Score (fingerprint) | Listings are at family level; the displayed "specimen" is the family's best member. Prevents listing 22 near-identical siblings. |
| 8 | **Strategy Dossier** | `canonical_family_key` (Layer 2) | back-references to all `fingerprint`s in the family + `edge_id` | Dossier covers the family: what it does, evidence curve, OOS robustness, sibling spread, cross-pair edge transfer. |
| 9 | **Pass Probability (v2)** | `(canonical_family_key, firm_slug)` composite | per-fingerprint analysis can be the input | Per-firm probability is family-level, not specimen-level. |
| 10 | **Auto-Mutation Runner** | `canonical_family_key` (Layer 2) — the *parent* to mutate | new specimens get a fresh `fingerprint`; the family they join is decided by validation, not by the runner's choice | The runner does *not* assign the family. Validation does. |
| 11 | **Factory Supervisor** | `edge_id` (Layer 3) for coverage planning | `canonical_family_key` for resource allocation | Supervisor decides "what edge to grow next" — that is an edge-level decision. Resource allocation per family. |
| 12 | **Lifecycle / Stage Engine** | `fingerprint` (Layer 0) | optionally lifted to `canonical_family_key` for family-stage aggregation | Stages are per-specimen so OOS/walk-forward events can be tracked, but family-stage rollups are informative. |

---

## 5. WRITE & READ INVARIANTS

| Invariant | Description |
|---|---|
| I1 | `fingerprint` is immutable and globally unique. |
| I2 | `validated_archetype` is set at validation time and immutable thereafter. If a specimen is re-validated and the archetype changes, a NEW `fingerprint` is generated. |
| I3 | `canonical_family_key` is a derivation, recomputed on read by any subsystem. It must not be persisted as a duplicate of its components — only its components (archetype, pair, tf, frozen_params) are persisted. |
| I4 | `edge_id`'s `semantic_tag` is operator/curator-assigned and may evolve. Re-tagging an edge does NOT invalidate any family — families are linked to `edge_id` by reference, not by name. |
| I5 | A `portfolio_id` cannot include two `canonical_family_key`s with the same `(archetype, pair, tf)` triple — that would be a self-correlated portfolio. (Exception: deliberate stress-test portfolios may carry a `relax_diversification=true` flag.) |
| I6 | A `master_bot_id` may reference at most one `portfolio_id`, but a `portfolio_id` may have multiple Master Bots (e.g., shadow + live variants of the same composition). |

---

## 6. MIGRATION-PATH MAPPING (for the 12-vCPU import)

When importing the 1-vCPU `strategy_library` into the target, the target should:

1. **Add the new fields to `strategy_library` schema (additive)**:
   - `validated_archetype: str` (computed from WF report)
   - `canonical_family_key: str` (computed on the fly, optionally cached)
   - `archetype_drift_flag: bool` (true if WF windows disagree — should be false for all 140 source records)
2. **Run a one-time derivation pass** to populate `validated_archetype` for every imported row (mode of WF windows).
3. **Compute `canonical_family_key`** at access time in all subsystems listed in §4.
4. **Assign `edge_id`s** via an operator-curated mapping table (`edges` collection):
   ```
   { _id: ObjectId,
     edge_id: ["breakout","session_range"],
     semantic_tag: "session_range",
     archetype: "breakout",
     curator: "operator|llm-assisted",
     created_at: ISODate,
     notes: "Asian/London-Open range breakouts; characterized by frozen_params with session-time keys" }
   ```
5. **DO NOT migrate the legacy `mutation_type` field as a strategy identity.** Migrate it as `legacy_label` for audit-trail only.

---

## 7. BACKWARDS-COMPATIBILITY CONTRACT

- All legacy fields (`strategy_text`, `parameters`, `mutation_type`, `fingerprint`) **remain** on imported rows.
- New fields are **additive only**.
- Subsystems that have not yet been re-keyed can continue to use `fingerprint` (per-specimen) without breaking — they will simply be coarser/finer than ideal.
- Re-keying is **per-subsystem**, in the order: Family Dedup → Portfolio Builder → Master Bot → Marketplace → Dossier → Trust / Evidence / Quality.

---

## 8. DERIVATION PSEUDOCODE (reference for target implementation)

```python
def validated_archetype(strategy_doc: dict) -> Optional[str]:
    """Return the mode of strategy_type across all WF windows."""
    wf = (strategy_doc.get("validation_report") or {}).get("walk_forward") or {}
    types = [w.get("strategy_type") for w in (wf.get("windows") or []) if w.get("strategy_type")]
    if not types:
        return None
    return Counter(types).most_common(1)[0][0]

def archetype_drift_flag(strategy_doc: dict) -> bool:
    wf = (strategy_doc.get("validation_report") or {}).get("walk_forward") or {}
    types = {w.get("strategy_type") for w in (wf.get("windows") or []) if w.get("strategy_type")}
    return len(types) > 1

def normalized_frozen_params_signature(strategy_doc: dict) -> str:
    wf = (strategy_doc.get("validation_report") or {}).get("walk_forward") or {}
    windows = wf.get("windows") or []
    # Aggregate (mode-per-key) across windows.
    keys = set()
    for w in windows:
        keys.update((w.get("frozen_params") or {}).keys())
    agg = {}
    for k in keys:
        values = [(w.get("frozen_params") or {}).get(k) for w in windows]
        values = [v for v in values if v is not None]
        if not values:
            continue
        # Round numerics to 1 sig-digit-region to bucket near-identical values.
        if all(isinstance(v, (int, float)) for v in values):
            agg[k] = round(sum(values)/len(values), 2)
        else:
            agg[k] = Counter(values).most_common(1)[0][0]
    return sha1(json.dumps(agg, sort_keys=True).encode()).hexdigest()

def canonical_family_key(strategy_doc: dict) -> str:
    arch = validated_archetype(strategy_doc)
    pair = strategy_doc.get("pair")
    tf   = strategy_doc.get("timeframe")
    sig  = normalized_frozen_params_signature(strategy_doc)
    return sha1(f"{arch}:{pair}:{tf}:{sig}".encode()).hexdigest()
```

---

## 9. EXPECTED IMPACT ON SUBSYSTEM OUTPUTS (using 1-vCPU data as preview)

| Subsystem | Before (label-keyed) | After (canonical-family-keyed) |
|---|---|---|
| Family Dedup | 34 families | **15 families** |
| Edge count surfaced | 5 (manual) | **5 (empirical, validated)** |
| Master Bot family seeds | 3–4 | **3 high-conviction + 2 exploratory** (V02 momentum/XAUUSD-H1, V03 breakout/XAUUSD-H1, V05 breakout/ETHUSD-H1, V07 breakout/ETHUSD-H4, V08 breakout/XAUUSD-H4) |
| Strict marketplace listings | 1–3 | **2–4** (V02, V07, V08 + possibly V03) |
| Trust Score concentration | spread across 34 names | **concentrated in 6 families covering 80 % of Elite/Strong** |
| Portfolio diversification | risk of sibling-duplication | **enforced via `edge_id` constraint** |

---

## 10. AUDIT BOUNDARY & NEXT STEPS

This identity model is a **design recommendation**. No code changes, no migrations, no exports have been executed by this audit. The model awaits operator decree before any implementation.

When implemented on the 12-vCPU target, the recommended *order of operations* is:

1. Additive schema change on `strategy_library` (`validated_archetype`, `archetype_drift_flag`).
2. Derivation pass to populate the new fields on imported rows.
3. Family Dedup re-key (Layer 2 keying) — POST_IMPORT_PIPELINE Stage 1.5 (new sub-stage).
4. Portfolio Builder re-key — POST_IMPORT_PIPELINE Stage 6.
5. Master Bot Builder re-key — POST_IMPORT_PIPELINE Stage 7.
6. Marketplace + Dossier re-key — POST_IMPORT_PIPELINE Stage 8.
7. Quality / Evidence / Trust re-key — POST_IMPORT_PIPELINE Stage 3.

All re-keys are *additive* — legacy keys remain valid; subsystems may continue to read `fingerprint` for per-specimen views.

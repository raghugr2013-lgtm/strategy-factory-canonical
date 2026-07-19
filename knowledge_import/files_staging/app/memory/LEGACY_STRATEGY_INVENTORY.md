# LEGACY STRATEGY INVENTORY
**Source:** 1-vCPU AI Strategy Factory v10 (pre-migration audit)
**Scope:** Complete enumeration of all 140 strategies in `strategy_library`
**Discipline:** Read-only. No exports, no mutations.
**Companion docs:** SURVIVOR_CLASSIFICATION.md, MIGRATION_COMPATIBILITY_AUDIT.md, DOWNLOAD_MANIFEST.md

---

## 1. EXECUTIVE SUMMARY

| Metric | Value |
|---|---|
| Total strategies | **140** |
| Distinct pairs | 3 (XAUUSD 63, EURUSD 46, ETHUSD 31) |
| Distinct timeframes | 2 (H1 = 128, H4 = 12) |
| Distinct styles | 1 (`unknown` — style tagging never populated) |
| Source engine | `mutation_engine` (100 %) — none from organic ingestion |
| Validation verdict | **`RISKY`** (100 %) — zero `APPROVED`, zero `REJECTED` |
| `pass_probability` | **0.0** (100 %) — never computed against firm rules |
| Expected Value | **−810.0 USD** (100 %) — constant default; EV grade `negative` |
| OOS ratio (avg) | 1.02 (min 0.70 / max 1.73) |
| Score range | 35.0 → 61.7 (avg 48.85) |
| PF range | 0.79 → 1.28 (avg 1.00) |
| Win rate range | 24.5 % → 56.7 % (avg 35.5 %) |
| Max DD range | 0.00 % → 0.97 % (avg 0.12 %) |
| Stability range | 50.6 → 96.8 (avg 74.8) |
| Lifecycle linkage | **0 / 140** (library fingerprints not present in `strategy_lifecycle.strategy_hash`) |
| Mutation generation | 100 % at `g1` (one strategy at `g2`) |

> ⚠️ **Critical observation:** Despite 1,042 mutation runs producing 10,430 events, the validation funnel collapsed every survivor to verdict=`RISKY` with pass_probability=0 and EV=−810. This deployment never produced a production-grade survivor. The 140 strategies represent **research evidence**, not deployable inventory.

> ⚠️ **Data integrity gap:** `strategy_library.fingerprint` and `strategy_lifecycle.strategy_hash` use disjoint identity schemes on this pod (overlap = 0). `library_id` is `null` on every lifecycle entry. This means the lifecycle table cannot be joined to the library on migration — both must be migrated, but post-import re-linking is required.

---

## 2. FIELD CONVENTIONS USED IN THE TABLE BELOW

- **Strategy ID** — truncated `strategy_id` from `strategy_library` (full ID preserved in Mongo)
- **Family** — strategy source family (`mutation` = born from `mutation_engine`)
- **PF** — profit factor (`profit_factor`)
- **Win%** — win rate
- **MaxDD** — max drawdown percent (`max_drawdown_pct`)
- **PassProb** — `pass_probability` (firm-clearance probability)
- **Validation** — `verdict` field (`RISKY` / `APPROVED` / `REJECTED`)
- **MutGen** — mutation generation depth (`g0` = root, `g1` = first mutation, `g2` = mutation of a mutation)
- **Rank** — variant rank within its parent `mutation_runs.variants` array (`—` if not reported)
- **Score** — composite `score` field
- **Class** — survivor classification (see SURVIVOR_CLASSIFICATION.md)

---

## 3. FULL INVENTORY (140 ROWS, sorted by class → score desc)

| # | Strategy ID | Pair | TF | Family | PF | Win% | MaxDD | PassProb | Validation | MutGen | Rank | Score | Class |
|---|-------------|------|----|--------|----|------|-------|----------|------------|--------|------|-------|-------|
| 1 | `6a09a77c0c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.7 | Average |
| 2 | `6a09a7b20c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.4 | Average |
| 3 | `6a09a80d0c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.3 | Average |
| 4 | `6a09a85c0c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.2 | Average |
| 5 | `6a09a8120c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.0 | Average |
| 6 | `6a08283cc2486b48ee` | XAUUSD | H1 | mutation | 0.98 | 31.7% | 0.00% | 0.00 | RISKY | g1 | — | 60.6 | Average |
| 7 | `6a084500ec5e5d2695` | EURUSD | H1 | mutation | 1.00 | 44.8% | 0.20% | 0.00 | RISKY | g1 | — | 59.9 | Average |
| 8 | `6a082af5c2486b48ee` | XAUUSD | H1 | mutation | 0.99 | 32.3% | 0.00% | 0.00 | RISKY | g1 | — | 59.8 | Average |
| 9 | `6a09a6880c1060696a` | ETHUSD | H4 | mutation | 0.97 | 33.0% | 0.00% | 0.00 | RISKY | g1 | — | 59.8 | Average |
| 10 | `6a082634c2486b48ee` | EURUSD | H1 | mutation | 1.02 | 46.5% | 0.51% | 0.00 | RISKY | g1 | — | 59.6 | Average |
| 11 | `6a082b5cc2486b48ee` | XAUUSD | H1 | mutation | 0.99 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 59.5 | Average |
| 12 | `6a0874be4b98749132` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 59.5 | Average |
| 13 | `6a082b35c2486b48ee` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 58.1 | Average |
| 14 | `6a09a8b60c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 57.2 | Average |
| 15 | `6a09a7210c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 56.1 | Average |
| 16 | `6a0873d84b98749132` | XAUUSD | H1 | mutation | 1.01 | 36.8% | 0.00% | 0.00 | RISKY | g1 | — | 54.1 | Average |
| 17 | `6a082a65c2486b48ee` | XAUUSD | H1 | mutation | 0.97 | 35.9% | 0.00% | 0.00 | RISKY | g1 | — | 54.0 | Average |
| 18 | `6a082904c2486b48ee` | XAUUSD | H1 | mutation | 1.01 | 37.3% | 0.00% | 0.00 | RISKY | g1 | — | 53.8 | Average |
| 19 | `6a08459aec5e5d2695` | EURUSD | H1 | mutation | 1.02 | 46.5% | 0.51% | 0.00 | RISKY | g1 | — | 53.8 | Average |
| 20 | `6a0874624b98749132` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 53.7 | Average |
| 21 | `6a08746b4b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 53.7 | Average |
| 22 | `6a09a6320c1060696a` | ETHUSD | H4 | mutation | 1.28 | 39.2% | 0.00% | 0.00 | RISKY | g1 | — | 53.7 | Average |
| 23 | `6a09a83d0c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 53.4 | Average |
| 24 | `6a0875194b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 53.2 | Average |
| 25 | `6a0873e04b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 53.0 | Average |
| 26 | `6a09a3330c1060696a` | XAUUSD | H1 | mutation | 0.97 | 37.0% | 0.00% | 0.00 | RISKY | g1 | — | 52.9 | Average |
| 27 | `6a0875314b98749132` | XAUUSD | H1 | mutation | 1.02 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 52.7 | Average |
| 28 | `6a0875054b98749132` | XAUUSD | H1 | mutation | 0.99 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 52.4 | Average |
| 29 | `6a082984c2486b48ee` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 52.3 | Average |
| 30 | `6a082bacc2486b48ee` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 52.2 | Average |
| 31 | `6a0829e8c2486b48ee` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 52.1 | Average |
| 32 | `6a082a7ac2486b48ee` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 52.1 | Average |
| 33 | `6a0829acc2486b48ee` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 51.9 | Average |
| 34 | `6a0873ea4b98749132` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 51.9 | Average |
| 35 | `6a0874364b98749132` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 51.7 | Average |
| 36 | `6a08740c4b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 51.6 | Average |
| 37 | `6a0875284b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 51.4 | Average |
| 38 | `6a0840c4f156cacdeb` | EURUSD | H1 | mutation | 0.98 | 44.7% | 0.21% | 0.00 | RISKY | g1 | — | 51.2 | Average |
| 39 | `6a09a72d0c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 51.2 | Average |
| 40 | `6a082602c2486b48ee` | EURUSD | H1 | mutation | 0.97 | 44.2% | 0.19% | 0.00 | RISKY | g1 | — | 50.9 | Average |
| 41 | `6a09a8c10c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 50.9 | Average |
| 42 | `6a084198f156cacdeb` | EURUSD | H1 | mutation | 0.98 | 44.3% | 0.21% | 0.00 | RISKY | g2 | — | 50.8 | Average |
| 43 | `6a084551ec5e5d2695` | EURUSD | H1 | mutation | 0.98 | 44.6% | 0.20% | 0.00 | RISKY | g1 | — | 50.8 | Average |
| 44 | `6a084445ec5e5d2695` | EURUSD | H1 | mutation | 0.98 | 44.6% | 0.20% | 0.00 | RISKY | g1 | — | 50.7 | Average |
| 45 | `6a09a7610c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 50.7 | Average |
| 46 | `6a09a6c00c1060696a` | ETHUSD | H4 | mutation | 1.28 | 39.2% | 0.00% | 0.00 | RISKY | g1 | — | 50.6 | Average |
| 47 | `6a08297fc2486b48ee` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 50.4 | Average |
| 48 | `6a09b2b47fffbb222f` | EURUSD | H1 | mutation | 1.02 | 46.5% | 0.51% | 0.00 | RISKY | g1 | — | 50.4 | Average |
| 49 | `6a0874654b98749132` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 50.0 | Average |
| 50 | `6a09a3a00c1060696a` | XAUUSD | H1 | mutation | 1.00 | 37.1% | 0.00% | 0.00 | RISKY | g1 | — | 49.7 | Average |
| 51 | `6a0829a6c2486b48ee` | XAUUSD | H1 | mutation | 0.98 | 36.2% | 0.00% | 0.00 | RISKY | g1 | — | 49.5 | Average |
| 52 | `6a0873e34b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 49.5 | Average |
| 53 | `6a0874dd4b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 49.5 | Average |
| 54 | `6a084071f156cacdeb` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 49.4 | Average |
| 55 | `6a082a28c2486b48ee` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 48.9 | Average |
| 56 | `6a09a6980c1060696a` | ETHUSD | H4 | mutation | 1.28 | 39.2% | 0.00% | 0.00 | RISKY | g1 | — | 48.9 | Average |
| 57 | `6a0874ac4b98749132` | XAUUSD | H1 | mutation | 1.00 | 32.3% | 0.00% | 0.00 | RISKY | g1 | — | 48.8 | Average |
| 58 | `6a09a7b60c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 48.6 | Average |
| 59 | `6a0824f0c2486b48ee` | EURUSD | H1 | mutation | 0.98 | 44.3% | 0.21% | 0.00 | RISKY | g1 | — | 48.4 | Average |
| 60 | `6a09a6710c1060696a` | ETHUSD | H4 | mutation | 1.06 | 30.2% | 0.00% | 0.00 | RISKY | g1 | — | 48.4 | Average |
| 61 | `6a08747a4b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 48.2 | Average |
| 62 | `6a0829fcc2486b48ee` | XAUUSD | H1 | mutation | 0.97 | 36.3% | 0.00% | 0.00 | RISKY | g1 | — | 47.2 | Average |
| 63 | `6a0827c9c2486b48ee` | EURUSD | H1 | mutation | 0.95 | 29.4% | 0.68% | 0.00 | RISKY | g1 | — | 47.1 | Average |
| 64 | `6a08915813e3fe854d` | EURUSD | H1 | mutation | 0.97 | 44.2% | 0.20% | 0.00 | RISKY | g1 | — | 47.1 | Average |
| 65 | `6a084525ec5e5d2695` | EURUSD | H1 | mutation | 1.01 | 56.7% | 0.16% | 0.00 | RISKY | g1 | — | 46.7 | Average |
| 66 | `6a09a7e10c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 46.7 | Average |
| 67 | `6a09a6a40c1060696a` | ETHUSD | H4 | mutation | 1.28 | 39.2% | 0.00% | 0.00 | RISKY | g1 | — | 46.6 | Average |
| 68 | `6a08246ec2486b48ee` | EURUSD | H1 | mutation | 0.96 | 44.3% | 0.21% | 0.00 | RISKY | g1 | — | 46.2 | Average |
| 69 | `6a09a7a10c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 45.9 | Average |
| 70 | `6a08297ac2486b48ee` | XAUUSD | H1 | mutation | 0.97 | 36.3% | 0.00% | 0.00 | RISKY | g1 | — | 45.3 | Average |
| 71 | `6a082b1dc2486b48ee` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 45.3 | Average |
| 72 | `6a09b28d7fffbb222f` | EURUSD | H1 | mutation | 0.98 | 44.4% | 0.20% | 0.00 | RISKY | g1 | — | 45.3 | Average |
| 73 | `6a082538c2486b48ee` | EURUSD | H1 | mutation | 0.98 | 44.6% | 0.20% | 0.00 | RISKY | g1 | — | 45.2 | Average |
| 74 | `6a09a9810c1060696a` | XAUUSD | H1 | mutation | 0.93 | 34.5% | 0.00% | 0.00 | RISKY | g1 | — | 61.2 | Experimental |
| 75 | `6a082801c2486b48ee` | XAUUSD | H1 | mutation | 0.94 | 34.5% | 0.00% | 0.00 | RISKY | g1 | — | 60.9 | Experimental |
| 76 | `6a08256ec2486b48ee` | EURUSD | H1 | mutation | 0.87 | 25.9% | 0.63% | 0.00 | RISKY | g1 | — | 60.3 | Experimental |
| 77 | `6a08255bc2486b48ee` | EURUSD | H1 | mutation | 0.92 | 24.6% | 0.33% | 0.00 | RISKY | g1 | — | 59.2 | Experimental |
| 78 | `6a0826a2c2486b48ee` | EURUSD | H1 | mutation | 0.92 | 24.6% | 0.34% | 0.00 | RISKY | g1 | — | 59.2 | Experimental |
| 79 | `6a09a9890c1060696a` | EURUSD | H1 | mutation | 0.84 | 26.7% | 0.34% | 0.00 | RISKY | g1 | — | 58.7 | Experimental |
| 80 | `6a09a8a60c1060696a` | ETHUSD | H1 | mutation | 0.92 | 31.5% | 0.00% | 0.00 | RISKY | g1 | — | 58.3 | Experimental |
| 81 | `6a08282ac2486b48ee` | EURUSD | H1 | mutation | 0.89 | 25.6% | 0.40% | 0.00 | RISKY | g1 | — | 57.7 | Experimental |
| 82 | `6a082b77c2486b48ee` | XAUUSD | H1 | mutation | 0.91 | 33.9% | 0.00% | 0.00 | RISKY | g1 | — | 57.7 | Experimental |
| 83 | `6a09a89e0c1060696a` | ETHUSD | H1 | mutation | 0.92 | 31.5% | 0.00% | 0.00 | RISKY | g1 | — | 52.8 | Experimental |
| 84 | `6a0842dcf156cacdeb` | EURUSD | H1 | mutation | 0.89 | 25.0% | 0.39% | 0.00 | RISKY | g1 | — | 52.3 | Experimental |
| 85 | `6a082adec2486b48ee` | XAUUSD | H1 | mutation | 0.83 | 34.2% | 0.00% | 0.00 | RISKY | g1 | — | 51.8 | Experimental |
| 86 | `6a09a8ae0c1060696a` | ETHUSD | H1 | mutation | 0.92 | 31.5% | 0.00% | 0.00 | RISKY | g1 | — | 50.7 | Experimental |
| 87 | `6a0829c2c2486b48ee` | XAUUSD | H1 | mutation | 0.90 | 33.9% | 0.00% | 0.00 | RISKY | g1 | — | 50.5 | Experimental |
| 88 | `6a084465ec5e5d2695` | EURUSD | H1 | mutation | 0.91 | 24.5% | 0.34% | 0.00 | RISKY | g1 | — | 50.2 | Experimental |
| 89 | `6a09a8680c1060696a` | ETHUSD | H1 | mutation | 0.92 | 31.5% | 0.00% | 0.00 | RISKY | g1 | — | 49.9 | Experimental |
| 90 | `6a08285fc2486b48ee` | EURUSD | H1 | mutation | 0.84 | 29.2% | 0.55% | 0.00 | RISKY | g1 | — | 48.4 | Experimental |
| 91 | `6a086f834b98749132` | XAUUSD | H1 | mutation | 0.92 | 34.4% | 0.00% | 0.00 | RISKY | g1 | — | 48.4 | Experimental |
| 92 | `6a08746e4b98749132` | XAUUSD | H1 | mutation | 0.90 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 48.3 | Experimental |
| 93 | `6a082b84c2486b48ee` | XAUUSD | H1 | mutation | 0.91 | 33.8% | 0.00% | 0.00 | RISKY | g1 | — | 47.7 | Experimental |
| 94 | `6a0844d4ec5e5d2695` | EURUSD | H1 | mutation | 0.87 | 27.4% | 0.50% | 0.00 | RISKY | g1 | — | 47.5 | Experimental |
| 95 | `6a08748d4b98749132` | XAUUSD | H1 | mutation | 0.85 | 47.4% | 0.00% | 0.00 | RISKY | g1 | — | 47.0 | Experimental |
| 96 | `6a0824ffc2486b48ee` | EURUSD | H1 | mutation | 0.92 | 24.6% | 0.34% | 0.00 | RISKY | g1 | — | 45.7 | Experimental |
| 97 | `6a086f7a4b98749132` | XAUUSD | H1 | mutation | 0.93 | 34.4% | 0.00% | 0.00 | RISKY | g1 | — | 45.7 | Experimental |
| 98 | `6a084549ec5e5d2695` | EURUSD | H1 | mutation | 0.86 | 26.7% | 0.79% | 0.00 | RISKY | g1 | — | 44.8 | Experimental |
| 99 | `6a084570ec5e5d2695` | EURUSD | H1 | mutation | 0.98 | 44.3% | 0.20% | 0.00 | RISKY | g1 | — | 44.8 | Experimental |
| 100 | `6a0828d0c2486b48ee` | EURUSD | H4 | mutation | 1.03 | 30.1% | 0.01% | 0.00 | RISKY | g1 | — | 44.4 | Experimental |
| 101 | `6a086f6e4b98749132` | EURUSD | H1 | mutation | 0.87 | 27.5% | 0.60% | 0.00 | RISKY | g1 | — | 44.4 | Experimental |
| 102 | `6a0870054b98749132` | XAUUSD | H1 | mutation | 1.01 | 37.4% | 0.00% | 0.00 | RISKY | g1 | — | 44.2 | Experimental |
| 103 | `6a082a6bc2486b48ee` | XAUUSD | H1 | mutation | 0.99 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 43.8 | Experimental |
| 104 | `6a09a7740c1060696a` | ETHUSD | H1 | mutation | 0.92 | 31.5% | 0.00% | 0.00 | RISKY | g1 | — | 43.8 | Experimental |
| 105 | `6a08916213e3fe854d` | XAUUSD | H4 | mutation | 1.23 | 39.4% | 0.00% | 0.00 | RISKY | g1 | — | 43.7 | Experimental |
| 106 | `6a09a31a0c1060696a` | XAUUSD | H1 | mutation | 0.98 | 31.8% | 0.00% | 0.00 | RISKY | g1 | — | 43.7 | Experimental |
| 107 | `6a09a8880c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 43.7 | Experimental |
| 108 | `6a086fa54b98749132` | XAUUSD | H1 | mutation | 0.94 | 34.4% | 0.00% | 0.00 | RISKY | g1 | — | 43.6 | Experimental |
| 109 | `6a082b70c2486b48ee` | XAUUSD | H1 | mutation | 1.00 | 32.2% | 0.00% | 0.00 | RISKY | g1 | — | 43.2 | Experimental |
| 110 | `6a0874d14b98749132` | XAUUSD | H1 | mutation | 1.03 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 43.1 | Experimental |
| 111 | `6a09a7d10c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 43.1 | Experimental |
| 112 | `6a09a7990c1060696a` | ETHUSD | H1 | mutation | 0.94 | 26.6% | 0.00% | 0.00 | RISKY | g1 | — | 42.8 | Experimental |
| 113 | `6a086fa14b98749132` | XAUUSD | H1 | mutation | 0.94 | 34.4% | 0.00% | 0.00 | RISKY | g1 | — | 42.6 | Experimental |
| 114 | `6a0874c74b98749132` | XAUUSD | H1 | mutation | 0.89 | 33.8% | 0.00% | 0.00 | RISKY | g1 | — | 42.4 | Experimental |
| 115 | `6a0826bbc2486b48ee` | EURUSD | H1 | mutation | 0.90 | 38.9% | 0.94% | 0.00 | RISKY | g1 | — | 42.3 | Experimental |
| 116 | `6a09a32d0c1060696a` | EURUSD | H1 | mutation | 0.88 | 26.0% | 0.40% | 0.00 | RISKY | g1 | — | 42.3 | Experimental |
| 117 | `6a0844b6ec5e5d2695` | EURUSD | H1 | mutation | 0.97 | 44.3% | 0.20% | 0.00 | RISKY | g1 | — | 42.2 | Experimental |
| 118 | `6a084583ec5e5d2695` | EURUSD | H1 | mutation | 0.87 | 25.9% | 0.63% | 0.00 | RISKY | g1 | — | 42.0 | Experimental |
| 119 | `6a084427ec5e5d2695` | EURUSD | H1 | mutation | 0.98 | 44.4% | 0.21% | 0.00 | RISKY | g1 | — | 41.8 | Experimental |
| 120 | `6a09a3640c1060696a` | XAUUSD | H4 | mutation | 1.12 | 37.1% | 0.00% | 0.00 | RISKY | g1 | — | 41.5 | Experimental |
| 121 | `6a09a7e60c1060696a` | ETHUSD | H1 | mutation | 1.28 | 39.1% | 0.00% | 0.00 | RISKY | g1 | — | 40.8 | Experimental |
| 122 | `6a08752b4b98749132` | XAUUSD | H1 | mutation | 1.03 | 36.7% | 0.00% | 0.00 | RISKY | g1 | — | 40.1 | Experimental |
| 123 | `6a08917613e3fe854d` | XAUUSD | H4 | mutation | 1.23 | 38.2% | 0.00% | 0.00 | RISKY | g1 | — | 40.0 | Experimental |
| 124 | `6a0842fbf156cacdeb` | XAUUSD | H4 | mutation | 1.28 | 40.0% | 0.00% | 0.00 | RISKY | g1 | — | 39.9 | Experimental |
| 125 | `6a084576ec5e5d2695` | EURUSD | H1 | mutation | 0.84 | 30.3% | 0.97% | 0.00 | RISKY | g1 | — | 39.7 | Experimental |
| 126 | `6a0844acec5e5d2695` | EURUSD | H1 | mutation | 0.89 | 39.8% | 0.55% | 0.00 | RISKY | g1 | — | 39.1 | Experimental |
| 127 | `6a0828f6c2486b48ee` | EURUSD | H1 | mutation | 0.85 | 28.2% | 0.45% | 0.00 | RISKY | g1 | — | 39.0 | Experimental |
| 128 | `6a09b27d7fffbb222f` | EURUSD | H1 | mutation | 0.98 | 44.6% | 0.20% | 0.00 | RISKY | g1 | — | 38.8 | Experimental |
| 129 | `6a09b2687fffbb222f` | EURUSD | H1 | mutation | 0.98 | 44.6% | 0.20% | 0.00 | RISKY | g1 | — | 38.5 | Experimental |
| 130 | `6a09a7500c1060696a` | ETHUSD | H1 | mutation | 1.01 | 29.5% | 0.00% | 0.00 | RISKY | g1 | — | 38.2 | Experimental |
| 131 | `6a082b42c2486b48ee` | XAUUSD | H1 | mutation | 1.04 | 37.7% | 0.00% | 0.00 | RISKY | g1 | — | 37.5 | Experimental |
| 132 | `6a082561c2486b48ee` | EURUSD | H1 | mutation | 0.92 | 24.6% | 0.34% | 0.00 | RISKY | g1 | — | 37.0 | Experimental |
| 133 | `6a082582c2486b48ee` | EURUSD | H1 | mutation | 0.99 | 45.0% | 0.21% | 0.00 | RISKY | g1 | — | 36.9 | Experimental |
| 134 | `6a09b2717fffbb222f` | EURUSD | H1 | mutation | 0.84 | 27.9% | 0.62% | 0.00 | RISKY | g1 | — | 36.5 | Experimental |
| 135 | `6a0873ce4b98749132` | XAUUSD | H1 | mutation | 0.91 | 33.9% | 0.00% | 0.00 | RISKY | g1 | — | 36.2 | Experimental |
| 136 | `6a08250ac2486b48ee` | EURUSD | H1 | mutation | 0.97 | 44.6% | 0.21% | 0.00 | RISKY | g1 | — | 36.1 | Experimental |
| 137 | `6a09a6460c1060696a` | ETHUSD | H4 | mutation | 1.28 | 39.2% | 0.00% | 0.00 | RISKY | g1 | — | 36.0 | Experimental |
| 138 | `6a082498c2486b48ee` | EURUSD | H1 | mutation | 0.99 | 45.0% | 0.20% | 0.00 | RISKY | g1 | — | 35.2 | Experimental |
| 139 | `6a0827d1c2486b48ee` | EURUSD | H1 | mutation | 0.99 | 31.6% | 0.41% | 0.00 | RISKY | g1 | — | 35.0 | Experimental |
| 140 | `6a0874ba4b98749132` | XAUUSD | H1 | mutation | 0.79 | 33.7% | 0.00% | 0.00 | RISKY | g1 | — | 45.3 | Deprecated |
---

## 4. PER-PAIR AGGREGATES

| Pair | Count | Avg Score | Avg PF | Avg Win% | Avg MaxDD | Best (score, PF) |
|---|---|---|---|---|---|---|
| XAUUSD | 63 | 48.7 | 0.99 | 35.4% | 0.02% | (61.2, 0.93) |
| EURUSD | 46 | 46.0 | 0.94 | 36.8% | 0.32% | (59.9, 1.00) |
| ETHUSD | 31 | 52.8 | 1.08 | 32.5% | 0.00% | (61.7, 1.01) |

Notes:
- **ETHUSD** has the best raw signal but only 31 specimens.
- **XAUUSD** has the highest specimen count but PF cluster around 1.0.
- **EURUSD** carries the largest drawdowns despite the lowest stability variance.

---

## 5. PER-TIMEFRAME AGGREGATES

| TF | Count | Avg Score | Avg PF | Avg MaxDD |
|---|---|---|---|---|
| H1 | 128 | 48.5 | 1.00 | 0.13% |
| H4 | 12  | 51.4 | 1.18 | 0.00% |

H4 is under-represented (12 specimens) but shows a higher average PF. Consider seeding additional H4 cycles post-migration once the new scoring pipeline is in place.

---

## 6. MUTATION LINEAGE

- 139 of 140 strategies are at generation **g1** (direct descendants of an originating base).
- 1 strategy is at generation **g2** (mutation of a mutation): `6a084198f156cacdeb` (EURUSD/H1).
- No g0 (root) entries appear in `strategy_library` — the library only stores post-mutation specimens.

---

## 7. INTEGRITY FINDINGS

| # | Finding | Impact | Recommended remediation |
|---|---|---|---|
| 1 | `strategy_library` and `strategy_lifecycle` have zero fingerprint overlap | Lifecycle stages cannot be inferred from library rows | Post-import: re-derive lifecycle from current evidence + history transitions |
| 2 | `pass_probability` = 0 on every row | Pre-30.3 prop-firm panel not actually exercised | Re-run prop-firm matching post-import (STAGE 3.5 / STAGE 5) |
| 3 | `expected_value.expected_value` = −810 (constant) on every row | EV computation is using a sentinel default, not a real series | Recompute EV during post-import re-scoring |
| 4 | All `verdict` = `RISKY` | Validation engine never promoted a strategy | Investigate thresholds post-migration; expected on new 12-vCPU scoring |
| 5 | `winning_trades`, `losing_trades`, `avg_win_*`, `avg_loss_*` are `None` on every row | Per-trade aggregates were not populated | Optional: regenerate from `validation_report.trades` if embedded |
| 6 | All `style` = `unknown` | Style tagging never populated | Tag during post-import dossier composition |

---

## 8. MIGRATION VALUE OF THIS INVENTORY

Despite the absence of "elite" strategies, the inventory has **substantial scientific value**:
- 140 validated specimens span 3 instruments × 2 timeframes
- 10,430 mutation events represent a real evolutionary search trajectory
- 1,047 performance history records allow for backward-evidence reconstruction
- OOS holdout data is intact (avg ratio 1.02) — provides robustness signal for re-scoring
- Stability scores are populated (avg 74.8) — directly feeds Trust Score on target

**See SURVIVOR_CLASSIFICATION.md for migration / marketplace / master-bot value estimates.**

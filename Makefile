# ══════════════════════════════════════════════════════════════════
# Strategy Factory — Tiered Regression Pyramid
# ══════════════════════════════════════════════════════════════════
#
# Tier 1  (every commit)      : memory backend, fast smoke
# Tier 2  (hourly)            : memory backend, full drill
# Tier 3  (daily)             : mongo backend, full drill
# Tier 4  (pre-release)       : mongo backend, replay + stress + 1000-order
# Tier 5  (production)        : paper broker, 24h / 72h validation
#
# Every tier is idempotent, exits 0 on PASS, non-zero on FAIL. Suitable
# for CI matrix wiring, cron, and GitHub Actions.
#
# Env auto-loaded from /app/backend/.env and /app/frontend/.env.
# ══════════════════════════════════════════════════════════════════

SHELL := /bin/bash

BACKEND_DIR := /app/backend
DRILL       := $(BACKEND_DIR)/scripts/paper_flow_drill.py
REPORTS_DIR := /app/test_reports

# Env — the Phase H drill + regression suites need these.
export MONGO_URL             := $(shell grep MONGO_URL $(BACKEND_DIR)/.env | cut -d= -f2 | tr -d ' ')
export DB_NAME               := $(shell grep '^DB_NAME=' $(BACKEND_DIR)/.env | cut -d= -f2 | tr -d ' ')
export REACT_APP_BACKEND_URL := $(shell grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2 | tr -d ' ')
export PYTHONPATH            := /app/backend:/app/backend/legacy


.PHONY: help
help: ## Show this help
	@echo "Strategy Factory — Regression Pyramid"
	@echo ""
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-24s\033[0m %s\n", $$1, $$2}'
	@echo ""


# ── Tier 1 · every commit (< 15s target) ─────────────────────────
.PHONY: tier1
tier1: ## Tier 1 (every commit): memory backend, fast smoke
	@echo "▸ Tier 1 · memory backend · fast smoke"
	@cd $(BACKEND_DIR) && python3 -m pytest \
	  tests/test_v1_2_0_alpha2_phase_h.py \
	  tests/test_v1_2_0_alpha2_phase_h_drill.py \
	  --tb=short -q
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 10 --backend memory


# ── Tier 2 · hourly (< 60s target) ────────────────────────────────
.PHONY: tier2
tier2: ## Tier 2 (hourly): memory backend, full drill
	@echo "▸ Tier 2 · memory backend · full drill (100 orders)"
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 100 --backend memory \
	  --json $(REPORTS_DIR)/tier2_$$(date +%Y%m%d_%H%M).json
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 500 --backend memory \
	  --reject-rate 0.05 --partial-rate 0.15 --slippage-pips 0.5 \
	  --json $(REPORTS_DIR)/tier2_stress_$$(date +%Y%m%d_%H%M).json


# ── Tier 3 · daily (< 3 min target) ───────────────────────────────
.PHONY: tier3
tier3: ## Tier 3 (daily): mongo backend, full integration drill
	@echo "▸ Tier 3 · mongo backend · full integration drill (500 orders)"
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 500 --backend mongo \
	  --json $(REPORTS_DIR)/tier3_$$(date +%Y%m%d).json
	@echo "▸ Full Phase A–H regression sweep"
	@cd $(BACKEND_DIR) && python3 -m pytest \
	  tests/test_v1_2_0_alpha2_phase_a.py \
	  tests/test_v1_2_0_alpha2_phase_b.py \
	  tests/test_v1_2_0_alpha2_phase_b1.py \
	  tests/test_v1_2_0_alpha2_phase_b2.py \
	  tests/test_v1_2_0_alpha2_phase_c.py \
	  tests/test_v1_2_0_alpha2_phase_d.py \
	  tests/test_v1_2_0_alpha2_phase_e.py \
	  tests/test_v1_2_0_alpha2_phase_f.py \
	  tests/test_v1_2_0_alpha2_phase_g.py \
	  tests/test_v1_2_0_alpha2_phase_h.py \
	  tests/test_v1_2_0_alpha2_phase_h_drill.py \
	  --tb=line -q


# ── Tier 4 · pre-release (< 10 min target) ───────────────────────
.PHONY: tier4
tier4: ## Tier 4 (pre-release): mongo backend, replay + stress + 1000-order
	@echo "▸ Tier 4 · mongo backend · pre-release validation"
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 1000 --backend mongo \
	  --json $(REPORTS_DIR)/tier4_1000_$$(date +%Y%m%d_%H%M).json
	@cd $(BACKEND_DIR) && python3 $(DRILL) --orders 1000 --backend mongo \
	  --reject-rate 0.10 --partial-rate 0.20 --slippage-pips 1.0 --latency-ms 60 \
	  --json $(REPORTS_DIR)/tier4_stress_$$(date +%Y%m%d_%H%M).json
	@echo "▸ Full regression (all phases, verbose failure output)"
	@$(MAKE) tier3


# ── Tier 5 · production validation (24h / 72h paper drill) ───────
# Long-running: launched as a background job under supervisor or
# scheduled via cron. Use `tier5-24h` for a 24-hour paper-broker
# validation, `tier5-72h` for the 72-hour extended run.
.PHONY: tier5-24h tier5-72h
tier5-24h: ## Tier 5 (production): paper broker, 24h validation
	@echo "▸ Tier 5 · paper broker · 24h validation (background)"
	@nohup python3 $(BACKEND_DIR)/scripts/tier5_validation.py \
	  --duration-hours 24 --backend mongo \
	  --json $(REPORTS_DIR)/tier5_24h_$$(date +%Y%m%d).json \
	  > /var/log/tier5_24h.log 2>&1 &
	@echo "  PID=$$!  ·  log: /var/log/tier5_24h.log"

tier5-72h: ## Tier 5 (production): paper broker, 72h validation
	@echo "▸ Tier 5 · paper broker · 72h validation (background)"
	@nohup python3 $(BACKEND_DIR)/scripts/tier5_validation.py \
	  --duration-hours 72 --backend mongo \
	  --json $(REPORTS_DIR)/tier5_72h_$$(date +%Y%m%d).json \
	  > /var/log/tier5_72h.log 2>&1 &
	@echo "  PID=$$!  ·  log: /var/log/tier5_72h.log"


.PHONY: pyramid
pyramid: tier1 tier2 tier3 ## Run tiers 1-3 sequentially (fast → deeper)
	@echo "▸ Regression pyramid complete (tiers 1-3)"

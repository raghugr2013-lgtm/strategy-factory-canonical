/*
 * navigation.js — Sprint 3 Phase-1 Engineering Workspace navigation model.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · UX-Review-2026-07-22 (Engineering Workspace)
 *
 * The rail now renders three grouped sections:
 *   1) MISSION CONTROL — the Operator OS surfaces (unchanged from Sprint 2).
 *   2) ENGINEERING     — advanced strategy-building capabilities. Phase 1 ships
 *                        the information architecture with professional empty
 *                        states; Phase 2 lights them up against live backend.
 *   3) ADMIN           — role-gated tooling (visible only to admin operators).
 *
 * The legacy flat ROUTES export in ./routes.js is preserved for backwards
 * compatibility (Header eyebrow lookup, ⌘K jump-to-surface). NAV_GROUPS is
 * additive and consumed by LeftRail + the Engineering group in ⌘K.
 */
import {
  Activity, ShieldCheck, Users as UsersIcon, LineChart, Settings as SettingsIcon,
  Compass, Bot, Database, Radio, Waves, FlaskConical, SlidersHorizontal, ClipboardCheck,
  PieChart, Building2, Rocket, FileText, Plug, ScrollText, GitBranch,
} from 'lucide-react';

/**
 * Item flags:
 *   - deepLink:  when true, this rail entry navigates to an existing surface
 *                rather than a Phase-1 empty-state (no duplication).
 *   - emptyState: when true, the underlying surface renders the Phase-2
 *                empty-state template with capability metadata.
 *   - phase2:    the Phase 2 backend hook that will replace the empty state.
 *   - roles:     which roles see the entry; omitted = everyone.
 */
export const NAV_GROUPS = [
  {
    id: 'mission-control',
    label: 'Mission Control',
    testId: 'nav-group-mission-control',
    items: [
      { path: '/c/mission',    label: 'Mission',    icon: Compass,     testId: 'nav-mission',    surface: 'mission' },
      { path: '/c/masterbot',  label: 'Master Bot', icon: Bot,         testId: 'nav-masterbot',  surface: 'masterbot' },
      { path: '/c/timeline',   label: 'Timeline',   icon: Activity,    testId: 'nav-timeline',   surface: 'timeline' },
      { path: '/c/approvals',  label: 'Approvals',  icon: ShieldCheck, testId: 'nav-approvals',  surface: 'approvals' },
      { path: '/c/workforce',  label: 'Workforce',  icon: UsersIcon,   testId: 'nav-workforce',  surface: 'workforce' },
    ],
  },
  {
    id: 'engineering',
    label: 'Engineering',
    testId: 'nav-group-engineering',
    items: [
      { path: '/c/engineering/market-data',   label: 'Market Data',       icon: Radio,             testId: 'nav-market-data',   surface: 'market-data' },
      { path: '/c/engineering/coverage',      label: 'Coverage',          icon: Waves,             testId: 'nav-coverage',      surface: 'coverage' },
      { path: '/c/engineering/datasets',      label: 'Datasets',          icon: Database,          testId: 'nav-datasets',      surface: 'datasets' },
      { path: '/c/engineering/strategy-lab',  label: 'Strategy Lab',      icon: FlaskConical,      testId: 'nav-strategy-lab',  surface: 'strategy-lab' },
      { path: '/c/engineering/strategy-pipeline', label: 'Strategy Pipeline', icon: GitBranch,       testId: 'nav-strategy-pipeline', surface: 'strategy-pipeline' },
      { path: '/c/engineering/optimization',  label: 'Optimization',      icon: SlidersHorizontal, testId: 'nav-optimization',  surface: 'optimization' },
      { path: '/c/engineering/validation',    label: 'Validation',        icon: ClipboardCheck,    testId: 'nav-validation',    surface: 'validation',    emptyState: true, phase2: 'GET /api/validation · POST /api/backtest' },
      { path: '/c/mission?focus=portfolio',   label: 'Portfolio',         icon: PieChart,          testId: 'nav-portfolio',     surface: 'mission',       deepLink: true },
      { path: '/c/engineering/prop-firms',    label: 'Prop Firms',        icon: Building2,         testId: 'nav-prop-firms',    surface: 'prop-firms',    emptyState: true, phase2: 'GET /api/prop-firms · GET /api/prop-firms/{id}/challenges' },
      { path: '/c/engineering/deployments',   label: 'Deployments',       icon: Rocket,            testId: 'nav-deployments',   surface: 'deployments',   emptyState: true, phase2: 'GET /api/deployments · POST /api/deployments/{id}/rollback' },
      { path: '/c/strategies',                label: 'Strategy Passports', icon: LineChart,        testId: 'nav-strategy-passports', surface: 'strategies', deepLink: true },
    ],
  },
  {
    id: 'admin',
    label: 'Admin',
    testId: 'nav-group-admin',
    roles: ['admin'],
    items: [
      { path: '/c/settings',           label: 'Settings',     icon: SettingsIcon, testId: 'nav-settings',      surface: 'settings' },
      { path: '/c/admin/users',        label: 'Users',        icon: UsersIcon,    testId: 'nav-users',         surface: 'users',        emptyState: true, phase2: 'GET /api/admin/users · CRUD' },
      { path: '/c/admin/integrations', label: 'Integrations', icon: Plug,         testId: 'nav-integrations',  surface: 'integrations', emptyState: true, phase2: 'POST /api/admin/providers/probe · connector CRUD' },
      { path: '/c/admin/logs',         label: 'Logs',         icon: ScrollText,   testId: 'nav-logs',          surface: 'logs',         emptyState: true, phase2: 'GET /api/admin/logs · streaming tail' },
    ],
  },
];

/**
 * Engineering-surface metadata used by both the routing layer and the
 * EngineeringSurface empty-state template. Keyed by URL param `slug` (last
 * segment of /c/engineering/:slug and /c/admin/:slug).
 */
export const ENGINEERING_SURFACES = {
  'market-data': {
    group: 'Engineering',
    title: 'Market Data',
    icon: Radio,
    headline: 'Real-time price, volume, and orderbook telemetry per venue.',
    briefing: 'A live grid of every symbol the Factory subscribes to — spot, futures, and options. Streaming quotes, last-tick freshness, cross-venue arbitrage indicators, and provider health.',
    capabilities: [
      'Per-venue subscription grid with streaming last-price + spread',
      'Provider heartbeat map (Kraken · Coinbase · Alpaca · IEX · Alpha Vantage)',
      'Symbol search + facet filter by asset class and market phase',
      'Cross-venue arbitrage indicator with configurable threshold',
    ],
    phase2Sources: ['GET /api/market-data/subscriptions', 'WSS /stream/ticks', 'POST /api/market-data/subscribe'],
    related: [
      { label: 'Ingestion status', path: '/c/timeline?actor=INGESTION' },
      { label: 'Provider probe (admin)', path: '/c/admin/integrations' },
    ],
  },
  'coverage': {
    group: 'Engineering',
    title: 'Coverage',
    icon: Waves,
    headline: 'Which markets, timeframes, and history depths the Factory can trust.',
    briefing: 'A capability map of every (symbol × timeframe × history-window) tuple the Factory can serve to a strategy — with gap severity, last-refresh times, and re-hydration triggers.',
    capabilities: [
      'Coverage matrix — symbol × timeframe with gap-severity heatmap',
      'History depth timeline (5y · 1y · 90d · 24h) per symbol',
      'Gap remediation panel with one-click re-hydrate proposals',
      'Coverage SLA violations flagged to Approvals',
    ],
    phase2Sources: ['GET /api/coverage/matrix', 'GET /api/coverage/gaps', 'POST /api/coverage/rehydrate'],
    related: [
      { label: 'Datasets', path: '/c/engineering/datasets' },
      { label: 'Timeline · INGESTION', path: '/c/timeline?actor=INGESTION' },
    ],
  },
  'datasets': {
    group: 'Engineering',
    title: 'Datasets',
    icon: Database,
    headline: 'Curated candle bundles, feature stores, and dataset downloads.',
    briefing: 'The persistent catalogue of every dataset the Factory has ever materialised — feature stores, candle bundles, and derived indicator sets — with lineage, size, and reproducibility hash.',
    capabilities: [
      'Dataset catalogue table with lineage back to source ticks',
      'Download center — Parquet · CSV · Arrow with size + row-count',
      'Reproducibility manifest per dataset (sha256, provider, generator)',
      'Retention policy visualiser and archival controls',
    ],
    phase2Sources: ['GET /api/datasets', 'GET /api/datasets/{id}/manifest', 'POST /api/datasets/download'],
    related: [
      { label: 'Coverage', path: '/c/engineering/coverage' },
      { label: 'Validation', path: '/c/engineering/validation' },
    ],
  },
  'strategy-lab': {
    group: 'Engineering',
    title: 'Strategy Lab',
    icon: FlaskConical,
    headline: 'Compose, generate, and iterate strategies with the Factory\u2019s LLM copilot.',
    briefing: 'The authoring workspace for strategies — compressed-natural-language prompts, generated code preview, quick-backtest, and iterative refinement — before a strategy earns a Passport.',
    capabilities: [
      'CNL prompt composer with hypothesis · market · regime · budget fields',
      'Generated-code preview with diff-vs-parent-strategy',
      'Quick-backtest panel (30-day slice) with go/no-go verdict',
      'Iterate → Optimize → Promote workflow buttons',
    ],
    phase2Sources: ['POST /api/strategies/generate', 'POST /api/strategies/{id}/iterate', 'POST /api/backtest/quick'],
    related: [
      { label: 'Strategy Passports', path: '/c/strategies' },
      { label: 'Optimization', path: '/c/engineering/optimization' },
    ],
  },
  'optimization': {
    group: 'Engineering',
    title: 'Optimization',
    icon: SlidersHorizontal,
    headline: 'Parameter sweeps, walk-forward analysis, and regime-aware tuning.',
    briefing: 'The optimization cockpit — kick off parameter sweeps against any strategy, watch cycle progress live, and promote the winning parameter set through a governed Approval.',
    capabilities: [
      'Cycle queue with progress bars per sweep',
      'Objective-function selector (Sharpe · Calmar · Custom)',
      'Walk-forward + regime-partitioned view of the parameter surface',
      'Winning parameter set → Approval bundle with lineage',
    ],
    phase2Sources: ['POST /api/optimize', 'GET /api/optimize/{cycleId}', 'WSS /stream/optimize'],
    related: [
      { label: 'Strategy Lab', path: '/c/engineering/strategy-lab' },
      { label: 'Approvals', path: '/c/approvals' },
    ],
  },
  'validation': {
    group: 'Engineering',
    title: 'Validation',
    icon: ClipboardCheck,
    headline: 'Backtest attestation, out-of-sample proof, and paper-trading receipts.',
    briefing: 'Every validation artefact the Factory has produced — backtest signatures, out-of-sample runs, paper-trading day summaries — with the attester and hash trail attached.',
    capabilities: [
      'Attested backtest list — signature, hash, validator, timestamp',
      'Out-of-sample panel with in-sample / OOS Sharpe delta',
      'Paper-trading receipts (per-day PnL, slippage, hit-rate)',
      'Re-run validation with one-click proposal',
    ],
    phase2Sources: ['GET /api/validation', 'GET /api/backtest/{id}', 'POST /api/backtest'],
    related: [
      { label: 'Strategy Passports', path: '/c/strategies' },
      { label: 'Approvals', path: '/c/approvals' },
    ],
  },
  'prop-firms': {
    group: 'Engineering',
    title: 'Prop Firms',
    icon: Building2,
    headline: 'Prop-firm challenges, funded accounts, and payout scheduling.',
    briefing: 'The book of every prop-firm relationship — active challenges, funded balances, drawdown telemetry, and payout cadence — with per-firm rule guardrails wired into the risk engine.',
    capabilities: [
      'Firm roster — FTMO · MyFundedFX · The Funded Trader · Topstep · custom',
      'Challenge tracker with days-elapsed and target progress',
      'Rule guardrail matrix (daily loss · overall loss · lot cap · news filter)',
      'Payout schedule and historical payout ledger',
    ],
    phase2Sources: ['GET /api/prop-firms', 'GET /api/prop-firms/{id}/challenges', 'POST /api/prop-firms/{id}/payout'],
    related: [
      { label: 'Deployments', path: '/c/engineering/deployments' },
      { label: 'Approvals', path: '/c/approvals' },
    ],
  },
  'deployments': {
    group: 'Engineering',
    title: 'Deployments',
    icon: Rocket,
    headline: 'Live and paper deployments — where every strategy is running right now.',
    briefing: 'The deployment ledger — every strategy currently running, its venue, its capital envelope, and its rollback point. Complements Approvals with a permanent history and a one-click rollback proposal.',
    capabilities: [
      'Deployment table — strategy · venue · capital · status · started-at',
      'Rollback proposal button (drops HIGH-risk ApprovalCard)',
      'Green/blue swap view for live vs paper',
      'Deployment history with per-strategy timeline',
    ],
    phase2Sources: ['GET /api/deployments', 'POST /api/deployments/{id}/rollback', 'GET /api/deployments/{id}/history'],
    related: [
      { label: 'Approvals · promote-to-live', path: '/c/approvals?risk=high' },
      { label: 'Timeline', path: '/c/timeline' },
    ],
  },
  'users': {
    group: 'Admin',
    title: 'Users',
    icon: UsersIcon,
    headline: 'Operator accounts, roles, and access provisioning.',
    briefing: 'CRUD for operator accounts — create, approve, revoke, delete — plus role assignment (operator · engineer · admin) and last-sign-in telemetry.',
    capabilities: [
      'User grid with role, status, last sign-in',
      'Invite operator flow with email + role picker',
      'Revoke / restore actions with governance trail',
      'Session inspector with active-token list per user',
    ],
    phase2Sources: ['GET /api/admin/users', 'POST /api/admin/users', 'DELETE /api/admin/users/{id}'],
    related: [
      { label: 'Integrations', path: '/c/admin/integrations' },
      { label: 'Logs', path: '/c/admin/logs' },
    ],
  },
  'integrations': {
    group: 'Admin',
    title: 'Integrations',
    icon: Plug,
    headline: 'Provider probes, connector health, and credential rotation.',
    briefing: 'The connector cockpit — every third-party the Factory speaks to (market-data providers, LLMs, prop-firm APIs, notification channels) with a probe button and a credential rotation trail.',
    capabilities: [
      'Connector matrix with health, last-probe, credential-age',
      'One-click probe with round-trip latency + payload assertion',
      'Credential rotation flow (drops MODERATE-risk ApprovalCard)',
      'Webhook & channel registry (Slack · Discord · Telegram · email)',
    ],
    phase2Sources: ['POST /api/admin/providers/probe', 'GET /api/admin/connectors', 'POST /api/admin/connectors/{id}/rotate'],
    related: [
      { label: 'Users', path: '/c/admin/users' },
      { label: 'Logs', path: '/c/admin/logs' },
    ],
  },
  'logs': {
    group: 'Admin',
    title: 'Logs',
    icon: ScrollText,
    headline: 'Streaming access, audit, and error logs across the Factory.',
    briefing: 'A pane-of-glass into every log stream the Factory emits — audit trail, access log, worker error, and orchestrator lifecycle — with saved queries and export.',
    capabilities: [
      'Multi-stream tail (audit · access · worker · orchestrator)',
      'Structured query bar with field-scoped filters',
      'Saved query bookmarks and export to CSV / NDJSON',
      'Retention window selector and archive proposals',
    ],
    phase2Sources: ['GET /api/admin/logs?stream=…', 'WSS /stream/logs'],
    related: [
      { label: 'Timeline', path: '/c/timeline' },
      { label: 'Users', path: '/c/admin/users' },
    ],
  },
};

/** Convenience: flatten NAV_GROUPS into a role-scoped list. */
export const flattenNav = (role) => NAV_GROUPS
  .filter((g) => !g.roles || g.roles.includes(role))
  .flatMap((g) => g.items);

/** Convenience for CmdKPalette — one entry per non-deep-link, non-existing surface. */
export const ENGINEERING_JUMP_ITEMS = NAV_GROUPS
  .find((g) => g.id === 'engineering')
  .items.filter((i) => !i.deepLink);

export const ADMIN_JUMP_ITEMS = NAV_GROUPS
  .find((g) => g.id === 'admin')
  .items;

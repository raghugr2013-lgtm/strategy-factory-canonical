/**
 * COMMAND · Phase U.2 — Module Registry
 * ----------------------------------------------------------------------------
 * Single source of truth that maps each of the 10 modules to:
 *   • its label and rail glyph (re-uses U.1 Glyphs)
 *   • its posture-availability flags (already defined in LeftRail.MODULES;
 *     kept consistent here)
 *   • a `load()` async factory that returns the React component to render
 *     inside the shell. Using React.lazy() keeps the initial shell bundle
 *     small — large operator components (StrategyDashboard ≈ 2.4k LOC,
 *     StrategyExplorer ≈ 1.4k LOC, AutoFactoryPhase55 ≈ 1k LOC) only load
 *     when their module is first opened.
 *   • a `subtitle` (one-line tactical label shown in the module header)
 *   • `briefingReadOnly` flag for posture-aware UI hints
 *
 * Important: this registry IMPORTS existing operator components — it does
 * not modify them. Each module renders the existing component AS-IS inside
 * a COMMAND panel. Future phases (U.3) may replace these with bespoke
 * shell-native screens; for U.2 we wrap.
 */
import React from 'react';
import {
  GlyphDashboard, GlyphLab, GlyphExplorer, GlyphMutate, GlyphPortfolio,
  GlyphPropFirm, GlyphExec, GlyphAI, GlyphDiag, GlyphGovernance,
  GlyphMasterBot, GlyphAdmin, GlyphScaling,
} from './Glyphs';
// Pilot Restoration Step 2 (GATE 0) — restored 1-vCPU Mission Control stack:
// MissionBriefing + the 8 legacy operator panels in locked order.
// See /app/memory/IMPLEMENTATION_SEQUENCE.md Step 2.
import DashboardComposite from './dashboard/DashboardComposite';

// Lazy wrappers — keep them syntactic so webpack can split them.
const lazy = (factory) => React.lazy(factory);

// Strategy Dashboard is the entry-point operator surface today.
const StrategyDashboard       = lazy(() => import('../../components/StrategyDashboard'));
const DeploymentReadinessCard = lazy(() => import('../../components/DeploymentReadinessCard'));
const OrchestratorPanel       = lazy(() => import('../../components/OrchestratorPanel'));

// COMMAND-native sections (Phase U.5.d onward).
const LlmCallRiver            = lazy(() => import('./ai/LlmCallRiver'));

// M2 — Future-phase reservation cards (Phase 13 · 14 · 15). Visual layout
// placeholders only; no implementation. Locked in:
//   /app/memory/visual_approval_package/10_FUTURE_PHASES_DOSSIER_VALUATION_MARKETPLACE.md
//   /app/memory/visual_approval_package/12_M1_ARCHITECTURAL_PRINCIPLES.md (P3, P4, P5)
// Restoration Step 4b — the reservation cards now render inside collapsed
// bottom-of-module accordions (cards themselves untouched; pure wrapper).
// See /app/memory/IMPLEMENTATION_SEQUENCE.md Step 4.
const ExplorerReservationsAccordion  = lazy(() => import('../reservations/ReservationsAccordion').then(m => ({ default: m.ExplorerReservationsAccordion })));
const PortfolioReservationsAccordion = lazy(() => import('../reservations/ReservationsAccordion').then(m => ({ default: m.PortfolioReservationsAccordion })));
const ExecutionBrokerChips         = lazy(() => import('../reservations/ExecutionBrokerChips'));
// Restoration Step 4a — one-glance Execution landing (read-only KPI strip).
const ExecutionOverview            = lazy(() => import('../../components/ExecutionOverview'));

// Research Lab cluster
const StrategyPanel           = lazy(() => import('../../components/StrategyPanel'));
const StrategyAnalysis        = lazy(() => import('../../components/StrategyAnalysis'));
const BacktestPanel           = lazy(() => import('../../components/BacktestPanel'));
const CbotPanel               = lazy(() => import('../../components/CbotPanel'));
const OptimizationPanel       = lazy(() => import('../../components/OptimizationPanel'));
const ValidationPanel         = lazy(() => import('../../components/ValidationPanel'));
// P1.1 — Workspace Composite (legacy 1-vCPU MORE-1 unified lab surface).
// Mounts the 8-component grid as a single section at /c/lab/workspace.
const WorkspaceComposite      = lazy(() => import('../../components/WorkspaceComposite'));

// Explorer
const StrategyExplorer        = lazy(() => import('../../components/StrategyExplorer'));
const SavedStrategies         = lazy(() => import('../../components/SavedStrategies'));

// Mutation
const AutoMutationRunner      = lazy(() => import('../../components/AutoMutationRunner'));
const MultiCycleRunner        = lazy(() => import('../../components/MultiCycleRunner'));
const AutoFactory             = lazy(() => import('../../components/AutoFactory'));
const AutoFactoryPhase55      = lazy(() => import('../../components/AutoFactoryPhase55'));

// Portfolio
const PortfolioBuilder        = lazy(() => import('../../components/PortfolioBuilder'));
const PortfolioPanel          = lazy(() => import('../../components/PortfolioPanel'));
const PortfolioIntelligence   = lazy(() => import('../../components/PortfolioIntelligence'));

// Prop firm
const PropFirmsAdmin          = lazy(() => import('../../components/PropFirmsAdmin'));
const FirmMatchPanel          = lazy(() => import('../../components/FirmMatchPanel'));

// Execution
const PaperExecution          = lazy(() => import('../../components/PaperExecution'));
const TradeRunner             = lazy(() => import('../../components/TradeRunner'));
const LiveTrackingPanel       = lazy(() => import('../../components/LiveTrackingPanel'));

// AI Workforce
const AutoSchedulerControl    = lazy(() => import('../../components/AutoSchedulerControl'));

// Diagnostics
const ParityCertificationCard = lazy(() => import('../../components/ParityCertificationCard'));
const IngestionHealthCard     = lazy(() => import('../../components/IngestionHealthCard'));
const PipelineLogsPanel       = lazy(() => import('../../components/PipelineLogsPanel'));
const DataMaintenancePanel    = lazy(() => import('../../components/DataMaintenancePanel'));
const StrategyIngestionCard   = lazy(() => import('../../components/StrategyIngestionCard'));
// Pre-RC1 parity restoration — re-expose legacy Manual Data Workbench
// (BID + BI5 + CSV upload + Server import + date-range download + gap fix).
// The component was authored in the old UI and never wired into the shell.
const DataUploadPanel         = lazy(() => import('../../components/DataUpload'));
// Pre-RC1 parity restoration — re-expose legacy Monitoring & Control surface
// (Stop-all / Resume / Save Thresholds / Breach Log / Fleet).
const MonitoringControlPanel  = lazy(() => import('../../components/Monitoring'));

// Governance
const GovernanceCard          = lazy(() => import('../../components/GovernanceCard'));
const UniverseGovernancePanel = lazy(() => import('../../components/UniverseGovernancePanel'));
// DSR-1 — Symbol Registry Panel (new operator surface for dynamic symbol onboarding).
const SymbolRegistryPanel     = lazy(() => import('../../components/SymbolRegistryPanel'));
const RulesReviewPanel        = lazy(() => import('../../components/RulesReviewPanel'));
const EnvPriorityPanel        = lazy(() => import('../../components/EnvPriorityPanel'));
const ReadinessPanel          = lazy(() => import('../../components/ReadinessPanel'));

// RC1 Parity Closure — re-expose existing operator components + thin
// design-system-consistent panels for backend-only surfaces.
// All wrappers and thin panels live in /components/OperatorParityPanels.jsx
// and re-use OperatorEndpointPanel for consistency.
const MasterBotDashboard        = lazy(() => import('../../components/MasterBotDashboard'));
const AdminUsers                = lazy(() => import('../../components/AdminUsers'));
const AutoSelection             = lazy(() => import('../../components/AutoSelection'));
const StrategyComparison        = lazy(() => import('../../components/StrategyComparison'));
const FactorySupervisorPanel    = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.FactorySupervisorPanel })));
const ScalingPanel              = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.ScalingPanel })));
const Phase12TuningPanel        = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.Phase12TuningPanel })));
const GemFactoryPanel           = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.GemFactoryPanel })));
const AdminFlagGovernancePanel  = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.AdminFlagGovernancePanel })));
const AdminExecutionRealismPanel= lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.AdminExecutionRealismPanel })));
const DataBackupPanel           = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.DataBackupPanel })));
const SoakDiagnosticsPanel      = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.SoakDiagnosticsPanel })));
const CpuPoolStatePanel         = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.CpuPoolStatePanel })));
const ChallengeMatchingPanel    = lazy(() => import('../../components/OperatorParityPanels').then(m => ({ default: m.ChallengeMatchingPanel })));

// Phase R1–R4 — Recovery sprint composites.
// MarketDataWorkbench composes DataUpload + DataMaintenance + DataBackup into one section (Manual · Automated · Archive).
// MonitoringSuite composes Monitoring + Soak + CPU Pool + Scaling into one diag/monitoring section (Runtime · Soak · Compute · Cluster).
// GovernanceAdminSuite composes AdminUsers + Flag Gov + Exec Realism + Phase 12 Tuning into governance/admin (Users · Flags · Realism · Tuning).
// MutateMasterBotCompile surfaces the compile flow as its own discoverable section per Handoff Screen 15.
const MarketDataWorkbench       = lazy(() => import('../../components/MarketDataWorkbench'));
const MonitoringSuite           = lazy(() => import('../../components/MonitoringSuite'));
// BI5 R1 — per-symbol BI5 ingest health surface.
const BI5HealthPanel            = lazy(() => import('../../components/BI5HealthPanel'));
// BI5 R2 / B-8 — Strategy & Data Certification panel (sweep history + manual trigger).
const Bi5CertPanel              = lazy(() => import('../../components/Bi5CertPanel'));
const GovernanceAdminSuite      = lazy(() => import('../../components/GovernanceAdminSuite'));
const MutateMasterBotCompile    = lazy(() => import('../../components/MutateMasterBotCompile'));

/**
 * Each `sections` entry is { id, title, Component, only? }.
 * `only` filters the section by posture: ['workstation'], ['workstation','tablet'], or undefined (all).
 */
export const MODULES = [
  // R1 — `dashboard/readiness` duplicate removed. Single source of truth is
  // `diag/readiness` per ASF_UI_Handoff Screen 27.
  {
    id: 'dashboard',
    label: 'Dashboard',
    Glyph: GlyphDashboard,
    subtitle: 'Mission control · briefing · restored operator workbench',
    briefing: true, tablet: true,
    briefingReadOnly: true,
    sections: [
      // Pilot Restoration Step 2 (GATE 0) — the section now renders the
      // restored 1-vCPU stacked workbench: MissionBriefing (read-only
      // synthesis, kept first) + the 8 legacy panels in locked order.
      // Briefing posture still renders MissionBriefing only (read-only
      // contract); tablet folds the stack into accordions.
      // Section id stays `briefing` so the testid + deep links are stable.
      { id: 'briefing',     title: 'Mission Control',         Component: DashboardComposite },
      // R1 — `dashboard/readiness` removed. Single source of truth: `diag/readiness`.
    ],
  },
  {
    id: 'lab',
    label: 'Research Lab',
    Glyph: GlyphLab,
    subtitle: 'Strategy generation · backtest · cbot · validate',
    briefing: false, tablet: false,
    sections: [
      // P1.1 — Workspace Composite restores the legacy 1-vCPU MORE-1
      // single-page lab. First section so the legacy "Workspace" tab lands here.
      { id: 'workspace', title: 'Workspace · Unified Lab',  Component: WorkspaceComposite, only: ['workstation'] },
      { id: 'panel',     title: 'Strategy Panel',     Component: StrategyPanel },
      { id: 'analysis',  title: 'Analysis',           Component: StrategyAnalysis },
      { id: 'backtest',  title: 'Backtest',           Component: BacktestPanel },
      { id: 'cbot',      title: 'cBot',               Component: CbotPanel },
      { id: 'optim',     title: 'Optimization',       Component: OptimizationPanel },
      { id: 'validate',  title: 'Validation',         Component: ValidationPanel },
    ],
  },
  {
    id: 'explorer',
    label: 'Strategy Explorer',
    Glyph: GlyphExplorer,
    subtitle: 'Ancestry · catalog · saved · lineage · compare',
    briefing: false, tablet: true,
    briefingReadOnly: true,
    sections: [
      { id: 'explorer', title: 'Explorer',         Component: StrategyExplorer },
      { id: 'saved',    title: 'Saved Strategies', Component: SavedStrategies },
      // GAP-P1-8 · Strategy Comparison promoted to a dedicated section.
      { id: 'compare',  title: 'Strategy Comparison', Component: StrategyComparison, only: ['workstation', 'tablet'] },
      // Restoration Step 4b — the M3 Strategy Score + Phase 13 Dossier +
      // Phase 15 Marketplace reservation cards now live inside ONE collapsed
      // accordion at the bottom of Explorer (masterplan §1.8). Cards are
      // unchanged; only the wrapper collapses them out of the browse scroll.
      { id: 'reservations', title: 'Phase 13 · 14 · 15 — Reservations', Component: ExplorerReservationsAccordion, only: ['workstation', 'tablet'] },
    ],
  },
  {
    id: 'mutate',
    label: 'Mutation Engine',
    Glyph: GlyphMutate,
    subtitle: 'Auto-mutation · multi-cycle · factory · selection · master bot',
    briefing: false, tablet: false,
    sections: [
      { id: 'auto',          title: 'Auto Mutation Runner',    Component: AutoMutationRunner },
      { id: 'cycle',         title: 'Multi-Cycle Runner',      Component: MultiCycleRunner },
      { id: 'factory',       title: 'Auto Factory',            Component: AutoFactory },
      { id: 'factory-55',    title: 'Auto Factory · Phase 55', Component: AutoFactoryPhase55 },
      { id: 'auto-select',   title: 'Auto Selection',          Component: AutoSelection,    only: ['workstation', 'tablet'] },
      // R1 — Master Bot folded into Mutation Engine per ASF_UI_Handoff Screens 14 + 15.
      { id: 'master-bot',         title: 'Master Bot',           Component: MasterBotDashboard,     only: ['workstation'] },
      { id: 'master-bot-compile', title: 'Master Bot Compile',   Component: MutateMasterBotCompile, only: ['workstation'] },
      // R4 — Developer-console surfaces (GEM Factory + Factory Supervisor) demoted
      // from primary operator nav. Their components remain wired and are reachable
      // via Command Palette (⌘K) under "Advanced / Power User" entry; status &
      // events surface via LeftRail status dots and the live Notification Drawer.
    ],
  },
  {
    id: 'portfolio',
    label: 'Portfolio OS',
    Glyph: GlyphPortfolio,
    subtitle: 'Builder · panel · intelligence',
    briefing: true, tablet: true,
    briefingReadOnly: true,
    sections: [
      { id: 'builder',  title: 'Portfolio Builder',      Component: PortfolioBuilder,    only: ['workstation'] },
      { id: 'panel',    title: 'Portfolio Panel',        Component: PortfolioPanel },
      { id: 'intel',    title: 'Portfolio Intelligence', Component: PortfolioIntelligence },
      // M2 · Phase 14 reservation — Prop Firm + Investor scorecards (dual-track)
      // and Automated Pricing Engine inputs. No manual-pricing fields.
      // Restoration Step 4b — now rendered inside a collapsed bottom accordion
      // (card unchanged; pure wrapper).
      { id: 'scorecards-reservations', title: 'Phase 14 · Reservations', Component: PortfolioReservationsAccordion, only: ['workstation', 'tablet'] },
    ],
  },
  // Phase R1 — Master Bot folded into Mutation Engine per ASF_UI_Handoff
  // Screens 14 + 15. Top-level `masterbot` module removed; sections moved here.
  {
    id: 'propfirm',
    label: 'Prop Firm',
    Glyph: GlyphPropFirm,
    subtitle: 'Firm catalogue · firm match · challenge matching',
    briefing: false, tablet: true,
    briefingReadOnly: true,
    sections: [
      { id: 'admin',  title: 'Prop Firms', Component: PropFirmsAdmin, only: ['workstation'] },
      { id: 'match',  title: 'Firm Match', Component: FirmMatchPanel },
      // Pilot Restoration Step 3 (GATE 0) — Challenge Matching surfaced at
      // its planned home (01_TAB_ROSTER.md MORE-3; recipe pre-approved in
      // MISSING_OR_HIDDEN_FEATURES.md §2.1). Backend endpoints were already
      // live; this only mounts the existing panel.
      { id: 'challenge', title: 'Challenge Matching', Component: ChallengeMatchingPanel, only: ['workstation', 'tablet'] },
      // R1 — Rules Review now has a single source of truth at governance/rules.
      // The duplicate propfirm/rules surface was removed; the component is
      // still mounted there via governance.
    ],
  },
  {
    id: 'exec',
    label: 'Execution Center',
    Glyph: GlyphExec,
    subtitle: 'Paper · Trade Runner · Live (Deploy & Observe)',
    briefing: true, tablet: true,
    briefingReadOnly: true,
    sections: [
      // Restoration Step 4a — one-glance Execution landing. Read-only KPI
      // strip (Paper · Runner · Live counts) mounted FIRST so the Execution
      // tab answers "what is the execution layer doing?" in one glance —
      // the 1-vCPU ExecutionDashboard intent. Detail panels stay below.
      { id: 'overview', title: 'Execution Overview', Component: ExecutionOverview },
      // M2 · Broker chip row — reserves cTrader Live + cTrader Demo
      // + Windows VPS + Broker Telemetry slots without re-flow.
      { id: 'brokers', title: 'Broker Accounts (Track A + Track B + reserved cTrader/VPS)', Component: ExecutionBrokerChips },
      { id: 'paper',   title: 'Paper Execution', Component: PaperExecution },
      { id: 'runner',  title: 'Trade Runner',    Component: TradeRunner,        only: ['workstation', 'tablet'] },
      { id: 'live',    title: 'Live Tracking',   Component: LiveTrackingPanel },
      // R1 — Monitoring & Control moved to `diag/monitoring` per ASF_UI_Handoff
      // Screen 33. Component file unchanged; only the parent section changed.
    ],
  },
  {
    id: 'ai',
    label: 'AI Workforce',
    Glyph: GlyphAI,
    subtitle: 'Live river · orchestrator · auto-scheduler',
    briefing: false, tablet: true,
    briefingReadOnly: true,
    sections: [
      { id: 'river', title: 'AI Workforce Live River', Component: LlmCallRiver, only: ['workstation', 'tablet'] },
      { id: 'orch',  title: 'Orchestrator',        Component: OrchestratorPanel },
      { id: 'sched', title: 'Auto-Scheduler',      Component: AutoSchedulerControl, only: ['workstation'] },
    ],
  },
  {
    id: 'diag',
    label: 'Diagnostics',
    Glyph: GlyphDiag,
    subtitle: 'Readiness · parity · ingestion · pipeline · market data · monitoring',
    briefing: true, tablet: true,
    briefingReadOnly: true,
    sections: [
      { id: 'readiness',  title: 'Deployment Readiness',     Component: DeploymentReadinessCard },
      { id: 'parity',     title: 'Parity Certification',     Component: ParityCertificationCard },
      { id: 'ingestion',  title: 'Ingestion Health',         Component: IngestionHealthCard },
      { id: 'ingest-src', title: 'Strategy Ingestion',       Component: StrategyIngestionCard, only: ['workstation'] },
      { id: 'pipeline',   title: 'Pipeline Logs',            Component: PipelineLogsPanel,     only: ['workstation', 'tablet'] },
      // R3 — Market Data consolidated. The `MarketDataWorkbench` composite
      // mounts DataUpload (Manual) + DataMaintenance (Automated) + DataBackup
      // (Archive) as sub-tabs of one operator surface, preserving every
      // BID / BI5 / CSV / Server / date-range / gap-fix workflow.
      { id: 'market-data', title: 'Market Data',             Component: MarketDataWorkbench,   only: ['workstation'] },
      // R1 — Monitoring composite (was `exec/monitoring`; now lives in diag per
      // Handoff Screen 33). Sub-tabs: Runtime / Soak / Compute / Cluster.
      { id: 'monitoring', title: 'Monitoring',               Component: MonitoringSuite,       only: ['workstation', 'tablet'] },
      // BI5 R1 — per-symbol ingest health (coverage · last sync · ticks · status · health score reserved).
      { id: 'bi5-health', title: 'BI5 R1 · BI5 Health (per-symbol)', Component: BI5HealthPanel, only: ['workstation', 'tablet'] },
      // BI5 R2 / B-8 — Strategy & Data Certification panel (sweep history + manual trigger).
      { id: 'bi5-cert', title: 'BI5 R2 · Strategy & Data Certification', Component: Bi5CertPanel, only: ['workstation', 'tablet'] },
    ],
  },
  {
    id: 'governance',
    label: 'Governance',
    Glyph: GlyphGovernance,
    subtitle: 'Promotion · universe · rules · env · readiness · admin',
    briefing: false, tablet: false,
    sections: [
      { id: 'gov',         title: 'Governance',           Component: GovernanceCard },
      { id: 'universe',    title: 'Universe Governance',  Component: UniverseGovernancePanel },
      // DSR-1 — Symbol Registry — operator-facing dynamic symbol onboarding.
      // ASF stays private; customers never reach this surface.
      { id: 'symbol-registry', title: 'DSR · Symbol Registry', Component: SymbolRegistryPanel, only: ['workstation', 'tablet'] },
      { id: 'rules',       title: 'Rules Review',         Component: RulesReviewPanel },
      { id: 'env',         title: 'Env Priority',         Component: EnvPriorityPanel },
      { id: 'readiness',   title: 'Readiness',            Component: ReadinessPanel },
      // R1 — Admin composite (Users + Flags + Realism + Tuning).
      // Top-level `admin` module removed; AdminUsers now lives as Users sub-tab.
      // Flag Governance + Execution Realism + Phase 12 Tuning previously
      // visible as separate Governance sections are folded into this Admin
      // surface's Power-User sub-tabs; their underlying components are
      // unchanged and remain backend-wired.
      { id: 'admin',       title: 'Admin',                Component: GovernanceAdminSuite, only: ['workstation'] },
    ],
  },
];

export const MODULES_BY_ID = Object.fromEntries(MODULES.map((m) => [m.id, m]));

export function visibleSections(module, posture) {
  if (!module || !module.sections) return [];
  return module.sections.filter((s) => !s.only || s.only.includes(posture));
}

export function moduleAvailableInPosture(module, posture) {
  if (!module) return false;
  if (posture === 'workstation') return true;
  if (posture === 'tablet')      return !!module.tablet;
  if (posture === 'briefing')    return !!module.briefing;
  return true;
}

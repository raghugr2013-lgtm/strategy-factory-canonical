/*
 * AppRouter — top-level route tree.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · UX-Review-2026-07-22 (Engineering Workspace)
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from '../shell/AppShell';
import { LoginScreen } from '../auth/LoginScreen';
import { RequireAuth } from '../auth/RequireAuth';
import { MissionControl } from '../surfaces/MissionControl';
import { MasterBot } from '../surfaces/MasterBot';
import { Timeline } from '../surfaces/Timeline';
import { Approvals } from '../surfaces/Approvals';
import { ApprovalCenter } from '../surfaces/ApprovalCenter';
import { Workforce } from '../surfaces/Workforce';
import { Strategies } from '../surfaces/Strategies';
import { StrategyExplorer } from '../surfaces/StrategyExplorer';
import { StrategyPassport } from '../surfaces/StrategyPassport';
import { Settings } from '../surfaces/Settings';
import { PrimitiveGallery } from '../gallery/PrimitiveGallery';
import { MarketData } from '../surfaces/engineering/MarketData';
import { Coverage } from '../surfaces/engineering/Coverage';
import { Datasets } from '../surfaces/engineering/Datasets';
import { StrategyLab } from '../surfaces/engineering/StrategyLab';
import { StrategyPipeline } from '../surfaces/engineering/StrategyPipeline';
import { Optimization } from '../surfaces/engineering/Optimization';
import { Validation } from '../surfaces/engineering/Validation';
import { PropFirms } from '../surfaces/engineering/PropFirms';
import { Deployments } from '../surfaces/engineering/Deployments';
import { Users } from '../surfaces/admin/Users';
import { Integrations } from '../surfaces/admin/Integrations';
import { Logs } from '../surfaces/admin/Logs';
import { OrchestratorDashboard } from '../surfaces/factory/OrchestratorDashboard';
import { MetaLearningDashboard } from '../surfaces/factory/MetaLearningDashboard';
import { FactoryEvalDashboard } from '../surfaces/factory/FactoryEvalDashboard';
import { DataGovernanceDashboard } from '../surfaces/factory/DataGovernanceDashboard';
import { FactoryCockpit } from '../surfaces/factory/FactoryCockpit';
import { CuratedLibraryDashboard } from '../surfaces/factory/CuratedLibraryDashboard';
import { EvaluationHarness } from '../surfaces/EvaluationHarness';
import { TimelineExplorer } from '../surfaces/TimelineExplorer';
import { WorkforceExplorer } from '../surfaces/WorkforceExplorer';
import { DEFAULT_AUTHENTICATED_ROUTE, SIGN_IN_ROUTE } from './routes';

export const AppRouter = () => (
  <BrowserRouter>
    <Routes>
      <Route path={SIGN_IN_ROUTE} element={<LoginScreen />} />
      <Route path="/auth" element={<Navigate to={SIGN_IN_ROUTE} replace />} />

      <Route
        path="/c/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        {/* Mission Control */}
        <Route path="mission"    element={<MissionControl />} />
        <Route path="masterbot"  element={<MasterBot />} />
        <Route path="timeline"   element={<Timeline />} />
        {/* Phase E · Timeline Explorer — additive dual-route. Order matters
            only for consistency; React Router v6 resolves by specificity. */}
        <Route path="timeline/explorer" element={<TimelineExplorer />} />
        <Route path="approvals"  element={<Approvals />} />
        <Route path="approvals/center" element={<ApprovalCenter />} />
        <Route path="workforce"  element={<Workforce />} />
        {/* Phase F · Workforce Explorer — additive dual-route. */}
        <Route path="workforce/explorer" element={<WorkforceExplorer />} />

        {/* Strategies (deep-linked from Engineering rail as "Strategy Passports") */}
        <Route path="strategies" element={<Strategies />} />
        {/* IMPORTANT: `strategies/explorer` MUST stay declared before
            `strategies/:id`. React Router v6 does match by specificity
            rather than order, but leaving this order explicit prevents
            future refactors from accidentally swallowing the exact
            /explorer path via the :id catch-all. Verified by testing-
            agent iteration_8 (Phase C). */}
        <Route path="strategies/explorer" element={<StrategyExplorer />} />
        <Route path="strategies/:id" element={<StrategyPassport />} />

        {/* Factory — FE-B Slice 1..5 Autonomous Research Factory dashboards */}
        <Route path="factory" element={<FactoryCockpit />} />
        <Route path="factory/orchestrator" element={<OrchestratorDashboard />} />
        <Route path="factory/meta-learning" element={<MetaLearningDashboard />} />
        <Route path="factory/evaluation" element={<FactoryEvalDashboard />} />
        <Route path="factory/data-governance" element={<DataGovernanceDashboard />} />
        <Route path="factory/curated" element={<CuratedLibraryDashboard />} />

        {/* Engineering — Phase 1 empty states */}
        <Route path="engineering/market-data"   element={<MarketData />} />
        <Route path="engineering/coverage"      element={<Coverage />} />
        <Route path="engineering/datasets"      element={<Datasets />} />
        <Route path="engineering/strategy-lab"  element={<StrategyLab />} />
        <Route path="engineering/strategy-pipeline" element={<StrategyPipeline />} />
        <Route path="engineering/optimization"  element={<Optimization />} />
        <Route path="engineering/validation"    element={<Validation />} />
        <Route path="engineering/prop-firms"    element={<PropFirms />} />
        <Route path="engineering/deployments"   element={<Deployments />} />

        {/* Admin — Phase 1 empty states */}
        <Route path="settings"          element={<Settings />} />
        <Route path="admin/users"        element={<Users />} />
        <Route path="admin/integrations" element={<Integrations />} />
        <Route path="admin/logs"         element={<Logs />} />

        <Route path="gallery"    element={<PrimitiveGallery />} />

        {/* Evaluation Harness — Phase D1 (read-only) · net-new additive.
            D2 unlocks verdict controls; layout is stable across D1→D2. */}
        <Route path="evaluation" element={<EvaluationHarness />} />

        <Route index element={<Navigate to="mission" replace />} />
        <Route path="*" element={<Navigate to="/c/mission" replace />} />
      </Route>

      <Route path="/" element={<Navigate to={DEFAULT_AUTHENTICATED_ROUTE} replace />} />
      <Route path="*" element={<Navigate to={DEFAULT_AUTHENTICATED_ROUTE} replace />} />
    </Routes>
  </BrowserRouter>
);

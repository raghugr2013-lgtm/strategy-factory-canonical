/*
 * Prototype entry — Phases 1–4.
 * Route table follows D8 §3.3.
 *   /auth/sign-in              — public login screen (E2 §3)
 *   /c/mission                 — Mission Control (P4)
 *   /c/timeline                — Timeline (P4)
 *   /c/approvals               — Approval Center (P4)
 *   /c/workforce               — Master Bot (P4)
 *   /c/strategies              — Strategy Explorer (P4)
 *   /c/strategies/:id          — Strategy Passport (P4)
 *   /c/settings                — placeholder for Sprint 1
 *   /prototype/gallery         — primitive gallery (P2, retained)
 * Anonymous root redirects to sign-in; authenticated root goes to Mission.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AppShell } from './shell/AppShell';
import { PrimitiveGallery } from './gallery/PrimitiveGallery';
import { LoginScreen } from './auth/LoginScreen';
import { RequireAuth } from './auth/RequireAuth';
import { useAuthStore } from './workspace-state/authStore';
import { MissionControl } from './surfaces/MissionControl';
import { Timeline } from './surfaces/Timeline';
import { ApprovalCenter } from './surfaces/ApprovalCenter';
import { MasterBot } from './surfaces/MasterBot';
import { StrategyExplorer } from './surfaces/StrategyExplorer';
import { StrategyPassport } from './surfaces/StrategyPassport';
import { SettingsStub } from './surfaces/SettingsStub';
import { EvaluationHarness } from './surfaces/EvaluationHarness';
import './tokens.css';

const RootRedirect: React.FC = () => {
  const stance = useAuthStore((s) => s.stance);
  return <Navigate to={stance === 'authenticated' ? '/c/mission' : '/auth/sign-in'} replace />;
};

const Guarded: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <RequireAuth>{children}</RequireAuth>
);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/auth/sign-in" element={<LoginScreen />} />
          <Route path="/c/mission"    element={<Guarded><MissionControl /></Guarded>} />
          <Route path="/c/timeline"   element={<Guarded><Timeline /></Guarded>} />
          <Route path="/c/approvals"  element={<Guarded><ApprovalCenter /></Guarded>} />
          <Route path="/c/workforce"  element={<Guarded><MasterBot /></Guarded>} />
          <Route path="/c/strategies" element={<Guarded><StrategyExplorer /></Guarded>} />
          <Route path="/c/strategies/:id" element={<Guarded><StrategyPassport /></Guarded>} />
          <Route path="/c/settings"   element={<Guarded><SettingsStub /></Guarded>} />
          <Route path="/prototype/gallery" element={<Guarded><PrimitiveGallery /></Guarded>} />
          <Route path="/prototype/eval"    element={<Guarded><EvaluationHarness /></Guarded>} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);

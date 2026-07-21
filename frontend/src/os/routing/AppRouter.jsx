/*
 * AppRouter — top-level route tree.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · D8 §3.3
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
import { Workforce } from '../surfaces/Workforce';
import { Strategies } from '../surfaces/Strategies';
import { StrategyPassport } from '../surfaces/StrategyPassport';
import { Settings } from '../surfaces/Settings';
import { PrimitiveGallery } from '../gallery/PrimitiveGallery';
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
        <Route path="mission"    element={<MissionControl />} />
        <Route path="masterbot"  element={<MasterBot />} />
        <Route path="timeline"   element={<Timeline />} />
        <Route path="approvals"  element={<Approvals />} />
        <Route path="workforce"  element={<Workforce />} />
        <Route path="strategies" element={<Strategies />} />
        <Route path="strategies/:id" element={<StrategyPassport />} />
        <Route path="settings"   element={<Settings />} />
        <Route path="gallery"    element={<PrimitiveGallery />} />
        <Route index element={<Navigate to="mission" replace />} />
        <Route path="*" element={<Navigate to="/c/mission" replace />} />
      </Route>

      <Route path="/" element={<Navigate to={DEFAULT_AUTHENTICATED_ROUTE} replace />} />
      <Route path="*" element={<Navigate to={DEFAULT_AUTHENTICATED_ROUTE} replace />} />
    </Routes>
  </BrowserRouter>
);

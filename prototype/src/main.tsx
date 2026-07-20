/*
 * Prototype entry — Phases 1–3.
 * Route table follows D8 §3.3.
 *   /auth/sign-in            — public login screen (E2 §3)
 *   /prototype/gallery       — primitive gallery (auth-guarded per E2 §5)
 *   /c/mission               — mission placeholder (auth-guarded)
 * Anonymous root redirects to sign-in; authenticated root goes to gallery.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CheckCircle } from 'lucide-react';
import { AppShell } from './shell/AppShell';
import { StateTemplate } from './primitives/StateTemplate';
import { PrimitiveGallery } from './gallery/PrimitiveGallery';
import { LoginScreen } from './auth/LoginScreen';
import { RequireAuth } from './auth/RequireAuth';
import { useAuthStore } from './workspace-state/authStore';
import './tokens.css';

const MissionPlaceholder: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
    <div>
      <div style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        Mission Control · Operations
      </div>
      <div style={{ fontSize: 'var(--font-h2)', color: 'var(--content-hi)', marginTop: 'var(--space-2)' }}>
        You are all caught up.
      </div>
    </div>
    <StateTemplate
      variant="empty"
      icon={CheckCircle}
      tone="ok"
      code="mc-empty-nothing-pending"
      headline="The Factory is operating autonomously."
      purpose="No approvals require your attention."
      primaryAction={{ label: 'open Timeline', onClick: () => {} }}
      secondaryLink={{ label: "view yesterday's briefing", onClick: () => {} }}
      advancedFootnote="master-bot@v55 · plan #47 · step 3/7"
    />
  </div>
);

const RootRedirect: React.FC = () => {
  const stance = useAuthStore((s) => s.stance);
  return <Navigate to={stance === 'authenticated' ? '/prototype/gallery' : '/auth/sign-in'} replace />;
};

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/auth/sign-in" element={<LoginScreen />} />
          <Route
            path="/prototype/gallery"
            element={<RequireAuth><PrimitiveGallery /></RequireAuth>}
          />
          <Route
            path="/c/mission"
            element={<RequireAuth><MissionPlaceholder /></RequireAuth>}
          />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);

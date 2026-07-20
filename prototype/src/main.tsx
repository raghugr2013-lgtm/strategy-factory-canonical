/*
 * Prototype entry — Phase 1 foundation.
 * Route table follows D8 §3.3.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { CheckCircle } from 'lucide-react';
import { AppShell } from './shell/AppShell';
import { StateTemplate } from './primitives/StateTemplate';
import './tokens.css';

// Phase 1 placeholder — real surfaces land in Phase 4.
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

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/c/mission" replace />} />
          <Route path="/c/mission" element={<MissionPlaceholder />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);

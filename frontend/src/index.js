/*
 * Strategy Factory — Sprint 1 Foundation entry.
 * refs DESIGN_FREEZE_v1.0.md · D8_SPRINT_1_EXECUTION_PLAN.md · M1
 *
 * Legacy v01 CommandShell files remain under /app/frontend/src/{command,components,styles,...}
 * as unimported dead code; they were superseded by the Design Freeze (see
 * memory/FRONTEND_AUDIT_AND_ROADMAP.md SUPERSEDED banner).
 */
import React, { useEffect } from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import './os/tokens.css';
import { AppRouter } from './os/routing/AppRouter';

// Ensure token variables apply — attach `os-body` class before render.
if (typeof document !== 'undefined') {
  document.body.classList.add('os-body');
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const App = () => {
  useEffect(() => {
    document.body.classList.add('os-body');
    document.title = 'Strategy Factory';
    return () => document.body.classList.remove('os-body');
  }, []);
  return (
    <QueryClientProvider client={queryClient}>
      <AppRouter />
    </QueryClientProvider>
  );
};

const rootEl = document.getElementById('root');
if (rootEl) {
  const root = ReactDOM.createRoot(rootEl);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

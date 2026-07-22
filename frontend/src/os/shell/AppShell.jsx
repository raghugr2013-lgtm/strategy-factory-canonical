/*
 * AppShell — persistent operator-facing chrome.
 * refs DESIGN_FREEZE_v1.0.md §1.5 · D8 §3.5 (I4)
 *
 * Grid: [LeftRail 220px] [Main 1fr] with Header on top and StatusRail on
 * bottom. Danger ribbon appears above the header when kill posture is
 * armed. CmdKPalette is mounted globally.
 */
import React from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { LeftRail } from './LeftRail';
import { StatusRail } from './StatusRail';
import { DangerRibbon } from './DangerRibbon';
import { CmdKPalette } from '../palette/CmdKPalette';
import { FactoryWalkthrough } from '../onboarding/FactoryWalkthrough';

export const AppShell = () => (
  <div className="os-body"
       data-testid="app-shell"
       style={{
         minHeight: '100vh',
         display: 'grid',
         gridTemplateColumns: '220px 1fr',
         gridTemplateRows: 'auto auto 1fr auto',
       }}>
    <div style={{ gridColumn: '1 / -1' }}>
      <DangerRibbon />
    </div>

    <aside style={{ gridColumn: '1', gridRow: '2 / span 2', background: 'var(--surface-1)', borderRight: '1px solid var(--stroke-1)' }}>
      <LeftRail />
    </aside>

    <header style={{ gridColumn: '2', gridRow: '2' }}>
      <Header />
    </header>

    <main data-testid="surface-outlet" style={{ gridColumn: '2', gridRow: '3', overflow: 'auto', background: 'var(--surface-0)' }}>
      <Outlet />
    </main>

    <div style={{ gridColumn: '1 / -1', gridRow: '4' }}>
      <StatusRail />
    </div>

    <CmdKPalette />
    <FactoryWalkthrough />
  </div>
);

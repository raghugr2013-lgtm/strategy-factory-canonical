/**
 * MutateMasterBotCompile — Phase R1
 * --------------------------------------------------------------------------
 * Surfaces the Master Bot Compile flow that was previously buried inside
 * MasterBotDashboard.jsx. This component re-uses the dashboard's compile
 * tab via an `initialTab` prop pattern; when MasterBotDashboard ignores the
 * prop it simply renders its default view (no-op fallback). The point is to
 * give compile its own discoverable section URL per Handoff Screen 15.
 */
import React from 'react';
const MasterBotDashboard = React.lazy(() => import('./MasterBotDashboard'));

export default function MutateMasterBotCompile() {
  return (
    <React.Suspense fallback={<div style={{ padding: 24, fontSize: 11 }}>Loading Master Bot…</div>}>
      <div data-testid="master-bot-compile-wrapper">
        <MasterBotDashboard initialTab="compile" />
      </div>
    </React.Suspense>
  );
}

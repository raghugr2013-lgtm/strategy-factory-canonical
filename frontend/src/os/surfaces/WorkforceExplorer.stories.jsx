/*
 * WorkforceExplorer.stories.jsx — Phase F gallery entry.
 *
 * Three variants exercise the three views (org / purpose / status) plus
 * a fourth showing the kill-posture ribbon armed. Fixtures come from the
 * real WORKERS_FIXTURE + MASTER_BOT_FIXTURE via the production adapters,
 * so the gallery stays in sync with the live surface.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { WorkforceExplorer } from './WorkforceExplorer';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';
import { useAuthStore } from '../workspace-state/authStore';

const seedAuth = () => {
  useAuthStore.setState({
    stance: 'authenticated', email: 'admin@strategy-factory.local',
    role: 'admin', status: 'active', authMode: 'live',
    signedInAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    sessionId: 'sf-story-workforce-f',
  });
};

const seedView = (view) => {
  useNavigationStore.setState((s) => ({
    memory: {
      ...s.memory,
      '/c/workforce/explorer': { view },
    },
  }));
};

const seedKill = (armed) => {
  useWorkspaceStore.setState({ killPostureArmed: armed });
};

const Frame = ({ children }) => (
  <MemoryRouter initialEntries={['/c/workforce/explorer']}>
    <div style={{ minHeight: 720, background: 'var(--surface-0)' }}>{children}</div>
  </MemoryRouter>
);

export default {
  title: 'Surfaces/WorkforceExplorer',
  component: WorkforceExplorer,
  parameters: { layout: 'fullscreen' },
};

export const Organization = () => {
  useEffect(() => { seedAuth(); seedView('org'); seedKill(false); }, []);
  return <Frame><WorkforceExplorer /></Frame>;
};

export const Purpose = () => {
  useEffect(() => { seedAuth(); seedView('purpose'); seedKill(false); }, []);
  return <Frame><WorkforceExplorer /></Frame>;
};

export const Status = () => {
  useEffect(() => { seedAuth(); seedView('status'); seedKill(false); }, []);
  return <Frame><WorkforceExplorer /></Frame>;
};

export const KillPostureArmed = () => {
  useEffect(() => { seedAuth(); seedView('org'); seedKill(true); }, []);
  return <Frame><WorkforceExplorer /></Frame>;
};

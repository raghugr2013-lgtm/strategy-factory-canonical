/*
 * UserMenu.stories.jsx — Phase A gallery entry.
 *
 * The menu is stateful (Zustand-backed) so stories seed the auth + workspace
 * stores directly and unmount cleanly. Each story renders the opened panel
 * to make design review easier without needing to click through.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { UserMenu } from './UserMenu';
import { useAuthStore } from '../workspace-state/authStore';
import { useWorkspaceStore } from '../workspace-state/store';

const seed = (session, opts = {}) => {
  useAuthStore.setState({
    stance: 'authenticated',
    email: session.email,
    role: session.role,
    status: 'active',
    authMode: session.authMode,
    signedInAt: session.signedInAt,
    expiresAt: session.expiresAt,
    sessionId: session.sessionId,
  });
  useWorkspaceStore.setState({ advancedLens: !!opts.advancedLens });
};

const Frame = ({ children }) => (
  <MemoryRouter>
    <div style={{ display: 'flex', justifyContent: 'flex-end', padding: 24, background: 'var(--surface-0)' }}>
      {children}
    </div>
  </MemoryRouter>
);

export default {
  title: 'Auth/UserMenu',
  component: UserMenu,
  parameters: { layout: 'fullscreen' },
};

export const Operator = () => {
  useEffect(() => seed({
    email: 'operator@coinnike.com',
    role: 'operator',
    authMode: 'live',
    signedInAt: '2026-07-24T15:04:00.000Z',
    expiresAt:  '2026-07-24T15:34:00.000Z',
    sessionId:  'sf-op-8a2f',
  }), []);
  return <Frame><UserMenu /></Frame>;
};

export const Admin = () => {
  useEffect(() => seed({
    email: 'admin@strategy-factory.local',
    role: 'admin',
    authMode: 'live',
    signedInAt: '2026-07-24T15:04:00.000Z',
    expiresAt:  '2026-07-24T15:34:00.000Z',
    sessionId:  'sf-adm-1c9b',
  }), []);
  return <Frame><UserMenu /></Frame>;
};

export const AdvancedLens = () => {
  useEffect(() => seed({
    email: 'admin@strategy-factory.local',
    role: 'admin',
    authMode: 'live',
    signedInAt: '2026-07-24T15:04:00.000Z',
    expiresAt:  '2026-07-24T15:34:00.000Z',
    sessionId:  'sf-adm-1c9b',
  }, { advancedLens: true }), []);
  return <Frame><UserMenu /></Frame>;
};

export const FixtureMode = () => {
  useEffect(() => seed({
    email: 'operator@coinnike.com',
    role: 'operator',
    authMode: 'fixture',
    signedInAt: '2026-07-24T15:04:00.000Z',
    expiresAt:  '2026-07-24T15:34:00.000Z',
    sessionId:  'sf-fix-4d21',
  }), []);
  return <Frame><UserMenu /></Frame>;
};

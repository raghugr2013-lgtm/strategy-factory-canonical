/*
 * TimelineExplorer.stories.jsx — Phase E gallery entry.
 *
 * Fixtures come from the app's real TIMELINE_FIXTURE via the adapter, so the
 * gallery stays in sync with the live surface. Three variants toggle the
 * navigationStore actor facet so reviewers can inspect the empty state,
 * a governance-only view, and the full stream without mocking.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { TimelineExplorer } from './TimelineExplorer';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useAuthStore } from '../workspace-state/authStore';

const seed = (facet = 'all') => {
  useAuthStore.setState({
    stance: 'authenticated', email: 'admin@strategy-factory.local',
    role: 'admin', status: 'active', authMode: 'live',
    signedInAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    sessionId: 'sf-story-timeline-e',
  });
  useNavigationStore.setState((s) => ({ facets: { ...s.facets, actor: facet } }));
};

const Frame = ({ children }) => (
  <MemoryRouter initialEntries={['/c/timeline/explorer']}>
    <div style={{ minHeight: 720, background: 'var(--surface-0)' }}>{children}</div>
  </MemoryRouter>
);

export default {
  title: 'Surfaces/TimelineExplorer',
  component: TimelineExplorer,
  parameters: { layout: 'fullscreen' },
};

export const AllActors = () => {
  useEffect(() => seed('all'), []);
  return <Frame><TimelineExplorer /></Frame>;
};

export const GovernanceOnly = () => {
  useEffect(() => seed('governance'), []);
  return <Frame><TimelineExplorer /></Frame>;
};

export const MasterBotOnly = () => {
  useEffect(() => seed('master-bot'), []);
  return <Frame><TimelineExplorer /></Frame>;
};

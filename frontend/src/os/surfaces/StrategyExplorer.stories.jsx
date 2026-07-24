/*
 * StrategyExplorer.stories.jsx — Phase C gallery entry.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { StrategyExplorer } from './StrategyExplorer';
import { useAuthStore } from '../workspace-state/authStore';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const seed = (facet = 'all', selectedId = null) => {
  useAuthStore.setState({
    stance: 'authenticated', email: 'admin@strategy-factory.local',
    role: 'admin', status: 'active', authMode: 'live',
    signedInAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    sessionId: 'sf-story-000',
  });
  useNavigationStore.setState((s) => ({ facets: { ...s.facets, status: facet } }));
  useWorkspaceStore.setState({ selectedStrategy: selectedId });
};

const Frame = ({ children }) => (
  <MemoryRouter initialEntries={['/c/strategies/explorer']}>
    <div style={{ minHeight: 720, background: 'var(--surface-0)' }}>{children}</div>
  </MemoryRouter>
);

export default {
  title: 'Surfaces/StrategyExplorer',
  component: StrategyExplorer,
  parameters: { layout: 'fullscreen' },
};

export const AllStatuses = () => {
  useEffect(() => seed('all'), []);
  return <Frame><StrategyExplorer /></Frame>;
};

export const LiveOnly = () => {
  useEffect(() => seed('live'), []);
  return <Frame><StrategyExplorer /></Frame>;
};

export const WithSelection = () => {
  useEffect(() => seed('all', 'strat-041'), []);
  return <Frame><StrategyExplorer /></Frame>;
};

export const EmptyPaperFacet = () => {
  useEffect(() => seed('archived'), []);
  return <Frame><StrategyExplorer /></Frame>;
};

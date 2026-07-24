/*
 * ApprovalCenter.stories.jsx — Phase B gallery entry.
 *
 * Fixtures use the app's real APPROVALS_FIXTURE via the adapter, so the
 * gallery stays in sync with the live surface. Two variants toggle the
 * navigationStore risk facet so reviewers can inspect both "clear"
 * and "loaded" states without mocking.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ApprovalCenter } from './ApprovalCenter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useAuthStore } from '../workspace-state/authStore';

const seed = (facet = 'all') => {
  useAuthStore.setState({
    stance: 'authenticated', email: 'admin@strategy-factory.local',
    role: 'admin', status: 'active', authMode: 'live',
    signedInAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    sessionId: 'sf-story-000',
  });
  useNavigationStore.setState((s) => ({ facets: { ...s.facets, risk: facet } }));
};

const Frame = ({ children }) => (
  <MemoryRouter initialEntries={['/c/approvals/center']}>
    <div style={{ minHeight: 720, background: 'var(--surface-0)' }}>{children}</div>
  </MemoryRouter>
);

export default {
  title: 'Surfaces/ApprovalCenter',
  component: ApprovalCenter,
  parameters: { layout: 'fullscreen' },
};

export const AllRisks = () => {
  useEffect(() => seed('all'), []);
  return <Frame><ApprovalCenter /></Frame>;
};

export const HighOnly = () => {
  useEffect(() => seed('high'), []);
  return <Frame><ApprovalCenter /></Frame>;
};

export const LowOnly = () => {
  useEffect(() => seed('low'), []);
  return <Frame><ApprovalCenter /></Frame>;
};

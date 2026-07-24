/*
 * EvaluationHarness.stories.jsx — Phase D1 gallery entry.
 *
 * Three stories exercise the three visible states the store can produce
 * against the read-only surface. Each story pre-seeds useEvaluationStore
 * with a synthetic verdict map so reviewers can inspect the derived
 * summary / readiness UI without touching localStorage.
 *
 * Interactive controls remain disabled — write-side mutators land in D2.
 */
import React, { useEffect } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { EvaluationHarness } from './EvaluationHarness';
import { useEvaluationStore, DIMENSIONS } from '../workspace-state/evaluationStore';
import { useAuthStore } from '../workspace-state/authStore';

const seedAuth = () => {
  useAuthStore.setState({
    stance: 'authenticated', email: 'admin@strategy-factory.local',
    role: 'admin', status: 'active', authMode: 'live',
    signedInAt: new Date().toISOString(),
    expiresAt: new Date(Date.now() + 30 * 60_000).toISOString(),
    sessionId: 'sf-story-eval',
  });
};

const seedVerdicts = (mapper) => {
  const next = {};
  DIMENSIONS.forEach((d) => d.criteria.forEach((c) => {
    const v = mapper(c.id, d.key);
    if (v) next[c.id] = v;
  }));
  useEvaluationStore.setState({ verdicts: next, notes: '', session: '' });
};

const Frame = ({ children }) => (
  <MemoryRouter initialEntries={['/c/evaluation']}>
    <div style={{ minHeight: 720, background: 'var(--surface-0)' }}>{children}</div>
  </MemoryRouter>
);

export default {
  title: 'Surfaces/EvaluationHarness',
  component: EvaluationHarness,
  parameters: { layout: 'fullscreen' },
};

// Cold-load — every criterion unset. Readiness = unstarted.
export const Unstarted = () => {
  useEffect(() => { seedAuth(); seedVerdicts(() => null); }, []);
  return <Frame><EvaluationHarness /></Frame>;
};

// Mixed verdicts (some pass, some review, some unset). Readiness = nearly.
export const InProgress = () => {
  useEffect(() => {
    seedAuth();
    seedVerdicts((_id, dim) => {
      if (dim === 'discoverability') return 'pass';
      if (dim === 'navigation-predictability') return 'review';
      if (dim === 'cognitive-load') return 'pass';
      return null; // trust / identity / interaction-rhythm remain unset
    });
  }, []);
  return <Frame><EvaluationHarness /></Frame>;
};

// One failing criterion — readiness = blocked.
export const Blocked = () => {
  useEffect(() => {
    seedAuth();
    seedVerdicts((id) => (id === 'trust-2' ? 'fail' : 'pass'));
  }, []);
  return <Frame><EvaluationHarness /></Frame>;
};

// All 24 passing — readiness = ready.
export const Ready = () => {
  useEffect(() => {
    seedAuth();
    seedVerdicts(() => 'pass');
  }, []);
  return <Frame><EvaluationHarness /></Frame>;
};

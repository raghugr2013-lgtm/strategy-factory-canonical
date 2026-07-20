/*
 * Scenario Presets — PROTOTYPE ONLY.
 * Fixture bundles that seed the Inspector with realistic operational
 * contexts for walkthrough sessions. Presets are DATA + STATE only;
 * they do NOT drive workflow logic, timers, or simulated background events.
 *
 * A preset assembles:
 *   - workspace mode  (executive · operations · research · developer)
 *   - density         (compact · cozy · cinema)
 *   - advanced lens
 *   - canonical state (happy · loading · empty · error · dormant)
 *   - long-content    (extended narrative bodies)
 *   - killPosture     (dormant / armed)
 *
 * Consumers may also read `scenarioKey` from the inspector store to select
 * scenario-scoped fixture slices (see fixtures.ts).
 */
import type { CanonicalState } from '../workspace-state/inspectorStore';

export type ScenarioKey =
  | 'executive-morning-review'
  | 'operations-shift-burst'
  | 'research-investigation'
  | 'incident-response'
  | 'governance-review'
  | 'compute-pressure';

export interface Scenario {
  key: ScenarioKey;
  title: string;
  blurb: string;
  mode: 'executive' | 'operations' | 'research' | 'developer';
  density: 'compact' | 'cozy' | 'cinema';
  advancedLens: boolean;
  canonicalState: CanonicalState;
  longContent: boolean;
  killPosture: boolean;
}

export const SCENARIOS: Scenario[] = [
  {
    key: 'executive-morning-review',
    title: 'Executive Morning Review',
    blurb: 'Overnight summary, gold-accented hero metrics, cinema density.',
    mode: 'executive',
    density: 'cinema',
    advancedLens: false,
    canonicalState: 'happy',
    longContent: true,
    killPosture: false,
  },
  {
    key: 'operations-shift-burst',
    title: 'Operations Shift Burst',
    blurb: 'Compact rows, activity feed active, several approvals aging.',
    mode: 'operations',
    density: 'compact',
    advancedLens: false,
    canonicalState: 'happy',
    longContent: false,
    killPosture: false,
  },
  {
    key: 'research-investigation',
    title: 'Research Investigation',
    blurb: 'Cozy density, advanced lens on, provenance and lineage foregrounded.',
    mode: 'research',
    density: 'cozy',
    advancedLens: true,
    canonicalState: 'happy',
    longContent: true,
    killPosture: false,
  },
  {
    key: 'incident-response',
    title: 'Incident Response',
    blurb: 'Kill posture armed, error state across data widgets, red pipeline stage.',
    mode: 'operations',
    density: 'compact',
    advancedLens: true,
    canonicalState: 'error',
    longContent: true,
    killPosture: true,
  },
  {
    key: 'governance-review',
    title: 'Governance Review',
    blurb: 'Advanced lens on, approvals foregrounded, moderate/high risk cards visible.',
    mode: 'operations',
    density: 'cozy',
    advancedLens: true,
    canonicalState: 'happy',
    longContent: true,
    killPosture: false,
  },
  {
    key: 'compute-pressure',
    title: 'Compute Pressure',
    blurb: 'Dormant workers, degraded charts, quota escalation pending.',
    mode: 'developer',
    density: 'compact',
    advancedLens: true,
    canonicalState: 'dormant',
    longContent: false,
    killPosture: false,
  },
];

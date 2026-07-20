/*
 * Scenario-scoped fixtures — PROTOTYPE ONLY.
 * Six deterministic slices, one per scenario preset, plus a default
 * "happy" slice used when no preset is active. NOT a simulator — just
 * hand-authored data + presentation flags per user directive:
 *
 *   • Executive Morning Review → healthy system, briefing, minimal approvals
 *   • Operations Shift Burst    → active timeline, several approvals, busy workforce
 *   • Research Investigation    → evidence, lineage, strategy comparisons
 *   • Incident Response         → degraded workers, danger ribbon, aged approvals
 *   • Governance Review         → policy conflicts, audit info, pending approvals
 *   • Compute Pressure          → utilization, queue depth, capacity signals
 *
 * A single `useScenarioFixture()` hook is exposed for surface components.
 */
import type { ScenarioKey } from './scenarios';
import { useInspectorStore } from '../workspace-state/inspectorStore';
import type { PipelineStage } from '../primitives/PipelineStageBar';
import type { ChipTone } from '../primitives/Chip';
import type { ActorKind } from '../primitives/ActivityRow';
import type { WorkerState } from '../primitives/WorkerCard';
import type { RiskLevel, ApprovalOrigin } from '../primitives/ApprovalCard';

// ─── Shape ─────────────────────────────────────────────────────────────

export interface MissionMetric {
  variant: 'A' | 'B' | 'C';
  eyebrow: string; value: string; unit?: string;
  deltaLabel?: string; deltaTone?: ChipTone;
  footnote?: string;
}

export interface TimelineEvent {
  timestamp: string;
  actor: { kind: ActorKind; name?: string };
  verb: string; subject: string;
  outcome?: { tone: ChipTone; label: string };
  trailer?: string;
}

export interface ApprovalFixture {
  id: string;
  title: string; origin: ApprovalOrigin; risk: RiskLevel;
  summary: string;
  provenance: { source?: string; transform?: string; attested?: string };
  decisionIdentity?: string;
  ageMinutes: number;
}

export interface WorkerFixture {
  id: string; name: string; purpose: string;
  subject?: string; state: WorkerState;
}

export interface StrategyRow {
  id: string; name: string; owner: string;
  sharpe: number; drawdownPct: number; hitPct: number;
  status: 'live' | 'paper' | 'paused' | 'reviewing';
  policyFlag?: string;
}

export interface StrategyPassport {
  id: string; name: string; owner: string; version: string;
  headline: string;
  sharpe: number; drawdownPct: number; hitPct: number; agreementPct: number;
  status: StrategyRow['status'];
  provenance: { source?: string; transform?: string; attested?: string };
  lineageAncestors: Array<{ id: string; label: string; kind: string }>;
  lineageDescendants: Array<{ id: string; label: string; kind: string }>;
  narrative: string;
}

export interface ScenarioFixture {
  // Mission Control
  missionEyebrow: string;
  missionHeadline: string;
  missionBriefing: string;
  missionMetrics: MissionMetric[];
  pipelineStages: PipelineStage[];
  missionSparkPoints: number[];
  missionTone: 'ok' | 'info' | 'warn' | 'crit' | 'advisory' | 'gold' | 'dormant';

  // Timeline
  timelineEvents: TimelineEvent[];

  // Approval Center
  approvals: ApprovalFixture[];

  // Master Bot / Workforce
  workforceEyebrow: string;
  workforcePurpose: string;
  workforceStatus: string;
  workers: WorkerFixture[];

  // Strategy Explorer
  strategies: StrategyRow[];

  // Strategy Passport (opened from Explorer)
  passportById: Record<string, StrategyPassport>;
}

// ─── Reusable base data ────────────────────────────────────────────────

const basePipeline: PipelineStage[] = [
  { key: 'ingest',   label: 'ingest',   status: 'done',    detail: '18/18 tickers' },
  { key: 'candle',   label: 'candle',   status: 'done',    detail: 'candles@v3' },
  { key: 'feature',  label: 'feature',  status: 'done',    detail: '112 features' },
  { key: 'signal',   label: 'signal',   status: 'active',  detail: 'epoch 4/6' },
  { key: 'backtest', label: 'backtest', status: 'pending', detail: 'awaiting' },
  { key: 'approve',  label: 'approve',  status: 'pending', detail: 'human gate' },
  { key: 'deploy',   label: 'deploy',   status: 'pending' },
  { key: 'monitor',  label: 'monitor',  status: 'pending' },
];

const spark = [12, 15, 11, 14, 17, 16, 19, 22, 21, 24, 26, 28];

// ─── Six presets + default ─────────────────────────────────────────────

const EXECUTIVE: ScenarioFixture = {
  missionEyebrow: 'Executive briefing · overnight',
  missionHeadline: 'The Factory ran cleanly overnight. No decisions required.',
  missionBriefing:
    'Between 22:00Z and 05:00Z the Factory promoted two signals into paper trading, ' +
    'closed 118 candles across 18 tickers, and completed 47 backtests. Governance held ' +
    'zero artefacts. Sharpe on the flagship strategy improved from 1.38 to 1.42.',
  missionMetrics: [
    { variant: 'C', eyebrow: 'assets under strategy', value: '$182.4', unit: 'm', deltaLabel: '+0.9% overnight', deltaTone: 'ok', footnote: 'closed 05:00Z · reconciled' },
    { variant: 'C', eyebrow: 'flagship sharpe',       value: '1.42',                deltaLabel: '+0.04 vs prev',   deltaTone: 'ok', footnote: 'strat-001-flagship · window 30d' },
    { variant: 'A', eyebrow: 'approvals pending',     value: '0',                    deltaLabel: 'nothing needs you', deltaTone: 'ok' },
  ],
  pipelineStages: basePipeline.map((s) => ({ ...s, status: 'done' as const })),
  missionSparkPoints: [130, 132, 131, 134, 138, 140, 141, 143, 145, 147, 149, 150],
  missionTone: 'gold',
  timelineEvents: [
    { timestamp: '04:58Z', actor: { kind: 'master-bot' }, verb: 'closed', subject: 'overnight plan #46', outcome: { tone: 'ok', label: 'passing' }, trailer: 'sha 8f2a…' },
    { timestamp: '03:12Z', actor: { kind: 'llm' },        verb: 'drafted', subject: 'briefing · morning 2026-02-04', outcome: { tone: 'info', label: 'draft' } },
    { timestamp: '01:47Z', actor: { kind: 'worker', name: 'signal-forge@v2' }, verb: 'promoted', subject: 'sig-8f2 → paper', outcome: { tone: 'ok', label: 'promoted' } },
  ],
  approvals: [],
  workforceEyebrow: 'Master Bot · workforce',
  workforcePurpose: 'The workforce is idle-active. All divisions healthy.',
  workforceStatus: 'v55 · plan #47 · 3/7 · healthy',
  workers: [
    { id: 'w1', name: 'signal-forge@v2',    purpose: 'Generates candidates from the feature store.',       subject: 'idle',    state: 'idle' },
    { id: 'w2', name: 'candle-pipe@v3',     purpose: 'Assembles OHLCV candles from tick streams.',         subject: 'live',    state: 'active' },
    { id: 'w3', name: 'backtest-suite@v4',  purpose: 'Evaluates candidates against the shadowed book.',    subject: 'idle',    state: 'idle' },
    { id: 'w4', name: 'governance-warden',  purpose: 'Holds any artefact violating a policy contract.',    subject: 'clear',   state: 'idle' },
  ],
  strategies: [
    { id: 'strat-001', name: 'flagship-momentum', owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'live' },
    { id: 'strat-014', name: 'mean-reversion-x',  owner: 'ops', sharpe: 1.18, drawdownPct: 6.4, hitPct: 54, status: 'live' },
    { id: 'strat-022', name: 'options-decay',     owner: 'res', sharpe: 0.98, drawdownPct: 3.2, hitPct: 51, status: 'paper' },
  ],
  passportById: {},
};

const OPERATIONS: ScenarioFixture = {
  missionEyebrow: 'Operations shift · in-flight',
  missionHeadline: 'A busy shift. The Factory needs three human decisions.',
  missionBriefing:
    'Signal generation is running hot; the backtest suite is at 78% utilisation. ' +
    'Three approvals are aged under 30 minutes.',
  missionMetrics: [
    { variant: 'A', eyebrow: 'strategies live',    value: '18', unit: 'of 22', deltaLabel: '+2 vs yesterday', deltaTone: 'ok', footnote: 'window 24h · owner ops' },
    { variant: 'B', eyebrow: 'signals in queue',   value: '47',                 deltaLabel: '+11 last hour',    deltaTone: 'info', footnote: 'scheduler@v9 · queue depth healthy' },
    { variant: 'A', eyebrow: 'approval SLA',       value: '14m',                deltaLabel: 'under target 30m', deltaTone: 'ok', footnote: 'p95 · aged approvals highlighted' },
  ],
  pipelineStages: basePipeline,
  missionSparkPoints: spark,
  missionTone: 'info',
  timelineEvents: [
    { timestamp: '15:04:12', actor: { kind: 'master-bot' }, verb: 'dispatched', subject: 'plan #47 · step 3', outcome: { tone: 'info', label: 'active' }, trailer: 'sha 91a2ce…' },
    { timestamp: '15:03:41', actor: { kind: 'worker', name: 'signal-forge@v2' }, verb: 'generated', subject: 'sig-8f2', outcome: { tone: 'ok', label: 'passing' }, trailer: 'epoch 4/6' },
    { timestamp: '15:02:58', actor: { kind: 'ingestion' },  verb: 'closed candle', subject: 'AAPL 15:00Z', outcome: { tone: 'ok', label: 'passing' } },
    { timestamp: '15:01:12', actor: { kind: 'governance' }, verb: 'held', subject: 'strat-014-schema-v3', outcome: { tone: 'warn', label: 'review' }, trailer: 'policy v2.1 §8.4' },
    { timestamp: '14:59:33', actor: { kind: 'llm' },        verb: 'drafted', subject: 'brief · daily 2026-02-04', outcome: { tone: 'info', label: 'draft' } },
    { timestamp: '14:57:18', actor: { kind: 'operator' },   verb: 'approved', subject: 'strat-011 promotion', outcome: { tone: 'ok', label: 'approved' } },
    { timestamp: '14:55:02', actor: { kind: 'scheduler' },  verb: 'queued', subject: 'bt-19a', outcome: { tone: 'info', label: 'queued' } },
  ],
  approvals: [
    { id: 'a1', title: 'Promote signal sig-8f2 into paper trading.',   origin: 'strategy',      risk: 'low',      summary: 'Backtest passed 12/13 checks. Sharpe 1.42, drawdown 4.1%.', provenance: { source: 'signal-forge@v2', transform: 'plan #47 · step 3', attested: 'gov-warden' }, decisionIdentity: 'plan #47 · sha 91a2ce…', ageMinutes: 14 },
    { id: 'a2', title: 'Rotate schema for feature store to v4.',         origin: 'schema-change', risk: 'moderate', summary: 'Adds five columns; drops one. Reversible via migration 07-b.', provenance: { source: 'feature-mill@v6', transform: 'plan #48 · step 1', attested: 'gov-warden' }, decisionIdentity: 'plan #48 · sha 5da0ff…', ageMinutes: 22 },
    { id: 'a3', title: 'Extend feature research access to J. Rivera.',   origin: 'access-request',risk: 'low',      summary: 'Read-only access to feature store for 30 days.', provenance: { source: 'operator@ops', transform: 'manual request', attested: 'gov-warden' }, decisionIdentity: 'req #211', ageMinutes: 7 },
  ],
  workforceEyebrow: 'Master Bot · workforce',
  workforcePurpose: 'Coordinates every research plan across ingest, feature, signal, backtest.',
  workforceStatus: 'v55 · plan #47 · 3/7',
  workers: [
    { id: 'w1', name: 'signal-forge@v2',    purpose: 'Generates candidates from the feature store.',       subject: 'sig-8f2',   state: 'active' },
    { id: 'w2', name: 'candle-pipe@v3',     purpose: 'Assembles OHLCV candles from tick streams.',         subject: 'cdl-90d',   state: 'active' },
    { id: 'w3', name: 'backtest-suite@v4',  purpose: 'Evaluates candidates against the shadowed book.',    subject: 'bt-19a',    state: 'active' },
    { id: 'w4', name: 'feature-mill@v6',    purpose: 'Materialises engineered features from candles.',     subject: 'ftr-77c',   state: 'idle' },
    { id: 'w5', name: 'scheduler@v9',       purpose: 'Owns queue depth, quotas, and back-pressure.',       subject: '47 queued', state: 'active' },
    { id: 'w6', name: 'governance-warden',  purpose: 'Holds any artefact violating a policy contract.',    subject: 'clear',     state: 'idle' },
  ],
  strategies: [
    { id: 'strat-001', name: 'flagship-momentum',   owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'live' },
    { id: 'strat-011', name: 'basket-mean-revert',  owner: 'ops', sharpe: 1.05, drawdownPct: 5.7, hitPct: 55, status: 'live' },
    { id: 'strat-014', name: 'mean-reversion-x',    owner: 'ops', sharpe: 1.18, drawdownPct: 6.4, hitPct: 54, status: 'live' },
    { id: 'strat-022', name: 'options-decay',       owner: 'res', sharpe: 0.98, drawdownPct: 3.2, hitPct: 51, status: 'paper' },
    { id: 'strat-030', name: 'vol-carry',           owner: 'res', sharpe: 0.88, drawdownPct: 8.1, hitPct: 49, status: 'paper' },
    { id: 'strat-041', name: 'earnings-drift',      owner: 'ops', sharpe: 1.10, drawdownPct: 4.9, hitPct: 56, status: 'paused' },
  ],
  passportById: {},
};

const RESEARCH: ScenarioFixture = {
  missionEyebrow: 'Research investigation · sig-8f2',
  missionHeadline: 'Comparing signal candidates against the shadowed book.',
  missionBriefing:
    'Provenance and lineage are foregrounded. Every metric on this page can be replayed ' +
    'from the underlying features and candles. Advanced Lens exposes worker versions ' +
    'and decision identities.',
  missionMetrics: [
    { variant: 'B', eyebrow: 'candidates evaluated',  value: '312',           deltaLabel: '+28 today', deltaTone: 'info', footnote: 'plan #47 · window 24h' },
    { variant: 'A', eyebrow: 'shadow agreement',       value: '96%',           deltaLabel: '+2pp vs prev', deltaTone: 'ok', footnote: 'signal-forge@v2 · book v3' },
    { variant: 'A', eyebrow: 'feature coverage',       value: '112 / 118',      deltaLabel: '6 features stale', deltaTone: 'advisory', footnote: 'feature-mill@v6' },
  ],
  pipelineStages: basePipeline,
  missionSparkPoints: spark.map((p) => p * 1.05),
  missionTone: 'info',
  timelineEvents: [
    { timestamp: '15:04Z', actor: { kind: 'worker', name: 'signal-forge@v2' }, verb: 'evaluated', subject: 'sig-8f2 vs shadow book', outcome: { tone: 'ok', label: '96% agreement' }, trailer: 'book@v3 · epoch 4' },
    { timestamp: '15:02Z', actor: { kind: 'worker', name: 'feature-mill@v6' }, verb: 'materialised', subject: '112 features',      outcome: { tone: 'ok', label: 'complete' }, trailer: 'ftr-77c' },
    { timestamp: '14:58Z', actor: { kind: 'validator' }, verb: 'attested', subject: 'sig-8f2 provenance', outcome: { tone: 'ok', label: 'attested' }, trailer: 'sha 91a2ce…' },
    { timestamp: '14:40Z', actor: { kind: 'llm' },       verb: 'summarised', subject: 'sig-8f2 narrative', outcome: { tone: 'info', label: 'draft' } },
  ],
  approvals: [
    { id: 'a1', title: 'Attach research narrative to sig-8f2 passport.', origin: 'strategy', risk: 'low', summary: 'LLM-drafted narrative reviewed by two researchers.', provenance: { source: 'llm-assistant@v4', transform: 'plan #47', attested: 'j.rivera' }, decisionIdentity: 'plan #47 · sig-8f2 · sha 91a2ce…', ageMinutes: 40 },
  ],
  workforceEyebrow: 'Research workforce',
  workforcePurpose: 'Focused on evidence attestation and lineage completeness.',
  workforceStatus: 'v55 · research lane · plan #47',
  workers: [
    { id: 'w1', name: 'signal-forge@v2',    purpose: 'Generates candidate signals from the feature store.', subject: 'sig-8f2', state: 'active' },
    { id: 'w2', name: 'feature-mill@v6',    purpose: 'Materialises engineered features from candles.',       subject: 'ftr-77c', state: 'active' },
    { id: 'w3', name: 'validator@v1',       purpose: 'Attests provenance triples for every research artefact.', subject: 'sig-8f2', state: 'active' },
    { id: 'w4', name: 'llm-assistant@v4',   purpose: 'Drafts narratives from evidence bundles.',              subject: 'brief-8f2', state: 'active' },
  ],
  strategies: [
    { id: 'strat-001', name: 'flagship-momentum', owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'live' },
    { id: 'strat-022', name: 'options-decay',     owner: 'res', sharpe: 0.98, drawdownPct: 3.2, hitPct: 51, status: 'paper' },
    { id: 'strat-030', name: 'vol-carry',         owner: 'res', sharpe: 0.88, drawdownPct: 8.1, hitPct: 49, status: 'paper' },
    { id: 'strat-055', name: 'earnings-fade',     owner: 'res', sharpe: 1.24, drawdownPct: 3.9, hitPct: 57, status: 'reviewing' },
  ],
  passportById: {},
};

const INCIDENT: ScenarioFixture = {
  missionEyebrow: 'Incident response · P2',
  missionHeadline: 'Kill posture armed. Two workers degraded, four approvals aged.',
  missionBriefing:
    'A partial ingestion gap between 08:00Z and 09:00Z propagated downstream. Governance ' +
    'has held one schema change and one strategy promotion pending review. The signal ' +
    'pipeline is red at stage 4.',
  missionMetrics: [
    { variant: 'A', eyebrow: 'aged approvals',   value: '4', deltaLabel: '2 over 60m',      deltaTone: 'crit', footnote: 'p95 breached · target 30m' },
    { variant: 'A', eyebrow: 'degraded workers', value: '2', deltaLabel: 'signal · candle', deltaTone: 'warn', footnote: 'ingestion gap · retry #3' },
    { variant: 'A', eyebrow: 'governance holds', value: '2', deltaLabel: '1 schema · 1 strat', deltaTone: 'advisory', footnote: 'policy v2.1 §8.4' },
  ],
  pipelineStages: basePipeline.map((s) =>
    s.key === 'signal'   ? { ...s, status: 'blocked' as const, detail: 'candle gap' } :
    s.key === 'candle'   ? { ...s, status: 'blocked' as const, detail: '08:00–09:00Z gap' } :
    s.key === 'feature'  ? { ...s, status: 'blocked' as const, detail: 'stale features' } :
    s
  ),
  missionSparkPoints: [22, 24, 26, 25, 12, 8, 6, 5, 4, 3, 3, 4], // sharp drop
  missionTone: 'crit',
  timelineEvents: [
    { timestamp: '15:04:12', actor: { kind: 'governance' }, verb: 'held',   subject: 'strat-014-schema-v3', outcome: { tone: 'warn', label: 'held' }, trailer: 'policy §8.4' },
    { timestamp: '15:02:41', actor: { kind: 'master-bot' }, verb: 'armed',  subject: 'kill posture',        outcome: { tone: 'crit', label: 'armed' }, trailer: 'plan #47 · reason: ingest gap' },
    { timestamp: '14:58:33', actor: { kind: 'ingestion' },  verb: 'gap detected', subject: 'AAPL 08:00–09:00Z', outcome: { tone: 'crit', label: 'gap' } },
    { timestamp: '14:45:12', actor: { kind: 'worker', name: 'signal-forge@v2' }, verb: 'blocked', subject: 'sig-8f3', outcome: { tone: 'crit', label: 'blocked' }, trailer: 'upstream candle missing' },
    { timestamp: '14:12:00', actor: { kind: 'operator' },   verb: 'paged',  subject: 'ops-oncall',           outcome: { tone: 'warn', label: 'paged' } },
  ],
  approvals: [
    { id: 'a1', title: 'Approve candle backfill for AAPL 08:00–09:00Z.', origin: 'data-ingest',   risk: 'high',     summary: '52 minutes of candles missing; backfill from vendor archive.', provenance: { source: 'ingestion@v22', transform: 'backfill plan', attested: undefined }, decisionIdentity: 'plan #47 · backfill', ageMinutes: 74 },
    { id: 'a2', title: 'Release governance hold on strat-014-schema-v3.', origin: 'schema-change', risk: 'high',     summary: 'Schema change violates policy §8.4. Author requests override.', provenance: { source: 'feature-mill@v6', transform: 'plan #48 · step 1', attested: 'gov-warden' }, decisionIdentity: 'plan #48 · sha 5da0ff…', ageMinutes: 82 },
    { id: 'a3', title: 'Roll back promotion of sig-8f3.',                 origin: 'strategy',     risk: 'moderate', summary: 'Signal generated on incomplete data; performance suspect.', provenance: { source: 'signal-forge@v2', transform: 'plan #47', attested: undefined }, decisionIdentity: 'sig-8f3 · sha 44b1c…', ageMinutes: 65 },
    { id: 'a4', title: 'Extend on-call access for the incident team.',    origin: 'access-request',risk: 'low',      summary: 'Six-hour elevated access to feature store + prod dashboards.', provenance: { source: 'operator@ops', transform: 'manual', attested: undefined }, decisionIdentity: 'req #227', ageMinutes: 8 },
  ],
  workforceEyebrow: 'Incident workforce',
  workforcePurpose: 'Two workers are degraded. The warden is actively holding artefacts.',
  workforceStatus: 'v55 · plan #47 · kill posture armed',
  workers: [
    { id: 'w1', name: 'signal-forge@v2',    purpose: 'Generates candidates from the feature store.',       subject: 'sig-8f3',                state: 'blocked' },
    { id: 'w2', name: 'candle-pipe@v3',     purpose: 'Assembles OHLCV candles from tick streams.',         subject: 'gap 08:00–09:00Z',       state: 'error' },
    { id: 'w3', name: 'feature-mill@v6',    purpose: 'Materialises engineered features from candles.',     subject: 'stale ftr-77c',          state: 'idle' },
    { id: 'w4', name: 'governance-warden',  purpose: 'Holds any artefact violating a policy contract.',    subject: 'strat-014-schema-v3',    state: 'active' },
    { id: 'w5', name: 'backtest-suite@v4',  purpose: 'Evaluates candidates against the shadowed book.',    subject: 'suspended',              state: 'blocked' },
  ],
  strategies: [
    { id: 'strat-001', name: 'flagship-momentum', owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'paused',    policyFlag: 'candle gap upstream' },
    { id: 'strat-011', name: 'basket-mean-revert',owner: 'ops', sharpe: 1.05, drawdownPct: 5.7, hitPct: 55, status: 'paused',    policyFlag: 'candle gap upstream' },
    { id: 'strat-014', name: 'mean-reversion-x',  owner: 'ops', sharpe: 1.18, drawdownPct: 6.4, hitPct: 54, status: 'reviewing', policyFlag: 'schema change held' },
    { id: 'strat-030', name: 'vol-carry',         owner: 'res', sharpe: 0.88, drawdownPct: 8.1, hitPct: 49, status: 'paper' },
  ],
  passportById: {},
};

const GOVERNANCE: ScenarioFixture = {
  missionEyebrow: 'Governance review · policy v2.1',
  missionHeadline: 'Two policy conflicts open. Audit trail is complete.',
  missionBriefing:
    'Policy v2.1 §8.4 requires all schema changes to declare an attester and a rollback ' +
    'plan. Two proposed changes are missing rollback plans. Advanced Lens exposes the ' +
    'attester chain for every open approval.',
  missionMetrics: [
    { variant: 'A', eyebrow: 'policy conflicts',      value: '2',      deltaLabel: '§8.4 attester missing', deltaTone: 'advisory', footnote: 'policy v2.1 · scope: schema' },
    { variant: 'A', eyebrow: 'attestations issued',   value: '312',    deltaLabel: '+11 today',              deltaTone: 'info',     footnote: 'validator@v1 · window 24h' },
    { variant: 'A', eyebrow: 'audit completeness',    value: '99.6%',  deltaLabel: '4 events unlinked',      deltaTone: 'advisory', footnote: 'evidence-store@v7' },
  ],
  pipelineStages: basePipeline.map((s) =>
    s.key === 'approve' ? { ...s, status: 'active' as const, detail: '2 policy' } : s
  ),
  missionSparkPoints: spark,
  missionTone: 'advisory',
  timelineEvents: [
    { timestamp: '15:05Z', actor: { kind: 'governance' }, verb: 'flagged', subject: 'strat-014-schema-v3', outcome: { tone: 'warn', label: 'policy §8.4' }, trailer: 'attester missing' },
    { timestamp: '14:52Z', actor: { kind: 'validator' },  verb: 'attested', subject: 'sig-8f2 provenance',  outcome: { tone: 'ok', label: 'attested' }, trailer: 'gov-warden · sha 91a2ce…' },
    { timestamp: '14:40Z', actor: { kind: 'governance' }, verb: 'audited', subject: 'plan #46 evidence',    outcome: { tone: 'ok', label: 'audited' } },
    { timestamp: '13:20Z', actor: { kind: 'operator' },   verb: 'requested', subject: 'policy exception',   outcome: { tone: 'info', label: 'pending' }, trailer: 'req #218' },
  ],
  approvals: [
    { id: 'a1', title: 'Grant policy exception for strat-014-schema-v3.',       origin: 'policy-change', risk: 'high',     summary: 'Author cannot provide rollback plan for the deleted column.', provenance: { source: 'feature-mill@v6', transform: 'plan #48', attested: undefined }, decisionIdentity: 'req #218 · policy v2.1 §8.4', ageMinutes: 105 },
    { id: 'a2', title: 'Update policy v2.1 §8.4 to require an attester field.', origin: 'policy-change', risk: 'moderate', summary: 'Ratifies existing enforcement. No functional change.',       provenance: { source: 'gov-warden',      transform: 'proposal §8.4', attested: 'gov-warden' }, decisionIdentity: 'policy proposal v2.2', ageMinutes: 52 },
    { id: 'a3', title: 'Attest sig-8f2 lineage bundle for audit.',              origin: 'strategy',      risk: 'low',      summary: 'Provenance triple complete; lineage covers 3 hops.',           provenance: { source: 'validator@v1',    transform: 'plan #47', attested: 'gov-warden' }, decisionIdentity: 'sig-8f2 · sha 91a2ce…', ageMinutes: 12 },
  ],
  workforceEyebrow: 'Governance workforce',
  workforcePurpose: 'Auditors and attesters. Holds anything that breaks the policy contract.',
  workforceStatus: 'v55 · governance lane',
  workers: [
    { id: 'w1', name: 'governance-warden',  purpose: 'Holds any artefact violating a policy contract.', subject: 'strat-014-schema-v3', state: 'active' },
    { id: 'w2', name: 'validator@v1',       purpose: 'Attests provenance triples for every artefact.',   subject: 'sig-8f2',              state: 'active' },
    { id: 'w3', name: 'auditor@v2',         purpose: 'Cross-links artefacts with policy citations.',    subject: 'plan #46',              state: 'idle' },
    { id: 'w4', name: 'lineage-inspector',  purpose: 'Detects broken provenance chains.',                subject: 'clear',                state: 'idle' },
  ],
  strategies: [
    { id: 'strat-014', name: 'mean-reversion-x',  owner: 'ops', sharpe: 1.18, drawdownPct: 6.4, hitPct: 54, status: 'reviewing', policyFlag: '§8.4 attester missing' },
    { id: 'strat-001', name: 'flagship-momentum', owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'live' },
    { id: 'strat-022', name: 'options-decay',     owner: 'res', sharpe: 0.98, drawdownPct: 3.2, hitPct: 51, status: 'paper',     policyFlag: 'rollback plan missing' },
  ],
  passportById: {},
};

const COMPUTE: ScenarioFixture = {
  missionEyebrow: 'Compute pressure · scheduler@v9',
  missionHeadline: 'Queue depth rising. Capacity headroom is 12%.',
  missionBriefing:
    'The backtest suite is at 88% utilisation. Signal generation has queued 47 candidates; ' +
    'the p95 wait time is 6.4 minutes. Two workers are dormant to reduce cost.',
  missionMetrics: [
    { variant: 'B', eyebrow: 'queue depth',           value: '47',    deltaLabel: '+18 vs typical', deltaTone: 'warn', footnote: 'scheduler@v9 · p95 wait 6.4m' },
    { variant: 'A', eyebrow: 'compute utilisation',   value: '88%',   deltaLabel: 'headroom 12%',   deltaTone: 'advisory', footnote: 'target: <75% steady state' },
    { variant: 'A', eyebrow: 'projected daily cost',  value: '$184',  deltaLabel: '+$41 vs budget', deltaTone: 'warn', footnote: 'budget $143 · projected rollover 03:00Z' },
  ],
  pipelineStages: basePipeline.map((s) =>
    s.key === 'backtest' ? { ...s, status: 'active' as const, detail: '88% util' } :
    s.key === 'signal'   ? { ...s, status: 'active' as const, detail: '47 queued' } :
    s
  ),
  missionSparkPoints: [30, 32, 28, 34, 36, 40, 42, 44, 45, 46, 47, 47],
  missionTone: 'warn',
  timelineEvents: [
    { timestamp: '15:04Z', actor: { kind: 'scheduler' }, verb: 'queued',   subject: 'bt-19b',        outcome: { tone: 'info', label: 'queued' }, trailer: 'p95 wait 6.4m' },
    { timestamp: '15:01Z', actor: { kind: 'scheduler' }, verb: 'paused',   subject: 'signal-forge@v3-canary', outcome: { tone: 'warn', label: 'paused' }, trailer: 'reason: capacity' },
    { timestamp: '14:53Z', actor: { kind: 'system' },    verb: 'alerted',  subject: 'compute budget @ 88%', outcome: { tone: 'warn', label: 'alert' } },
    { timestamp: '14:40Z', actor: { kind: 'operator' },  verb: 'requested', subject: 'quota increase +40%', outcome: { tone: 'info', label: 'pending' } },
  ],
  approvals: [
    { id: 'a1', title: 'Raise compute quota for backtest suite by 40%.',   origin: 'compute-quota', risk: 'high',     summary: 'Estimated $184/day incremental cost. Impacts other tenants.', provenance: { source: 'operator@ops', transform: 'manual request', attested: undefined }, decisionIdentity: 'req #113', ageMinutes: 22 },
    { id: 'a2', title: 'Retire dormant worker signal-forge@v3-canary.',    origin: 'compute-quota', risk: 'low',      summary: 'Canary has been dormant 72h. Frees 8 vCPU.',                     provenance: { source: 'scheduler@v9',  transform: 'auto', attested: 'gov-warden' }, decisionIdentity: 'sched · canary retire', ageMinutes: 14 },
  ],
  workforceEyebrow: 'Compute workforce',
  workforcePurpose: 'Scheduler is holding the line. Canary workers dormant to save cost.',
  workforceStatus: 'v55 · scheduler at 88%',
  workers: [
    { id: 'w1', name: 'scheduler@v9',              purpose: 'Owns queue depth, quotas, and back-pressure.',       subject: '47 queued',    state: 'active' },
    { id: 'w2', name: 'backtest-suite@v4',         purpose: 'Evaluates candidates against the shadowed book.',    subject: 'bt-19a',       state: 'active' },
    { id: 'w3', name: 'signal-forge@v2',           purpose: 'Generates candidates from the feature store.',       subject: 'sig-8f2',      state: 'active' },
    { id: 'w4', name: 'signal-forge@v3-canary',    purpose: 'Canary of the next signal generator.',               subject: 'paused',       state: 'dormant' },
    { id: 'w5', name: 'feature-mill@v6-canary',    purpose: 'Canary of the next feature mill.',                   subject: 'paused',       state: 'dormant' },
  ],
  strategies: [
    { id: 'strat-001', name: 'flagship-momentum', owner: 'ops', sharpe: 1.42, drawdownPct: 4.1, hitPct: 58, status: 'live' },
    { id: 'strat-014', name: 'mean-reversion-x',  owner: 'ops', sharpe: 1.18, drawdownPct: 6.4, hitPct: 54, status: 'live' },
    { id: 'strat-022', name: 'options-decay',     owner: 'res', sharpe: 0.98, drawdownPct: 3.2, hitPct: 51, status: 'paper' },
    { id: 'strat-041', name: 'earnings-drift',    owner: 'ops', sharpe: 1.10, drawdownPct: 4.9, hitPct: 56, status: 'paused', policyFlag: 'quota-reserved' },
  ],
  passportById: {},
};

const DEFAULT_FIXTURE: ScenarioFixture = OPERATIONS;

// ─── Strategy Passport is derived from the current fixture ─────────────

const passportFor = (fx: ScenarioFixture): Record<string, StrategyPassport> => {
  const out: Record<string, StrategyPassport> = {};
  fx.strategies.forEach((s, i) => {
    out[s.id] = {
      id: s.id,
      name: s.name,
      owner: s.owner,
      version: `v${20 + i}`,
      headline: s.status === 'live'
        ? 'This strategy is live and passing all guardrails.'
        : s.status === 'paper'
        ? 'This strategy is running in paper trading.'
        : s.status === 'paused'
        ? 'This strategy is paused pending an upstream fix.'
        : 'This strategy is under review by governance.',
      sharpe: s.sharpe,
      drawdownPct: s.drawdownPct,
      hitPct: s.hitPct,
      agreementPct: 96 - i,
      status: s.status,
      provenance: { source: `${s.name}-worker@v${2 + i}`, transform: `plan #${47 + i}`, attested: s.policyFlag ? undefined : 'gov-warden' },
      lineageAncestors: [
        { id: `ftr-${77 + i}`, label: `ftr-${77 + i}`, kind: 'feature' },
        { id: `cdl-${90 + i}`, label: `cdl-${90 + i}`, kind: 'candle' },
      ],
      lineageDescendants: [
        { id: `bt-${19 + i}`, label: `bt-${19 + i}`, kind: 'backtest' },
      ],
      narrative: s.policyFlag
        ? `Governance held this strategy: ${s.policyFlag}. Review the linked policy citation before proceeding.`
        : `Performance is stable. The provenance chain is complete and attested by governance-warden.`,
    };
  });
  return out;
};

const FIXTURES: Record<ScenarioKey, ScenarioFixture> = {
  'executive-morning-review': EXECUTIVE,
  'operations-shift-burst':    OPERATIONS,
  'research-investigation':    RESEARCH,
  'incident-response':         INCIDENT,
  'governance-review':         GOVERNANCE,
  'compute-pressure':          COMPUTE,
};

Object.values(FIXTURES).forEach((fx) => { fx.passportById = passportFor(fx); });
DEFAULT_FIXTURE.passportById = passportFor(DEFAULT_FIXTURE);

// ─── Consumer hook ─────────────────────────────────────────────────────

export const useScenarioFixture = (): ScenarioFixture => {
  const key = useInspectorStore((s) => s.scenarioKey);
  return key ? FIXTURES[key] : DEFAULT_FIXTURE;
};

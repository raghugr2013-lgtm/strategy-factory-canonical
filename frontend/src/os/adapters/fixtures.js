/*
 * Fixtures — Sprint 1 M3 fixture-first foundation.
 * refs DESIGN_FREEZE_v1.0.md §3 (fixture data content extendable)
 * refs Kickoff Plan §4 · M3 (adapters fallback when REACT_APP_BACKEND_URL absent)
 *
 * These fixtures mirror the prototype's scenario data. Adapters read from
 * this module until a real backend response supersedes them (M5).
 */
export const TIMELINE_FIXTURE = [
  { id: 'e-01', timestamp: '12:34:02', actorKind: 'governance', actorName: 'Gov-Warden',
    verb: 'held', subject: 'strat-014-schema-v3', outcome: { tone: 'warn', label: 'review' },
    trailer: 'policy v2.1 §8.4', provenance: { source: 'governance', transform: 'plan #47', attested: 'gov-warden' },
    lineage: { self: { id: 'strat-014', label: 'STRAT-014', kind: 'strategy' },
               ancestors: [{ id: 'plan-47', label: 'PLAN #47', kind: 'plan' }] } },
  { id: 'e-02', timestamp: '12:14:11', actorKind: 'master-bot', actorName: 'Master Bot',
    verb: 'deployed', subject: 'signal-forge@v2 → plan #47',
    outcome: { tone: 'ok', label: 'success' }, trailer: 'sha 91a2b',
    provenance: { source: 'master-bot', transform: 'plan #47 · step 1', attested: 'gov-warden' } },
  { id: 'e-03', timestamp: '11:58:44', actorKind: 'llm', actorName: 'LLM',
    verb: 'proposed', subject: 'feature-mill@v6',
    outcome: { tone: 'info', label: 'draft' }, trailer: 'claude sonnet 4.6',
    provenance: { source: 'llm', transform: 'proposal', attested: 'gov-warden' } },
  { id: 'e-04', timestamp: '11:52:03', actorKind: 'ingestion', actorName: 'Ingestion',
    verb: 'failed', subject: 'candles-gap 08:00–09:00',
    outcome: { tone: 'crit', label: 'failed' }, trailer: 'retry #3',
    provenance: { source: 'ingestion@v22', transform: 'candles@v3', attested: 'gov-warden' } },
  { id: 'e-05', timestamp: '11:38:22', actorKind: 'operator', actorName: 'Operator',
    verb: 'approved', subject: 'compute quota +25%',
    outcome: { tone: 'ok', label: 'approved' }, trailer: 'quota v11',
    provenance: { source: 'operator', transform: 'approval', attested: 'gov-warden' } },
  { id: 'e-06', timestamp: '11:22:07', actorKind: 'validator', actorName: 'Validator',
    verb: 'attested', subject: 'backtest-891',
    outcome: { tone: 'ok', label: 'passed' },
    provenance: { source: 'validator', transform: 'backtest', attested: 'gov-warden' } },
  { id: 'e-07', timestamp: '10:58:19', actorKind: 'scheduler', actorName: 'Scheduler',
    verb: 'queued', subject: 'nightly-rebalance',
    outcome: { tone: 'info', label: 'queued' },
    provenance: { source: 'scheduler@v11', transform: 'cron', attested: 'gov-warden' } },
];

export const APPROVALS_FIXTURE = [
  { id: 'a-01', title: 'Promote strat-014 flagship-momentum from paper to live.',
    origin: 'strategy', risk: 'moderate', ageMinutes: 44,
    summary: 'Sharpe 1.62 over 42 days. Guardrails passing. Governance advisory: matches historical crowded-trade signature at v1.3.',
    provenance: { source: 'flagship-momentum-worker@v2', transform: 'plan #47 · step 1', attested: 'gov-warden' },
    decisionIdentity: 'plan #47 · signal-forge@v2 · sha 91a2b3c' },
  { id: 'a-02', title: 'Approve schema change · strat-014-schema-v3.',
    origin: 'schema-change', risk: 'high', ageMinutes: 82,
    summary: 'Column added to signal envelope. Downstream models require re-fit within 24h.',
    provenance: { source: 'schema-registry', transform: 'gov-warden', attested: 'gov-warden' },
    decisionIdentity: 'plan #47 · step 2 · sha 8c1d0' },
  { id: 'a-03', title: 'Grant read access to research-guest@coinnike.com.',
    origin: 'access-request', risk: 'low', ageMinutes: 12,
    summary: 'One-day read-only pass to backtest archive. Auto-revoke at 24h.',
    provenance: { source: 'iam', transform: 'access-request', attested: 'gov-warden' },
    decisionIdentity: 'iam-req #221 · sha 44f9' },
];

export const WORKERS_FIXTURE = [
  { id: 'w-01', name: 'ingestion@v22', purpose: 'Streams bar candles from primary + fallback feeds.',
    subject: 'candles@v3 · window 24h', state: 'active' },
  { id: 'w-02', name: 'signal-forge@v2', purpose: 'Trains candidate signals from the feature store.',
    subject: 'plan #47 · epoch 4/6', state: 'active' },
  { id: 'w-03', name: 'feature-mill@v6', purpose: 'Assembles feature vectors from candles + external factors.',
    subject: 'strat-014 · batch 5/5', state: 'idle' },
  { id: 'w-04', name: 'gov-warden', purpose: 'Attests schema, policy, and governance holds.',
    state: 'blocked' },
  { id: 'w-05', name: 'candle-mill@v3', purpose: 'Fell over. Attempting reconnect.',
    state: 'error' },
];

export const PIPELINE_FIXTURE = [
  { key: 'ingest',   label: 'ingest',   status: 'done',    detail: '18/18 tickers' },
  { key: 'candle',   label: 'candle',   status: 'done',    detail: 'candles@v3' },
  { key: 'feature',  label: 'feature',  status: 'done',    detail: '112 features' },
  { key: 'signal',   label: 'signal',   status: 'active',  detail: 'training epoch 4/6' },
  { key: 'backtest', label: 'backtest', status: 'pending', detail: 'awaiting signal' },
  { key: 'approve',  label: 'approve',  status: 'pending', detail: 'human gate' },
  { key: 'deploy',   label: 'deploy',   status: 'pending' },
  { key: 'monitor',  label: 'monitor',  status: 'pending' },
];

export const STRATEGIES_FIXTURE = [
  { id: 'strat-014', name: 'flagship-momentum',  status: 'live',     sharpe: 1.62, drawdown: -3.4 },
  { id: 'strat-030', name: 'vol-carry',          status: 'paper',    sharpe: 0.94, drawdown: -5.1 },
  { id: 'strat-041', name: 'mean-revert-eu',     status: 'paper',    sharpe: 1.11, drawdown: -4.2 },
  { id: 'strat-052', name: 'archived-trend',     status: 'archived', sharpe: 0.42, drawdown: -8.7 },
  { id: 'strat-063', name: 'liquidity-scout',    status: 'live',     sharpe: 1.28, drawdown: -2.9 },
  { id: 'strat-074', name: 'earnings-momentum',  status: 'paper',    sharpe: 1.55, drawdown: -3.8 },
];

export const MISSION_METRICS_FIXTURE = {
  strategiesLive: { value: '12', delta: '+2 today', tone: 'ok' },
  signalsInQueue: { value: '34', unit: 'jobs', delta: 'steady', tone: 'info' },
  approvalsPending: { value: '3', delta: '1 aged', tone: 'warn' },
  throughput: [12, 15, 14, 18, 22, 20, 26, 24, 28, 30, 27, 32, 34, 30, 36],
};

/**
 * COMMAND · M4 — Operator Inbox event store
 * ----------------------------------------------------------------------------
 * Single source of truth for the operator-inbox events. Today: an in-memory
 * mock stream. Forward-compatible with the future `/api/inbox/events` route.
 *
 * Shape of an event:
 *   { id, category, severity, ts, source, title, subtitle, quickAction }
 *
 * Consumers:
 *   • OperatorInboxDrawer.jsx (drawer + 5 categorised sections)
 *   • DangerRibbon.jsx        (thin status-only ribbon showing the latest danger)
 *
 * Keeping the data here lets both surfaces stay in sync without re-fetching.
 */

export const INBOX_CATEGORIES = [
  { id: 'factory',        label: 'Factory Events',        accent: '#F0B90B', icon: '⚙' },
  { id: 'validation',     label: 'Validation Events',     accent: '#03A9F4', icon: '✓' },
  { id: 'deployment',     label: 'Deployment Events',     accent: '#0ECB81', icon: '▲' },
  { id: 'infrastructure', label: 'Infrastructure Events', accent: '#B895FF', icon: '⊡' },
  { id: 'marketplace',    label: 'Marketplace Events',    accent: '#5E6673', icon: '⛁', future: true },
];

export const SEVERITY_TONE = {
  info:    { dot: '#03A9F4', label: 'info'    },
  success: { dot: '#0ECB81', label: 'success' },
  warn:    { dot: '#F0B90B', label: 'warn'    },
  danger:  { dot: '#F44158', label: 'danger'  },
};

/** Severity priority (high → low) used by the danger ribbon to pick the
 *  single most-important event to surface. */
export const SEVERITY_PRIORITY = { danger: 3, warn: 2, info: 1, success: 0 };

export const MOCK_EVENTS = [
  {
    id: 'evt-001', category: 'factory', severity: 'success',
    ts: Date.now() - 12 * 60_000, source: 'auto-factory.runner',
    title: 'Survivor cohort ready · 14 strategies',
    subtitle: 'Cycle 4/20 · PF≥1.45 · MaxDD≤8% · ready for operator review',
    quickAction: { label: 'Open Auto Factory', route: '/c/mutate#factory-55' },
  },
  {
    id: 'evt-002', category: 'factory', severity: 'info',
    ts: Date.now() - 47 * 60_000, source: 'mutate.engine',
    title: 'Mutation soak completed · 220 candidates',
    subtitle: 'Universe: EURUSD H1 · 6h soak · 18 survivors',
    quickAction: { label: 'Open Auto Select', route: '/c/mutate#auto-select' },
  },
  {
    id: 'evt-003', category: 'factory', severity: 'warn',
    ts: Date.now() - 3 * 3600_000, source: 'generate.engine',
    title: 'Genome pool exhausted on XAUUSD M15',
    subtitle: 'Try widening universe or relaxing min-PF gate',
    quickAction: { label: 'Open Generate', route: '/c/mutate#factory' },
  },
  {
    id: 'evt-101', category: 'validation', severity: 'warn',
    ts: Date.now() - 4 * 60_000, source: 'validation.suite',
    title: 'BI5 realism check pending operator review',
    subtitle: 's_021 EURUSD H1 · slippage spike detected · awaiting verdict',
    quickAction: { label: 'Open Monitoring · BI5', route: '/c/diag#monitoring' },
  },
  {
    id: 'evt-102', category: 'validation', severity: 'success',
    ts: Date.now() - 86 * 60_000, source: 'oos.runner',
    title: 'OOS hold-out passed · 8 strategies',
    subtitle: 'IS/OOS delta within 12% threshold for the survivor cohort',
    quickAction: { label: 'Open Validate', route: '/c/lab#validate' },
  },
  {
    id: 'evt-201', category: 'deployment', severity: 'danger',
    ts: Date.now() - 62 * 60_000, source: 'master-bot.compile',
    title: 'Master Bot compile failed · signing error',
    subtitle: 'mb_032 · X.509 cert expired · regenerate before redeploy',
    quickAction: { label: 'Open Master Bot Compile', route: '/c/mutate#master-bot-compile' },
  },
  {
    id: 'evt-202', category: 'deployment', severity: 'success',
    ts: Date.now() - 5 * 3600_000, source: 'master-bot.runner',
    title: 'Master Bot mb_028 promoted to live',
    subtitle: 'Paper → Live · Track A · Prop Firm · governance approved',
    quickAction: { label: 'Open Trade Runner', route: '/c/exec#runner' },
  },
  {
    id: 'evt-301', category: 'infrastructure', severity: 'warn',
    ts: Date.now() - 4 * 60_000, source: 'bi5.ingest',
    title: 'BI5 ingest stalled at frame 87 / 120',
    subtitle: 'EURUSD M5 · Dukascopy connector lag detected · auto-retry in 60s',
    quickAction: { label: 'Open Ingestion', route: '/c/diag#ingestion' },
  },
  {
    id: 'evt-302', category: 'infrastructure', severity: 'info',
    ts: Date.now() - 25 * 60_000, source: 'llm.runner',
    title: 'LLM runner key rotated · budget refreshed',
    subtitle: 'EMERGENT_LLM_KEY · $200 budget · 0 spent · auto-topup armed',
    quickAction: { label: 'Open Diagnostics', route: '/c/diag' },
  },
  {
    id: 'evt-303', category: 'infrastructure', severity: 'success',
    ts: Date.now() - 9 * 3600_000, source: 'scheduler',
    title: 'Auto-scheduler resumed nightly soak',
    subtitle: 'Soak window 22:00–06:00 UTC · 8h headroom',
    quickAction: { label: 'Open AI Suite', route: '/c/ai' },
  },
];

/** Return the single highest-priority event currently in the inbox (danger
 *  preferred; falls back to warn). Returns null if the inbox is all-clear. */
export function selectTopAlert(events = MOCK_EVENTS) {
  const candidates = events.filter(e => e.severity === 'danger' || e.severity === 'warn');
  if (candidates.length === 0) return null;
  candidates.sort((a, b) => {
    const dp = (SEVERITY_PRIORITY[b.severity] ?? 0) - (SEVERITY_PRIORITY[a.severity] ?? 0);
    if (dp !== 0) return dp;
    return b.ts - a.ts; // most-recent first within the same severity tier
  });
  return candidates[0];
}

/** Format an event timestamp as a short relative-time string. */
export function fmtAgo(ts) {
  const dt = Math.max(0, Date.now() - ts);
  if (dt < 60_000) return 'just now';
  if (dt < 3_600_000) return `${Math.floor(dt / 60_000)}m ago`;
  if (dt < 86_400_000) return `${Math.floor(dt / 3_600_000)}h ago`;
  return `${Math.floor(dt / 86_400_000)}d ago`;
}

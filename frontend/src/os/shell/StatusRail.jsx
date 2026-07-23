/*
 * StatusRail — bottom system-status chrome.
 * refs DESIGN_FREEZE_v1.0.md §1.5 (P·W·F·A·I taxonomy) · Bible §7.6 · D8 §4.I (I10)
 *
 * FE-A refinement (2026-07-23): every chip now hydrates from the live
 * backend via useStatusRailLive() when the operator is authenticated,
 * degrading to fixture defaults pre-auth or when a slot is 401 / 5xx /
 * offline. The chip visual contract (data-testid, tone glyph, label
 * text, · detail suffix) is preserved byte-for-byte with Sprint-1.
 *
 * Signal → backend endpoint map (all pre-existing under Feature Freeze):
 *   Orchestrator → GET /api/orchestrator/status
 *   Ingestion    → GET /api/data-maintenance/status (auto data maintainer)
 *   Scheduler    → GET /api/orchestrator/status.meta.tick_count (0 = paused)
 *   LLM          → GET /api/ai-workforce/providers (first configured)
 *   Governance   → GET /api/governance/summary (via legacy governance router)
 *
 * Every hook is polled at 15 s cadence + revalidated on window focus.
 */
import React, { useEffect, useState } from 'react';
import { useWorkspaceStore } from '../workspace-state/store';
import { useStream } from '../features/useStream';
import { StreamPostmark } from '../features/StreamPostmark';
import { useAuthStore } from '../workspace-state/authStore';
import { apiFetch, isLiveMode } from '../adapters/apiClient';

const TONE_COLORS = {
  P: 'var(--sig-ok)',
  W: 'var(--sig-info)',
  F: 'var(--sig-crit)',
  A: 'var(--sig-warn)',
  I: 'var(--sig-dormant)',
};

// Fixture defaults — used pre-auth AND as a per-chip fall-back so a single
// slow endpoint never breaks the whole rail.
const DEFAULT_CHIPS = {
  orchestrator: { id: 'orchestrator', label: 'Orchestrator', tone: 'P', detail: 'Idle · nominal' },
  ingestion:    { id: 'ingestion',    label: 'Ingestion',    tone: 'P', detail: 'Streaming' },
  scheduler:    { id: 'scheduler',    label: 'Scheduler',    tone: 'I', detail: 'Cron paused' },
  llm:          { id: 'llm',          label: 'LLM',          tone: 'W', detail: 'Warm · Claude Sonnet 4.6' },
  governance:   { id: 'governance',   label: 'Governance',   tone: 'P', detail: 'Gov-Warden · v2.1' },
};

/** Best-effort JSON fetch that always resolves. Never throws — a failed
 *  probe yields null so the chip renders its fixture default. */
const safeFetch = async (path) => {
  if (!isLiveMode()) return null;
  try {
    return await apiFetch(path);
  } catch (_) {
    return null;
  }
};

const inferOrchChip = (raw) => {
  if (!raw) return DEFAULT_CHIPS.orchestrator;
  const running = raw.running === true;
  const err = raw.meta?.last_error;
  const band = raw.meta?.last_tick?.band;
  const tick = raw.meta?.tick_count ?? 0;
  const disp = raw.meta?.dispatched_total ?? 0;
  const tone = err ? 'F' : (!running ? 'I' : band === 'critical' ? 'F' : band === 'warn' ? 'A' : 'P');
  const detail = err
    ? `Error · ${String(err).slice(0, 40)}`
    : !running
      ? 'Halted'
      : `${tick} ticks · ${disp} dispatched · ${band || 'nominal'}`;
  return { ...DEFAULT_CHIPS.orchestrator, tone, detail };
};

const inferSchedulerChip = (raw) => {
  if (!raw) return DEFAULT_CHIPS.scheduler;
  const subordinated = raw.meta?.subordinated_schedulers?.length > 0;
  const tick = raw.meta?.tick_count ?? 0;
  if (raw.running && subordinated) return { ...DEFAULT_CHIPS.scheduler, tone: 'I', detail: 'Subordinated to orchestrator' };
  if (raw.running && tick > 0)     return { ...DEFAULT_CHIPS.scheduler, tone: 'W', detail: `Live · ${tick} ticks` };
  return { ...DEFAULT_CHIPS.scheduler, tone: 'I', detail: 'Cron paused' };
};

const inferIngestionChip = (raw) => {
  if (!raw) return DEFAULT_CHIPS.ingestion;
  const enabled = raw.enabled === true || raw.running === true;
  const lastRun = raw.last_run_at || raw.last_run || null;
  const gaps = raw.gaps ?? raw.missing ?? 0;
  const tone = !enabled ? 'I' : gaps > 0 ? 'A' : 'P';
  const detail = !enabled ? 'Paused' : gaps > 0 ? `${gaps} gaps` : (lastRun ? `Streaming · ${String(lastRun).slice(11, 16)}Z` : 'Streaming');
  return { ...DEFAULT_CHIPS.ingestion, tone, detail };
};

const inferLLMChip = (raw) => {
  if (!raw) return DEFAULT_CHIPS.llm;
  const providers = Array.isArray(raw) ? raw : (raw.providers || raw.items || []);
  const configured = providers.filter((p) => p.configured || p.enabled || p.available);
  const openCircuit = configured.find((p) => (p.circuit === 'open' || p.state === 'open'));
  const active = configured.find((p) => p.active) || configured[0];
  const tone = openCircuit ? 'F' : configured.length === 0 ? 'I' : 'W';
  const detail = openCircuit
    ? `Circuit open · ${openCircuit.name || openCircuit.provider || 'provider'}`
    : configured.length === 0
      ? 'No provider configured'
      : `Warm · ${active?.name || active?.provider || active?.id || 'provider'}${active?.model ? ` · ${active.model}` : ''}`;
  return { ...DEFAULT_CHIPS.llm, tone, detail };
};

const inferGovernanceChip = (raw) => {
  if (!raw) return DEFAULT_CHIPS.governance;
  const alerts = raw.open_alerts ?? raw.alerts ?? 0;
  const version = raw.version || raw.warden_version || DEFAULT_CHIPS.governance.detail.split(' · ')[1];
  const tone = alerts > 0 ? 'A' : 'P';
  const detail = alerts > 0 ? `${alerts} open alerts` : `Gov-Warden · ${version || 'active'}`;
  return { ...DEFAULT_CHIPS.governance, tone, detail };
};

/**
 * useStatusRailLive — one shared timer that hits five endpoints in
 * parallel every 15 s, plus one refresh on window focus. Guarded so it
 * never fires while the operator is signed out.
 */
const useStatusRailLive = ({ enabled }) => {
  const [chips, setChips] = useState(DEFAULT_CHIPS);

  useEffect(() => {
    if (!enabled) return undefined;
    let cancelled = false;

    const refresh = async () => {
      const [orch, ingest, providers, gov] = await Promise.all([
        safeFetch('/api/orchestrator/status'),
        safeFetch('/api/data-maintenance/status'),
        safeFetch('/api/ai-workforce/providers'),
        safeFetch('/api/governance/summary'),
      ]);
      if (cancelled) return;
      setChips({
        orchestrator: inferOrchChip(orch),
        scheduler:    inferSchedulerChip(orch),  // same source, different projection
        ingestion:    inferIngestionChip(ingest),
        llm:          inferLLMChip(providers),
        governance:   inferGovernanceChip(gov),
      });
    };

    refresh();
    const id = setInterval(refresh, 15_000);
    const onFocus = () => { refresh(); };
    window.addEventListener('focus', onFocus);
    return () => {
      cancelled = true;
      clearInterval(id);
      window.removeEventListener('focus', onFocus);
    };
  }, [enabled]);

  return chips;
};

export const StatusRail = ({ preAuth = false }) => {
  const killPostureArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const stance = useAuthStore((s) => s.stance);
  const streamStatus = useStream('status-rail', { intervalMs: 10_000 });

  const authenticated = stance === 'authenticated' && !preAuth;
  const live = useStatusRailLive({ enabled: authenticated });
  const chips = authenticated ? live : DEFAULT_CHIPS;

  const killChip = killPostureArmed
    ? { id: 'kill', label: 'Kill posture', tone: 'F', detail: 'ARMED' }
    : { id: 'kill', label: 'Kill posture', tone: 'I', detail: 'Disarmed' };

  const ORDERED = [chips.orchestrator, chips.ingestion, chips.scheduler, chips.llm, chips.governance, killChip];

  return (
    <footer data-testid="status-rail-region" role="contentinfo" aria-label="System status" style={{ display: 'block' }}>
    <div data-testid="status-rail"
         tabIndex={0}
         aria-label="System status rail"
         data-live={authenticated ? 'true' : 'false'}
         style={{
           background: 'var(--surface-1)',
           borderTop: '1px solid var(--stroke-1)',
           padding: 'var(--space-2) var(--space-5)',
           display: 'flex',
           alignItems: 'center',
           gap: 'var(--space-4)',
           fontSize: 'var(--font-caption)',
           letterSpacing: '0.06em',
           textTransform: 'uppercase',
           color: 'var(--content-md)',
           overflow: 'auto',
         }}>
      {ORDERED.map((c) => (
        <div key={c.id}
             data-testid={`status-chip-${c.id}`}
             style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', whiteSpace: 'nowrap' }}>
          <span aria-hidden style={{ width: 6, height: 6, borderRadius: '50%', background: TONE_COLORS[c.tone], boxShadow: c.tone === 'P' ? 'var(--glow-active)' : 'none' }} />
          <span style={{ color: 'var(--content-lo)' }}>{c.tone}</span>
          <span>{c.label}</span>
          <span style={{ color: 'var(--content-lo)' }}>· {c.detail}</span>
        </div>
      ))}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}
           data-testid="status-rail-postmark">
        <StreamPostmark status={streamStatus} testId="status-rail-stream-postmark" />
        <span style={{ color: 'var(--content-lo)' }}>
          {preAuth ? 'Pre-auth · public status' : authenticated ? 'System status · live' : 'System status · offline'}
        </span>
      </div>
    </div>
    </footer>
  );
};

/*
 * StatusRail — bottom system-status chrome.
 * refs DESIGN_FREEZE_v1.0.md §1.5 (P·W·F·A·I taxonomy) · Bible §7.6 · D8 §4.I (I10)
 *
 * Six chips: Orchestrator · Ingestion · Scheduler · LLM · Governance · Kill posture.
 * Each chip resolves to one of five signal tones (Bible §5.1):
 *   P Passing · W Working · F Failed · A Attention · I Idle (Dormant).
 *
 * Sprint 1 M1 ships fixture data; M3 wires adapters against v1.1.0-stage4.
 */
import React from 'react';
import { useWorkspaceStore } from '../workspace-state/store';
import { useStream } from '../features/useStream';
import { StreamPostmark } from '../features/StreamPostmark';

const CHIPS = [
  { id: 'orchestrator', label: 'Orchestrator', tone: 'P', detail: 'Idle · nominal' },
  { id: 'ingestion',    label: 'Ingestion',    tone: 'P', detail: 'Streaming' },
  { id: 'scheduler',    label: 'Scheduler',    tone: 'I', detail: 'Cron paused' },
  { id: 'llm',          label: 'LLM',          tone: 'W', detail: 'Warm · Claude Sonnet 4.6' },
  { id: 'governance',   label: 'Governance',   tone: 'P', detail: 'Gov-Warden · v2.1' },
];

const TONE_COLORS = {
  P: 'var(--sig-ok)',
  W: 'var(--sig-info)',
  F: 'var(--sig-crit)',
  A: 'var(--sig-warn)',
  I: 'var(--sig-dormant)',
};

export const StatusRail = ({ preAuth = false }) => {
  const killPostureArmed = useWorkspaceStore((s) => s.killPostureArmed);
  const streamStatus = useStream('status-rail', { intervalMs: 10_000 });
  const killChip = killPostureArmed
    ? { id: 'kill', label: 'Kill posture', tone: 'F', detail: 'ARMED' }
    : { id: 'kill', label: 'Kill posture', tone: 'I', detail: 'Disarmed' };

  return (
    <footer data-testid="status-rail-region" role="contentinfo" aria-label="System status" style={{ display: 'block' }}>
    <div data-testid="status-rail"
         tabIndex={0}
         aria-label="System status rail"
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
      {[...CHIPS, killChip].map((c) => (
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
          {preAuth ? 'Pre-auth · public status' : 'System status · live'}
        </span>
      </div>
    </div>
    </footer>
  );
};

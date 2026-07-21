/*
 * PipelineStageBar — Bible §7.3 · 8 canonical stages.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { motion } from 'framer-motion';
import { useMotionEnabled, fadeInUp } from './motion';

const DEFAULT_STAGES = [
  { key: 'ingest',   label: 'ingest',   status: 'done',    detail: '18/18 tickers' },
  { key: 'candle',   label: 'candle',   status: 'done',    detail: 'candles@v3' },
  { key: 'feature',  label: 'feature',  status: 'done',    detail: '112 features' },
  { key: 'signal',   label: 'signal',   status: 'active',  detail: 'training epoch 4/6' },
  { key: 'backtest', label: 'backtest', status: 'pending', detail: 'awaiting signal' },
  { key: 'approve',  label: 'approve',  status: 'pending', detail: 'human gate' },
  { key: 'deploy',   label: 'deploy',   status: 'pending' },
  { key: 'monitor',  label: 'monitor',  status: 'pending' },
];

const TONE = {
  done:    { bg: 'rgba(61,220,132,0.12)',  fg: 'var(--sig-ok)',      border: 'var(--sig-ok)' },
  active:  { bg: 'rgba(78,161,243,0.18)',  fg: 'var(--sig-info)',    border: 'var(--sig-info)' },
  pending: { bg: 'transparent',            fg: 'var(--content-lo)',  border: 'var(--stroke-2)' },
  blocked: { bg: 'rgba(255,91,91,0.14)',   fg: 'var(--sig-crit)',    border: 'var(--sig-crit)' },
  skipped: { bg: 'transparent',            fg: 'var(--sig-dormant)', border: 'var(--stroke-1)' },
};

const ariaTone = (s) => s === 'done' ? 'ok' : s === 'active' ? 'info' : s === 'blocked' ? 'crit' : 'dormant';

export const PipelineStageBar = ({ stages = DEFAULT_STAGES, testId }) => {
  const motionEnabled = useMotionEnabled();
  const El = motionEnabled ? motion.div : 'div';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};

  return (
    <El data-testid={testId ?? 'pipeline-stage-bar'} {...motionProps}
        role="group" aria-label="Pipeline stages"
        style={{ display: 'grid', gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))`,
                 gap: 2, background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                 borderRadius: 'var(--radius-2)', padding: 2 }}>
      {stages.map((s) => {
        const t = TONE[s.status];
        return (
          <div key={s.key} title={s.detail} data-testid={`pipeline-stage-${s.key}`}
               aria-label={`${s.label} ${ariaTone(s.status)}`}
               style={{ background: t.bg, color: t.fg, borderTop: `2px solid ${t.border}`,
                        padding: '10px 8px', fontSize: 'var(--font-caption)',
                        textTransform: 'uppercase', letterSpacing: '0.08em',
                        display: 'flex', flexDirection: 'column', gap: 4,
                        minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        transition: 'background-color var(--dur-medium) var(--ease-standard)' }}>
            <span style={{ fontFamily: 'ui-monospace, monospace' }}>{s.label}</span>
            {s.detail && <span style={{ color: 'var(--content-lo)', fontSize: 10 }}>{s.detail}</span>}
          </div>
        );
      })}
    </El>
  );
};

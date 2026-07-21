/*
 * ActivityRow — Bible §7.4 · D2 §3–§5.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { motion } from 'framer-motion';
import { useMotionEnabled, fadeIn } from './motion';
import { Chip } from './Chip';
import { useWorkspaceStore } from '../workspace-state/store';

const ACTOR_LABEL = {
  operator: 'Operator', 'master-bot': 'Master Bot', worker: 'Worker',
  scheduler: 'Scheduler', ingestion: 'Ingestion', governance: 'Governance',
  llm: 'LLM', validator: 'Validator', system: 'System', user: 'User',
};

const ACTOR_ACCENT = {
  operator: 'var(--sig-info)', 'master-bot': 'var(--accent-gold)', worker: 'var(--c1)',
  scheduler: 'var(--c5)', ingestion: 'var(--c2)', governance: 'var(--sig-warn)',
  llm: 'var(--c6)', validator: 'var(--c0)', system: 'var(--content-lo)', user: 'var(--content-md)',
};

export const ActivityRow = ({ timestamp, actor, verb, subject, outcome, trailer, onOpen, testId }) => {
  const motionEnabled = useMotionEnabled();
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const El = motionEnabled ? motion.div : 'div';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeIn } : {};
  const ActorIcon = actor.icon;

  return (
    <El data-testid={testId ?? `activity-${timestamp}-${actor.kind}`}
        {...motionProps}
        role="listitem"
        tabIndex={onOpen ? 0 : -1}
        onClick={onOpen}
        onKeyDown={(e) => { if (onOpen && e.key === 'Enter') onOpen(); }}
        style={{ display: 'grid',
                 gridTemplateColumns: 'auto 88px 140px 1fr auto',
                 gap: 'var(--space-3)', alignItems: 'center',
                 padding: '8px 12px', borderBottom: '1px solid var(--stroke-1)',
                 cursor: onOpen ? 'pointer' : 'default',
                 transition: 'background-color var(--dur-fast) var(--ease-standard)' }}
        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
      <span aria-hidden style={{ width: 6, height: 6, borderRadius: 999,
                                  background: ACTOR_ACCENT[actor.kind], display: 'inline-block' }} />
      <span className="mono-num"
            style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                     textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {timestamp}
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                     fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                     textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {ActorIcon && <ActorIcon size={12} color={ACTOR_ACCENT[actor.kind]} aria-hidden />}
        {actor.name ?? ACTOR_LABEL[actor.kind]}
      </span>
      <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)',
                     minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        <span style={{ color: 'var(--content-md)' }}>{verb}</span>{' '}
        <span className="mono-num">{subject}</span>
        {advLens && trailer && (
          <span className="mono-num" style={{ color: 'var(--content-lo)',
                                              fontSize: 'var(--font-caption)', marginLeft: 8 }}>
            · {trailer}
          </span>
        )}
      </span>
      {outcome && <Chip tone={outcome.tone} label={outcome.label} />}
    </El>
  );
};

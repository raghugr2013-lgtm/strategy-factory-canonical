/*
 * WorkerCard — Bible §7.6 · D4 §5.3.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { motion } from 'framer-motion';
import { useMotionEnabled, fadeInUp } from './motion';
import { Chip } from './Chip';

const STATE_TONE = {
  active:  { chip: 'ok',      accent: 'var(--sig-ok)',      label: 'active' },
  idle:    { chip: 'info',    accent: 'var(--sig-info)',    label: 'idle' },
  error:   { chip: 'crit',    accent: 'var(--sig-crit)',    label: 'error' },
  blocked: { chip: 'warn',    accent: 'var(--sig-warn)',    label: 'blocked' },
  dormant: { chip: 'dormant', accent: 'var(--sig-dormant)', label: 'dormant' },
};

export const WorkerCard = ({ name, purpose, subject, state, icon: Icon, onOpen, testId }) => {
  const motionEnabled = useMotionEnabled();
  const El = motionEnabled ? motion.article : 'article';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};
  const t = STATE_TONE[state];

  return (
    <El data-testid={testId ?? `worker-${name.replace(/\W+/g, '-')}`}
        {...motionProps}
        tabIndex={onOpen ? 0 : -1}
        onClick={onOpen}
        onKeyDown={(e) => { if (onOpen && e.key === 'Enter') onOpen(); }}
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
                 background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                 borderLeft: `2px solid ${t.accent}`, borderRadius: 'var(--radius-3)',
                 padding: 'var(--space-4)', cursor: onOpen ? 'pointer' : 'default',
                 opacity: state === 'dormant' ? 0.6 : 1,
                 transition: 'transform var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-standard)' }}
        onMouseEnter={(e) => { if (onOpen) e.currentTarget.style.transform = 'translateY(-1px)'; }}
        onMouseLeave={(e) => { if (onOpen) e.currentTarget.style.transform = 'translateY(0)'; }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                    fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                    textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {Icon && <Icon size={12} color={t.accent} aria-hidden />}
        <span className="mono-num">{name}</span>
        <span style={{ marginLeft: 'auto' }}><Chip tone={t.chip} label={t.label} /></span>
      </div>
      <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', lineHeight: 1.4 }}>
        {purpose}
      </div>
      {subject && (
        <div className="mono-num"
             style={{ fontSize: 'var(--font-caption)', color: 'var(--content-md)',
                      borderTop: '1px solid var(--stroke-1)', paddingTop: 'var(--space-2)' }}>
          subject · {subject}
        </div>
      )}
    </El>
  );
};

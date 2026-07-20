/*
 * ActivityRow — Bible §7.4, D2 §3–§5.
 * A single AI Activity Timeline row.
 * Anatomy: [glyph] · timestamp · actor · verb · subject · outcome-chip · advanced trailer
 *
 * Supports 10 actor types via `actor.kind`, colour-coded but never redundant
 * (Chip carries the letter glyph fallback).
 */
import type { LucideIcon } from 'lucide-react';
import { motion } from 'framer-motion';
import { useMotionEnabled, fadeIn } from './motion';
import { Chip, type ChipTone } from './Chip';
import { useWorkspaceStore } from '../workspace-state/store';

export type ActorKind =
  | 'operator' | 'master-bot' | 'worker' | 'scheduler'
  | 'ingestion' | 'governance' | 'llm' | 'validator'
  | 'system' | 'user';

const actorLabel: Record<ActorKind, string> = {
  operator: 'Operator', 'master-bot': 'Master Bot', worker: 'Worker',
  scheduler: 'Scheduler', ingestion: 'Ingestion', governance: 'Governance',
  llm: 'LLM', validator: 'Validator', system: 'System', user: 'User',
};

const actorAccent: Record<ActorKind, string> = {
  operator: 'var(--sig-info)',
  'master-bot': 'var(--accent-gold)',
  worker: 'var(--c1)',
  scheduler: 'var(--c5)',
  ingestion: 'var(--c2)',
  governance: 'var(--sig-warn)',
  llm: 'var(--c6)',
  validator: 'var(--c0)',
  system: 'var(--content-lo)',
  user: 'var(--content-md)',
};

export interface ActivityRowProps {
  timestamp: string;               // ISO or short "12:34:56"
  actor: { kind: ActorKind; name?: string; icon?: LucideIcon };
  verb: string;                    // e.g. "approved", "generated", "gated"
  subject: string;                 // artefact id / label
  outcome?: { tone: ChipTone; label: string };
  trailer?: string;                // advanced footnote
  onOpen?: () => void;
  testId?: string;
}

export const ActivityRow: React.FC<ActivityRowProps> = ({
  timestamp, actor, verb, subject, outcome, trailer, onOpen, testId,
}) => {
  const motionEnabled = useMotionEnabled();
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const El: React.ElementType = motionEnabled ? motion.div : 'div';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeIn } : {};
  const ActorIcon = actor.icon;

  return (
    <El
      data-testid={testId ?? `activity-${timestamp}-${actor.kind}`}
      {...motionProps}
      role="listitem"
      tabIndex={onOpen ? 0 : -1}
      onClick={onOpen}
      onKeyDown={(e) => { if (onOpen && e.key === 'Enter') onOpen(); }}
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 88px 140px 1fr auto',
        gap: 'var(--space-3)',
        alignItems: 'center',
        padding: '8px 12px',
        borderBottom: '1px solid var(--stroke-1)',
        cursor: onOpen ? 'pointer' : 'default',
        transition: `background-color var(--dur-fast) var(--ease-standard)`,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--surface-2)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      <span
        aria-hidden="true"
        style={{
          width: 6, height: 6, borderRadius: 999,
          background: actorAccent[actor.kind],
          display: 'inline-block',
        }}
      />
      <span
        className="mono-num"
        style={{
          fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        {timestamp}
      </span>
      <span
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 'var(--font-caption)', color: 'var(--content-md)',
          textTransform: 'uppercase', letterSpacing: '0.06em',
        }}
      >
        {ActorIcon && <ActorIcon size={12} color={actorAccent[actor.kind]} aria-hidden="true" />}
        {actor.name ?? actorLabel[actor.kind]}
      </span>
      <span style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-hi)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>
        <span style={{ color: 'var(--content-md)' }}>{verb}</span>{' '}
        <span className="mono-num">{subject}</span>
        {advLens && trailer && (
          <span className="mono-num" style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)', marginLeft: 8 }}>
            · {trailer}
          </span>
        )}
      </span>
      {outcome && <Chip tone={outcome.tone} label={outcome.label} />}
    </El>
  );
};

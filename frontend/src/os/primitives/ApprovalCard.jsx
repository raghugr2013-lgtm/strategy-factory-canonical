/*
 * ApprovalCard — Bible §7.5 · D3 §2.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { motion } from 'framer-motion';
import { CheckCircle2, Clock, Ban } from 'lucide-react';
import { Chip } from './Chip';
import { ProvenanceTriple } from './ProvenanceTriple';
import { useMotionEnabled, fadeInUp } from './motion';
import { useWorkspaceStore } from '../workspace-state/store';

const RISK_TONE = {
  low:      { chip: 'ok',       label: 'low risk' },
  moderate: { chip: 'advisory', label: 'moderate risk' },
  high:     { chip: 'crit',     label: 'high risk' },
};

const ORIGIN_LABEL = {
  strategy: 'strategy', 'schema-change': 'schema change',
  'policy-change': 'policy change', 'compute-quota': 'compute quota',
  'access-request': 'access request', 'data-ingest': 'data ingest',
};

export const ApprovalCard = ({
  title, origin, risk, summary, provenance, decisionIdentity, ageMinutes,
  onApprove, onDefer, onBlock, testId,
}) => {
  const motionEnabled = useMotionEnabled();
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const El = motionEnabled ? motion.article : 'article';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};
  const code = title.toLowerCase().replace(/\W+/g, '-').slice(0, 40);
  const rootId = testId ?? `approval-${code}`;
  const t = RISK_TONE[risk];
  const borderColor = risk === 'high' ? 'var(--sig-crit)' :
                      risk === 'moderate' ? 'var(--sig-advisory)' : 'var(--sig-ok)';

  return (
    <El data-testid={rootId} {...motionProps}
        style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)',
                 background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                 borderTop: `2px solid ${borderColor}`, borderRadius: 'var(--radius-3)',
                 padding: 'var(--space-5)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        <Chip tone={t.chip} label={t.label} />
        <Chip tone="info" label={ORIGIN_LABEL[origin]} showGlyph={false} />
        {ageMinutes !== undefined && (
          <span className="mono-num"
                style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                         color: ageMinutes > 60 ? 'var(--sig-warn)' : 'var(--content-lo)',
                         textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            aged {ageMinutes}m
          </span>
        )}
      </div>
      <div style={{ fontSize: 'var(--font-body-md)', color: 'var(--content-hi)', lineHeight: 1.35 }}>{title}</div>
      <div style={{ fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.5 }}>{summary}</div>
      <ProvenanceTriple {...provenance} />
      {advLens && decisionIdentity && (
        <div className="mono-num"
             style={{ fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                      borderTop: '1px solid var(--stroke-1)', paddingTop: 'var(--space-2)' }}>
          {decisionIdentity}
        </div>
      )}
      <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-2)' }}>
        <button data-testid={`${rootId}-approve`} onClick={onApprove}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                         background: 'var(--sig-ok)', color: 'var(--surface-0)',
                         border: 'none', borderRadius: 'var(--radius-1)',
                         padding: '8px 14px', fontSize: 'var(--font-body-sm)',
                         fontFamily: 'inherit', cursor: 'pointer',
                         transition: 'filter var(--dur-fast) var(--ease-standard)' }}
                onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.1)')}
                onMouseLeave={(e) => (e.currentTarget.style.filter = 'brightness(1)')}>
          <CheckCircle2 size={14} /> Approve
        </button>
        <button data-testid={`${rootId}-defer`} onClick={onDefer}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                         background: 'transparent', color: 'var(--content-md)',
                         border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-1)',
                         padding: '8px 14px', fontSize: 'var(--font-body-sm)',
                         fontFamily: 'inherit', cursor: 'pointer' }}>
          <Clock size={14} /> Defer
        </button>
        <button data-testid={`${rootId}-block`} onClick={onBlock}
                style={{ display: 'inline-flex', alignItems: 'center', gap: 6,
                         background: 'transparent', color: 'var(--sig-crit)',
                         border: '1px solid var(--sig-crit)', borderRadius: 'var(--radius-1)',
                         padding: '8px 14px', fontSize: 'var(--font-body-sm)',
                         fontFamily: 'inherit', cursor: 'pointer', marginLeft: 'auto' }}>
          <Ban size={14} /> Block
        </button>
      </div>
    </El>
  );
};

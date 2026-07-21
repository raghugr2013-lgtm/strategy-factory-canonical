/*
 * ChartTile — Bible §7.11.2. Sprint 1 supports line + sparkline.
 * refs DESIGN_FREEZE_v1.0.md §1.3
 */
import React from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, MinusCircle, Download } from 'lucide-react';
import { useMotionEnabled, fadeInUp } from './motion';
import { SignatureFrame } from './SignatureFrame';
import { StateTemplate } from './StateTemplate';
import { Chip } from './Chip';
import { useWorkspaceStore } from '../workspace-state/store';

const TONE = { ok: 'var(--sig-ok)', info: 'var(--sig-info)', warn: 'var(--sig-warn)',
               crit: 'var(--sig-crit)', advisory: 'var(--sig-advisory)',
               dormant: 'var(--sig-dormant)', gold: 'var(--accent-gold)' };

const buildPath = (pts, w, h) => {
  if (!pts.length) return '';
  const min = Math.min(...pts), max = Math.max(...pts), span = (max - min) || 1;
  const stepX = w / (pts.length - 1 || 1);
  return pts.map((p, i) => {
    const x = i * stepX; const y = h - ((p - min) / span) * h;
    return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
};

export const ChartTile = ({
  caption, points, variant = 'line', timeWindow = 'last 24h', unit,
  state = 'happy', tone = 'info', onDrill, testId,
}) => {
  const motionEnabled = useMotionEnabled();
  const advLens = useWorkspaceStore((s) => s.advancedLens);
  const code = caption.toLowerCase().replace(/\W+/g, '-');
  const isSpark = variant === 'sparkline';
  const w = isSpark ? 120 : 480;
  const h = isSpark ? 32 : 160;

  const El = motionEnabled ? motion.div : 'div';
  const motionProps = motionEnabled ? { initial: 'hidden', animate: 'visible', variants: fadeInUp } : {};

  let body;
  if (state === 'error') {
    body = (
      <StateTemplate variant="error" code={`${code}-error`} icon={AlertTriangle} tone="crit"
                     headline="Chart unavailable." purpose="The upstream series failed to load."
                     advancedFootnote="candles@v3 · gap 08:00–09:00 · retrying" />
    );
  } else if (state === 'empty' || (state === 'happy' && !points.length)) {
    body = (
      <StateTemplate variant="empty" code={`${code}-empty`} icon={MinusCircle} tone="dormant"
                     headline="No observations in this window."
                     purpose="Widen the time window or try another market." />
    );
  } else if (state === 'loading') {
    body = (
      <div aria-hidden style={{ width: '100%', height: h,
        background: 'linear-gradient(90deg, var(--surface-2) 0%, var(--surface-3) 50%, var(--surface-2) 100%)',
        backgroundSize: '200% 100%', animation: 'sf-skeleton 1.6s var(--ease-standard) infinite',
        borderRadius: 'var(--radius-2)' }} />
    );
  } else {
    const max = Math.max(...points), min = Math.min(...points);
    body = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
             role="img" aria-label={`${caption} ${variant}`} onClick={onDrill}
             style={{ cursor: onDrill ? 'crosshair' : 'default', opacity: state === 'dormant' ? 0.5 : 1 }}>
          {!isSpark && Array.from({ length: 3 }).map((_, i) => (
            <line key={i} x1={0} x2={w} y1={(h/3)*(i+1)} y2={(h/3)*(i+1)}
                  stroke="var(--stroke-1)" strokeDasharray="2 4" />
          ))}
          <path d={buildPath(points, w, h)} fill="none" stroke={TONE[tone]} strokeWidth={1.5} />
        </svg>
        {!isSpark && (
          <div className="mono-num"
               style={{ display: 'flex', justifyContent: 'space-between',
                        fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
                        textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            <span>high {max.toFixed(2)}{unit ? ` ${unit}` : ''}</span>
            <span>low {min.toFixed(2)}{unit ? ` ${unit}` : ''}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <El data-testid={testId ?? `chart-${code}`} {...motionProps}>
      <SignatureFrame tone={tone === 'gold' ? 'gold' : tone} caption={caption}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          <Chip tone="info" label={timeWindow} showGlyph={false} testId={`${code}-window`} />
          {advLens && (
            <button data-testid={`${code}-export`}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginLeft: 'auto',
                             background: 'transparent', border: '1px solid var(--stroke-2)',
                             color: 'var(--content-md)', fontFamily: 'inherit',
                             fontSize: 'var(--font-caption)', textTransform: 'uppercase',
                             letterSpacing: '0.06em', padding: '2px 6px', borderRadius: 'var(--radius-1)' }}>
              <Download size={10} /> CSV
            </button>
          )}
        </div>
        {body}
      </SignatureFrame>
    </El>
  );
};

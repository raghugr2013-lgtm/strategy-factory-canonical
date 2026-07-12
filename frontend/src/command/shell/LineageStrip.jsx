/**
 * COMMAND · Phase U.1 — Lineage widgets (lightweight, additive)
 * ----------------------------------------------------------------------------
 * Operator decree: keep the first version lightweight; do not build a giant
 * graph engine. Three forms exist on paper; U.1 ships two:
 *
 *   <LineageStrip />   compact horizontal SVG, 3–5 nodes, hover hints
 *   <LineageInline />  inline 5-dot pill — embeddable in any chip row
 *
 * The full <LineagePanel /> is reserved for Phase U.4.
 *
 * Data source: a `lineage` prop OR a `fetchLineage(id)` async callback. U.1
 * ships with the mock helper so the widget renders correctly in
 * /command-preview without any backend change.
 */
import React, { useEffect, useState } from 'react';

/* ────────── Data shape ──────────
   Lineage = {
     strategyId: string,
     activeIndex: number,         // node index that is the current/active one
     nodes: [{
        id: string,
        ai: bool,                  // AI-derived?
        confidence: number,        // 0..1
        regimeFit: [bool x5],
        actor: string,             // 'groq', 'anthropic', 'manual', ...
        ts: string,                // ISO
     }]
   }
*/

export function mockLineage(strategyId = 'STR-2C1A47F9') {
  return {
    strategyId,
    activeIndex: 3,
    nodes: [
      { id: 'STR-A001', ai: false, confidence: 0.62, regimeFit: [1, 1, 0, 0, 0], actor: 'manual',    ts: '2026-05-21T08:01:00Z' },
      { id: 'MUT-7B12', ai: true,  confidence: 0.71, regimeFit: [1, 1, 1, 0, 0], actor: 'groq',      ts: '2026-05-23T14:18:00Z' },
      { id: 'MUT-9C04', ai: true,  confidence: 0.68, regimeFit: [1, 1, 0, 0, 1], actor: 'anthropic', ts: '2026-05-25T03:42:00Z' },
      { id: strategyId, ai: true,  confidence: 0.74, regimeFit: [1, 1, 1, 0, 0], actor: 'groq',      ts: '2026-05-26T11:30:00Z' },
    ],
  };
}

/* ────────── <LineageInline /> — 5-dot embeddable pill ────────── */
export function LineageInline({ lineage, ariaLabel }) {
  if (!lineage || !lineage.nodes) return null;
  const last5 = lineage.nodes.slice(-5);
  const padding = Math.max(0, 5 - last5.length);
  const dots = [
    ...Array(padding).fill({ kind: 'empty' }),
    ...last5.map((n, i) => ({
      kind: 'present',
      ai: n.ai,
      active: i + padding === (lineage.activeIndex - (lineage.nodes.length - last5.length)),
    })),
  ];
  return (
    <span
      className="lineage-inline"
      data-testid="lineage-inline"
      aria-label={ariaLabel || 'Lineage'}
    >
      LIN
      <span className="lineage-inline__dots">
        {dots.map((d, i) => {
          let cls = 'lineage-inline__dot';
          if (d.kind === 'present') {
            if (d.active) cls += ' lineage-inline__dot--active';
            else if (d.ai) cls += ' lineage-inline__dot--ai';
          }
          return <span key={i} className={cls} />;
        })}
      </span>
      <span style={{ color: 'var(--cmd-ink-1)' }}>
        {lineage.nodes.length}
      </span>
    </span>
  );
}

/* ────────── <LineageStrip /> — compact horizontal SVG strip ────────── */
export default function LineageStrip({
  strategyId,
  lineage,
  fetchLineage,
  height = 140,
  variant = 'standard',
  onNodeClick,
}) {
  const [data, setData] = useState(lineage || null);

  useEffect(() => {
    if (lineage) { setData(lineage); return; }
    if (fetchLineage && strategyId) {
      let cancelled = false;
      (async () => {
        try {
          const d = await fetchLineage(strategyId);
          if (!cancelled) setData(d);
        } catch (_) { /* noop */ }
      })();
      return () => { cancelled = true; };
    }
    // Last resort — use mock so the widget never renders empty
    setData(mockLineage(strategyId));
    return undefined;
  }, [strategyId, lineage, fetchLineage]);

  if (!data || !data.nodes || data.nodes.length === 0) {
    return (
      <div className="lineage-strip" data-testid="lineage-strip-empty">
        <div className="lineage-strip__hd">· lineage · no ancestry</div>
        <div style={{ fontSize: 11, color: 'var(--cmd-ink-2)' }}>
          No mutation history recorded for this strategy yet.
        </div>
      </div>
    );
  }

  const padX = 36;
  const padY = variant === 'compact' ? 24 : 38;
  const w = 880;
  const h = height;
  const stepX = data.nodes.length > 1
    ? (w - padX * 2) / (data.nodes.length - 1)
    : 0;
  const baseY = h / 2;
  const wave = variant === 'compact' ? 12 : 22;

  const nodes = data.nodes.map((n, i) => ({
    ...n,
    cx: padX + i * stepX,
    cy: baseY + (i % 2 === 0 ? -wave : wave) * (i === 0 ? 0 : 1),
    active: i === data.activeIndex,
  }));

  return (
    <div className="lineage-strip" data-testid="lineage-strip">
      <div className="lineage-strip__hd">
        · lineage · {data.strategyId}
        <span style={{ flex: 1 }} />
        <span className="chip chip--violet">
          <span className="chip__dot" />
          <span className="chip__label">{nodes.filter((n) => n.ai).length} AI-mutated</span>
        </span>
        <span className="chip chip--cyan" style={{ marginLeft: 6 }}>
          <span className="chip__dot cmd-dot--live" />
          <span className="chip__label">depth {nodes.length}</span>
        </span>
      </div>

      <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} role="img" aria-label="Strategy lineage">
        {/* edges */}
        {nodes.slice(0, -1).map((n, i) => {
          const next = nodes[i + 1];
          const active = next.active || n.active;
          const c1x = n.cx + stepX / 2;
          const c1y = n.cy;
          const c2x = next.cx - stepX / 2;
          const c2y = next.cy;
          return (
            <path
              key={`e-${i}`}
              className={`lineage__edge${active ? ' lineage__edge--active' : ''}`}
              d={`M ${n.cx} ${n.cy} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${next.cx} ${next.cy}`}
            />
          );
        })}
        {/* nodes */}
        {nodes.map((n, i) => {
          const r = 9;
          const cls = n.active
            ? 'lineage__node lineage__node--active'
            : n.ai ? 'lineage__node lineage__node--ai' : 'lineage__node';
          return (
            <g
              key={n.id}
              transform={`translate(${n.cx - r} ${n.cy - r})`}
              style={{ cursor: onNodeClick ? 'pointer' : 'default' }}
              onClick={() => onNodeClick && onNodeClick(n, i)}
            >
              <foreignObject width={r * 2} height={r * 2}>
                <div
                  className={cls}
                  style={{ width: '100%', height: '100%' }}
                  title={`${n.id} · C ${n.confidence.toFixed(2)} · ${n.actor}`}
                />
              </foreignObject>
              <text
                x={r}
                y={r * 2 + 12}
                textAnchor="middle"
                fill="var(--cmd-ink-2)"
                fontSize="9"
                fontFamily="JetBrains Mono"
                letterSpacing="0.04em"
              >
                {n.id.length > 8 ? `${n.id.slice(0, 8)}…` : n.id}
              </text>
              <text
                x={r}
                y={r * 2 + 22}
                textAnchor="middle"
                fill={n.active ? 'var(--cmd-cyan)' : 'var(--cmd-ink-2)'}
                fontSize="9"
                fontFamily="JetBrains Mono"
              >
                C {n.confidence.toFixed(2)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

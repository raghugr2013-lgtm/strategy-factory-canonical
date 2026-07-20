/*
 * Timeline — Bible §7.4, D2.
 * The AI Activity Timeline. Chronological stream of every actor's actions,
 * with a coarse facet chip strip (Sprint 1: actor kind only). Row click
 * opens a detail focus card inline (evidence drawer opens with lineage).
 */
import { useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { ActivityRow } from '../primitives/ActivityRow';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';
import { Chip, type ChipTone } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import type { ActorKind } from '../primitives/ActivityRow';
import { useScenarioFixture } from '../gallery/scenarioFixtures';

const ACTOR_FILTERS: Array<{ key: ActorKind | 'all'; label: string }> = [
  { key: 'all',         label: 'all' },
  { key: 'master-bot',  label: 'master' },
  { key: 'worker',      label: 'workers' },
  { key: 'governance',  label: 'governance' },
  { key: 'ingestion',   label: 'ingestion' },
  { key: 'operator',    label: 'operators' },
  { key: 'llm',         label: 'llm' },
  { key: 'scheduler',   label: 'scheduler' },
];

export const Timeline: React.FC = () => {
  const fx = useScenarioFixture();
  const [filter, setFilter] = useState<ActorKind | 'all'>('all');
  const [selected, setSelected] = useState<number | null>(null);

  const filtered = useMemo(() => {
    if (filter === 'all') return fx.timelineEvents;
    return fx.timelineEvents.filter((e) => e.actor.kind === filter);
  }, [fx.timelineEvents, filter]);

  const sel = selected !== null ? filtered[selected] ?? null : null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Timeline · all activity"
        headline="Every action, every actor, one chronological stream."
        briefing="Filter by actor kind to focus. Click any row to open its evidence bundle — provenance, lineage, and the operator's notes."
        status={`${fx.timelineEvents.length} events`}
        testId="timeline-header"
      />

      <div
        data-testid="timeline-facet-bar"
        role="tablist"
        aria-label="Filter timeline by actor kind"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span
          style={{
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          actor ·
        </span>
        {ACTOR_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`timeline-facet-${f.key}`}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            style={{
              background: filter === f.key ? 'var(--sig-info)' : 'var(--surface-2)',
              color: filter === f.key ? 'var(--surface-0)' : 'var(--content-md)',
              border: '1px solid var(--stroke-2)',
              borderRadius: 'var(--radius-1)',
              padding: '4px 10px',
              fontFamily: 'ui-monospace, monospace',
              fontSize: 'var(--font-caption)',
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              cursor: 'pointer',
            }}
          >
            {f.label}
          </button>
        ))}
      </div>

      <SignatureFrame tone="info" caption={`Events · ${filter}`}>
        {filtered.length === 0 ? (
          <StateTemplate
            variant="empty"
            code={`timeline-empty-${filter}`}
            icon={Activity}
            tone="dormant"
            headline="Nothing here for this filter."
            purpose="Widen the facet or switch back to 'all'."
          />
        ) : (
          <div role="list" style={{ display: 'flex', flexDirection: 'column' }}>
            {filtered.map((e, i) => (
              <ActivityRow
                key={i}
                timestamp={e.timestamp}
                actor={{ kind: e.actor.kind, name: e.actor.name }}
                verb={e.verb}
                subject={e.subject}
                outcome={e.outcome as { tone: ChipTone; label: string } | undefined}
                trailer={e.trailer}
                onOpen={() => setSelected(i)}
                testId={`timeline-row-${i}`}
              />
            ))}
          </div>
        )}
      </SignatureFrame>

      <div
        style={{
          fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
          textTransform: 'uppercase', letterSpacing: '0.08em',
          display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)',
        }}
      >
        <span>coverage · {filtered.length} of {fx.timelineEvents.length}</span>
        <Chip tone="ok" label="attested" showGlyph={false} />
        <Chip tone="info" label="fixture stream" showGlyph={false} />
      </div>

      <EvidenceDrawer
        open={sel !== null}
        onClose={() => setSelected(null)}
        title={sel ? `${sel.verb} · ${sel.subject}` : ''}
        subtitle={sel ? `${sel.timestamp} · ${sel.actor.name ?? sel.actor.kind}` : undefined}
        provenance={{ source: sel?.actor.name ?? sel?.actor.kind, transform: 'plan #47', attested: 'gov-warden' }}
        lineage={{
          self: { id: sel?.subject ?? 'unknown', label: sel?.subject ?? 'unknown', kind: sel?.actor.kind ?? 'event' },
          ancestors: [{ id: 'plan-47', label: 'plan #47', kind: 'plan' }],
          descendants: [],
        }}
        sections={sel ? [
          { heading: 'trailer', body: sel.trailer ?? 'No trailer captured.' },
          { heading: 'outcome', body: sel.outcome ? `${sel.outcome.label} (${sel.outcome.tone})` : 'No outcome.' },
        ] : []}
      />
    </div>
  );
};

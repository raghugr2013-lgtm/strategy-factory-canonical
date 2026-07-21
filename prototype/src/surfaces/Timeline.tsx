/*
 * Timeline — Bible §7.4, D2. Phase 5-wired:
 *   • Actor facet reads from + writes to `navigationStore.facets.actor`
 *     so the cascade persists into Approvals / Explorer.
 *   • Selected row is written to surface memory keyed by pathname, so
 *     returning to `/c/timeline` re-opens the same row (Rule of Predictable
 *     Return).
 *   • When a strategy id appears in the subject, a "open passport"
 *     shortcut drops a return-crumb before navigating.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
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
import { useNavigationStore, type ActorFacet } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const ACTOR_FILTERS: Array<{ key: ActorFacet; label: string }> = [
  { key: 'all',         label: 'all' },
  { key: 'master-bot',  label: 'master' },
  { key: 'worker',      label: 'workers' },
  { key: 'governance',  label: 'governance' },
  { key: 'ingestion',   label: 'ingestion' },
  { key: 'operator',    label: 'operators' },
  { key: 'llm',         label: 'llm' },
  { key: 'scheduler',   label: 'scheduler' },
];

// Best-effort extraction of a strategy id from an event subject.
const findStrategyId = (subject: string): string | null => {
  const m = subject.match(/strat-\d+/);
  return m ? m[0] : null;
};

export const Timeline: React.FC = () => {
  const fx = useScenarioFixture();
  const nav = useNavigate();
  const loc = useLocation();

  const facet = useNavigationStore((s) => s.facets.actor);
  const setFacet = useNavigationStore((s) => s.setFacet);
  const saveSurface = useNavigationStore((s) => s.saveSurface);
  const readSurface = useNavigationStore((s) => s.readSurface);
  const setCrumb = useNavigationStore((s) => s.setCrumb);
  const selectStrategy = useWorkspaceStore((s) => s.selectStrategy);

  const [selected, setSelected] = useState<number | null>(() => {
    const mem = readSurface<{ selected: number }>(loc.pathname);
    return mem?.selected ?? null;
  });

  useEffect(() => {
    saveSurface(loc.pathname, { selected });
  }, [selected, loc.pathname, saveSurface]);

  const filtered = useMemo(() => {
    if (facet === 'all') return fx.timelineEvents;
    return fx.timelineEvents.filter((e) => e.actor.kind === facet);
  }, [fx.timelineEvents, facet]);

  const sel = selected !== null ? filtered[selected] ?? null : null;
  const selStratId = sel ? findStrategyId(sel.subject) : null;

  const openPassport = (id: string) => {
    selectStrategy(id);
    setCrumb({ path: loc.pathname, label: 'back to timeline', origin: 'timeline' });
    nav(`/c/strategies/${id}`);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Timeline · all activity"
        headline="Every action, every actor, one chronological stream."
        briefing="Filter by actor kind to focus. Facet selections persist across surfaces — actor here, risk in Approvals, status in Explorer — so the plane you build is remembered when you return. Click any row to open its evidence bundle."
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
            aria-selected={facet === f.key}
            onClick={() => setFacet('actor', f.key)}
            style={{
              background: facet === f.key ? 'var(--sig-info)' : 'var(--surface-2)',
              color: facet === f.key ? 'var(--surface-0)' : 'var(--content-md)',
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
        <span
          data-testid="timeline-cascade-hint"
          style={{
            marginLeft: 'auto', fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          cascade · actor {facet}
        </span>
      </div>

      <SignatureFrame tone="info" caption={`Events · ${facet}`}>
        {filtered.length === 0 ? (
          <StateTemplate
            variant="empty"
            code={`timeline-empty-${facet}`}
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
                actor={{ kind: e.actor.kind as ActorKind, name: e.actor.name }}
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
          ...(selStratId ? [{
            heading: 'decision identity',
            body: `This event references strategy ${selStratId}. Opening the passport preserves your position — the timeline will restore this row on return.`,
          }] : []),
        ] : []}
        footerAction={selStratId ? {
          label: `open passport · ${selStratId}`,
          testId: 'timeline-drawer-open-passport',
          onClick: () => openPassport(selStratId!),
        } : undefined}
      />
    </div>
  );
};

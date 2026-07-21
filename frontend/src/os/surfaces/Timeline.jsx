/*
 * Timeline surface — S2. Chronological activity feed with FacetBar (actor).
 * refs DESIGN_FREEZE_v1.0.md §1.4 · D2 · Bible §7.4
 */
import React, { useEffect, useState } from 'react';
import { Bot, Landmark, Cpu, Activity, Sparkles, GitBranch, ClipboardList } from 'lucide-react';
import { FacetBar } from '../features/FacetBar';
import { TimeWindowChip } from '../features/TimeWindowChip';
import { ActivityRow } from '../primitives/ActivityRow';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchTimeline } from '../adapters/timelineAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const ACTOR_ICON = { governance: Landmark, 'master-bot': Bot, llm: Sparkles,
                     ingestion: Cpu, operator: ClipboardList, validator: Activity,
                     scheduler: GitBranch };

const ACTOR_OPTIONS = [
  { key: 'all', label: 'All' },
  { key: 'governance', label: 'Governance' },
  { key: 'master-bot', label: 'Master Bot' },
  { key: 'llm', label: 'LLM' },
  { key: 'ingestion', label: 'Ingestion' },
  { key: 'operator', label: 'Operator' },
  { key: 'validator', label: 'Validator' },
  { key: 'scheduler', label: 'Scheduler' },
];

export const Timeline = () => {
  const actorFacet = useNavigationStore((s) => s.facets.actor);
  const timeWindow = useWorkspaceStore((s) => s.timeWindow);
  const [events, setEvents] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let live = true;
    setEvents(null);
    fetchTimeline({ actor: actorFacet, window: timeWindow })
      .then((e) => { if (live) setEvents(e); })
      .catch(() => { if (live) setEvents([]); });
    return () => { live = false; };
  }, [actorFacet, timeWindow]);

  const totalCount = events?.length ?? 0;

  return (
    <section data-testid="timeline"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div>
        <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                       letterSpacing: '0.1em', textTransform: 'uppercase',
                       marginBottom: 'var(--space-2)' }}>
          Timeline
        </div>
        <h1 data-testid="timeline-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
          Every action, every actor, one chronological stream.
        </h1>
        <p data-testid="timeline-briefing"
           style={{ margin: 0, maxWidth: 720, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          Filter by actor kind to focus. Facet selections persist across surfaces — actor here, risk in
          Approvals, status in Strategies — so the plane you build is remembered when you return.
          Click any row to open its evidence bundle.
        </p>
      </div>

      <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}>
        <FacetBar axis="actor" options={ACTOR_OPTIONS} testIdPrefix="timeline-facet" />
        <TimeWindowChip testId="timeline-time-window" />
        <span data-testid="timeline-cascade-hint"
              style={{ marginLeft: 'auto', fontSize: 'var(--font-caption)',
                       color: 'var(--content-lo)', textTransform: 'uppercase',
                       letterSpacing: '0.08em' }}>
          cascade · actor {actorFacet}
        </span>
      </div>

      {events === null ? (
        <div style={{ padding: 'var(--space-4)', color: 'var(--content-lo)' }}>Loading timeline…</div>
      ) : totalCount === 0 ? (
        <StateTemplate variant="empty" code="timeline-empty" icon={Activity} tone="dormant"
                       headline="No events for this facet in this window."
                       purpose="Widen the time window or clear the actor filter." />
      ) : (
        <div data-testid="timeline-list"
             role="list"
             style={{ background: 'var(--surface-1)', border: '1px solid var(--stroke-1)',
                      borderRadius: 'var(--radius-3)', overflow: 'hidden' }}>
          {events.map((e) => (
            <ActivityRow key={e.id}
                         timestamp={e.timestamp}
                         actor={{ kind: e.actorKind, name: e.actorName, icon: ACTOR_ICON[e.actorKind] }}
                         verb={e.verb}
                         subject={e.subject}
                         outcome={e.outcome}
                         trailer={e.trailer}
                         onOpen={() => setSelected(e)}
                         testId={`timeline-row-${e.id}`} />
          ))}
        </div>
      )}

      <EvidenceDrawer open={Boolean(selected)}
                      onClose={() => setSelected(null)}
                      title={selected ? `${selected.verb} · ${selected.subject}` : ''}
                      subtitle={selected ? `${selected.timestamp}Z · ${selected.actorName}` : ''}
                      provenance={selected?.provenance ?? {}}
                      lineage={selected?.lineage ?? { self: { id: selected?.id ?? '—', label: selected?.subject ?? '—', kind: 'event' } }}
                      sections={selected ? [
                        { heading: 'Trailer', body: selected.trailer || '—' },
                        { heading: 'Outcome', body: `${selected.outcome.label} (${selected.outcome.tone})` },
                        { heading: 'Decision identity', body: 'Opening the passport preserves your position — the timeline will restore this row on return.' },
                      ] : []} />
    </section>
  );
};

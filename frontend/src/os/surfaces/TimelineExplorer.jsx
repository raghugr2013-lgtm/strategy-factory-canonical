/*
 * TimelineExplorer — Phase E: prototype-polished chronological activity feed.
 *
 * Merges the visual language of prototype/src/surfaces/Timeline.tsx with the
 * production wiring of the sibling Timeline.jsx surface:
 *
 *   • Visual language (prototype):
 *     - SurfaceHeader anatomy (eyebrow · headline · briefing · mono trailer)
 *     - SignatureFrame around the event list (info tone, caption per facet)
 *     - Row memory keyed by pathname → Rule of Predictable Return
 *     - EvidenceDrawer footer action: "open passport · strat-XXX" when the
 *       subject references a strategy id
 *     - Return-crumb stamped ("back to timeline") before navigation
 *     - Decision Identity: selectStrategy() so the same passport row is
 *       highlighted in Explorer + Timeline + Approvals
 *
 *   • Production wiring (kept from Timeline.jsx):
 *     - Real API via fetchTimeline() with transparent fixture fallback
 *     - FacetBar (shared axis: actor) — cascades to Approvals + Strategies
 *     - TimeWindowChip (production-only time-window plane)
 *     - StreamPostmark + useStream (live poll @ 15s)
 *     - StateTemplate empty-state
 *
 * Coexistence contract:
 *   /c/timeline            → legacy Timeline surface (unchanged)
 *   /c/timeline/explorer   → this new surface
 * The existing surface is untouched. Rollback = revert this commit.
 */
import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Bot, Landmark, Cpu, Activity, Sparkles, GitBranch, ClipboardList,
} from 'lucide-react';
import { SurfaceHeader } from '../primitives/SurfaceHeader';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { Chip } from '../primitives/Chip';
import { ActivityRow } from '../primitives/ActivityRow';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';
import { StateTemplate } from '../primitives/StateTemplate';
import { FacetBar } from '../features/FacetBar';
import { TimeWindowChip } from '../features/TimeWindowChip';
import { StreamPostmark } from '../features/StreamPostmark';
import { useStream } from '../features/useStream';
import { fetchTimeline } from '../adapters/timelineAdapter';
import { useNavigationStore } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

const ACTOR_ICON = {
  governance: Landmark, 'master-bot': Bot, llm: Sparkles,
  ingestion: Cpu, operator: ClipboardList, validator: Activity,
  scheduler: GitBranch,
};

const ACTOR_OPTIONS = [
  { key: 'all',        label: 'All' },
  { key: 'governance', label: 'Governance' },
  { key: 'master-bot', label: 'Master Bot' },
  { key: 'llm',        label: 'LLM' },
  { key: 'ingestion',  label: 'Ingestion' },
  { key: 'operator',   label: 'Operator' },
  { key: 'validator',  label: 'Validator' },
  { key: 'scheduler',  label: 'Scheduler' },
];

// Best-effort extraction of a strategy id from an event subject.
// Matches strings like "strat-014" or "strat-014-schema-v3".
const findStrategyId = (subject) => {
  if (typeof subject !== 'string') return null;
  const m = subject.match(/strat-\d+/);
  return m ? m[0] : null;
};

export const TimelineExplorer = () => {
  const nav = useNavigate();
  const loc = useLocation();

  const actorFacet     = useNavigationStore((s) => s.facets.actor);
  const saveSurface    = useNavigationStore((s) => s.saveSurface);
  const readSurface    = useNavigationStore((s) => s.readSurface);
  const setCrumb       = useNavigationStore((s) => s.setCrumb);
  const timeWindow     = useWorkspaceStore((s) => s.timeWindow);
  const selectStrategy = useWorkspaceStore((s) => s.selectStrategy);

  const [events, setEvents] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  // Restore last-selected row from surface memory (Predictable Return).
  useEffect(() => {
    const mem = readSurface(loc.pathname);
    if (mem?.selectedId) setSelectedId(mem.selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loc.pathname]);

  // Persist row selection into surface memory.
  useEffect(() => {
    saveSurface(loc.pathname, { selectedId });
  }, [selectedId, loc.pathname, saveSurface]);

  const refetch = useCallback(() => {
    fetchTimeline({ actor: actorFacet, window: timeWindow })
      .then((e) => setEvents(e))
      .catch(() => setEvents([]));
  }, [actorFacet, timeWindow]);

  useEffect(() => {
    let live = true;
    setEvents(null);
    fetchTimeline({ actor: actorFacet, window: timeWindow })
      .then((e) => { if (live) setEvents(e); })
      .catch(() => { if (live) setEvents([]); });
    return () => { live = false; };
  }, [actorFacet, timeWindow]);

  const streamStatus = useStream('timeline-explorer', {
    intervalMs: 15_000,
    onTick: (payload) => { if (payload.mode !== 'initial') refetch(); },
  });

  const totalCount = events?.length ?? 0;
  const isLoading = events === null;
  const isEmpty = Array.isArray(events) && events.length === 0;

  const selected = useMemo(
    () => (events && selectedId ? events.find((e) => e.id === selectedId) ?? null : null),
    [events, selectedId],
  );
  const selectedStratId = selected ? findStrategyId(selected.subject) : null;

  const openPassport = (id) => {
    selectStrategy(id);
    setCrumb({
      path: loc.pathname,
      label: 'back to timeline',
      origin: 'timeline-explorer',
      originId: id,
    });
    nav(`/c/strategies/${encodeURIComponent(id)}`);
  };

  const trailer =
    isLoading ? 'loading…' : `${totalCount} event${totalCount === 1 ? '' : 's'}`;

  return (
    <section
      data-testid="timeline-explorer"
      style={{
        padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
        display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
      }}
    >
      <SurfaceHeader
        eyebrow="Timeline Explorer · all activity"
        headline="Every action, every actor, one chronological stream."
        briefing="Filter by actor kind to focus. Facet selections persist across surfaces — actor here, risk in Approvals, status in Explorer — so the plane you build is remembered when you return. Click any row to open its evidence bundle; strategy references reveal an open-passport shortcut."
        status={trailer}
        testId="timeline-explorer-header"
      />

      <div
        data-testid="timeline-explorer-controls"
        style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center', flexWrap: 'wrap' }}
      >
        <FacetBar axis="actor" options={ACTOR_OPTIONS} testIdPrefix="timeline-explorer-facet" />
        <TimeWindowChip testId="timeline-explorer-time-window" />
        <StreamPostmark status={streamStatus} testId="timeline-explorer-stream-postmark" />
        <span
          data-testid="timeline-explorer-cascade-hint"
          style={{
            marginLeft: 'auto', fontSize: 'var(--font-caption)',
            color: 'var(--content-lo)', textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          cascade · actor {actorFacet}
        </span>
      </div>

      <SignatureFrame tone="info" caption={`Events · ${actorFacet}`} testId="timeline-explorer-frame">
        {isLoading ? (
          <div style={{ padding: 'var(--space-4)', color: 'var(--content-lo)' }}>
            Loading timeline…
          </div>
        ) : isEmpty ? (
          <StateTemplate
            variant="empty"
            code={`timeline-explorer-empty-${actorFacet}`}
            icon={Activity}
            tone="dormant"
            headline={
              actorFacet === 'all'
                ? 'No events in this window.'
                : `No ${actorFacet} events in this window.`
            }
            purpose="Widen the time window or clear the actor filter."
          />
        ) : (
          <div
            data-testid="timeline-explorer-list"
            role="list"
            style={{ display: 'flex', flexDirection: 'column' }}
          >
            {events.map((e) => (
              <ActivityRow
                key={e.id}
                timestamp={e.timestamp}
                actor={{ kind: e.actorKind, name: e.actorName, icon: ACTOR_ICON[e.actorKind] }}
                verb={e.verb}
                subject={e.subject}
                outcome={e.outcome}
                trailer={e.trailer}
                onOpen={() => setSelectedId(e.id)}
                testId={`timeline-explorer-row-${e.id}`}
              />
            ))}
          </div>
        )}
      </SignatureFrame>

      <div
        data-testid="timeline-explorer-coverage"
        style={{
          fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
          textTransform: 'uppercase', letterSpacing: '0.08em',
          display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center',
        }}
      >
        <span>coverage · {totalCount} event{totalCount === 1 ? '' : 's'}</span>
        <Chip tone="ok"   label="attested"   showGlyph={false} />
        <Chip tone="info" label="live stream" showGlyph={false} />
      </div>

      <EvidenceDrawer
        open={Boolean(selected)}
        onClose={() => setSelectedId(null)}
        title={selected ? `${selected.verb} · ${selected.subject}` : ''}
        subtitle={selected ? `${selected.timestamp}Z · ${selected.actorName ?? selected.actorKind}` : ''}
        provenance={selected?.provenance ?? {}}
        lineage={
          selected?.lineage ?? {
            self: {
              id: selected?.id ?? '—',
              label: selected?.subject ?? '—',
              kind: 'event',
            },
          }
        }
        sections={
          selected
            ? [
                { heading: 'Trailer', body: selected.trailer || '—' },
                {
                  heading: 'Outcome',
                  body: selected.outcome
                    ? `${selected.outcome.label} (${selected.outcome.tone})`
                    : '—',
                },
                ...(selectedStratId
                  ? [{
                      heading: 'Decision identity',
                      body: `This event references strategy ${selectedStratId}. Opening the passport preserves your position — the timeline will restore this row on return.`,
                    }]
                  : []),
              ]
            : []
        }
        footerAction={
          selectedStratId
            ? {
                label: `open passport · ${selectedStratId}`,
                testId: 'timeline-explorer-drawer-open-passport',
                onClick: () => openPassport(selectedStratId),
              }
            : undefined
        }
      />
    </section>
  );
};

export default TimelineExplorer;

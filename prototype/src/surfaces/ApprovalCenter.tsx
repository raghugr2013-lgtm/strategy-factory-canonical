/*
 * ApprovalCenter — Bible §7.5, D3.
 * Every human gate lives here. Cards are risk-sorted by default; aged
 * approvals (>60m) are elevated. Clicking Approve/Defer/Block optimistically
 * removes the card (fixture-only; no backend call).
 */
import { useMemo, useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { useScenarioFixture, type ApprovalFixture } from '../gallery/scenarioFixtures';

type ResolvedMap = Record<string, 'approved' | 'deferred' | 'blocked'>;

const sortByPriority = (a: ApprovalFixture, b: ApprovalFixture) => {
  const risk = (r: string) => (r === 'high' ? 2 : r === 'moderate' ? 1 : 0);
  const rd = risk(b.risk) - risk(a.risk);
  if (rd !== 0) return rd;
  return b.ageMinutes - a.ageMinutes;
};

export const ApprovalCenter: React.FC = () => {
  const fx = useScenarioFixture();
  const [resolved, setResolved] = useState<ResolvedMap>({});

  const sorted = useMemo(
    () => fx.approvals.filter((a) => !resolved[a.id]).sort(sortByPriority),
    [fx.approvals, resolved],
  );

  const resolvedList = fx.approvals.filter((a) => resolved[a.id]);

  const decide = (id: string, verdict: 'approved' | 'deferred' | 'blocked') =>
    setResolved((r) => ({ ...r, [id]: verdict }));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Approval Center · human gates"
        headline={
          sorted.length === 0
            ? 'You are all caught up.'
            : `${sorted.length} approvals need a human decision.`
        }
        briefing={
          sorted.length === 0
            ? 'The Factory is running autonomously. New approvals will appear here in real time.'
            : 'Sorted by risk, then by age. Every card carries its receipts. Nothing is decided without provenance.'
        }
        status={sorted.length ? `${sorted.filter((a) => a.risk === 'high').length}h · ${sorted.filter((a) => a.risk === 'moderate').length}m · ${sorted.filter((a) => a.risk === 'low').length}l` : 'clear'}
        testId="approvals-header"
      />

      {sorted.length === 0 ? (
        <StateTemplate
          variant="empty"
          code="approvals-empty"
          icon={CheckCircle2}
          tone="ok"
          headline="Nothing needs your attention."
          purpose="The Master Bot has cleared the queue."
          advancedFootnote="master-bot@v55 · queue depth 0"
        />
      ) : (
        <div
          data-testid="approvals-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
            gap: 'var(--space-4)',
          }}
        >
          {sorted.map((a) => (
            <ApprovalCard
              key={a.id}
              testId={`approval-${a.id}`}
              title={a.title}
              origin={a.origin}
              risk={a.risk}
              summary={a.summary}
              provenance={a.provenance}
              decisionIdentity={a.decisionIdentity}
              ageMinutes={a.ageMinutes}
              onApprove={() => decide(a.id, 'approved')}
              onDefer={() => decide(a.id, 'deferred')}
              onBlock={() => decide(a.id, 'blocked')}
            />
          ))}
        </div>
      )}

      {resolvedList.length > 0 && (
        <section
          data-testid="approvals-resolved-strip"
          style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
        >
          <div
            style={{
              fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
              textTransform: 'uppercase', letterSpacing: '0.08em',
            }}
          >
            resolved · this session
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {resolvedList.map((a) => {
              const verdict = resolved[a.id];
              const tone = verdict === 'approved' ? 'ok' : verdict === 'deferred' ? 'info' : 'crit';
              return (
                <Chip
                  key={a.id}
                  tone={tone}
                  label={`${verdict} · ${a.id}`}
                  showGlyph={false}
                  testId={`approvals-resolved-${a.id}`}
                />
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
};

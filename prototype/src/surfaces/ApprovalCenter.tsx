/*
 * ApprovalCenter — Bible §7.5, D3. Phase 5-wired:
 *   • Reads/writes the shared risk facet from `navigationStore.facets.risk`
 *     so switching risk here also narrows Strategy Explorer's status
 *     projection (facet cascade).
 *   • Resolved-map lives in surface memory keyed by pathname, so the
 *     resolved chips are still visible on return (Predictable Return).
 *   • Opening a strategy-scoped approval sets Decision Identity +
 *     drops a return-crumb before navigating to the passport.
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { ApprovalCard } from '../primitives/ApprovalCard';
import { Chip } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { useScenarioFixture, type ApprovalFixture } from '../gallery/scenarioFixtures';
import { useNavigationStore, type RiskFacet } from '../workspace-state/navigationStore';
import { useWorkspaceStore } from '../workspace-state/store';

type ResolvedMap = Record<string, 'approved' | 'deferred' | 'blocked'>;

const RISK_FILTERS: Array<{ key: RiskFacet; label: string }> = [
  { key: 'all',      label: 'all' },
  { key: 'high',     label: 'high' },
  { key: 'moderate', label: 'moderate' },
  { key: 'low',      label: 'low' },
];

const sortByPriority = (a: ApprovalFixture, b: ApprovalFixture) => {
  const risk = (r: string) => (r === 'high' ? 2 : r === 'moderate' ? 1 : 0);
  const rd = risk(b.risk) - risk(a.risk);
  if (rd !== 0) return rd;
  return b.ageMinutes - a.ageMinutes;
};

const findStrategyId = (a: ApprovalFixture): string | null => {
  const hay = `${a.title} ${a.summary} ${a.decisionIdentity ?? ''}`;
  const m = hay.match(/strat-\d+/);
  return m ? m[0] : null;
};

export const ApprovalCenter: React.FC = () => {
  const fx = useScenarioFixture();
  const nav = useNavigate();
  const loc = useLocation();

  const riskFacet = useNavigationStore((s) => s.facets.risk);
  const setFacet  = useNavigationStore((s) => s.setFacet);
  const saveSurface = useNavigationStore((s) => s.saveSurface);
  const readSurface = useNavigationStore((s) => s.readSurface);
  const setCrumb    = useNavigationStore((s) => s.setCrumb);
  const selectStrategy = useWorkspaceStore((s) => s.selectStrategy);

  const [resolved, setResolved] = useState<ResolvedMap>(() => {
    const mem = readSurface<{ resolved: ResolvedMap }>(loc.pathname);
    return mem?.resolved ?? {};
  });

  useEffect(() => {
    saveSurface(loc.pathname, { resolved });
  }, [resolved, loc.pathname, saveSurface]);

  const filteredAll = useMemo(() => {
    if (riskFacet === 'all') return fx.approvals;
    return fx.approvals.filter((a) => a.risk === riskFacet);
  }, [fx.approvals, riskFacet]);

  const sorted = useMemo(
    () => filteredAll.filter((a) => !resolved[a.id]).sort(sortByPriority),
    [filteredAll, resolved],
  );

  const resolvedList = fx.approvals.filter((a) => resolved[a.id]);

  const decide = (id: string, verdict: 'approved' | 'deferred' | 'blocked') =>
    setResolved((r) => ({ ...r, [id]: verdict }));

  const openPassport = (a: ApprovalFixture) => {
    const id = findStrategyId(a);
    if (!id) return;
    selectStrategy(id);
    setCrumb({
      path: loc.pathname,
      label: 'back to approvals',
      origin: 'approvals',
      originId: a.id,
    });
    nav(`/c/strategies/${id}`);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />
      <SurfaceHeader
        eyebrow="Approval Center · human gates"
        headline={
          sorted.length === 0
            ? riskFacet === 'all'
              ? 'You are all caught up.'
              : `No ${riskFacet}-risk approvals waiting.`
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

      <div
        data-testid="approvals-facet-bar"
        role="tablist"
        aria-label="Filter approvals by risk"
        style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', alignItems: 'center' }}
      >
        <span
          style={{
            fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          risk ·
        </span>
        {RISK_FILTERS.map((f) => (
          <button
            key={f.key}
            data-testid={`approvals-facet-${f.key}`}
            role="tab"
            aria-selected={riskFacet === f.key}
            onClick={() => setFacet('risk', f.key)}
            style={{
              background: riskFacet === f.key ? 'var(--sig-info)' : 'var(--surface-2)',
              color: riskFacet === f.key ? 'var(--surface-0)' : 'var(--content-md)',
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
          data-testid="approvals-cascade-hint"
          style={{
            marginLeft: 'auto', fontSize: 'var(--font-caption)', color: 'var(--content-lo)',
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          cascade · risk {riskFacet}
        </span>
      </div>

      {sorted.length === 0 ? (
        <StateTemplate
          variant="empty"
          code={`approvals-empty-${riskFacet}`}
          icon={CheckCircle2}
          tone="ok"
          headline={
            riskFacet === 'all'
              ? 'Nothing needs your attention.'
              : `No ${riskFacet}-risk approvals in this scenario.`
          }
          purpose={
            riskFacet === 'all'
              ? 'The Master Bot has cleared the queue.'
              : `Widen the risk facet to see other decisions.`
          }
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
          {sorted.map((a) => {
            const stratId = findStrategyId(a);
            return (
              <div key={a.id} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <ApprovalCard
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
                {stratId && (
                  <button
                    data-testid={`approval-${a.id}-open-passport`}
                    onClick={() => openPassport(a)}
                    style={{
                      alignSelf: 'flex-end',
                      background: 'transparent',
                      color: 'var(--content-md)',
                      border: '1px solid var(--stroke-2)',
                      borderRadius: 'var(--radius-1)',
                      padding: '3px 8px',
                      fontFamily: 'ui-monospace, monospace',
                      fontSize: 'var(--font-caption)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      cursor: 'pointer',
                    }}
                  >
                    open passport · {stratId} →
                  </button>
                )}
              </div>
            );
          })}
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

/*
 * CuratedLibraryDashboard — FE-B Slice 6 · surfaces the HKB Curated Strategy Library.
 * refs docs/HKB_MIGRATION_REPORT.md § 4.3 · Backend Feature Freeze v1.1.0-stage4.
 *
 * Read-only. Consumes existing endpoints:
 *   • GET /api/knowledge/health
 *   • GET /api/knowledge/statistics
 *   • GET /api/knowledge/champions
 *
 * Data source: `strategy_knowledge_base.strategy_kb_view` +
 * `strategy_knowledge_base.strategy_kb_champions`, populated by
 * `hkb/scripts/build_kb_views.py` from the migrated HKB corpus.
 */
import React, { useMemo } from 'react';
import { Sparkles, Trophy, Filter, Layers } from 'lucide-react';
import { MetricBlock } from '../../primitives/MetricBlock';
import { Chip } from '../../primitives/Chip';
import { StateTemplate } from '../../primitives/StateTemplate';
import { SignalStateBadge, FreezeCaption } from '../engineering/LivenessBadge';
import { useKBHealth, useKBStatistics, useKBChampions } from '../../adapters/curatedLibraryAdapter';
import {
  SummaryPanel, SectionHeader, sectionPanel, eyebrowLabel, cell, cellHead,
} from './factoryPrimitives';

const tierTone = (tier) => {
  const t = String(tier || '').toUpperCase();
  if (t.startsWith('A')) return 'ok';
  if (t.startsWith('B')) return 'info';
  if (t.startsWith('C')) return 'warn';
  return 'dormant';
};

const ChampionCategoryTable = ({ category, rows }) => {
  const list = rows || [];
  return (
    <div style={{ marginBottom: 'var(--space-4)' }} data-testid={`champ-cat-${category}`}>
      <SectionHeader icon={Trophy} title={category.replace(/_/g, ' ').toUpperCase()} testId={`champ-header-${category}`}
                     right={<Chip tone={list.length > 0 ? 'info' : 'dormant'} label={`${list.length}`} />} />
      <div style={sectionPanel} data-testid={`champ-panel-${category}`}>
        {list.length === 0 ? (
          <StateTemplate variant="empty" code={`champ-empty-${category}`} icon={Trophy} tone="dormant"
                         headline="No candidates in this tier yet."
                         purpose={category === 'a_elite'
                           ? "A-Elite requires composite score ≥ 0.70; the historical HKB carries no such specimens (every entry was labelled verdict=RISKY by the legacy factory). New strategies produced post-VPS-activation will populate this tier."
                           : `${category.replace(/_/g, ' ')} is currently empty in the curated library snapshot.`} />
        ) : (
          <div style={{ overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--font-body-sm)' }} data-testid={`champ-table-${category}`}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--content-lo)', textTransform: 'uppercase', fontSize: 'var(--font-caption)', letterSpacing: '0.08em' }}>
                  <th style={cellHead}>#</th>
                  <th style={cellHead}>Pair</th>
                  <th style={cellHead}>TF</th>
                  <th style={cellHead}>Composite</th>
                  <th style={cellHead}>PF</th>
                  <th style={cellHead}>DD %</th>
                  <th style={cellHead}>Trades</th>
                  <th style={cellHead}>Tier</th>
                  <th style={cellHead}>Strategy ID</th>
                </tr>
              </thead>
              <tbody>
                {list.map((r, i) => (
                  <tr key={r.strategy_id || i} data-testid={`champ-row-${category}-${i}`} style={{ borderTop: '1px solid var(--stroke-1)' }}>
                    <td style={cell}><span className="mono-num">{r.unique_rank || i + 1}</span></td>
                    <td style={cell}><span className="mono-num">{r.pair || '—'}</span></td>
                    <td style={cell}><span className="mono-num">{r.timeframe || '—'}</span></td>
                    <td style={cell}><span className="mono-num" style={{ color: 'var(--content-hi)' }}>{(r.composite_score ?? 0).toFixed(3)}</span></td>
                    <td style={cell}><span className="mono-num">{(r.profit_factor ?? 0).toFixed(2)}</span></td>
                    <td style={cell}><span className="mono-num">{(r.max_drawdown_pct ?? 0).toFixed(1)}</span></td>
                    <td style={cell}><span className="mono-num">{r.total_trades ?? 0}</span></td>
                    <td style={cell}><Chip tone={tierTone(r.tier)} label={String(r.tier || 'unknown').toUpperCase()} /></td>
                    <td style={cell}><span className="mono-num" style={{ color: 'var(--content-lo)' }}>{String(r.strategy_id || '').slice(0, 12)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export const CuratedLibraryDashboard = () => {
  const healthQ = useKBHealth();
  const statsQ  = useKBStatistics();
  const champsQ = useKBChampions();

  const health = healthQ.data;
  const stats  = statsQ.data;
  const champs = champsQ.data;

  const corpus = stats?.total_strategies ?? 0;
  const families = stats?.canonical_families ?? 0;
  const multi = stats?.multi_member_families ?? 0;
  const positive = stats?.positive_return_pf_gt_1 ?? 0;

  const CATEGORY_ORDER = ['top_by_composite', 'top_by_pair', 'top_by_timeframe', 'a_elite', 'b_candidate', 'c_experimental'];
  const categories = champs?.categories || {};
  const catNames = CATEGORY_ORDER;
  const totalChamps = catNames.reduce((n, k) => n + (categories[k]?.length || 0), 0);
  const eliteCount = (categories.a_elite || []).length;
  const bCount     = (categories.b_candidate || []).length;
  const cCount     = (categories.c_experimental || []).length;

  const pairs = Object.entries(stats?.pair_distribution || {});
  const cells = useMemo(() => ([
    { label: 'HKB corpus',        tone: corpus > 0 ? 'info' : 'dormant', value: `${corpus}`,   sub: 'strategy_kb_view',            testId: 'cur-cell-corpus' },
    { label: 'Canonical families',tone: families > 0 ? 'info' : 'dormant', value: `${families}`, sub: 'unique structural fingerprints', testId: 'cur-cell-families' },
    { label: 'Multi-member',      tone: multi > 0 ? 'info' : 'dormant', value: `${multi}`,      sub: 'families with 2+ variants',   testId: 'cur-cell-multi' },
    { label: 'PF > 1 winners',    tone: positive > 0 ? 'ok' : 'dormant', value: `${positive}`, sub: 'positive-return specimens',   testId: 'cur-cell-positive' },
    { label: 'A · Elite',         tone: eliteCount > 0 ? 'ok' : 'dormant', value: `${eliteCount}`, sub: 'composite ≥ 0.70',           testId: 'cur-cell-a' },
    { label: 'B · Candidate',     tone: bCount > 0 ? 'info' : 'dormant', value: `${bCount}`,   sub: 'composite ≥ 0.50',           testId: 'cur-cell-b' },
    { label: 'C · Experimental',  tone: cCount > 0 ? 'warn' : 'dormant', value: `${cCount}`,   sub: 'composite ≥ 0.30',           testId: 'cur-cell-c' },
    { label: 'Champion rows',     tone: totalChamps > 0 ? 'info' : 'dormant', value: `${totalChamps}`, sub: `${catNames.length} categories`, testId: 'cur-cell-champs' },
  ]), [corpus, families, multi, positive, eliteCount, bCount, cCount, totalChamps, catNames.length]);

  const signalState = health ? (String(health.status).toLowerCase() === 'ok' ? 'live' : 'partial') : 'error';

  return (
    <section data-testid="curated-library-dashboard" style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1400 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
        <span style={eyebrowLabel}>Factory</span>
        <span style={{ color: 'var(--content-lo)' }}>/</span>
        <span style={{ ...eyebrowLabel, color: 'var(--content-hi)' }}>Curated Library</span>
        <SignalStateBadge state={signalState} reason={health ? `HKB status=${health.status} · corpus=${health.corpus_size}` : 'unreachable'} testId="cur-header-signal" />
        <span style={{ marginLeft: 'auto' }}><FreezeCaption /></span>
      </div>

      <h1 data-testid="cur-headline" style={{ margin: 0, marginBottom: 'var(--space-2)', fontSize: 'var(--font-h2)', fontWeight: 400, letterSpacing: '-0.01em', color: 'var(--content-hi)' }}>
        Curated Strategy Library · {corpus} in HKB · {bCount + cCount + eliteCount} curated candidates
      </h1>
      <p data-testid="cur-briefing" style={{ margin: 0, marginBottom: 'var(--space-6)', maxWidth: 900, fontSize: 'var(--font-body-md)', lineHeight: 1.6, color: 'var(--content-md)' }}>
        Institutional research inherited from the 1-vCPU pod, curated to the highest-quality
        unique candidates. Every row carries <span className="mono-num">__legacy=true</span> so
        legacy imports remain distinguishable from research produced after VPS Phase-1 activation.
      </p>

      <SummaryPanel testId="curated-summary-panel" signalState={signalState}
                    signalReason={health ? `corpus=${corpus} · families=${families}` : 'endpoint unreachable'}
                    cells={cells} />

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 'var(--space-4)', marginBottom: 'var(--space-6)' }}
           data-testid="cur-metric-row">
        <MetricBlock variant="B" eyebrow="HKB SIZE" value={corpus}
                     deltaLabel="LEGACY" deltaTone="info"
                     state={statsQ.isLoading ? 'loading' : 'happy'} testId="metric-cur-corpus" />
        <MetricBlock variant="A" eyebrow="FAMILIES" value={families}
                     deltaLabel={`${multi} MULTI`} deltaTone="info"
                     state={statsQ.isLoading ? 'loading' : 'happy'} testId="metric-cur-families" />
        <MetricBlock variant="A" eyebrow="PF > 1" value={positive}
                     deltaLabel={corpus > 0 ? `${Math.round(positive*100/corpus)}%` : '—'} deltaTone="info"
                     state={statsQ.isLoading ? 'loading' : 'happy'} testId="metric-cur-positive" />
        <MetricBlock variant="A" eyebrow="CANDIDATES" value={bCount + cCount + eliteCount}
                     deltaLabel={eliteCount > 0 ? `${eliteCount} ELITE` : 'NO ELITE'} deltaTone={eliteCount > 0 ? 'ok' : 'dormant'}
                     state={champsQ.isLoading ? 'loading' : 'happy'} testId="metric-cur-candidates" />
      </div>

      {/* Pair distribution row */}
      {pairs.length > 0 && (
        <>
          <SectionHeader icon={Filter} title="Pair Distribution" testId="cur-pairs-header" />
          <div style={sectionPanel} data-testid="cur-pairs-panel">
            <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
              {pairs.map(([pair, n]) => (
                <div key={pair} data-testid={`cur-pair-${pair}`} style={{
                  display: 'flex', alignItems: 'center', gap: 'var(--space-2)',
                  padding: 'var(--space-2) var(--space-3)',
                  background: 'var(--surface-1)', border: '1px solid var(--stroke-1)', borderRadius: 'var(--radius-2)',
                }}>
                  <span className="mono-num" style={{ color: 'var(--content-hi)' }}>{pair}</span>
                  <Chip tone="info" label={`${n}`} />
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* Champions section */}
      <div style={{ marginTop: 'var(--space-6)' }}>
        <SectionHeader icon={Trophy} title="Champions" testId="cur-champs-header"
                       right={<Chip tone="info" label={`${totalChamps} rows`} testId="cur-champs-total" />} />
        {champsQ.isLoading ? (
          <StateTemplate variant="loading" code="cur-champs-loading" icon={Trophy} tone="info"
                         headline="Loading champions…" purpose="/api/knowledge/champions" />
        ) : catNames.length === 0 ? (
          <StateTemplate variant="empty" code="cur-champs-empty" icon={Trophy} tone="dormant"
                         headline="No curated candidates yet."
                         purpose="The HKB has been imported but the post-import pipeline has not yet produced a Curated Strategy Library." />
        ) : (
          <div>
            {catNames.map((cat) => (
              <ChampionCategoryTable key={cat} category={cat} rows={categories[cat] || []} />
            ))}
          </div>
        )}
      </div>

      <div style={{ marginTop: 'var(--space-6)', fontSize: 'var(--font-caption)', color: 'var(--content-lo)', letterSpacing: '0.06em' }}>
        <span data-testid="cur-refresh-hint">Auto-refresh: 30s · Sources: <span className="mono-num">/api/knowledge/{'{health,statistics,champions}'}</span></span>
      </div>
    </section>
  );
};

export default CuratedLibraryDashboard;

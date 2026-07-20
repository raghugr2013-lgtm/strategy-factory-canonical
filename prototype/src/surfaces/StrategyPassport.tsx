/*
 * StrategyPassport — E1 §4, D1 §11.
 * Detailed view for one strategy. Anatomy:
 *   Header · Passport hero (name + status + version) ·
 *   MetricBlocks (sharpe, drawdown, hit, agreement) ·
 *   ProvenanceTriple · LineageBar · sparkline chart ·
 *   narrative (research/governance body) · action strip (fixture only).
 */
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Sparkles } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { SignatureFrame } from '../primitives/SignatureFrame';
import { MetricBlock } from '../primitives/MetricBlock';
import { ProvenanceTriple } from '../primitives/ProvenanceTriple';
import { LineageBar } from '../primitives/LineageBar';
import { ChartTile } from '../primitives/ChartTile';
import { Chip, type ChipTone } from '../primitives/Chip';
import { StateTemplate } from '../primitives/StateTemplate';
import { EvidenceDrawer } from '../primitives/EvidenceDrawer';
import { useScenarioFixture, type StrategyPassport as PassportShape } from '../gallery/scenarioFixtures';

const statusTone: Record<PassportShape['status'], ChipTone> = {
  live: 'ok', paper: 'info', paused: 'warn', reviewing: 'advisory',
};

const heroSpark = (sharpe: number) =>
  Array.from({ length: 16 }).map((_, i) =>
    100 + i * (sharpe * 3) + Math.sin(i * 0.7) * 4,
  );

export const StrategyPassport: React.FC = () => {
  const { id } = useParams();
  const fx = useScenarioFixture();
  const nav = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  const p = id ? fx.passportById[id] : undefined;

  if (!p) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <StateTemplate
          variant="empty"
          code="passport-not-found"
          icon={Sparkles}
          tone="dormant"
          headline="This strategy passport is unavailable in the current scenario."
          purpose="Return to the Explorer to browse strategies for this scenario."
          primaryAction={{ label: 'open Strategy Explorer', onClick: () => nav('/c/strategies') }}
          advancedFootnote={`requested id · ${id}`}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <ScenarioBanner />

      <button
        data-testid="passport-back"
        onClick={() => nav('/c/strategies')}
        style={{
          alignSelf: 'flex-start',
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: 'transparent', border: '1px solid var(--stroke-2)',
          color: 'var(--content-md)', fontFamily: 'inherit',
          borderRadius: 'var(--radius-1)',
          padding: '4px 10px', fontSize: 'var(--font-caption)',
          textTransform: 'uppercase', letterSpacing: '0.06em',
          cursor: 'pointer',
        }}
      >
        <ArrowLeft size={12} /> back to explorer
      </button>

      <SurfaceHeader
        eyebrow={`Strategy passport · ${p.owner}`}
        headline={p.headline}
        status={`${p.name} · ${p.version}`}
        testId="passport-header"
      />

      <SignatureFrame tone={p.status === 'live' ? 'gold' : 'info'} caption={`${p.name}`}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-3)', alignItems: 'center' }}>
          <Chip tone={statusTone[p.status]} label={p.status} />
          <Chip tone="info" label={p.version} showGlyph={false} />
          <Chip tone="info" label={p.owner} showGlyph={false} />
          {p.status === 'reviewing' && <Chip tone="advisory" label="governance hold" />}
        </div>
      </SignatureFrame>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 'var(--space-4)',
        }}
      >
        <MetricBlock variant="C" eyebrow="sharpe"           value={p.sharpe.toFixed(2)} deltaLabel="30d window" deltaTone="ok"  footnote="rolling window · attested"     testId={`passport-metric-sharpe`} />
        <MetricBlock variant="A" eyebrow="drawdown"          value={`${p.drawdownPct.toFixed(1)}%`} deltaLabel="under target 10%" deltaTone="ok"  footnote="max in window"       testId={`passport-metric-drawdown`} />
        <MetricBlock variant="A" eyebrow="hit rate"          value={`${p.hitPct}%`}       deltaLabel="stable"             deltaTone="info" footnote="wins / trades"                    testId={`passport-metric-hit`} />
        <MetricBlock variant="B" eyebrow="shadow agreement"  value={`${p.agreementPct}%`} deltaLabel="+2pp vs prior"      deltaTone="ok"  footnote="book v3 vs live"                  testId={`passport-metric-agreement`} />
      </div>

      <SignatureFrame tone="info" caption="Provenance & lineage">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          <ProvenanceTriple {...p.provenance} />
          <LineageBar
            self={{ id: p.id, label: p.id, kind: 'strategy' }}
            ancestors={p.lineageAncestors}
            descendants={p.lineageDescendants}
            onOpen={() => setDrawerOpen(true)}
          />
          <button
            data-testid="passport-open-evidence"
            onClick={() => setDrawerOpen(true)}
            style={{
              alignSelf: 'flex-start',
              background: 'var(--sig-info)',
              color: 'var(--surface-0)',
              border: 'none',
              borderRadius: 'var(--radius-1)',
              padding: '8px 14px',
              fontFamily: 'inherit',
              fontSize: 'var(--font-body-sm)',
              cursor: 'pointer',
            }}
          >
            open evidence drawer →
          </button>
        </div>
      </SignatureFrame>

      <ChartTile
        caption={`${p.name} · trailing performance`}
        points={heroSpark(p.sharpe)}
        tone={p.status === 'live' ? 'ok' : p.status === 'reviewing' ? 'advisory' : 'info'}
        timeWindow="last 30 sessions"
        testId="passport-chart"
      />

      <SignatureFrame tone={p.status === 'reviewing' ? 'advisory' : 'info'} caption="Narrative">
        <p style={{ margin: 0, fontSize: 'var(--font-body-sm)', color: 'var(--content-md)', lineHeight: 1.6 }}>
          {p.narrative}
        </p>
      </SignatureFrame>

      <EvidenceDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={`${p.name} · evidence`}
        subtitle={`${p.id} · ${p.version}`}
        provenance={p.provenance}
        lineage={{
          self: { id: p.id, label: p.id, kind: 'strategy' },
          ancestors: p.lineageAncestors,
          descendants: p.lineageDescendants,
        }}
        sections={[
          { heading: 'metrics',   body: `Sharpe ${p.sharpe.toFixed(2)} · drawdown ${p.drawdownPct.toFixed(1)}% · hit ${p.hitPct}% · agreement ${p.agreementPct}%.` },
          { heading: 'narrative', body: p.narrative },
        ]}
      />
    </div>
  );
};

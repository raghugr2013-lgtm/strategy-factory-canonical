/*
 * AI Workforce — S4 skeleton.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · D4
 */
import React, { useEffect, useState } from 'react';
import { Cpu, Sparkles, Landmark, Bot } from 'lucide-react';
import { PipelineStageBar } from '../primitives/PipelineStageBar';
import { WorkerCard } from '../primitives/WorkerCard';
import { DivisionCaption } from '../primitives/DivisionCaption';
import { StateTemplate } from '../primitives/StateTemplate';
import { fetchWorkers, fetchPipeline } from '../adapters/factoryAdapter';

const NAME_ICON = { ingestion: Cpu, signal: Sparkles, feature: Sparkles,
                    gov: Landmark, candle: Cpu, 'master-bot': Bot };
const iconFor = (name = '') => {
  const key = Object.keys(NAME_ICON).find((k) => name.includes(k));
  return NAME_ICON[key] ?? Cpu;
};

export const Workforce = () => {
  const [workers, setWorkers] = useState(null);
  const [pipeline, setPipeline] = useState([]);

  useEffect(() => {
    fetchWorkers().then(setWorkers);
    fetchPipeline().then(setPipeline);
  }, []);

  return (
    <section data-testid="workforce"
             style={{ padding: 'var(--space-6) var(--space-5)', maxWidth: 1200,
                      display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <div>
        <div style={{ color: 'var(--content-lo)', fontSize: 'var(--font-caption)',
                       letterSpacing: '0.1em', textTransform: 'uppercase',
                       marginBottom: 'var(--space-2)' }}>Workforce</div>
        <h1 data-testid="workforce-headline"
            style={{ margin: 0, marginBottom: 'var(--space-3)', fontSize: 'var(--font-h2)',
                     fontWeight: 400, color: 'var(--content-hi)' }}>
          Coordinates every research plan across ingest, feature, signal, backtest.
        </h1>
        <p data-testid="workforce-briefing"
           style={{ margin: 0, maxWidth: 720, fontSize: 'var(--font-body-md)',
                    lineHeight: 1.55, color: 'var(--content-md)' }}>
          Each worker is a purposeful agent. States tell you where attention is needed; subjects tell
          you what they're working on right now.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <DivisionCaption eyebrow="Master Bot pipeline" icon={Bot}
                         status={pipeline.filter((s) => s.status === 'done').length + '/' + pipeline.length + ' green'}
                         purpose="The current plan advances through eight canonical stages." />
        <PipelineStageBar stages={pipeline} testId="workforce-pipeline" />
      </div>

      {workers === null ? (
        <div style={{ color: 'var(--content-lo)' }}>Loading workers…</div>
      ) : workers.length === 0 ? (
        <StateTemplate variant="dormant" code="workforce-empty" icon={Cpu} tone="dormant"
                       headline="No workers currently registered." purpose="The Factory is idle." />
      ) : (
        <div data-testid="workforce-grid"
             style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                      gap: 'var(--space-4)' }}>
          {workers.map((w) => (
            <WorkerCard key={w.id}
                        testId={`workforce-worker-${w.id}`}
                        name={w.name} purpose={w.purpose} subject={w.subject}
                        state={w.state} icon={iconFor(w.name)} />
          ))}
        </div>
      )}
    </section>
  );
};

/*
 * ScenarioBanner — PROTOTYPE ONLY.
 * A compact strip above every surface that shows which walkthrough
 * scenario is active. Removed at Design Freeze.
 */
import { useInspectorStore } from '../workspace-state/inspectorStore';
import { SCENARIOS } from '../gallery/scenarios';

export const ScenarioBanner: React.FC = () => {
  const scenarioKey = useInspectorStore((s) => s.scenarioKey);
  const scenario = SCENARIOS.find((s) => s.key === scenarioKey);
  if (!scenario) return null;
  return (
    <div
      data-testid="scenario-banner"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 'var(--space-2)',
        alignSelf: 'flex-start',
        background: 'var(--surface-2)',
        border: '1px solid var(--stroke-2)',
        borderRadius: 'var(--radius-1)',
        padding: '3px 8px',
        fontSize: 'var(--font-caption)',
        color: 'var(--content-lo)',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        fontFamily: 'ui-monospace, monospace',
      }}
    >
      <span aria-hidden="true">◆</span>
      <span>scenario ·</span>
      <span style={{ color: 'var(--content-md)' }}>{scenario.title.toLowerCase()}</span>
    </div>
  );
};

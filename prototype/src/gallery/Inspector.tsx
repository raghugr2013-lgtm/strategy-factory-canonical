/*
 * Inspector — PROTOTYPE ONLY.
 * Fixture Debug Panel scaffolding for Phase 2. The full Phase 6 harness will
 * replace this. Toggles: canonical state · reduced motion · long content ·
 * density · mode · advanced lens.
 */
import { useInspectorStore } from '../workspace-state/inspectorStore';
import { useWorkspaceStore } from '../workspace-state/store';

const label: React.CSSProperties = {
  fontSize: 'var(--font-caption)',
  color: 'var(--content-lo)',
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
};

const control: React.CSSProperties = {
  background: 'var(--surface-2)',
  color: 'var(--content-md)',
  borderStyle: 'solid',
  borderWidth: 1,
  borderColor: 'var(--stroke-2)',
  borderRadius: 'var(--radius-1)',
  padding: '4px 8px',
  fontSize: 'var(--font-caption)',
  fontFamily: 'ui-monospace, monospace',
  textTransform: 'uppercase',
  letterSpacing: '0.06em',
  cursor: 'pointer',
};

const activeControl: React.CSSProperties = {
  ...control,
  background: 'var(--sig-info)',
  color: 'var(--surface-0)',
  borderColor: 'var(--sig-info)',
};

export const Inspector: React.FC = () => {
  const {
    canonicalState, setCanonicalState,
    reducedMotion, setReducedMotion,
    longContent, setLongContent,
  } = useInspectorStore();
  const { mode, setMode, density, setDensity, advancedLens, toggleAdvancedLens } = useWorkspaceStore();

  const states: Array<'happy' | 'loading' | 'empty' | 'error' | 'dormant'> =
    ['happy', 'loading', 'empty', 'error', 'dormant'];
  const modes: Array<'executive' | 'operations' | 'research' | 'developer'> =
    ['executive', 'operations', 'research', 'developer'];
  const densities: Array<'compact' | 'cozy' | 'cinema'> = ['compact', 'cozy', 'cinema'];

  return (
    <aside
      data-testid="inspector-panel"
      role="region"
      aria-label="Prototype fixture inspector"
      style={{
        position: 'sticky', top: 'var(--space-4)', alignSelf: 'flex-start',
        background: 'var(--surface-1)',
        border: '1px solid var(--stroke-2)',
        borderRadius: 'var(--radius-3)',
        padding: 'var(--space-4)',
        display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
        minWidth: 240,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={label}>Prototype Inspector</span>
        <span style={{ fontSize: 10, color: 'var(--content-lo)' }}>
          Fixture-only. Removed at Design Freeze.
        </span>
      </div>

      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <legend style={label}>Canonical state</legend>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {states.map((s) => (
            <button
              key={s}
              data-testid={`inspector-state-${s}`}
              onClick={() => setCanonicalState(s)}
              style={canonicalState === s ? activeControl : control}
            >
              {s}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <legend style={label}>Mode</legend>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {modes.map((m) => (
            <button
              key={m}
              data-testid={`inspector-mode-${m}`}
              onClick={() => setMode(m)}
              style={mode === m ? activeControl : control}
            >
              {m}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <legend style={label}>Density</legend>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {densities.map((d) => (
            <button
              key={d}
              data-testid={`inspector-density-${d}`}
              onClick={() => setDensity(d)}
              style={density === d ? activeControl : control}
            >
              {d}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset style={{ border: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <legend style={label}>Toggles</legend>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <button
            data-testid="inspector-advanced-lens"
            onClick={toggleAdvancedLens}
            style={advancedLens ? activeControl : control}
          >
            advanced lens
          </button>
          <button
            data-testid="inspector-reduced-motion"
            onClick={() => setReducedMotion(!reducedMotion)}
            style={reducedMotion ? activeControl : control}
          >
            reduced motion
          </button>
          <button
            data-testid="inspector-long-content"
            onClick={() => setLongContent(!longContent)}
            style={longContent ? activeControl : control}
          >
            long content
          </button>
        </div>
      </fieldset>
    </aside>
  );
};

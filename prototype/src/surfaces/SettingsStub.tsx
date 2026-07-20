/*
 * SettingsStub — minimal placeholder so the LeftRail "settings" module has a
 * destination while the real Settings surface is out of Phase 4 scope.
 */
import { Settings } from 'lucide-react';
import { SurfaceHeader } from './SurfaceHeader';
import { ScenarioBanner } from './ScenarioBanner';
import { StateTemplate } from '../primitives/StateTemplate';

export const SettingsStub: React.FC = () => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
    <ScenarioBanner />
    <SurfaceHeader
      eyebrow="Settings · workspace"
      headline="Settings arrive in Sprint 1."
      briefing="Personalization Mode, density, and shortcuts already live in the header user menu."
      testId="settings-header"
    />
    <StateTemplate
      variant="dormant"
      code="settings-out-of-scope"
      icon={Settings}
      tone="dormant"
      headline="Not part of the interactive prototype."
      purpose="This surface will be authored during Sprint 1 in production."
      advancedFootnote="phase 4 · out of scope"
    />
  </div>
);

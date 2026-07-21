import React from 'react';
import { KeyboardShortcut, KeyboardShortcutHUD } from './KeyboardShortcutHUD';

export default {
  title: 'Primitives/KeyboardShortcut',
  component: KeyboardShortcut,
  parameters: { docs: { description: { component: 'Bible §7.10 · keyboard-chord affordance.' } } },
};

export const CommandK = { args: { chord: '⌘K', label: 'find anything' } };
export const Escape = { args: { chord: 'Esc', label: 'close overlay' } };
export const ChordSequence = { args: { chord: 'g m', label: 'go · mission control' } };
export const HUDMounted = { render: () => (
  <div>
    <p style={{ color: 'var(--content-md)' }}>Press <kbd>?</kbd> to open the HUD.</p>
    <KeyboardShortcutHUD />
  </div>
) };

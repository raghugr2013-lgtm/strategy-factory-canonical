/*
 * Storybook preview · loads OS design tokens + a11y baseline.
 */
import React from 'react';
import '../src/os/tokens.css';
import '../src/index.css';

/** @type {import('@storybook/react').Preview} */
const preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'sf-dark',
      values: [
        { name: 'sf-dark', value: '#0b0d10' },
        { name: 'sf-surface', value: '#12151a' },
        { name: 'white', value: '#ffffff' },
      ],
    },
    a11y: {
      config: {
        rules: [
          // Design Freeze v1.0 §1.5 — Chip glyphs are decorative letters (P/W/F/A/I);
          // color-contrast is enforced by tokens.css. We keep the rule ON here.
        ],
      },
      options: {},
    },
    options: {
      storySort: {
        order: ['Primitives', 'Features', 'Surfaces', 'Shell'],
      },
    },
  },
  decorators: [
    (Story) =>
      React.createElement(
        'div',
        {
          'data-sb-frame': 'true',
          style: {
            padding: 'var(--space-5)',
            background: 'var(--surface-0)',
            color: 'var(--content-hi)',
            minHeight: '100vh',
            fontFamily: 'var(--font-body)',
          },
        },
        React.createElement(Story)
      ),
  ],
};

export default preview;

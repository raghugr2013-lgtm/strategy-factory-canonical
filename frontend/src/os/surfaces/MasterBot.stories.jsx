import React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { MasterBot } from './MasterBot';

export default {
  title: 'Surfaces/MasterBot',
  component: MasterBot,
  parameters: {
    docs: { description: { component: 'Sprint 2 N2 · Surface D4 (standalone). Identity strip + current plan card + last decisions log. Fixture-only until backend exposes /api/master-bot/*.' } },
    layout: 'fullscreen',
  },
  decorators: [
    (Story) => (
      <BrowserRouter>
        <div style={{ background: 'var(--surface-0)', minHeight: '100vh' }}>
          <Story />
        </div>
      </BrowserRouter>
    ),
  ],
};

export const Default = { render: () => <MasterBot /> };

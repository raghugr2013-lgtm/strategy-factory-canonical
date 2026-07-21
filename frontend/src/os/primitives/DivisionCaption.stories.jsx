import React from 'react';
import { GitBranch, Activity } from 'lucide-react';
import { DivisionCaption } from './DivisionCaption';

export default {
  title: 'Primitives/DivisionCaption',
  component: DivisionCaption,
  parameters: { docs: { description: { component: 'D4 §5.1.1 · purpose-first sectional heading.' } } },
};

export const PipelineSection = { args: { eyebrow: 'Factory pipeline', icon: GitBranch, status: '5/8 stages green',
  purpose: 'The Factory advances a strategy through eight canonical stages, from ingest to monitor.' } };
export const LatestActivity = { args: { eyebrow: 'Latest activity', icon: Activity, status: '12 recent events',
  purpose: 'A ranked feed of the last few decisions the Factory took.' } };

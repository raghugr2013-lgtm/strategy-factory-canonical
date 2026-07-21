import React from 'react';
import { Sparkles } from 'lucide-react';
import { SignatureFrame } from './SignatureFrame';

export default {
  title: 'Primitives/SignatureFrame',
  component: SignatureFrame,
  parameters: { docs: { description: { component: 'D5 §2 · editorial gallery-card framing.' } } },
};

export const InfoTone = { args: { tone: 'info', caption: 'Passport strategy #47', children: 'Body copy · replaces with hero metrics.' } };
export const GoldTone = { args: { tone: 'gold', icon: Sparkles, caption: 'Flagship', children: 'Hero framing for signature surfaces.' } };
export const CritTone = { args: { tone: 'crit', caption: 'Kill posture', children: 'Break-glass warning card.' } };
export const DormantTone = { args: { tone: 'dormant', caption: 'Archived plan', children: 'Muted for archived items.' } };

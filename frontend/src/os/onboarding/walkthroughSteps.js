/*
 * walkthroughSteps.js — content for the Factory Walkthrough.
 * refs UX-Review-2026-07-22 · Sprint 3 Phase-1 · onboarding follow-up
 *
 * Nine self-paced slides:
 *   0  intro     — product philosophy in one sentence
 *   1  mission   — the executive glance
 *   2  masterbot — the overseer AI
 *   3  timeline  — the audit trail
 *   4  approvals — the human gate
 *   5  workforce — the AI workers
 *   6  engineering — build & improve
 *   7  admin     — configure & operate
 *   8  outro    — restate the split; hand off to Mission
 *
 * Each slide is designed to be read in <4 seconds. Total time under 30s at
 * a comfortable pace; skip-any-time preserved.
 */
import {
  Compass, Bot, Activity, ShieldCheck, Users, FlaskConical, Shield, Sparkles,
} from 'lucide-react';

export const WALKTHROUGH_VERSION = '1.3.0-sprint3-phase1';

export const WALKTHROUGH_STEPS = [
  {
    id: 'intro',
    tone: 'accent',
    icon: Sparkles,
    eyebrow: 'Welcome',
    title: 'The Strategy Factory has two sides.',
    body: [
      'The Operator OS supervises the AI Factory — one clean shell, one place for approvals.',
      'The Engineering Workspace builds and improves it — every research, data, and deployment capability sits behind one grouped rail.',
      "This 30-second walkthrough shows you where each lives and why they are split. Press \u2192 to continue, or Esc to skip.",
    ],
  },
  {
    id: 'mission',
    tone: 'info',
    icon: Compass,
    eyebrow: 'Mission Control · 1 of 7',
    title: 'What does the Factory need from you right now?',
    body: [
      'The landing surface answers six operator questions in one glance: strategies live, approvals pending, signals in queue, portfolio equity, factory pipeline health, and last-shift throughput.',
      'If Mission is quiet, the Factory is quiet. If it flags a decision, click through — Approvals, Timeline and Workforce are one step away.',
    ],
    surfaceHint: '/c/mission',
  },
  {
    id: 'masterbot',
    tone: 'info',
    icon: Bot,
    eyebrow: 'Master Bot · 2 of 7',
    title: 'The overseer AI. Its stance, plan, and last decisions.',
    body: [
      'The Master Bot orchestrates the entire Factory under a governed trust budget.',
      'Read the plan card to see the current ambition and next-tick postmark. Every decision is here first, then it flows into Approvals for a human gate.',
    ],
    surfaceHint: '/c/masterbot',
  },
  {
    id: 'timeline',
    tone: 'info',
    icon: Activity,
    eyebrow: 'Timeline · 3 of 7',
    title: 'Every action by every actor. One chronological stream.',
    body: [
      'This is the audit trail — Governance holds, Master Bot plans, LLM proposals, ingestion failures, your approvals.',
      "Filter by actor when you're investigating; the stream postmark proves the surface is live.",
    ],
    surfaceHint: '/c/timeline',
  },
  {
    id: 'approvals',
    tone: 'info',
    icon: ShieldCheck,
    eyebrow: 'Approvals · 4 of 7',
    title: 'The human gate — with evidence already attached.',
    body: [
      'Every governance decision materialises here as an ApprovalCard: headline, evidence body, provenance triple, risk chip.',
      'Approve, Defer, or Block. Under the current Backend Feature Freeze, verdicts are acknowledged locally and queued for commit when the freeze lifts.',
    ],
    surfaceHint: '/c/approvals',
  },
  {
    id: 'workforce',
    tone: 'info',
    icon: Users,
    eyebrow: 'Workforce · 5 of 7',
    title: 'The AI workers and what each one is doing right now.',
    body: [
      'Signal-Forge, Backtest-Warden, LLM-Composer — each with a state chip (Active · Idle · Blocked · Error) and a live subject line.',
      'A blocked worker means an Approval is waiting. An errored worker will reconnect on its own; if it does not, propose a restart via \u2318K.',
    ],
    surfaceHint: '/c/workforce',
  },
  {
    id: 'engineering',
    tone: 'engineering',
    icon: FlaskConical,
    eyebrow: 'Engineering Workspace · 6 of 7',
    title: 'This is where you build the AI Factory.',
    body: [
      'Ten surfaces — Market Data, Coverage, Datasets, Strategy Lab, Optimization, Validation, Portfolio, Prop Firms, Deployments, Strategy Passports.',
      'Most are marked SCHEDULED FOR PHASE 2: each empty state documents what it will present and which live endpoint will feed it, so you know exactly what is coming.',
    ],
    surfaceHint: '/c/engineering/market-data',
  },
  {
    id: 'admin',
    tone: 'warn',
    icon: Shield,
    eyebrow: 'Admin · 7 of 7',
    title: 'System configuration and operational management.',
    body: [
      'Visible only to admins — Settings, Users, Integrations, and Logs.',
      'Under the freeze this section is scaffolded; Phase 2 will bring live user CRUD, connector probes, and streaming log tails.',
    ],
    surfaceHint: '/c/settings',
    adminOnly: true,
  },
  {
    id: 'outro',
    tone: 'accent',
    icon: Sparkles,
    eyebrow: 'Ready',
    title: 'Operator supervises. Engineering builds.',
    body: [
      'That is the whole product philosophy. Use Mission Control day-to-day; jump into the Engineering Workspace when you want to iterate.',
      'You can re-open this walkthrough anytime from the user menu \u2192 Factory Walkthrough.',
    ],
  },
];

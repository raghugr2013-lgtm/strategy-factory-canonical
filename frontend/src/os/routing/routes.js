/*
 * Route registry — canonical Sprint 1 URL scheme.
 * refs DESIGN_FREEZE_v1.0.md §1.4 (Surfaces) · D8 §3.3
 *
 * Every route is a first-class citizen; every route is bookmarkable.
 * State-Memory data never enters the URL — CNL payload (mode · facets ·
 * strategy · time_window) is passed as query params.
 */
import { Activity, ShieldCheck, Users, LineChart, Settings as SettingsIcon, Compass, Terminal, Bot } from 'lucide-react';

export const ROUTES = [
  { path: '/c/mission',    label: 'MISSION',    icon: Compass,      testId: 'nav-mission',    surface: 'mission' },
  { path: '/c/masterbot',  label: 'MASTER BOT', icon: Bot,          testId: 'nav-masterbot',  surface: 'masterbot' },
  { path: '/c/timeline',   label: 'TIMELINE',   icon: Activity,     testId: 'nav-timeline',   surface: 'timeline' },
  { path: '/c/approvals',  label: 'APPROVALS',  icon: ShieldCheck,  testId: 'nav-approvals',  surface: 'approvals' },
  { path: '/c/workforce',  label: 'WORKFORCE',  icon: Users,        testId: 'nav-workforce',  surface: 'workforce' },
  { path: '/c/strategies', label: 'STRATEGIES', icon: LineChart,    testId: 'nav-strategies', surface: 'strategies' },
  { path: '/c/settings',   label: 'SETTINGS',   icon: SettingsIcon, testId: 'nav-settings',   surface: 'settings' },
];

export const DEFAULT_AUTHENTICATED_ROUTE = '/c/mission';
export const SIGN_IN_ROUTE = '/auth/sign-in';

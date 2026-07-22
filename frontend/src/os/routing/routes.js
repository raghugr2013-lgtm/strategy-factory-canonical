/*
 * routes.js — canonical Sprint 1 URL scheme, extended for Sprint 3 Phase-1.
 * refs DESIGN_FREEZE_v1.0.md §1.4 · UX-Review-2026-07-22
 *
 * ROUTES remains the flat list consumed by:
 *   - Header eyebrow lookup (Header.jsx)
 *   - ⌘K jump-to-surface list (CmdKPalette.jsx)
 * Sprint 3 Phase-1 adds Engineering + Admin entries (all frontend-additive,
 * no backend changes under Feature Freeze v1.1.0-stage4).
 */
import { flattenNav } from './navigation';

export const ROUTES = flattenNav('admin');

export const DEFAULT_AUTHENTICATED_ROUTE = '/c/mission';
export const SIGN_IN_ROUTE = '/auth/sign-in';

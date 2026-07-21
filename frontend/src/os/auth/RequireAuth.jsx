/*
 * RequireAuth — auth guard + Rule of Predictable Return (E5 §4.5).
 * refs DESIGN_FREEZE_v1.0.md §1.2 principle E5
 *
 * If the operator is anonymous or expired, redirect to /auth/sign-in
 * with ?next=<original>. On sign-in, LoginScreen honours ?next.
 */
import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../workspace-state/authStore';
import { SIGN_IN_ROUTE } from '../routing/routes';

export const RequireAuth = ({ children }) => {
  const stance = useAuthStore((s) => s.stance);
  const location = useLocation();

  if (stance !== 'authenticated') {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    return <Navigate to={`${SIGN_IN_ROUTE}?next=${next}`} replace />;
  }
  return children;
};

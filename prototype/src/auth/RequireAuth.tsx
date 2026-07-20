/*
 * RequireAuth — E2 §5 · route guard.
 * If the operator is not authenticated, redirect to /auth/sign-in with the
 * intended destination captured as `?next=`. Preserves CNL query params.
 */
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../workspace-state/authStore';

export const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const stance = useAuthStore((s) => s.stance);
  const loc = useLocation();
  if (stance !== 'authenticated') {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/auth/sign-in?next=${next}`} replace />;
  }
  return <>{children}</>;
};

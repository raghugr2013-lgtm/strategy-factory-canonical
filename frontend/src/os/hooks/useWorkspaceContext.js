/*
 * useWorkspaceContext — canonical §9 primitive.
 * refs docs/ARCHITECTURE.md §9 · Workspace context model
 *
 * A small, URL-encoded state that every surface honours as an implicit
 * filter. Four fields, all optional:
 *
 *   pair       (e.g. "XAUUSD")
 *   timeframe  (e.g. "H4")
 *   strategy   (strategy_id)
 *   cycle      (optimization cycle id — post-freeze; carried for shape only)
 *
 * Source of truth is the URL query string. This hook mirrors that state
 * into a stable React value and exposes a setter that patches the URL
 * without a full navigation.
 *
 * Session-lived: not persisted across sessions (browser handles that
 * implicitly by clearing the URL on new tab). Every day starts fresh.
 *
 * Canonical URL keys (short, stable, human-typeable):
 *   pair  → ?pair=XAUUSD
 *   tf    → ?tf=H4
 *   sid   → ?sid=84d32cc1...
 *   cyc   → ?cyc=...     (reserved)
 */
import { useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

const KEYS = { pair: 'pair', timeframe: 'tf', strategy: 'sid', cycle: 'cyc' };

const readContext = (search) => {
  const q = new URLSearchParams(search);
  return {
    pair:      q.get(KEYS.pair)      || null,
    timeframe: q.get(KEYS.timeframe) || null,
    strategy:  q.get(KEYS.strategy)  || null,
    cycle:     q.get(KEYS.cycle)     || null,
  };
};

const writeContext = (search, patch) => {
  const q = new URLSearchParams(search);
  for (const [k, urlKey] of Object.entries(KEYS)) {
    if (k in patch) {
      const v = patch[k];
      if (v == null || v === '') q.delete(urlKey);
      else q.set(urlKey, String(v));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : '';
};

export const useWorkspaceContext = () => {
  const location = useLocation();
  const navigate = useNavigate();

  const context = useMemo(() => readContext(location.search), [location.search]);

  const setContext = useCallback((patch) => {
    const next = writeContext(location.search, patch || {});
    navigate({ pathname: location.pathname, search: next }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const clearContext = useCallback(() => {
    // Preserve non-canonical query keys (feature flags, deep links) — only
    // strip the four canonical context keys.
    const q = new URLSearchParams(location.search);
    for (const urlKey of Object.values(KEYS)) q.delete(urlKey);
    const s = q.toString();
    navigate({ pathname: location.pathname, search: s ? `?${s}` : '' }, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const isActive = useMemo(
    () => !!(context.pair || context.timeframe || context.strategy || context.cycle),
    [context]
  );

  return { context, setContext, clearContext, isActive };
};

/**
 * matchesContext — helper for surfaces filtering their own inventories
 * against the current workspace context. Case-insensitive comparison.
 * Fields the context has not set are treated as "any" (match everything).
 */
export const matchesContext = (row, context) => {
  if (!context) return true;
  const eq = (a, b) => String(a || '').toLowerCase() === String(b || '').toLowerCase();
  if (context.pair       && !eq(row.symbol || row.pair,   context.pair))       return false;
  if (context.timeframe  && !eq(row.timeframe,             context.timeframe))  return false;
  if (context.strategy   && !eq(row.strategy_id,           context.strategy))   return false;
  return true;
};

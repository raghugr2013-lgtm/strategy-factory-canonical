/**
 * COMMAND · Phase U.4 — Inspector context
 * ----------------------------------------------------------------------------
 * Global selection state shared across modules. Any UI element (a survivor
 * row, a call-log row, an attention item, a lineage node) can call
 *   inspector.inspect({ type, ...meta })
 * and the right-side <InspectorPane /> updates with the appropriate view.
 *
 * Selection types in U.4:
 *   • 'strategy'   { strategyId }
 *   • 'llm-call'   { call }
 *   • 'attention'  { item }
 *   • null         (closed)
 *
 * Persistence: the current selection survives a route change inside the
 * COMMAND shell — the operator can click a strategy in /c/explorer, then
 * navigate to /c/ai, and the strategy lineage stays in the inspector.
 * Selection is NOT persisted across hard reloads (it's UX state, not data).
 */
import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

const InspectorContext = createContext({
  selection: null,
  open: false,
  inspect: () => {},
  close: () => {},
  toggle: () => {},
});

export function InspectorProvider({ children }) {
  const [selection, setSelection] = useState(null);
  const [open, setOpen]           = useState(false);

  const inspect = useCallback((sel) => {
    if (!sel || !sel.type) { setSelection(null); setOpen(false); return; }
    setSelection(sel);
    setOpen(true);
  }, []);

  const close = useCallback(() => setOpen(false), []);
  const toggle = useCallback(() => setOpen((v) => !v), []);

  const value = useMemo(
    () => ({ selection, open, inspect, close, toggle }),
    [selection, open, inspect, close, toggle],
  );

  return (
    <InspectorContext.Provider value={value}>
      {children}
    </InspectorContext.Provider>
  );
}

export function useInspector() {
  return useContext(InspectorContext);
}

/*
 * Optimistic-UI middleware — Bible §6.3 · Kickoff Plan §4 · M3 · F3.
 * refs DESIGN_FREEZE_v1.0.md §1.4 (Approval Center) · Bible §6.3
 *
 * Contract:
 *   const [state, action] = useOptimistic(initial, {
 *     apply:  (state, payload) => nextState,
 *     commit: async (payload) => any,      // real network call
 *     revert: (state, payload) => state,   // rollback on commit failure
 *   });
 *   action({ ...payload });
 *
 * On dispatch:
 *   1. Immediately apply state locally (UI feels instant).
 *   2. Fire commit(). On success: keep local state.
 *   3. On failure: call revert(state, payload) and rethrow so callers can toast.
 */
import { useCallback, useState } from 'react';

export const useOptimistic = (initial, { apply, commit, revert }) => {
  const [state, setState] = useState(initial);

  const dispatch = useCallback(async (payload) => {
    let previous;
    setState((s) => { previous = s; return apply(s, payload); });
    try {
      await commit(payload);
      return { ok: true };
    } catch (err) {
      setState((s) => (revert ? revert(previous ?? s, payload) : (previous ?? s)));
      return { ok: false, error: err };
    }
  }, [apply, commit, revert]);

  return [state, dispatch, setState];
};

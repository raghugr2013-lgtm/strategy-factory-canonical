/*
 * ApprovalsModal — canonical §12 · Approvals / confirmation pattern.
 * refs docs/ARCHITECTURE.md §12 · Approvals pattern
 * refs docs/ARCHITECTURE.md §13 · Event vocabulary
 * refs docs/ARCHITECTURE.md §20 · Autonomy boundaries (H tier channel)
 *
 * A single systemic modal for every state-changing mutation. Not
 * per-surface confirm dialogs (§12). Anatomy is fixed:
 *
 *   [ APPROVE · <action label> ]
 *   Strategy · <target name+id>
 *   Actor    · <email> · <role>
 *   Reason   · [required textarea]
 *   Consequences bullets
 *   [ CANCEL ]         [ CONFIRM ⌘⏎ ]
 *
 * Cancel is default focus. Confirm requires ⌘⏎ (§12 keyboard-first).
 * Every confirm emits a §13 event to the timeline shim BEFORE the
 * executor runs; failed executors emit a matching `_failed` event.
 *
 * Global open handle via `openApproval(config)` — modal is registered
 * once at the shell root so any surface can open it without prop drill.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { create } from 'zustand';
import { ShieldCheck, X } from 'lucide-react';
import { useAuthStore } from '../workspace-state/authStore';
import { useTimelineShim } from '../adapters/timelineShim';

// Global registry — one modal per shell, one open action at a time.
const useApprovalsStore = create((set) => ({
  request: null, // { action_label, event_name, target, context, consequences, executor }
  open: (request) => set({ request }),
  close: () => set({ request: null }),
}));

export const openApproval = (request) => useApprovalsStore.getState().open(request);
export const closeApproval = () => useApprovalsStore.getState().close();

export const ApprovalsModal = () => {
  const request = useApprovalsStore((s) => s.request);
  const close = useApprovalsStore((s) => s.close);
  const emit = useTimelineShim((s) => s.emit);
  const email = useAuthStore((s) => s.email);
  const role = useAuthStore((s) => s.role);
  const cancelRef = useRef(null);
  const [reason, setReason] = useState('');
  const [phase, setPhase] = useState('idle'); // idle · submitting · error
  const [errMsg, setErrMsg] = useState(null);

  // Reset on open
  useEffect(() => {
    if (request) {
      setReason('');
      setPhase('idle');
      setErrMsg(null);
      setTimeout(() => cancelRef.current?.focus(), 40);
    }
  }, [request]);

  const onConfirm = useCallback(async () => {
    if (!request || !reason.trim()) return;
    setPhase('submitting');
    setErrMsg(null);
    // §13 — emit BEFORE executing so the intent is always audited.
    const requestedEvt = emit({
      event_name: `${request.event_name}_requested`,
      actor: { email, role, session_id: null },
      object: request.target,
      context: request.context || {},
      reason: reason.trim(),
    });
    try {
      const result = request.executor ? await request.executor({ reason: reason.trim(), approvedEvt: requestedEvt }) : null;
      emit({
        event_name: `${request.event_name}_approved`,
        actor: { email, role, session_id: null },
        object: request.target,
        context: request.context || {},
        reason: reason.trim(),
      });
      request.onSuccess?.(result);
      close();
    } catch (err) {
      emit({
        event_name: `${request.event_name}_failed`,
        actor: { email, role, session_id: null },
        object: request.target,
        context: request.context || {},
        reason: `${reason.trim()} · ${err?.message || 'executor error'}`,
      });
      setPhase('error');
      setErrMsg(err?.message || 'Executor failed.');
    }
  }, [request, reason, emit, email, role, close]);

  // ⌘⏎ / Ctrl+⏎ confirm shortcut (§12)
  useEffect(() => {
    if (!request) return;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        onConfirm();
      }
      if (e.key === 'Escape') { e.preventDefault(); close(); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [request, onConfirm, close]);

  if (!request) return null;

  const canConfirm = reason.trim().length > 0 && phase !== 'submitting';

  return (
    <div data-testid="approvals-modal-overlay"
         onClick={close}
         style={{
           position: 'fixed', inset: 0, zIndex: 200,
           background: 'color-mix(in oklab, var(--surface-0) 70%, transparent)',
           backdropFilter: 'blur(4px)',
           display: 'flex', alignItems: 'center', justifyContent: 'center',
         }}>
      <div data-testid="approvals-modal"
           role="dialog"
           aria-modal="true"
           onClick={(e) => e.stopPropagation()}
           style={{
             minWidth: 520, maxWidth: 640,
             background: 'var(--surface-1)',
             border: '1px solid var(--stroke-2)',
             borderRadius: 'var(--radius-3)',
             padding: 'var(--space-5)',
             boxShadow: '0 24px 64px rgba(0,0,0,0.4)',
           }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', marginBottom: 'var(--space-3)' }}>
          <ShieldCheck size={16} strokeWidth={1.75} color="var(--accent-gold)" />
          <div data-testid="approvals-modal-title"
               style={{ fontSize: 'var(--font-caption)', letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent-gold)', fontWeight: 600 }}>
            Approve · {request.action_label}
          </div>
          <button type="button" data-testid="approvals-modal-x" onClick={close} style={xBtn}>
            <X size={14} strokeWidth={1.75} />
          </button>
        </div>
        <KV k="Strategy" v={<><span style={{ color: 'var(--content-hi)' }}>{request.target?.name || '—'}</span>
          {' · '}<code className="mono-num" style={{ color: 'var(--content-md)' }}>{request.target?.id || '—'}</code></>} />
        <KV k="Actor"    v={<><span style={{ color: 'var(--content-hi)' }}>{email || 'anonymous'}</span>
          {' · '}<code style={{ color: 'var(--content-md)' }}>{role || 'operator'}</code></>} />
        <KV k="Event"    v={<code className="mono-num" style={{ color: 'var(--sig-info)' }}>{request.event_name}_approved</code>} last />

        <div data-testid="approvals-modal-reason-wrap" style={{ marginTop: 'var(--space-3)' }}>
          <label style={eyebrow}>Reason (required)</label>
          <textarea data-testid="approvals-modal-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={3}
                    placeholder="Why is this transition safe?"
                    style={textareaStyle} />
        </div>

        {Array.isArray(request.consequences) && request.consequences.length > 0 && (
          <div data-testid="approvals-modal-consequences" style={{ marginTop: 'var(--space-3)', fontSize: 'var(--font-body-sm)', color: 'var(--content-md)' }}>
            <div style={eyebrow}>This will</div>
            <ul style={{ margin: 'var(--space-2) 0 0 var(--space-4)', padding: 0, lineHeight: 1.7 }}>
              {request.consequences.map((c, i) => (<li key={i}>{c}</li>))}
            </ul>
          </div>
        )}

        {phase === 'error' && errMsg && (
          <div data-testid="approvals-modal-error"
               style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2) var(--space-3)',
                        border: '1px solid color-mix(in oklab, var(--sig-crit) 40%, transparent)',
                        background: 'color-mix(in oklab, var(--sig-crit) 6%, transparent)',
                        color: 'var(--sig-crit)', borderRadius: 'var(--radius-2)', fontSize: 'var(--font-body-sm)' }}>
            {errMsg}
          </div>
        )}

        <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'flex-end', marginTop: 'var(--space-4)' }}>
          <button type="button" ref={cancelRef} data-testid="approvals-modal-cancel"
                  onClick={close} style={cancelBtn}>
            Cancel
          </button>
          <button type="button" data-testid="approvals-modal-confirm"
                  onClick={onConfirm}
                  disabled={!canConfirm}
                  style={{ ...confirmBtn, opacity: canConfirm ? 1 : 0.5, cursor: canConfirm ? 'pointer' : 'not-allowed' }}>
            {phase === 'submitting' ? 'Submitting…' : (
              <>Confirm <span style={{ opacity: 0.7, marginLeft: 6 }}>⌘⏎</span></>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

const KV = ({ k, v, last }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--space-3)', padding: 'var(--space-2) 0', borderBottom: last ? '1px solid var(--stroke-1)' : '1px solid var(--stroke-1)', fontSize: 'var(--font-body-sm)' }}>
    <span style={{ color: 'var(--content-lo)' }}>{k}</span>
    <span style={{ textAlign: 'right' }}>{v}</span>
  </div>
);

const eyebrow = {
  color: 'var(--content-lo)',
  fontSize: 'var(--font-caption)',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  display: 'block',
  marginBottom: 'var(--space-1)',
};
const textareaStyle = {
  width: '100%', boxSizing: 'border-box',
  background: 'var(--surface-2)', color: 'var(--content-hi)',
  border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-2)',
  padding: 'var(--space-2) var(--space-3)',
  fontSize: 'var(--font-body-sm)', fontFamily: 'inherit', outline: 'none', resize: 'vertical',
};
const cancelBtn = {
  padding: 'var(--space-2) var(--space-4)',
  background: 'var(--surface-2)', color: 'var(--content-md)',
  border: '1px solid var(--stroke-2)', borderRadius: 'var(--radius-2)',
  fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase',
  fontFamily: 'inherit', cursor: 'pointer',
};
const confirmBtn = {
  padding: 'var(--space-2) var(--space-4)',
  background: 'var(--accent-gold)', color: 'var(--surface-0)',
  border: 'none', borderRadius: 'var(--radius-2)',
  fontSize: 'var(--font-caption)', letterSpacing: '0.08em', textTransform: 'uppercase',
  fontFamily: 'inherit', fontWeight: 600,
};
const xBtn = {
  marginLeft: 'auto', width: 22, height: 22, borderRadius: '50%',
  background: 'transparent', border: 'none', color: 'var(--content-lo)',
  cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
};

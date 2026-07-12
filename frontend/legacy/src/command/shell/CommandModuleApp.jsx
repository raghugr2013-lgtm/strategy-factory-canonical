/**
 * COMMAND · Phase U.2 — CommandModuleApp
 * ----------------------------------------------------------------------------
 * Top-level page that boots the COMMAND shell for any /c/* URL.
 *
 * Behaviour:
 *   • Forces [data-ui="command"] on the body so foundations apply.
 *   • Hooks router → shell so LeftRail / palette / drawer all navigate via
 *     URL pushState. Back/forward buttons just work.
 *   • Renders <ModuleSurface/> inside <CommandShell/>. The shell handles
 *     posture, command bar, status rail, etc.
 *
 * Auth:
 *   Mounted by App.js BEFORE AuthGate only when an explicit auth bypass
 *   is requested via ?preview=1. For normal /c/* paths, App.js places
 *   <CommandModuleApp/> AFTER AuthGate, so the same auth gate that
 *   protects legacy /  protects the COMMAND OS.
 */
import React, { useEffect } from 'react';
import CommandShell from './CommandShell';
import ModuleSurface from './ModuleSurface';
import { useRoute } from './router';
import { usePosture } from './usePosture';

export default function CommandModuleApp({ user }) {
  const { moduleId, navigate } = useRoute();
  const posture = usePosture();

  // Force COMMAND mode while this app is mounted.
  useEffect(() => {
    const body = document.body;
    const prev = body.getAttribute('data-ui');
    body.setAttribute('data-ui', 'command');
    try { localStorage.setItem('cmd-ui-mode', '1'); } catch (_) {}
    return () => {
      if (prev) body.setAttribute('data-ui', prev);
      else body.removeAttribute('data-ui');
    };
  }, []);

  return (
    <CommandShell
      activeId={moduleId}
      onNavigate={navigate}
      user={user}
    >
      <ModuleSurface moduleId={moduleId} posture={posture} />
    </CommandShell>
  );
}

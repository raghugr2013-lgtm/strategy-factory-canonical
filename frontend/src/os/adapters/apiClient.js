/*
 * apiClient — Sprint 2 N4 edition.
 * refs SPRINT_2_PLANNING.md §2 N4 (401 interceptor + strict-live flag)
 *
 * • isLiveMode()           — REACT_APP_BACKEND_URL present.
 * • isStrictLive()         — REACT_APP_STRICT_LIVE=1 disables fixture fallback
 *                            so surfaces surface adapter errors instead of
 *                            silently substituting fixtures (dev diagnostic).
 * • apiFetch()             — Bearer JWT + centralized 401 interceptor.
 *                            On 401 the interceptor clears the session token
 *                            and dispatches a browser event that RequireAuth
 *                            listens for → forces sign-in redirect.
 * • fixtureOrLive()        — tries live, falls back to fixture (unless strict).
 * • unavailableBreadcrumb  — single-shot dev breadcrumb for gated endpoints.
 */
// CRA / craco replaces `process.env.<var>` with a string literal at build
// time via DefinePlugin. Wrap in a try/catch so this file is also safe to
// load in a bare Node context where `process.env` is available but the
// individual keys may be undefined. The prior `typeof process !== 'undefined'`
// guard mis-fired at runtime in the browser (where `process` is not defined
// as a global) and silently forced the entire app into fixture-mode — this
// unblocks live-mode consumption of the Backend Feature Freeze v1.1.0-stage4
// endpoints for Sprint 3 Phase-2.
let _BACKEND_URL = '';
let _STRICT_LIVE = false;
try { _BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || '').trim(); } catch { /* noop */ }
try { _STRICT_LIVE = (process.env.REACT_APP_STRICT_LIVE || '') === '1'; } catch { /* noop */ }
const BACKEND_URL = _BACKEND_URL;
const STRICT_LIVE = _STRICT_LIVE;

export const isLiveMode = () => Boolean(BACKEND_URL);
export const isStrictLive = () => STRICT_LIVE;

const readToken = () => {
  try { return sessionStorage.getItem('sf-auth-token') || null; } catch { return null; }
};

const clearToken = () => {
  try { sessionStorage.removeItem('sf-auth-token'); } catch { /* noop */ }
};

const dispatchUnauthorized = (path) => {
  try {
    window.dispatchEvent(new CustomEvent('sf-auth-unauthorized', { detail: { path } }));
  } catch { /* noop */ }
};

export const apiFetch = async (path, opts = {}) => {
  if (!BACKEND_URL) throw new Error('fixture-mode');
  const token = readToken();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${BACKEND_URL}${path}`, { ...opts, headers });
  if (res.status === 401) {
    // Sprint 2 N4 · centralized 401 interceptor.
    clearToken();
    dispatchUnauthorized(path);
    const err = new Error(`api ${path} 401 unauthorized`);
    err.status = 401;
    throw err;
  }
  if (!res.ok) {
    const err = new Error(`api ${path} ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const ct = res.headers.get('content-type') || '';
  return ct.includes('application/json') ? res.json() : res.text();
};

export const fixtureOrLive = async (endpoint, fixture, opts) => {
  if (!isLiveMode() || !endpoint) return fixture;
  try {
    return await apiFetch(endpoint, opts);
  } catch (e) {
    if (STRICT_LIVE) throw e;
    console.warn(`[adapter] live fetch failed for ${endpoint}, falling back to fixture:`, e.message);
    return fixture;
  }
};

const _seen = new Set();
export const unavailableBreadcrumb = (adapterName, expectedEndpoint, reason) => {
  if (_seen.has(adapterName)) return;
  _seen.add(adapterName);
  console.info(
    `[adapter] ${adapterName} · endpoint ${expectedEndpoint} unavailable under Backend Feature Freeze v1.1.0-stage4 · reason: ${reason} · using fixture data.`
  );
};

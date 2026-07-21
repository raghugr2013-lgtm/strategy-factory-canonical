/*
 * apiClient — Backend Integration edition.
 * refs SPRINT_1_COMPLETION_REPORT.md §6.1 + operator directive
 *     "Adapter layer is the compatibility boundary between the frozen backend
 *      and the Sprint 1 frontend."
 *
 * `isLiveMode()` gates live traffic on REACT_APP_BACKEND_URL presence.
 * `apiFetch()` injects Bearer JWT from sessionStorage.
 * `fixtureOrLive()` tries the endpoint and falls back to the fixture on any
 *   error (with console.warn), so surfaces cannot break under partial backend.
 * `unavailableBreadcrumb(name)` — single-shot dev-only log for adapters whose
 *   endpoint is not exposed under the current v1.1.0-stage4 Backend Feature
 *   Freeze. Emits once per adapter per session.
 */
const BACKEND_URL = (typeof process !== 'undefined' && process.env.REACT_APP_BACKEND_URL) || '';

export const isLiveMode = () => Boolean(BACKEND_URL);

const readToken = () => {
  try { return sessionStorage.getItem('sf-auth-token') || null; } catch { return null; }
};

export const apiFetch = async (path, opts = {}) => {
  if (!BACKEND_URL) throw new Error('fixture-mode');
  const token = readToken();
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${BACKEND_URL}${path}`, { ...opts, headers });
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
    console.warn(`[adapter] live fetch failed for ${endpoint}, falling back to fixture:`, e.message);
    return fixture;
  }
};

// Adapter-unavailability breadcrumbs (single-shot per adapter name).
const _seen = new Set();
export const unavailableBreadcrumb = (adapterName, expectedEndpoint, reason) => {
  if (_seen.has(adapterName)) return;
  _seen.add(adapterName);
  // Not warn-level — this is expected and documented; use info so it doesn't
  // pollute the dev console with fake alarms.
  console.info(
    `[adapter] ${adapterName} · endpoint ${expectedEndpoint} unavailable under Backend Feature Freeze v1.1.0-stage4 · reason: ${reason} · using fixture data.`
  );
};

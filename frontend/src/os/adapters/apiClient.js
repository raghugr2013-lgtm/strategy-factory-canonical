/*
 * apiClient — Sprint 1 M3 · adapters use fixtures unless REACT_APP_BACKEND_URL
 * is populated AND the user is authenticated. When live-mode is on, adapters
 * hit `/api/**` routes on the v1.1.0-stage4 backend.
 * refs DESIGN_FREEZE_v1.0.md §3 (out-of-scope: backend contracts)
 * refs Kickoff Plan §4 · M3 exit gate
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

/**
 * Fixture-or-live gate. If liveMode + endpoint provided, tries the api call
 * and falls back to the fixture on error (with a console.warn). If liveMode
 * is off, immediately returns the fixture.
 */
export const fixtureOrLive = async (endpoint, fixture, opts) => {
  if (!isLiveMode() || !endpoint) return fixture;
  try {
    return await apiFetch(endpoint, opts);
  } catch (e) {
    console.warn(`[adapter] live fetch failed for ${endpoint}, falling back to fixture:`, e.message);
    return fixture;
  }
};

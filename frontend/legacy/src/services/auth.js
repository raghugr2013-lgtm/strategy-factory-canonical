// Auth state management + fetch wrapper for the Strategy Factory UI.
// Stores JWT in localStorage (key: asf_auth_token) and exposes helpers
// used by the AuthGate modal and the Admin Users tab.

const TOKEN_KEY = 'asf_auth_token';
const USER_KEY = 'asf_auth_user';

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function getStoredUser() {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
export function setAuth(token, user) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {/* ignore */}
}
export function clearAuth() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {/* ignore */}
}

function formatErr(detail) {
  if (detail == null) return 'Something went wrong';
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => (e && typeof e.msg === 'string' ? e.msg : JSON.stringify(e)))
      .filter(Boolean).join(' · ');
  }
  if (detail && typeof detail.msg === 'string') return detail.msg;
  return String(detail);
}

// Backend URL resolver mirroring services/api.js
const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8000`
  : (process.env.REACT_APP_BACKEND_URL || '');

// Global fetch interceptor — injects Authorization: Bearer <token>
// on every call to the backend API, so existing services/api.js code
// doesn't need per-call changes. Internal paths (/api/auth/signup and
// /api/auth/login) and non-backend origins are untouched.
let _fetchPatched = false;
export function installAuthFetchInterceptor() {
  if (_fetchPatched || typeof window === 'undefined') return;
  _fetchPatched = true;
  const orig = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      // Match both absolute backend URLs and relative /api/* paths.
      // Many legacy components fetch('/api/...') without prefixing API_URL.
      const isBackendCall =
        (API_URL && url.startsWith(API_URL)) ||
        url.startsWith('/api/');
      const isPublic = url.endsWith('/api/auth/signup') || url.endsWith('/api/auth/login');
      const token = getToken();
      if (isBackendCall && !isPublic && token) {
        const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined) || {});
        if (!headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);
        init = { ...init, headers };
      }
      const res = await orig(input, init);
      // Auto-logout only when a token *existed* (stale-token scenario).
      // Avoids reload-loops before the user has logged in.
      if (res && res.status === 401 && isBackendCall && !isPublic && token) {
        clearAuth();
        if (typeof window !== 'undefined' && !window.__asf_reloading) {
          window.__asf_reloading = true;
          setTimeout(() => window.location.reload(), 50);
        }
      }
      return res;
    } catch (e) {
      return orig(input, init);
    }
  };
}

async function postJson(path, body) {
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatErr(data.detail));
  return data;
}

async function getJson(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatErr(data.detail));
  return data;
}

async function postAuthed(path, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, {
    method: 'POST', headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(formatErr(data.detail));
  return data;
}

// ───────── Public auth helpers ─────────
export async function signup(email, password) {
  return postJson('/api/auth/signup', { email, password });
}
export async function login(email, password) {
  const res = await postJson('/api/auth/login', { email, password });
  setAuth(res.token, res.user);
  return res;
}
export async function fetchMe() {
  return getJson('/api/auth/me');
}
export async function adminListUsers(status) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return getJson(`/api/admin/users${qs}`);
}
export async function adminApproveUser(userId) {
  return postAuthed(`/api/admin/approve/${encodeURIComponent(userId)}`);
}
export async function adminRejectUser(userId) {
  return postAuthed(`/api/admin/reject/${encodeURIComponent(userId)}`);
}
export async function adminReadinessCheck() {
  return getJson('/api/admin/readiness');
}

// Phase 9 — API helpers for Phase 5/7/8 endpoints. Additive; existing
// services/api.js is left untouched.
//
// FIX: every response body is read EXACTLY ONCE via res.text() and then
// JSON.parse'd. Previously this file called res.json() and then fell
// back to res.text() in a catch — which throws
// "Failed to execute 'json' on 'Response': body stream already read"
// because the body stream is already consumed by the first read.
const IS_LOCAL = typeof window !== 'undefined' && (
  window.location.hostname === 'localhost' ||
  window.location.hostname === '127.0.0.1'
);
const API_URL = IS_LOCAL
  ? `http://${window.location.hostname}:8001`
  : process.env.REACT_APP_BACKEND_URL;

async function _jsonOrThrow(res, label) {
  // Read body ONCE as text; parse once.
  const raw = await res.text().catch(() => '');
  let body = null;
  if (raw) {
    try { body = JSON.parse(raw); } catch { body = { raw }; }
  }
  if (!res.ok) {
    const detail = typeof body?.detail === 'string'
      ? body.detail
      : (body?.detail ? JSON.stringify(body.detail) : (body?.raw || `HTTP ${res.status}`));
    const err = new Error(`${label}: ${detail}`);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return body || {};
}

// ── Phase 5 — Auto Factory ──
export const autoFactoryStatus = () =>
  fetch(`${API_URL}/api/auto-factory/status`).then(r => _jsonOrThrow(r, 'auto-factory status'));

export const autoFactoryRun = (body = {}) =>
  fetch(`${API_URL}/api/auto-factory/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ wait: false, ...body }),
  }).then(r => _jsonOrThrow(r, 'auto-factory run'));

export const autoFactorySchedule = (enabled, intervalHours) =>
  fetch(`${API_URL}/api/auto-factory/schedule`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled, interval_hours: intervalHours }),
  }).then(r => _jsonOrThrow(r, 'auto-factory schedule'));

// ── Phase 7 — Portfolio ──
export const portfolioBuild = (params) =>
  fetch(`${API_URL}/api/portfolio/build`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  }).then(r => _jsonOrThrow(r, 'portfolio build'));

export const portfolioStatus = (limit = 10) =>
  fetch(`${API_URL}/api/portfolio/status?limit=${limit}`).then(r => _jsonOrThrow(r, 'portfolio status'));

// ── Phase 8 — Execution ──
export const executionStart = (body) =>
  fetch(`${API_URL}/api/execution/start`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(r => _jsonOrThrow(r, 'execution start'));

export const executionStop = (sessionId, reason = 'manual') =>
  fetch(`${API_URL}/api/execution/stop`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, reason }),
  }).then(r => _jsonOrThrow(r, 'execution stop'));

export const executionEmergencyStop = () =>
  fetch(`${API_URL}/api/execution/emergency-stop`, { method: 'POST' })
    .then(r => _jsonOrThrow(r, 'emergency stop'));

export const executionStatus = () =>
  fetch(`${API_URL}/api/execution/status`).then(r => _jsonOrThrow(r, 'execution status'));

export const executionCbot = (sessionId, strategyId) =>
  fetch(`${API_URL}/api/execution/cbot/${sessionId}/${strategyId}`)
    .then(r => _jsonOrThrow(r, 'execution cbot'));

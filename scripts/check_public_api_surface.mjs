#!/usr/bin/env node
// Outside-in probe of the PUBLIC API surface at regengine.co.
//
// Purpose: the docs once advertised endpoints the public host never served
// (Vercel 404s), and nothing caught it because nothing exercises the surface
// as an outsider. This script asserts, from the outside, that every
// documented-public endpoint answers the way the docs promise — and that
// not-yet-wired paths stay explicitly acknowledged below instead of silently
// drifting.
//
// When wiring new public rewrites (see next.config.js rewrites() and
// CSRF_EXEMPT_PREFIXES in frontend/src/lib/csrf.ts), update EXPECTATIONS in
// the same PR. A backend-served response is JSON; an edge/Vercel miss is HTML.

const EXPECTATIONS = [
  {
    method: 'POST',
    url: 'https://regengine.co/api/v1/webhooks/ingest',
    expect: [401],
    mustBeJson: true,
    note: 'Public webhook ingest: backend auth must answer (401 JSON), never an edge 404/CSRF page.',
  },
  {
    method: 'GET',
    url: 'https://regengine.co/api/health',
    expect: [200],
    mustBeJson: true,
    note: 'Public health endpoint proxied to the backend.',
  },
  {
    method: 'GET',
    url: 'https://regengine.co/docs',
    expect: [200],
    note: 'API docs page.',
  },
  {
    method: 'GET',
    url: 'https://regengine.co/api/v1/records',
    expect: [401],
    mustBeJson: true,
    mustStayOnHost: true,
    note: 'Public read API (records rewrite): backend API-key auth must answer (401 JSON), never an edge 404. Bare path must proxy via the exact rewrite — a redirect here leaks the backend host (FastAPI redirect_slashes on the trailing-slash :path* render).',
  },
  {
    method: 'GET',
    url: 'https://regengine.co/api/v1/fda/export',
    expect: [401],
    mustBeJson: true,
    note: 'Public FDA trace/export API rewrite: backend API-key auth must answer (401 JSON).',
  },
  {
    method: 'POST',
    url: 'https://regengine.co/api/v1/fda/export/verify',
    expect: [401],
    mustBeJson: true,
    note: 'Mutating FDA endpoint must reach the backend (401 JSON), not the CSRF 403 — guards the /api/v1/fda/ entry in CSRF_EXEMPT_PREFIXES.',
  },
];

// Per-request timeout so one hung endpoint cannot stall the probe and CI.
const REQUEST_TIMEOUT_MS = 15000;

async function fetchWithTimeout(url, options) {
  return fetch(url, { ...options, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
}

let failures = 0;
for (const { method, url, expect, mustBeJson, mustStayOnHost, note } of EXPECTATIONS) {
  let status, contentType, finalUrl;
  try {
    const res = await fetchWithTimeout(url, {
      method,
      headers: { 'Content-Type': 'application/json', 'User-Agent': 'regengine-surface-probe' },
      body: method === 'POST' ? '{}' : undefined,
      redirect: 'follow',
    });
    status = res.status;
    contentType = res.headers.get('content-type') || '';
    finalUrl = res.url;
  } catch (err) {
    console.error(`FAIL ${method} ${url} — request error: ${err.message}`);
    failures += 1;
    continue;
  }
  const statusOk = expect.includes(status);
  const jsonOk = !mustBeJson || contentType.includes('application/json');
  // Rewrites must proxy transparently; a followed redirect that lands off
  // regengine.co leaks the backend host to callers.
  const hostOk = !mustStayOnHost || new URL(finalUrl).hostname.endsWith('regengine.co');
  if (statusOk && jsonOk && hostOk) {
    console.log(`ok   ${method} ${url} -> ${status}`);
  } else {
    console.error(`FAIL ${method} ${url} -> ${status} (${contentType}) final=${finalUrl}`);
    console.error(`     expected ${expect.join('/')}${mustBeJson ? ' with application/json' : ''}${mustStayOnHost ? ' staying on regengine.co' : ''} — ${note}`);
    failures += 1;
  }
}

if (failures > 0) {
  console.error(`\npublic-api-surface: ${failures} expectation(s) failed. The public surface has drifted from what the docs promise.`);
  process.exit(1);
}
console.log('public-api-surface: ok');

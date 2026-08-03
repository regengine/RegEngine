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
    expect: [404],
    note: 'NOT publicly wired yet — docs mark the read API "provisioned endpoint" (#2743). When the public rewrite ships (option B), flip this to expect 401 JSON.',
  },
];

let failures = 0;
for (const { method, url, expect, mustBeJson, note } of EXPECTATIONS) {
  let status, contentType;
  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', 'User-Agent': 'regengine-surface-probe' },
      body: method === 'POST' ? '{}' : undefined,
      redirect: 'follow',
    });
    status = res.status;
    contentType = res.headers.get('content-type') || '';
  } catch (err) {
    console.error(`FAIL ${method} ${url} — request error: ${err.message}`);
    failures += 1;
    continue;
  }
  const statusOk = expect.includes(status);
  const jsonOk = !mustBeJson || contentType.includes('application/json');
  if (statusOk && jsonOk) {
    console.log(`ok   ${method} ${url} -> ${status}`);
  } else {
    console.error(`FAIL ${method} ${url} -> ${status} (${contentType})`);
    console.error(`     expected ${expect.join('/')}${mustBeJson ? ' with application/json' : ''} — ${note}`);
    failures += 1;
  }
}

if (failures > 0) {
  console.error(`\npublic-api-surface: ${failures} expectation(s) failed. The public surface has drifted from what the docs promise.`);
  process.exit(1);
}
console.log('public-api-surface: ok');

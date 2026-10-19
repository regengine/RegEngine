import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@/lib/admin-targets', () => ({
  getAdminTargets: () => ['https://admin.regengine.test'],
  shouldRetryAdminProxyResponse: () => false,
}));

import { POST as proxyPost } from '@/app/api/proxy/route';
import { POST as checkoutPost } from '@/app/api/billing/checkout/route';
import { GET as complianceStatusGet } from '@/app/api/v1/compliance/status/[tenantId]/route';
import { GET as snapshotsListGet } from '@/app/api/v1/compliance/snapshots/[tenantId]/route';
import { POST as attestPost } from '@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/attest/route';
import { POST as approvePost } from '@/app/api/review/[id]/approve/route';
import { POST as rejectPost } from '@/app/api/review/[id]/reject/route';
import { POST as contactPost } from '@/app/api/contact/route';
import { POST as clientErrorsPost } from '@/app/api/client-errors/route';
import { DELETE as sessionDelete, GET as sessionGet, POST as sessionPost } from '@/app/api/session/route';
import { POST as toolsVerifyPost } from '@/app/api/tools/verify/route';
import { sanitizePath, validateUuid } from '@/lib/api-proxy';
import { isCsrfExempt, signCsrfToken, verifyCsrfToken } from '@/lib/csrf';

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';
const SNAPSHOT_ID = '33333333-3333-4333-8333-333333333333';
const REVIEW_ID = '44444444-4444-4444-8444-444444444444';

function b64url(value: unknown): string {
  return Buffer.from(JSON.stringify(value)).toString('base64url');
}

function makeJwt(tenantId: string): string {
  const claims = {
    iss: 'regengine-admin',
    aud: 'regengine-api',
    exp: Math.floor(Date.now() / 1000) + 3600,
    tenant_id: tenantId,
  };
  return `${b64url({ alg: 'none', typ: 'JWT' })}.${b64url(claims)}.dummy-signature`;
}

function apiRequest(
  path: string,
  init: {
    method?: string;
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
    body?: unknown;
    rawBody?: string;
  } = {},
): NextRequest {
  const headers = new Headers(init.headers);
  const cookieHeader = Object.entries(init.cookies ?? {})
    .map(([name, value]) => `${name}=${value}`)
    .join('; ');
  if (cookieHeader) headers.set('cookie', cookieHeader);
  if (init.body !== undefined) {
    headers.set('content-type', 'application/json');
  }
  return new NextRequest(`https://regengine.test${path}`, {
    method: init.method ?? 'GET',
    headers,
    body: init.rawBody ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
  });
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

describe('frontend api route hardening', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    process.env.COMPLIANCE_SERVICE_URL = 'https://compliance.regengine.test';
    process.env.CONTACT_WEBHOOK_URL = 'https://hooks.regengine.test/contact';
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.COMPLIANCE_SERVICE_URL;
    delete process.env.CONTACT_WEBHOOK_URL;
    delete process.env.CSRF_SECRET;
  });

  describe('generic proxy SSRF guard', () => {
    it('rejects unauthenticated callers before reading the body', async () => {
      const response = await proxyPost(apiRequest('/api/proxy', {
        method: 'POST',
        body: { url: '/api/v1/things' },
      }));
      expect(response.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it.each([
      ['absolute url', 'https://evil.example/api/v1/things'],
      ['protocol-relative url', '//evil.example/api/v1/things'],
      ['non-api path', '/internal/admin/keys'],
      ['normalized traversal', '/api/../admin/keys'],
      ['scheme in path', '/api/v1/https://evil.example'],
    ])('rejects %s without calling the backend', async (_label, url) => {
      const response = await proxyPost(apiRequest('/api/proxy', {
        method: 'POST',
        cookies: { re_api_key: 'caller-key-1' },
        body: { url },
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects methods outside the allowlist', async () => {
      const response = await proxyPost(apiRequest('/api/proxy', {
        method: 'POST',
        cookies: { re_api_key: 'caller-key-1' },
        body: { url: '/api/v1/things', method: 'trace' },
      }));
      expect(response.status).toBe(405);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('forwards the relative path and injects the cookie api key', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
      const response = await proxyPost(apiRequest('/api/proxy', {
        method: 'POST',
        cookies: { re_api_key: 'caller-key-1' },
        body: { url: '/api/v1/things?page=2', method: 'get' },
      }));
      expect(response.status).toBe(200);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe('http://localhost:8400/api/v1/things?page=2');
      expect(new Headers(init.headers).get('x-regengine-api-key')).toBe('caller-key-1');
    });

    it('refuses upstream redirects without leaking the location', async () => {
      fetchMock.mockResolvedValue(new Response(null, {
        status: 302,
        headers: { location: 'https://evil.example/capture' },
      }));
      const response = await proxyPost(apiRequest('/api/proxy', {
        method: 'POST',
        cookies: { re_api_key: 'caller-key-1' },
        body: { url: '/api/v1/things' },
      }));
      expect(response.status).toBe(502);
      expect(response.headers.get('location')).toBeNull();
      expect(JSON.stringify(await response.json())).not.toContain('evil.example');
    });
  });

  describe('billing checkout (money movement)', () => {
    it('requires plan_id', async () => {
      const response = await checkoutPost(apiRequest('/api/billing/checkout', {
        method: 'POST',
        body: {},
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects a malformed tenant identifier', async () => {
      const response = await checkoutPost(apiRequest('/api/billing/checkout', {
        method: 'POST',
        body: { plan_id: 'plan_pro', tenant_id: 'not-a-uuid' },
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects body tenant that disagrees with the session cookie', async () => {
      const response = await checkoutPost(apiRequest('/api/billing/checkout', {
        method: 'POST',
        cookies: { re_api_key: 'caller-key-1', re_tenant_id: TENANT_A },
        body: { plan_id: 'plan_pro', tenant_id: TENANT_B },
      }));
      expect(response.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('does not downgrade a forged browser api key to anonymous checkout', async () => {
      const response = await checkoutPost(apiRequest('/api/billing/checkout', {
        method: 'POST',
        headers: { origin: 'https://regengine.test', 'x-regengine-api-key': 'forged-key' },
        body: { plan_id: 'plan_pro' },
      }));
      expect(response.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('binds an authenticated checkout to the session tenant', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ checkout_url: 'https://stripe.example/c/1' }));
      const response = await checkoutPost(apiRequest('/api/billing/checkout', {
        method: 'POST',
        cookies: {
          re_api_key: 'caller-key-1',
          re_access_token: makeJwt(TENANT_A),
          re_tenant_id: TENANT_A,
        },
        body: { plan_id: 'plan_pro', tenant_id: TENANT_A },
      }));
      expect(response.status).toBe(200);
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toContain('/api/v1/billing/checkout');
      const sent = JSON.parse(String(init.body));
      expect(sent.tenant_id).toBe(TENANT_A);
      expect(sent.plan_id).toBe('plan_pro');
    });
  });

  describe('tenant isolation on compliance routes', () => {
    function statusGet(tenantId: string, cookies: Record<string, string> = { re_api_key: 'caller-key-1' }) {
      return complianceStatusGet(apiRequest(`/api/v1/compliance/status/${tenantId}`, { cookies }), {
        params: Promise.resolve({ tenantId }),
      });
    }

    it('rejects unauthenticated callers', async () => {
      const response = await statusGet(TENANT_A, {});
      expect(response.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects a non-uuid tenant before any upstream fetch', async () => {
      const response = await statusGet('not-a-uuid');
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects a jwt bound to a different tenant (cross-tenant read)', async () => {
      const response = await complianceStatusGet(
        apiRequest(`/api/v1/compliance/status/${TENANT_B}`, {
          cookies: { re_access_token: makeJwt(TENANT_A) },
        }),
        { params: Promise.resolve({ tenantId: TENANT_B }) },
      );
      expect(response.status).toBe(403);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('proxies a same-tenant read to the tenant-scoped upstream url', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ status: 'compliant' }));
      const response = await complianceStatusGet(
        apiRequest(`/api/v1/compliance/status/${TENANT_A}`, {
          cookies: { re_access_token: makeJwt(TENANT_A) },
        }),
        { params: Promise.resolve({ tenantId: TENANT_A }) },
      );
      expect(response.status).toBe(200);
      const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe(`https://compliance.regengine.test/v1/compliance/status/${TENANT_A}?detailed=false`);
    });

    it('rejects a malformed snapshot tenant before any upstream fetch', async () => {
      const response = await snapshotsListGet(apiRequest('/api/v1/compliance/snapshots/nope', {
        cookies: { re_api_key: 'caller-key-1' },
      }), { params: Promise.resolve({ tenantId: 'nope' }) });
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects attestation with a malformed snapshot identifier', async () => {
      const response = await attestPost(
        apiRequest(`/api/v1/compliance/snapshots/${TENANT_A}/nope/attest`, {
          method: 'POST',
          cookies: { re_api_key: 'caller-key-1' },
          body: { attested_by: 'owner@example.com' },
        }),
        { params: Promise.resolve({ tenantId: TENANT_A, snapshotId: 'nope' }) },
      );
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  describe('review moderation auth', () => {
    it('rejects a non-uuid review id on approve', async () => {
      const response = await approvePost(
        apiRequest('/api/review/nope/approve', { method: 'POST' }),
        { params: Promise.resolve({ id: 'nope' }) },
      );
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects a non-uuid review id on reject', async () => {
      const response = await rejectPost(
        apiRequest('/api/review/nope/reject', { method: 'POST' }),
        { params: Promise.resolve({ id: 'nope' }) },
      );
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects the retired x-admin-key even with a session cookie', async () => {
      const response = await approvePost(
        apiRequest(`/api/review/${REVIEW_ID}/approve`, {
          method: 'POST',
          cookies: { __Host_regengine_session: 'opaque-session' },
          headers: { 'x-admin-key': 'legacy-secret' },
        }),
        { params: Promise.resolve({ id: REVIEW_ID }) },
      );
      expect(response.status).toBe(401);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('passes backend auth failures through without rewriting them', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ detail: 'Unauthorized' }, 401));
      const response = await approvePost(
        apiRequest(`/api/review/${REVIEW_ID}/approve`, { method: 'POST' }),
        { params: Promise.resolve({ id: REVIEW_ID }) },
      );
      expect(response.status).toBe(401);
      expect(await response.json()).toEqual({ error: 'Unauthorized' });
    });
  });

  describe('contact form abuse controls', () => {
    const validPayload = { name: 'Ada', email: 'ada@example.com', message: 'Hello' };

    it('answers honeypot submissions with fake success and no delivery', async () => {
      const response = await contactPost(new Request('https://regengine.test/api/contact', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ ...validPayload, website: 'http://spam.example' }),
      }));
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ ok: true });
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('requires name, email and message', async () => {
      const response = await contactPost(new Request('https://regengine.test/api/contact', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name: 'Ada' }),
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects a malformed email', async () => {
      const response = await contactPost(new Request('https://regengine.test/api/contact', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ ...validPayload, email: 'not-an-email' }),
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('returns 503 when no webhook is configured', async () => {
      delete process.env.CONTACT_WEBHOOK_URL;
      delete process.env.RESEND_API_KEY;
      const response = await contactPost(new Request('https://regengine.test/api/contact', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(validPayload),
      }));
      expect(response.status).toBe(503);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('delivers a valid submission and throttles bursts from one ip', async () => {
      fetchMock.mockResolvedValue(new Response(null, { status: 200 }));
      const send = () => contactPost(new Request('https://regengine.test/api/contact', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-forwarded-for': '203.0.113.71' },
        body: JSON.stringify(validPayload),
      }));
      for (let i = 0; i < 5; i += 1) {
        expect((await send()).status).toBe(200);
      }
      const throttled = await send();
      expect(throttled.status).toBe(429);
      expect(throttled.headers.get('retry-after')).toBe('600');
      expect(fetchMock).toHaveBeenCalledTimes(5);
    });
  });

  describe('client error beacon', () => {
    const beacon = (body: unknown, ip: string) => clientErrorsPost(apiRequest('/api/client-errors', {
      method: 'POST',
      headers: { 'x-forwarded-for': ip },
      rawBody: typeof body === 'string' ? body : JSON.stringify(body),
    }));

    it('drops oversized bodies without logging', async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      try {
        const response = await beacon(`{"message":"${'x'.repeat(9000)}"}`, '198.51.100.11');
        expect(response.status).toBe(204);
        expect(spy).not.toHaveBeenCalled();
      } finally {
        spy.mockRestore();
      }
    });

    it('drops payloads with no message', async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      try {
        const response = await beacon({ kind: 'error' }, '198.51.100.12');
        expect(response.status).toBe(204);
        expect(spy).not.toHaveBeenCalled();
      } finally {
        spy.mockRestore();
      }
    });

    it('strips query strings before writing to logs', async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
      try {
        const response = await beacon(
          { message: 'boom', url: 'https://app.regengine.test/page?token=secret&x=1' },
          '198.51.100.13',
        );
        expect(response.status).toBe(204);
        expect(spy).toHaveBeenCalledTimes(1);
        const logged = String(spy.mock.calls[0][1]);
        expect(logged).not.toContain('token=secret');
        expect(logged).toContain('https://app.regengine.test/page');
      } finally {
        spy.mockRestore();
      }
    });

    it('rate limits a flooding ip', async () => {
      for (let i = 0; i < 10; i += 1) {
        const response = await beacon({ message: `boom-${i}` }, '198.51.100.14');
        expect(response.status).toBe(204);
      }
      const limited = await beacon({ message: 'boom-10' }, '198.51.100.14');
      expect(limited.status).toBe(429);
    });
  });

  describe('session cookie handling', () => {
    it('rejects a tenant assertion that disagrees with the jwt', async () => {
      const response = await sessionPost(apiRequest('/api/session', {
        method: 'POST',
        body: { access_token: makeJwt(TENANT_A), tenant_id: TENANT_B },
      }));
      expect(response.status).toBe(403);
    });

    it('rejects a malformed session token', async () => {
      const response = await sessionPost(apiRequest('/api/session', {
        method: 'POST',
        body: { access_token: 'not-a-jwt' },
      }));
      expect(response.status).toBe(401);
    });

    it('stores credentials in http-only cookies plus the csrf pair', async () => {
      process.env.CSRF_SECRET = 'test-csrf-secret-with-enough-length-123';
      const token = makeJwt(TENANT_A);
      const response = await sessionPost(apiRequest('/api/session', {
        method: 'POST',
        body: { access_token: token, tenant_id: TENANT_A, user: { id: 'u-1' } },
      }));
      expect(response.status).toBe(200);
      expect(response.cookies.get('re_access_token')?.value).toBe(token);
      expect(response.cookies.get('re_access_token')?.httpOnly).toBe(true);
      expect(response.cookies.get('re_tenant_id')?.value).toBe(TENANT_A);
      expect(response.cookies.get('re_tenant_id')?.httpOnly).toBe(false);
      expect(response.cookies.get('re_csrf')?.value).toBeTruthy();
      expect(response.cookies.get('re_csrf_sig')?.value).toBeTruthy();
    });

    it('never exposes raw tokens in the session snapshot', async () => {
      const token = makeJwt(TENANT_A);
      const response = await sessionGet(apiRequest('/api/session', {
        cookies: {
          re_access_token: token,
          re_api_key: 'super-secret-api-key',
          re_tenant_id: TENANT_A,
          re_user: JSON.stringify({ id: 'u-1' }),
        },
      }));
      expect(response.status).toBe(200);
      const data = await response.json();
      expect(data.authenticated).toBe(true);
      expect(data.has_api_key).toBe(true);
      const serialized = JSON.stringify(data);
      expect(serialized).not.toContain(token);
      expect(serialized).not.toContain('super-secret-api-key');
    });

    it('clears every session cookie on logout', async () => {
      fetchMock.mockResolvedValue(new Response(null, { status: 200 }));
      const response = await sessionDelete(apiRequest('/api/session', {
        method: 'DELETE',
        cookies: {
          re_access_token: makeJwt(TENANT_A),
          re_api_key: 'k',
          re_tenant_id: TENANT_A,
          re_user: '{"id":"u-1"}',
          __Host_regengine_session: 'opaque-session',
        },
      }));
      expect(response.status).toBe(200);
      expect(response.cookies.get('re_access_token')?.value).toBe('');
      expect(response.cookies.get('re_api_key')?.value).toBe('');
      expect(response.cookies.get('re_tenant_id')?.value).toBe('');
      expect(response.cookies.get('__Host-regengine_session')?.maxAge).toBe(0);
    });
  });

  describe('tool verification gate', () => {
    it('rejects a null json body with 400 instead of crashing', async () => {
      const response = await toolsVerifyPost(apiRequest('/api/tools/verify', {
        method: 'POST',
        rawBody: 'null',
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('rejects malformed json with 400', async () => {
      const response = await toolsVerifyPost(apiRequest('/api/tools/verify', {
        method: 'POST',
        rawBody: '{not json',
      }));
      expect(response.status).toBe(400);
      expect(fetchMock).not.toHaveBeenCalled();
    });

    it('refuses upstream redirects', async () => {
      fetchMock.mockResolvedValue(new Response(null, {
        status: 302,
        headers: { location: 'https://evil.example/' },
      }));
      const response = await toolsVerifyPost(apiRequest('/api/tools/verify', {
        method: 'POST',
        body: { action: 'verify', email: 'ada@example.com' },
      }));
      expect(response.status).toBe(502);
    });

    it('sets an http-only access cookie on confirmed codes', async () => {
      fetchMock.mockResolvedValue(jsonResponse({ token: 'grant-123' }));
      const response = await toolsVerifyPost(apiRequest('/api/tools/verify', {
        method: 'POST',
        body: { action: 'confirm', email: 'ada@example.com', code: '123456' },
      }));
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual({ status: 'verified' });
      expect(response.cookies.get('re_tool_access')?.value).toBe('grant-123');
      expect(response.cookies.get('re_tool_access')?.httpOnly).toBe(true);
    });
  });

  describe('shared proxy validators', () => {
    it.each([
      ['empty path', []],
      ['dotdot segment', ['api', '..', 'admin']],
      ['space in segment', ['api', 'a b']],
      ['shell metacharacters', ['api', '$(id)']],
      ['null byte', ['api' + String.fromCharCode(0) + 'x']],
    ])('sanitizePath rejects %s', (_label, parts) => {
      expect(sanitizePath(parts as string[])).toBeNull();
    });

    it('sanitizePath accepts a normal service path', () => {
      expect(sanitizePath(['v1', 'admin', 'tenants'])).toBe('v1/admin/tenants');
    });

    it('validateUuid lowercases a valid uuid and rejects the rest', () => {
      expect(validateUuid(TENANT_A.toUpperCase())).toBe(TENANT_A);
      expect(validateUuid('not-a-uuid')).toBeNull();
      expect(validateUuid('')).toBeNull();
      expect(validateUuid(null)).toBeNull();
      expect(validateUuid(undefined)).toBeNull();
      expect(validateUuid('00000000-0000-0000-0000-000000000000')).toBeNull();
    });
  });

  describe('csrf token helpers', () => {
    it('round-trips sign then verify with the configured secret', async () => {
      process.env.CSRF_SECRET = 'test-csrf-secret-with-enough-length-123';
      const token = 'token-abc';
      const signature = await signCsrfToken(token);
      expect(signature).toBeTruthy();
      await expect(verifyCsrfToken(token, signature)).resolves.toBe(true);
      await expect(verifyCsrfToken(token, `${signature}ff`)).resolves.toBe(false);
      await expect(verifyCsrfToken('', signature)).resolves.toBe(false);
    });

    it('scopes exemptions to exact routes and methods', () => {
      expect(isCsrfExempt('/api/tools/verify', 'POST')).toBe(true);
      expect(isCsrfExempt('/api/tools/verify-extra', 'POST')).toBe(false);
      expect(isCsrfExempt('/api/tools/verify', 'GET')).toBe(false);
      expect(isCsrfExempt('/api/session', 'POST')).toBe(false);
    });
  });
});

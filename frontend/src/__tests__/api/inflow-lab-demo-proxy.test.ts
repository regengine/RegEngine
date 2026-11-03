import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
    GET,
    POST,
    __resetInflowLabDemoRateLimitForTests,
    trustedClientIp,
    sanitizePathSegment,
    stripTenantLike,
} from '@/app/api/inflow-lab-demo/[...path]/route';
import { CSRF_HEADER, CSRF_SIG_COOKIE, signCsrfToken } from '@/lib/csrf';
import type { NextRequest } from 'next/server';

function makeRequest({
    method = 'GET',
    url = 'http://localhost/api/inflow-lab-demo/api/healthz',
    headers = {},
    body = '',
    cookies = {} as Record<string, string>,
}: {
    method?: string;
    url?: string;
    headers?: Record<string, string>;
    body?: string;
    cookies?: Record<string, string>;
} = {}): NextRequest {
    const cookieEntries = Object.entries(cookies).map(([name, value]) => ({ name, value }));
    return {
        method,
        headers: new Headers(headers),
        nextUrl: new URL(url),
        cookies: {
            getAll: vi.fn(() => cookieEntries),
            get: vi.fn((name: string) => cookieEntries.find((cookie) => cookie.name === name)),
        },
        text: vi.fn().mockResolvedValue(body),
    } as unknown as NextRequest;
}

async function csrfCookies(token = 'public-csrf-token') {
    const signature = await signCsrfToken(token);
    return {
        token,
        cookies: {
            re_csrf: token,
            [CSRF_SIG_COOKIE]: signature,
        },
        headers: {
            [CSRF_HEADER]: token,
            origin: 'http://localhost',
            'content-type': 'application/json',
        },
    };
}

describe('Inflow Lab public proxy', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        __resetInflowLabDemoRateLimitForTests();
        vi.stubEnv('NODE_ENV', 'test');
        vi.stubEnv('INFLOW_LAB_SERVICE_URL', 'http://inflow.test');
        vi.stubEnv('CSRF_SECRET', 'test-csrf-secret-for-public-proxy');
        vi.stubEnv('INFLOW_LAB_DEMO_RATE_MAX', '100');
        vi.stubEnv('INFLOW_LAB_DEMO_RATE_WINDOW_MS', '60000');
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        __resetInflowLabDemoRateLimitForTests();
    });

    it('allows unauthenticated allowlisted GET healthz without contacting auth', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ ok: true, status: 'healthy' }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/healthz',
                cookies: {},
            }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toEqual({ ok: true, status: 'healthy' });
        expect(mockFetch).toHaveBeenCalledTimes(1);
        expect(String(mockFetch.mock.calls[0][0])).toBe('http://inflow.test/api/healthz');
        const init = mockFetch.mock.calls[0][1] as RequestInit;
        const headers = init.headers as Headers;
        expect(headers.get('cookie')).toBeNull();
        expect(headers.get('authorization')).toBeNull();
        expect(headers.get('x-regengine-tenant')).toBeNull();
        expect(init.credentials).toBe('omit');
    });

    it('forwards allowlisted POST mutations with CSRF and strips tenant_id fields from the body', async () => {
        const csrf = await csrfCookies();
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_USERNAME', 'service-user');
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_PASSWORD', 'service-password');
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ started: true, tenant_id: 'upstream-tenant' }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await POST(
            makeRequest({
                method: 'POST',
                url: 'http://localhost/api/inflow-lab-demo/api/simulate/start',
                headers: csrf.headers,
                cookies: {
                    ...csrf.cookies,
                    __Host_regengine_session: 'opaque-session',
                    re_access_token: 'should-not-forward',
                },
                body: JSON.stringify({
                    config: {
                        source: 'fixture',
                        delivery: { mode: 'local', tenant_id: 'tenant-should-strip', customer_id: 'cust' },
                        tenantId: 'also-strip',
                    },
                }),
            }),
            { params: Promise.resolve({ path: ['api', 'simulate', 'start'] }) },
        );

        expect(response.status).toBe(200);
        // Response tenant fields are stripped before reflection.
        await expect(response.json()).resolves.toEqual({ started: true });
        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [url, init] = mockFetch.mock.calls[0];
        expect(String(url)).toBe('http://inflow.test/api/simulate/start');
        const headers = init.headers as Headers;
        expect(headers.get('authorization')).toMatch(/^Basic /);
        expect(headers.get('cookie')).toBeNull();
        expect(headers.get('x-regengine-tenant')).toBeNull();
        expect(JSON.parse(String(init.body))).toEqual({
            config: {
                source: 'fixture',
                delivery: { mode: 'local' },
            },
        });
    });

    it('strips nested tenant-like keys from proxied JSON responses', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    ok: true,
                    tenant_id: 'should-vanish',
                    delivery: { mode: 'local', tenantId: 'also-vanish', posted: 3 },
                    events: [{ id: 'e1', customer_id: 'c1', lot: 'L1' }],
                }),
                { status: 200, headers: { 'content-type': 'application/json' } },
            ),
        );

        const response = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab-demo/api/events' }),
            { params: Promise.resolve({ path: ['api', 'events'] }) },
        );

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toEqual({
            ok: true,
            delivery: { mode: 'local', posted: 3 },
            events: [{ id: 'e1', lot: 'L1' }],
        });
    });

    it('rejects non-allowlisted paths without contacting upstream', async () => {
        const scenarios = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab-demo/api/scenarios' }),
            { params: Promise.resolve({ path: ['api', 'scenarios'] }) },
        );
        expect(scenarios.status).toBe(404);
        await expect(scenarios.json()).resolves.toMatchObject({ code: 'NOT_ALLOWLISTED' });
        expect(mockFetch).not.toHaveBeenCalled();

        const admin = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab-demo/api/admin/tenants' }),
            { params: Promise.resolve({ path: ['api', 'admin', 'tenants'] }) },
        );
        expect(admin.status).toBe(404);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('allowlists export preview GETs under /api/inflow-lab-demo and streams the body', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response('lot,qty\nL1,10\n', {
                status: 200,
                headers: {
                    'content-type': 'text/csv',
                    'content-disposition': 'attachment; filename="preview.csv"',
                },
            }),
        );

        const response = await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/regengine/export/fda-request?preset=all_records',
            }),
            { params: Promise.resolve({ path: ['api', 'regengine', 'export', 'fda-request'] }) },
        );

        expect(response.status).toBe(200);
        expect(response.headers.get('content-type')).toContain('text/csv');
        expect(await response.text()).toBe('lot,qty\nL1,10\n');
        expect(String(mockFetch.mock.calls[0][0])).toContain(
            'http://inflow.test/api/regengine/export/fda-request',
        );

        mockFetch.mockResolvedValueOnce(
            new Response('<epcis/>', {
                status: 200,
                headers: { 'content-type': 'application/xml' },
            }),
        );
        const epcis = await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/regengine/export/epcis',
            }),
            { params: Promise.resolve({ path: ['api', 'regengine', 'export', 'epcis'] }) },
        );
        expect(epcis.status).toBe(200);
        expect(await epcis.text()).toBe('<epcis/>');
    });

    it('rejects cross-origin requests', async () => {
        const response = await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/healthz',
                headers: { origin: 'https://attacker.example' },
            }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toMatchObject({ code: 'CROSS_ORIGIN' });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('rejects mutations missing CSRF', async () => {
        const response = await POST(
            makeRequest({
                method: 'POST',
                url: 'http://localhost/api/inflow-lab-demo/api/simulate/stop',
                headers: {
                    origin: 'http://localhost',
                    'content-type': 'application/json',
                },
                body: '{}',
            }),
            { params: Promise.resolve({ path: ['api', 'simulate', 'stop'] }) },
        );
        expect(response.status).toBe(403);
        await expect(response.json()).resolves.toMatchObject({ code: 'CSRF_MISSING' });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('does not forward caller Authorization or Cookie headers upstream', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/events?limit=10&tenant_id=nope',
                headers: {
                    authorization: 'Bearer stolen-user-token',
                    cookie: 're_access_token=stolen; __Host-regengine_session=opaque',
                },
            }),
            { params: Promise.resolve({ path: ['api', 'events'] }) },
        );

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [url, init] = mockFetch.mock.calls[0];
        expect(String(url)).toBe('http://inflow.test/api/events?limit=10');
        const headers = init.headers as Headers;
        expect(headers.get('authorization')).toBeNull();
        expect(headers.get('cookie')).toBeNull();
    });

    it('keys the rate limit on trusted platform IP, not client-spoofed XFF', async () => {
        vi.stubEnv('INFLOW_LAB_DEMO_RATE_MAX', '2');
        mockFetch.mockResolvedValue(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const trusted = { 'x-real-ip': '198.51.100.20', 'x-forwarded-for': '203.0.113.1' };
        const first = await GET(
            makeRequest({ headers: trusted }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        const second = await GET(
            makeRequest({ headers: { ...trusted, 'x-forwarded-for': '203.0.113.2' } }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        // Spoofing the left XFF hop must not reset the bucket keyed on x-real-ip.
        const third = await GET(
            makeRequest({ headers: { ...trusted, 'x-forwarded-for': '203.0.113.3' } }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(first.status).toBe(200);
        expect(second.status).toBe(200);
        expect(third.status).toBe(429);
        expect(mockFetch).toHaveBeenCalledTimes(2);

        expect(
            trustedClientIp(
                makeRequest({
                    headers: {
                        'x-forwarded-for': '203.0.113.9, 198.51.100.20',
                        'x-real-ip': '198.51.100.20',
                    },
                }),
            ),
        ).toBe('198.51.100.20');
        expect(
            trustedClientIp(
                makeRequest({
                    headers: { 'x-vercel-forwarded-for': '198.51.100.44, 10.0.0.1' },
                }),
            ),
        ).toBe('198.51.100.44');
        expect(
            trustedClientIp(
                makeRequest({
                    headers: { 'x-forwarded-for': '203.0.113.9, 198.51.100.77' },
                }),
            ),
        ).toBe('198.51.100.77');
    });

    it('rejects encoded traversal and unsafe path IDs before contacting upstream', async () => {
        const cases: Array<{ path: string[]; label: string }> = [
            { path: ['api', 'lineage', '..'], label: 'dotdot' },
            { path: ['api', 'lineage', '%2e%2e'], label: 'encoded-dotdot' },
            { path: ['api', 'lineage', '%2e%2e%2fetc'], label: 'encoded-slash' },
            { path: ['api', 'lineage', '%252e%252e'], label: 'double-encoded' },
            { path: ['api', 'lineage', 'foo%2fbar'], label: 'encoded-slash-mid' },
            { path: ['api', 'lineage', 'foo\\bar'], label: 'backslash' },
            { path: ['api', 'demo-fixtures', '..%2Fsecret', 'load'], label: 'fixture-traversal' },
            { path: ['api', 'lineage', '../secret'], label: 'slash-dotdot' },
        ];

        for (const { path } of cases) {
            mockFetch.mockClear();
            const response = await GET(
                makeRequest({
                    url: `http://localhost/api/inflow-lab-demo/${path.join('/')}`,
                }),
                { params: Promise.resolve({ path }) },
            );
            expect(response.status, path.join('/')).toBe(404);
            expect(mockFetch, path.join('/')).not.toHaveBeenCalled();
        }

        expect(sanitizePathSegment('LOT-001')).toBe('LOT-001');
        expect(sanitizePathSegment('%2e%2e')).toBeNull();
        expect(sanitizePathSegment('%252e%252e')).toBeNull();
        expect(sanitizePathSegment('..\\windows')).toBeNull();
        expect(sanitizePathSegment('a/b')).toBeNull();
        expect(stripTenantLike({ tenant_id: 't', keep: 1 })).toEqual({ keep: 1 });
    });

    it('returns exact 404 in production unless the public proxy flag is enabled', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('REGENGINE_ENABLE_INFLOW_LAB_DEMO_PROXY', '');

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(response.status).toBe(404);
        expect(await response.text()).toBe('');
        expect(mockFetch).not.toHaveBeenCalled();
    });
});

describe('Inflow Lab client export hrefs use the public proxy base', () => {
    it('documents the public base + safe relative export paths', async () => {
        // Mirrors InflowLabClient: INFLOW_API + servicePath + safeHref.
        const INFLOW_API = '/api/inflow-lab-demo';
        function servicePath(path: string) {
            return `${INFLOW_API}${path}`;
        }
        function safeHref(raw: string): string {
            try {
                const parsed = new URL(raw, 'https://regengine.invalid');
                if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
                    return raw.startsWith('/')
                        ? `${parsed.pathname}${parsed.search}${parsed.hash}`
                        : parsed.toString();
                }
            } catch {
                // fall through
            }
            return '#';
        }

        const csv = safeHref(
            servicePath(
                '/api/regengine/export/fda-request?preset=all_records&traceability_lot_code=L1',
            ),
        );
        const epcis = safeHref(
            servicePath('/api/regengine/export/epcis?traceability_lot_code=L1'),
        );

        expect(csv.startsWith('/api/inflow-lab-demo/api/regengine/export/fda-request')).toBe(true);
        expect(epcis.startsWith('/api/inflow-lab-demo/api/regengine/export/epcis')).toBe(true);
        expect(csv.includes('://')).toBe(false);
        expect(epcis.includes('://')).toBe(false);
    });
});

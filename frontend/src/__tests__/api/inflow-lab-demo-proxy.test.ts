import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GET, POST, __resetInflowLabDemoRateLimitForTests } from '@/app/api/inflow-lab-demo/[...path]/route';
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

async function csrfCookies(token = 'demo-csrf-token') {
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

describe('Inflow Lab public demo proxy', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        __resetInflowLabDemoRateLimitForTests();
        vi.stubEnv('NODE_ENV', 'test');
        vi.stubEnv('INFLOW_LAB_SERVICE_URL', 'http://inflow.test');
        vi.stubEnv('CSRF_SECRET', 'test-csrf-secret-for-demo-proxy');
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
                // No session cookies — public demo.
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

    it('forwards allowlisted POST mutations with CSRF and strips tenant_id fields', async () => {
        const csrf = await csrfCookies();
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_USERNAME', 'service-user');
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_PASSWORD', 'service-password');
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ started: true }), {
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
                    // Browser session cookies must never be forwarded upstream.
                    __Host_regengine_session: 'opaque-session',
                    re_access_token: 'should-not-forward',
                },
                body: JSON.stringify({
                    config: {
                        source: 'demo',
                        delivery: { mode: 'local', tenant_id: 'tenant-should-strip', customer_id: 'cust' },
                        tenantId: 'also-strip',
                    },
                }),
            }),
            { params: Promise.resolve({ path: ['api', 'simulate', 'start'] }) },
        );

        expect(response.status).toBe(200);
        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [url, init] = mockFetch.mock.calls[0];
        expect(String(url)).toBe('http://inflow.test/api/simulate/start');
        const headers = init.headers as Headers;
        expect(headers.get('authorization')).toMatch(/^Basic /);
        expect(headers.get('cookie')).toBeNull();
        expect(headers.get('x-regengine-tenant')).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBeNull();
        expect(JSON.parse(String(init.body))).toEqual({
            config: {
                source: 'demo',
                delivery: { mode: 'local' },
            },
        });
    });

    it('rejects non-allowlisted paths without contacting upstream', async () => {
        const response = await GET(
            makeRequest({
                url: 'http://localhost/api/inflow-lab-demo/api/regengine/export/fda-request',
            }),
            { params: Promise.resolve({ path: ['api', 'regengine', 'export', 'fda-request'] }) },
        );
        expect(response.status).toBe(404);
        await expect(response.json()).resolves.toMatchObject({ code: 'NOT_ALLOWLISTED' });
        expect(mockFetch).not.toHaveBeenCalled();

        const scenarios = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab-demo/api/scenarios' }),
            { params: Promise.resolve({ path: ['api', 'scenarios'] }) },
        );
        expect(scenarios.status).toBe(404);
        expect(mockFetch).not.toHaveBeenCalled();
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

    it('trips the per-IP rate limit', async () => {
        vi.stubEnv('INFLOW_LAB_DEMO_RATE_MAX', '2');
        mockFetch.mockResolvedValue(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const first = await GET(
            makeRequest({ headers: { 'x-forwarded-for': '203.0.113.9' } }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        const second = await GET(
            makeRequest({ headers: { 'x-forwarded-for': '203.0.113.9' } }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        const third = await GET(
            makeRequest({ headers: { 'x-forwarded-for': '203.0.113.9' } }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(first.status).toBe(200);
        expect(second.status).toBe(200);
        expect(third.status).toBe(429);
        await expect(third.json()).resolves.toMatchObject({ code: 'RATE_LIMITED' });
        expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    it('returns exact 404 in production unless the demo proxy flag is enabled', async () => {
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

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GET, POST } from '@/app/api/inflow-lab/[...path]/route';
import type { NextRequest } from 'next/server';

function makeRequest({
    method = 'GET',
    url = 'http://localhost/api/inflow-lab/api/healthz',
    headers = {},
    body = '',
    sessionToken = 'opaque-session',
}: {
    method?: string;
    url?: string;
    headers?: Record<string, string>;
    body?: string;
    sessionToken?: string | null;
} = {}): NextRequest {
    const cookies = sessionToken
        ? [{ name: '__Host-regengine_session', value: sessionToken }]
        : [];
    return {
        method,
        headers: new Headers(headers),
        nextUrl: new URL(url),
        cookies: {
            getAll: vi.fn(() => cookies),
            get: vi.fn((name: string) => cookies.find((cookie) => cookie.name === name)),
        },
        text: vi.fn().mockResolvedValue(body),
    } as unknown as NextRequest;
}

describe('Inflow Lab API proxy', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubEnv('NODE_ENV', 'test');
        vi.stubEnv('ADMIN_SERVICE_URL', 'http://admin.test');
        vi.stubEnv('INFLOW_LAB_SERVICE_URL', 'http://inflow.test');
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    function mockSessionThenUpstream(upstream: Response | Error) {
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ tenant_id: '11111111-1111-4111-8111-111111111111' }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );
        if (upstream instanceof Error) {
            mockFetch.mockRejectedValueOnce(upstream);
        } else {
            mockFetch.mockResolvedValueOnce(upstream);
        }
    }

    it('proxies successful GET requests to the configured simulator service', async () => {
        mockSessionThenUpstream(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab/api/healthz?verbose=1' }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(mockFetch).toHaveBeenNthCalledWith(
            2,
            new URL('http://inflow.test/api/healthz?verbose=1'),
            expect.objectContaining({
                method: 'GET',
                cache: 'no-store',
                headers: expect.any(Headers),
            }),
        );
        const upstreamHeaders = mockFetch.mock.calls[1][1]?.headers as Headers;
        expect(upstreamHeaders.get('x-regengine-tenant')).toBe('11111111-1111-4111-8111-111111111111');
        await expect(response.json()).resolves.toEqual({ ok: true });
        expect(response.status).toBe(200);
    });

    it('forwards POST JSON bodies and tenant header on allowed API paths', async () => {
        mockSessionThenUpstream(
            new Response(JSON.stringify({ loaded: true }), {
                status: 202,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await POST(
            makeRequest({
                method: 'POST',
                url: 'http://localhost/api/inflow-lab/api/demo-fixtures/leafy/load',
                headers: {
                    'content-type': 'application/json',
                    'x-regengine-tenant': 'tenant-123',
                },
                body: JSON.stringify({ reset: true }),
            }),
            { params: Promise.resolve({ path: ['api', 'demo-fixtures', 'leafy', 'load'] }) },
        );

        const [, init] = mockFetch.mock.calls[1];
        expect(String(mockFetch.mock.calls[1][0])).toBe('http://inflow.test/api/demo-fixtures/leafy/load');
        expect(init).toMatchObject({ method: 'POST', body: JSON.stringify({ reset: true }) });
        expect((init.headers as Headers).get('content-type')).toBe('application/json');
        expect((init.headers as Headers).get('x-regengine-tenant')).toBe('11111111-1111-4111-8111-111111111111');
        expect(response.status).toBe(202);
        await expect(response.json()).resolves.toEqual({ loaded: true });
    });

    it('returns a quiet offline payload for optional read probes when the simulator service cannot be reached', async () => {
        mockSessionThenUpstream(new Error('ECONNREFUSED'));

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        await expect(response.json()).resolves.toMatchObject({
            ok: true,
            available: false,
            offline: true,
        });
        expect(response.status).toBe(200);
    });

    it('rejects unauthenticated and API-key-only callers before attaching server Basic auth', async () => {
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_USERNAME', 'service-user');
        vi.stubEnv('INFLOW_LAB_BASIC_AUTH_PASSWORD', 'service-password');

        const anonymous = await GET(
            makeRequest({ sessionToken: null }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        expect(anonymous.status).toBe(401);

        const unverifiedApiKey = await GET(
            makeRequest({
                sessionToken: null,
                headers: { 'x-regengine-api-key': 'unverified-caller-value' },
            }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );
        expect(unverifiedApiKey.status).toBe(401);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('fails closed when backend auth/me rejects the opaque session', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ detail: 'invalid' }), {
                status: 401,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(response.status).toBe(401);
        expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('returns exact 404 in production unless the server-only proxy flag is enabled', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('REGENGINE_ENABLE_INFLOW_LAB_PROXY', '');

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(response.status).toBe(404);
        expect(await response.text()).toBe('');
        expect(mockFetch).not.toHaveBeenCalled();
    });
});

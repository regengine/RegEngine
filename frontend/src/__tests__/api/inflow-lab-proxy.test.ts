import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GET, POST } from '@/app/api/inflow-lab/[...path]/route';
import type { NextRequest } from 'next/server';

function makeRequest({
    method = 'GET',
    url = 'http://localhost/api/inflow-lab/api/healthz',
    headers = {},
    body = '',
}: {
    method?: string;
    url?: string;
    headers?: Record<string, string>;
    body?: string;
} = {}): NextRequest {
    return {
        method,
        headers: new Headers(headers),
        nextUrl: new URL(url),
        cookies: {
            getAll: vi.fn(() => []),
            get: vi.fn(() => undefined),
        },
        text: vi.fn().mockResolvedValue(body),
    } as unknown as NextRequest;
}

describe('Inflow Lab API proxy', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubEnv('INFLOW_LAB_SERVICE_URL', 'http://inflow.test');
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it('proxies successful GET requests to the configured simulator service', async () => {
        mockFetch.mockResolvedValueOnce(
            new Response(JSON.stringify({ ok: true }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );

        const response = await GET(
            makeRequest({ url: 'http://localhost/api/inflow-lab/api/healthz?verbose=1' }),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        expect(mockFetch).toHaveBeenCalledWith(
            new URL('http://inflow.test/api/healthz?verbose=1'),
            expect.objectContaining({ method: 'GET', cache: 'no-store' }),
        );
        await expect(response.json()).resolves.toEqual({ ok: true });
        expect(response.status).toBe(200);
    });

    it('forwards POST JSON bodies and tenant header on allowed API paths', async () => {
        mockFetch.mockResolvedValueOnce(
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

        const [, init] = mockFetch.mock.calls[0];
        expect(String(mockFetch.mock.calls[0][0])).toBe('http://inflow.test/api/demo-fixtures/leafy/load');
        expect(init).toMatchObject({ method: 'POST', body: JSON.stringify({ reset: true }) });
        expect((init.headers as Headers).get('content-type')).toBe('application/json');
        expect((init.headers as Headers).get('x-regengine-tenant')).toBe('tenant-123');
        expect(response.status).toBe(202);
        await expect(response.json()).resolves.toEqual({ loaded: true });
    });

    it('returns an unavailable response when the simulator service cannot be reached', async () => {
        mockFetch.mockRejectedValueOnce(new Error('ECONNREFUSED'));

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['api', 'healthz'] }) },
        );

        await expect(response.json()).resolves.toMatchObject({
            error: 'Inflow Lab service unavailable',
        });
        expect(response.status).toBe(502);
    });
});

/**
 * GET /api/session tri-state: the opaque /auth/me lookup must report
 * 'unauthenticated' ONLY on HTTP 401/403. Timeouts, aborts, network errors,
 * and any other non-OK status are indeterminate and must answer 503 with
 * { authenticated: null, status: 'unknown' } — never authenticated:false —
 * so the client keeps its stored profile instead of logging the user out.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GET } from '@/app/api/session/route';
import type { NextRequest } from 'next/server';

function makeRequest({ cookies = {} }: { cookies?: Record<string, string> } = {}): NextRequest {
    return {
        method: 'GET',
        headers: new Headers(),
        nextUrl: new URL('http://localhost/api/session'),
        cookies: {
            getAll: vi.fn(() => Object.entries(cookies).map(([name, value]) => ({ name, value }))),
            get: vi.fn((name: string) =>
                cookies[name] !== undefined ? { name, value: cookies[name] } : undefined,
            ),
        },
        json: vi.fn(),
    } as unknown as NextRequest;
}

describe('GET /api/session opaque lookup tri-state', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', 'https://admin.regengine.test');
        vi.stubEnv('CSRF_SECRET', 'test-secret-for-tristate');
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        vi.unstubAllGlobals();
    });

    it('reports unknown (503) when /auth/me times out', async () => {
        const tenantId = crypto.randomUUID();
        const userId = crypto.randomUUID();
        const storedUser = { id: userId, email: 'owner@example.com' };
        vi.stubGlobal(
            'fetch',
            vi.fn().mockRejectedValue(new DOMException('The operation was aborted', 'AbortError')),
        );

        const response = await GET(
            makeRequest({
                cookies: {
                    '__Host-regengine_session': 'opaque-session-token',
                    re_tenant_id: tenantId,
                    re_user: JSON.stringify(storedUser),
                },
            }),
        );

        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toEqual({
            authenticated: null,
            status: 'unknown',
            has_api_key: false,
            has_credentials: null,
            tenant_id: tenantId,
            auth_method: null,
            user: storedUser,
        });
        // Session cookies are kept, not rewritten or cleared.
        expect(response.cookies.get('re_tenant_id')).toBeUndefined();
        expect(response.cookies.get('re_user')).toBeUndefined();
    });

    it('reports unknown (503) on network error and on 5xx', async () => {
        const fetchMock = vi.fn().mockRejectedValue(new Error('fetch failed'));
        vi.stubGlobal('fetch', fetchMock);

        const networkResponse = await GET(
            makeRequest({ cookies: { '__Host-regengine_session': 'opaque-session-token' } }),
        );
        expect(networkResponse.status).toBe(503);
        await expect(networkResponse.json()).resolves.toEqual(
            expect.objectContaining({ authenticated: null, status: 'unknown' }),
        );

        fetchMock.mockResolvedValue(new Response(null, { status: 502 }));
        const fiveXxResponse = await GET(
            makeRequest({ cookies: { '__Host-regengine_session': 'opaque-session-token' } }),
        );
        expect(fiveXxResponse.status).toBe(503);
        await expect(fiveXxResponse.json()).resolves.toEqual(
            expect.objectContaining({ authenticated: null, status: 'unknown' }),
        );
    });

    it('bounds the whole fallback loop: multiple slow targets return unknown at the overall deadline', async () => {
        const fetchMock = vi.fn().mockImplementation(
            (_url: string, init?: { signal?: AbortSignal }) =>
                // Slow targets: hang until the passed signal aborts.
                new Promise<Response>((_resolve, reject) => {
                    if (init?.signal?.aborted) {
                        reject(new DOMException('The operation was aborted', 'AbortError'));
                        return;
                    }
                    init?.signal?.addEventListener('abort', () => {
                        reject(new DOMException('The operation was aborted', 'AbortError'));
                    });
                }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const startedAt = Date.now();
        const response = await GET(
            makeRequest({ cookies: { '__Host-regengine_session': 'opaque-session-token' } }),
        );
        const elapsedMs = Date.now() - startedAt;

        // Multiple slow targets were attempted, but the whole lookup finished
        // at the ~8s overall deadline — not N x 5s of serialized per-target
        // timeouts — and well before the client's 10s abort.
        expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
        expect(elapsedMs).toBeGreaterThanOrEqual(7000);
        expect(elapsedMs).toBeLessThan(10000);
        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toEqual(
            expect.objectContaining({ authenticated: null, status: 'unknown' }),
        );
    }, 20000);

    it('reports unauthenticated (200, authenticated:false) on HTTP 401', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

        const response = await GET(
            makeRequest({ cookies: { '__Host-regengine_session': 'stale-session-token' } }),
        );

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toEqual({
            authenticated: false,
            has_api_key: false,
            has_credentials: false,
            tenant_id: null,
            auth_method: null,
            user: null,
        });
    });

    it('reports unauthenticated (200, authenticated:false) on HTTP 403', async () => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 403 })));

        const response = await GET(
            makeRequest({ cookies: { '__Host-regengine_session': 'forbidden-session-token' } }),
        );

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toEqual({
            authenticated: false,
            has_api_key: false,
            has_credentials: false,
            tenant_id: null,
            auth_method: null,
            user: null,
        });
    });
});

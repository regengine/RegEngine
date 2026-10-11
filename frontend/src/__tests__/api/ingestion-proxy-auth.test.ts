import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { GET, POST } from '@/app/api/ingestion/[...path]/route';

const TEST_PATH = ['api', 'v1', 'score', 'summary'];
const WRITE_PATH = ['api', 'v1', 'inflow-workbench', 'runs'];
const INGESTION_URL = 'https://ingestion.example.test';
const ADMIN_URL = 'https://admin.example.test';
const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';

function makeRequest(options: {
    method?: string;
    path?: string[];
    query?: string;
    headers?: Record<string, string>;
    cookies?: Record<string, string>;
} = {}): NextRequest {
    const cookies = options.cookies ?? {};
    const path = options.path ?? TEST_PATH;
    return {
        method: options.method ?? 'GET',
        url: `https://regengine.co/api/ingestion/${path.join('/')}${options.query ?? ''}`,
        headers: new Headers(options.headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
        body: null,
        arrayBuffer: async () => new ArrayBuffer(0),
    } as unknown as NextRequest;
}

function authMeResponse(tenantId: string): Response {
    return new Response(JSON.stringify({
        user_id: '33333333-3333-4333-8333-333333333333',
        email: 'owner@example.com',
        organization_id: TENANT_B,
        tenant_id: tenantId,
        role: 'owner',
        auth_method: 'webauthn',
    }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

function calledUrls(mock: ReturnType<typeof vi.fn>): string[] {
    return mock.mock.calls.map(([url]) => String(url));
}

describe('ingestion BFF credential boundary', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubEnv('NEXT_PUBLIC_INGESTION_URL', INGESTION_URL);
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', ADMIN_URL);
        vi.stubEnv('REGENGINE_API_KEY', 'ambient-server-key'); // pragma: allowlist secret
        vi.stubEnv('REGENGINE_API_KEY_TENANT_ID', TENANT_A);
        vi.stubEnv('API_KEY', 'legacy-ambient-key'); // pragma: allowlist secret
        vi.stubEnv('INFLOW_WORKBENCH_READ_API_KEY', 'scoped-inflow-read-key'); // pragma: allowlist secret
        fetchMock.mockReset();
        fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: 'Unauthorized' }), {
            status: 401,
            headers: { 'content-type': 'application/json' },
        }));
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        vi.unstubAllGlobals();
    });

    it.each([
        ['browser-forged API key', {
            headers: {
                origin: 'https://regengine.co',
                'x-regengine-api-key': 'forged-browser-key',
            },
        }],
        ['junk bearer token', {
            headers: { authorization: 'Bearer definitely-not-valid' },
        }],
    ])('never upgrades a %s to the ambient API key', async (_label, options) => {
        const response = await GET!(
            makeRequest(options),
            { params: Promise.resolve({ path: TEST_PATH }) },
        );

        expect(response.status).toBe(401);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [, init] = fetchMock.mock.calls[0];
        const headers = new Headers(init.headers as HeadersInit);
        expect(headers.get('x-regengine-api-key')).toBeNull();
    });

    it('does not upgrade an unsigned JWT and leaves rejection to the upstream verifier', async () => {
        const response = await GET!(
            makeRequest({
                cookies: {
                    re_access_token: 'eyJhbGciOiJub25lIn0.eyJ0ZW5hbnRfaWQiOiJmb3JnZWQifQ.', // pragma: allowlist secret
                },
            }),
            { params: Promise.resolve({ path: TEST_PATH }) },
        );

        expect(response.status).toBe(401);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [, init] = fetchMock.mock.calls[0];
        const headers = new Headers(init.headers as HeadersInit);
        expect(headers.get('x-regengine-api-key')).toBeNull();
    });

    describe('opaque session on non-readiness routes', () => {
        it('rejects an arbitrary opaque cookie at /auth/me without contacting ingestion', async () => {
            const response = await GET!(
                makeRequest({
                    cookies: {
                        '__Host-regengine_session': 'fake-opaque-session',
                        re_tenant_id: TENANT_A,
                    },
                }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(401);
            await expect(response.json()).resolves.toMatchObject({ code: 'SESSION_INVALID' });
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('rejects an expired opaque cookie without contacting ingestion', async () => {
            fetchMock.mockResolvedValue(new Response(null, { status: 403 }));

            const response = await GET!(
                makeRequest({ cookies: { '__Host-regengine_session': 'expired-session' } }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(401);
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('rejects a forged re_tenant_id cookie that does not match the session tenant', async () => {
            fetchMock.mockResolvedValue(authMeResponse(TENANT_A));

            const response = await GET!(
                makeRequest({
                    headers: { origin: 'https://regengine.co' },
                    cookies: {
                        '__Host-regengine_session': 'valid-session',
                        re_tenant_id: TENANT_B,
                    },
                }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(403);
            await expect(response.json()).resolves.toMatchObject({ code: 'TENANT_CONTEXT_MISMATCH' });
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('rejects a caller x-tenant-id header that does not match the session tenant', async () => {
            fetchMock.mockResolvedValue(authMeResponse(TENANT_A));

            const response = await GET!(
                makeRequest({
                    headers: { 'x-tenant-id': TENANT_B },
                    cookies: { '__Host-regengine_session': 'valid-session' },
                }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(403);
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('rejects a tenant_id query parameter that does not match the session tenant', async () => {
            fetchMock.mockResolvedValue(authMeResponse(TENANT_A));

            const response = await GET!(
                makeRequest({
                    query: `?tenant_id=${TENANT_B}`,
                    cookies: { '__Host-regengine_session': 'valid-session' },
                }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(403);
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('forwards a validated session with the server-derived tenant and no server key', async () => {
            fetchMock
                .mockResolvedValueOnce(authMeResponse(TENANT_A))
                .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
                    status: 200,
                    headers: { 'content-type': 'application/json' },
                }));

            const response = await GET!(
                makeRequest({
                    headers: { origin: 'https://regengine.co' },
                    cookies: {
                        '__Host-regengine_session': 'valid-session',
                        re_tenant_id: TENANT_A.toUpperCase(),
                    },
                }),
                { params: Promise.resolve({ path: TEST_PATH }) },
            );

            expect(response.status).toBe(200);
            expect(calledUrls(fetchMock)).toEqual([
                `${ADMIN_URL}/auth/me`,
                `${INGESTION_URL}/${TEST_PATH.join('/')}`,
            ]);
            const [, init] = fetchMock.mock.calls[1];
            const headers = new Headers(init.headers as HeadersInit);
            // Tenant comes from /auth/me, not the client-writable cookie.
            expect(headers.get('x-tenant-id')).toBe(TENANT_A);
            expect(headers.get('x-regengine-api-key')).toBeNull();
            expect(headers.get('authorization')).toBeNull();
        });

        it('refuses a cross-tenant write before contacting ingestion', async () => {
            fetchMock.mockResolvedValue(authMeResponse(TENANT_A));

            const response = await POST!(
                makeRequest({
                    method: 'POST',
                    path: WRITE_PATH,
                    headers: { origin: 'https://regengine.co', 'content-type': 'application/json' },
                    cookies: {
                        '__Host-regengine_session': 'valid-session',
                        re_tenant_id: TENANT_B,
                    },
                }),
                { params: Promise.resolve({ path: WRITE_PATH }) },
            );

            expect(response.status).toBe(403);
            expect(calledUrls(fetchMock)).toEqual([`${ADMIN_URL}/auth/me`]);
        });

        it('forwards x-webhook-signature so signed posts survive the proxy (#3229)', async () => {
            fetchMock
                .mockResolvedValueOnce(authMeResponse(TENANT_A))
                .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
                    status: 200,
                    headers: { 'content-type': 'application/json' },
                }));

            const response = await POST!(
                makeRequest({
                    method: 'POST',
                    path: ['api', 'v1', 'webhooks', 'ingest'],
                    headers: {
                        origin: 'https://regengine.co',
                        'content-type': 'application/json',
                        'x-webhook-signature': 'sha256=deadbeef',
                    },
                    cookies: { '__Host-regengine_session': 'valid-session' },
                }),
                { params: Promise.resolve({ path: ['api', 'v1', 'webhooks', 'ingest'] }) },
            );

            expect(response.status).toBe(200);
            const [, init] = fetchMock.mock.calls[1];
            const headers = new Headers(init.headers as HeadersInit);
            expect(headers.get('x-webhook-signature')).toBe('sha256=deadbeef');
        });

        it('leaves write authorization to the upstream with no server credential attached', async () => {
            fetchMock
                .mockResolvedValueOnce(authMeResponse(TENANT_A))
                .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'Forbidden' }), {
                    status: 403,
                    headers: { 'content-type': 'application/json' },
                }));

            const response = await POST!(
                makeRequest({
                    method: 'POST',
                    path: WRITE_PATH,
                    headers: { origin: 'https://regengine.co', 'content-type': 'application/json' },
                    cookies: { '__Host-regengine_session': 'valid-session' },
                }),
                { params: Promise.resolve({ path: WRITE_PATH }) },
            );

            // A read-only session user gains no write authority at the proxy;
            // the upstream decides with only the caller's own identity.
            expect(response.status).toBe(403);
            const [, init] = fetchMock.mock.calls[1];
            const headers = new Headers(init.headers as HeadersInit);
            expect(headers.get('x-tenant-id')).toBe(TENANT_A);
            expect(headers.get('x-regengine-api-key')).toBeNull();
            expect(headers.get('authorization')).toBeNull();
        });
    });
});

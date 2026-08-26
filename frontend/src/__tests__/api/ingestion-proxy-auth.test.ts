import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { GET } from '@/app/api/ingestion/[...path]/route';

const TEST_PATH = ['api', 'v1', 'score', 'summary'];

function makeRequest(options: {
    headers?: Record<string, string>;
    cookies?: Record<string, string>;
} = {}): NextRequest {
    const cookies = options.cookies ?? {};
    return {
        method: 'GET',
        url: `https://regengine.co/api/ingestion/${TEST_PATH.join('/')}`,
        headers: new Headers(options.headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
        body: null,
    } as unknown as NextRequest;
}

describe('ingestion BFF credential boundary', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubEnv('NEXT_PUBLIC_INGESTION_URL', 'https://ingestion.example.test');
        vi.stubEnv('REGENGINE_API_KEY', 'ambient-server-key'); // pragma: allowlist secret
        vi.stubEnv('REGENGINE_API_KEY_TENANT_ID', '11111111-1111-4111-8111-111111111111');
        vi.stubEnv('API_KEY', 'legacy-ambient-key'); // pragma: allowlist secret
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
        ['fake opaque session', {
            cookies: { '__Host-regengine_session': 'fake-opaque-session' },
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
});

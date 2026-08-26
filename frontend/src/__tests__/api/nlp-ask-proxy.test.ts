/**
 * /api/nlp/ask proxy hardening tests (#2538).
 *
 * This route was the only hand-written proxy that skipped requireProxyAuth /
 * validateProxySession and forwarded caller-supplied credential headers
 * verbatim. It now runs the shared preflight, forwards only caller-owned
 * credentials, and never substitutes an ambient server API key.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { createHmac } from 'node:crypto';
import { POST } from '@/app/api/nlp/ask/route';
import type { NextRequest } from 'next/server';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

const TENANT_A = '11111111-1111-4111-8111-111111111111';

function base64url(value: string): string {
    return Buffer.from(value, 'utf8').toString('base64url');
}

function signToken(payload: Record<string, unknown>): string {
    const claims = { ...payload, exp: Math.floor(Date.now() / 1000) + 3600 };
    const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const body = base64url(JSON.stringify(claims));
    const signature = createHmac('sha256', 'test-material').update(`${header}.${body}`).digest('base64url');
    return `${header}.${body}.${signature}`;
}

function makeRequest(options: {
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
    jsonBody?: unknown;
} = {}): NextRequest {
    const cookies = options.cookies ?? {};
    return {
        url: 'http://localhost/api/nlp/ask',
        headers: new Headers(options.headers ?? {}),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
        json: async () => options.jsonBody ?? { query: 'where did lot 42 ship?' },
    } as unknown as NextRequest;
}

const ORIGINAL = {
    REGENGINE_API_KEY: process.env.REGENGINE_API_KEY,
    REGENGINE_API_KEY_TENANT_ID: process.env.REGENGINE_API_KEY_TENANT_ID,
    NLP_SERVICE_URL: process.env.NLP_SERVICE_URL,
    EXPERIMENTAL: process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES,
};

describe('/api/nlp/ask proxy (#2538)', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', mockFetch);
        process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES = 'true';
        process.env.NLP_SERVICE_URL = 'http://nlp.test';
        process.env.REGENGINE_API_KEY = 'server-side-key';
        process.env.REGENGINE_API_KEY_TENANT_ID = TENANT_A;
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({ answer: 'ok' }),
        } as unknown as Response);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        for (const [k, v] of Object.entries(ORIGINAL)) {
            const key = k === 'EXPERIMENTAL' ? 'NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES' : k;
            if (v === undefined) delete process.env[key];
            else process.env[key] = v;
        }
    });

    it('returns 404 when experimental features are disabled', async () => {
        process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES = 'false';
        const response = await POST(makeRequest());
        expect(response.status).toBe(404);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('rejects an unauthenticated request before any upstream fetch', async () => {
        const response = await POST(makeRequest());
        expect(response.status).toBe(401);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('never upgrades a browser-forged credential to the ambient server key', async () => {
        const token = signToken({ tenant_id: TENANT_A });
        const response = await POST(
            makeRequest({
                cookies: { re_access_token: token, re_tenant_id: TENANT_A },
                headers: {
                    origin: 'http://localhost',
                    'X-RegEngine-API-Key': 'attacker-injected-key',
                    'X-Tenant-ID': '99999999-9999-4999-8999-999999999999',
                    Authorization: 'Bearer attacker-token',
                },
                jsonBody: { query: 'q' },
            }),
        );

        expect(response.status).toBe(200);
        expect(mockFetch).toHaveBeenCalledTimes(1);

        const [, init] = mockFetch.mock.calls[0];
        const sent = new Headers(init.headers as HeadersInit);

        // Browser-provided keys are stripped and the ambient key is never used.
        expect(sent.has('x-regengine-api-key')).toBe(false);
        expect(sent.get('x-regengine-api-key')).not.toBe('attacker-injected-key');

        // Authoritative tenant comes from the cookie, not the injected header.
        expect(sent.get('x-tenant-id')).toBe(TENANT_A);

        // Authorization is rebuilt from the validated cookie token, not the
        // attacker-supplied Bearer value.
        expect(sent.get('authorization')).toBe(`Bearer ${token}`);
        expect(sent.get('authorization')).not.toBe('Bearer attacker-token');
    });

    it.each([
        ['junk bearer', { headers: { authorization: 'Bearer definitely-not-valid' } }],
        ['fake opaque session', { cookies: { '__Host-regengine_session': 'fake-session' } }],
        ['unsigned JWT cookie', {
            cookies: { re_access_token: 'eyJhbGciOiJub25lIn0.eyJ0ZW5hbnRfaWQiOiJmb3JnZWQifQ.' }, // pragma: allowlist secret
        }],
    ])('does not attach the server key for %s', async (_label, requestOptions) => {
        const response = await POST(makeRequest(requestOptions));

        // A malformed JWT is rejected locally. Other opaque credentials are
        // left for the upstream authority, but none receive ambient authority.
        if (response.status === 401) {
            expect(mockFetch).not.toHaveBeenCalled();
            return;
        }

        expect(mockFetch).toHaveBeenCalledTimes(1);
        const [, init] = mockFetch.mock.calls[0];
        const sent = new Headers(init.headers as HeadersInit);
        expect(sent.has('x-regengine-api-key')).toBe(false);
    });
});

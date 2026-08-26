import type { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/billing/checkout/route';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'https://billing.example.test',
}));

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';

function makeRequest(
    body: Record<string, unknown>,
    options: { headers?: Record<string, string>; cookies?: Record<string, string> } = {},
): NextRequest {
    const cookies = options.cookies ?? {};
    return {
        url: 'https://regengine.co/api/billing/checkout',
        method: 'POST',
        headers: new Headers(options.headers),
        json: vi.fn().mockResolvedValue(body),
        cookies: {
            get: vi.fn((name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            }),
            getAll: vi.fn(() => Object.entries(cookies).map(([name, value]) => ({ name, value }))),
        },
    } as unknown as NextRequest;
}

describe('billing checkout route', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ checkout_url: 'https://checkout.stripe.test/cs', session_id: 'cs_test' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            }),
        ));
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it('does not put checkout session IDs in success URL query params', async () => {
        await POST(makeRequest({ plan_id: 'growth&debug=true', billing_period: 'monthly' }));

        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const payload = JSON.parse(fetchMock.mock.calls[0][1].body as string);

        expect(payload.success_url).toBe('https://regengine.co/signup?checkout=success&plan=growth%26debug%3Dtrue');
        expect(payload.success_url).not.toContain('session_id=');
        expect(payload.success_url).not.toContain('{CHECKOUT_SESSION_ID}');
    });

    it('does not inject an environment API key or caller-supplied tenant into public checkout', async () => {
        vi.stubEnv('REGENGINE_API_KEY', 'must-not-be-forwarded'); // pragma: allowlist secret
        vi.stubEnv('REGENGINE_API_KEY_TENANT_ID', TENANT_A);

        const response = await POST(makeRequest({ plan_id: 'growth', tenant_id: TENANT_A }));

        expect(response.status).toBe(200);
        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const init = fetchMock.mock.calls[0][1] as RequestInit;
        const headers = new Headers(init.headers);
        const payload = JSON.parse(init.body as string);
        expect(headers.has('x-regengine-api-key')).toBe(false);
        expect(headers.has('x-tenant-id')).toBe(false);
        expect(payload.tenant_id).toBeUndefined();
    });

    it('attaches signed platform IP metadata and strips raw forwarding headers on Vercel', async () => {
        vi.stubEnv('VERCEL', '1');
        vi.stubEnv('VERCEL_ENV', 'production');
        vi.stubEnv('REGENGINE_PROXY_IP_HMAC_KEY', 'test-proxy-ip-hmac-key-material-32-bytes'); // pragma: allowlist secret

        const response = await POST(makeRequest(
            { plan_id: 'growth' },
            {
                headers: {
                    'x-vercel-forwarded-for': '203.0.113.44',
                    'x-forwarded-for': '192.0.2.10',
                    'x-real-ip': '192.0.2.11',
                    'x-request-id': 'billing-checkout-request',
                },
            },
        ));

        expect(response.status).toBe(200);
        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const headers = new Headers(fetchMock.mock.calls[0][1].headers as HeadersInit);
        expect(headers.has('x-forwarded-for')).toBe(false);
        expect(headers.has('x-real-ip')).toBe(false);
        expect(headers.get('x-regengine-proxy-client-ip')).toBe('203.0.113.44');
        expect(headers.get('x-regengine-proxy-signature')).toMatch(/^v1=[A-Za-z0-9_-]{43}$/);
    });

    it('rejects a tenant assertion that conflicts with the authenticated cookie tenant', async () => {
        const response = await POST(makeRequest(
            { plan_id: 'growth', tenant_id: TENANT_B },
            { cookies: { re_api_key: 'tenant-a-key', re_tenant_id: TENANT_A } }, // pragma: allowlist secret
        ));

        expect(response.status).toBe(403);
        expect(fetch).not.toHaveBeenCalled();
    });

    it('forwards a caller-owned tenant key without replacing it with the env key', async () => {
        vi.stubEnv('REGENGINE_API_KEY', 'different-env-key'); // pragma: allowlist secret
        vi.stubEnv('REGENGINE_API_KEY_TENANT_ID', TENANT_B);

        const response = await POST(makeRequest(
            { plan_id: 'growth', tenant_id: TENANT_A },
            { cookies: { re_api_key: 'tenant-a-key', re_tenant_id: TENANT_A } }, // pragma: allowlist secret
        ));

        expect(response.status).toBe(200);
        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const init = fetchMock.mock.calls[0][1] as RequestInit;
        const headers = new Headers(init.headers);
        expect(headers.get('x-regengine-api-key')).toBe('tenant-a-key');
        expect(headers.get('x-tenant-id')).toBe(TENANT_A);
    });

    it('rejects the retired privileged header even on public checkout', async () => {
        const response = await POST(makeRequest(
            { plan_id: 'growth' },
            { headers: { 'x-admin-key': 'retired-value' } }, // pragma: allowlist secret
        ));

        expect(response.status).toBe(401);
        expect(fetch).not.toHaveBeenCalled();
    });

    it('rejects a browser-forged API key instead of downgrading to anonymous checkout', async () => {
        vi.stubEnv('REGENGINE_API_KEY', 'ambient-server-key'); // pragma: allowlist secret
        const response = await POST(makeRequest(
            { plan_id: 'growth' },
            {
                headers: {
                    origin: 'https://regengine.co',
                    'x-regengine-api-key': 'forged-browser-key',
                },
            },
        ));

        expect(response.status).toBe(401);
        expect(fetch).not.toHaveBeenCalled();
    });

    it('never upgrades an unsigned JWT-shaped cookie to the ambient key', async () => {
        vi.stubEnv('REGENGINE_API_KEY', 'ambient-server-key'); // pragma: allowlist secret
        const response = await POST(makeRequest(
            { plan_id: 'growth' },
            {
                cookies: {
                    re_access_token: 'eyJhbGciOiJub25lIn0.eyJ0ZW5hbnRfaWQiOiJmb3JnZWQifQ.', // pragma: allowlist secret
                },
            },
        ));

        // The backend mock represents the public checkout path; the security
        // assertion is that no tenant key was attached to the request.
        expect(response.status).toBe(200);
        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(new Headers(init.headers).get('x-regengine-api-key')).toBeNull();
    });
});

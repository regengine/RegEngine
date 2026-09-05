import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { GET } from '@/app/api/v1/compliance/status/[tenantId]/route';
import { GET as listSnapshots } from '@/app/api/v1/compliance/snapshots/[tenantId]/route';

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';

describe('tenant-named compliance BFF credential boundary', () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
        vi.stubEnv('COMPLIANCE_SERVICE_URL', 'https://compliance.example.test');
        vi.stubEnv('REGENGINE_API_KEY', 'ambient-server-key'); // pragma: allowlist secret
        vi.stubEnv('REGENGINE_API_KEY_TENANT_ID', TENANT_A);
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

    it('does not upgrade a browser-forged API key to an ambient tenant key', async () => {
        const request = new NextRequest(
            `https://regengine.co/api/v1/compliance/status/${TENANT_A}`,
            {
                headers: {
                    origin: 'https://regengine.co',
                    'x-regengine-api-key': 'forged-browser-key',
                },
            },
        );

        const response = await GET(request, {
            params: Promise.resolve({ tenantId: TENANT_A }),
        });

        expect(response.status).toBe(401);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init.headers);
        expect(headers.get('x-regengine-api-key')).toBeNull();
        expect(headers.get('x-tenant-id')).toBe(TENANT_A);
    });

    for (const [routeName, handler] of [['status', GET], ['snapshots', listSnapshots]] as const) {
        describe(routeName, () => {
            it.each([
                ['cookie', { cookie: 're_api_key=caller-key', origin: 'https://regengine.co' }],
                ['canonical header', { 'x-regengine-api-key': 'caller-key' }],
                ['legacy alias', { 'x-api-key': 'caller-key' }],
            ] as [string, Record<string, string>][])('preserves %s credentials and upstream tenant rejection', async (_name, requestHeaders) => {
                const upstreamError = { detail: { code: 'E_TENANT_MISMATCH' } };
                fetchMock.mockResolvedValue(new Response(JSON.stringify(upstreamError), {
                    status: 409,
                    headers: { 'content-type': 'application/json' },
                }));
                const request = new NextRequest(
                    `https://regengine.co/api/v1/compliance/${routeName}/${TENANT_B}`,
                    { headers: requestHeaders },
                );

                const response = await handler(request, { params: Promise.resolve({ tenantId: TENANT_B }) });

                expect(response.status).toBe(409);
                await expect(response.json()).resolves.toEqual(routeName === 'snapshots'
                    ? { error: upstreamError.detail, items: [] }
                    : upstreamError);
                expect(fetchMock).toHaveBeenCalledTimes(1);
                const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
                expect(url).toContain(`/${routeName}/${TENANT_B}`);
                const headers = new Headers(init.headers);
                expect(headers.get('x-regengine-api-key')).toBe('caller-key');
                expect(headers.get('x-api-key')).toBeNull();
                expect(headers.get('x-tenant-id')).toBe(TENANT_B);
                expect(init.redirect).toBe('manual');
            });

            it('returns an upstream invalid-key rejection without substituting the server key', async () => {
                const request = new NextRequest(
                    `https://regengine.co/api/v1/compliance/${routeName}/${TENANT_A}`,
                    { headers: { 'x-regengine-api-key': 'invalid-caller-key' } },
                );
                const response = await handler(request, { params: Promise.resolve({ tenantId: TENANT_A }) });
                expect(response.status).toBe(401);
                expect(fetchMock).toHaveBeenCalledTimes(1);
                const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
                expect(new Headers(init.headers).get('x-regengine-api-key')).toBe('invalid-caller-key');
            });

            it('rejects a request with no credentials before contacting the backend', async () => {
                const request = new NextRequest(`https://regengine.co/api/v1/compliance/${routeName}/${TENANT_A}`);
                const response = await handler(request, { params: Promise.resolve({ tenantId: TENANT_A }) });
                expect(response.status).toBe(401);
                expect(fetchMock).not.toHaveBeenCalled();
            });
        });
    }
});

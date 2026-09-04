import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { GET } from '@/app/api/v1/compliance/status/[tenantId]/route';

const TENANT_A = '11111111-1111-4111-8111-111111111111';

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
});

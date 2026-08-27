/**
 * #2922 — the FSMA customer-readiness proxies ran with no auth preflight and
 * converted every backend failure (401, 500, network error) into an
 * unconditional 200 "not yet configured for this account" stub, which is the
 * same shape a *healthy* backend returns. A real outage was therefore
 * indistinguishable from an unconfigured account, and the swallowed exception
 * had no error-level log.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as getExportJobs, POST as postExportJobs } from '@/app/api/fsma/customer-readiness/export-jobs/route';
import { GET as getRecallDrills, POST as postRecallDrills } from '@/app/api/fsma/customer-readiness/recall-drills/route';
import type { NextRequest } from 'next/server';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

function makeRequest(cookies: Record<string, string> = {}): NextRequest {
    return {
        method: 'GET',
        url: 'http://localhost/api/fsma/customer-readiness/export-jobs',
        headers: new Headers(),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
    } as unknown as NextRequest;
}

// A plain API-key cookie is enough to clear requireProxyAuth, and
// validateProxySession short-circuits to null for it once Supabase is unset.
const AUTHED = { re_api_key: 'k-123' };

const mockFetch = vi.fn();

describe.each([
    ['export-jobs', getExportJobs, postExportJobs, 'jobs'] as const,
    ['recall-drills', getRecallDrills, postRecallDrills, 'items'] as const,
])('/api/fsma/customer-readiness/%s (#2922)', (name, GET, POST, collectionKey) => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', mockFetch);
        vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', '');
        vi.stubEnv('NEXT_PUBLIC_SUPABASE_ANON_KEY', '');
        vi.stubEnv('INGESTION_SERVICE_URL', 'http://ingestion.test');
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.unstubAllEnvs();
    });

    it('rejects an unauthenticated caller with 401 and issues no upstream request', async () => {
        const response = await GET(makeRequest());
        expect(response.status).toBe(401);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('rejects an unauthenticated POST with 401 instead of the 501 stub', async () => {
        const response = await POST(makeRequest());
        expect(response.status).toBe(401);
    });

    it('propagates a backend 500 as a non-2xx error, not a fake not_connected 200', async () => {
        mockFetch.mockResolvedValue({ ok: false, status: 500, json: async () => ({}) });

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(502);
        const body = await response.json();
        expect(body.code).toBe('E_INGESTION_ERROR');
        expect(body.meta.status).toBe('error');
        expect(body.meta.status).not.toBe('not_connected');
    });

    it('propagates a backend 401 rather than masking it as success', async () => {
        mockFetch.mockResolvedValue({ ok: false, status: 401, json: async () => ({}) });

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(401);
        await expect(response.json()).resolves.toMatchObject({ code: 'E_INGESTION_ERROR' });
    });

    it('propagates a network failure as 502 and logs at error level', async () => {
        const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        mockFetch.mockRejectedValue(new Error('ECONNREFUSED'));

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(502);
        await expect(response.json()).resolves.toMatchObject({
            code: 'E_INGESTION_UNREACHABLE',
        });
        expect(errorSpy).toHaveBeenCalled();
        errorSpy.mockRestore();
    });

    it('returns the not_connected stub only when INGESTION_SERVICE_URL is unset', async () => {
        vi.stubEnv('INGESTION_SERVICE_URL', '');

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(200);
        const body = await response.json();
        expect(body.meta).toMatchObject({ status: 'not_connected', reason: 'unconfigured' });
        expect(body[collectionKey]).toEqual([]);
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('tags an upstream 404 as a distinct not_connected reason', async () => {
        const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
        mockFetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({}) });

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toMatchObject({
            meta: { status: 'not_connected', reason: 'upstream_route_missing' },
        });
        warnSpy.mockRestore();
    });

    it('passes a healthy backend payload straight through', async () => {
        mockFetch.mockResolvedValue({
            ok: true,
            status: 200,
            json: async () => ({ [collectionKey]: [], meta: { status: 'not_connected' } }),
        });

        const response = await GET(makeRequest(AUTHED));

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toMatchObject({
            meta: { status: 'not_connected' },
        });
        expect(mockFetch).toHaveBeenCalledTimes(1);
        expect(mockFetch.mock.calls[0][0]).toContain(`http://ingestion.test/api/v1/fsma/`);
    });

    it('never forwards a client-writable re_tenant_id cookie as the tenant header', async () => {
        mockFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });

        await GET(makeRequest({ ...AUTHED, re_tenant_id: '22222222-2222-4222-8222-222222222222' }));

        const headers = mockFetch.mock.calls[0][1].headers as Record<string, string>;
        expect(headers['X-Tenant-ID']).toBeUndefined();
    });

    it(`names the ${name} route in its upstream URL`, async () => {
        mockFetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
        await GET(makeRequest(AUTHED));
        const url = mockFetch.mock.calls[0][0] as string;
        expect(url).toBe(
            name === 'export-jobs'
                ? 'http://ingestion.test/api/v1/fsma/export-jobs'
                : 'http://ingestion.test/api/v1/fsma/recall/drills',
        );
    });
});

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'https://admin.regengine.test',
}));

vi.mock('@/lib/admin-targets', () => ({
    getAdminTargets: () => ['https://admin.regengine.test'],
    shouldRetryAdminProxyResponse: () => false,
}));

import { GET as proxyAdminGet } from '@/app/api/admin/[...path]/route';
import { GET as proxyReviewGet } from '@/app/api/review/[...path]/route';
import { GET as getReviewItems } from '@/app/api/review/items/route';
import { POST as approveReviewItem } from '@/app/api/review/[id]/approve/route';
import { POST as rejectReviewItem } from '@/app/api/review/[id]/reject/route';

const fetchMock = vi.fn();

function browserRequest(
    url: string,
    method = 'GET',
    options: {
        includeRetiredHeader?: boolean;
        extraHeaders?: Record<string, string>;
    } = {},
): NextRequest {
    return new NextRequest(url, {
        method,
        headers: {
            accept: 'application/json',
            cookie: [
                '__Host-regengine_session=opaque-session-token',
                're_admin_key=retired-browser-secret',
                'unrelated_cookie=must-not-leak',
            ].join('; '),
            origin: 'https://app.regengine.test',
            referer: 'https://app.regengine.test/admin',
            'user-agent': 'RegEngine test browser',
            ...(options.includeRetiredHeader ? { 'x-admin-key': 'retired-header-secret' } : {}),
            'x-csrf-token': 'csrf-token',
            'x-request-id': 'request-123',
            'x-tenant-id': 'tenant-123',
            ...options.extraHeaders,
        },
    });
}

function assertOpaqueSessionOnly(init: RequestInit | undefined): void {
    const headers = new Headers(init?.headers);
    expect(headers.get('cookie')).toBe('__Host-regengine_session=opaque-session-token');
    expect(headers.has('x-admin-key')).toBe(false);
    expect(headers.get('x-csrf-token')).toBe('csrf-token');
    expect(headers.get('x-request-id')).toBe('request-123');
}

describe('privileged frontend session forwarding', () => {
    beforeEach(() => {
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.unstubAllEnvs();
    });

    it('forwards the selected opaque session through the admin catch-all proxy', async () => {
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify([]), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }));

        const response = await proxyAdminGet!(
            browserRequest('https://app.regengine.test/api/admin/v1/admin/keys'),
            { params: Promise.resolve({ path: ['v1', 'admin', 'keys'] }) },
        );

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe('https://admin.regengine.test/v1/admin/keys');
        assertOpaqueSessionOnly(fetchMock.mock.calls[0][1]);
    });

    it('rejects the retired header even when an opaque session is valid', async () => {
        const response = await proxyAdminGet!(
            browserRequest(
                'https://app.regengine.test/api/admin/v1/admin/keys',
                'GET',
                { includeRetiredHeader: true },
            ),
            { params: Promise.resolve({ path: ['v1', 'admin', 'keys'] }) },
        );

        expect(response.status).toBe(401);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('forwards the opaque session when reading the tenant review queue', async () => {
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }));

        const response = await getReviewItems(
            browserRequest('https://app.regengine.test/api/review/items'),
        );

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        assertOpaqueSessionOnly(fetchMock.mock.calls[0][1]);
    });

    it('copies the upstream x-request-id onto review queue error responses', async () => {
        const requestId = crypto.randomUUID();
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'boom' }), {
            status: 500,
            headers: { 'content-type': 'application/json', 'x-request-id': requestId },
        }));

        const response = await getReviewItems(
            browserRequest('https://app.regengine.test/api/review/items'),
        );

        expect(response.status).toBe(500);
        expect(response.headers.get('x-request-id')).toBe(requestId);
        expect(await response.json()).toEqual({ error: 'boom' });
    });

    it('copies the upstream x-request-id onto transformed review queue success responses', async () => {
        const requestId = crypto.randomUUID();
        const reviewId = crypto.randomUUID();
        const docHash = crypto.randomUUID().replace(/-/g, '');
        const confidenceScore = Math.random();
        const createdAt = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
        const updatedAt = new Date(Date.now()).toISOString();
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
            items: [{
                review_id: reviewId,
                doc_hash: docHash,
                confidence_score: confidenceScore,
                created_at: createdAt,
                updated_at: updatedAt,
                status: 'PENDING',
                tenant_id: 'tenant-123',
                text_preview: 'preview text',
                extraction: { lot: 'L1' },
            }],
        }), {
            status: 200,
            headers: { 'content-type': 'application/json', 'x-request-id': requestId },
        }));

        const response = await getReviewItems(
            browserRequest('https://app.regengine.test/api/review/items'),
        );

        expect(response.status).toBe(200);
        expect(response.headers.get('x-request-id')).toBe(requestId);
        expect(await response.json()).toEqual([{
            id: reviewId,
            doc_hash: docHash,
            confidence_score: confidenceScore,
            created_at: createdAt,
            updated_at: updatedAt,
            status: 'PENDING',
            tenant_id: 'tenant-123',
            source_text: 'preview text',
            extracted_data: { lot: 'L1' },
        }]);
    });

    it('sends no reviewer identity or retired credential on a decision', async () => {
        const reviewId = crypto.randomUUID();
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
            status: 'approved',
            review_id: reviewId,
            updated: true,
        }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }));

        const response = await approveReviewItem(
            browserRequest(`https://app.regengine.test/api/review/${reviewId}/approve`, 'POST'),
            { params: Promise.resolve({ id: reviewId }) },
        );

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        assertOpaqueSessionOnly(init);
        expect(init.body).toBe(JSON.stringify({}));
        expect(String(init.body)).not.toContain('reviewer_id');
    });

    it('rejects the retired header on review routes without contacting the backend', async () => {
        const response = await getReviewItems(
            browserRequest(
                'https://app.regengine.test/api/review/items',
                'GET',
                { includeRetiredHeader: true },
            ),
        );

        expect(response.status).toBe(401);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it.each([
        ['admin', async () => proxyAdminGet!(
            browserRequest(
                'https://app.regengine.test/api/admin/v1/admin/keys',
                'GET',
                {
                    extraHeaders: {
                        'x-vercel-forwarded-for': '2001:0db8:0:0:0:0:0:1',
                        'x-forwarded-for': '192.0.2.10',
                        'x-real-ip': '192.0.2.11',
                        'x-regengine-proxy-client-ip': '192.0.2.12',
                        'x-regengine-proxy-timestamp': '1',
                        'x-regengine-proxy-signature': 'v1=attacker',
                    },
                },
            ),
            { params: Promise.resolve({ path: ['v1', 'admin', 'keys'] }) },
        )],
        ['review', async () => getReviewItems(
            browserRequest(
                'https://app.regengine.test/api/review/items',
                'GET',
                {
                    extraHeaders: {
                        'x-vercel-forwarded-for': '2001:0db8:0:0:0:0:0:1',
                        'x-forwarded-for': '192.0.2.10',
                        'x-real-ip': '192.0.2.11',
                        'x-regengine-proxy-client-ip': '192.0.2.12',
                        'x-regengine-proxy-timestamp': '1',
                        'x-regengine-proxy-signature': 'v1=attacker',
                    },
                },
            ),
        )],
        ['review catch-all', async () => proxyReviewGet!(
            browserRequest(
                'https://app.regengine.test/api/review/flagged-extractions',
                'GET',
                {
                    extraHeaders: {
                        'x-vercel-forwarded-for': '2001:0db8:0:0:0:0:0:1',
                        'x-forwarded-for': '192.0.2.10',
                        'x-real-ip': '192.0.2.11',
                        'x-regengine-proxy-client-ip': '192.0.2.12',
                        'x-regengine-proxy-timestamp': '1',
                        'x-regengine-proxy-signature': 'v1=attacker',
                    },
                },
            ),
            { params: Promise.resolve({ path: ['flagged-extractions'] }) },
        )],
        ['review reject', (() => {
            const reviewId = crypto.randomUUID();
            return async () => rejectReviewItem(
                browserRequest(
                    `https://app.regengine.test/api/review/${reviewId}/reject`,
                    'POST',
                    {
                        extraHeaders: {
                            'x-vercel-forwarded-for': '2001:0db8:0:0:0:0:0:1',
                            'x-forwarded-for': '192.0.2.10',
                            'x-real-ip': '192.0.2.11',
                            'x-regengine-proxy-client-ip': '192.0.2.12',
                            'x-regengine-proxy-timestamp': '1',
                            'x-regengine-proxy-signature': 'v1=attacker',
                        },
                    },
                ),
                { params: Promise.resolve({ id: reviewId }) },
            );
        })()],
    ])('attests the platform client IP on the %s privileged proxy', async (_label, invoke) => {
        vi.stubEnv('VERCEL', '1');
        vi.stubEnv('VERCEL_ENV', 'production');
        vi.stubEnv(
            'REGENGINE_PROXY_IP_HMAC_KEY',
            'test-proxy-ip-hmac-key-material-32-bytes', // pragma: allowlist secret
        );
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }));

        const response = await invoke();

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
        expect(headers.has('x-forwarded-for')).toBe(false);
        expect(headers.has('x-real-ip')).toBe(false);
        expect(headers.get('x-regengine-proxy-client-ip')).toBe('2001:db8::1');
        expect(headers.get('x-regengine-proxy-timestamp')).toMatch(/^\d+$/);
        expect(headers.get('x-regengine-proxy-signature')).toMatch(/^v1=[A-Za-z0-9_-]{43}$/);
    });

    it.each([
        ['admin', async () => proxyAdminGet!(
            browserRequest('https://app.regengine.test/api/admin/v1/admin/keys'),
            { params: Promise.resolve({ path: ['v1', 'admin', 'keys'] }) },
        )],
        ['review', async () => getReviewItems(
            browserRequest('https://app.regengine.test/api/review/items'),
        )],
        ['review catch-all', async () => proxyReviewGet!(
            browserRequest('https://app.regengine.test/api/review/flagged-extractions'),
            { params: Promise.resolve({ path: ['flagged-extractions'] }) },
        )],
        ['review reject', (() => {
            const reviewId = crypto.randomUUID();
            return async () => rejectReviewItem(
                browserRequest(`https://app.regengine.test/api/review/${reviewId}/reject`, 'POST'),
                { params: Promise.resolve({ id: reviewId }) },
            );
        })()],
    ])('fails the %s privileged proxy closed when Vercel omits the platform IP', async (_label, invoke) => {
        vi.stubEnv('VERCEL', '1');
        vi.stubEnv('VERCEL_ENV', 'production');
        vi.stubEnv(
            'REGENGINE_PROXY_IP_HMAC_KEY',
            'test-proxy-ip-hmac-key-material-32-bytes', // pragma: allowlist secret
        );

        const response = await invoke();

        expect(response.status).toBe(503);
        expect(fetchMock).not.toHaveBeenCalled();
    });
});

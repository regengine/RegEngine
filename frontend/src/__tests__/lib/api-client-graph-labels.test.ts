/**
 * #2887 — graph label paths must carry the full /api/v1 prefix.
 *
 * graphClient's browser base is the same-origin proxy /api/graph, and
 * src/app/api/graph/[...path]/route.ts:26 forwards the remaining path verbatim:
 *   buildTargetUrl: (path, queryString) => `${GRAPH_URL}/${path}${queryString}`
 *
 * The labels router is mounted at:
 *   services/graph/app/routes.py:55
 *     v1_router.include_router(labels.router, prefix="/labels", tags=["labels"])
 *   server/main.py:910
 *     app.include_router(graph_router, prefix="/api/v1", tags=["Graph Operations"])
 * giving /api/v1/labels/* — with services/graph/app/routers/labels.py:171
 * `@router.get("/health")` and :177 `@router.post("/batch/init")`.
 *
 * The old '/v1/labels/...' paths resolved to /v1/labels/... on the backend,
 * which nothing registers, so both calls 404'd.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => `/api/${service}`,
}));

vi.mock('@/lib/csrf', () => ({
    CSRF_PROTECTED_METHODS: new Set(['POST', 'PUT', 'PATCH', 'DELETE']),
    getCsrfHeaders: () => ({ 'X-CSRF-Token': 'csrf-token' }),
}));

const fetchMock = vi.fn();

function jsonResponse(data: unknown): Response {
    return new Response(JSON.stringify(data), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });
}

async function importFreshClient() {
    vi.resetModules();
    vi.stubGlobal('fetch', fetchMock);
    return import('@/lib/api-client');
}

describe('graph labels endpoints (#2887)', () => {
    beforeEach(() => {
        fetchMock.mockReset();
        vi.unstubAllGlobals();
    });

    it('requests label health at /api/graph/api/v1/labels/health', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({ status: 'healthy' }));

        const { apiClient } = await importFreshClient();
        await apiClient.getLabelsHealth();

        const url = fetchMock.mock.calls[0][0] as string;
        expect(url).toBe('/api/graph/api/v1/labels/health');
        // The proxy forwards everything after /api/graph verbatim, so the
        // backend must see /api/v1/labels/health.
        expect(url.replace('/api/graph', '')).toBe('/api/v1/labels/health');
    });

    it('initializes a label batch at /api/graph/api/v1/labels/batch/init', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({ batch_id: 'b-1', labels: [] }));

        const { apiClient } = await importFreshClient();
        await apiClient.initializeLabelBatch(
            { count: 1 } as unknown as Parameters<typeof apiClient.initializeLabelBatch>[0],
            'tenant-1',
        );

        const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/graph/api/v1/labels/batch/init');
        expect(url.replace('/api/graph', '')).toBe('/api/v1/labels/batch/init');
        expect(init.method).toBe('POST');
        expect((init.headers as Record<string, string>)['X-Tenant-ID']).toBe('tenant-1');
    });

    it('never emits the unregistered bare /v1/labels prefix', async () => {
        // A fresh Response per call — a Response body can only be read once.
        fetchMock.mockImplementation(async () => jsonResponse({}));

        const { apiClient } = await importFreshClient();
        await apiClient.getLabelsHealth();
        await apiClient.initializeLabelBatch(
            { count: 1 } as unknown as Parameters<typeof apiClient.initializeLabelBatch>[0],
        );

        for (const call of fetchMock.mock.calls) {
            expect(call[0]).not.toMatch(/\/api\/graph\/v1\/labels/);
        }
    });
});

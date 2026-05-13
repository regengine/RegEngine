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

describe('apiClient review queue contract', () => {
    beforeEach(() => {
        fetchMock.mockReset();
        vi.unstubAllGlobals();
    });

    it('uses backend pagination and status_filter params and normalizes queue items', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({
            items: [
                {
                    review_id: 'rev-1',
                    confidence_score: 0.42,
                    text_preview: 'Preview text',
                    extraction: { lot: 'LOT-1' },
                    created_at: '2026-05-04T12:00:00.000Z',
                    status: 'pending',
                },
            ],
            total: 1,
            offset: 0,
            limit: 50,
        }));

        const { apiClient } = await importFreshClient();
        const items = await apiClient.getReviewItems('cookie-managed');

        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/v1/admin/review/flagged-extractions?status_filter=PENDING&limit=50',
            expect.objectContaining({
                method: 'GET',
                headers: {},
                credentials: 'include',
            }),
        );
        expect(items).toEqual([
            {
                id: 'rev-1',
                confidence_score: 0.42,
                source_text: 'Preview text',
                extracted_data: { lot: 'LOT-1' },
                status: 'PENDING',
                created_at: '2026-05-04T12:00:00.000Z',
                updated_at: '2026-05-04T12:00:00.000Z',
                tenant_id: '',
            },
        ]);
    });

    it('sends reviewer metadata with approve and reject decisions', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({}))
            .mockResolvedValueOnce(jsonResponse({}));

        const { apiClient } = await importFreshClient();
        await apiClient.approveReviewItem('admin-key', 'rev-1');
        await apiClient.rejectReviewItem('admin-key', 'rev-1');

        expect(fetchMock).toHaveBeenNthCalledWith(
            1,
            '/api/admin/v1/admin/review/flagged-extractions/rev-1/approve',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    'X-Admin-Key': 'admin-key',
                    'X-CSRF-Token': 'csrf-token',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ reviewer_id: 'web-frontend', notes: 'Approved via web interface' }),
            }),
        );
        expect(fetchMock).toHaveBeenNthCalledWith(
            2,
            '/api/admin/v1/admin/review/flagged-extractions/rev-1/reject',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    'X-Admin-Key': 'admin-key',
                    'X-CSRF-Token': 'csrf-token',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ reviewer_id: 'web-frontend', notes: 'Rejected via web interface' }),
            }),
        );
    });

    it('omits X-RegEngine-API-Key for cookie-backed file ingest calls when no apiKey is provided', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({ job_id: 'job-1' }));

        const { apiClient } = await importFreshClient();
        const file = new File(['csv,data'], 'upload.csv', { type: 'text/csv' });
        await apiClient.ingestFile(null, file, 'mobile_capture_pwa_offline');

        const [, init] = fetchMock.mock.calls[0];
        expect(fetchMock.mock.calls[0][0]).toBe('/api/ingestion/api/v1/ingest/csv');
        expect(init).toEqual(expect.objectContaining({
            method: 'POST',
            body: expect.any(FormData),
            credentials: 'include',
        }));
        expect(init.headers).toEqual({ 'X-CSRF-Token': 'csrf-token' });
        expect(init.headers).not.toHaveProperty('X-RegEngine-API-Key');
        expect(init.headers).not.toHaveProperty('Content-Type');
    });

    it('unwraps paginated admin user-management responses', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    { id: 'user-1', email: 'owner@example.com', is_sysadmin: false, status: 'active' },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }))
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    { id: 'role-1', name: 'Viewer', is_system: true },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }))
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    {
                        id: 'invite-1',
                        email: 'pending@example.com',
                        role_id: 'role-1',
                        status: 'pending',
                        created_at: '2026-05-05T00:00:00.000Z',
                        expires_at: '2026-05-12T00:00:00.000Z',
                    },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }));

        const { apiClient } = await importFreshClient();

        await expect(apiClient.getUsers()).resolves.toEqual([
            { id: 'user-1', email: 'owner@example.com', is_sysadmin: false, status: 'active' },
        ]);
        await expect(apiClient.getRoles()).resolves.toEqual([
            { id: 'role-1', name: 'Viewer', is_system: true },
        ]);
        await expect(apiClient.getInvites()).resolves.toEqual([
            {
                id: 'invite-1',
                email: 'pending@example.com',
                role_id: 'role-1',
                status: 'pending',
                created_at: '2026-05-05T00:00:00.000Z',
                expires_at: '2026-05-12T00:00:00.000Z',
            },
        ]);
    });
});

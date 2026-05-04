import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosMock = vi.hoisted(() => {
    const clients: any[] = [];
    return {
        clients,
        create: vi.fn(() => {
            const client = {
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
                get: vi.fn(),
                post: vi.fn(),
                patch: vi.fn(),
                delete: vi.fn(),
            };
            clients.push(client);
            return client;
        }),
    };
});

vi.mock('axios', () => ({
    default: { create: axiosMock.create },
    create: axiosMock.create,
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => `/api/${service}`,
}));

vi.mock('@/lib/csrf', () => ({
    CSRF_PROTECTED_METHODS: new Set(['POST', 'PUT', 'PATCH', 'DELETE']),
    getCsrfHeaders: () => ({ 'X-CSRF-Token': 'csrf-token' }),
}));

describe('apiClient review queue contract', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('uses backend pagination and status_filter params and normalizes queue items', async () => {
        const { apiClient } = await import('@/lib/api-client');
        const adminClient = axiosMock.clients[0];
        adminClient.get.mockResolvedValueOnce({
            data: {
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
            },
        });

        const items = await apiClient.getReviewItems('cookie-managed');

        expect(adminClient.get).toHaveBeenCalledWith('/v1/admin/review/flagged-extractions', {
            params: { status_filter: 'PENDING', limit: 50 },
            headers: {},
        });
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
        const { apiClient } = await import('@/lib/api-client');
        const adminClient = axiosMock.clients[0];
        adminClient.post.mockResolvedValue({ data: {} });

        await apiClient.approveReviewItem('admin-key', 'rev-1');
        await apiClient.rejectReviewItem('admin-key', 'rev-1');

        expect(adminClient.post).toHaveBeenNthCalledWith(
            1,
            '/v1/admin/review/flagged-extractions/rev-1/approve',
            { reviewer_id: 'web-frontend', notes: 'Approved via web interface' },
            { headers: { 'X-Admin-Key': 'admin-key' } },
        );
        expect(adminClient.post).toHaveBeenNthCalledWith(
            2,
            '/v1/admin/review/flagged-extractions/rev-1/reject',
            { reviewer_id: 'web-frontend', notes: 'Rejected via web interface' },
            { headers: { 'X-Admin-Key': 'admin-key' } },
        );
    });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

describe('agent review API hook helpers', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('builds the V1 operator read model URL with safe filters', async () => {
        const { buildAgentReviewItemsUrl } = await import('@/hooks/use-agent-reviews');

        expect(
            buildAgentReviewItemsUrl({
                tenantId: '22222222-2222-4222-8222-222222222222',
                ingestionRunId: '33333333-3333-4333-8333-333333333333',
                reviewStatus: 'pending',
                artifactType: 'validation_explanation',
                createdAfter: '2026-05-01T00:00:00Z',
                createdBefore: '2026-05-13T23:59:59Z',
                limit: 100,
                offset: 20,
            }),
        ).toBe(
            '/api/admin/v1/agent-reviews/items?tenant_id=22222222-2222-4222-8222-222222222222&ingestion_run_id=33333333-3333-4333-8333-333333333333&review_status=pending&artifact_type=validation_explanation&created_after=2026-05-01T00%3A00%3A00Z&created_before=2026-05-13T23%3A59%3A59Z&limit=100&offset=20',
        );
    });

    it('omits all-valued filters and fetches through the admin proxy with cookies', async () => {
        const { fetchAgentReviewItems } = await import('@/hooks/use-agent-reviews');

        fetchWithCsrfMock.mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: [], total: 0, limit: 50, offset: 0 }),
        });

        await expect(fetchAgentReviewItems({ reviewStatus: 'all', artifactType: 'all' })).resolves.toEqual({
            items: [],
            total: 0,
            limit: 50,
            offset: 0,
        });

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/admin/v1/agent-reviews/items?limit=50&offset=0',
            expect.objectContaining({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }),
        );
    });

    it('builds and posts review decisions through the single decision endpoint helper', async () => {
        const { buildAgentReviewDecisionUrl, submitAgentReviewDecision } = await import('@/hooks/use-agent-reviews');

        fetchWithCsrfMock.mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({
                artifact_id: 'artifact-123',
                review_id: 'review-456',
                status: 'accepted',
                reviewed_by: 'operator-789',
                reviewed_at: '2026-05-13T16:00:00Z',
            }),
        });

        expect(buildAgentReviewDecisionUrl('artifact/123')).toBe(
            '/api/admin/v1/agent-reviews/items/artifact%2F123/review',
        );

        await expect(
            submitAgentReviewDecision({
                artifactId: 'artifact-123',
                status: 'accepted',
            }),
        ).resolves.toEqual({
            artifact_id: 'artifact-123',
            review_id: 'review-456',
            review_status: 'accepted',
            reviewed_by: 'operator-789',
            reviewed_at: '2026-05-13T16:00:00Z',
        });

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/admin/v1/agent-reviews/items/artifact-123/review',
            expect.objectContaining({
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'accepted' }),
            }),
        );
    });

    it('surfaces backend detail errors for operator feedback', async () => {
        const { fetchAgentReviewItems } = await import('@/hooks/use-agent-reviews');

        fetchWithCsrfMock.mockResolvedValueOnce({
            ok: false,
            status: 403,
            statusText: 'Forbidden',
            json: async () => ({ detail: 'Tenant mismatch' }),
        });

        await expect(fetchAgentReviewItems()).rejects.toThrow('Tenant mismatch');
    });
});

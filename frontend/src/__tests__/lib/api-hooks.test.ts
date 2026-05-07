import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: fetchWithCsrfMock,
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => (service === 'ingestion' ? '/api/ingestion' : `/api/${service}`),
}));

describe('internal api hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('fetches workbench readiness through the authenticated proxy without tenant_id in the URL', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                score: 92,
                label: 'Ready',
                run_id: 'run-1',
                saved_at: '2026-05-07T00:00:00.000Z',
                unresolved_fix_count: 0,
                export_eligible: true,
                source: 'database',
            }),
        });

        const { fetchWorkbenchReadinessSummary } = await import('@/lib/api-hooks');
        await fetchWorkbenchReadinessSummary('tenant-123', 'cookie-managed');

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/ingestion/api/v1/inflow-workbench/readiness/summary',
            expect.objectContaining({ credentials: 'include' }),
        );
        const [url] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(url).not.toContain('tenant_id=');
    });

    it('creates checkout sessions via the billing proxy without client tenant payload', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                session_id: 'cs_test_123',
                checkout_url: 'https://checkout.stripe.test/session',
                tier: 'growth',
                billing_cycle: 'annual',
                subtotal: '1200',
                credits_applied: null,
                total: '1200',
                sandbox_mode: false,
            }),
        });

        const { createCheckout } = await import('@/lib/api-hooks');
        await createCheckout('cookie-managed', 'growth', 'tenant-123', 'annual');

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/billing/checkout',
            expect.objectContaining({
                method: 'POST',
                credentials: 'include',
            }),
        );
        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(JSON.parse(String(init.body))).toEqual({
            plan_id: 'growth',
            billing_period: 'annual',
        });
    });
});

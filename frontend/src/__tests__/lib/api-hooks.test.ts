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

    it('fetches workbench readiness through the authenticated proxy with explicit tenant context', async () => {
        const tenantId = '11111111-1111-4111-8111-111111111111';
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: tenantId,
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
        await fetchWorkbenchReadinessSummary(tenantId);

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            `/api/ingestion/api/v1/inflow-workbench/readiness/summary?tenant_id=${tenantId}`,
            expect.objectContaining({ credentials: 'include' }),
        );
        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(new Headers(init.headers).get('X-RegEngine-API-Key')).toBeNull();
    });

    it('fetches alerts and compliance score without a browser API-key header', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    tenant_id: 'tenant-123',
                    alerts: [],
                    total: 0,
                    unacknowledged: 0,
                }),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    tenant_id: 'tenant-123',
                    overall_score: 94,
                    grade: 'A',
                }),
            });

        const { fetchAlerts, fetchComplianceScore } = await import('@/lib/api-hooks');
        await fetchAlerts('tenant-123');
        await fetchComplianceScore('tenant-123');

        const [alertsUrl, alertsInit] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(alertsUrl).toBe('/api/ingestion/api/v1/alerts/tenant-123');
        expect(new Headers(alertsInit.headers).get('X-RegEngine-API-Key')).toBeNull();

        const [scoreUrl, scoreInit] = fetchWithCsrfMock.mock.calls[1] as [string, RequestInit];
        expect(scoreUrl).toBe('/api/ingestion/api/v1/compliance/score/tenant-123');
        expect(new Headers(scoreInit.headers).get('X-RegEngine-API-Key')).toBeNull();
    });

    it('attempts a failed POST exactly once so a 500 cannot apply the action twice', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: false,
            status: 500,
            statusText: 'Internal Server Error',
        });

        const { acknowledgeAlert } = await import('@/lib/api-hooks');
        await expect(acknowledgeAlert('tenant-123', null, 'alert-1')).rejects.toThrow('API error: 500');

        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
    });

    it('attempts a POST with a network failure exactly once', async () => {
        fetchWithCsrfMock.mockRejectedValue(new TypeError('fetch failed'));

        const { acknowledgeAlert } = await import('@/lib/api-hooks');
        await expect(acknowledgeAlert('tenant-123', null, 'alert-1')).rejects.toThrow('fetch failed');

        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1);
    });

    it('still retries a failed GET and returns the recovery response', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: false,
                status: 500,
                statusText: 'Internal Server Error',
            })
            .mockResolvedValueOnce({
                ok: true,
                json: async () => ({
                    tenant_id: 'tenant-123',
                    overall_score: 94,
                    grade: 'A',
                }),
            });

        const { fetchComplianceScore } = await import('@/lib/api-hooks');
        const result = await fetchComplianceScore('tenant-123');

        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2);
        expect(result).toEqual({
            tenant_id: 'tenant-123',
            overall_score: 94,
            grade: 'A',
        });
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

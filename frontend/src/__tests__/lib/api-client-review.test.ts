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

function csvResult(statuses: Array<'accepted' | 'rejected'>) {
    return {
        total: statuses.length,
        accepted: statuses.filter(status => status === 'accepted').length,
        rejected: statuses.filter(status => status === 'rejected').length,
        ingestion_timestamp: '2026-08-31T12:00:00+00:00',
        events: statuses.map((status, index) => ({
            traceability_lot_code: `LOT-${index + 1}`,
            cte_type: 'shipping',
            status,
            event_id: status === 'accepted' ? `evt-${index + 1}` : null,
            sha256_hash: status === 'accepted' ? `sha-${index + 1}` : null,
            chain_hash: status === 'accepted' ? `chain-${index + 1}` : null,
            errors: status === 'rejected' ? [`Row ${index + 2}: rejected`] : [],
        })),
    };
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
        const items = await apiClient.getReviewItems();

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

    it('derives reviewer identity server-side and sends no privileged key header', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({}))
            .mockResolvedValueOnce(jsonResponse({}));

        const { apiClient } = await importFreshClient();
        await apiClient.approveReviewItem('rev-1');
        await apiClient.rejectReviewItem('rev-1');

        expect(fetchMock).toHaveBeenNthCalledWith(
            1,
            '/api/admin/v1/admin/review/flagged-extractions/rev-1/approve',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    'X-CSRF-Token': 'csrf-token',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
                credentials: 'include',
            }),
        );
        expect(fetchMock).toHaveBeenNthCalledWith(
            2,
            '/api/admin/v1/admin/review/flagged-extractions/rev-1/reject',
            expect.objectContaining({
                method: 'POST',
                headers: {
                    'X-CSRF-Token': 'csrf-token',
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}),
                credentials: 'include',
            }),
        );

        for (const [, init] of fetchMock.mock.calls) {
            const headers = new Headers(init.headers);
            expect(headers.has('x-admin-key')).toBe(false);
        }
    });

    it('manages tenants and live keys through the opaque browser session contract', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({ key_id: 'key-1', api_key: 'raw-once' }))
            .mockResolvedValueOnce(jsonResponse({
                items: [{
                    id: 'key-1',
                    key_id: 'key-1',
                    name: 'Deploy key',
                    created_at: '2026-08-03T12:00:00Z',
                }],
                total: 1,
                skip: 0,
                limit: 100,
            }))
            .mockResolvedValueOnce(new Response(null, { status: 204 }))
            .mockResolvedValueOnce(jsonResponse({ id: 'tenant-1', name: 'Acme' }));

        const { apiClient } = await importFreshClient();
        await apiClient.createAPIKey({ name: 'Deploy key', tenantId: 'tenant-1' });
        const keys = await apiClient.listAPIKeys();
        await apiClient.revokeAPIKey('key-1');
        await apiClient.createTenant('Acme');

        expect(keys).toEqual([{
            id: 'key-1',
            key_id: 'key-1',
            name: 'Deploy key',
            created_at: '2026-08-03T12:00:00Z',
        }]);

        expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
            '/api/admin/v1/admin/keys',
            '/api/admin/v1/admin/keys',
            '/api/admin/v1/admin/keys/key-1',
            '/api/admin/v1/admin/tenants',
        ]);
        for (const [, init] of fetchMock.mock.calls) {
            const headers = new Headers(init.headers);
            expect(init.credentials).toBe('include');
            expect(headers.has('x-admin-key')).toBe(false);
        }
    });

    it('omits X-RegEngine-API-Key for cookie-backed file ingest calls when no apiKey is provided', async () => {
        const result = csvResult(['accepted']);
        fetchMock.mockResolvedValueOnce(jsonResponse(result));

        const { apiClient } = await importFreshClient();
        const file = new File(['csv,data'], 'upload.csv', { type: 'text/csv' });
        await expect(apiClient.ingestFile(null, file, 'mobile_capture_pwa_offline')).resolves.toEqual(result);

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

    it('fetches sysadmin QA health through the admin proxy', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({
            schema_version: '1.0',
            generated_at: '2026-06-04T00:00:00Z',
            source: { kind: 'ci_artifact', path: 'qa/qa-health/latest.json' },
            overall: { status: 'failing', ready_percent: 28, blocking_count: 3, advisory_count: 1 },
            suites: [],
            clusters: [],
            decision_checks: [],
            artifact_refs: [],
        }));

        const { apiClient } = await importFreshClient();
        await apiClient.getQAHealth();

        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/v1/system/qa-health',
            expect.objectContaining({
                method: 'GET',
                headers: {},
                credentials: 'include',
            }),
        );
    });

    it.each([
        [400, { message: 'No valid rows found', errors: ['Row 2: No CTE type'] }, 'No valid rows found: Row 2: No CTE type'],
        [400, 'CSV contained no data rows', 'CSV contained no data rows'],
        [422, [{ loc: ['body', 'file'], msg: 'Field required', type: 'missing' }], 'Field required'],
        [401, 'Authentication required', 'Authentication required'],
        [403, 'Tenant mismatch', 'Tenant mismatch'],
        [500, { unexpected: { value: 'not a display message' } }, 'Request failed'],
    ])('normalizes CSV failure status %i without losing the HTTP response', async (status, detail, message) => {
        fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail }), {
            status,
            headers: { 'Content-Type': 'application/json' },
        }));
        const { apiClient } = await importFreshClient();
        await expect(apiClient.ingestFile(null, new File([''], 'events.csv'))).rejects.toMatchObject({
            message,
            response: { status, data: { detail } },
        });
    });

    it.each([
        { job_id: 'legacy-job-1' },
        { total: 2, accepted: 2, rejected: 1, events: [] },
        { total: 1, accepted: -1, rejected: 2, events: [] },
        { total: 1, accepted: 0, rejected: 1, events: [null] },
        { total: 1, accepted: 0, rejected: 1, events: [{ status: 'rejected', errors: [{}] }] },
        { total: 1, accepted: 1, rejected: 0, events: [], kde_warnings: { message: 'not an array' } },
    ])('rejects a CSV response without trustworthy counts: %j', async (result) => {
        fetchMock.mockResolvedValueOnce(jsonResponse(result));
        const { apiClient } = await importFreshClient();
        await expect(apiClient.ingestFile(null, new File([''], 'events.csv'))).rejects.toThrow('Unexpected CSV ingestion response');
    });

    it('preserves the selected tenant and CSV source without fabricating a job', async () => {
        const result = csvResult(['rejected', 'rejected']);
        fetchMock.mockResolvedValueOnce(jsonResponse(result));
        const { apiClient } = await importFreshClient();
        apiClient.setCurrentTenant('tenant-123');
        await expect(apiClient.ingestFile('cookie-managed', new File([''], 'events.csv'), 'fsma', 'shipping')).resolves.toEqual(result);
        const [, init] = fetchMock.mock.calls[0];
        expect(init.headers).toEqual({ 'X-CSRF-Token': 'csrf-token', 'X-Tenant-ID': 'tenant-123' });
        expect(init.body.get('source')).toBe('fsma');
        expect(init.body.get('cte_type')).toBe('shipping');
        expect(init.body.has('tenant_id')).toBe(false);
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

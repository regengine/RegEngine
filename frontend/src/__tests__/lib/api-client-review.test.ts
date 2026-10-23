import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => `/api/${service}`,
}));

vi.mock('@/lib/csrf', () => ({
    CSRF_PROTECTED_METHODS: new Set(['POST', 'PUT', 'PATCH', 'DELETE']),
    getCsrfHeaders: () => ({ 'X-CSRF-Token': 'csrf-token' }),
}));

// Runtime-relative timestamps (no fixed calendar dates); order and gaps match the
// original fixtures, and invites still expire 7 days after creation.
const DAY_MS = 24 * 60 * 60 * 1000;
const NOW_MS = Date.now();
const INGESTED_AT = new Date(NOW_MS - DAY_MS).toISOString();
const KEY_CREATED_AT = new Date(NOW_MS - 29 * DAY_MS).toISOString();
const INVITE_CREATED_AT = new Date(NOW_MS - 119.5 * DAY_MS).toISOString();
const INVITE_EXPIRES_AT = new Date(NOW_MS - 119.5 * DAY_MS + 7 * DAY_MS).toISOString();
const REVIEW_CREATED_AT = new Date(NOW_MS - 120 * DAY_MS).toISOString();

// Runtime-generated identifiers and text (no invented names, emails or IDs).
// Each expected value reuses the same constant as its input.
const uid = () => crypto.randomUUID();
const REVIEW_ID = uid();
const REVIEW_PREVIEW_TEXT = uid();
const REVIEW_LOT_CODE = uid();
const KEY_ID = uid();
const KEY_NAME = uid();
const RAW_API_KEY = uid();
const TENANT_ID = uid();
const TENANT_NAME = uid();
const SELECTED_TENANT_ID = uid();
const LEGACY_JOB_ID = uid();
const EVENT_ID = uid();
const USER_ID = uid();
const ROLE_ID = uid();
const INVITE_ID = uid();
// .invalid is a reserved TLD (RFC 2606), so these can never be real addresses.
const USER_EMAIL = `${uid()}@example.invalid`;
const INVITE_EMAIL = `${uid()}@example.invalid`;
// Real system role label from services/ingestion/app/team_mgmt.py ("viewer" -> "Viewer").
const SYSTEM_ROLE_NAME = 'Viewer';

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
        ingestion_timestamp: INGESTED_AT,
        events: statuses.map((status, index) => ({
            traceability_lot_code: uid(),
            cte_type: 'shipping',
            status,
            event_id: status === 'accepted' ? uid() : null,
            sha256_hash: status === 'accepted' ? 'a'.repeat(64) : null,
            chain_hash: status === 'accepted' ? 'b'.repeat(64) : null,
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
                    review_id: REVIEW_ID,
                    confidence_score: 0.42,
                    text_preview: REVIEW_PREVIEW_TEXT,
                    extraction: { lot: REVIEW_LOT_CODE },
                    created_at: REVIEW_CREATED_AT,
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
                id: REVIEW_ID,
                confidence_score: 0.42,
                source_text: REVIEW_PREVIEW_TEXT,
                extracted_data: { lot: REVIEW_LOT_CODE },
                status: 'PENDING',
                created_at: REVIEW_CREATED_AT,
                updated_at: REVIEW_CREATED_AT,
                tenant_id: '',
            },
        ]);
    });

    it('derives reviewer identity server-side and sends no privileged key header', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({}))
            .mockResolvedValueOnce(jsonResponse({}));

        const { apiClient } = await importFreshClient();
        await apiClient.approveReviewItem(REVIEW_ID);
        await apiClient.rejectReviewItem(REVIEW_ID);

        expect(fetchMock).toHaveBeenNthCalledWith(
            1,
            `/api/admin/v1/admin/review/flagged-extractions/${REVIEW_ID}/approve`,
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
            `/api/admin/v1/admin/review/flagged-extractions/${REVIEW_ID}/reject`,
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
            .mockResolvedValueOnce(jsonResponse({ key_id: KEY_ID, api_key: RAW_API_KEY }))
            .mockResolvedValueOnce(jsonResponse({
                items: [{
                    id: KEY_ID,
                    key_id: KEY_ID,
                    name: KEY_NAME,
                    created_at: KEY_CREATED_AT,
                }],
                total: 1,
                skip: 0,
                limit: 100,
            }))
            .mockResolvedValueOnce(new Response(null, { status: 204 }))
            .mockResolvedValueOnce(jsonResponse({ id: TENANT_ID, name: TENANT_NAME }));

        const { apiClient } = await importFreshClient();
        await apiClient.createAPIKey({ name: KEY_NAME, tenantId: TENANT_ID });
        const keys = await apiClient.listAPIKeys();
        await apiClient.revokeAPIKey(KEY_ID);
        await apiClient.createTenant(TENANT_NAME);

        expect(keys).toEqual([{
            id: KEY_ID,
            key_id: KEY_ID,
            name: KEY_NAME,
            created_at: KEY_CREATED_AT,
        }]);

        expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
            '/api/admin/v1/admin/keys',
            '/api/admin/v1/admin/keys',
            `/api/admin/v1/admin/keys/${KEY_ID}`,
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
            generated_at: '',
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
        { job_id: LEGACY_JOB_ID },
        { total: 2, accepted: 2, rejected: 1, events: [] },
        { total: 1, accepted: -1, rejected: 2, events: [] },
        { total: 1, accepted: 0, rejected: 1, events: [null] },
        { total: 1, accepted: 0, rejected: 1, events: [{ status: 'rejected', errors: [{}] }] },
        { total: 1, accepted: 1, rejected: 0, events: [], kde_warnings: { message: 'not an array' } },
        {
            total: 1,
            accepted: 1,
            rejected: 0,
            ingestion_timestamp: INGESTED_AT,
            events: [{
                traceability_lot_code: uid(), cte_type: 'shipping', status: 'accepted',
                event_id: '', sha256_hash: 'a'.repeat(64), chain_hash: 'b'.repeat(64), errors: [],
            }],
        },
        {
            total: 1,
            accepted: 1,
            rejected: 0,
            ingestion_timestamp: INGESTED_AT,
            events: [{
                traceability_lot_code: uid(), cte_type: 'shipping', status: 'accepted',
                event_id: EVENT_ID, sha256_hash: 'not-a-hash', chain_hash: 'b'.repeat(64), errors: [],
            }],
        },
        {
            total: 1,
            accepted: 1,
            rejected: 0,
            ingestion_timestamp: INGESTED_AT,
            events: [{
                traceability_lot_code: uid(), cte_type: 'shipping', status: 'accepted',
                event_id: EVENT_ID, sha256_hash: 'a'.repeat(64), chain_hash: 'b'.repeat(64),
                errors: ['persistence warning'],
            }],
        },
    ])('rejects a CSV response without trustworthy counts: %j', async (result) => {
        fetchMock.mockResolvedValueOnce(jsonResponse(result));
        const { apiClient } = await importFreshClient();
        await expect(apiClient.ingestFile(null, new File([''], 'events.csv'))).rejects.toThrow('Unexpected CSV ingestion response');
    });

    it('preserves the selected tenant and CSV source without fabricating a job', async () => {
        const result = csvResult(['rejected', 'rejected']);
        fetchMock.mockResolvedValueOnce(jsonResponse(result));
        const { apiClient } = await importFreshClient();
        apiClient.setCurrentTenant(SELECTED_TENANT_ID);
        await expect(apiClient.ingestFile('cookie-managed', new File([''], 'events.csv'), 'fsma', 'shipping')).resolves.toEqual(result);
        const [, init] = fetchMock.mock.calls[0];
        expect(init.headers).toEqual({ 'X-CSRF-Token': 'csrf-token', 'X-Tenant-ID': SELECTED_TENANT_ID });
        expect(init.body.get('source')).toBe('fsma');
        expect(init.body.get('cte_type')).toBe('shipping');
        expect(init.body.has('tenant_id')).toBe(false);
    });

    it('unwraps paginated admin user-management responses', async () => {
        fetchMock
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    { id: USER_ID, email: USER_EMAIL, is_sysadmin: false, status: 'active' },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }))
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    { id: ROLE_ID, name: SYSTEM_ROLE_NAME, is_system: true },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }))
            .mockResolvedValueOnce(jsonResponse({
                items: [
                    {
                        id: INVITE_ID,
                        email: INVITE_EMAIL,
                        role_id: ROLE_ID,
                        status: 'pending',
                        created_at: INVITE_CREATED_AT,
                        expires_at: INVITE_EXPIRES_AT,
                    },
                ],
                total: 1,
                skip: 0,
                limit: 20,
            }));

        const { apiClient } = await importFreshClient();

        await expect(apiClient.getUsers()).resolves.toEqual([
            { id: USER_ID, email: USER_EMAIL, is_sysadmin: false, status: 'active' },
        ]);
        await expect(apiClient.getRoles()).resolves.toEqual([
            { id: ROLE_ID, name: SYSTEM_ROLE_NAME, is_system: true },
        ]);
        await expect(apiClient.getInvites()).resolves.toEqual([
            {
                id: INVITE_ID,
                email: INVITE_EMAIL,
                role_id: ROLE_ID,
                status: 'pending',
                created_at: INVITE_CREATED_AT,
                expires_at: INVITE_EXPIRES_AT,
            },
        ]);
    });
});

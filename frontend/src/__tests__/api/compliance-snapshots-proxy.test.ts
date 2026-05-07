import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET as listSnapshots, POST as createSnapshot } from '@/app/api/v1/compliance/snapshots/[tenantId]/route';
import { GET as verifySnapshot } from '@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/verify/route';
import { GET as getFdaResponse } from '@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/fda-response/route';
import { GET as getAuditPack } from '@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/audit-pack/route';
import { POST as refreezeSnapshot } from '@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/refreeze/route';
import { GET as diffSnapshots } from '@/app/api/v1/compliance/snapshots/[tenantId]/diff/route';
import { _resetDevComplianceSnapshotsForTesting } from '@/lib/dev-compliance-snapshots';
import type { NextRequest } from 'next/server';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'http://compliance.test',
}));

const {
    mockRequireProxyAuth,
    mockValidateProxySession,
    mockGetServerApiKey,
} = vi.hoisted(() => ({
    mockRequireProxyAuth: vi.fn(() => null),
    mockValidateProxySession: vi.fn(async () => null),
    mockGetServerApiKey: vi.fn(() => null),
}));

vi.mock('@/lib/api-proxy', async () => {
    const actual = await vi.importActual<typeof import('@/lib/api-proxy')>('@/lib/api-proxy');
    return {
        ...actual,
        requireProxyAuth: mockRequireProxyAuth,
        validateProxySession: mockValidateProxySession,
        getServerApiKey: mockGetServerApiKey,
    };
});

const TENANT_ID = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';

function makeRequest({
    method = 'GET',
    url = 'http://localhost/api/v1/compliance/snapshots',
    headers = {},
    body,
}: {
    method?: string;
    url?: string;
    headers?: Record<string, string>;
    body?: Record<string, unknown>;
} = {}): NextRequest {
    const textBody = body ? JSON.stringify(body) : '';
    return {
        method,
        url,
        headers: new Headers(headers),
        cookies: {
            getAll: vi.fn(() => []),
            get: vi.fn(() => undefined),
        },
        json: vi.fn().mockResolvedValue(body ?? {}),
        text: vi.fn().mockResolvedValue(textBody),
    } as unknown as NextRequest;
}

async function createFallbackSnapshot(name: string, reason?: string) {
    const response = await createSnapshot(
        makeRequest({
            method: 'POST',
            url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}`,
            headers: { 'content-type': 'application/json' },
            body: {
                snapshot_name: name,
                snapshot_reason: reason,
                created_by: 'playwright@regengine.local',
            },
        }),
        { params: Promise.resolve({ tenantId: TENANT_ID }) },
    );
    expect(response.status).toBe(200);
    return response.json();
}

describe('Compliance snapshot proxy routes', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        _resetDevComplianceSnapshotsForTesting();
        vi.stubEnv('NODE_ENV', 'development');
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        vi.unstubAllGlobals();
    });

    it('creates and lists fallback snapshots when the compliance service is unreachable', async () => {
        mockFetch.mockRejectedValue(new Error('ECONNREFUSED'));

        const created = await createFallbackSnapshot('Manual Freeze', 'Local dev fallback');
        expect(created).toMatchObject({
            tenant_id: TENANT_ID,
            snapshot_name: 'Manual Freeze',
            snapshot_reason: 'Local dev fallback',
            created_by: 'playwright@regengine.local',
        });

        const response = await listSnapshots(
            makeRequest({
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}`,
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID }) },
        );

        expect(response.status).toBe(200);
        await expect(response.json()).resolves.toMatchObject({
            items: [
                expect.objectContaining({
                    id: created.id,
                    snapshot_name: 'Manual Freeze',
                }),
            ],
        });
    });

    it('supports verify, diff, FDA response, audit pack, and refreeze via the fallback store', async () => {
        mockFetch.mockRejectedValue(new Error('backend unavailable'));

        const older = await createFallbackSnapshot('Snapshot A', 'First run');
        const newer = await createFallbackSnapshot('Snapshot B', 'Second run');

        const verifyResponse = await verifySnapshot(
            makeRequest({
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${older.id}/verify?verified_by=tester%40regengine.local`,
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: older.id }) },
        );
        await expect(verifyResponse.json()).resolves.toMatchObject({
            is_valid: true,
            hash_match: true,
            verified_by: 'tester@regengine.local',
        });

        const diffResponse = await diffSnapshots(
            makeRequest({
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/diff?snapshot_a=${older.id}&snapshot_b=${newer.id}`,
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID }) },
        );
        await expect(diffResponse.json()).resolves.toMatchObject({
            snapshot_a: { name: 'Snapshot A' },
            snapshot_b: { name: 'Snapshot B' },
            changes: expect.arrayContaining([
                expect.objectContaining({ label: 'Snapshot Name' }),
            ]),
        });

        const fdaResponse = await getFdaResponse(
            makeRequest({
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${newer.id}/fda-response`,
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: newer.id }) },
        );
        await expect(fdaResponse.json()).resolves.toMatchObject({
            text: expect.stringContaining('FDA Response Template'),
        });

        const auditPack = await getAuditPack(
            makeRequest({
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${newer.id}/audit-pack`,
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: newer.id }) },
        );
        expect(auditPack.status).toBe(200);
        expect(auditPack.headers.get('content-disposition')).toContain('ZeroTrust-AuditPack-');
        await expect(auditPack.text()).resolves.toContain('RegEngine Zero-Trust Audit Pack');

        const refreezeResponse = await refreezeSnapshot(
            makeRequest({
                method: 'POST',
                url: `http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${older.id}/refreeze`,
                headers: { 'content-type': 'application/json' },
                body: { created_by: 'qa@regengine.local' },
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: older.id }) },
        );
        await expect(refreezeResponse.json()).resolves.toMatchObject({
            id: older.id,
            created_by: 'qa@regengine.local',
            snapshot_state: 'VALID',
        });
    });

    it('rejects invalid tenant or snapshot identifiers before reaching the backend', async () => {
        const invalidListResponse = await listSnapshots(
            makeRequest({
                url: 'http://localhost/api/v1/compliance/snapshots/../../admin',
            }),
            { params: Promise.resolve({ tenantId: '../../admin' }) },
        );
        expect(invalidListResponse.status).toBe(400);
        expect(mockFetch).not.toHaveBeenCalled();

        const invalidVerifyResponse = await verifySnapshot(
            makeRequest({
                url: 'http://localhost/api/v1/compliance/snapshots/bad/not-a-uuid/verify',
            }),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: 'not-a-uuid' }) },
        );
        expect(invalidVerifyResponse.status).toBe(400);
        expect(mockFetch).not.toHaveBeenCalled();
    });
});

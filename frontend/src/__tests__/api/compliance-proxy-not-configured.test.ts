/**
 * Compliance proxy "backend not configured" handling (#2541).
 *
 * On Vercel, getServerServiceURL returns the '' sentinel when no compliance /
 * API base URL is configured. The compliance proxies must surface an explicit
 * "not configured" 503 and never interpolate the empty base into a relative
 * fetch (which throws TypeError: Failed to parse URL and was previously
 * mis-reported as a generic "service unavailable" backend-down 503).
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import type { NextRequest } from 'next/server';

// Force the unconfigured-on-Vercel sentinel.
vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => '',
}));

const { mockEnforceTenantMatch } = vi.hoisted(() => ({
    mockEnforceTenantMatch: vi.fn(async () => null),
}));

vi.mock('@/lib/api-proxy', async () => {
    const actual = await vi.importActual<typeof import('@/lib/api-proxy')>('@/lib/api-proxy');
    return {
        ...actual,
        requireProxyAuth: vi.fn(() => null),
        validateProxySession: vi.fn(async () => null),
        getServerApiKey: vi.fn(() => 'server-key'),
        enforceTenantMatch: mockEnforceTenantMatch,
    };
});

// Disable the dev fallback so the not-configured 503 path is exercised.
vi.mock('@/lib/dev-compliance-snapshots', async () => {
    const actual = await vi.importActual<typeof import('@/lib/dev-compliance-snapshots')>(
        '@/lib/dev-compliance-snapshots',
    );
    return {
        ...actual,
        allowDevComplianceSnapshotFallback: () => false,
    };
});

const TENANT_ID = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';
const SNAPSHOT_ID = '6ba7b811-9dad-41d1-a0b4-00c04fd430c8';

function makeRequest(url: string): NextRequest {
    return {
        method: 'GET',
        url,
        nextUrl: new URL(url),
        headers: new Headers(),
        cookies: { get: () => undefined, getAll: () => [] },
        json: async () => ({}),
        text: async () => '',
    } as unknown as NextRequest;
}

describe('compliance proxies return an explicit not-configured 503 on empty base (#2541)', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        delete process.env.COMPLIANCE_SERVICE_URL;
        delete process.env.NEXT_PUBLIC_API_BASE_URL;
        mockEnforceTenantMatch.mockResolvedValue(null);
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('status route: 503 backend_not_configured, no relative fetch', async () => {
        const { GET } = await import('@/app/api/v1/compliance/status/[tenantId]/route');
        const response = await GET(
            makeRequest(`http://localhost/api/v1/compliance/status/${TENANT_ID}`),
            { params: Promise.resolve({ tenantId: TENANT_ID }) },
        );
        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toMatchObject({ error: 'backend_not_configured' });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('snapshots list route: 503 backend_not_configured, no relative fetch', async () => {
        const { GET } = await import('@/app/api/v1/compliance/snapshots/[tenantId]/route');
        const response = await GET(
            makeRequest(`http://localhost/api/v1/compliance/snapshots/${TENANT_ID}`),
            { params: Promise.resolve({ tenantId: TENANT_ID }) },
        );
        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toMatchObject({ error: 'backend_not_configured' });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('export route: 503 backend_not_configured, no relative fetch', async () => {
        const { GET } = await import('@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/export/route');
        const response = await GET(
            makeRequest(`http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${SNAPSHOT_ID}/export`),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: SNAPSHOT_ID }) },
        );
        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toMatchObject({ error: 'backend_not_configured' });
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('verify route: 503 backend_not_configured, no relative fetch', async () => {
        const { GET } = await import('@/app/api/v1/compliance/snapshots/[tenantId]/[snapshotId]/verify/route');
        const response = await GET(
            makeRequest(`http://localhost/api/v1/compliance/snapshots/${TENANT_ID}/${SNAPSHOT_ID}/verify`),
            { params: Promise.resolve({ tenantId: TENANT_ID, snapshotId: SNAPSHOT_ID }) },
        );
        expect(response.status).toBe(503);
        await expect(response.json()).resolves.toMatchObject({ error: 'backend_not_configured' });
        expect(mockFetch).not.toHaveBeenCalled();
    });
});

/**
 * enforceTenantMatch cross-tenant authorization tests (#2501).
 *
 * The `[tenantId]` compliance proxy routes forward caller credentials without
 * ambient privilege. enforceTenantMatch is a defense-in-depth IDOR backstop
 * binding a request to the caller's server-derived tenant. The fix for #2501 stops trusting the
 * client-writable `re_tenant_id` cookie for opaque (`__Host-regengine_session`)
 * sessions and derives the authoritative tenant from the backend `/auth/me`
 * `tenant_id` instead, failing closed when none is available.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { createHmac } from 'node:crypto';
import { enforceTenantMatch } from '@/lib/api-proxy';
import type { NextRequest } from 'next/server';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

const {
    mockGetAdminTargets,
    mockShouldRetryAdminProxyResponse,
} = vi.hoisted(() => ({
    mockGetAdminTargets: vi.fn(() => ['http://admin.test']),
    mockShouldRetryAdminProxyResponse: vi.fn(() => false),
}));

vi.mock('@/lib/admin-targets', () => ({
    getAdminTargets: mockGetAdminTargets,
    shouldRetryAdminProxyResponse: mockShouldRetryAdminProxyResponse,
}));

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';

function base64url(value: string): string {
    return Buffer.from(value, 'utf8').toString('base64url');
}

function signToken(payload: Record<string, unknown>): string {
    const claims = { ...payload, exp: Math.floor(Date.now() / 1000) + 3600 };
    const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const body = base64url(JSON.stringify(claims));
    const signature = createHmac('sha256', 'test-material').update(`${header}.${body}`).digest('base64url');
    return `${header}.${body}.${signature}`;
}

function makeRequest(cookies: Record<string, string> = {}, headers: Record<string, string> = {}): NextRequest {
    return {
        url: 'http://localhost/api/v1/compliance/snapshots',
        headers: new Headers(headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
    } as unknown as NextRequest;
}

describe('enforceTenantMatch — RegEngine JWT sessions', () => {
    it('allows a JWT whose tenant claim matches the path tenant', async () => {
        const token = signToken({ tenant_id: TENANT_A });
        const result = await enforceTenantMatch(makeRequest({ re_access_token: token }), TENANT_A);
        expect(result).toBeNull();
    });

    it('rejects a JWT whose tenant claim does not match the path tenant', async () => {
        const token = signToken({ tenant_id: TENANT_A });
        const result = await enforceTenantMatch(makeRequest({ re_access_token: token }), TENANT_B);
        expect(result?.status).toBe(403);
    });

    it('fails closed for a tenant-unbound token on a tenant-named route', async () => {
        const token = signToken({ role: 'sysadmin' });
        const result = await enforceTenantMatch(makeRequest({ re_access_token: token }), TENANT_B);
        expect(result?.status).toBe(403);
    });
});

describe('enforceTenantMatch — opaque __Host-regengine_session sessions (#2501)', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        mockGetAdminTargets.mockReturnValue(['http://admin.test']);
        mockShouldRetryAdminProxyResponse.mockReturnValue(false);
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    function authMeResponse(tenantId: string | null, status = 200): Response {
        return {
            ok: status >= 200 && status < 300,
            status,
            json: async () => ({
                user_id: 'u1',
                email: 'u@example.com',
                organization_id: TENANT_B,
                tenant_id: tenantId,
                auth_method: 'sso',
            }),
        } as unknown as Response;
    }

    it('derives the authoritative tenant from /auth/me tenant_id and allows a match', async () => {
        mockFetch.mockResolvedValue(authMeResponse(TENANT_A));
        const result = await enforceTenantMatch(
            makeRequest({ '__Host-regengine_session': 'opaque-token' }),
            TENANT_A,
        );
        expect(result).toBeNull();
        expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    it('rejects when the server-derived tenant does not match the path tenant', async () => {
        mockFetch.mockResolvedValue(authMeResponse(TENANT_A));
        const result = await enforceTenantMatch(
            makeRequest({ '__Host-regengine_session': 'opaque-token' }),
            TENANT_B,
        );
        expect(result?.status).toBe(403);
    });

    it('ignores a forged re_tenant_id cookie — IDOR: server tenant is A, cookie+path say B', async () => {
        // Attacker overwrites the non-httpOnly re_tenant_id cookie to the victim
        // tenant B and requests path tenant B. The cookie must NOT be trusted;
        // /auth/me proves the real tenant is A → 403.
        mockFetch.mockResolvedValue(authMeResponse(TENANT_A));
        const result = await enforceTenantMatch(
            makeRequest({ '__Host-regengine_session': 'opaque-token', re_tenant_id: TENANT_B }),
            TENANT_B,
        );
        expect(result?.status).toBe(403);
    });

    it('fails closed when /auth/me yields no tenant_id', async () => {
        mockFetch.mockResolvedValue(authMeResponse(null));
        const result = await enforceTenantMatch(
            makeRequest({ '__Host-regengine_session': 'opaque-token' }),
            TENANT_A,
        );
        expect(result?.status).toBe(403);
    });

    it('fails closed when /auth/me rejects the session (401)', async () => {
        mockFetch.mockResolvedValue(authMeResponse(null, 401));
        const result = await enforceTenantMatch(
            makeRequest({ '__Host-regengine_session': 'opaque-token' }),
            TENANT_A,
        );
        expect(result?.status).toBe(403);
    });
});

describe('enforceTenantMatch — non-session callers', () => {
    it('does not trust a bare re_tenant_id cookie (no JWT, no opaque session)', async () => {
        // Pre-#2501 this returned null (allow) when the cookie matched. The
        // client-writable cookie is no longer an authorization input.
        const result = await enforceTenantMatch(makeRequest({ re_tenant_id: TENANT_B }), TENANT_B);
        expect(result?.status).toBe(403);
    });

    it('defers to the backend for API-key callers (re_api_key cookie)', async () => {
        const result = await enforceTenantMatch(makeRequest({ re_api_key: 'k-123' }), TENANT_B);
        expect(result).toBeNull();
    });

    it('defers to the backend for API-key callers (x-regengine-api-key header)', async () => {
        const result = await enforceTenantMatch(makeRequest({}, { 'x-regengine-api-key': 'k-123' }), TENANT_B);
        expect(result).toBeNull();
    });
});

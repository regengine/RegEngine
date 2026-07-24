import { afterEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { applyInflowWorkbenchReadCredentials } from '@/lib/inflow-workbench-proxy';

const TENANT_A = '11111111-1111-4111-8111-111111111111';
const TENANT_B = '22222222-2222-4222-8222-222222222222';
const READINESS_PATH = 'api/v1/inflow-workbench/readiness/summary';

const ORIGINAL_SCOPED_KEY = process.env.INFLOW_WORKBENCH_READ_API_KEY;
const ORIGINAL_ADMIN_URL = process.env.NEXT_PUBLIC_ADMIN_URL;

function makeRequest(options: {
    tenantId?: string;
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
} = {}): NextRequest {
    const query = options.tenantId ? `?tenant_id=${encodeURIComponent(options.tenantId)}` : '';
    const cookies = options.cookies ?? {};
    return {
        url: `https://www.regengine.co/api/ingestion/${READINESS_PATH}${query}`,
        headers: new Headers(options.headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
        },
    } as unknown as NextRequest;
}

function sessionRequest(tenantId = TENANT_A): NextRequest {
    return makeRequest({
        tenantId,
        cookies: { '__Host-regengine_session': 'opaque-session-token' },
    });
}

function authMeResponse(organizationId: string): Response {
    return new Response(JSON.stringify({
        user_id: '33333333-3333-4333-8333-333333333333',
        email: 'owner@example.com',
        organization_id: organizationId,
        role: 'owner',
        auth_method: 'webauthn',
    }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
    });
}

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    if (ORIGINAL_SCOPED_KEY === undefined) {
        delete process.env.INFLOW_WORKBENCH_READ_API_KEY;
    } else {
        process.env.INFLOW_WORKBENCH_READ_API_KEY = ORIGINAL_SCOPED_KEY;
    }
    if (ORIGINAL_ADMIN_URL === undefined) {
        delete process.env.NEXT_PUBLIC_ADMIN_URL;
    } else {
        process.env.NEXT_PUBLIC_ADMIN_URL = ORIGINAL_ADMIN_URL;
    }
});

describe('Inflow Workbench readiness credential bridge', () => {
    it('injects the scoped key only after the opaque session tenant is verified', async () => {
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        const fetchMock = vi.fn().mockResolvedValue(authMeResponse(TENANT_A));
        vi.stubGlobal('fetch', fetchMock);
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            sessionRequest(),
            READINESS_PATH,
        );

        expect(error).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBe('scoped-inflow-read-key');
        expect(headers.get('x-tenant-id')).toBe(TENANT_A);
        expect(fetchMock).toHaveBeenCalledWith(
            'https://admin.example.com/auth/me',
            expect.objectContaining({
                headers: expect.objectContaining({
                    cookie: '__Host-regengine_session=opaque-session-token',
                }),
            }),
        );
    });

    it('resolves the session by tenant_id, not organization_id', async () => {
        // /auth/me returns BOTH ids and they differ. The bridge must trust
        // tenant_id (organization_id is null or unrelated for many users).
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        const authMeBoth = new Response(JSON.stringify({
            user_id: '33333333-3333-4333-8333-333333333333',
            email: 'owner@example.com',
            organization_id: TENANT_B, // deliberately NOT the requested tenant
            tenant_id: TENANT_A,
            role: 'owner',
            auth_method: 'webauthn',
        }), { status: 200, headers: { 'content-type': 'application/json' } });
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authMeBoth));
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(headers, sessionRequest(TENANT_A), READINESS_PATH);

        expect(error).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBe('scoped-inflow-read-key');
        expect(headers.get('x-tenant-id')).toBe(TENANT_A);
    });

    it('rejects when requested tenant matches only the organization_id, not tenant_id', async () => {
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        const authMeBoth = new Response(JSON.stringify({
            user_id: '33333333-3333-4333-8333-333333333333',
            email: 'owner@example.com',
            organization_id: TENANT_A,
            tenant_id: TENANT_B,
            role: 'owner',
            auth_method: 'webauthn',
        }), { status: 200, headers: { 'content-type': 'application/json' } });
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authMeBoth));
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(headers, sessionRequest(TENANT_A), READINESS_PATH);

        expect(error?.status).toBe(403);
        expect(headers.get('x-regengine-api-key')).toBeNull();
    });

    it('rejects a tenant that does not match the validated opaque session', async () => {
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authMeResponse(TENANT_A)));
        const headers = new Headers({ 'x-tenant-id': TENANT_B });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            sessionRequest(TENANT_B),
            READINESS_PATH,
        );

        expect(error?.status).toBe(403);
        await expect(error?.json()).resolves.toMatchObject({ code: 'TENANT_CONTEXT_MISMATCH' });
        expect(headers.has('x-regengine-api-key')).toBe(false);
    });

    it('rejects an invalid or expired opaque session', async () => {
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 401 })));
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            sessionRequest(),
            READINESS_PATH,
        );

        expect(error?.status).toBe(401);
        await expect(error?.json()).resolves.toMatchObject({ code: 'SESSION_INVALID' });
        expect(headers.has('x-regengine-api-key')).toBe(false);
    });

    it('fails closed when the scoped inflow.read key is not configured', async () => {
        process.env.NEXT_PUBLIC_ADMIN_URL = 'https://admin.example.com';
        delete process.env.INFLOW_WORKBENCH_READ_API_KEY;
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(authMeResponse(TENANT_A)));
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            sessionRequest(),
            READINESS_PATH,
        );

        expect(error?.status).toBe(503);
        await expect(error?.json()).resolves.toEqual({ error: 'Service temporarily unavailable' });
        expect(headers.has('x-regengine-api-key')).toBe(false);
    });

    it('does not grant a scoped key without an opaque passwordless session', async () => {
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        const headers = new Headers({ 'x-tenant-id': TENANT_A });
        const request = makeRequest({
            tenantId: TENANT_A,
            headers: {
                origin: 'https://www.regengine.co',
                'x-regengine-api-key': 'browser-injected-key',
            },
        });

        const error = await applyInflowWorkbenchReadCredentials(headers, request, READINESS_PATH);

        expect(error?.status).toBe(401);
        await expect(error?.json()).resolves.toMatchObject({ code: 'SESSION_CREDENTIAL_REQUIRED' });
        expect(headers.has('x-regengine-api-key')).toBe(false);
    });

    it('preserves a caller API key instead of replacing it with the scoped key', async () => {
        process.env.INFLOW_WORKBENCH_READ_API_KEY = 'scoped-inflow-read-key'; // pragma: allowlist secret
        const headers = new Headers({
            'x-regengine-api-key': 'caller-api-key', // pragma: allowlist secret
            'x-tenant-id': TENANT_A,
        });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            makeRequest({ tenantId: TENANT_A }),
            READINESS_PATH,
        );

        expect(error).toBeNull();
        expect(headers.get('x-regengine-api-key')).toBe('caller-api-key');
    });

    it('rejects conflicting query and header tenant contexts before session lookup', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);
        const headers = new Headers({ 'x-tenant-id': TENANT_A });

        const error = await applyInflowWorkbenchReadCredentials(
            headers,
            sessionRequest(TENANT_B),
            READINESS_PATH,
        );

        expect(error?.status).toBe(403);
        expect(fetchMock).not.toHaveBeenCalled();
        expect(headers.has('x-regengine-api-key')).toBe(false);
    });
});

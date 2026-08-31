/**
 * RE-SEC-003: same-origin enforcement on POST /api/session.
 *
 * /api/session bootstraps the CSRF cookies on first login, so it is
 * necessarily exempt from the CSRF double-submit check. To prevent
 * login-CSRF / session-fixation, POST is gated on the Origin header
 * matching the deploy-configured ALLOWED_ORIGINS list (production only).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createHmac } from 'crypto';
import { POST, GET, DELETE } from '@/app/api/session/route';
import { isCsrfExempt } from '@/lib/csrf';
import type { NextRequest } from 'next/server';

function makeRequest({
    headers = {},
    body = {},
    cookies = {},
    method = 'POST',
}: {
    headers?: Record<string, string>;
    body?: Record<string, unknown>;
    cookies?: Record<string, string>;
    method?: string;
} = {}): NextRequest {
    return {
        method,
        headers: new Headers(headers),
        nextUrl: new URL('http://localhost/api/session'),
        cookies: {
            getAll: vi.fn(() => Object.entries(cookies).map(([name, value]) => ({ name, value }))),
            get: vi.fn((name: string) =>
                cookies[name] !== undefined ? { name, value: cookies[name] } : undefined,
            ),
        },
        json: vi.fn().mockResolvedValue(body),
    } as unknown as NextRequest;
}

describe('POST /api/session Origin enforcement (RE-SEC-003)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        vi.unstubAllEnvs();
        vi.doUnmock('jose');
        vi.unstubAllGlobals();
    });

    it('rejects POST with no Origin header in production', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('ALLOWED_ORIGINS', 'https://app.regengine.io');

        const response = await POST(makeRequest({ body: {} }));

        expect(response.status).toBe(403);
        const json = await response.json();
        expect(json.error).toMatch(/cross-origin/i);
    });

    it('passes the Origin check when Origin is in ALLOWED_ORIGINS in production', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv(
            'ALLOWED_ORIGINS',
            'https://app.regengine.io,https://regengine.io',
        );

        // Empty body — body has no credentials, so the handler falls through
        // to setting CSRF cookies and returns 200. Critically, it does NOT
        // 403 from the new Origin check.
        const response = await POST(
            makeRequest({
                headers: { origin: 'https://app.regengine.io' },
                body: {},
            }),
        );

        expect(response.status).not.toBe(403);
    });

    it('rejects POST with an Origin not in ALLOWED_ORIGINS in production', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('ALLOWED_ORIGINS', 'https://app.regengine.io');

        const response = await POST(
            makeRequest({
                headers: { origin: 'https://attacker.example.com' },
                body: {},
            }),
        );

        expect(response.status).toBe(403);
        const json = await response.json();
        expect(json.error).toMatch(/cross-origin/i);
    });

    it('does not enforce the Origin check outside production (e.g. dev/test)', async () => {
        vi.stubEnv('NODE_ENV', 'development');
        // Intentionally no ALLOWED_ORIGINS set, no Origin header — must NOT 403.
        const response = await POST(makeRequest({ body: {} }));

        expect(response.status).not.toBe(403);
    });

    it('/api/session is no longer in the CSRF exempt prefix list', () => {
        // Structural assertion: the bootstrap gap that forced the exemption is
        // closed by GET /api/session issuing the CSRF cookies. The middleware
        // must now enforce CSRF on POST /api/session like every other mutating
        // endpoint. If /api/session ever drifts back into CSRF_EXEMPT_PREFIXES,
        // this test fails and forces an explicit threat-model conversation.
        expect(isCsrfExempt('/api/session', 'POST')).toBe(false);
        // Passwordless auth starts are still pre-auth — sanity check.
        expect(isCsrfExempt('/api/admin/auth/challenges', 'POST')).toBe(true);
    });

    it('GET /api/session sets re_csrf and re_csrf_sig cookies on first call', async () => {
        vi.stubEnv('CSRF_SECRET', 'test-secret-for-bootstrap');
        const response = await GET(makeRequest({ method: 'GET', cookies: {} }));

        // NextResponse exposes cookies via .cookies.getAll()
        const setCookies = response.cookies.getAll();
        const names = setCookies.map((c: { name: string }) => c.name);
        expect(names).toContain('re_csrf');
        expect(names).toContain('re_csrf_sig');
        const csrf = setCookies.find((c: { name: string }) => c.name === 're_csrf');
        const csrfSig = setCookies.find((c: { name: string }) => c.name === 're_csrf_sig');
        expect(csrf?.value).toBeTruthy();
        expect(csrfSig?.value).toBeTruthy();
    });

    it('GET /api/session does NOT re-issue CSRF cookies when they already exist (idempotent)', async () => {
        vi.stubEnv('CSRF_SECRET', 'test-secret-for-bootstrap');
        const response = await GET(
            makeRequest({
                method: 'GET',
                cookies: { re_csrf: 'existing-token', re_csrf_sig: 'existing-sig' },
            }),
        );

        const setCookies = response.cookies.getAll();
        const names = setCookies.map((c: { name: string }) => c.name);
        expect(names).not.toContain('re_csrf');
        expect(names).not.toContain('re_csrf_sig');
    });

    it('GET /api/session hydrates opaque session profile data from backend /auth/me', async () => {
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', 'https://admin.regengine.test');
        vi.stubEnv('CSRF_SECRET', 'test-secret-for-bootstrap');
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(
                JSON.stringify({
                    user_id: '11111111-1111-4111-8111-111111111111',
                    email: 'owner@example.com',
                    organization_id: '22222222-2222-4222-8222-222222222222',
                    role: 'owner',
                    auth_method: 'webauthn',
                    is_sysadmin: true,
                    permissions: ['review.read', 'review.decide'],
                }),
                { status: 200, headers: { 'content-type': 'application/json' } },
            ),
        );
        vi.stubGlobal('fetch', fetchMock);

        const response = await GET(
            makeRequest({
                method: 'GET',
                cookies: {
                    '__Host-regengine_session': 'opaque-session-token',
                    re_user: JSON.stringify({ id: 'stale-user', email: 'stale@example.com' }),
                    re_tenant_id: 'stale-tenant',
                },
            }),
        );

        expect(fetchMock).toHaveBeenCalledWith('https://admin.regengine.test/auth/me', {
            method: 'GET',
            headers: {
                accept: 'application/json',
                cookie: '__Host-regengine_session=opaque-session-token',
            },
            cache: 'no-store',
            redirect: 'manual',
        });
        await expect(response.json()).resolves.toEqual({
            authenticated: true,
            has_api_key: false,
            has_credentials: true,
            tenant_id: '22222222-2222-4222-8222-222222222222',
            auth_method: 'webauthn',
            user: {
                id: '11111111-1111-4111-8111-111111111111',
                email: 'owner@example.com',
                is_sysadmin: true,
                status: 'active',
                role_name: 'owner',
                organization_id: '22222222-2222-4222-8222-222222222222',
                auth_method: 'webauthn',
                permissions: ['review.read', 'review.decide'],
            },
        });
        expect(response.cookies.get('re_tenant_id')?.value).toBe('22222222-2222-4222-8222-222222222222');
        expect(response.cookies.get('re_user')?.value).toContain('owner@example.com');
    });

    it('GET /api/session rejects stale opaque cookies when backend /auth/me rejects them', async () => {
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', 'https://admin.regengine.test');
        vi.stubEnv('CSRF_SECRET', 'test-secret-for-bootstrap');
        const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
        vi.stubGlobal('fetch', fetchMock);

        const response = await GET(
            makeRequest({
                method: 'GET',
                cookies: {
                    '__Host-regengine_session': 'stale-session-token',
                },
            }),
        );

        await expect(response.json()).resolves.toEqual({
            authenticated: false,
            has_api_key: false,
            has_credentials: false,
            tenant_id: null,
            auth_method: null,
            user: null,
        });
    });

    it('returns 500 when ALLOWED_ORIGINS is unset in production (fail-closed misconfig)', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('ALLOWED_ORIGINS', '');

        const response = await POST(
            makeRequest({
                headers: { origin: 'https://app.regengine.io' },
                body: {},
            }),
        );

        expect(response.status).toBe(500);
    });

    it('sets persistent credential cookies by default for remembered sessions', async () => {
        const response = await POST(
            makeRequest({
                body: {
                    api_key: 'persistent-api-key',
                    tenant_id: 'tenant-persistent',
                    user: { id: 'user-persistent', email: 'persistent@example.com' },
                },
            }),
        );

        expect(response.status).toBe(200);
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({
                name: 're_api_key',
                value: 'persistent-api-key',
                maxAge: 60 * 60 * 24 * 7,
            }),
        );
        expect(response.cookies.get('re_tenant_id')?.maxAge).toBe(60 * 60 * 24 * 7);
        expect(response.cookies.get('re_user')?.maxAge).toBe(60 * 60 * 24 * 7);
        expect(response.cookies.get('re_csrf')?.maxAge).toBe(60 * 60 * 24 * 7);
        expect(response.cookies.get('re_csrf_sig')?.maxAge).toBe(60 * 60 * 24 * 7);
    });

    it('omits Max-Age when remember_me is false so cookies are browser-session scoped', async () => {
        const response = await POST(
            makeRequest({
                body: {
                    api_key: 'session-api-key',
                    tenant_id: 'tenant-session',
                    user: { id: 'user-session', email: 'session@example.com' },
                    remember_me: false,
                },
            }),
        );

        expect(response.status).toBe(200);
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({
                name: 're_api_key',
                value: 'session-api-key',
            }),
        );
        expect(response.cookies.get('re_api_key')?.maxAge).toBeUndefined();
        expect(response.cookies.get('re_tenant_id')?.maxAge).toBeUndefined();
        expect(response.cookies.get('re_user')?.maxAge).toBeUndefined();
        expect(response.cookies.get('re_csrf')?.maxAge).toBeUndefined();
        expect(response.cookies.get('re_csrf_sig')?.maxAge).toBeUndefined();
    });

    it('sets production credential cookies with HttpOnly, Secure, and SameSite=Lax', async () => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('ALLOWED_ORIGINS', 'https://app.regengine.io');

        const response = await POST(
            makeRequest({
                headers: { origin: 'https://app.regengine.io' },
                body: { api_key: 'prod-api-key' },
            }),
        );

        expect(response.status).toBe(200);
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({
                name: 're_api_key',
                value: 'prod-api-key',
                httpOnly: true,
                secure: true,
                sameSite: 'lax',
            }),
        );
    });

    it('deletes a stale tenant API-key cookie when accepting a new access token', async () => {
        // Signing material is irrelevant — the route decodes claims without verifying.
        const accessToken = await signRegEngineJwt('session-origin-test-secret', 'tenant-access');

        const response = await POST(
            makeRequest({
                body: {
                    access_token: accessToken,
                    tenant_id: 'tenant-access',
                },
                cookies: {
                    re_api_key: 'stale-api-key',
                },
            }),
        );

        expect(response.status).toBe(200);
        expect(response.cookies.get('re_access_token')?.value).toBe(accessToken);
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({ name: 're_api_key', value: '' }),
        );
    });

    it('ignores a retired administrative credential field instead of creating a cookie', async () => {
        // Signing material is irrelevant — the route decodes claims without verifying.
        const accessToken = await signRegEngineJwt('session-origin-test-secret', 'tenant-access');

        const response = await POST(
            makeRequest({
                body: {
                    access_token: accessToken,
                    tenant_id: 'tenant-access',
                    api_key: '',
                    admin_key: 'cookie-managed',
                },
                cookies: {
                    re_api_key: 'stale-api-key',
                },
            }),
        );

        expect(response.status).toBe(200);
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({ name: 're_api_key', value: '' }),
        );
        expect(response.cookies.get('re_admin_key')).toBeUndefined();
    });

    it('DELETE calls backend logout with the bearer token and clears cookies', async () => {
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', 'https://admin.regengine.test');
        const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
        vi.stubGlobal('fetch', fetchMock);

        const response = await DELETE(
            makeRequest({
                method: 'DELETE',
                cookies: { re_access_token: 'access-token-to-revoke' },
            }),
        );

        expect(fetchMock).toHaveBeenCalledWith('https://admin.regengine.test/auth/logout', {
            method: 'POST',
            headers: {
                Authorization: 'Bearer access-token-to-revoke',
            },
            redirect: 'manual',
        });
        expect(response.cookies.get('re_access_token')).toEqual(
            expect.objectContaining({ name: 're_access_token', value: '' }),
        );
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({ name: 're_api_key', value: '' }),
        );
    });

    it('DELETE forwards the opaque session cookie to backend /auth/session/logout and clears it', async () => {
        vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', 'https://admin.regengine.test');
        const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
        vi.stubGlobal('fetch', fetchMock);

        const response = await DELETE(
            makeRequest({
                method: 'DELETE',
                cookies: { '__Host-regengine_session': 'opaque-session-token' },
            }),
        );

        expect(fetchMock).toHaveBeenCalledWith('https://admin.regengine.test/auth/session/logout', {
            method: 'POST',
            headers: {
                cookie: '__Host-regengine_session=opaque-session-token',
            },
            redirect: 'manual',
        });
        expect(response.cookies.get('__Host-regengine_session')).toEqual(
            expect.objectContaining({ name: '__Host-regengine_session', value: '' }),
        );
    });

    it('DELETE without an access token skips backend logout and still clears cookies', async () => {
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);

        const response = await DELETE(makeRequest({ method: 'DELETE', cookies: {} }));

        expect(fetchMock).not.toHaveBeenCalled();
        expect(response.cookies.get('re_access_token')).toEqual(
            expect.objectContaining({ name: 're_access_token', value: '' }),
        );
        expect(response.cookies.get('re_api_key')).toEqual(
            expect.objectContaining({ name: 're_api_key', value: '' }),
        );
    });
});

async function signRegEngineJwt(secret: string, tenantId: string): Promise<string> {
    const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const payload = base64url(JSON.stringify({
        tenant_id: tenantId,
        aud: 'regengine-api',
        iss: 'regengine-admin',
    }));
    const signature = createHmac('sha256', secret)
        .update(`${header}.${payload}`)
        .digest('base64url');
    return `${header}.${payload}.${signature}`;
}

function base64url(value: string): string {
    return Buffer.from(value).toString('base64url');
}

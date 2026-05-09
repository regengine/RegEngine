/**
 * RE-SEC-003: same-origin enforcement on POST /api/session.
 *
 * /api/session bootstraps the CSRF cookies on first login, so it is
 * necessarily exempt from the CSRF double-submit check. To prevent
 * login-CSRF / session-fixation, POST is gated on the Origin header
 * matching the deploy-configured ALLOWED_ORIGINS list (production only).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { POST, GET } from '@/app/api/session/route';
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
        expect(isCsrfExempt('/api/session')).toBe(false);
        // /api/auth/* still exempt (pre-auth callbacks) — sanity check.
        expect(isCsrfExempt('/api/auth/callback')).toBe(true);
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
});

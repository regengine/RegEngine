/**
 * RE-SEC-003: same-origin enforcement on POST /api/session.
 *
 * /api/session bootstraps the CSRF cookies on first login, so it is
 * necessarily exempt from the CSRF double-submit check. To prevent
 * login-CSRF / session-fixation, POST is gated on the Origin header
 * matching the deploy-configured ALLOWED_ORIGINS list (production only).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { POST } from '@/app/api/session/route';
import type { NextRequest } from 'next/server';

function makeRequest({
    headers = {},
    body = {},
}: {
    headers?: Record<string, string>;
    body?: Record<string, unknown>;
} = {}): NextRequest {
    return {
        method: 'POST',
        headers: new Headers(headers),
        nextUrl: new URL('http://localhost/api/session'),
        cookies: {
            getAll: vi.fn(() => []),
            get: vi.fn(() => undefined),
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

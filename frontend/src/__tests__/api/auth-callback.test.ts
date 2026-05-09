/**
 * RE-FE-AUDIT-001 / OQ-1: x-forwarded-host trust dropped.
 * RE-FE-AUDIT-002 / OQ-2: next param validated against open-redirect bypass.
 *
 * /auth/callback derives the redirect base from `request.url`'s origin and
 * MUST NOT consult `x-forwarded-host`, which is attacker-controllable on
 * proxies that don't normalize the header.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { NextRequest } from 'next/server';

const exchangeCodeForSession = vi.fn();

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(() => ({
        auth: { exchangeCodeForSession },
    })),
}));

import { GET } from '@/app/auth/callback/route';

function makeRequest({
    url,
    headers = {},
}: {
    url: string;
    headers?: Record<string, string>;
}): NextRequest {
    return {
        url,
        headers: new Headers(headers),
        cookies: {
            getAll: vi.fn(() => []),
            get: vi.fn(() => undefined),
        },
    } as unknown as NextRequest;
}

describe('/auth/callback redirect hardening', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        exchangeCodeForSession.mockResolvedValue({ error: null });
        process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://test.supabase.co';
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
    });

    it('ignores x-forwarded-host and uses request.url origin (RE-FE-AUDIT-001)', async () => {
        const response = await GET(
            makeRequest({
                url: 'https://app.regengine.io/auth/callback?code=abc&next=/dashboard',
                headers: { 'x-forwarded-host': 'evil.com' },
            }),
        );

        expect(response.status).toBe(307); // NextResponse.redirect default
        const location = response.headers.get('location');
        expect(location).toBe('https://app.regengine.io/dashboard');
        expect(location).not.toContain('evil.com');
    });

    it('falls back to /dashboard when next is a protocol-relative bypass (RE-FE-AUDIT-002)', async () => {
        const response = await GET(
            makeRequest({
                url: 'https://app.regengine.io/auth/callback?code=abc&next=//attacker.com/path',
            }),
        );

        const location = response.headers.get('location');
        expect(location).toBe('https://app.regengine.io/dashboard');
        expect(location).not.toContain('attacker.com');
    });

    it('preserves a clean next path', async () => {
        const response = await GET(
            makeRequest({
                url: 'https://app.regengine.io/auth/callback?code=abc&next=/developer/portal',
            }),
        );

        expect(response.headers.get('location')).toBe(
            'https://app.regengine.io/developer/portal',
        );
    });

    it('rejects javascript: scheme in next', async () => {
        const response = await GET(
            makeRequest({
                url: 'https://app.regengine.io/auth/callback?code=abc&next=javascript:alert(1)',
            }),
        );

        expect(response.headers.get('location')).toBe(
            'https://app.regengine.io/dashboard',
        );
    });
});

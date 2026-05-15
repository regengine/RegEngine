import type { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET } from '@/app/auth/callback/route';

const { createServerClientMock } = vi.hoisted(() => ({
    createServerClientMock: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
    createServerClient: createServerClientMock,
}));

const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
const ORIGINAL_SITE_URL = process.env.NEXT_PUBLIC_SITE_URL;
const ORIGINAL_VERCEL_URL = process.env.VERCEL_URL;

function restoreEnv() {
    if (ORIGINAL_SUPABASE_URL === undefined) {
        delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    } else {
        process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_SUPABASE_URL;
    }
    if (ORIGINAL_SUPABASE_ANON_KEY === undefined) {
        delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    } else {
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_SUPABASE_ANON_KEY;
    }
    if (ORIGINAL_SITE_URL === undefined) {
        delete process.env.NEXT_PUBLIC_SITE_URL;
    } else {
        process.env.NEXT_PUBLIC_SITE_URL = ORIGINAL_SITE_URL;
    }
    if (ORIGINAL_VERCEL_URL === undefined) {
        delete process.env.VERCEL_URL;
    } else {
        process.env.VERCEL_URL = ORIGINAL_VERCEL_URL;
    }
}

function makeRequest(url: string, headers: Record<string, string> = {}): NextRequest {
    return {
        url,
        headers: new Headers(headers),
        cookies: {
            getAll() {
                return [];
            },
        },
    } as unknown as NextRequest;
}

describe('auth callback redirect safety', () => {
    beforeEach(() => {
        restoreEnv();
        process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://supabase.example.test';
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
        createServerClientMock.mockReset();
        createServerClientMock.mockReturnValue({
            auth: {
                exchangeCodeForSession: vi.fn().mockResolvedValue({ error: null }),
            },
        });
    });

    afterEach(() => {
        createServerClientMock.mockReset();
        restoreEnv();
    });

    it('does not redirect off-origin when next is a host-like relative value', async () => {
        const response = await GET(makeRequest('https://regengine.co/auth/callback?code=valid&next=@evil.com'));
        const location = new URL(response.headers.get('location')!, 'https://regengine.co');

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/dashboard');
    });

    it('preserves a safe internal callback destination with query parameters', async () => {
        const response = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Fdeveloper%2Fportal%3Ftab%3Dkeys',
        ));
        const location = new URL(response.headers.get('location')!, 'https://regengine.co');

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/developer/portal');
        expect(location.searchParams.get('tab')).toBe('keys');
    });

    it('rejects protocol-relative callback destinations', async () => {
        const response = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2F%2Fevil.example%2Fsteal',
        ));
        const location = new URL(response.headers.get('location')!, 'https://regengine.co');

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/dashboard');
    });

    it('rejects login callback loops and unsafe characters', async () => {
        const loginResponse = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Flogin%3Fnext%3D%252Fdashboard',
        ));
        const backslashResponse = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Fdashboard%5C..%5Cadmin',
        ));

        expect(new URL(loginResponse.headers.get('location')!).pathname).toBe('/dashboard');
        expect(new URL(backslashResponse.headers.get('location')!).pathname).toBe('/dashboard');
    });

    it('does not trust spoofed forwarded hosts for redirect origin', async () => {
        const response = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Fdeveloper%2Fportal',
            { 'x-forwarded-host': 'evil.example' },
        ));
        const location = new URL(response.headers.get('location')!);

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/developer/portal');
    });

    it('uses the configured public site origin when present', async () => {
        process.env.NEXT_PUBLIC_SITE_URL = 'https://app.regengine.test/some/path';

        const response = await GET(makeRequest(
            'https://internal.local/auth/callback?code=valid&next=%2Fdashboard',
            { 'x-forwarded-host': 'evil.example' },
        ));
        const location = new URL(response.headers.get('location')!);

        expect(location.origin).toBe('https://app.regengine.test');
        expect(location.pathname).toBe('/dashboard');
    });

    it('falls back to the request origin when NEXT_PUBLIC_SITE_URL is unset', async () => {
        delete process.env.NEXT_PUBLIC_SITE_URL;

        const response = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Fdashboard',
        ));
        const location = new URL(response.headers.get('location')!);

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/dashboard');
    });

    it('ignores VERCEL_URL even when set (2026-05-13 outage regression guard)', async () => {
        // VERCEL_URL is the deployment-specific hostname, never the canonical
        // alias. Falling back to it broke prod login because Supabase session
        // cookies set on the deployment origin did not stick on the alias.
        delete process.env.NEXT_PUBLIC_SITE_URL;
        process.env.VERCEL_URL = 'regengine-xxxx.vercel.app';

        const response = await GET(makeRequest(
            'https://regengine.co/auth/callback?code=valid&next=%2Fdashboard',
        ));
        const location = new URL(response.headers.get('location')!);

        // Should use request origin (canonical alias), not VERCEL_URL.
        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/dashboard');
    });

    it('NEXT_PUBLIC_SITE_URL overrides the request origin', async () => {
        process.env.NEXT_PUBLIC_SITE_URL = 'https://regengine.co';

        const response = await GET(makeRequest(
            'https://regengine-preview-xyz.vercel.app/auth/callback?code=valid&next=%2Fdashboard',
        ));
        const location = new URL(response.headers.get('location')!);

        expect(location.origin).toBe('https://regengine.co');
        expect(location.pathname).toBe('/dashboard');
    });
});

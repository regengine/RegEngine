import { createHmac } from 'node:crypto';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { proxy } from '@/proxy';
import { _resetForTesting as resetJwtKeysForTesting } from '@/lib/jwt-keys';

const { createServerClientMock } = vi.hoisted(() => ({
    createServerClientMock: vi.fn(),
}));

vi.mock('@supabase/ssr', () => ({
    createServerClient: createServerClientMock,
}));

const ORIGINAL_JWT_SIGNING_KEY = process.env.JWT_SIGNING_KEY;
const ORIGINAL_AUTH_SECRET_KEY = process.env.AUTH_SECRET_KEY;
const ORIGINAL_SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

function makeRequest(url: string, cookies: Record<string, string> = {}): NextRequest {
    const cookieHeader = Object.entries(cookies)
        .map(([name, value]) => `${name}=${value}`)
        .join('; ');

    const request = new NextRequest(url, {
        headers: cookieHeader ? { cookie: cookieHeader } : undefined,
    });
    for (const [name, value] of Object.entries(cookies)) {
        request.cookies.set(name, value);
    }
    return request;
}

function base64url(value: string): string {
    return Buffer.from(value, 'utf8').toString('base64url');
}

function signToken(payload: Record<string, unknown>, secret: string): string {
    const header = base64url(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
    const body = base64url(JSON.stringify({
        aud: 'regengine-api',
        iss: 'regengine-admin',
        exp: Math.floor(Date.now() / 1000) + 3600,
        ...payload,
    }));
    const signature = createHmac('sha256', secret)
        .update(`${header}.${body}`)
        .digest('base64url');
    return `${header}.${body}.${signature}`;
}

function location(response: Response): URL {
    const value = response.headers.get('location');
    if (!value) throw new Error('Missing redirect location');
    return new URL(value);
}

function queryResult(data: unknown) {
    return {
        select: vi.fn(() => ({
            eq: vi.fn(() => ({
                maybeSingle: vi.fn().mockResolvedValue({ data, error: null }),
            })),
        })),
    };
}

beforeEach(() => {
    vi.restoreAllMocks();
    createServerClientMock.mockReset();
    process.env.JWT_SIGNING_KEY = 'frontend-auth-boundary-secret';
    process.env.AUTH_SECRET_KEY = 'frontend-auth-boundary-secret';
    delete process.env.NEXT_PUBLIC_SUPABASE_URL;
    delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    resetJwtKeysForTesting();
});

afterEach(() => {
    createServerClientMock.mockReset();
    if (ORIGINAL_JWT_SIGNING_KEY === undefined) {
        delete process.env.JWT_SIGNING_KEY;
    } else {
        process.env.JWT_SIGNING_KEY = ORIGINAL_JWT_SIGNING_KEY;
    }
    if (ORIGINAL_AUTH_SECRET_KEY === undefined) {
        delete process.env.AUTH_SECRET_KEY;
    } else {
        process.env.AUTH_SECRET_KEY = ORIGINAL_AUTH_SECRET_KEY;
    }
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
    resetJwtKeysForTesting();
});

describe('frontend auth boundary middleware', () => {
    it('redirects logged-out protected URLs with the full destination in next', async () => {
        const response = await proxy(makeRequest(
            'http://localhost/dashboard/settings?tab=team&mode=edit&next=%2Fother',
        ));

        expect(response.status).toBe(307);
        const redirect = location(response);
        expect(redirect.pathname).toBe('/login');
        expect(redirect.searchParams.get('next')).toBe(
            '/dashboard/settings?tab=team&mode=edit&next=%2Fother',
        );
        expect(redirect.searchParams.get('tab')).toBeNull();
        expect(redirect.searchParams.get('mode')).toBeNull();
    });

    it('redirects logged-out request URLs with query strings intact', async () => {
        const response = await proxy(makeRequest(
            'http://localhost/requests/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?view=timeline',
        ));

        const redirect = location(response);
        expect(redirect.pathname).toBe('/login');
        expect(redirect.searchParams.get('next')).toBe(
            '/requests/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?view=timeline',
        );
    });

    it('does not allow a stale sysadmin JWT claim when the fresh Supabase check denies it', async () => {
        process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://supabase.example.test';
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
        createServerClientMock.mockReturnValue({
            auth: {
                getUser: vi.fn().mockResolvedValue({ data: { user: null } }),
            },
            from: vi.fn((table: string) => {
                if (table === 'tenants') {
                    return queryResult({ status: 'active' });
                }
                if (table === 'users') {
                    return queryResult({ is_sysadmin: false });
                }
                return queryResult(null);
            }),
        });
        const token = signToken({
            sub: 'user-a',
            tenant_id: '11111111-1111-1111-1111-111111111111',
            tenant_status: 'active',
            is_sysadmin: true,
            tv: 0,
        }, 'frontend-auth-boundary-secret');

        const response = await proxy(makeRequest('http://localhost/sysadmin', {
            re_access_token: token,
            'sb-auth-token': 'present',
        }));

        expect(response.status).toBe(307);
        expect(location(response).pathname).toBe('/dashboard');
    });
});

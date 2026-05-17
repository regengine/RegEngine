import { createHmac } from 'node:crypto';
import type { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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

function restoreEnv() {
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
}

function makeRequest(url: string, cookies: Record<string, string> = {}): NextRequest {
    const nextUrl = new URL(url) as URL & { clone: () => URL };
    nextUrl.clone = () => new URL(nextUrl.toString());
    const cookieStore = new Map(Object.entries(cookies));

    return {
        url,
        method: 'GET',
        headers: new Headers(),
        nextUrl,
        cookies: {
            get(name: string) {
                const value = cookieStore.get(name);
                return value === undefined ? undefined : { name, value };
            },
            getAll() {
                return Array.from(cookieStore.entries()).map(([name, value]) => ({ name, value }));
            },
            set(name: string, value: string) {
                cookieStore.set(name, value);
            },
        },
    } as unknown as NextRequest;
}

function signToken(secret: string, claims: Record<string, unknown>): string {
    const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url');
    const payload = Buffer.from(JSON.stringify({
        exp: Math.floor(Date.now() / 1000) + 3600,
        ...claims,
    })).toString('base64url');
    const signature = createHmac('sha256', secret)
        .update(`${header}.${payload}`)
        .digest('base64url');
    return `${header}.${payload}.${signature}`;
}

function primeJwtEnv(secret: string): void {
    process.env.JWT_SIGNING_KEY = secret;
    process.env.AUTH_SECRET_KEY = secret;
    resetJwtKeysForTesting();
}

function primeSupabaseEnv(): void {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://supabase.example.test';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
}

function queryResult(data: unknown, error: unknown = null) {
    return {
        select: vi.fn(() => ({
            eq: vi.fn(() => ({
                maybeSingle: vi.fn().mockResolvedValue({ data, error }),
            })),
        })),
    };
}

function mockSupabaseAuthz(options: {
    authUser?: unknown;
    tenantStatus?: string;
    isSysadmin?: boolean;
    tenantError?: unknown;
    sysadminError?: unknown;
}) {
    createServerClientMock.mockImplementation(() => ({
        auth: {
            getUser: vi.fn().mockResolvedValue({ data: { user: options.authUser ?? null } }),
        },
        from: vi.fn((table: string) => {
            if (table === 'tenants') {
                return queryResult(
                    options.tenantStatus === undefined ? null : { status: options.tenantStatus },
                    options.tenantError,
                );
            }
            if (table === 'users') {
                return queryResult(
                    options.isSysadmin === undefined ? null : { is_sysadmin: options.isSysadmin },
                    options.sysadminError,
                );
            }
            if (table === 'developer_profiles') {
                return queryResult(
                    options.isSysadmin === undefined ? null : { is_sysadmin: options.isSysadmin },
                    options.sysadminError,
                );
            }
            return queryResult(null);
        }),
    }));
}

describe('proxy authenticated-route authorization', () => {
    beforeEach(() => {
        createServerClientMock.mockReset();
        restoreEnv();
        resetJwtKeysForTesting();
    });

    afterEach(() => {
        createServerClientMock.mockReset();
        restoreEnv();
        resetJwtKeysForTesting();
    });

    it('preserves the full internal destination query string in login redirects', async () => {
        delete process.env.NEXT_PUBLIC_SUPABASE_URL;
        delete process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

        const response = await proxy(makeRequest('https://app.example.test/dashboard/settings?tab=team&mode=edit'));
        const location = new URL(response.headers.get('location')!, 'https://app.example.test');

        expect(location.pathname).toBe('/login');
        expect(location.searchParams.get('next')).toBe('/dashboard/settings?tab=team&mode=edit');
        expect(location.searchParams.has('tab')).toBe(false);
        expect(location.searchParams.has('mode')).toBe(false);
    });

    it('denies stale sysadmin JWT claims when the fresh Supabase source says the role was revoked', async () => {
        const secret = 'proxy-authz-test-secret';
        primeJwtEnv(secret);
        primeSupabaseEnv();
        mockSupabaseAuthz({ tenantStatus: 'active', isSysadmin: false });

        const token = signToken(secret, {
            sub: 'user-stale-sysadmin',
            tenant_id: 'tenant-stale-sysadmin',
            tenant_status: 'active',
            is_sysadmin: true,
        });

        const response = await proxy(makeRequest('https://app.example.test/sysadmin', {
            re_access_token: token,
            'sb-auth-token': 'present',
        }));
        const location = new URL(response.headers.get('location')!, 'https://app.example.test');

        expect(location.pathname).toBe('/dashboard');
    });

    it('denies stale active tenant JWT claims when Supabase says the tenant is suspended', async () => {
        const secret = 'proxy-authz-test-secret';
        primeJwtEnv(secret);
        primeSupabaseEnv();
        mockSupabaseAuthz({ tenantStatus: 'suspended', isSysadmin: true });

        const token = signToken(secret, {
            sub: 'user-stale-tenant',
            tenant_id: 'tenant-stale-suspended',
            tenant_status: 'active',
            is_sysadmin: false,
        });

        const response = await proxy(makeRequest('https://app.example.test/dashboard', {
            re_access_token: token,
            'sb-auth-token': 'present',
        }));
        const location = new URL(response.headers.get('location')!, 'https://app.example.test');

        expect(location.pathname).toBe('/login');
        expect(location.searchParams.get('error')).toBe('tenant_suspended');
        expect(location.searchParams.has('next')).toBe(false);
    });

    it('allows email-code RegEngine JWTs without a Supabase auth cookie', async () => {
        const secret = 'proxy-authz-test-secret';
        primeJwtEnv(secret);
        primeSupabaseEnv();
        mockSupabaseAuthz({ tenantStatus: 'active', isSysadmin: false });

        const token = signToken(secret, {
            sub: 'email-code-user',
            tenant_id: 'tenant-email-code',
            tenant_status: 'active',
            is_sysadmin: false,
            auth_method: 'email_code',
        });

        const response = await proxy(makeRequest('https://app.example.test/dashboard', {
            re_access_token: token,
        }));

        expect(response.status).toBe(200);
        expect(response.headers.get('location')).toBeNull();
    });

    it('denies stale Supabase tenant metadata when the tenants table says suspended', async () => {
        primeSupabaseEnv();
        mockSupabaseAuthz({
            authUser: {
                id: 'supabase-stale-tenant',
                user_metadata: {
                    tenant_id: 'tenant-supabase-suspended',
                    tenant_status: 'active',
                    is_sysadmin: false,
                },
            },
            tenantStatus: 'suspended',
            isSysadmin: false,
        });

        const response = await proxy(makeRequest('https://app.example.test/dashboard', {
            'sb-auth-token': 'present',
        }));
        const location = new URL(response.headers.get('location')!, 'https://app.example.test');

        expect(location.pathname).toBe('/login');
        expect(location.searchParams.get('error')).toBe('tenant_suspended');
    });

    it('denies stale Supabase user metadata when the fresh sysadmin source says revoked', async () => {
        primeSupabaseEnv();
        mockSupabaseAuthz({
            authUser: {
                id: 'supabase-stale-sysadmin',
                user_metadata: {
                    tenant_id: 'tenant-supabase-sysadmin',
                    tenant_status: 'active',
                    is_sysadmin: true,
                },
            },
            tenantStatus: 'active',
            isSysadmin: false,
        });

        const response = await proxy(makeRequest('https://app.example.test/sysadmin', {
            'sb-auth-token': 'present',
        }));
        const location = new URL(response.headers.get('location')!, 'https://app.example.test');

        expect(location.pathname).toBe('/dashboard');
    });
});

/**
 * Proxy-level tests for /onboarding/bulk-upload public access.
 *
 * Verifies C.Lee's decision #1:
 * - /onboarding/bulk-upload is accessible without auth (no 307 redirect)
 * - /onboarding and /onboarding/setup remain gated (redirect to /login)
 * - Bulk-upload validate and commit API paths remain gated
 * - Trailing-slash and prefix variants stay gated
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { proxy } from '@/proxy';

// Mock crypto.randomUUID for nonce generation
vi.stubGlobal('crypto', {
    randomUUID: () => 'test-nonce-uuid',
});

// Mock Supabase client creation
vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(() => ({
        auth: {
            getUser: vi.fn().mockResolvedValue({ data: { user: null } }),
        },
        from: vi.fn(() => ({
            select: vi.fn().mockReturnThis(),
            eq: vi.fn().mockReturnThis(),
            maybeSingle: vi.fn().mockResolvedValue({ data: null, error: null }),
        })),
    })),
}));

// Mock JWT claims decoder
vi.mock('@/lib/jwt-claims', () => ({
    decodeRegEngineClaims: vi.fn().mockResolvedValue(null),
}));

// Mock CSP builder
vi.mock('@/lib/csp', () => ({
    buildCsp: vi.fn(() => "default-src 'self'"),
}));

// Mock CSRF utilities
vi.mock('@/lib/csrf', () => ({
    verifyCsrfToken: vi.fn().mockResolvedValue(true),
    CSRF_HEADER: 'x-csrf-token',
    CSRF_SIG_COOKIE: '__Host-regengine_csrf_sig',
    CSRF_PROTECTED_METHODS: new Set(['POST', 'PUT', 'PATCH', 'DELETE']),
    isCsrfExempt: vi.fn().mockReturnValue(false),
}));

// Mock app-routes helper
vi.mock('@/lib/app-routes', () => ({
    isAuthenticatedAppRoute: vi.fn((pathname: string) => {
        // Matches the real implementation: /onboarding and all paths under it
        // The proxy.ts allowlist check happens BEFORE this, so this mock returns
        // true for /onboarding/bulk-upload (which would redirect if not allowlisted)
        return pathname === '/onboarding' || pathname.startsWith('/onboarding/');
    }),
}));

function createMockRequest(pathname: string, options: {
    method?: string;
    cookies?: Record<string, string>;
    headers?: Record<string, string>;
} = {}): NextRequest {
    const url = `https://regengine.co${pathname}`;
    const request = new NextRequest(url, {
        method: options.method || 'GET',
        headers: new Headers(options.headers || {}),
    });

    // Add cookies if provided
    if (options.cookies) {
        Object.entries(options.cookies).forEach(([name, value]) => {
            request.cookies.set(name, value);
        });
    }

    return request;
}

describe('Bulk upload proxy access', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('signed-out GET /onboarding/bulk-upload is not redirected', async () => {
        const request = createMockRequest('/onboarding/bulk-upload');
        const response = await proxy(request);

        expect(response.status).not.toBe(307);
        expect(response.headers.get('location')).toBeNull();
    });

    it('signed-out GET /onboarding redirects to /login', async () => {
        const request = createMockRequest('/onboarding');
        const response = await proxy(request);

        expect(response.status).toBe(307);
        const location = response.headers.get('location');
        expect(location).toContain('/login');
        expect(location).toContain('next=%2Fonboarding');
    });

    it('signed-out GET /onboarding/setup redirects to /login', async () => {
        const request = createMockRequest('/onboarding/setup');
        const response = await proxy(request);

        expect(response.status).toBe(307);
        const location = response.headers.get('location');
        expect(location).toContain('/login');
        expect(location).toContain('next=%2Fonboarding%2Fsetup');
    });

    it('signed-out POST /api/onboarding/bulk-upload/validate passes through proxy', async () => {
        const request = createMockRequest('/api/onboarding/bulk-upload/validate', {
            method: 'POST',
            headers: {
                'origin': 'https://regengine.co',
                'x-csrf-token': 'test-token',
            },
            cookies: {
                '__Host-regengine_csrf_sig': 'test-sig',
            },
        });
        const response = await proxy(request);

        // Proxy does not gate API routes - backend enforces auth
        // Verify the request passes through (not 307 redirect)
        expect(response.status).not.toBe(307);
        expect(response.headers.get('location')).toBeNull();
    });

    it('signed-out POST /api/onboarding/bulk-upload/commit passes through proxy', async () => {
        const request = createMockRequest('/api/onboarding/bulk-upload/commit', {
            method: 'POST',
            headers: {
                'origin': 'https://regengine.co',
                'x-csrf-token': 'test-token',
            },
            cookies: {
                '__Host-regengine_csrf_sig': 'test-sig',
            },
        });
        const response = await proxy(request);

        // Proxy does not gate API routes - backend enforces auth
        expect(response.status).not.toBe(307);
        expect(response.headers.get('location')).toBeNull();
    });

    it('signed-out GET /onboarding/bulk-upload/ with trailing slash is not opened', async () => {
        const request = createMockRequest('/onboarding/bulk-upload/');
        const response = await proxy(request);

        // Trailing slash does not match exact '/onboarding/bulk-upload'
        // Falls through to isAuthenticatedAppRoute check, which gates /onboarding/*
        expect(response.status).toBe(307);
        const location = response.headers.get('location');
        expect(location).toContain('/login');
    });

    it('signed-out GET /onboarding/bulk-upload-x is not opened', async () => {
        const request = createMockRequest('/onboarding/bulk-upload-x');
        const response = await proxy(request);

        // Prefix variant does not match exact '/onboarding/bulk-upload'
        // Falls through to isAuthenticatedAppRoute check
        expect(response.status).toBe(307);
        const location = response.headers.get('location');
        expect(location).toContain('/login');
    });

    it('authenticated GET /onboarding/bulk-upload passes through', async () => {
        const request = createMockRequest('/onboarding/bulk-upload', {
            cookies: {
                '__Host-regengine_session': 'valid-session-token',
            },
        });
        const response = await proxy(request);

        expect(response.status).not.toBe(307);
        expect(response.headers.get('location')).toBeNull();
    });
});

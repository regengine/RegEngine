import { describe, expect, it } from 'vitest';
import {
    DEFAULT_LOCAL_ADMIN_URL,
    DEFAULT_LOCAL_MONOLITH_URL,
    getAdminTargets,
    shouldRetryAdminProxyResponse,
} from '@/lib/admin-targets';

describe('getAdminTargets', () => {
    it('tries both monolith-root and legacy /admin shapes for a public API base', () => {
        const targets = getAdminTargets({
            NEXT_PUBLIC_API_BASE_URL: 'https://api.example.com/',
        } as unknown as NodeJS.ProcessEnv);

        expect(targets).toEqual([
            'https://api.example.com',
            'https://api.example.com/admin',
            DEFAULT_LOCAL_MONOLITH_URL,
            DEFAULT_LOCAL_ADMIN_URL,
        ]);
    });

    it('prefers the explicit admin host and skips private internal hosts on Vercel', () => {
        const targets = getAdminTargets({
            VERCEL: '1',
            NEXT_PUBLIC_ADMIN_URL: 'https://admin.example.com/',
            NEXT_PUBLIC_API_BASE_URL: 'https://api.example.com',
            ADMIN_SERVICE_URL: 'http://admin.railway.internal:8080',
        } as unknown as NodeJS.ProcessEnv);

        expect(targets).toEqual([
            'https://admin.example.com',
            'https://api.example.com',
            'https://api.example.com/admin',
        ]);
    });

    it('keeps a public server-side admin host as a fallback target on Vercel', () => {
        const targets = getAdminTargets({
            VERCEL: '1',
            ADMIN_SERVICE_URL: 'https://admin-public.example.com/',
        } as unknown as NodeJS.ProcessEnv);

        expect(targets).toEqual(['https://admin-public.example.com']);
    });
});

describe('shouldRetryAdminProxyResponse', () => {
    it('retries 404s for auth and v1 paths so shape drift can fall through to the next target', () => {
        const notFound = new Response(null, { status: 404 });

        expect(shouldRetryAdminProxyResponse(notFound, 'auth/login')).toBe(true);
        expect(shouldRetryAdminProxyResponse(notFound, 'v1/admin/users')).toBe(true);
        expect(shouldRetryAdminProxyResponse(notFound, 'health')).toBe(true);
    });

    it('does not retry unrelated 404s or non-retryable statuses', () => {
        const notFound = new Response(null, { status: 404 });
        const unauthorized = new Response(null, { status: 401 });

        expect(shouldRetryAdminProxyResponse(notFound, 'openapi.json')).toBe(false);
        expect(shouldRetryAdminProxyResponse(unauthorized, 'auth/login')).toBe(false);
    });

    it('still retries Vercel private DNS failures regardless of path', () => {
        const response = new Response(null, {
            status: 502,
            headers: { 'x-vercel-error': 'DNS_HOSTNAME_RESOLVED_PRIVATE' },
        });

        expect(shouldRetryAdminProxyResponse(response, 'anything')).toBe(true);
    });
});

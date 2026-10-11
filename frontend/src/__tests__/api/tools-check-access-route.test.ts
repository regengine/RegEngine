import type { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGINAL_ENV = { ...process.env };

function makeGetRequest(cookieValue: string | undefined): NextRequest {
    return {
        cookies: {
            get: (name: string) =>
                name === 're_tool_access' && cookieValue !== undefined
                    ? { value: cookieValue }
                    : undefined,
        },
    } as unknown as NextRequest;
}

describe('tools check-access route', () => {
    beforeEach(() => {
        vi.resetModules();
        process.env = { ...ORIGINAL_ENV };
        process.env.ADMIN_SERVICE_URL = 'https://admin.example.com';
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        process.env = { ...ORIGINAL_ENV };
    });

    it('returns no access when the cookie is missing without calling the backend', async () => {
        vi.stubGlobal('fetch', vi.fn());
        const { GET } = await import('@/app/api/tools/check-access/route');

        const response = await GET(makeGetRequest(undefined));

        expect(await response.json()).toEqual({ hasAccess: false });
        expect(fetch).not.toHaveBeenCalled();
    });

    it('returns access when the backend verifies the cookie', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ hasAccess: true }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                }),
            ),
        );
        const { GET } = await import('@/app/api/tools/check-access/route');

        const response = await GET(makeGetRequest('valid.jwt.token'));

        expect(fetch).toHaveBeenCalledWith(
            'https://admin.example.com/api/v1/tools/check-access',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ token: 'valid.jwt.token' }),
            }),
        );
        expect(await response.json()).toEqual({ hasAccess: true });
    });

    it('returns no access and clears the cookie when the token is expired', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ hasAccess: false }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                }),
            ),
        );
        const { GET } = await import('@/app/api/tools/check-access/route');

        const response = await GET(makeGetRequest('expired.jwt.token'));

        expect(await response.json()).toEqual({ hasAccess: false });
        const setCookie = response.headers.get('set-cookie') ?? '';
        expect(setCookie).toContain('re_tool_access=');
        expect(setCookie).toMatch(/Max-Age=0/i);
    });

    it('fails closed when the backend is unreachable', async () => {
        vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
        const { GET } = await import('@/app/api/tools/check-access/route');

        const response = await GET(makeGetRequest('some.jwt.token'));

        expect(await response.json()).toEqual({ hasAccess: false });
    });

    it('treats any non-empty cookie as unverified until the backend confirms it', async () => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue(
                new Response(JSON.stringify({ hasAccess: false }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                }),
            ),
        );
        const { GET } = await import('@/app/api/tools/check-access/route');

        // A forged garbage cookie must not grant access.
        const response = await GET(makeGetRequest('forged-cookie-value'));

        expect(fetch).toHaveBeenCalled();
        expect(await response.json()).toEqual({ hasAccess: false });
    });
});

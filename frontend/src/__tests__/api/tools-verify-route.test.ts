import type { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGINAL_ENV = { ...process.env };

function makeRequest(body: Record<string, unknown>): NextRequest {
    return {
        json: vi.fn().mockResolvedValue(body),
    } as unknown as NextRequest;
}

describe('tools verify route', () => {
    beforeEach(() => {
        vi.resetModules();
        process.env = { ...ORIGINAL_ENV };
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ status: 'code_sent' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            }),
        ));
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        process.env = { ...ORIGINAL_ENV };
    });

    it('uses the configured admin service before the public API base', async () => {
        process.env.VERCEL = '1';
        process.env.NEXT_PUBLIC_API_BASE_URL = 'https://regengine.co';
        process.env.ADMIN_SERVICE_URL = 'https://regengine-production.up.railway.app';

        const { POST } = await import('@/app/api/tools/verify/route');

        await POST(makeRequest({
            action: 'verify',
            email: 'user@example.com',
            tool_name: 'ftl-checker',
        }));

        expect(fetch).toHaveBeenCalledWith(
            'https://regengine-production.up.railway.app/api/v1/tools/verify-email',
            expect.objectContaining({
                method: 'POST',
                redirect: 'manual',
                body: JSON.stringify({
                    email: 'user@example.com',
                    tool_name: 'ftl-checker',
                }),
            }),
        );
    });

    it('sets the cookie maxAge from the backend token lifetime', async () => {
        process.env.ADMIN_SERVICE_URL = 'https://admin.example.com';
        vi.mocked(fetch).mockResolvedValueOnce(new Response(
            JSON.stringify({ status: 'verified', token: 'jwt-token', expires_in_seconds: 7200 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
        const { POST } = await import('@/app/api/tools/verify/route');

        const response = await POST(makeRequest({
            action: 'confirm',
            email: 'user@example.com',
            code: '123456',
        }));

        const setCookie = response.headers.get('set-cookie') ?? '';
        expect(setCookie).toContain('re_tool_access=jwt-token');
        expect(setCookie).toMatch(/Max-Age=7200/i);
    });

    it('defaults the cookie to a 24-hour maxAge when the backend omits the lifetime', async () => {
        process.env.ADMIN_SERVICE_URL = 'https://admin.example.com';
        vi.mocked(fetch).mockResolvedValueOnce(new Response(
            JSON.stringify({ status: 'verified', token: 'jwt-token' }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
        const { POST } = await import('@/app/api/tools/verify/route');

        const response = await POST(makeRequest({
            action: 'confirm',
            email: 'user@example.com',
            code: '123456',
        }));

        const setCookie = response.headers.get('set-cookie') ?? '';
        expect(setCookie).toMatch(/Max-Age=86400/i);
        expect(setCookie).not.toMatch(/Max-Age=2592000/i);
    });

    it('caps an over-long backend lifetime at the 24-hour cookie maxAge', async () => {
        process.env.ADMIN_SERVICE_URL = 'https://admin.example.com';
        vi.mocked(fetch).mockResolvedValueOnce(new Response(
            JSON.stringify({ status: 'verified', token: 'jwt-token', expires_in_seconds: 2592000 }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
        ));
        const { POST } = await import('@/app/api/tools/verify/route');

        const response = await POST(makeRequest({
            action: 'confirm',
            email: 'user@example.com',
            code: '123456',
        }));

        const setCookie = response.headers.get('set-cookie') ?? '';
        expect(setCookie).toMatch(/Max-Age=86400/i);
    });

    it('rejects redirects without forwarding a Location response', async () => {
        process.env.ADMIN_SERVICE_URL = 'https://admin.example.com';
        vi.mocked(fetch).mockResolvedValueOnce(new Response(null, {
            status: 307,
            headers: { location: 'http://127.0.0.1/internal' },
        }));
        const { POST } = await import('@/app/api/tools/verify/route');

        const response = await POST(makeRequest({
            action: 'confirm',
            email: 'user@example.com',
            code: '123456',
        }));

        expect(response.status).toBe(502);
        expect(response.headers.get('location')).toBeNull();
    });
});

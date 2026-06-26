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
                body: JSON.stringify({
                    email: 'user@example.com',
                    tool_name: 'ftl-checker',
                }),
            }),
        );
    });
});

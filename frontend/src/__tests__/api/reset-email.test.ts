import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { NextRequest } from 'next/server';

const resetPasswordForEmail = vi.fn();
const applyCookies = vi.fn((response) => response);

vi.mock('@/lib/supabase/route-client', () => ({
    getSupabaseRouteConfig: vi.fn(() => ({ url: 'https://test.supabase.co', anonKey: 'anon-key' })),
    createSupabaseRouteClient: vi.fn(() => ({
        supabase: {
            auth: { resetPasswordForEmail },
        },
        applyCookies,
    })),
}));

import { POST } from '@/app/api/auth/supabase/reset-email/route';

function makeRequest(body: unknown, url = 'https://app.regengine.io/api/auth/supabase/reset-email') {
    return {
        url,
        json: vi.fn(async () => body),
    } as unknown as NextRequest;
}

describe('/api/auth/supabase/reset-email', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        resetPasswordForEmail.mockResolvedValue({ error: null });
    });

    it('derives redirectTo from request origin instead of attacker input', async () => {
        const response = await POST(
            makeRequest({
                email: 'user@example.com',
                redirectTo: 'https://evil.example/auth/callback?next=/reset-password',
            }),
        );

        expect(response.status).toBe(200);
        expect(resetPasswordForEmail).toHaveBeenCalledWith('user@example.com', {
            redirectTo: 'https://app.regengine.io/auth/callback?next=/reset-password',
        });
    });

    it('does not require client-provided redirectTo', async () => {
        const response = await POST(makeRequest({ email: 'user@example.com' }));

        expect(response.status).toBe(200);
        expect(resetPasswordForEmail).toHaveBeenCalledWith('user@example.com', {
            redirectTo: 'https://app.regengine.io/auth/callback?next=/reset-password',
        });
    });

    it('rejects requests without an email', async () => {
        const response = await POST(makeRequest({ redirectTo: 'https://app.regengine.io/auth/callback' }));

        expect(response.status).toBe(400);
        expect(resetPasswordForEmail).not.toHaveBeenCalled();
    });
});

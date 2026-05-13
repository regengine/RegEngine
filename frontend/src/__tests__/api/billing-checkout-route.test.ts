import type { NextRequest } from 'next/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/billing/checkout/route';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'https://billing.example.test',
}));

function makeRequest(body: Record<string, unknown>): NextRequest {
    return {
        json: vi.fn().mockResolvedValue(body),
        cookies: {
            get: vi.fn().mockReturnValue(undefined),
        },
    } as unknown as NextRequest;
}

describe('billing checkout route', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ checkout_url: 'https://checkout.stripe.test/cs', session_id: 'cs_test' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            }),
        ));
    });

    it('does not put checkout session IDs in success URL query params', async () => {
        await POST(makeRequest({ plan_id: 'growth&debug=true', billing_period: 'monthly' }));

        const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
        const payload = JSON.parse(fetchMock.mock.calls[0][1].body as string);

        expect(payload.success_url).toBe('https://regengine.co/signup?checkout=success&plan=growth%26debug%3Dtrue');
        expect(payload.success_url).not.toContain('session_id=');
        expect(payload.success_url).not.toContain('{CHECKOUT_SESSION_ID}');
    });
});

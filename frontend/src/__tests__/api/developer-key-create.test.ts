// @vitest-environment node
import { beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { POST } from '@/app/api/developer/portal/keys/route';
const mocks = vi.hoisted(() => ({ context: vi.fn(), insert: vi.fn(), order: vi.fn() }));
vi.mock('@/app/api/developer/portal/_utils', () => ({
    getDeveloperPortalContext: mocks.context,
    withDeveloperCookies: (_context: unknown, response: Response) => response,
}));
beforeEach(() => {
    vi.clearAllMocks();
    mocks.context.mockResolvedValue({ ok: true, profile: { id: 'dev-1' }, client: { supabase: {
        from: () => ({ insert: mocks.insert, select: () => ({ eq: () => ({ order: mocks.order }) }) }),
    } } });
});
const request = () => new NextRequest('http://localhost/api/developer/portal/keys', {
    method: 'POST', body: JSON.stringify({ name: 'CI' }),
});
it('preserves the one-time key response when creation succeeds but metadata refresh fails', async () => {
    mocks.insert.mockResolvedValue({ error: null });
    mocks.order.mockResolvedValue({ error: { message: 'Unavailable' } });
    const response = await POST(request());
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body.rawKey).toMatch(/^rge_test_/);
    expect(body.keys).toBeUndefined();
    expect(body.keysRefreshFailed).toBe(true);
    expect(mocks.insert).toHaveBeenCalledTimes(1);
});
it('returns a failure without refreshing when insertion fails', async () => {
    mocks.insert.mockResolvedValue({ error: { message: 'Unavailable' } });
    const response = await POST(request());
    expect(response.status).toBe(502);
    expect((await response.json()).rawKey).toBeUndefined();
    expect(mocks.order).not.toHaveBeenCalled();
});

it('returns the key and metadata on successful creation', async () => {
    mocks.insert.mockResolvedValue({ error: null });
    mocks.order.mockResolvedValue({ data: [{ id: 'key-1', name: 'CI' }], error: null });
    const response = await POST(request());
    const body = await response.json();
    expect(response.status).toBe(200);
    expect(body.rawKey).toMatch(/^rge_test_/);
    expect(body.keys).toEqual([{ id: 'key-1', name: 'CI' }]);
    expect(body.keysRefreshFailed).toBeUndefined();
});
it('does not insert when authentication requires step-up', async () => {
    mocks.context.mockResolvedValue({ ok: false, response: new Response(
        JSON.stringify({ detail: { code: 'requires_step_up' } }), { status: 403 },
    ) });
    const response = await POST(request());
    expect(response.status).toBe(403);
    expect(mocks.insert).not.toHaveBeenCalled();
    expect(mocks.order).not.toHaveBeenCalled();
});

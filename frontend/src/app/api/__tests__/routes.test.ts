import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@/lib/admin-targets', () => ({
  getAdminTargets: () => ['https://admin.regengine.test'],
  shouldRetryAdminProxyResponse: () => false,
}));

import { POST as adminPost } from '@/app/api/admin/[...path]/route';
import { GET as reviewItemsGet } from '@/app/api/review/items/route';

describe('security-sensitive API route contracts', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('rejects tenant creation without a caller session before any upstream fetch', async () => {
    const request = new NextRequest('https://regengine.co/api/admin/v1/admin/tenants', {
      method: 'POST',
      body: JSON.stringify({ name: 'Acme Corp' }),
      headers: { 'content-type': 'application/json' },
    });

    const response = await adminPost!(request, {
      params: Promise.resolve({ path: ['v1', 'admin', 'tenants'] }),
    });

    expect(response.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('transforms the real review route response while forwarding only the opaque session', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({
      items: [{
        review_id: 'review-1',
        doc_hash: 'sha256:abc',
        confidence_score: 0.8,
        created_at: '2026-08-03T00:00:00Z',
        text_preview: 'sample',
      }],
    }), { status: 200, headers: { 'content-type': 'application/json' } }));
    const request = new NextRequest('https://regengine.co/api/review/items', {
      headers: { cookie: '__Host-regengine_session=opaque-session' },
    });

    const response = await reviewItemsGet(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual([expect.objectContaining({
      id: 'review-1',
      source_text: 'sample',
    })]);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get('cookie')).toBe('__Host-regengine_session=opaque-session');
    expect(headers.has('x-admin-key')).toBe(false);
  });
});

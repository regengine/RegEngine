import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { GET } from '@/app/api/ingestion/[...path]/route';

const TENANT = '11111111-1111-4111-8111-111111111111';
const OTHER_TENANT = '22222222-2222-4222-8222-222222222222';
const ADMIN_URL = 'https://admin.example.test';
const INGESTION_URL = 'https://ingestion.example.test';

function requestFor(path: string, tenant = TENANT): NextRequest {
  const cookies: Record<string, string> = {
    '__Host-regengine_session': 'owner-session',
    re_tenant_id: tenant,
    re_api_key: 'old-key', // pragma: allowlist secret
  };
  return {
    method: 'GET',
    url: `https://regengine.test/api/ingestion/${path}`,
    headers: new Headers({ origin: 'https://regengine.test' }),
    cookies: {
      get: (name: string) => cookies[name] ? { name, value: cookies[name] } : undefined,
      getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
    },
  } as unknown as NextRequest;
}

describe('SEL-409 workspace session proxy', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.stubEnv('NEXT_PUBLIC_ADMIN_URL', ADMIN_URL);
    vi.stubEnv('NEXT_PUBLIC_INGESTION_URL', INGESTION_URL);
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it.each([
    'api/v1/records',
    'api/v1/rules',
    'api/v1/exceptions',
    'api/v1/requests',
    'api/v1/ingest/csv',
  ])('forwards only the verified owner session to %s', async (path) => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ tenant_id: TENANT }), {
        status: 200, headers: { 'content-type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200, headers: { 'content-type': 'application/json' },
      }));

    const response = await GET!(requestFor(path), { params: Promise.resolve({ path: path.split('/') }) });
    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${ADMIN_URL}/auth/me`);
    expect(String(fetchMock.mock.calls[1][0])).toBe(`${INGESTION_URL}/${path}`);
    const headers = new Headers(fetchMock.mock.calls[1][1].headers);
    expect(headers.get('cookie')).toBe('__Host-regengine_session=owner-session');
    expect(headers.get('x-tenant-id')).toBe(TENANT);
    expect(headers.get('x-regengine-api-key')).toBeNull();
    expect(headers.get('authorization')).toBeNull();
  });

  it('rejects a forged tenant cookie before calling ingestion', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ tenant_id: TENANT }), {
      status: 200, headers: { 'content-type': 'application/json' },
    }));
    const path = 'api/v1/records';
    const response = await GET!(requestFor(path, OTHER_TENANT), {
      params: Promise.resolve({ path: path.split('/') }),
    });
    expect(response.status).toBe(403);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// @vitest-environment node
import { afterEach, expect, it, vi } from 'vitest';
import { GET } from '@/app/api/health/route';

afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

it('uses dependency readiness for ingestion and propagates failure', async () => {
  vi.stubEnv('INGESTION_SERVICE_URL', 'https://ingestion.example/');
  vi.stubEnv('ADMIN_SERVICE_URL', 'https://admin.example');
  const fetchMock = vi.fn(async (url: string) => new Response('{}', { status: url.includes('/readiness') ? 503 : 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const response = await GET();
  expect(response.status).toBe(503);
  expect(fetchMock).toHaveBeenCalledWith('https://ingestion.example/readiness', expect.anything());
  expect(fetchMock).toHaveBeenCalledWith('https://admin.example/health', expect.anything());
  expect((await response.json()).services).toContainEqual(expect.objectContaining({ name: 'ingestion', status: 'unhealthy', code: 503 }));
});

it('marks an unreachable ingestion service degraded', async () => {
  vi.stubEnv('INGESTION_SERVICE_URL', 'https://ingestion.example');
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('timeout')));
  expect((await GET()).status).toBe(503);
});

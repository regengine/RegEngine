import { describe, expect, it } from 'vitest';

import { GET } from '@/app/api/openapi.json/route';
import { publicOpenApiSpec } from '@/lib/public-openapi';

describe('public OpenAPI spec', () => {
  it('publishes the curated public ingest contract with rate-limit headers', () => {
    expect(publicOpenApiSpec.openapi).toBe('3.0.3');
    expect(publicOpenApiSpec.paths['/api/v1/webhooks/ingest']).toBeDefined();

    const ingestHeaders = publicOpenApiSpec.paths['/api/v1/webhooks/ingest'].post.responses['200'].headers;
    expect(Object.keys(ingestHeaders)).toEqual(
      expect.arrayContaining([
        'X-RateLimit-Limit',
        'X-RateLimit-Remaining',
        'X-RateLimit-Reset',
        'X-RateLimit-Tenant',
        'X-RateLimit-Scope',
      ]),
    );
  });

  it('does not expose internal service routes in the public spec', () => {
    const serialized = JSON.stringify(publicOpenApiSpec);

    expect(serialized).not.toMatch(/\/admin|\/kernel|\/nlp|\/debug/i);
    expect(Object.keys(publicOpenApiSpec.paths).every((path) => path.startsWith('/api/v1/'))).toBe(true);
  });

  it('serves the same spec from /api/openapi.json', async () => {
    const response = await GET();
    const body = await response.json();

    expect(response.headers.get('cache-control')).toContain('s-maxage=3600');
    expect(body).toEqual(publicOpenApiSpec);
  });
});

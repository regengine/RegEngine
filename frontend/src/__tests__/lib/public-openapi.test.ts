import { describe, expect, it } from 'vitest';

import { GET as getApiOpenApi } from '@/app/api/openapi.json/route';
import { GET as getRootOpenApi } from '@/app/openapi.json/route';
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

    expect(serialized).not.toMatch(/\/admin|\/internal|\/kernel|\/nlp|\/debug/i);
    expect(serialized).not.toMatch(/x-admin-key|bearer|localhost/i);
    expect(Object.keys(publicOpenApiSpec.paths).every((path) => path.startsWith('/api/v1/'))).toBe(true);
    expect(publicOpenApiSpec.components.parameters.TenantHeader.required).toBe(false);
    expect(publicOpenApiSpec.components.parameters.TenantHeader.description).toMatch(/optional tenant assertion/i);
  });

  it('serves one identical spec from both public URLs', async () => {
    const apiResponse = await getApiOpenApi();
    const rootResponse = await getRootOpenApi();
    const apiBody = await apiResponse.json();
    const rootBody = await rootResponse.json();

    expect(apiResponse.headers.get('cache-control')).toContain('s-maxage=3600');
    expect(rootResponse.headers.get('cache-control')).toContain('s-maxage=3600');
    expect(apiBody).toEqual(publicOpenApiSpec);
    expect(rootBody).toEqual(publicOpenApiSpec);
  });
});

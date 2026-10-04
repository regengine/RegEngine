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

  it('documents GET /records for the key-bound workspace', () => {
    const records = publicOpenApiSpec.paths['/api/v1/records'].get;

    expect(records.operationId).toBe('listRecords');
    const params = records.parameters.map((p) => p.name);
    expect(params).toEqual(
      expect.arrayContaining(['tlc', 'event_type', 'status', 'source_system', 'start_date', 'end_date', 'limit', 'offset']),
    );
    // The workspace comes from the key: no tenant parameter on this route.
    expect(params).not.toContain('tenant_id');
    expect(records.responses['200'].content['application/json'].schema.$ref).toBe('#/components/schemas/RecordsResponse');

    const response = publicOpenApiSpec.components.schemas.RecordsResponse;
    expect(response.required).toEqual(['tenant_id', 'events', 'total']);
  });

  it('requires the X-Webhook-Signature and Idempotency-Key headers on ingest', () => {
    const ingest = publicOpenApiSpec.paths['/api/v1/webhooks/ingest'].post;
    const refs = ingest.parameters.map((p) => p.$ref);

    expect(refs).toContain('#/components/parameters/WebhookSignature');
    expect(refs).toContain('#/components/parameters/IdempotencyKey');
    // X-Tenant-ID is not part of the documented ingest call.
    expect(refs).not.toContain('#/components/parameters/TenantHeader');

    const signature = publicOpenApiSpec.components.parameters.WebhookSignature;
    expect(signature.name).toBe('X-Webhook-Signature');
    expect(signature.in).toBe('header');
    expect(signature.required).toBe(true);
    expect(signature.description).toMatch(/HMAC-SHA256/);
  });

  it('describes the timestamp window and the 422 a future event causes', () => {
    const ingest = publicOpenApiSpec.paths['/api/v1/webhooks/ingest'].post;
    const timestamp = publicOpenApiSpec.components.schemas.IngestEvent.properties.timestamp.description;

    expect(ingest.responses['422'].$ref).toBe('#/components/responses/ValidationFailed');
    expect(publicOpenApiSpec.components.responses.ValidationFailed.description).toMatch(/nothing is stored/i);
    expect(timestamp).toMatch(/older than 90 days[^.]*rejected/);
    expect(timestamp).toMatch(/24 hours ahead[^.]*422/);
    expect(timestamp).not.toMatch(/24 hours ahead[^.]*rejected/);
  });

  it('documents 402 and 403 and ties each operation to a scope', () => {
    const ingest = publicOpenApiSpec.paths['/api/v1/webhooks/ingest'].post;
    expect(ingest.responses['402'].$ref).toBe('#/components/responses/PaymentRequired');
    expect(ingest.responses['403'].$ref).toBe('#/components/responses/Forbidden');
    expect(publicOpenApiSpec.paths['/api/v1/fda/export/all'].get.responses['402']).toBeDefined();

    const scopes = {
      '/api/v1/webhooks/ingest': ['post', 'webhooks.ingest'],
      '/api/v1/webhooks/recent': ['get', 'webhooks.read'],
      '/api/v1/webhooks/chain/verify': ['get', 'webhooks.read'],
      '/api/v1/records': ['get', 'records.read'],
      '/api/v1/records/ingestion-runs': ['get', 'records.read'],
      '/api/v1/fda/export/all': ['get', 'fda.export'],
    } as const;
    const paths = publicOpenApiSpec.paths as Record<string, Record<string, Record<string, unknown>>>;
    for (const [path, [method, scope]] of Object.entries(scopes)) {
      expect(paths[path][method]['x-required-scope'], `${method} ${path}`).toBe(scope);
      expect(JSON.stringify(paths[path][method].responses), `${method} ${path} responses`).toContain('Forbidden');
    }

    // Every public operation declares a scope; none is left implied.
    for (const [path, operations] of Object.entries(paths)) {
      for (const [method, operation] of Object.entries(operations)) {
        expect(operation['x-required-scope'], `${method} ${path}`).toBeTruthy();
      }
    }
  });

  it('does not publish numeric rate limits or promise headers on a 429', () => {
    const spec = publicOpenApiSpec;
    const limitHeader = spec.paths['/api/v1/webhooks/ingest'].post.responses['200'].headers['X-RateLimit-Limit'];

    expect(limitHeader.schema).not.toHaveProperty('example');
    expect(spec.components.responses.RateLimited).not.toHaveProperty('headers');
    expect(spec.components.responses.RateLimited.description).toMatch(/not reliably sent/i);
  });

  it('does not expose internal service routes in the public spec', () => {
    const serialized = JSON.stringify(publicOpenApiSpec);

    expect(serialized).not.toMatch(/\/admin|\/internal|\/kernel|\/nlp|\/debug/i);
    expect(serialized).not.toMatch(/x-admin-key|bearer|localhost/i);
    expect(Object.keys(publicOpenApiSpec.paths).every((path) => path.startsWith('/api/v1/'))).toBe(true);
    expect(publicOpenApiSpec.components.parameters.TenantHeader.required).toBe(false);
    expect(publicOpenApiSpec.components.parameters.TenantHeader.description).toMatch(/optional tenant assertion/i);
  });

  it('documents the runtime nested error envelope without dropping bespoke fields', () => {
    const schema = publicOpenApiSpec.components.schemas.ErrorResponse;
    expect(schema.required).toEqual(['error']);
    expect(schema.properties.error.type).toBe('object');
    expect(schema.properties.error.required).toEqual(['type', 'message']);
    expect(schema.properties.error.additionalProperties).toBe(true);
    expect(schema.properties).not.toHaveProperty('detail');
    for (const response of Object.values(publicOpenApiSpec.components.responses)) {
      expect(response.content['application/json'].schema.$ref).toBe('#/components/schemas/ErrorResponse');
    }
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

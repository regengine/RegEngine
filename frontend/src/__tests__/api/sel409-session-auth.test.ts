import { describe, expect, it } from 'vitest';

import { acceptsWorkspaceSession } from '@/lib/ingestion-session-routes';

describe('SEL-409 ingestion proxy route policy', () => {
  it.each([
    'api/v1/records',
    'api/v1/rules',
    'api/v1/exceptions',
    'api/v1/requests',
    'api/v1/epcis/events',
    'v1/ingest/url',
    'ingest/csv',
  ])('accepts a verified session on %s', (path) => {
    expect(acceptsWorkspaceSession(path)).toBe(true);
  });

  it.each([
    'api/v1/products',
    'api/v1/settings',
    'api/v1/sources',
    'api/v1/discovery',
    'api/v1/ingest/status',
  ])('keeps caller API-key authentication on %s', (path) => {
    expect(acceptsWorkspaceSession(path)).toBe(false);
  });
});

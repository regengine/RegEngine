const rateLimitHeaders = {
  'X-RateLimit-Limit': {
    description: 'Maximum requests allowed in the current window for this tenant and scope.',
    schema: { type: 'integer', example: 75 },
  },
  'X-RateLimit-Remaining': {
    description: 'Requests remaining in the current window.',
    schema: { type: 'integer', example: 74 },
  },
  'X-RateLimit-Reset': {
    description: 'Unix timestamp for the next rate-limit window boundary.',
    schema: { type: 'integer', example: 1778522430 },
  },
  'X-RateLimit-Tenant': {
    description: 'Tenant ID whose bucket was applied.',
    schema: { type: 'string', example: '11111111-1111-1111-1111-111111111111' },
  },
  'X-RateLimit-Scope': {
    description: 'Rate-limit bucket scope for this request.',
    schema: { type: 'string', example: 'webhooks.ingest' },
  },
} as const;

export const publicOpenApiSpec = {
  openapi: '3.0.3',
  info: {
    title: 'RegEngine Public API',
    version: '1.0.0',
    description:
      'Curated public API surface for FSMA 204 traceability ingestion, record lookup, and export workflows. Public callers authenticate only with X-RegEngine-API-Key. Browser and human administration uses opaque session cookies and is not part of this specification. X-Tenant-ID is an optional assertion that must match the credential-bound tenant; it is not an authentication mechanism.',
  },
  servers: [
    {
      url: 'https://regengine.co',
      description: 'Production',
    },
  ],
  tags: [
    { name: 'Webhook Ingestion', description: 'Create tenant-scoped CTE/KDE records.' },
    { name: 'Records', description: 'Read canonical ingestion-run records.' },
    { name: 'FDA Export', description: 'Export FDA-oriented sortable records where configured data supports the request.' },
  ],
  security: [{ RegEngineApiKey: [] }],
  paths: {
    '/api/v1/webhooks/ingest': {
      post: {
        tags: ['Webhook Ingestion'],
        operationId: 'ingestWebhookEvents',
        summary: 'Ingest traceability events',
        description:
          'Accept CTE events from external systems and persist tenant-scoped records after validation.',
        parameters: [
          { $ref: '#/components/parameters/TenantHeader' },
          { $ref: '#/components/parameters/IdempotencyKey' },
        ],
        requestBody: {
          required: true,
          content: {
            'application/json': {
              schema: { $ref: '#/components/schemas/WebhookPayload' },
            },
          },
        },
        responses: {
          '200': {
            description: 'Events accepted or rejected with per-event status.',
            headers: rateLimitHeaders,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/IngestResponse' },
              },
            },
          },
          '400': { $ref: '#/components/responses/BadRequest' },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/webhooks/recent': {
      get: {
        tags: ['Webhook Ingestion'],
        operationId: 'listRecentWebhookEvents',
        summary: 'List recent traceability events',
        parameters: [
          { $ref: '#/components/parameters/TenantQuery' },
          {
            name: 'limit',
            in: 'query',
            schema: { type: 'integer', minimum: 1, maximum: 100, default: 10 },
          },
        ],
        responses: {
          '200': {
            description: 'Recent tenant events.',
            headers: rateLimitHeaders,
            content: {
              'application/json': {
                schema: { type: 'object', additionalProperties: true },
              },
            },
          },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '404': { $ref: '#/components/responses/NotFound' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/webhooks/chain/verify': {
      get: {
        tags: ['Webhook Ingestion'],
        operationId: 'verifyWebhookChain',
        summary: 'Verify a tenant hash chain',
        parameters: [{ $ref: '#/components/parameters/TenantQuery' }],
        responses: {
          '200': {
            description: 'Hash-chain verification result.',
            headers: rateLimitHeaders,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/ChainVerifyResponse' },
              },
            },
          },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '404': { $ref: '#/components/responses/NotFound' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/records/ingestion-runs': {
      get: {
        tags: ['Records'],
        operationId: 'listIngestionRuns',
        summary: 'List ingestion runs',
        parameters: [{ $ref: '#/components/parameters/TenantQuery' }],
        responses: {
          '200': {
            description: 'Tenant ingestion runs.',
            headers: rateLimitHeaders,
            content: {
              'application/json': {
                schema: { type: 'object', additionalProperties: true },
              },
            },
          },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/fda/export/all': {
      get: {
        tags: ['FDA Export'],
        operationId: 'exportAllFdaRecords',
        summary: 'Export all FDA response records',
        parameters: [
          { $ref: '#/components/parameters/TenantQuery' },
          {
            name: 'format',
            in: 'query',
            schema: { type: 'string', enum: ['csv', 'json', 'zip'], default: 'csv' },
          },
        ],
        responses: {
          '200': {
            description: 'Export file or JSON package.',
            headers: rateLimitHeaders,
            content: {
              'text/csv': { schema: { type: 'string', format: 'binary' } },
              'application/json': { schema: { type: 'object', additionalProperties: true } },
              'application/zip': { schema: { type: 'string', format: 'binary' } },
            },
          },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
  },
  components: {
    securitySchemes: {
      RegEngineApiKey: {
        type: 'apiKey',
        in: 'header',
        name: 'X-RegEngine-API-Key',
      },
    },
    parameters: {
      TenantHeader: {
        name: 'X-Tenant-ID',
        in: 'header',
        required: false,
        description:
          'Optional tenant assertion. When supplied, it must match the tenant bound to X-RegEngine-API-Key.',
        schema: { type: 'string', format: 'uuid' },
      },
      TenantQuery: {
        name: 'tenant_id',
        in: 'query',
        required: true,
        schema: { type: 'string', format: 'uuid' },
      },
      IdempotencyKey: {
        name: 'Idempotency-Key',
        in: 'header',
        required: true,
        schema: { type: 'string', minLength: 8, maxLength: 255 },
      },
    },
    responses: {
      BadRequest: {
        description: 'Request validation failed.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      Unauthorized: {
        description: 'Missing or invalid API key.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      NotFound: {
        description: 'Resource not found or not visible to this tenant.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      RateLimited: {
        description: 'Rate limit exceeded.',
        headers: rateLimitHeaders,
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
    },
    schemas: {
      WebhookPayload: {
        type: 'object',
        required: ['source', 'events'],
        properties: {
          tenant_id: { type: 'string', format: 'uuid' },
          source: { type: 'string', example: 'erp' },
          events: {
            type: 'array',
            minItems: 1,
            items: { $ref: '#/components/schemas/IngestEvent' },
          },
        },
      },
      IngestEvent: {
        type: 'object',
        required: ['cte_type', 'traceability_lot_code', 'product_description', 'timestamp'],
        properties: {
          cte_type: { type: 'string', example: 'receiving' },
          traceability_lot_code: { type: 'string', example: '00012345678901-LOT-2026-001' },
          product_description: { type: 'string', example: 'Romaine Lettuce' },
          quantity: { type: 'number', example: 500 },
          unit_of_measure: { type: 'string', example: 'cases' },
          location_name: { type: 'string', example: 'Distribution Center #4' },
          timestamp: { type: 'string', format: 'date-time' },
          kdes: { type: 'object', additionalProperties: true },
        },
      },
      IngestResponse: {
        type: 'object',
        required: ['accepted', 'rejected', 'total', 'events'],
        properties: {
          accepted: { type: 'integer' },
          rejected: { type: 'integer' },
          total: { type: 'integer' },
          events: {
            type: 'array',
            items: {
              type: 'object',
              additionalProperties: true,
            },
          },
        },
      },
      ChainVerifyResponse: {
        type: 'object',
        required: ['tenant_id', 'chain_valid', 'chain_length', 'errors'],
        properties: {
          tenant_id: { type: 'string', format: 'uuid' },
          chain_valid: { type: 'boolean' },
          chain_length: { type: 'integer' },
          errors: { type: 'array', items: { type: 'string' } },
        },
      },
      ErrorResponse: {
        type: 'object',
        required: ['error'],
        properties: {
          error: {
            type: 'object',
            required: ['type', 'message'],
            properties: {
              type: { type: 'string' },
              message: { type: 'string' },
            },
            additionalProperties: true,
          },
        },
        additionalProperties: true,
      },
    },
  },
} as const;

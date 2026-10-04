const rateLimitHeaders = {
  'X-RateLimit-Limit': {
    description: 'Maximum requests allowed in the current window for this tenant and scope.',
    schema: { type: 'integer' },
  },
  'X-RateLimit-Remaining': {
    description: 'Requests remaining in the current window.',
    schema: { type: 'integer' },
  },
  'X-RateLimit-Reset': {
    description: 'Unix timestamp for the next rate-limit window boundary.',
    schema: { type: 'integer', example: 1778522430 },
  },
  'X-RateLimit-Tenant': {
    description: 'Tenant ID whose bucket was applied.',
    schema: { type: 'string', format: 'uuid' },
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
      'Curated public API surface for FSMA 204 traceability ingestion, record lookup, and export workflows. Public callers authenticate only with X-RegEngine-API-Key, which RegEngine issues on request together with the workspace ID and the ingest signing secret. Each operation lists the scope it needs in x-required-scope. Scopes do not make a key read-only: some operations outside this specification accept any valid tenant key. Browser and human administration uses opaque session cookies and is not part of this specification. X-Tenant-ID is an optional assertion that must match the credential-bound tenant; omit it. It is not an authentication mechanism.',
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
          'Accept CTE events from external systems and persist tenant-scoped records after validation. Requires the webhooks.ingest scope and an active subscription. The body must be signed with X-Webhook-Signature. Accepted events are written permanently and may be billed. A valid request returns 200 even when some events are rejected; check each event status. Repeating an Idempotency-Key with the same bytes within 24 hours replays the first successful response; repeating it with different bytes returns 409.',
        'x-required-scope': 'webhooks.ingest',
        parameters: [
          { $ref: '#/components/parameters/WebhookSignature' },
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
          '402': { $ref: '#/components/responses/PaymentRequired' },
          '403': { $ref: '#/components/responses/Forbidden' },
          '422': { $ref: '#/components/responses/ValidationFailed' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/webhooks/recent': {
      get: {
        tags: ['Webhook Ingestion'],
        operationId: 'listRecentWebhookEvents',
        summary: 'List recent traceability events',
        description: 'Requires the webhooks.read scope.',
        'x-required-scope': 'webhooks.read',
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
          '403': { $ref: '#/components/responses/Forbidden' },
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
        description: 'Requires the webhooks.read scope.',
        'x-required-scope': 'webhooks.read',
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
          '403': { $ref: '#/components/responses/Forbidden' },
          '404': { $ref: '#/components/responses/NotFound' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/records': {
      get: {
        tags: ['Records'],
        operationId: 'listRecords',
        summary: 'List canonical traceability events',
        description:
          'Search canonical events for the workspace bound to the API key. Requires the records.read scope. Do not send tenant_id or X-Tenant-ID: the workspace comes from the key. Pages with limit and offset; total is the number of matching events.',
        'x-required-scope': 'records.read',
        parameters: [
          { name: 'tlc', in: 'query', description: 'Filter by traceability lot code.', schema: { type: 'string' } },
          { name: 'event_type', in: 'query', description: 'Filter by CTE type, for example receiving.', schema: { type: 'string' } },
          { name: 'status', in: 'query', description: 'Record status.', schema: { type: 'string', default: 'active' } },
          { name: 'source_system', in: 'query', description: 'Filter by ingestion source.', schema: { type: 'string' } },
          { name: 'start_date', in: 'query', description: 'Events at or after this timestamp.', schema: { type: 'string', format: 'date-time' } },
          { name: 'end_date', in: 'query', description: 'Events at or before this timestamp.', schema: { type: 'string', format: 'date-time' } },
          { name: 'limit', in: 'query', schema: { type: 'integer', maximum: 500, default: 50 } },
          { name: 'offset', in: 'query', schema: { type: 'integer', default: 0 } },
        ],
        responses: {
          '200': {
            description: 'Matching events for the workspace.',
            headers: rateLimitHeaders,
            content: {
              'application/json': {
                schema: { $ref: '#/components/schemas/RecordsResponse' },
              },
            },
          },
          '401': { $ref: '#/components/responses/Unauthorized' },
          '403': { $ref: '#/components/responses/Forbidden' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/records/ingestion-runs': {
      get: {
        tags: ['Records'],
        operationId: 'listIngestionRuns',
        summary: 'List ingestion runs',
        description: 'Requires the records.read scope.',
        'x-required-scope': 'records.read',
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
          '403': { $ref: '#/components/responses/Forbidden' },
          '429': { $ref: '#/components/responses/RateLimited' },
        },
      },
    },
    '/api/v1/fda/export/all': {
      get: {
        tags: ['FDA Export'],
        operationId: 'exportAllFdaRecords',
        summary: 'Export all FDA response records',
        description: 'Requires the fda.export scope and an active subscription.',
        'x-required-scope': 'fda.export',
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
          '402': { $ref: '#/components/responses/PaymentRequired' },
          '403': { $ref: '#/components/responses/Forbidden' },
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
          'Optional tenant assertion. When supplied, it must match the tenant bound to X-RegEngine-API-Key; a different value is refused with 403. Omit it.',
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
        description:
          'Use a new value for every new payload. The same key with the same bytes replays the first successful response for 24 hours; the same key with different bytes returns 409.',
        schema: { type: 'string', minLength: 8, maxLength: 255 },
      },
      WebhookSignature: {
        name: 'X-Webhook-Signature',
        in: 'header',
        required: true,
        description:
          'sha256= followed by the HMAC-SHA256 hex digest of the exact request body bytes, keyed with the signing secret RegEngine issues. A missing or wrong signature returns 401.',
        schema: { type: 'string', example: 'sha256=<64 hex characters>' },
      },
    },
    responses: {
      BadRequest: {
        description: 'Bad request, for example a missing Idempotency-Key header.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      Unauthorized: {
        description: 'Missing or invalid API key.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      PaymentRequired: {
        description: 'The workspace has no active subscription.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      Forbidden: {
        description:
          'The key lacks the scope this operation requires, or X-Tenant-ID or tenant_id names a different workspace than the key.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      NotFound: {
        description: 'Resource not found or not visible to this tenant.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      ValidationFailed: {
        description:
          'The body failed validation, for example an event timestamp more than 24 hours ahead or a malformed event. The whole request is refused and nothing is stored. The details are in error.details.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
      RateLimited: {
        description:
          'Rate limit exceeded. Stop for 60 seconds, then retry. Retry-After and rate-limit headers are not reliably sent on a 429.',
        content: { 'application/json': { schema: { $ref: '#/components/schemas/ErrorResponse' } } },
      },
    },
    schemas: {
      WebhookPayload: {
        type: 'object',
        required: ['source', 'events'],
        properties: {
          tenant_id: {
            type: 'string',
            format: 'uuid',
            description: 'Omit. The workspace comes from the API key, and a different value is refused.',
          },
          source: { type: 'string', example: 'erp' },
          events: {
            type: 'array',
            minItems: 1,
            maxItems: 500,
            items: { $ref: '#/components/schemas/IngestEvent' },
          },
        },
      },
      IngestEvent: {
        type: 'object',
        required: ['cte_type', 'traceability_lot_code', 'product_description', 'quantity', 'unit_of_measure', 'timestamp'],
        properties: {
          cte_type: {
            type: 'string',
            enum: [
              'harvesting',
              'cooling',
              'initial_packing',
              'first_land_based_receiving',
              'shipping',
              'receiving',
              'transformation',
            ],
            example: 'receiving',
          },
          traceability_lot_code: { type: 'string', minLength: 3, example: 'TEST-00012345678901-LOT-001' },
          product_description: { type: 'string', example: 'Romaine Lettuce' },
          quantity: { type: 'number', exclusiveMinimum: true, minimum: 0, example: 500 },
          unit_of_measure: { type: 'string', example: 'cases' },
          location_name: {
            type: 'string',
            description: 'Each event needs at least one location: location_name, location_gln, or a location KDE.',
            example: 'Distribution Center #4',
          },
          location_gln: { type: 'string', description: 'GS1 Global Location Number, 13 digits.' },
          timestamp: {
            type: 'string',
            format: 'date-time',
            description:
              'An event older than 90 days comes back with status "rejected" inside a 200. An event more than 24 hours ahead fails the whole request with a 422 and nothing is stored.',
          },
          kdes: {
            type: 'object',
            additionalProperties: true,
            description:
              'Key Data Elements for the event type. A receiving event needs receive_date, receiving_location, immediate_previous_source, reference_document and tlc_source_reference. The required keys for every event type are listed at https://regengine.co/docs/api#required-kdes.',
          },
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
      RecordsResponse: {
        type: 'object',
        required: ['tenant_id', 'events', 'total'],
        properties: {
          tenant_id: { type: 'string', format: 'uuid' },
          events: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                event_id: { type: 'string', format: 'uuid' },
                event_type: { type: 'string', example: 'receiving' },
                traceability_lot_code: { type: 'string' },
                product_reference: { type: 'string' },
                quantity: { type: 'number' },
                unit_of_measure: { type: 'string' },
                from_facility_reference: { type: 'string', nullable: true },
                to_facility_reference: { type: 'string', nullable: true },
                event_timestamp: { type: 'string', format: 'date-time', nullable: true },
                source_system: { type: 'string', example: 'webhook_api' },
                status: { type: 'string', example: 'active' },
                confidence_score: { type: 'number' },
                schema_version: { type: 'string' },
                created_at: { type: 'string', format: 'date-time', nullable: true },
              },
              additionalProperties: true,
            },
          },
          total: { type: 'integer' },
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

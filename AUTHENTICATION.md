# RegEngine Authentication

RegEngine uses API key-based authentication to secure all endpoints.

## Overview

All RegEngine API endpoints (except `/health` and `/metrics`) require authentication via an API key passed in the `X-RegEngine-API-Key` header.

## Getting Started (Local Development)

### 1. Start the services

```bash
docker-compose up -d
```

### 2. Initialize demo API keys

```bash
bash scripts/init-demo-keys.sh
```

This will create two API keys:
- **Demo Key**: 100 requests/minute, scopes: read, ingest
- **Admin Key**: 1000 requests/minute, scopes: read, ingest, admin

The keys will be printed to the console and saved to `.api-keys` (gitignored).

### 3. Use the API keys

```bash
# Load keys from file
source .api-keys

# Ingest a document
curl -X POST http://localhost:8000/ingest/url \
  -H 'Content-Type: application/json' \
  -H "X-RegEngine-API-Key: $DEMO_KEY" \
  -d '{"url": "https://example.com/doc.pdf", "source_system": "demo"}'

# Query opportunities
curl "http://localhost:8300/opportunities/gaps?j1=US&j2=EU" \
  -H "X-RegEngine-API-Key: $DEMO_KEY"
```

## API Key Management

### Creating API Keys

Use the Admin API to create new keys:

```bash
curl -X POST http://localhost:8400/admin/keys \
  -H 'Content-Type: application/json' \
  -H 'X-Admin-Key: your-admin-master-key' \
  -d '{
    "name": "Production Key",
    "rate_limit_per_minute": 500,
    "scopes": ["read", "ingest"],
    "expires_at": "2025-12-31T23:59:59Z"
  }'
```

Response:
```json
{
  "api_key": "rge_xxxxxxxxxxxxxxxxxxxxx",
  "key_id": "rge_xxxxxxxxx",
  "name": "Production Key",
  "created_at": "2025-01-15T10:30:00Z",
  "expires_at": "2025-12-31T23:59:59Z",
  "rate_limit_per_minute": 500,
  "scopes": ["read", "ingest"],
  "warning": "Store this key securely. It will not be shown again."
}
```

**IMPORTANT**: Save the `api_key` value immediately. It cannot be retrieved later.

### Listing API Keys

```bash
curl http://localhost:8400/admin/keys \
  -H 'X-Admin-Key: your-admin-master-key'
```

### Revoking API Keys

```bash
curl -X DELETE http://localhost:8400/admin/keys/rge_xxxxxxxxx \
  -H 'X-Admin-Key: your-admin-master-key'
```

## Rate Limiting

Each API key has a configurable rate limit (requests per minute). When exceeded:

- **HTTP Status**: `429 Too Many Requests`
- **Header**: `Retry-After: 60`
- **Response**: `{"detail": "Rate limit exceeded"}`

Rate limit windows are rolling 60-second windows.

## Scopes

API keys support the following scopes:

- **read**: Query APIs (opportunities, gaps, arbitrage)
- **ingest**: Document ingestion APIs
- **admin**: Administrative operations (key management)

## Production Configuration

### Admin Master Key

The admin master key is used to manage API keys. **Change it immediately in production!**

Set via environment variable:

```bash
export ADMIN_MASTER_KEY="your-secure-random-key"
```

Or in docker-compose:

```yaml
environment:
  ADMIN_MASTER_KEY: ${ADMIN_MASTER_KEY}
```

**NEVER commit the admin master key to version control.**

### API Key Storage

The current implementation uses in-memory storage for API keys. For production:

**Recommended upgrades**:
1. **Redis** - For distributed, persistent key storage
2. **Database** - PostgreSQL/MySQL with encrypted key storage
3. **Secrets Manager** - AWS Secrets Manager, HashiCorp Vault, etc.

See `shared/auth.py` for the `APIKeyStore` implementation.

## Security Best Practices

### For API Consumers

1. **Never commit API keys** to version control
2. **Use environment variables** to store keys
3. **Rotate keys regularly** (every 90 days recommended)
4. **Use separate keys** for dev/staging/prod
5. **Limit scopes** to minimum required permissions
6. **Set expiration dates** on keys when possible

### For Operators

1. **Change admin master key** from default
2. **Enable HTTPS** in production (TLS 1.2+)
3. **Monitor rate limits** for abuse detection
4. **Audit key usage** via logs
5. **Implement key rotation** policies
6. **Use secrets management** infrastructure
7. **Enable network isolation** (VPC, security groups)

## Troubleshooting

### 401 Unauthorized

**Cause**: Missing or invalid API key

**Solutions**:
- Verify the `X-RegEngine-API-Key` header is present
- Check that the key hasn't been revoked
- Ensure the key hasn't expired
- Verify the key value is correct (no extra spaces/newlines)

### 429 Too Many Requests

**Cause**: Rate limit exceeded

**Solutions**:
- Wait 60 seconds before retrying
- Request a higher rate limit key
- Implement exponential backoff in your client

### 403 Forbidden

**Cause**: Insufficient scopes for the requested operation

**Solutions**:
- Verify your key has the required scopes
- Request a new key with appropriate scopes

## API Reference

### Authentication Header

All authenticated endpoints require:

```
X-RegEngine-API-Key: rge_xxxxxxxxxxxxxxxxxxxxx
```

### Protected Endpoints

| Service | Endpoint | Required Scope |
|---------|----------|----------------|
| Ingestion | `POST /ingest/url` | `ingest` |
| Opportunity | `GET /opportunities/arbitrage` | `read` |
| Opportunity | `GET /opportunities/gaps` | `read` |
| Admin | `POST /admin/keys` | N/A (uses admin master key) |
| Admin | `GET /admin/keys` | N/A (uses admin master key) |
| Admin | `DELETE /admin/keys/:id` | N/A (uses admin master key) |

### Unprotected Endpoints

| Service | Endpoint | Description |
|---------|----------|-------------|
| All | `GET /health` | Health check |
| All | `GET /metrics` | Prometheus metrics |

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ X-RegEngine-API-Key: rge_xxxxx
       ▼
┌─────────────────────────────────┐
│   FastAPI Dependency Injection  │
│   (require_api_key middleware)  │
└────────────┬────────────────────┘
             │
             ▼
      ┌──────────────┐
      │ APIKeyStore  │
      │ (in-memory)  │
      └──────────────┘
             │
             ├── Validate hash (constant-time)
             ├── Check expiration
             ├── Check enabled status
             └── Enforce rate limit
```

## Future Enhancements

- [ ] OAuth 2.0 / JWT token support
- [ ] Role-based access control (RBAC)
- [ ] IP whitelisting
- [ ] Key rotation automation
- [ ] Usage analytics dashboard
- [ ] Webhook authentication
- [ ] Multi-factor authentication (MFA) for admin

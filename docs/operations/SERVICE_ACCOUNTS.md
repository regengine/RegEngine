# Service Accounts Guide

## Overview

Service accounts provide programmatic access to RegEngine APIs for automated integrations, CI/CD pipelines, and backend-to-backend communication.

## Creating a Service Account

### Via Admin API (Recommended)

```bash
# Create service account API key
curl -X POST http://localhost:8400/admin/keys \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CI/CD Pipeline",
    "tenant_id": "YOUR_TENANT_UUID",
    "scopes": ["read", "ingest"],
    "rate_limit_per_minute": 120,
    "expires_at": "2027-01-01T00:00:00Z"
  }'
```

**Response:**
```json
{
  "api_key": "rge_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "key_id": "key_abc123",
  "name": "CI/CD Pipeline",
  "warning": "Store this key securely. It will not be shown again."
}
```

### Scopes

| Scope | Description |
|-------|-------------|
| `read` | Read regulations, analysis, graph data |
| `ingest` | Upload documents for processing |
| `write` | Modify tenant data |
| `admin` | Tenant administration |

## Using Service Account Keys

### API Authentication

```bash
# Include in X-RegEngine-API-Key header
curl -X GET http://localhost:8200/v1/labels/search \
  -H "X-RegEngine-API-Key: rge_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  -H "X-Tenant-ID: YOUR_TENANT_UUID"
```

### Service-to-Service Communication

Service accounts are automatically detected when `is_service_account: true` is set in the JWT payload or API key metadata. This enables:

- Bypass of interactive auth flows
- Rate limit escalation for bulk operations
- Audit log attribution to the service identity

## Managing Service Accounts

### List Keys
```bash
curl -X GET http://localhost:8400/admin/keys \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY"
```

### Revoke Key
```bash
curl -X DELETE http://localhost:8400/admin/keys/{key_id} \
  -H "X-Admin-Key: $ADMIN_MASTER_KEY"
```

## Best Practices

1. **Least Privilege**: Request only required scopes
2. **Rotation**: Set expiration and rotate keys quarterly
3. **Secrets Management**: Store keys in vault/secrets manager
4. **Audit**: Monitor API key usage in audit logs
5. **Naming**: Use descriptive names (e.g., "GitHub Actions - FSMA Sync")

## Security Considerations

- API keys are hashed before storage (SHA-256)
- Keys cannot be retrieved after creation
- All access is logged in the audit trail
- Revocation takes effect immediately

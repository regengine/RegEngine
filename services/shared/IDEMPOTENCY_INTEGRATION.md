# Idempotency Middleware Integration

Integration guide for `services/shared/idempotency.py` to support idempotent POST endpoints.

## Quick Start

### 1. Add middleware to FastAPI app

**Admin service** (`services/admin/main.py` or `services/admin/app/main.py`):

```python
from shared.idempotency import IdempotencyMiddleware

app.add_middleware(IdempotencyMiddleware)
```

**Ingestion service** (`services/ingestion/main.py`):

```python
from shared.idempotency import IdempotencyMiddleware

app.add_middleware(IdempotencyMiddleware)
```

The middleware should be added AFTER error handlers but BEFORE routing, so it sees the actual response.

### 2. (Optional) Add dependency for strict validation

For endpoints that require the `Idempotency-Key` header:

```python
from fastapi import APIRouter, Depends
from shared.idempotency import IdempotencyDependency

router = APIRouter()
strict_idempotency = IdempotencyDependency(strict=True)

@router.post("/v1/admin/keys")
async def create_api_key(
    idempotency_key: str | None = Depends(strict_idempotency),
    # ... other dependencies
):
    """Create an API key. Requires Idempotency-Key for safe retries."""
    pass
```

## How It Works

### Request Handling

1. **Incoming request**: Middleware checks for `Idempotency-Key` header
2. **Cache hit**: If key exists in Redis, return cached response immediately
3. **Cache miss**: Let request proceed to route handler
4. **Success response**: Cache 2xx responses in Redis with 24h TTL
5. **Non-2xx**: Don't cache errors; let client retry naturally

### Key Features

- **Graceful degradation**: If Redis is unavailable, requests proceed without caching
- **Binary-safe**: Handles text/JSON/binary response bodies
- **Long TTL**: 24 hours allows safe client retries
- **Status filtering**: Only caches 2xx responses (200-299)
- **Request/response logging**: Structured logs track cache hits/misses

## Client Usage

### Example: Admin API - Create tenant

```bash
curl -X POST http://localhost:8400/v1/admin/tenants \
  -H "Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000" \
  -H "Content-Type: application/json" \
  -d '{"name": "acme-corp"}'

# First request: 201 Created
# Immediate retry with same key: 201 Created (cached response)
# After 24h: 201 Created (new response)
```

### Example: Ingestion API - Webhook ingest

```bash
curl -X POST http://localhost:8002/api/v1/webhooks/ingest \
  -H "Idempotency-Key: webhook-12345-20260412" \
  -H "Content-Type: application/json" \
  -d '{"event": "fda_recall", "data": {...}}'
```

## Redis Configuration

Middleware reads `REDIS_URL` from environment (default: `redis://redis:6379/0`).

Override if needed:

```python
from shared.idempotency import IdempotencyMiddleware

app.add_middleware(
    IdempotencyMiddleware,
    redis_url="redis://redis:6379/3"  # Use database 3
)
```

## Monitoring

Check Redis cache usage:

```bash
redis-cli
> KEYS "idempotency:*"
> TTL idempotency:550e8400-e29b-41d4-a716-446655440000
```

Logs to watch:

```
idempotency_cache_hit - Request matched cached response
idempotency_cached - Response was cached
idempotency_redis_unavailable - Redis connection failed
idempotency_cache_read_error - Error reading cache
idempotency_cache_write_error - Error writing cache
```

## Error Handling

- **Missing key**: Allowed (middleware skips caching)
- **Redis down**: Request proceeds without caching, no error to client
- **Cache read error**: Proceed with request, skip caching
- **Cache write error**: Return original response, log warning
- **Invalid key format**: Request proceeds normally (middleware doesn't validate format)

For strict validation (require key), use `IdempotencyDependency(strict=True)`.

## Testing

Unit test example:

```python
import pytest
from fastapi.testclient import TestClient
from shared.idempotency import IdempotencyMiddleware

def test_idempotent_post(app):
    app.add_middleware(IdempotencyMiddleware)
    client = TestClient(app)
    
    idempotency_key = "test-key-123"
    
    # First request
    resp1 = client.post(
        "/v1/admin/keys",
        json={"name": "key1"},
        headers={"Idempotency-Key": idempotency_key}
    )
    assert resp1.status_code == 201
    
    # Retry with same key
    resp2 = client.post(
        "/v1/admin/keys",
        json={"name": "key1"},
        headers={"Idempotency-Key": idempotency_key}
    )
    assert resp2.status_code == 201
    assert resp2.json() == resp1.json()  # Exact same response
```

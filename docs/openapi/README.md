# OpenAPI Specifications

The JSON files in this directory are **point-in-time snapshots** of each service's
OpenAPI spec. They may be stale — FastAPI auto-generates the live spec at runtime.

## Live specs (authoritative)

Access `/openapi.json` on each running service:

| Service | Production URL |
|---------|---------------|
| Admin | `https://regengine-production.up.railway.app/openapi.json` |
| Ingestion | `https://believable-respect-production-2fb3.up.railway.app/openapi.json` |
| Compliance | `https://intelligent-essence-production.up.railway.app/openapi.json` |
| Graph | `[graph-service-url]/openapi.json` |

## Regenerating snapshots

Run each service locally and save the output:

```bash
for svc in admin ingestion compliance graph; do
  curl -s http://localhost:800X/openapi.json | python3 -m json.tool > docs/openapi/${svc}-api.json
done
```

Ports: admin=8001, ingestion=8002, graph=8003, compliance=8500.

## Current snapshot status

| Spec | Lines | Notes |
|------|-------|-------|
| admin-api.json | 3,655 | Likely current |
| compliance-api.json | 1,020 | Likely current |
| graph-api.json | 3,500 | Likely current |
| ingestion-api.json | 945 | **Stale** — service has 48 routers but spec is only 945 lines |

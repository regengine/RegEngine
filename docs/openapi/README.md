# OpenAPI Specifications

## Live specs (authoritative)

RegEngine is one consolidated FastAPI app, so there is a single spec — not one
per service. The published spec is a **static asset generated from the app and
drift-checked in CI**, not a live endpoint:

| Spec | URL | What it is |
|------|-----|-----------|
| Public API | `https://regengine.co/openapi.json` | Curated external surface served from `frontend/src/lib/public-openapi.ts` |
| Public API alias | `https://regengine.co/api/openapi.json` | Byte-equivalent application route for existing callers |

The backend does **not** serve `/openapi.json` in production. `server/main.py`
sets `openapi_url=None if _is_prod`, alongside `docs_url` and `redoc_url`, so
`https://regengine-production.up.railway.app/openapi.json` returns 404 by
design. Hitting the app directly for a spec only works in a non-production
environment (local, or a preview with `ENVIRONMENT` unset).

## Updating the published spec

```bash
cd frontend
npm test -- --run src/__tests__/lib/public-openapi.test.ts
```

`openapi-public-spec.yml` runs the contract test for every public-spec or docs
change. Both public URLs must return the same object, and the test rejects
administrative, internal, Bearer, retired-header, and localhost content.

## Archived snapshots

`admin-api.json`, `compliance-api.json`, `graph-api.json`, and
`ingestion-api.json` are **pre-consolidation artifacts** — point-in-time dumps
from the six-service topology that was retired in May 2026. They are kept for
historical diffing only. They are not regenerated, nothing validates them, and
they should not be treated as a description of the current API. Use the
published spec above instead. They live under `docs/archive/openapi/` so stale
authentication contracts cannot be mistaken for active documentation.

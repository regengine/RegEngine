# OpenAPI Specifications

## Live specs (authoritative)

RegEngine is one consolidated FastAPI app, so there is a single spec — not one
per service. The published spec is a **static asset generated from the app and
drift-checked in CI**, not a live endpoint:

| Spec | URL | What it is |
|------|-----|-----------|
| Full generated spec | `https://regengine.co/openapi.json` | Every route the generator exports, served from `frontend/public/openapi.json` |
| Curated public API | `https://regengine.co/api/openapi.json` | Hand-scoped external surface (`frontend/src/app/api/openapi.json`) |

The backend does **not** serve `/openapi.json` in production. `server/main.py`
sets `openapi_url=None if _is_prod`, alongside `docs_url` and `redoc_url`, so
`https://regengine-production.up.railway.app/openapi.json` returns 404 by
design. Hitting the app directly for a spec only works in a non-production
environment (local, or a preview with `ENVIRONMENT` unset).

## Regenerating the published spec

```bash
python scripts/generate_openapi.py            # writes frontend/public/openapi.json
python scripts/generate_openapi.py --check    # what CI runs; non-zero if stale
```

`openapi-public-spec.yml` runs `--check` on every PR touching the ingestion or
shared code, so a route change that is not regenerated fails CI. Commit the
regenerated file in the same PR as the route change.

## Snapshots in this directory

`admin-api.json`, `compliance-api.json`, `graph-api.json`, and
`ingestion-api.json` are **pre-consolidation artifacts** — point-in-time dumps
from the six-service topology that was retired in May 2026. They are kept for
historical diffing only. They are not regenerated, nothing validates them, and
they should not be treated as a description of the current API. Use the
published spec above instead.
